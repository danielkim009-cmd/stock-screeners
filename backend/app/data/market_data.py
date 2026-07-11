"""
OHLCV data fetcher using yfinance (default) or Tiingo, with a per-trading-day
on-disk cache so a given universe is downloaded from Yahoo at most once per
calendar day.
"""
from __future__ import annotations

import logging
import os
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx
import pandas as pd
import yfinance as yf

log = logging.getLogger("stock_screener.market_data")


# --------------------------------------------------------------------------- #
#  Daily OHLCV disk cache + yfinance thread-safety
# --------------------------------------------------------------------------- #
#
# Cache: every successfully fetched frame is pickled under
# .ohlcv_cache/<YYYY-MM-DD>/<TICKER>_<interval>.pkl together with the start
# date of the window it covers. Any later request that same day whose window
# is covered by the cached one is served by slicing the cached frame instead
# of hitting Yahoo again. This makes repeated screen runs fast and — more
# importantly — deterministic (identical requests see identical data), and
# because it lives on disk it survives uvicorn --reload restarts. Tickers
# Yahoo returned nothing for (inside an otherwise successful batch) get a
# negative entry (df=None) so they aren't re-attempted on every request.
# Old date folders are pruned automatically.

_CACHE_ROOT = Path(
    os.environ.get("OHLCV_CACHE_DIR")
    or Path(__file__).resolve().parents[2] / ".ohlcv_cache"
)
_CACHE_KEEP_DAYS = 3
_cache_pruned_for: Optional[str] = None  # date the prune already ran for

# yfinance's yf.download() passes results through a MODULE-GLOBAL dict
# (yfinance.shared._DFS): it resets it, populates it from worker threads,
# then reads results back out of it. Two overlapping yf.download() calls in
# one process therefore corrupt each other — one request can literally
# receive another ticker's prices. FastAPI runs sync routes on a threadpool,
# so every yf.download() in this process is serialized behind this lock.
# (Single-ticker fetches use yf.Ticker(...).history() instead, which does not
# touch the shared dict and never needs to wait on this lock.)
_YF_DOWNLOAD_LOCK = threading.Lock()


def _today_str() -> str:
    return datetime.today().strftime("%Y-%m-%d")


def _cache_path(ticker: str, interval: str, date_str: str) -> Path:
    safe = ticker.replace("/", "_").upper()
    return _CACHE_ROOT / date_str / f"{safe}_{interval}.pkl"


def _prune_old_cache_dirs(today: str) -> None:
    """Delete cache folders older than _CACHE_KEEP_DAYS (runs once per day)."""
    global _cache_pruned_for
    if _cache_pruned_for == today:
        return
    _cache_pruned_for = today
    cutoff = (datetime.today() - timedelta(days=_CACHE_KEEP_DAYS)).strftime("%Y-%m-%d")
    try:
        if not _CACHE_ROOT.exists():
            return
        for child in _CACHE_ROOT.iterdir():
            # only touch folders that look like YYYY-MM-DD
            if child.is_dir() and len(child.name) == 10 and child.name < cutoff:
                shutil.rmtree(child, ignore_errors=True)
    except Exception as e:
        log.warning("ohlcv cache prune failed: %s", e)


def _normalize_ohlcv(df: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
    """
    Normalize a yfinance frame to the shape the rest of the app expects:
    tz-naive DatetimeIndex + flat Open/High/Low/Close/Volume columns, NaNs
    dropped. Returns None if the frame is empty/unusable.
    """
    if df is None or df.empty:
        return None
    df = df.copy()
    df.index = pd.to_datetime(df.index)
    if getattr(df.index, "tz", None) is not None:
        # match yf.download()'s daily-interval output (ignore_tz=True)
        df.index = df.index.tz_localize(None)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    try:
        df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    except KeyError:
        return None
    return df if not df.empty else None


def _cache_read(
    ticker: str, interval: str, start_str: str, date_str: str
) -> tuple[bool, Optional[pd.DataFrame]]:
    """
    Look up today's cache entry for (ticker, interval).

    Returns (hit, df):
      (False, None) — no usable entry (not cached, or cached window too short)
      (True,  df)   — cached frame sliced to the requested window
      (True,  None) — negative hit: Yahoo had no data for this ticker today
    """
    path = _cache_path(ticker, interval, date_str)
    try:
        if not path.exists():
            return False, None
        entry = pd.read_pickle(path)
        if not isinstance(entry, dict) or "start" not in entry:
            return False, None
        if entry["start"] > start_str:  # cached window starts too late
            return False, None
        df = entry.get("df")
        if df is None:
            return True, None
        # Slice to the requested window so a hit from a longer cached window
        # returns exactly what a fresh fetch of this window would have.
        df = df[df.index >= pd.Timestamp(start_str)]
        if df.empty:
            return True, None
        return True, df
    except Exception as e:
        log.warning("ohlcv cache read failed for %s: %s", ticker, e)
        return False, None


def _cache_write(
    ticker: str,
    interval: str,
    start_str: str,
    date_str: str,
    df: Optional[pd.DataFrame],
) -> None:
    """
    Store today's frame for (ticker, interval). df=None records a negative
    entry ("Yahoo had nothing for this ticker today"). Never clobbers an
    existing entry that covers a longer window, and never replaces a positive
    entry with a negative one. Writes are atomic (tmp file + os.replace).
    """
    try:
        path = _cache_path(ticker, interval, date_str)
        if path.exists():
            try:
                existing = pd.read_pickle(path)
                if (
                    isinstance(existing, dict)
                    and existing.get("start", "9999-99-99") <= start_str
                    and (existing.get("df") is not None or df is None)
                ):
                    return  # existing entry is at least as good — keep it
            except Exception:
                pass  # unreadable entry — overwrite it
        _prune_old_cache_dirs(date_str)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}.{threading.get_ident()}")
        pd.to_pickle({"start": start_str, "df": df}, tmp)
        os.replace(tmp, path)
    except Exception as e:
        log.warning("ohlcv cache write failed for %s: %s", ticker, e)


def _reset_yfinance_session() -> bool:
    """
    Force yfinance to establish a brand-new Yahoo Finance session (fresh
    cookie + crumb), in-process — no server restart required.

    yfinance's `YfData` is a process-wide singleton that caches a cookie and
    "crumb" (Yahoo's auth token) for the lifetime of the process. If that
    cached state goes stale — rate-limited, expired, or otherwise rejected —
    every subsequent call silently fails until the singleton's state is
    cleared. This reproduces what a full process restart accomplishes (a
    fresh session with no stale cookie/crumb), without needing one.

    Returns True if the reset was applied, False if it failed for any reason
    (best-effort — callers should proceed with their normal retry either way).
    """
    try:
        from curl_cffi import requests as curl_requests
        from yfinance.data import YfData

        yfdata = YfData()  # returns the existing process-wide singleton
        with yfdata._cookie_lock:
            yfdata._cookie = None
            yfdata._crumb = None
        yfdata._set_session(curl_requests.Session(impersonate="chrome"))

        # Also drop the on-disk cached cookie so it isn't immediately reloaded
        # back into the fresh session — yfinance persists it under the fixed
        # key "curlCffi" (see YfData._save_cookie_curlCffi/_load_cookie_curlCffi
        # in yfinance/data.py), not the cookie-strategy name.
        try:
            from yfinance import cache as yf_cache
            yf_cache.get_cookie_cache().store("curlCffi", None)
        except Exception:
            pass

        log.warning("yfinance session reset: cleared cached cookie/crumb and issued a fresh session")
        return True
    except Exception as e:
        log.warning("yfinance session reset failed (continuing without it): %s", e)
        return False


def fetch_ohlcv(
    ticker: str,
    period_days: int = 365,
    interval: str = "1d",
    use_cache: bool = True,
) -> Optional[pd.DataFrame]:
    """
    Fetch OHLCV data for a single ticker.

    Served from the daily disk cache when a covering window is already there
    (e.g. after a bulk screen run cached the whole universe); otherwise
    fetched via yf.Ticker(...).history(), which — unlike yf.download() — does
    not pass results through yfinance's module-global dict and is therefore
    safe to run concurrently with a bulk screen download.

    Returns DataFrame with columns: Open, High, Low, Close, Volume
    or None on failure.
    """
    end = datetime.today() + timedelta(days=1)
    start = end - timedelta(days=period_days + 1)
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")
    date_str = _today_str()

    if use_cache:
        hit, df = _cache_read(ticker, interval, start_str, date_str)
        if hit:
            return df  # may be None (known no-data) — same contract as a miss

    try:
        df = yf.Ticker(ticker).history(
            start=start_str,
            end=end_str,
            interval=interval,
            auto_adjust=True,
            actions=False,
            raise_errors=False,
        )
        df = _normalize_ohlcv(df)
        if df is None:
            return None
        if use_cache:
            _cache_write(ticker, interval, start_str, date_str, df)
        return df
    except Exception:
        return None


def fetch_bulk_ohlcv(
    tickers: list[str],
    period_days: int = 365,
    batch_size: int = 100,
    max_retries: int = 2,
    use_cache: bool = True,
) -> dict[str, pd.DataFrame]:
    """
    Fetch OHLCV for multiple tickers in batches using yfinance.
    Batching avoids silent failures from overly large single requests.

    Caching: each ticker is served from the daily disk cache when a covering
    window is already there, so a given universe is downloaded from Yahoo at
    most once per calendar day — repeated screen runs are fast and see
    identical data. Only cache misses are fetched live.

    Thread-safety: all yf.download() calls are serialized behind a
    process-wide lock (yf.download() is NOT thread-safe — see
    _YF_DOWNLOAD_LOCK). A request that blocks on the lock re-checks the cache
    afterwards, so concurrent first-of-the-day requests don't double-fetch.

    Each batch is retried (with backoff) if yfinance returns nothing, since an
    empty/exception response is frequently a transient rate-limit (429) or a
    stale auth "crumb" in a long-running process rather than a real absence of
    data. On the first failure anywhere in the run, this also force-resets
    yfinance's process-wide session (see `_reset_yfinance_session`) — the same
    fix a server restart provides, applied automatically and in-process, so a
    stuck session self-heals without manual intervention. Failures are logged
    instead of silently swallowed, and a run that produces no data at all
    (0 of N tickers, nothing cached) raises so callers/API responses don't
    misreport a data outage as "0 candidates today".

    Returns {ticker: DataFrame}.
    """
    end = datetime.today() + timedelta(days=1)
    start = end - timedelta(days=period_days + 1)
    start_str = start.strftime("%Y-%m-%d")
    end_str   = end.strftime("%Y-%m-%d")
    date_str  = _today_str()

    result: dict[str, pd.DataFrame] = {}

    def _take_from_cache(remaining: list[str]) -> list[str]:
        """Move cache hits into result; return the tickers still missing."""
        misses = []
        for t in remaining:
            hit, df = _cache_read(t, "1d", start_str, date_str)
            if hit:
                if df is not None:
                    result[t] = df
                # negative hit: known no-data today — skip, don't re-fetch
            else:
                misses.append(t)
        return misses

    to_fetch = list(tickers)
    if use_cache:
        to_fetch = _take_from_cache(to_fetch)
        if not to_fetch:
            return result
        if len(result):
            log.info(
                "fetch_bulk_ohlcv: %d/%d tickers served from cache; fetching %d from Yahoo",
                len(result), len(tickers), len(to_fetch),
            )

    with _YF_DOWNLOAD_LOCK:
        # A concurrent request may have fetched (and cached) these while we
        # waited on the lock — re-check before hitting Yahoo.
        if use_cache:
            to_fetch = _take_from_cache(to_fetch)
        if not to_fetch:
            return result

        failed_batches = 0
        total_batches = (len(to_fetch) + batch_size - 1) // batch_size
        session_was_reset = False

        for i in range(0, len(to_fetch), batch_size):
            batch = to_fetch[i : i + batch_size]
            raw = None
            last_err: Optional[Exception] = None

            for attempt in range(max_retries + 1):
                try:
                    raw = yf.download(
                        batch,
                        start=start_str,
                        end=end_str,
                        auto_adjust=True,
                        progress=False,
                        group_by="ticker",
                    )
                    if raw is not None and not raw.empty:
                        break
                    raw = None
                except Exception as e:
                    last_err = e
                    raw = None

                if attempt < max_retries:
                    # First failure anywhere in this run: the most common cause is
                    # a stuck yfinance session (stale/rate-limited cookie+crumb)
                    # that will keep failing every batch until cleared — so reset
                    # it once, in-process, rather than waiting for someone to
                    # restart the server. Cheap even if this wasn't the cause.
                    if not session_was_reset:
                        session_was_reset = True
                        _reset_yfinance_session()
                    # Backoff — gives a transient rate-limit time to clear too.
                    time.sleep(2 * (attempt + 1))

            if raw is None:
                failed_batches += 1
                log.warning(
                    "fetch_bulk_ohlcv: batch %d/%d (%d tickers) returned no data after %d attempt(s)%s",
                    i // batch_size + 1, total_batches, len(batch), max_retries + 1,
                    f" — last error: {last_err}" if last_err else "",
                )
                continue

            # Single ticker: yfinance may return a flat frame or one still
            # grouped under the ticker name
            if len(batch) == 1:
                ticker = batch[0]
                try:
                    sub = raw
                    if isinstance(sub.columns, pd.MultiIndex) and ticker in sub.columns.get_level_values(0):
                        sub = sub[ticker]
                    df = _normalize_ohlcv(sub)
                    if df is not None:
                        result[ticker] = df
                        if use_cache:
                            _cache_write(ticker, "1d", start_str, date_str, df)
                    elif use_cache:
                        _cache_write(ticker, "1d", start_str, date_str, None)
                except Exception as e:
                    log.warning("fetch_bulk_ohlcv: failed to parse single-ticker batch %s: %s", ticker, e)
            else:
                for ticker in batch:
                    df = None
                    try:
                        df = _normalize_ohlcv(raw[ticker])
                    except Exception:
                        df = None
                    if df is not None:
                        result[ticker] = df
                        if use_cache:
                            _cache_write(ticker, "1d", start_str, date_str, df)
                    elif use_cache:
                        # The batch succeeded but Yahoo had nothing for this
                        # ticker — remember that for the rest of the day.
                        _cache_write(ticker, "1d", start_str, date_str, None)

        if failed_batches == total_batches and total_batches > 0 and not result:
            raise RuntimeError(
                f"fetch_bulk_ohlcv: all {total_batches} batch(es) failed to return data "
                f"for {len(to_fetch)} tickers (and nothing was cached), even after an "
                f"automatic yfinance session "
                f"reset{' (attempted)' if session_was_reset else ' (not attempted — no failures triggered it, so this is likely a real outage or network issue)'}. "
                f"Yahoo Finance may be down or blocking this IP outright — check "
                f"https://query1.finance.yahoo.com/v1/test/getcrumb directly, or retry shortly."
            )
        elif failed_batches:
            log.warning(
                "fetch_bulk_ohlcv: %d of %d batches failed; proceeding with partial data (%d/%d tickers fetched)",
                failed_batches, total_batches, len(result), len(tickers),
            )

    return result


# --------------------------------------------------------------------------- #
#  Tiingo data fetcher
# --------------------------------------------------------------------------- #

_TIINGO_BASE = "https://api.tiingo.com/tiingo/daily"


def _get_tiingo_key() -> Optional[str]:
    """Read Tiingo API key from env var or Streamlit secrets."""
    key = os.environ.get("TIINGO_API_KEY")
    if key:
        return key
    try:
        import streamlit as st
        return st.secrets.get("TIINGO_API_KEY")
    except Exception:
        return None


def _fetch_one_tiingo(
    ticker: str, start_str: str, end_str: str, api_key: str
) -> tuple[str, Optional[pd.DataFrame]]:
    """Fetch OHLCV for a single ticker from Tiingo."""
    url = f"{_TIINGO_BASE}/{ticker}/prices"
    params = {
        "startDate": start_str,
        "endDate": end_str,
        "format": "json",
        "token": api_key,
    }
    try:
        resp = httpx.get(url, params=params, timeout=30)
        if resp.status_code != 200:
            return ticker, None
        data = resp.json()
        if not data:
            return ticker, None
        df = pd.DataFrame(data)
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        df = df.set_index("date")
        df = df.rename(columns={
            "adjOpen": "Open", "adjHigh": "High",
            "adjLow": "Low", "adjClose": "Close",
            "adjVolume": "Volume",
        })
        df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
        if df.empty:
            return ticker, None
        return ticker, df
    except Exception:
        return ticker, None


def fetch_bulk_ohlcv_tiingo(
    tickers: list[str],
    period_days: int = 365,
    max_workers: int = 10,
) -> dict[str, pd.DataFrame]:
    """
    Fetch OHLCV for multiple tickers from Tiingo in parallel.
    Returns {ticker: DataFrame}. Requires TIINGO_API_KEY env var.
    """
    api_key = _get_tiingo_key()
    if not api_key:
        raise ValueError("TIINGO_API_KEY not set. Add it to your environment or Streamlit secrets.")

    end = datetime.today() + timedelta(days=1)
    start = end - timedelta(days=period_days + 1)
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    result = {}
    workers = min(max_workers, len(tickers))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(_fetch_one_tiingo, t, start_str, end_str, api_key)
            for t in tickers
        ]
        for f in futures:
            ticker, df = f.result()
            if df is not None and not df.empty:
                result[ticker] = df
    return result


def compute_ohlcv_extras(df: pd.DataFrame) -> dict:
    """
    Compute 1-day metrics derivable from OHLCV data alone:
      price_change_pct — today's close vs yesterday's close (%)
      today_vol        — today's share volume
      rel_vol          — today's volume / 30-day average volume
    """
    close  = df["Close"]
    volume = df["Volume"]
    n = len(df)

    today_vol   = float(volume.iloc[-1])
    avg_vol_30d = float(volume.iloc[max(0, n - 31) : n - 1].mean()) if n >= 2 else today_vol
    rel_vol     = round(today_vol / avg_vol_30d, 2) if avg_vol_30d > 0 else 0.0

    price_change_pct = None
    if n >= 2:
        prev = float(close.iloc[-2])
        if prev > 0:
            price_change_pct = round((float(close.iloc[-1]) - prev) / prev * 100, 2)

    return {
        "price_change_pct": price_change_pct,
        "today_vol": round(today_vol, 0),
        "rel_vol": rel_vol,
    }


def _fetch_one_info(ticker: str) -> tuple[str, dict]:
    """
    Fetch lightweight metadata for a single ticker from Yahoo Finance.

    Uses fast_info for market_cap (reliable in 0.2.x) and falls back to
    the full info dict for name, EPS, sector, and analyst rating.
    Retries up to 3 times with backoff to handle transient rate limits.
    """
    import time

    result: dict = {
        "name": None, "market_cap": None,
        "eps": None, "sector": None, "analyst_rating": None,
    }
    for attempt in range(3):
        try:
            t = yf.Ticker(ticker)

            # fast_info uses a lightweight endpoint — more reliable for market cap
            try:
                result["market_cap"] = t.fast_info.market_cap
            except Exception:
                pass

            # info provides the richer fundamental data
            try:
                info = t.info
                result["name"] = info.get("shortName") or info.get("longName")
                # yfinance field name varies across versions
                result["eps"] = (
                    info.get("trailingEps")
                    or info.get("epsTrailingTwelveMonths")
                )
                result["sector"] = info.get("sector")
                result["analyst_rating"] = info.get("recommendationKey")
                # use info's market cap as fallback if fast_info returned None
                if result["market_cap"] is None:
                    result["market_cap"] = info.get("marketCap")
                break  # success — stop retrying
            except Exception:
                if attempt < 2:
                    time.sleep(5)

        except Exception:
            break

    return ticker, result


def fetch_ticker_info(tickers: list[str], max_workers: int = 4) -> dict[str, dict]:
    """
    Fetch name, market cap, EPS, sector, and analyst rating for multiple
    tickers in parallel.  Returns {ticker: {field: value}}.
    """
    if not tickers:
        return {}
    workers = min(max_workers, len(tickers))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return dict(pool.map(_fetch_one_info, tickers))
