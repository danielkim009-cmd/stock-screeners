"""
Minervini SEPA (Specific Entry Point Analysis) Screener
--------------------------------------------------------
Implements Mark Minervini's Trend Template — 8 criteria that must
all be satisfied for a stock to qualify as a Stage 2 uptrend candidate.

Criteria:
  C1: Price > 150-day MA  AND  Price > 200-day MA
  C2: 150-day MA > 200-day MA
  C3: 200-day MA is trending up (higher than 21 trading days ago ≈ 1 month)
  C4: 50-day MA > 150-day MA  AND  50-day MA > 200-day MA
  C5: Price > 50-day MA
  C6: Price is within 25% of its 52-week high  (i.e. ≥ 75% of the high)
  C7: Price is at least 30% above its 52-week low
  C8: RS Rating > 85  (percentile rank of 12-month return vs the universe)
  C9: Relative Volume ≥ 1.5×  (today's volume / 30-day avg volume)

RS Rating is computed externally (pass it in), since it requires comparing
all stocks in the chosen universe.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class MinerviniSignal:
    ticker: str
    last_close: float
    ma50: float
    ma150: float
    ma200: float
    ma200_trend: float      # % change in MA200 over past ~1 month
    high_52w: float
    low_52w: float
    pct_from_high: float    # % below 52-week high  (negative = below)
    pct_from_low: float     # % above 52-week low
    rs_rating: float        # percentile vs universe  (0–100)
    # Individual criteria
    c1: bool   # Price > MA150 and MA200
    c2: bool   # MA150 > MA200
    c3: bool   # MA200 trending up
    c4: bool   # MA50 > MA150 and MA200
    c5: bool   # Price > MA50
    c6: bool   # Within 25% of 52-week high
    c7: bool   # ≥ 30% above 52-week low
    c8: bool   # RS Rating > 85
    c9: bool   # Rel Vol ≥ 1.5
    c10: bool  # Avg Vol (10d) ≥ 1M
    criteria_met: int
    passes: bool            # all 10 criteria satisfied


def compute_rs_ratings(returns_by_ticker: dict[str, float]) -> dict[str, float]:
    """
    Compute RS Rating (0–100 percentile) for each ticker based on
    12-month price performance relative to all other tickers in the universe.

    A rating of 90 means the stock outperformed 90% of the universe.
    """
    if not returns_by_ticker:
        return {}
    tickers = list(returns_by_ticker.keys())
    arr = np.array([returns_by_ticker[t] for t in tickers], dtype=float)
    ratings = {}
    for i, t in enumerate(tickers):
        # Fraction of stocks this one beat × 100
        ratings[t] = round(float(np.sum(arr < arr[i]) / len(arr) * 100), 1)
    return ratings


def calc_12m_return(df: pd.DataFrame) -> Optional[float]:
    """Return 12-month price return, or None if insufficient data."""
    if len(df) < 252:
        return None
    start = float(df["Close"].iloc[-252])
    end = float(df["Close"].iloc[-1])
    if start <= 0:
        return None
    return (end - start) / start * 100


def screen_minervini(
    df: pd.DataFrame,
    ticker: str,
    rs_rating: float,
    rel_vol: float = 1.5,
    avg_vol_10d: float = 1_000_000,
) -> Optional[MinerviniSignal]:
    """
    Apply the 10 Minervini SEPA criteria to one stock's OHLCV DataFrame.

    df           — OHLCV DataFrame, must have at least 221 rows
    ticker       — symbol string
    rs_rating    — pre-computed percentile rank (0–100) from compute_rs_ratings()
    rel_vol      — today's volume / 30-day avg volume (defaults to 1.5 for backtest)
    avg_vol_10d  — 10-day average volume (defaults to 1M for backtest)

    Returns MinerviniSignal or None if data is insufficient.
    """
    # Need at least 200 bars for MA200 + 21 bars lookback for trend check
    if len(df) < 221:
        return None

    close = df["Close"]
    high  = df["High"]
    low   = df["Low"]

    ma50  = close.rolling(50).mean()
    ma150 = close.rolling(150).mean()
    ma200 = close.rolling(200).mean()

    last_close    = float(close.iloc[-1])
    last_ma50     = float(ma50.iloc[-1])
    last_ma150    = float(ma150.iloc[-1])
    last_ma200    = float(ma200.iloc[-1])
    last_ma200_1m = float(ma200.iloc[-21])   # ~1 month ago (21 trading days)

    # 52-week high / low  (up to 252 trading days)
    lookback  = min(252, len(df))
    high_52w  = float(high.iloc[-lookback:].max())
    low_52w   = float(low.iloc[-lookback:].min())

    pct_from_high = (last_close - high_52w) / high_52w * 100  # ≤ 0 if below ATH
    pct_from_low  = (last_close - low_52w) / low_52w * 100
    ma200_trend   = (last_ma200 - last_ma200_1m) / last_ma200_1m * 100

    # Evaluate the 8 criteria
    c1 = last_close > last_ma150 and last_close > last_ma200
    c2 = last_ma150 > last_ma200
    c3 = last_ma200 > last_ma200_1m
    c4 = last_ma50 > last_ma150 and last_ma50 > last_ma200
    c5 = last_close > last_ma50
    c6 = pct_from_high >= -25.0   # price ≥ 75% of 52-week high
    c7 = pct_from_low >= 30.0     # price ≥ 130% of 52-week low
    c8  = rs_rating > 85.0
    c9  = rel_vol >= 1.5
    c10 = avg_vol_10d >= 1_000_000

    criteria_list = [c1, c2, c3, c4, c5, c6, c7, c8, c9, c10]
    criteria_met  = sum(criteria_list)

    return MinerviniSignal(
        ticker=ticker,
        last_close=round(last_close, 2),
        ma50=round(last_ma50, 2),
        ma150=round(last_ma150, 2),
        ma200=round(last_ma200, 2),
        ma200_trend=round(ma200_trend, 2),
        high_52w=round(high_52w, 2),
        low_52w=round(low_52w, 2),
        pct_from_high=round(pct_from_high, 1),
        pct_from_low=round(pct_from_low, 1),
        rs_rating=rs_rating,
        c1=c1, c2=c2, c3=c3, c4=c4,
        c5=c5, c6=c6, c7=c7, c8=c8, c9=c9, c10=c10,
        criteria_met=criteria_met,
        passes=all(criteria_list),
    )
