"""
Daniel's Breakout Portfolio Backtester
---------------------------------------
Simulates running the Daniel's breakout screener daily on the S&P 500,
holding up to max_positions at one time, equal-weight position sizing.

Entry:  All 6 Daniel criteria met at close of bar i → enter next bar's open.
Ranking: ties broken by rel_vol descending (biggest institutional surge first).
Exit:   Configurable — SMA50 / 2×ATR(20) trailing stop / PCT trailing stop.
Benchmark: SPY buy-and-hold over the same period.

Note: uses current S&P 500 composition (survivorship bias applies).
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
class PortfolioTrade:
    ticker:      str
    entry_date:  str
    exit_date:   str
    entry_price: float
    exit_price:  float
    pnl_pct:     float
    days_held:   int
    exit_reason: str


@dataclass
class PortfolioBacktestResult:
    n_bars:            int
    exit_mode:         str
    max_positions:     int
    initial_capital:   float
    final_value:       float        # ending portfolio value in dollars
    dollar_gain:       float        # final_value - initial_capital
    cagr:              float        # compound annual growth rate (%)
    trades:            list[PortfolioTrade]
    equity_curve:      list[dict]   # [{date, value}, ...]
    bh_curve:          list[dict]   # [{date, value}, ...] — SPY daily equity curve
    total_return_pct:  float
    bh_return_pct:     float        # SPY buy-and-hold over the same window
    bh_cagr:           float        # SPY CAGR over the same window
    max_drawdown_pct:  float
    bh_max_drawdown_pct: float
    win_rate_pct:      float
    avg_win_pct:       float
    avg_loss_pct:      float
    n_trades:          int
    sharpe_ratio:      float
    avg_trade_pnl_pct: float
    avg_positions:     float        # average concurrent open positions


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #

def _atr(df: pd.DataFrame, period: int = 20) -> np.ndarray:
    h = df["High"]
    l = df["Low"]
    c = df["Close"].shift(1)
    tr = pd.concat([h - l, (h - c).abs(), (l - c).abs()], axis=1).max(axis=1)
    return tr.ewm(com=period - 1, adjust=False).mean().values


# --------------------------------------------------------------------------- #
#  Main function
# --------------------------------------------------------------------------- #

def run_daniels_portfolio_backtest(
    stock_dfs: dict[str, pd.DataFrame],
    spy_df: Optional[pd.DataFrame] = None,
    exit_mode: str = "BOTH",
    trail_pct: float = 10.0,
    atr_multiplier: float = 2.0,
    max_positions: int = 10,
    rebalance: str = "NONE",          # "NONE" | "DAILY" | "WEEKLY" | "MONTHLY"
    initial_capital: float = 100_000.0,
    backtest_start: Optional[str] = None,   # "YYYY-MM-DD" — skip bars before this date
    rank_by: str = "REL_VOL",         # "REL_VOL" | "RS_20" | "RS_63" | "RS_126" | "RS_VOL"
) -> Optional[PortfolioBacktestResult]:
    """
    Run a portfolio-level walk-forward backtest of Daniel's breakout strategy.

    Parameters
    ----------
    stock_dfs  : {ticker: OHLCV DataFrame} — the universe to screen
    spy_df     : SPY OHLCV DataFrame for buy-and-hold benchmark
    exit_mode  : "SMA50" | "ATR_TRAIL" | "PCT_TRAIL" | "BOTH"
    trail_pct  : percentage drawdown from peak to trigger PCT_TRAIL exit
    atr_multiplier : multiplier for ATR trailing stop
    max_positions  : maximum concurrent open positions
    rebalance  : "NONE" | "DAILY" | "WEEKLY" | "MONTHLY"
                 On each rebalance date, force-exit positions no longer in
                 the top-N signals and replace them with current top signals.
    initial_capital : starting portfolio value
    """
    if not stock_dfs:
        return None

    WARMUP = 130   # bars needed for EMA100 + 6m-high + vol history

    # ── 0. Precompute benchmark ROC lookup {date: roc_N} ─────────────────── #
    bm_roc: dict[str, dict] = {}   # date → {"r20": float, "r63": float, "r126": float}
    if spy_df is not None and len(spy_df) >= 130:
        bm_close = spy_df["Close"]
        with np.errstate(invalid="ignore", divide="ignore"):
            bm_r20  = (bm_close / bm_close.shift(20)  - 1).values
            bm_r63  = (bm_close / bm_close.shift(63)  - 1).values
            bm_r126 = (bm_close / bm_close.shift(126) - 1).values
        for i, idx in enumerate(spy_df.index):
            d = str(idx.date())
            bm_roc[d] = {
                "r20":  float(bm_r20[i])  if not np.isnan(bm_r20[i])  else 0.0,
                "r63":  float(bm_r63[i])  if not np.isnan(bm_r63[i])  else 0.0,
                "r126": float(bm_r126[i]) if not np.isnan(bm_r126[i]) else 0.0,
            }

    # ── 1. Precompute indicators for every stock ─────────────────────────── #
    precomputed: dict[str, dict] = {}

    for ticker, df in stock_dfs.items():
        if df is None or len(df) < WARMUP + 10:
            continue

        close_s = df["Close"]
        vol_s   = df["Volume"]
        close   = close_s.values
        open_   = df["Open"].values
        dates   = [str(idx.date()) for idx in df.index]

        ema21  = close_s.ewm(span=21,  adjust=False).mean().values
        ema50  = close_s.ewm(span=50,  adjust=False).mean().values
        ema100 = close_s.ewm(span=100, adjust=False).mean().values
        sma50  = close_s.rolling(50).mean().values
        atr20  = _atr(df, 20)
        volume = vol_s.values

        high_6m     = close_s.shift(1).rolling(126).max().values
        avg_vol_30d = vol_s.shift(1).rolling(30).mean().values
        avg_vol_10d = vol_s.shift(1).rolling(10).mean().values

        with np.errstate(invalid="ignore", divide="ignore"):
            rel_vol = np.where(avg_vol_30d > 0, volume / avg_vol_30d, 0.0)

        c1 = close > ema21
        c2 = ema21 >= ema50
        c3 = ema50 >= ema100
        c4 = np.where(np.isnan(high_6m),   False, close >= high_6m)
        c5 = rel_vol >= 1.5
        c6 = np.where(np.isnan(avg_vol_10d), False, avg_vol_10d >= 1_000_000)
        signal = c1 & c2 & c3 & c4 & c5 & c6

        date_to_idx = {d: i for i, d in enumerate(dates)}

        # RS arrays: stock_roc_N / benchmark_roc_N (relative strength vs benchmark)
        with np.errstate(invalid="ignore", divide="ignore"):
            stk_r20  = (close_s / close_s.shift(20)  - 1).values
            stk_r63  = (close_s / close_s.shift(63)  - 1).values
            stk_r126 = (close_s / close_s.shift(126) - 1).values

        rs_20  = np.full(len(dates), np.nan)
        rs_63  = np.full(len(dates), np.nan)
        rs_126 = np.full(len(dates), np.nan)
        for i, d in enumerate(dates):
            bm = bm_roc.get(d)
            if bm is None:
                continue
            if not np.isnan(stk_r20[i]):
                rs_20[i]  = stk_r20[i]  - bm["r20"]
            if not np.isnan(stk_r63[i]):
                rs_63[i]  = stk_r63[i]  - bm["r63"]
            if not np.isnan(stk_r126[i]):
                rs_126[i] = stk_r126[i] - bm["r126"]

        precomputed[ticker] = {
            "dates":       dates,
            "close":       close,
            "open":        open_,
            "ema21":       ema21,
            "ema50":       ema50,
            "sma50":       sma50,
            "atr20":       atr20,
            "rel_vol":     rel_vol,
            "rs_20":       rs_20,
            "rs_63":       rs_63,
            "rs_126":      rs_126,
            "signal":      signal,
            "date_to_idx": date_to_idx,
            "n":           len(dates),
        }

    if not precomputed:
        return None

    # ── 2. Build master date calendar ────────────────────────────────────── #
    all_dates_set: set[str] = set()
    for pc in precomputed.values():
        all_dates_set.update(pc["dates"])
    all_dates = sorted(all_dates_set)
    n_total = len(all_dates)
    date_to_master_idx = {d: i for i, d in enumerate(all_dates)}

    if n_total < WARMUP + 30:
        return None

    # ── Rebalance cadence helper ─────────────────────────────────────────── #
    _rebal = rebalance.upper()

    def is_rebalance_date(di: int, date: str) -> bool:
        if _rebal == "NONE":
            return False
        if _rebal == "DAILY":
            return True
        # For weekly/monthly use the calendar position of the master date list
        if di == 0:
            return False
        prev_date = all_dates[di - 1]
        d_cur  = pd.Timestamp(date)
        d_prev = pd.Timestamp(prev_date)
        if _rebal == "WEEKLY":
            return d_cur.isocalendar()[1] != d_prev.isocalendar()[1]
        if _rebal == "MONTHLY":
            return d_cur.month != d_prev.month
        if _rebal == "QUARTERLY":
            return ((d_cur.month - 1) // 3) != ((d_prev.month - 1) // 3)
        return False

    # ── Ranking score helper ─────────────────────────────────────────────── #
    _rank = rank_by.upper()

    def rank_score(pc: dict, idx: int) -> float:
        rv = float(pc["rel_vol"][idx])
        if _rank == "REL_VOL":
            return rv
        if _rank == "RS_20":
            v = float(pc["rs_20"][idx])
            return v if not np.isnan(v) else -999.0
        if _rank == "RS_63":
            v = float(pc["rs_63"][idx])
            return v if not np.isnan(v) else -999.0
        if _rank == "RS_126":
            v = float(pc["rs_126"][idx])
            return v if not np.isnan(v) else -999.0
        if _rank == "RS_VOL":
            v = float(pc["rs_63"][idx])
            return rv * v if not np.isnan(v) else -999.0
        return rv

    # ── 3. Portfolio walk-forward ─────────────────────────────────────────── #
    cash      = float(initial_capital)
    positions: dict[str, dict] = {}          # ticker → position info
    pending:   list[tuple[str, float]] = []  # (ticker, score) entered next open
    trades:    list[PortfolioTrade] = []
    equity_curve: list[dict] = []
    position_counts: list[int] = []

    def portfolio_value(date: str) -> float:
        total = cash
        for t, pos in positions.items():
            pc = precomputed.get(t)
            if pc is None:
                total += pos["position_value"]
                continue
            idx = pc["date_to_idx"].get(date)
            if idx is None:
                total += pos["position_value"]
                continue
            cp = float(pc["close"][idx])
            if cp > 0 and not np.isnan(cp):
                total += pos["position_value"] * cp / pos["entry_price"]
            else:
                total += pos["position_value"]
        return total

    for di, date in enumerate(all_dates):
        if di < WARMUP:
            continue
        if backtest_start and date < backtest_start:
            continue

        # ── 3a. Enter pending positions at today's open ───────────────────── #
        for ticker, _ in pending:
            if len(positions) >= max_positions:
                break
            if ticker in positions:
                continue
            pc = precomputed.get(ticker)
            if pc is None:
                continue
            idx = pc["date_to_idx"].get(date)
            if idx is None or idx >= pc["n"]:
                continue
            entry_price = float(pc["open"][idx])
            if entry_price <= 0 or np.isnan(entry_price):
                continue

            # Equal weight: 1/max_positions of current total equity
            total_eq   = portfolio_value(date)
            slot_value = total_eq / max_positions
            if cash < slot_value * 0.5:
                continue
            alloc = min(slot_value, cash)
            cash -= alloc
            positions[ticker] = {
                "entry_price":    entry_price,
                "entry_date":     date,
                "trail_high":     entry_price,
                "position_value": alloc,
                "entry_master_idx": di,
            }
        pending = []

        # ── 3b. Check exits at today's close ─────────────────────────────── #
        exited: list[str] = []
        for ticker, pos in positions.items():
            pc = precomputed.get(ticker)
            if pc is None:
                continue
            idx = pc["date_to_idx"].get(date)
            if idx is None:
                continue

            cp = float(pc["close"][idx])
            if np.isnan(cp) or cp <= 0:
                continue

            pos["trail_high"] = max(pos["trail_high"], cp)
            atr_val  = float(pc["atr20"][idx])
            atr_stop = pos["trail_high"] - atr_multiplier * atr_val
            pct_stop = pos["trail_high"] * (1.0 - trail_pct / 100.0)
            sma50_v  = float(pc["sma50"][idx])

            exit_sma = exit_mode in ("SMA50", "BOTH") and not np.isnan(sma50_v) and cp < sma50_v
            exit_atr = exit_mode in ("ATR_TRAIL", "BOTH") and not np.isnan(atr_stop) and cp < atr_stop
            exit_pct = exit_mode == "PCT_TRAIL" and cp < pct_stop
            at_end   = (di == n_total - 1)

            if exit_sma or exit_atr or exit_pct or at_end:
                exit_val = pos["position_value"] * cp / pos["entry_price"]
                pnl_pct  = (cp - pos["entry_price"]) / pos["entry_price"] * 100
                cash    += exit_val

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

                days_held = di - pos["entry_master_idx"]

                trades.append(PortfolioTrade(
                    ticker=ticker,
                    entry_date=pos["entry_date"],
                    exit_date=date,
                    entry_price=round(pos["entry_price"], 2),
                    exit_price=round(cp, 2),
                    pnl_pct=round(pnl_pct, 2),
                    days_held=days_held,
                    exit_reason=reason,
                ))
                exited.append(ticker)

        for t in exited:
            del positions[t]

        # ── 3b2. Rebalance: force-exit positions outside top-N signals ──────── #
        if is_rebalance_date(di, date) and positions:
            # Build full ranked signal list for today
            all_signals: list[tuple[str, float]] = []
            for ticker, pc in precomputed.items():
                idx = pc["date_to_idx"].get(date)
                if idx is None or idx < WARMUP:
                    continue
                if bool(pc["signal"][idx]):
                    all_signals.append((ticker, rank_score(pc, idx)))
            all_signals.sort(key=lambda x: -x[1])
            target_set = {t for t, _ in all_signals[:max_positions]}

            rebal_exited: list[str] = []
            for ticker, pos in positions.items():
                if ticker in target_set:
                    continue  # keep it
                pc = precomputed.get(ticker)
                if pc is None:
                    continue
                idx = pc["date_to_idx"].get(date)
                if idx is None:
                    continue
                cp = float(pc["close"][idx])
                if np.isnan(cp) or cp <= 0:
                    continue
                exit_val = pos["position_value"] * cp / pos["entry_price"]
                pnl_pct  = (cp - pos["entry_price"]) / pos["entry_price"] * 100
                cash    += exit_val
                trades.append(PortfolioTrade(
                    ticker=ticker,
                    entry_date=pos["entry_date"],
                    exit_date=date,
                    entry_price=round(pos["entry_price"], 2),
                    exit_price=round(cp, 2),
                    pnl_pct=round(pnl_pct, 2),
                    days_held=di - pos["entry_master_idx"],
                    exit_reason="REBALANCE",
                ))
                rebal_exited.append(ticker)

            for t in rebal_exited:
                del positions[t]

            # Queue the top-N signals not already held for entry tomorrow
            new_entries = [(t, rv) for t, rv in all_signals[:max_positions * 2] if t not in positions]
            slots = max_positions - len(positions)
            pending = new_entries[:slots * 2]

        # ── 3c. Scan for new breakout signals ────────────────────────────── #
        if len(positions) < max_positions:
            new_signals: list[tuple[str, float]] = []
            for ticker, pc in precomputed.items():
                if ticker in positions:
                    continue
                idx = pc["date_to_idx"].get(date)
                if idx is None or idx < WARMUP:
                    continue
                if bool(pc["signal"][idx]) and idx + 1 < pc["n"]:
                    new_signals.append((ticker, rank_score(pc, idx)))

            new_signals.sort(key=lambda x: -x[1])
            slots = max_positions - len(positions)
            pending = new_signals[:slots * 2]

        # ── 3d. Record equity snapshot ────────────────────────────────────── #
        equity_curve.append({"date": date, "value": round(portfolio_value(date), 2)})
        position_counts.append(len(positions))

    if not equity_curve:
        return None

    # ── 4. Performance metrics ────────────────────────────────────────────── #
    start_val = equity_curve[0]["value"]
    end_val   = equity_curve[-1]["value"]
    total_return_pct = (end_val / start_val - 1) * 100 if start_val > 0 else 0.0

    # SPY buy-and-hold over same date range — real daily curve
    bh_return_pct = 0.0
    bh_cagr       = 0.0
    bh_curve: list[dict] = []
    if spy_df is not None and len(spy_df) >= 2:
        spy_dates = [str(idx.date()) for idx in spy_df.index]
        spy_close = spy_df["Close"].values
        spy_dmap  = {d: i for i, d in enumerate(spy_dates)}
        eq_start_date = equity_curve[0]["date"]
        eq_end_date   = equity_curve[-1]["date"]
        si = spy_dmap.get(eq_start_date, 0)
        ei = spy_dmap.get(eq_end_date,   len(spy_close) - 1)
        spy_start_price = float(spy_close[si])
        if si < ei and spy_start_price > 0:
            bh_return_pct = (float(spy_close[ei]) / spy_start_price - 1) * 100
            bh_years = (pd.Timestamp(eq_end_date) - pd.Timestamp(eq_start_date)).days / 365.25
            if bh_years > 0:
                bh_cagr = ((float(spy_close[ei]) / spy_start_price) ** (1 / bh_years) - 1) * 100
            # Build normalized SPY curve aligned to equity_curve dates
            eq_dates_set = {e["date"] for e in equity_curve}
            for d, ci in spy_dmap.items():
                if d < eq_start_date or d > eq_end_date:
                    continue
                if d not in eq_dates_set:
                    continue
                cp = float(spy_close[ci])
                if cp > 0 and not np.isnan(cp):
                    bh_curve.append({"date": d, "value": round(initial_capital * cp / spy_start_price, 2)})
            bh_curve.sort(key=lambda x: x["date"])

    # Benchmark max drawdown from the normalized bh_curve
    bh_max_drawdown_pct = 0.0
    if len(bh_curve) > 1:
        bh_vals = np.array([e["value"] for e in bh_curve], dtype=float)
        bh_peak = np.maximum.accumulate(bh_vals)
        bh_max_drawdown_pct = float(((bh_vals - bh_peak) / bh_peak * 100).min())

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
    wins      = len(win_pnls)
    win_rate  = wins / n_trades * 100 if n_trades > 0 else 0.0
    avg_win   = sum(win_pnls)  / len(win_pnls)  if win_pnls  else 0.0
    avg_loss  = sum(loss_pnls) / len(loss_pnls) if loss_pnls else 0.0
    avg_pnl   = sum(t.pnl_pct for t in trades) / n_trades if n_trades > 0 else 0.0
    avg_pos  = sum(position_counts) / len(position_counts) if position_counts else 0.0

    final_value = end_val
    dollar_gain = final_value - initial_capital

    # CAGR: use actual calendar days spanned by the equity curve
    if len(equity_curve) >= 2:
        years = (pd.Timestamp(equity_curve[-1]["date"]) - pd.Timestamp(equity_curve[0]["date"])).days / 365.25
        cagr  = ((final_value / initial_capital) ** (1 / years) - 1) * 100 if years > 0 and initial_capital > 0 else 0.0
    else:
        cagr = 0.0

    return PortfolioBacktestResult(
        n_bars=n_total - WARMUP,
        exit_mode=exit_mode,
        max_positions=max_positions,
        initial_capital=round(initial_capital, 2),
        final_value=round(final_value, 2),
        dollar_gain=round(dollar_gain, 2),
        cagr=round(cagr, 2),
        trades=trades,
        equity_curve=equity_curve,
        bh_curve=bh_curve,
        total_return_pct=round(total_return_pct, 2),
        bh_return_pct=round(bh_return_pct, 2),
        bh_cagr=round(bh_cagr, 2),
        max_drawdown_pct=round(max_dd, 1),
        bh_max_drawdown_pct=round(bh_max_drawdown_pct, 1),
        win_rate_pct=round(win_rate, 1),
        avg_win_pct=round(avg_win, 2),
        avg_loss_pct=round(avg_loss, 2),
        n_trades=n_trades,
        sharpe_ratio=round(sharpe, 2),
        avg_trade_pnl_pct=round(avg_pnl, 2),
        avg_positions=round(avg_pos, 1),
    )
