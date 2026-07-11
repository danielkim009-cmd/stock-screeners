"""
Daniel's Breakout Backtester
-----------------------------
Walk-forward simulation of Daniel's breakout strategy on a single ticker.

Entry:  ≥ min_criteria of Daniel's 8 criteria satisfied at bar i (default: all 8,
        matching the screener's strict pass) → enter at bar i+1 open.
Exit (configurable):
  SMA50     — close drops below 50-day simple moving average
  ATR_TRAIL — 2× ATR(20) trailing stop below the highest close since entry
  PCT_TRAIL — close drops by trail_pct % from the highest close since entry
  BOTH      — SMA50 + ATR_TRAIL, whichever triggers first (default)

Costs:    cost_bps is applied one-way on every fill (entry and exit) to model
          slippage + commission. 0 by default for backward compatibility;
          5–10 bps is a realistic setting for liquid US large caps.
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
    exit_reason: str   # "SMA50" | "ATR_STOP" | "SMA50+ATR" | "PCT_TRAIL" | "END"


@dataclass
class BacktestResult:
    ticker:             str
    n_bars:             int    # trading bars in the backtest window
    exit_mode:          str
    trades:             list[BacktestTrade]
    equity_curve:       list[dict]   # [{date, value}, ...]
    total_return_pct:   float
    bh_return_pct:      float
    max_drawdown_pct:   float
    win_rate_pct:       float
    n_trades:           int
    sharpe_ratio:       float
    avg_trade_pnl_pct:  float
    avg_win_pct:        float = 0.0
    avg_loss_pct:       float = 0.0
    bh_max_drawdown_pct: float = 0.0


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

def run_daniels_backtest(
    df: pd.DataFrame,
    ticker: str,
    exit_mode: str = "BOTH",          # "SMA50" | "ATR_TRAIL" | "PCT_TRAIL" | "BOTH"
    atr_multiplier: float = 2.0,
    trail_pct: float = 10.0,          # used when exit_mode == "PCT_TRAIL"
    initial_capital: float = 100_000.0,
    min_criteria: int = 8,            # min criteria (of 8) to trigger entry; 8 = strict screener pass
    cost_bps: float = 0.0,            # one-way slippage+commission per fill, in basis points
) -> Optional[BacktestResult]:
    """
    Run Daniel's breakout backtest on a pre-fetched OHLCV DataFrame.

    Requires at least 220 trading bars (EMA200 warmup).  Returns None if
    insufficient data.  All criteria are evaluated using only data available
    at bar i (no look-ahead).
    """
    n = len(df)
    if n < 220:
        return None

    close_s = df["Close"]
    vol_s   = df["Volume"]

    close  = close_s.values
    open_  = df["Open"].values
    dates  = [str(idx.date()) for idx in df.index]

    # ── Precompute indicators (vectorised) ──────────────────────────────── #
    ema21  = close_s.ewm(span=21,  adjust=False).mean().values
    ema50  = close_s.ewm(span=50,  adjust=False).mean().values
    ema100 = close_s.ewm(span=100, adjust=False).mean().values
    ema150 = close_s.ewm(span=150, adjust=False).mean().values
    ema200 = close_s.ewm(span=200, adjust=False).mean().values
    sma50  = close_s.rolling(50).mean().values   # exit signal
    atr20  = _atr(df, 20)
    volume = vol_s.values

    # 6-month high: max of prior 126 closes (excluding current bar)
    high_6m_s   = close_s.shift(1).rolling(126).max().values
    avg_vol_30d = vol_s.shift(1).rolling(30).mean().values
    avg_vol_10d = vol_s.shift(1).rolling(10).mean().values

    with np.errstate(invalid="ignore", divide="ignore"):
        rel_vol = np.where(avg_vol_30d > 0, volume / avg_vol_30d, 0.0)

    # ── Entry criteria at every bar (vectorised) ────────────────────────── #
    c1 = close > ema21
    c2 = ema21 >= ema50
    c3 = ema50 >= ema100
    c4 = np.where(np.isnan(high_6m_s),   False, close >= high_6m_s)
    c5 = rel_vol >= 1.5
    c6 = np.where(np.isnan(avg_vol_10d), False, avg_vol_10d >= 1_000_000)
    c7 = ema100 >= ema150
    c8 = ema150 >= ema200
    criteria_met = (c1.astype(int) + c2.astype(int) + c3.astype(int) + c4.astype(int)
                    + c5.astype(int) + c6.astype(int) + c7.astype(int) + c8.astype(int))
    entry_signal = criteria_met >= min_criteria

    # ── Walk-forward simulation ─────────────────────────────────────────── #
    warmup = 210   # bars needed for EMA200 warmup + vol/high history
    cost   = cost_bps / 10_000.0

    trades:       list[BacktestTrade] = []
    equity_curve: list[dict]          = []
    equity        = initial_capital

    in_position  = False
    entry_equity = 0.0
    entry_price  = 0.0   # raw fill price (reported)
    entry_eff    = 0.0   # fill price incl. one-way costs (used for P&L)
    entry_date   = ""
    entry_idx    = 0
    trail_high   = 0.0
    cooldown     = 0

    for i in range(warmup, n):
        # Mark-to-market at close of bar i
        mtm = (entry_equity * close[i] / entry_eff) if in_position else equity
        equity_curve.append({"date": dates[i], "value": round(mtm, 2)})

        if in_position:
            trail_high = max(trail_high, close[i])
            atr_stop   = trail_high - atr_multiplier * float(atr20[i])

            pct_stop   = trail_high * (1.0 - trail_pct / 100.0)
            exit_sma = (exit_mode in ("SMA50",     "BOTH")) and not np.isnan(sma50[i]) and bool(close[i] < sma50[i])
            exit_atr = (exit_mode in ("ATR_TRAIL", "BOTH")) and not np.isnan(atr_stop) and bool(close[i] < atr_stop)
            exit_pct = (exit_mode == "PCT_TRAIL") and bool(close[i] < pct_stop)
            at_end   = (i == n - 1)

            if exit_sma or exit_atr or exit_pct or at_end:
                exit_price = float(close[i])
                exit_eff   = exit_price * (1.0 - cost)
                pnl_pct    = (exit_eff - entry_eff) / entry_eff * 100
                equity     = entry_equity * exit_eff / entry_eff

                if at_end and not exit_sma and not exit_atr and not exit_pct:
                    reason = "END"
                elif exit_sma and exit_atr:
                    reason = "SMA50+ATR"
                elif exit_pct:
                    reason = "PCT_TRAIL"
                elif exit_sma:
                    reason = "SMA50"
                else:
                    reason = "ATR_STOP"

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
                entry_eff    = entry_price * (1.0 + cost)
                entry_date   = dates[i + 1]
                entry_idx    = i + 1
                trail_high   = entry_price
                in_position  = True

    # ── Performance metrics ─────────────────────────────────────────────── #
    total_return_pct = (equity / initial_capital - 1) * 100

    bh_start      = float(close[warmup])
    bh_end        = float(close[-1])
    bh_return_pct = (bh_end / bh_start - 1) * 100 if bh_start > 0 else 0.0

    # Buy-and-hold max drawdown over the same window
    bh_vals = np.asarray(close[warmup:], dtype=float)
    if len(bh_vals) > 1:
        bh_peak   = np.maximum.accumulate(bh_vals)
        bh_max_dd = float(((bh_vals - bh_peak) / bh_peak * 100).min())
    else:
        bh_max_dd = 0.0

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

    n_trades  = len(trades)
    win_pnls  = [t.pnl_pct for t in trades if t.pnl_pct > 0]
    loss_pnls = [t.pnl_pct for t in trades if t.pnl_pct < 0]
    win_rate  = len(win_pnls) / n_trades * 100 if n_trades > 0 else 0.0
    avg_win   = sum(win_pnls)  / len(win_pnls)  if win_pnls  else 0.0
    avg_loss  = sum(loss_pnls) / len(loss_pnls) if loss_pnls else 0.0
    avg_pnl   = sum(t.pnl_pct for t in trades) / n_trades if n_trades > 0 else 0.0

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
        avg_win_pct=round(avg_win, 2),
        avg_loss_pct=round(avg_loss, 2),
        bh_max_drawdown_pct=round(bh_max_dd, 1),
    )
