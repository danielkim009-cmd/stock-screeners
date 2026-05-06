"""
Point-in-time NASDAQ 100 composition from Wikipedia.

Scrapes the current constituents and historical changes from
https://en.wikipedia.org/wiki/Nasdaq-100
to reconstruct the index membership at any past date.

Cache: 24-hour TTL, same pattern as universes.py / sp500_history.py.
"""
from __future__ import annotations

import json
import time
from io import StringIO
from pathlib import Path

import httpx
import pandas as pd

CACHE_DIR = Path(__file__).parent
CACHE_TTL_HOURS = 24

_WIKI_URL = "https://en.wikipedia.org/wiki/Nasdaq-100"
_WIKI_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; stock-screener/1.0)",
    "Accept-Language": "en-US,en;q=0.9",
}


def _yf_ticker(symbol: str) -> str:
    """Convert Wikipedia ticker format to yfinance format (e.g. BRK.B → BRK-B)."""
    return symbol.replace(".", "-")


def _cache_path(name: str) -> Path:
    return CACHE_DIR / f"_{name}_cache.json"


def _cache_is_fresh(name: str) -> bool:
    p = _cache_path(name)
    if not p.exists():
        return False
    return (time.time() - p.stat().st_mtime) / 3600 < CACHE_TTL_HOURS


def _fetch_wiki_tables() -> list[pd.DataFrame]:
    """Fetch and return all tables from the Wikipedia NASDAQ 100 page."""
    resp = httpx.get(_WIKI_URL, headers=_WIKI_HEADERS, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    return pd.read_html(StringIO(resp.text))


def _find_current_table(tables: list[pd.DataFrame]) -> pd.DataFrame:
    """Find the current constituents table (has 'Ticker' and 'Company' columns, ~101 rows)."""
    for t in tables:
        cols = [str(c) for c in t.columns]
        if "Ticker" in cols and "Company" in cols and len(t) >= 90:
            return t
    raise ValueError("Could not find NASDAQ 100 current constituents table on Wikipedia")


def _find_changes_table(tables: list[pd.DataFrame]) -> pd.DataFrame:
    """Find the historical changes table (6 multi-level columns with Added/Removed headers)."""
    for t in tables:
        col_strs = [str(c) for c in t.columns]
        has_added = any("Added" in c for c in col_strs)
        has_removed = any("Removed" in c for c in col_strs)
        has_date = any("Date" in c for c in col_strs)
        if has_added and has_removed and has_date and len(t) >= 50:
            return t
    raise ValueError("Could not find NASDAQ 100 changes table on Wikipedia")


def _fetch_nasdaq100_current() -> list[str]:
    """Scrape current NASDAQ 100 constituents from Wikipedia."""
    cache_name = "nasdaq100_wiki_current"
    if _cache_is_fresh(cache_name):
        return json.loads(_cache_path(cache_name).read_text())

    tables = _fetch_wiki_tables()
    df = _find_current_table(tables)
    tickers = (
        df["Ticker"]
        .dropna()
        .astype(str)
        .str.strip()
        .apply(_yf_ticker)
        .tolist()
    )
    _cache_path(cache_name).write_text(json.dumps(tickers))
    return tickers


def _fetch_nasdaq100_changes() -> list[dict]:
    """Scrape NASDAQ 100 historical changes from Wikipedia.

    Returns a list of dicts sorted by date descending:
        [{"date": "2025-12-22", "added": "ALNY", "removed": "BIIB"}, ...]
    """
    cache_name = "nasdaq100_wiki_changes"
    if _cache_is_fresh(cache_name):
        return json.loads(_cache_path(cache_name).read_text())

    tables = _fetch_wiki_tables()
    changes_df = _find_changes_table(tables)

    # Flatten multi-level columns
    changes_df.columns = [
        "date", "added_ticker", "added_name",
        "removed_ticker", "removed_name", "reason",
    ]

    rows: list[dict] = []
    for _, row in changes_df.iterrows():
        date_str = str(row["date"]).strip()
        added = str(row["added_ticker"]).strip() if pd.notna(row["added_ticker"]) else ""
        removed = str(row["removed_ticker"]).strip() if pd.notna(row["removed_ticker"]) else ""

        # Filter out "nan" strings
        if added.lower() == "nan":
            added = ""
        if removed.lower() == "nan":
            removed = ""

        # Parse the date
        try:
            parsed = pd.to_datetime(date_str)
            iso_date = parsed.strftime("%Y-%m-%d")
        except Exception:
            continue

        if added or removed:
            rows.append({
                "date": iso_date,
                "added": _yf_ticker(added) if added else "",
                "removed": _yf_ticker(removed) if removed else "",
            })

    # Sort newest first
    rows.sort(key=lambda r: r["date"], reverse=True)

    _cache_path(cache_name).write_text(json.dumps(rows))
    return rows


def get_nasdaq100_at_date(target_date: str) -> list[str]:
    """Reconstruct the NASDAQ 100 composition at a given date.

    Algorithm:
        1. Start with today's constituent list.
        2. Walk changes newest-first; for each change AFTER target_date,
           reverse it (remove what was added, add back what was removed).
        3. Return the resulting ticker list.

    Parameters
    ----------
    target_date : str
        ISO date string, e.g. "2015-01-01".

    Returns
    -------
    list[str]
        Ticker symbols in yfinance format.
    """
    current = set(_fetch_nasdaq100_current())
    changes = _fetch_nasdaq100_changes()

    for ch in changes:
        if ch["date"] <= target_date:
            break  # changes are sorted newest-first; stop when we pass the target

        # Reverse this change: undo the addition, restore the removal
        if ch["added"]:
            current.discard(ch["added"])
        if ch["removed"]:
            current.add(ch["removed"])

    return sorted(current)


def get_nasdaq100_pit_data(start_date: str, end_date: str) -> tuple[list[str], list[str], list[dict]]:
    """Return everything needed for a point-in-time backtest over a date range.

    Returns
    -------
    (initial_tickers, all_tickers, changes_in_range)
        initial_tickers : composition at start_date
        all_tickers     : union of all tickers that were ever in the index
                          between start_date and end_date (for OHLCV fetching)
        changes_in_range: changes within [start_date, end_date], sorted by date
                          ascending — each dict has {date, added, removed}
    """
    changes = _fetch_nasdaq100_changes()

    # Composition at start date
    initial = set(_fetch_nasdaq100_current())
    for ch in changes:
        if ch["date"] <= start_date:
            break
        if ch["added"]:
            initial.discard(ch["added"])
        if ch["removed"]:
            initial.add(ch["removed"])

    # Changes that fall within the backtest window
    in_range = [
        ch for ch in changes
        if start_date < ch["date"] <= end_date
    ]
    in_range.sort(key=lambda r: r["date"])  # ascending for forward walk

    # Union: start with initial, then add anything that gets added during the range
    all_tickers = set(initial)
    for ch in in_range:
        if ch["added"]:
            all_tickers.add(ch["added"])

    return sorted(initial), sorted(all_tickers), in_range
