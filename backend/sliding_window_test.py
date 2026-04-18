"""
Sliding 10-year window backtest for Daniel's breakout strategy on S&P 500.
Config: PCT_TRAIL 25%, max 3 positions, RS_20 ranking, Quarterly rebalance.
Windows: 3/1/2006→3/1/2016, 3/1/2007→3/1/2017, ..., 3/1/2016→3/1/2026
Data is fetched once for the full period and sliced per window.
"""
import sys
import pandas as pd
import numpy as np

sys.path.insert(0, ".")
from app.data.universes import fetch_tickers
from app.data.market_data import fetch_bulk_ohlcv
from app.strategies.daniels_portfolio_backtest import run_daniels_portfolio_backtest

# ── Config ────────────────────────────────────────────────────────────────────
EXIT_MODE      = "PCT_TRAIL"
TRAIL_PCT      = 25.0
MAX_POSITIONS  = 3
REBALANCE      = "QUARTERLY"
RANK_BY        = "RS_20"
INITIAL_CAP    = 100_000.0
UNIVERSE       = "sp500"
BENCHMARK      = "SPY"
WARMUP_DAYS    = 220   # extra calendar days for indicator warmup

START_YEARS = range(2006, 2017)   # 2006..2016 inclusive
WINDOW_YEARS = 10

# ── Fetch data once (full period 2006-01-01 to today) ────────────────────────
print("Fetching tickers…")
tickers = fetch_tickers(UNIVERSE)
print(f"  {len(tickers)} tickers")

fetch_days = (pd.Timestamp.today() - pd.Timestamp("2006-01-01")).days + WARMUP_DAYS
print(f"Fetching {fetch_days} days of OHLCV for {len(tickers)+1} symbols (this takes a while)…")
all_tickers = list(set(tickers + [BENCHMARK]))
raw_dfs = fetch_bulk_ohlcv(all_tickers, period_days=fetch_days)
spy_df_full = raw_dfs.pop(BENCHMARK, None)
print(f"  Data ready for {len(raw_dfs)} tickers")

# ── Run each window ───────────────────────────────────────────────────────────
rows = []
for start_year in START_YEARS:
    t_start = pd.Timestamp(f"{start_year}-03-01")
    t_end   = pd.Timestamp(f"{start_year + WINDOW_YEARS}-03-01")

    # Slice each df: keep full history up to t_end (warmup before t_start is needed)
    def _trim(df):
        if df is None or df.empty:
            return df
        return df[df.index <= t_end]

    stock_dfs = {t: _trim(df) for t, df in raw_dfs.items() if df is not None and not df.empty}
    spy_df    = _trim(spy_df_full)

    label = f"{t_start.strftime('%Y-%m-%d')} → {t_end.strftime('%Y-%m-%d')}"
    print(f"Running {label}…", end=" ", flush=True)

    result = run_daniels_portfolio_backtest(
        stock_dfs=stock_dfs,
        spy_df=spy_df,
        exit_mode=EXIT_MODE,
        trail_pct=TRAIL_PCT,
        max_positions=MAX_POSITIONS,
        rebalance=REBALANCE,
        initial_capital=INITIAL_CAP,
        backtest_start=str(t_start.date()),
        rank_by=RANK_BY,
    )

    if result is None:
        print("NO DATA")
        rows.append({"Window": label})
        continue

    final = result.final_value
    gain  = result.dollar_gain
    rows.append({
        "Window":        label,
        "Total Return":  f"{result.total_return_pct:+.1f}%",
        "CAGR":          f"{result.cagr:+.1f}%",
        f"{BENCHMARK} Return": f"{result.bh_return_pct:+.1f}%",
        f"{BENCHMARK} CAGR":   f"{result.bh_cagr:+.1f}%",
        "Alpha":         f"{result.total_return_pct - result.bh_return_pct:+.1f}%",
        "Max DD":        f"{result.max_drawdown_pct:.1f}%",
        f"{BENCHMARK} Max DD": f"{result.bh_max_drawdown_pct:.1f}%",
        "Final $":       f"${final:,.0f}",
        "Gain $":        f"${gain:+,.0f}",
        "Sharpe":        f"{result.sharpe_ratio:.2f}",
        "Win Rate":      f"{result.win_rate_pct:.1f}%",
        "Avg Win":       f"{result.avg_win_pct:+.1f}%",
        "Avg Loss":      f"{result.avg_loss_pct:+.1f}%",
        "Trades":        result.n_trades,
    })
    print(f"CAGR={result.cagr:+.1f}%  SPY={result.bh_cagr:+.1f}%  Alpha={result.total_return_pct-result.bh_return_pct:+.1f}%  MaxDD={result.max_drawdown_pct:.1f}%")

# ── Print summary table ───────────────────────────────────────────────────────
print("\n" + "="*120)
print("SLIDING 10-YEAR WINDOW RESULTS — S&P 500 | PCT_TRAIL 25% | 3 positions | RS_20 | Quarterly rebalance")
print("="*120)
df = pd.DataFrame(rows).set_index("Window")
with pd.option_context("display.max_columns", None, "display.width", 200):
    print(df.to_string())
print("="*120)
