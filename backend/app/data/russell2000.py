"""
Russell 2000 ticker list fetcher.
Primary source: Wikipedia IWM holdings page.
Falls back to a bundled static list if unavailable.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

import httpx
import pandas as pd

CACHE_PATH = Path(__file__).parent / "_russell2000_cache.json"
CACHE_TTL_HOURS = 24


def _cache_is_fresh() -> bool:
    if not CACHE_PATH.exists():
        return False
    age_hours = (time.time() - CACHE_PATH.stat().st_mtime) / 3600
    return age_hours < CACHE_TTL_HOURS


def fetch_russell2000_tickers() -> list[str]:
    """Return list of Russell 2000 ticker symbols."""
    if _cache_is_fresh():
        return json.loads(CACHE_PATH.read_text())

    tickers = _fetch_from_wikipedia()
    if not tickers:
        tickers = _fetch_from_static_fallback()

    if tickers:
        CACHE_PATH.write_text(json.dumps(tickers))

    return tickers


def _fetch_from_wikipedia() -> list[str]:
    """Scrape the iShares IWM holdings CSV for Russell 2000 components."""
    url = "https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/1467271812596.ajax?fileType=csv&fileName=IWM_holdings&dataType=fund"
    try:
        resp = httpx.get(url, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        lines = resp.text.splitlines()
        # iShares CSV has metadata rows at the top; find the header
        header_idx = next(i for i, l in enumerate(lines) if l.startswith("Ticker"))
        from io import StringIO
        df = pd.read_csv(StringIO("\n".join(lines[header_idx:])))
        tickers = (
            df["Ticker"]
            .dropna()
            .astype(str)
            .str.strip()
            .str.upper()
        )
        # Filter out non-equity rows (cash, '-', etc.)
        tickers = [t for t in tickers if t.isalpha() and len(t) <= 5]
        return tickers
    except Exception:
        return []


def _fetch_from_static_fallback() -> list[str]:
    """Return a small hard-coded sample for offline/dev use."""
    return [
        "ACLS", "ACLX", "ACMR", "ACNB", "ACON", "ACRS", "ACTG", "ACVA",
        "ADEA", "ADER", "ADMA", "ADNT", "ADUS", "ADVM", "AEAC", "AEHL",
        "AEHR", "AEIS", "AEMD", "AENZ", "AESI", "AEVA", "AFCG", "AFRI",
        "AGCO", "AGFS", "AGIO", "AGMH", "AGYS", "AHCO", "AHPI", "AHRN",
        "AIRC", "AIRG", "AIRT", "AIXI", "AJRD", "AKAM", "AKBA", "AKRO",
        "ALEC", "ALGT", "ALIM", "ALLO", "ALNT", "ALRM", "ALRS", "ALSA",
        "ALSK", "ALTI", "ALUR", "ALVO", "ALXO", "AMAG", "AMBC", "AMCX",
    ]
