"""
Turtle Trading Backtester
--------------------------
Walk-forward simulation of the classic Turtle Trading rules on a single ticker.

Entry:
  System 1 (S1): close breaks above the prior 20-day Donchian high → enter next open
  System 2 (S2): close breaks above the prior 55-day Donchian high → enter next open

Exit (determined by which system triggered the entry):
  S1 entry → exit when close drops below the 10-day Donchian low
  S2 entry → exit when close drops below the 20-day Donchian low
  ATR Stop → fixed hard stop at 2×ATR(20) below the entry price (always active)

"system" parameter:
  S1   — only trade System 1 (20-day) breakouts
  S2   — only trade System 2 (55-day) breakouts
  BOTH — trade both; S2 takes priority if both trigger simultaneously

Cooldown: 1 bar after any exit before re-entry is considered.
Capital:  Fully-invested single position (no leverage, no partial sizing).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


# --------------------------------------------------------------------------- #
#  Data classes
# --------------------------------------------------------------------------- #

@dataclass
class BacktestTrade:
    entry_date:  str
    exit_date:   str
    entry_price: float
    exit_price:  float
    pnl_pct:     float
    days_held:   int
    exit_reason: str   # "LOW10" | "LOW20" | "ATR_STOP" | "END"
    system:      str   # "S1" | "S2"


@dataclass
class BacktestResult:
    ticker:             str
    n_bars:             int
    exit_mode:          str     # stores the "system" parameter
    trades:             list[BacktestTrade]
    equity_curve:       list[dict]
    total_return_pct:   float
    bh_return_pct:      float
    max_drawdown_pct:   float
    win_rate_pct:       float
    n_trades:           int
    sharpe_ratio:       float
    avg_trade_pnl_pct:  float


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #

def _atr(df: pd.DataFrame, period: int = 20) -> np.ndarray:
    """Simple (non-Wilder) ATR for consistency with the Turtle 'N'."""
    h = df["High"]
    l = df["Low"]
    c = df["Close"].shift(1)
    tr = pd.concat([h - l, (h - c).abs(), (l - c).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean().values


# --------------------------------------------------------------------------- #
#  Main backtest function
# --------------------------------------------------------------------------- #

def run_turtle_backtest(
    df: pd.DataFrame,
    ticker: str,
    system: str = "S2",             # "S1" | "S2" | "BOTH"
    atr_multiplier: float = 2.0,
    initial_capital: float = 100_000.0,
) -> Optional[BacktestResult]:
    """
    Run Turtle backtest on a pre-fetched OHLCV DataFrame.

    Requires at least 120 trading bars.  Returns None if insufficient data.
    Entry uses the prior bar's Donchian channel high (no look-ahead).
    Exit uses the current bar's Donchian channel low.
    ATR stop is fixed from entry (original Turtle N-stop: entry - 2×N).
    """
    n = len(df)
    if n < 120:
        return None

    close_s = df["Close"]
    high_s  = df["High"]
    low_s   = df["Low"]

    close  = close_s.values
    open_  = df["Open"].values
    dates  = [str(idx.date()) for idx in df.index]

    # ── Precompute channels (vectorised) ─────────────────────────────────── #
    # Entry: prior bar's N-day high of High prices
    high_20_ch = high_s.rolling(20).max().shift(1).values
    high_55_ch = high_s.rolling(55).max().shift(1).values

    # Exit: current bar's N-day low of Low prices
    low_10_ch  = low_s.rolling(10).min().values
    low_20_ch  = low_s.rolling(20).min().values

    # ATR(20) — simple rolling mean of true range (Turtle "N")
    atr20 = _atr(df, 20)

    # ── Entry signals ────────────────────────────────────────────────────── #
    s1_entry = np.where(np.isnan(high_20_ch), False, close > high_20_ch)
    s2_entry = np.where(np.isnan(high_55_ch), False, close > high_55_ch)

    # ── Walk-forward simulation ─────────────────────────────────────────── #
    warmup = 60   # enough for 55-day channel + ATR warmup

    trades:       list[BacktestTrade] = []
    equity_curve: list[dict]          = []
    equity        = initial_capital

    in_position   = False
    entry_system  = ""     # "S1" or "S2" — tracks which channel to use for exit
    entry_equity  = 0.0
    entry_price   = 0.0
    entry_date    = ""
    entry_idx     = 0
    atr_stop      = 0.0    # fixed from entry (not trailing)
    cooldown      = 0

    for i in range(warmup, n):
        mtm = (entry_equity * close[i] / entry_price) if in_position else equity
        equity_curve.append({"date": dates[i], "value": round(mtm, 2)})

        if in_position:
            # Donchian channel exit depends on which system entered
            if entry_system == "S1":
                exit_ch = (
                    not np.isnan(low_10_ch[i])
                    and bool(close[i] < low_10_ch[i])
                )
                ch_reason = "LOW10"
            else:
                exit_ch = (
                    not np.isnan(low_20_ch[i])
                    and bool(close[i] < low_20_ch[i])
                )
                ch_reason = "LOW20"

            exit_atr = not np.isnan(atr_stop) and bool(close[i] < atr_stop)
            at_end   = (i == n - 1)

            if exit_ch or exit_atr or at_end:
                exit_price = float(close[i])
                pnl_pct    = (exit_price - entry_price) / entry_price * 100
                equity     = entry_equity * exit_price / entry_price

                if at_end and not exit_ch and not exit_atr:
                    reason = "END"
                elif exit_atr and not exit_ch:
                    reason = "ATR_STOP"
                else:
                    reason = ch_reason  # LOW10 or LOW20 (channel takes priority label)

                trades.append(BacktestTrade(
                    entry_date=entry_date,
                    exit_date=dates[i],
                    entry_price=round(entry_price, 2),
                    exit_price=round(exit_price, 2),
                    pnl_pct=round(pnl_pct, 2),
                    days_held=i - entry_idx,
                    exit_reason=reason,
                    system=entry_system,
                ))
                in_position = False
                cooldown    = 1

        else:
            if cooldown > 0:
                cooldown -= 1
            elif i + 1 < n:
                # S2 takes priority if both trigger simultaneously
                trigger_s2 = system in ("S2", "BOTH") and bool(s2_entry[i])
                trigger_s1 = system in ("S1", "BOTH") and bool(s1_entry[i])

                if trigger_s2 or trigger_s1:
                    entry_system = "S2" if trigger_s2 else "S1"
                    entry_equity = equity
                    entry_price  = float(open_[i + 1])
                    entry_date   = dates[i + 1]
                    entry_idx    = i + 1
                    # Fixed ATR stop: entry - 2×N (N = ATR at signal bar)
                    atr_stop     = entry_price - atr_multiplier * float(atr20[i])
                    in_position  = True

    # ── Performance metrics ─────────────────────────────────────────────── #
    total_return_pct = (equity / initial_capital - 1) * 100

    bh_start      = float(close[warmup])
    bh_end        = float(close[-1])
    bh_return_pct = (bh_end / bh_start - 1) * 100 if bh_start > 0 else 0.0

    eq_vals = np.array([e["value"] for e in equity_curve], dtype=float)
    if len(eq_vals) > 1:
        peak      = np.maximum.accumulate(eq_vals)
        max_dd    = float(((eq_vals - peak) / peak * 100).min())
        daily_ret = np.diff(eq_vals) / eq_vals[:-1]
        std       = daily_ret.std()
        sharpe    = float(daily_ret.mean() / std * np.sqrt(252)) if std > 0 else 0.0
    else:
        max_dd = 0.0
        sharpe = 0.0

    n_trades = len(trades)
    wins     = sum(1 for t in trades if t.pnl_pct > 0)
    win_rate = wins / n_trades * 100 if n_trades > 0 else 0.0
    avg_pnl  = sum(t.pnl_pct for t in trades) / n_trades if n_trades > 0 else 0.0

    return BacktestResult(
        ticker=ticker,
        n_bars=n,
        exit_mode=system,
        trades=trades,
        equity_curve=equity_curve,
        total_return_pct=round(total_return_pct, 2),
        bh_return_pct=round(bh_return_pct, 2),
        max_drawdown_pct=round(max_dd, 1),
        win_rate_pct=round(win_rate, 1),
        n_trades=n_trades,
        sharpe_ratio=round(sharpe, 2),
        avg_trade_pnl_pct=round(avg_pnl, 2),
    )
