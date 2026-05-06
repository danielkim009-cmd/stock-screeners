"""
Point-in-time parameter optimizer for Daniel's breakout strategy on S&P 500.
Tests combinations of key parameters using PIT composition (2016-01-04 → 2026-01-01).
"""
import sys
import time
import pandas as pd
import numpy as np
from itertools import product

sys.path.insert(0, ".")
from app.data.sp500_history import get_sp500_pit_data
from app.data.market_data import fetch_bulk_ohlcv
from app.strategies.daniels_portfolio_backtest import run_daniels_portfolio_backtest

# ── Parameter grid ───────────────────────────────────────────────────────────
TRAIL_PCTS     = [15.0, 20.0, 25.0, 30.0]
MAX_POSITIONS  = [3, 5, 7, 10]
RANK_BYS       = ["RS_20", "RS_63", "RS_126", "REL_VOL"]
REBALANCES     = ["MONTHLY", "QUARTERLY"]

START = "2016-01-04"
END   = "2026-01-01"
INITIAL_CAP = 100_000.0
BENCHMARK = "SPY"

combos = list(product(TRAIL_PCTS, MAX_POSITIONS, RANK_BYS, REBALANCES))
print(f"Testing {len(combos)} parameter combinations")
print(f"  Trail %:    {TRAIL_PCTS}")
print(f"  Positions:  {MAX_POSITIONS}")
print(f"  Rank By:    {RANK_BYS}")
print(f"  Rebalance:  {REBALANCES}")

# ── Fetch data once ──────────────────────────────────────────────────────────
print(f"\nFetching PIT composition for {START} → {END}...")
pit_initial, pit_all, pit_changes = get_sp500_pit_data(START, END)
print(f"  Initial: {len(pit_initial)} | All: {len(pit_all)} | Changes: {len(pit_changes)}")

today = pd.Timestamp.today().normalize()
t_start = pd.Timestamp(START)
t_end = pd.Timestamp(END)
fetch_days = int((today - t_start).days) + 220

all_tkrs = list(set(pit_all + [BENCHMARK]))
print(f"Fetching OHLCV for {len(all_tkrs)} tickers...")
raw_dfs = fetch_bulk_ohlcv(all_tkrs, period_days=fetch_days)

spy_df_raw = raw_dfs.pop(BENCHMARK, None)
spy_df = spy_df_raw[spy_df_raw.index <= t_end] if spy_df_raw is not None else None
stock_dfs = {
    t: df[df.index <= t_end]
    for t, df in raw_dfs.items()
    if df is not None and not df.empty
}
print(f"  {len(stock_dfs)} tickers with data\n")

# ── Run all combos ───────────────────────────────────────────────────────────
results = []
t0 = time.time()

for i, (trail, pos, rank, rebal) in enumerate(combos):
    rebal_mode = "QUARTERLY" if rebal == "QUARTERLY" else "MONTHLY"
    rebal_months = (1, 4, 7, 10) if rebal == "QUARTERLY" else ()

    res = run_daniels_portfolio_backtest(
        stock_dfs=stock_dfs,
        spy_df=spy_df,
        exit_mode="PCT_TRAIL",
        trail_pct=trail,
        max_positions=pos,
        backtest_start=START,
        rank_by=rank,
        rebalance=rebal_mode,
        quarterly_months=rebal_months,
        rebalance_timing="FIRST",
        initial_capital=INITIAL_CAP,
        pit_initial=set(pit_initial),
        pit_changes=pit_changes,
    )

    if res is None:
        continue

    row = {
        "Trail%": trail,
        "Pos": pos,
        "Rank": rank,
        "Rebal": rebal,
        "CAGR": round(res.cagr, 2),
        "Total%": round(res.total_return_pct, 1),
        "MaxDD%": round(res.max_drawdown_pct, 1),
        "Sharpe": round(res.sharpe_ratio, 2),
        "WinRate%": round(res.win_rate_pct, 1),
        "Trades": res.n_trades,
        "AvgPos": round(res.avg_positions, 1),
        "Final$": round(res.final_value, 0),
    }
    results.append(row)

    if (i + 1) % 16 == 0:
        elapsed = time.time() - t0
        pct = (i + 1) / len(combos) * 100
        eta = elapsed / (i + 1) * (len(combos) - i - 1)
        print(f"  [{i+1}/{len(combos)}] {pct:.0f}% done, {elapsed:.0f}s elapsed, ~{eta:.0f}s remaining")

elapsed = time.time() - t0
print(f"\nAll {len(results)} runs complete in {elapsed:.1f}s")

# ── Sort and display ─────────────────────────────────────────────────────────
df = pd.DataFrame(results)

# Get benchmark stats
if spy_df is not None:
    spy_start = spy_df.loc[spy_df.index >= t_start, "Close"].iloc[0]
    spy_end = spy_df["Close"].iloc[-1]
    spy_ret = (spy_end / spy_start - 1) * 100
    n_years = (t_end - t_start).days / 365.25
    spy_cagr = ((spy_end / spy_start) ** (1 / n_years) - 1) * 100
    print(f"\nBenchmark (SPY): CAGR={spy_cagr:.2f}%, Total={spy_ret:.1f}%")

print("\n" + "=" * 130)
print("TOP 20 BY CAGR")
print("=" * 130)
top = df.sort_values("CAGR", ascending=False).head(20).reset_index(drop=True)
top.index = top.index + 1
with pd.option_context("display.max_columns", None, "display.width", 200):
    print(top.to_string())

print("\n" + "=" * 130)
print("TOP 20 BY SHARPE RATIO (risk-adjusted)")
print("=" * 130)
top_sharpe = df.sort_values("Sharpe", ascending=False).head(20).reset_index(drop=True)
top_sharpe.index = top_sharpe.index + 1
with pd.option_context("display.max_columns", None, "display.width", 200):
    print(top_sharpe.to_string())

print("\n" + "=" * 130)
print("TOP 10 BY CAGR WITH MAX DD < 30%")
print("=" * 130)
safe = df[df["MaxDD%"] > -30].sort_values("CAGR", ascending=False).head(10).reset_index(drop=True)
safe.index = safe.index + 1
with pd.option_context("display.max_columns", None, "display.width", 200):
    print(safe.to_string())
