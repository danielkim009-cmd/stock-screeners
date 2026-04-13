"""
Turtle Trading Strategy Screener
---------------------------------
Classic Richard Dennis / William Eckhardt rules:

Entry signals:
  - System 1 (short-term): Price breaks above 20-day high (long)
  - System 2 (long-term):  Price breaks above 55-day high (long)

Filter: Only enter if the last System 1 trade would have been a loss
(original Turtle filter) — simplified here: we flag both signals
and let the user decide which to use.

Additional output:
  - ATR(20) for position sizing reference
  - N-day high/low levels
  - Whether today is a breakout day
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class TurtleSignal:
    ticker: str
    last_close: float
    atr_20: float
    high_20: float
    high_55: float
    low_10: float   # System 1 exit
    low_20: float   # System 2 exit
    breakout_20: bool   # System 1 entry signal
    breakout_55: bool   # System 2 entry signal
    signal: str         # "S1_BUY", "S2_BUY", "NONE"
    days_since_breakout: Optional[int]  # days ago the most recent breakout occurred


def _atr(df: pd.DataFrame, period: int = 20) -> pd.Series:
    high = df["High"]
    low = df["Low"]
    prev_close = df["Close"].shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.rolling(period).mean()


def screen_turtle(df: pd.DataFrame, ticker: str) -> Optional[TurtleSignal]:
    """
    Apply Turtle strategy to a single stock's OHLCV DataFrame.
    Returns TurtleSignal or None if data is insufficient.
    """
    if len(df) < 60:
        return None

    close = df["Close"]
    high = df["High"]
    low = df["Low"]

    # Rolling channels
    high_20 = high.rolling(20).max()
    high_55 = high.rolling(55).max()
    low_10 = low.rolling(10).min()
    low_20 = low.rolling(20).min()
    atr20 = _atr(df, 20)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    h20 = high_20.iloc[-2]   # yesterday's 20-day high (breakout = today close > this)
    h55 = high_55.iloc[-2]

    breakout_20 = bool(float(last["Close"]) > float(h20))
    breakout_55 = bool(float(last["Close"]) > float(h55))

    if breakout_55:
        signal = "S2_BUY"
    elif breakout_20:
        signal = "S1_BUY"
    else:
        signal = "NONE"

    # Find how many days ago the most recent S2 breakout occurred (within 10 days)
    days_since = None
    if not breakout_20 and not breakout_55:
        for i in range(2, min(11, len(df))):
            row = df.iloc[-i]
            prev_row = df.iloc[-(i + 1)]
            if float(row["Close"]) > float(high_20.iloc[-(i + 1)]):
                days_since = i - 1
                break

    return TurtleSignal(
        ticker=ticker,
        last_close=round(float(last["Close"]), 2),
        atr_20=round(float(atr20.iloc[-1]), 2),
        high_20=round(float(h20), 2),
        high_55=round(float(h55), 2),
        low_10=round(float(low_10.iloc[-1]), 2),
        low_20=round(float(low_20.iloc[-1]), 2),
        breakout_20=breakout_20,
        breakout_55=breakout_55,
        signal=signal,
        days_since_breakout=days_since,
    )
