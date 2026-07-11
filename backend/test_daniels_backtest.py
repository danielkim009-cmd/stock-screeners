"""Functional tests for the improved Daniel's breakout backtests (synthetic data)."""
import sys, math
import numpy as np
import pandas as pd

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))

from app.strategies.daniels_backtest import run_daniels_backtest
from app.strategies.daniels_portfolio_backtest import run_daniels_portfolio_backtest
from app.strategies.daniels_breakout import screen_daniels_breakout

rng = np.random.default_rng(42)


def make_df(n=700, trend=0.0009, vol=0.015, seed=None, start="2023-01-02"):
    r = np.random.default_rng(seed)
    rets = r.normal(trend, vol, n)
    close = 50 * np.exp(np.cumsum(rets))
    open_ = close * (1 + r.normal(0, 0.003, n))
    high = np.maximum(open_, close) * (1 + abs(r.normal(0, 0.005, n)))
    low = np.minimum(open_, close) * (1 - abs(r.normal(0, 0.005, n)))
    volume = r.integers(1_500_000, 6_000_000, n).astype(float)
    # inject periodic volume surges so C5 can trigger
    volume[::7] *= 2.5
    idx = pd.bdate_range(start, periods=n)
    return pd.DataFrame({"Open": open_, "High": high, "Low": low,
                         "Close": close, "Volume": volume}, index=idx)


fails = []
def check(name, cond, extra=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name} {extra}")
    if not cond:
        fails.append(name)


# ── 1. Screener still works ────────────────────────────────────────────── #
df = make_df(seed=1)
sig = screen_daniels_breakout(df, "TEST")
check("screener returns signal", sig is not None)

# ── 2. Single-ticker backtest: new fields + criteria alignment ─────────── #
res8 = run_daniels_backtest(df, "TEST", exit_mode="BOTH", min_criteria=8)
res6 = run_daniels_backtest(df, "TEST", exit_mode="BOTH", min_criteria=6)
check("single backtest runs (min_criteria=8)", res8 is not None)
check("single backtest runs (min_criteria=6)", res6 is not None)
if res8 and res6:
    check("new fields exist", hasattr(res8, "avg_win_pct") and hasattr(res8, "bh_max_drawdown_pct"),
          f"avg_win={res8.avg_win_pct} avg_loss={res8.avg_loss_pct} bh_dd={res8.bh_max_drawdown_pct}")
    check("stricter criteria -> fewer or equal trades", res8.n_trades <= res6.n_trades,
          f"({res8.n_trades} vs {res6.n_trades})")

# ── 3. Costs reduce returns ────────────────────────────────────────────── #
res_free = run_daniels_backtest(df, "TEST", exit_mode="BOTH", min_criteria=6, cost_bps=0)
res_cost = run_daniels_backtest(df, "TEST", exit_mode="BOTH", min_criteria=6, cost_bps=20)
if res_free and res_cost and res_free.n_trades > 0:
    check("costs reduce total return", res_cost.total_return_pct < res_free.total_return_pct,
          f"({res_cost.total_return_pct}% vs {res_free.total_return_pct}%, {res_free.n_trades} trades)")
    # expected drag ≈ 2 fills × 20bps × n_trades (compounded, so approximate)
    drag = res_free.total_return_pct - res_cost.total_return_pct
    check("cost drag plausible", 0 < drag < res_free.n_trades * 2 * 0.20 * 3 + 5, f"drag={drag:.2f}pp")

# ── 4. Portfolio backtest: baseline still runs, equity conserved ───────── #
universe = {f"S{i}": make_df(seed=10 + i, trend=0.0004 + 0.0002 * (i % 4)) for i in range(12)}
spy = make_df(seed=99, trend=0.0004, vol=0.010)

base = run_daniels_portfolio_backtest(universe, spy_df=spy, min_criteria=6, max_positions=5)
check("portfolio backtest runs", base is not None)
if base:
    check("portfolio has trades", base.n_trades > 0, f"n_trades={base.n_trades}")
    check("final value sane", base.final_value > 0)

# ── 5. Portfolio costs reduce returns ──────────────────────────────────── #
cost = run_daniels_portfolio_backtest(universe, spy_df=spy, min_criteria=6, max_positions=5, cost_bps=20)
if base and cost:
    check("portfolio costs reduce return", cost.total_return_pct < base.total_return_pct,
          f"({cost.total_return_pct}% vs {base.total_return_pct}%)")

# ── 6. Regime filter: bear benchmark blocks entries ────────────────────── #
bear_spy = make_df(seed=99, trend=-0.0012, vol=0.012)
reg = run_daniels_portfolio_backtest(universe, spy_df=bear_spy, min_criteria=6, max_positions=5,
                                     regime_filter=True)
noreg = run_daniels_portfolio_backtest(universe, spy_df=bear_spy, min_criteria=6, max_positions=5,
                                       regime_filter=False)
if reg and noreg:
    check("regime filter reduces trade count", reg.n_trades <= noreg.n_trades,
          f"({reg.n_trades} vs {noreg.n_trades})")

# ── 7. ATR risk sizing runs and differs from equal weight ──────────────── #
atrs = run_daniels_portfolio_backtest(universe, spy_df=spy, min_criteria=6, max_positions=5,
                                      sizing="ATR_RISK", risk_pct=0.75)
if base and atrs:
    check("ATR sizing runs", atrs.n_trades > 0, f"n_trades={atrs.n_trades}")
    check("ATR sizing changes equity path", atrs.final_value != base.final_value,
          f"({atrs.final_value} vs {base.final_value})")

# ── 8. Delisted ticker: force-exit, no zombie ──────────────────────────── #
universe2 = dict(universe)
# truncate one ticker's data 100 bars before the end -> simulated delisting
universe2["S3"] = universe2["S3"].iloc[:-100]
delist = run_daniels_portfolio_backtest(universe2, spy_df=spy, min_criteria=6, max_positions=5)
if delist:
    reasons = {t.exit_reason for t in delist.trades}
    s3_trades = [t for t in delist.trades if t.ticker == "S3"]
    open_ended_s3 = [t for t in s3_trades if t.exit_reason == "END"]
    print(f"    exit reasons seen: {reasons}")
    check("no S3 trade dangling at END after data gap",
          all(t.exit_date <= str(universe2['S3'].index[-1].date()) for t in s3_trades))

# ── 9. Backward compat: default params ≈ old behavior (no costs, EQUAL) ── #
base2 = run_daniels_portfolio_backtest(universe, spy_df=spy, min_criteria=6, max_positions=5)
if base and base2:
    check("deterministic across runs", base2.final_value == base.final_value)

print()
if fails:
    print("FAILURES:", fails)
    sys.exit(1)
print("ALL TESTS PASSED")
