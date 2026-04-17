"""
Stock universe fetchers.
Supports: S&P 500, NASDAQ-100, Russell 2000, Russell 3000.
Each universe is cached to a local JSON file with a 24-hour TTL.
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

UNIVERSES = {
    "sp500":      {"label": "S&P 500",      "approx_size": 503},
    "nasdaq100":  {"label": "NASDAQ 100",   "approx_size": 101},
    "russell2000": {"label": "Russell 2000", "approx_size": 2000},
    "russell3000": {"label": "Russell 3000", "approx_size": 3000},
    "futures":    {"label": "Futures",      "approx_size": 25},
    "crypto":     {"label": "Crypto",       "approx_size": 48},
}


def _cache_path(universe: str) -> Path:
    return CACHE_DIR / f"_{universe}_cache.json"


def _cache_is_fresh(universe: str) -> bool:
    p = _cache_path(universe)
    if not p.exists():
        return False
    return (time.time() - p.stat().st_mtime) / 3600 < CACHE_TTL_HOURS


def fetch_tickers(universe: str) -> list[str]:
    """Return ticker list for the given universe identifier."""
    if universe not in UNIVERSES:
        raise ValueError(f"Unknown universe '{universe}'. Choose from: {list(UNIVERSES)}")
    if _cache_is_fresh(universe):
        return json.loads(_cache_path(universe).read_text())

    dispatch = {
        "sp500":       lambda: _fetch_ishares("IVV"),
        "nasdaq100":   _fetch_nasdaq100,
        "russell2000": lambda: _fetch_ishares("IWM"),
        "russell3000": lambda: _fetch_ishares("IWB"),
        "futures":     _fetch_futures,
        "crypto":      _fetch_crypto,
    }
    tickers = dispatch[universe]()

    if tickers:
        _cache_path(universe).write_text(json.dumps(tickers))
    return tickers


# --------------------------------------------------------------------------- #
#  Per-universe fetchers
# --------------------------------------------------------------------------- #

_WIKI_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; stock-screener/1.0)",
    "Accept-Language": "en-US,en;q=0.9",
}


def _fetch_crypto() -> list[str]:
    """Top 50 crypto by market cap (stablecoins excluded) — yfinance USD pairs."""
    return [
        # Mega cap
        "BTC-USD", "ETH-USD", "BNB-USD", "XRP-USD", "SOL-USD",
        "TRX-USD", "ADA-USD", "DOGE-USD",
        # Large cap
        "TON-USD", "SHIB-USD", "AVAX-USD", "LINK-USD", "HBAR-USD",
        "XLM-USD", "DOT-USD", "BCH-USD", "LTC-USD", "UNI-USD",
        "NEAR-USD", "SUI-USD",
        # Mid cap
        "APT-USD", "ICP-USD", "XMR-USD", "ETC-USD", "ARB-USD",
        "ATOM-USD", "RNDR-USD", "POL-USD", "KAS-USD", "OP-USD",
        "VET-USD", "FIL-USD", "INJ-USD", "AAVE-USD", "STX-USD",
        "MKR-USD", "GRT-USD", "MNT-USD", "FET-USD", "IMX-USD",
        # Smaller / emerging
        "SEI-USD", "TIA-USD", "ONDO-USD", "ALGO-USD", "EOS-USD",
        "PYTH-USD", "FLOW-USD", "W-USD",
    ]


def _fetch_futures() -> list[str]:
    """Static list of common futures tickers supported by yfinance."""
    return [
        # Equity index
        "ES=F", "NQ=F", "YM=F", "RTY=F", "NKD=F",
        # Energy
        "CL=F", "NG=F", "RB=F", "HO=F", "BZ=F",
        # Metals
        "GC=F", "SI=F", "HG=F", "PL=F", "PA=F",
        # Grains / Softs
        "ZC=F", "ZW=F", "ZS=F", "ZO=F", "KC=F", "CT=F", "SB=F",
        # Fixed income
        "ZB=F", "ZN=F", "ZF=F", "ZT=F",
        # FX
        "6E=F", "6J=F", "6B=F", "6A=F", "6C=F",
        # Crypto
        "BTC=F", "ETH=F",
        # Micro contracts
        "MES=F", "MNQ=F", "MYM=F", "M2K=F",
    ]


_NASDAQ100_FALLBACK = [
    "AAPL","MSFT","NVDA","AMZN","META","GOOGL","GOOG","TSLA","AVGO","COST",
    "NFLX","AMD","ASML","ADBE","CSCO","TMUS","LIN","INTU","TXN","ISRG",
    "QCOM","CMCSA","AMGN","AMAT","ARM","HON","MRVL","BKNG","MU","PEP",
    "ADI","GILD","INTC","PANW","SBUX","LRCX","KLAC","MELI","MDLZ","ADP",
    "SNPS","CDNS","CSGP","CEG","MAR","ORLY","PYPL","NXPI","PAYX","CRWD",
    "MNST","MCHP","FTNT","CHTR","FAST","ROP","WDAY","IDXX","VRSK","ROST",
    "ABNB","KDP","ODFL","DDOG","CTAS","BKR","CPRT","AXON","DXCM","EXC",
    "PCAR","APP","PLTR","CSX","EA","DASH","GEHC","KHC","TTWO","REGN",
    "FANG","XEL","AEP","TEAM","SHOP","ALNY","MSTR","CCEP","WDC","TRI",
    "INSM","STX","FER","PDD","ADSK","MPWR","VRTX","WMT","WBD","CTSH","PDD",
]


def _fetch_nasdaq100() -> list[str]:
    """Fetch NASDAQ-100 components.
    Sources tried in order:
      1. nasdaq.com market-activity page (JSON embedded in __NEXT_DATA__)
      2. Wikipedia Nasdaq-100 article
      3. Static fallback list
    """
    import json as _json
    import re as _re

    # --- Source 1: nasdaq.com ---
    try:
        resp = httpx.get(
            "https://www.nasdaq.com/market-activity/quotes/nasdaq-ndx-index",
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=15,
            follow_redirects=True,
        )
        resp.raise_for_status()
        # The page embeds Next.js data in <script id="__NEXT_DATA__"> as JSON.
        match = _re.search(
            r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
            resp.text,
            _re.DOTALL,
        )
        if match:
            data = _json.loads(match.group(1))
            # Walk into the nested structure to find the constituents list.
            # Path varies by page build; search recursively for a list of dicts
            # that each have a "symbol" key.
            def _find_symbols(obj: object) -> list[str]:
                if isinstance(obj, dict):
                    if "symbol" in obj and isinstance(obj["symbol"], str):
                        return [obj["symbol"].strip()]
                    found: list[str] = []
                    for v in obj.values():
                        found.extend(_find_symbols(v))
                    return found
                if isinstance(obj, list):
                    found = []
                    for item in obj:
                        found.extend(_find_symbols(item))
                    return found
                return []

            symbols = _find_symbols(data)
            tickers = list(dict.fromkeys(
                t.upper() for t in symbols if t and len(t) <= 6
            ))
            if len(tickers) > 50:
                return tickers
    except Exception:
        pass

    # --- Source 2: Wikipedia ---
    try:
        resp = httpx.get(
            "https://en.wikipedia.org/wiki/Nasdaq-100",
            headers=_WIKI_HEADERS,
            timeout=15,
            follow_redirects=True,
        )
        resp.raise_for_status()
        tables = pd.read_html(StringIO(resp.text))
        for df in tables:
            if "Ticker" in df.columns:
                tickers = df["Ticker"].dropna().astype(str).str.strip().tolist()
                tickers = [t for t in tickers if t and len(t) <= 6]
                if len(tickers) > 50:
                    return tickers
    except Exception:
        pass

    # --- Source 3: static fallback list ---
    return list(dict.fromkeys(_NASDAQ100_FALLBACK))  # deduplicate, preserve order


def _fetch_ishares(fund: str) -> list[str]:
    """Fetch iShares ETF holdings CSV.
    Supported: IVV (S&P 500), QQQ-proxy, IWM (Russell 2000), IWB (Russell 3000).
    """
    etf_ids = {
        "IVV": "239726/ishares-core-sp-500-etf",
        "IWM": "239710/ishares-russell-2000-etf",
        "IWB": "239714/ishares-russell-3000-etf",
    }
    url = (
        f"https://www.ishares.com/us/products/{etf_ids[fund]}"
        f"/1467271812596.ajax?fileType=csv&fileName={fund}_holdings&dataType=fund"
    )
    try:
        resp = httpx.get(url, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        lines = resp.text.splitlines()
        header_idx = next(i for i, line in enumerate(lines) if line.startswith("Ticker"))
        df = pd.read_csv(StringIO("\n".join(lines[header_idx:])))
        tickers = df["Ticker"].dropna().astype(str).str.strip().str.upper()
        return [t for t in tickers if t.isalpha() and len(t) <= 5]
    except Exception:
        return []
