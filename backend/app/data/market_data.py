"""
OHLCV data fetcher using yfinance with in-memory caching.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Optional

import pandas as pd
import yfinance as yf


def fetch_ohlcv(
    ticker: str,
    period_days: int = 365,
    interval: str = "1d",
) -> Optional[pd.DataFrame]:
    """
    Fetch OHLCV data for a single ticker.
    Returns DataFrame with columns: Open, High, Low, Close, Volume
    or None on failure.
    """
    end = datetime.today() + timedelta(days=1)
    start = end - timedelta(days=period_days + 1)
    try:
        df = yf.download(
            ticker,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            interval=interval,
            auto_adjust=True,
            progress=False,
        )
        if df is None or df.empty:
            return None
        df.index = pd.to_datetime(df.index)
        df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
        # Flatten MultiIndex columns if yfinance returns them
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except Exception:
        return None


def fetch_bulk_ohlcv(
    tickers: list[str],
    period_days: int = 365,
) -> dict[str, pd.DataFrame]:
    """
    Fetch OHLCV for multiple tickers in one yfinance call (faster).
    Returns {ticker: DataFrame}.
    """
    end = datetime.today() + timedelta(days=1)
    start = end - timedelta(days=period_days + 1)
    try:
        raw = yf.download(
            tickers,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            auto_adjust=True,
            progress=False,
            group_by="ticker",
        )
    except Exception:
        return {}

    result = {}
    for ticker in tickers:
        try:
            df = raw[ticker][["Open", "High", "Low", "Close", "Volume"]].dropna()
            if not df.empty:
                result[ticker] = df
        except Exception:
            continue
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
                    time.sleep(0.5 * (attempt + 1))

        except Exception:
            break

    return ticker, result


def fetch_ticker_info(tickers: list[str], max_workers: int = 8) -> dict[str, dict]:
    """
    Fetch name, market cap, EPS, sector, and analyst rating for multiple
    tickers in parallel.  Returns {ticker: {field: value}}.
    """
    if not tickers:
        return {}
    workers = min(max_workers, len(tickers))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return dict(pool.map(_fetch_one_info, tickers))
