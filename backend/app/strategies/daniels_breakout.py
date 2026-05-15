"""
Daniel's Breakout Screener
--------------------------
EMA momentum stack + volume-confirmed breakout to a new 6-month high.

Criteria:
  C1: Price > 21-day EMA
  C2: 21-day EMA ≥ 50-day EMA
  C3: 50-day EMA ≥ 100-day EMA
  C4: Price at or above new 6-month high (highest close in prior 125 trading days)
  C5: Today's volume ≥ 1.5× 30-day average volume (relative volume surge)
  C6: 10-day average volume ≥ 1,000,000 shares (liquidity)
  C7: 100-day EMA ≥ 150-day EMA
  C8: 150-day EMA ≥ 200-day EMA

Results sorted by relative volume descending (highest surge first).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass
class DanielsBreakoutSignal:
    ticker: str
    last_close: float
    ema21: float
    ema50: float
    ema100: float
    ema150: float
    ema200: float
    high_6m: float        # highest close in prior 125 trading days
    rel_volume: float     # today's vol ÷ 30-day avg vol
    avg_vol_10d: float    # 10-day average volume (shares)
    c1: bool   # Price > EMA21
    c2: bool   # EMA21 ≥ EMA50
    c3: bool   # EMA50 ≥ EMA100
    c4: bool   # new 6-month high
    c5: bool   # rel vol ≥ 1.5
    c6: bool   # 10d avg vol ≥ 1M
    c7: bool   # EMA100 ≥ EMA150
    c8: bool   # EMA150 ≥ EMA200
    criteria_met: int
    passes: bool          # all 8 criteria satisfied


def screen_daniels_breakout(
    df: pd.DataFrame,
    ticker: str,
    min_rel_vol: float = 1.5,
    min_avg_vol: int = 1_000_000,
    high_lookback: int = 125,
) -> Optional[DanielsBreakoutSignal]:
    """
    Apply Daniel's breakout criteria to one stock's OHLCV DataFrame.

    df             — OHLCV DataFrame; needs ≥ 210 rows (200 for EMA200 warmup + vol buffer)
    ticker         — symbol string
    min_rel_vol    — C5 threshold: min relative volume vs 30-day avg (default 1.5)
    min_avg_vol    — C6 threshold: min 10-day average volume in shares (default 1,000,000)
    high_lookback  — C4 lookback: trading bars for the new-high window (default 125 ≈ 6 months)

    Returns DanielsBreakoutSignal or None if data is insufficient.
    """
    if len(df) < 210:
        return None

    close  = df["Close"]
    volume = df["Volume"]

    ema21  = close.ewm(span=21,  adjust=False).mean()
    ema50  = close.ewm(span=50,  adjust=False).mean()
    ema100 = close.ewm(span=100, adjust=False).mean()
    ema150 = close.ewm(span=150, adjust=False).mean()
    ema200 = close.ewm(span=200, adjust=False).mean()

    last_close  = float(close.iloc[-1])
    last_ema21  = float(ema21.iloc[-1])
    last_ema50  = float(ema50.iloc[-1])
    last_ema100 = float(ema100.iloc[-1])
    last_ema150 = float(ema150.iloc[-1])
    last_ema200 = float(ema200.iloc[-1])

    # New high: highest close in the `high_lookback` bars BEFORE today
    lookback     = min(high_lookback + 1, len(df) - 1)
    high_6m      = float(close.iloc[-lookback - 1 : -1].max())

    # Volume: exclude today so we compare today vs the prior period
    today_vol    = float(volume.iloc[-1])
    avg_vol_30d  = float(volume.iloc[-31:-1].mean())
    avg_vol_10d  = float(volume.iloc[-11:-1].mean())
    rel_volume   = round(today_vol / avg_vol_30d, 2) if avg_vol_30d > 0 else 0.0

    c1 = last_close > last_ema21
    c2 = last_ema21 >= last_ema50
    c3 = last_ema50 >= last_ema100
    c4 = last_close >= high_6m
    c5 = rel_volume >= min_rel_vol
    c6 = avg_vol_10d >= min_avg_vol
    c7 = last_ema100 >= last_ema150
    c8 = last_ema150 >= last_ema200

    criteria_list = [c1, c2, c3, c4, c5, c6, c7, c8]
    criteria_met  = sum(criteria_list)

    return DanielsBreakoutSignal(
        ticker=ticker,
        last_close=round(last_close, 2),
        ema21=round(last_ema21, 2),
        ema50=round(last_ema50, 2),
        ema100=round(last_ema100, 2),
        ema150=round(last_ema150, 2),
        ema200=round(last_ema200, 2),
        high_6m=round(high_6m, 2),
        rel_volume=rel_volume,
        avg_vol_10d=round(avg_vol_10d, 0),
        c1=c1, c2=c2, c3=c3, c4=c4, c5=c5, c6=c6, c7=c7, c8=c8,
        criteria_met=criteria_met,
        passes=all(criteria_list),
    )
