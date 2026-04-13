"""
Minervini SEPA Backtester
--------------------------
Walk-forward simulation of Minervini's SEPA trend template on a single ticker.

Entry:  C1–C7 all satisfied at bar i (C8 RS Rating is omitted — it requires
        universe-wide comparison and cannot be computed for a single ticker).
        Enter at bar i+1 open.

Exit (configurable):
  SMA50     — close drops below 50-day simple moving average
  ATR_TRAIL — 2× ATR(20) trailing stop below the highest close since entry
  PCT_TRAIL — trail_pct% trailing stop below the highest close since entry
  BOTH      — SMA50 + ATR_TRAIL, whichever triggers first

Cooldown: 1 bar after any exit before re-entry is considered.
Capital:  Fully-invested single position (no leverage, no partial sizing).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


# --------------------------------------------------------------------------- #
#  Data classes (mirror daniels_backtest for a shared response model)
# --------------------------------------------------------------------------- #

@dataclass
class BacktestTrade:
    entry_date:  str
    exit_date:   str
    entry_price: float
    exit_price:  float
    pnl_pct:     float
    days_held:   int
    exit_reason: str   # "SMA50" | "ATR_STOP" | "PCT_STOP" | "SMA50+ATR" | "END"


@dataclass
class BacktestResult:
    ticker:             str
    n_bars:             int
    exit_mode:          str
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
    """Wilder's Average True Range."""
    h = df["High"]
    l = df["Low"]
    c = df["Close"].shift(1)
    tr = pd.concat([h - l, (h - c).abs(), (l - c).abs()], axis=1).max(axis=1)
    return tr.ewm(com=period - 1, adjust=False).mean().values


# --------------------------------------------------------------------------- #
#  Main backtest function
# --------------------------------------------------------------------------- #

def run_minervini_backtest(
    df: pd.DataFrame,
    ticker: str,
    exit_mode: str = "SMA50",       # "SMA50" | "ATR_TRAIL" | "PCT_TRAIL" | "BOTH"
    atr_multiplier: float = 2.0,
    trail_pct: float = 8.0,         # used when exit_mode = "PCT_TRAIL"
    initial_capital: float = 100_000.0,
) -> Optional[BacktestResult]:
    """
    Run Minervini SEPA backtest on a pre-fetched OHLCV DataFrame.

    Requires at least 300 trading bars (≈ 15 months).
    Returns None if insufficient data.
    Entry uses C1–C7 only (RS rating C8 is omitted for single-ticker backtests).
    """
    n = len(df)
    if n < 300:
        return None

    close_s = df["Close"]
    high_s  = df["High"]
    low_s   = df["Low"]

    close  = close_s.values
    open_  = df["Open"].values
    high_  = high_s.values
    low_   = low_s.values
    dates  = [str(idx.date()) for idx in df.index]

    # ── Precompute indicators (vectorised) ──────────────────────────────── #
    ma50  = close_s.rolling(50).mean().values
    ma150 = close_s.rolling(150).mean().values
    ma200 = close_s.rolling(200).mean().values
    sma50 = ma50   # exit signal (same series)
    atr20 = _atr(df, 20)

    # MA200 trend: compare current MA200 to value 21 bars ago
    ma200_21ago = close_s.rolling(200).mean().shift(21).values

    # 52-week high / low using High/Low columns (rolling 252 bars)
    high_52w = high_s.rolling(252).max().values
    low_52w  = low_s.rolling(252).min().values

    # ── Entry criteria (vectorised) ─────────────────────────────────────── #
    c1 = (close > ma150) & (close > ma200)
    c2 = ma150 > ma200
    c3 = np.where(np.isnan(ma200_21ago), False, ma200 > ma200_21ago)
    c4 = (ma50 > ma150) & (ma50 > ma200)
    c5 = close > ma50
    c6 = np.where(
        np.isnan(high_52w) | (high_52w <= 0),
        False,
        close >= high_52w * 0.75,      # within 25% of 52-week high
    )
    c7 = np.where(
        np.isnan(low_52w) | (low_52w <= 0),
        False,
        close >= low_52w * 1.30,       # at least 30% above 52-week low
    )
    entry_signal = c1 & c2 & c3 & c4 & c5 & c6 & c7

    # ── Walk-forward simulation ─────────────────────────────────────────── #
    warmup = 260   # bars needed for MA200 + 21-bar trend + 52-week history

    trades:       list[BacktestTrade] = []
    equity_curve: list[dict]          = []
    equity        = initial_capital

    in_position  = False
    entry_equity = 0.0
    entry_price  = 0.0
    entry_date   = ""
    entry_idx    = 0
    trail_high   = 0.0
    cooldown     = 0

    for i in range(warmup, n):
        mtm = (entry_equity * close[i] / entry_price) if in_position else equity
        equity_curve.append({"date": dates[i], "value": round(mtm, 2)})

        if in_position:
            trail_high = max(trail_high, close[i])
            atr_stop   = trail_high - atr_multiplier * float(atr20[i])
            pct_stop   = trail_high * (1.0 - trail_pct / 100.0)

            exit_sma = (
                exit_mode in ("SMA50", "BOTH")
                and not np.isnan(sma50[i])
                and bool(close[i] < sma50[i])
            )
            exit_atr = (
                exit_mode in ("ATR_TRAIL", "BOTH")
                and not np.isnan(atr_stop)
                and bool(close[i] < atr_stop)
            )
            exit_pct = (
                exit_mode == "PCT_TRAIL"
                and bool(close[i] < pct_stop)
            )
            at_end = (i == n - 1)

            if exit_sma or exit_atr or exit_pct or at_end:
                exit_price = float(close[i])
                pnl_pct    = (exit_price - entry_price) / entry_price * 100
                equity     = entry_equity * exit_price / entry_price

                if at_end and not exit_sma and not exit_atr and not exit_pct:
                    reason = "END"
                elif exit_sma and exit_atr:
                    reason = "SMA50+ATR"
                elif exit_sma:
                    reason = "SMA50"
                elif exit_atr:
                    reason = "ATR_STOP"
                else:
                    reason = "PCT_STOP"

                trades.append(BacktestTrade(
                    entry_date=entry_date,
                    exit_date=dates[i],
                    entry_price=round(entry_price, 2),
                    exit_price=round(exit_price, 2),
                    pnl_pct=round(pnl_pct, 2),
                    days_held=i - entry_idx,
                    exit_reason=reason,
                ))
                in_position = False
                cooldown    = 1

        else:
            if cooldown > 0:
                cooldown -= 1
            elif entry_signal[i] and i + 1 < n:
                entry_equity = equity
                entry_price  = float(open_[i + 1])
                entry_date   = dates[i + 1]
                entry_idx    = i + 1
                trail_high   = entry_price
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
        exit_mode=exit_mode,
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
