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
    high_6m: float        # highest close in prior 125 trading days
    rel_volume: float     # today's vol ÷ 30-day avg vol
    avg_vol_10d: float    # 10-day average volume (shares)
    c1: bool   # Price > EMA21
    c2: bool   # EMA21 ≥ EMA50
    c3: bool   # EMA50 ≥ EMA100
    c4: bool   # new 6-month high
    c5: bool   # rel vol ≥ 1.5
    c6: bool   # 10d avg vol ≥ 1M
    criteria_met: int
    passes: bool          # all 6 criteria satisfied


def screen_daniels_breakout(
    df: pd.DataFrame,
    ticker: str,
) -> Optional[DanielsBreakoutSignal]:
    """
    Apply Daniel's breakout criteria to one stock's OHLCV DataFrame.

    df     — OHLCV DataFrame; needs ≥ 130 rows (100 for EMA100 + vol buffer)
    ticker — symbol string

    Returns DanielsBreakoutSignal or None if data is insufficient.
    """
    if len(df) < 130:
        return None

    close  = df["Close"]
    volume = df["Volume"]

    ema21  = close.ewm(span=21,  adjust=False).mean()
    ema50  = close.ewm(span=50,  adjust=False).mean()
    ema100 = close.ewm(span=100, adjust=False).mean()

    last_close  = float(close.iloc[-1])
    last_ema21  = float(ema21.iloc[-1])
    last_ema50  = float(ema50.iloc[-1])
    last_ema100 = float(ema100.iloc[-1])

    # 6-month high: highest close in the 125 bars BEFORE today
    lookback     = min(126, len(df) - 1)
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
    c5 = rel_volume >= 1.5
    c6 = avg_vol_10d >= 1_000_000

    criteria_list = [c1, c2, c3, c4, c5, c6]
    criteria_met  = sum(criteria_list)

    return DanielsBreakoutSignal(
        ticker=ticker,
        last_close=round(last_close, 2),
        ema21=round(last_ema21, 2),
        ema50=round(last_ema50, 2),
        ema100=round(last_ema100, 2),
        high_6m=round(high_6m, 2),
        rel_volume=rel_volume,
        avg_vol_10d=round(avg_vol_10d, 0),
        c1=c1, c2=c2, c3=c3, c4=c4, c5=c5, c6=c6,
        criteria_met=criteria_met,
        passes=all(criteria_list),
    )
