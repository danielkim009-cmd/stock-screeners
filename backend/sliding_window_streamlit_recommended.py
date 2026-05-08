"""
Sliding 10-year window backtest — Daniel's Breakout on S&P 500
Config: Streamlit recommended settings
  PCT_TRAIL 25%, 6 positions, RS_126 ranking, Monthly rebalance, C4 lookback 63 bars

Uses point-in-time S&P 500 composition to avoid survivorship bias.
Windows: 2006-03-01 → 2016-03-01 through 2016-03-01 → 2026-03-01
Data fetched once for full period and sliced per window.
"""
import sys
import json
import os
import pandas as pd
import numpy as np

sys.path.insert(0, ".")
from app.data.market_data import fetch_bulk_ohlcv
from app.data.sp500_history import get_sp500_pit_data
from app.strategies.daniels_portfolio_backtest import run_daniels_portfolio_backtest

# ── Config (Streamlit recommended settings for S&P 500) ──────────────────────
EXIT_MODE      = "PCT_TRAIL"
TRAIL_PCT      = 25.0
MAX_POSITIONS  = 5
REBALANCE      = "QUARTERLY"
RANK_BY        = "RS_126"
HIGH_LOOKBACK  = 63        # C4: 3-month high lookback
MIN_CRITERIA   = 6
INITIAL_CAP    = 100_000.0
UNIVERSE       = "sp500"
BENCHMARK      = "SPY"
WARMUP_DAYS    = 220

START_YEARS = range(2006, 2017)   # 2006..2016 inclusive
WINDOW_YEARS = 10

# ── Fetch point-in-time data for the full range ───────────────────────────────
FULL_START = "2006-01-01"
FULL_END   = "2026-03-01"

print("Fetching point-in-time S&P 500 composition for full range…")
pit_initial_full, pit_all_full, pit_changes_full = get_sp500_pit_data(FULL_START, FULL_END)
print(f"  {len(pit_initial_full)} tickers at start, {len(pit_all_full)} total across full range")

fetch_days = (pd.Timestamp.today() - pd.Timestamp(FULL_START)).days + WARMUP_DAYS
all_fetch = list(set(pit_all_full + [BENCHMARK]))
print(f"Fetching {fetch_days} days of OHLCV for {len(all_fetch)} symbols (this takes a while)…")
raw_dfs = fetch_bulk_ohlcv(all_fetch, period_days=fetch_days)
spy_df_full = raw_dfs.pop(BENCHMARK, None)
print(f"  Data ready for {len(raw_dfs)} tickers")

# ── Run each window ───────────────────────────────────────────────────────────
rows = []
results_detail = []  # store raw numeric results for HTML generation

for start_year in START_YEARS:
    t_start = pd.Timestamp(f"{start_year}-03-01")
    t_end   = pd.Timestamp(f"{start_year + WINDOW_YEARS}-03-01")

    def _trim(df):
        if df is None or df.empty:
            return df
        return df[df.index <= t_end]

    # Get point-in-time composition for this window
    w_start_str = str(t_start.date())
    w_end_str   = str(t_end.date())
    pit_initial_w, pit_all_w, pit_changes_w = get_sp500_pit_data(w_start_str, w_end_str)

    # Only include tickers relevant to this window
    stock_dfs = {
        t: _trim(df)
        for t, df in raw_dfs.items()
        if t in set(pit_all_w) and df is not None and not df.empty
    }
    spy_df = _trim(spy_df_full)

    label = f"{t_start.strftime('%Y-%m-%d')} → {t_end.strftime('%Y-%m-%d')}"
    print(f"Running {label} (PIT: {len(pit_initial_w)} initial, {len(pit_all_w)} total tickers)…", end=" ", flush=True)

    result = run_daniels_portfolio_backtest(
        stock_dfs=stock_dfs,
        spy_df=spy_df,
        exit_mode=EXIT_MODE,
        trail_pct=TRAIL_PCT,
        max_positions=MAX_POSITIONS,
        min_criteria=MIN_CRITERIA,
        high_lookback=HIGH_LOOKBACK,
        rebalance=REBALANCE,
        initial_capital=INITIAL_CAP,
        backtest_start=str(t_start.date()),
        rank_by=RANK_BY,
        pit_initial=set(pit_initial_w),
        pit_changes=pit_changes_w,
    )

    if result is None:
        print("NO DATA")
        rows.append({"Window": label})
        results_detail.append(None)
        continue

    alpha = result.total_return_pct - result.bh_return_pct
    beat  = result.cagr > result.bh_cagr

    rows.append({
        "Window":        label,
        "Total Return":  f"{result.total_return_pct:+.1f}%",
        "CAGR":          f"{result.cagr:+.1f}%",
        f"{BENCHMARK} Return": f"{result.bh_return_pct:+.1f}%",
        f"{BENCHMARK} CAGR":   f"{result.bh_cagr:+.1f}%",
        "Alpha":         f"{alpha:+.1f}%",
        "Max DD":        f"{result.max_drawdown_pct:.1f}%",
        f"{BENCHMARK} Max DD": f"{result.bh_max_drawdown_pct:.1f}%",
        "Final $":       f"${result.final_value:,.0f}",
        "Gain $":        f"${result.dollar_gain:+,.0f}",
        "Sharpe":        f"{result.sharpe_ratio:.2f}",
        "Win Rate":      f"{result.win_rate_pct:.1f}%",
        "Avg Win":       f"{result.avg_win_pct:+.1f}%",
        "Avg Loss":      f"{result.avg_loss_pct:+.1f}%",
        "Trades":        result.n_trades,
    })
    results_detail.append({
        "label":          label,
        "start_year":     start_year,
        "total_ret":      result.total_return_pct,
        "cagr":           result.cagr,
        "bh_ret":         result.bh_return_pct,
        "bh_cagr":        result.bh_cagr,
        "alpha":          alpha,
        "max_dd":         result.max_drawdown_pct,
        "bh_max_dd":      result.bh_max_drawdown_pct,
        "final_val":      result.final_value,
        "dollar_gain":    result.dollar_gain,
        "sharpe":         result.sharpe_ratio,
        "win_rate":       result.win_rate_pct,
        "avg_win":        result.avg_win_pct,
        "avg_loss":       result.avg_loss_pct,
        "n_trades":       result.n_trades,
        "beat_spy":       beat,
    })
    print(f"CAGR={result.cagr:+.1f}%  SPY={result.bh_cagr:+.1f}%  Alpha={alpha:+.1f}%  MaxDD={result.max_drawdown_pct:.1f}%")

# ── Print summary table ───────────────────────────────────────────────────────
print("\n" + "="*130)
print(f"SLIDING 10-YEAR WINDOW RESULTS — S&P 500 | PCT_TRAIL {TRAIL_PCT}% | {MAX_POSITIONS} positions | {RANK_BY} | {REBALANCE} rebalance | C4 lookback {HIGH_LOOKBACK}d")
print("="*130)
df_out = pd.DataFrame(rows).set_index("Window")
with pd.option_context("display.max_columns", None, "display.width", 200):
    print(df_out.to_string())
print("="*130)

# ── Compute summary stats for HTML ────────────────────────────────────────────
valid = [r for r in results_detail if r is not None]
avg_cagr       = np.mean([r["cagr"]     for r in valid]) if valid else 0
avg_spy_cagr   = np.mean([r["bh_cagr"]  for r in valid]) if valid else 0
beats_spy      = sum(1 for r in valid if r["beat_spy"])
avg_max_dd     = np.mean([r["max_dd"]   for r in valid]) if valid else 0
avg_spy_dd     = np.mean([r["bh_max_dd"] for r in valid]) if valid else 0
avg_win_rate   = np.mean([r["win_rate"] for r in valid]) if valid else 0
avg_sharpe     = np.mean([r["sharpe"]   for r in valid]) if valid else 0
best_cagr      = max((r["cagr"] for r in valid), default=0)
best_label     = next((r["label"] for r in valid if r["cagr"] == best_cagr), "")
worst_cagr     = min((r["cagr"] for r in valid), default=0)
worst_label    = next((r["label"] for r in valid if r["cagr"] == worst_cagr), "")

# ── Generate HTML ─────────────────────────────────────────────────────────────
def _cls(v, flip=False):
    """Return CSS class based on sign."""
    if flip:
        return "neg" if v > 0 else "pos"
    return "pos" if v > 0 else "neg"

def _badge(v):
    if v > 2:   return f'<span class="badge badge-green">{v:+.1f}%</span>'
    if v > -2:  return f'<span class="badge badge-amber">{v:+.1f}%</span>'
    return f'<span class="badge badge-red">{v:+.1f}%</span>'

def _bar_row(label, val, max_val, color, suffix="%"):
    pct = abs(val) / max(abs(max_val), 0.01) * 100
    sign = "+" if val >= 0 else ""
    return f"""
    <div class="bar-row">
      <div class="bar-label">{label}</div>
      <div class="bar-track"><div class="bar-fill" style="width:{pct:.0f}%;background:{color}"></div></div>
      <div class="bar-val" style="color:{color}">{sign}{val:.1f}{suffix}</div>
    </div>"""

table_rows_html = ""
max_cagr_abs = max((abs(r["cagr"]) for r in valid), default=1)

for r in results_detail:
    if r is None:
        continue
    hl = ' class="highlight"' if r["beat_spy"] else ""
    table_rows_html += f"""
    <tr{hl}>
      <td>{r["label"]}</td>
      <td class="{_cls(r["total_ret"])}">{r["total_ret"]:+.1f}%</td>
      <td class="{_cls(r["cagr"])}">{r["cagr"]:+.1f}%</td>
      <td class="neutral">{r["bh_ret"]:+.1f}%</td>
      <td class="neutral">{r["bh_cagr"]:+.1f}%</td>
      <td>{_badge(r["alpha"])}</td>
      <td class="{_cls(r["max_dd"], flip=True)}">{r["max_dd"]:.1f}%</td>
      <td class="{_cls(r["bh_max_dd"], flip=True)}">{r["bh_max_dd"]:.1f}%</td>
      <td>${r["final_val"]:,.0f}</td>
      <td>{r["sharpe"]:.2f}</td>
      <td>{r["win_rate"]:.1f}%</td>
      <td class="{_cls(r["avg_win"])}">{r["avg_win"]:+.1f}%</td>
      <td class="{_cls(r["avg_loss"])}">{r["avg_loss"]:+.1f}%</td>
      <td class="neutral">{r["n_trades"]:,}</td>
    </tr>"""

cagr_bars = ""
spy_bars = ""
max_abs = max(max(abs(r["cagr"]) for r in valid), max(abs(r["bh_cagr"]) for r in valid), 0.01) if valid else 1

for r in valid:
    yr_lbl = f"{r['start_year']}–{r['start_year']+10}"
    col_s = "#56d364" if r["cagr"] >= 0 else "#f85149"
    col_b = "#58a6ff"
    cagr_bars += _bar_row(yr_lbl, r["cagr"], max_abs, col_s)
    spy_bars  += _bar_row(yr_lbl, r["bh_cagr"], max_abs, col_b)

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Daniel's Breakout — S&amp;P 500 Sliding Window Backtest (Streamlit Recommended)</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #0d1117; color: #e6edf3; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; padding: 32px 24px; max-width: 1280px; margin: 0 auto; }}
  h1 {{ font-size: 22px; font-weight: 700; margin-bottom: 6px; color: #f0f6fc; }}
  h2 {{ font-size: 15px; font-weight: 600; margin: 32px 0 12px; color: #58a6ff; text-transform: uppercase; letter-spacing: 0.06em; }}
  .subtitle {{ font-size: 13px; color: #8b949e; margin-bottom: 28px; }}
  .config-bar {{ display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 28px; }}
  .chip {{ background: #161b22; border: 1px solid #30363d; border-radius: 20px; padding: 4px 12px; font-size: 12px; color: #79c0ff; font-weight: 600; }}
  .chip span {{ color: #8b949e; font-weight: 400; }}

  .cards {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 32px; }}
  .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 14px 18px; flex: 1 1 140px; }}
  .card-label {{ font-size: 11px; color: #8b949e; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 6px; }}
  .card-value {{ font-size: 20px; font-weight: 700; }}
  .green {{ color: #56d364; }}
  .red   {{ color: #f85149; }}
  .blue  {{ color: #58a6ff; }}
  .amber {{ color: #e3b341; }}
  .muted {{ color: #8b949e; }}

  .table-wrap {{ overflow-x: auto; border-radius: 10px; border: 1px solid #30363d; margin-bottom: 32px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  thead th {{ background: #161b22; padding: 10px 14px; text-align: right; font-size: 11px; color: #8b949e; text-transform: uppercase; letter-spacing: 0.06em; white-space: nowrap; border-bottom: 1px solid #30363d; }}
  thead th:first-child {{ text-align: left; }}
  tbody tr {{ border-bottom: 1px solid #21262d; }}
  tbody tr:last-child {{ border-bottom: none; }}
  tbody tr:hover {{ background: #1c2128; }}
  td {{ padding: 10px 14px; text-align: right; white-space: nowrap; }}
  td:first-child {{ text-align: left; font-weight: 600; color: #f0f6fc; }}
  .pos {{ color: #56d364; font-weight: 700; }}
  .neg {{ color: #f85149; font-weight: 700; }}
  .neutral {{ color: #8b949e; }}
  .highlight {{ background: #0d2b0d !important; }}
  .highlight td:first-child {{ color: #56d364; }}
  .badge {{ display: inline-block; padding: 2px 7px; border-radius: 4px; font-size: 11px; font-weight: 700; }}
  .badge-green  {{ background: #56d36422; color: #56d364; border: 1px solid #56d36455; }}
  .badge-red    {{ background: #f8514922; color: #f85149; border: 1px solid #f8514955; }}
  .badge-amber  {{ background: #e3b34122; color: #e3b341; border: 1px solid #e3b34155; }}

  .bar-section {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 32px; }}
  @media (max-width: 700px) {{ .bar-section {{ grid-template-columns: 1fr; }} }}
  .bar-chart {{ background: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 18px; }}
  .bar-chart-title {{ font-size: 12px; color: #8b949e; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 14px; }}
  .bar-row {{ display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }}
  .bar-label {{ font-size: 11px; color: #8b949e; width: 80px; flex-shrink: 0; text-align: right; }}
  .bar-track {{ flex: 1; background: #21262d; border-radius: 3px; height: 14px; overflow: hidden; }}
  .bar-fill {{ height: 100%; border-radius: 3px; transition: width 0.4s; }}
  .bar-val {{ font-size: 11px; font-weight: 700; width: 52px; flex-shrink: 0; }}

  .observations {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 32px; }}
  @media (max-width: 700px) {{ .observations {{ grid-template-columns: 1fr; }} }}
  .obs-card {{ background: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 16px 18px; }}
  .obs-card h3 {{ font-size: 13px; font-weight: 700; margin-bottom: 8px; }}
  .obs-card p, .obs-card li {{ font-size: 12px; color: #8b949e; line-height: 1.6; }}
  .obs-card ul {{ padding-left: 16px; }}
  .obs-card li {{ margin-bottom: 4px; }}
  .obs-green {{ border-color: #2ea04366; }}
  .obs-green h3 {{ color: #56d364; }}
  .obs-blue  {{ border-color: #388bfd66; }}
  .obs-blue  h3 {{ color: #58a6ff; }}
  .obs-amber {{ border-color: #e3b34166; }}
  .obs-amber h3 {{ color: #e3b341; }}
  .obs-red   {{ border-color: #f8514966; }}
  .obs-red   h3 {{ color: #f85149; }}

  .footer {{ font-size: 11px; color: #484f58; border-top: 1px solid #21262d; padding-top: 16px; margin-top: 32px; }}
</style>
</head>
<body>

<h1>Daniel's Breakout Strategy — S&amp;P 500 Sliding 10-Year Window Backtest</h1>
<p class="subtitle">Streamlit recommended settings with point-in-time S&amp;P 500 composition (no survivorship bias). Each window runs for exactly 10 years, starting March 1 of the given year. Walk-forward, no look-ahead bias. Initial capital $100,000. Highlighted rows = strategy beat SPY.</p>

<div class="config-bar">
  <div class="chip"><span>Universe </span>S&amp;P 500 (~500 stocks)</div>
  <div class="chip"><span>Exit </span>PCT Trailing Stop {TRAIL_PCT:.0f}%</div>
  <div class="chip"><span>Max Positions </span>{MAX_POSITIONS}</div>
  <div class="chip"><span>Rank By </span>{RANK_BY.replace("RS_", "Rel Strength ").replace("126", "126d vs SPY")}</div>
  <div class="chip"><span>Rebalance </span>{REBALANCE.title()}</div>
  <div class="chip"><span>C4 Lookback </span>{HIGH_LOOKBACK}d (3 months)</div>
  <div class="chip"><span>Min Criteria </span>{MIN_CRITERIA}/6</div>
  <div class="chip"><span>Windows </span>2006–2016 through 2016–2026</div>
</div>

<h2>At a Glance</h2>
<div class="cards">
  <div class="card">
    <div class="card-label">Avg CAGR (Strategy)</div>
    <div class="card-value {'green' if avg_cagr >= 0 else 'red'}">{avg_cagr:+.1f}%</div>
  </div>
  <div class="card">
    <div class="card-label">Avg CAGR (SPY)</div>
    <div class="card-value blue">{avg_spy_cagr:+.1f}%</div>
  </div>
  <div class="card">
    <div class="card-label">Strategy Beat SPY</div>
    <div class="card-value amber">{beats_spy} / {len(valid)}</div>
  </div>
  <div class="card">
    <div class="card-label">Avg Max Drawdown</div>
    <div class="card-value red">{avg_max_dd:.1f}%</div>
  </div>
  <div class="card">
    <div class="card-label">Avg SPY Max DD</div>
    <div class="card-value red">{avg_spy_dd:.1f}%</div>
  </div>
  <div class="card">
    <div class="card-label">Avg Win Rate</div>
    <div class="card-value muted">{avg_win_rate:.1f}%</div>
  </div>
  <div class="card">
    <div class="card-label">Avg Sharpe Ratio</div>
    <div class="card-value muted">{avg_sharpe:.2f}</div>
  </div>
  <div class="card">
    <div class="card-label">Best Window CAGR</div>
    <div class="card-value green">{best_cagr:+.1f}%</div>
  </div>
</div>

<h2>Window-by-Window Results</h2>
<div class="table-wrap">
<table>
  <thead>
    <tr>
      <th style="text-align:left">Window (10 years)</th>
      <th>Total Return</th>
      <th>CAGR</th>
      <th>SPY Return</th>
      <th>SPY CAGR</th>
      <th>Alpha</th>
      <th>Max DD</th>
      <th>SPY Max DD</th>
      <th>Final $</th>
      <th>Sharpe</th>
      <th>Win Rate</th>
      <th>Avg Win</th>
      <th>Avg Loss</th>
      <th>Trades</th>
    </tr>
  </thead>
  <tbody>
    {table_rows_html}
  </tbody>
</table>
</div>

<h2>CAGR by Window</h2>
<div class="bar-section">
  <div class="bar-chart">
    <div class="bar-chart-title">Strategy CAGR per window</div>
    {cagr_bars}
  </div>
  <div class="bar-chart">
    <div class="bar-chart-title">SPY CAGR per window</div>
    {spy_bars}
  </div>
</div>

<h2>Observations</h2>
<div class="observations">
  <div class="obs-card obs-green">
    <h3>Best Window</h3>
    <p>{best_label}<br>CAGR: <strong style="color:#56d364">{best_cagr:+.1f}%</strong></p>
  </div>
  <div class="obs-card obs-red">
    <h3>Worst Window</h3>
    <p>{worst_label}<br>CAGR: <strong style="color:#f85149">{worst_cagr:+.1f}%</strong></p>
  </div>
  <div class="obs-card obs-blue">
    <h3>Configuration</h3>
    <ul>
      <li>Streamlit recommended settings for S&amp;P 500</li>
      <li>Monthly rebalance keeps portfolio fresh</li>
      <li>RS_126 ranks by 6-month relative strength vs SPY</li>
      <li>6 equal-weight positions, 25% trailing stop</li>
    </ul>
  </div>
  <div class="obs-card obs-amber">
    <h3>Methodology Notes</h3>
    <ul>
      <li>Point-in-time composition — no survivorship bias</li>
      <li>Walk-forward: each window only uses data up to its end date</li>
      <li>Entries at next open after signal; exits at close</li>
      <li>C4: 3-month high lookback (63 trading days)</li>
    </ul>
  </div>
</div>

<div class="footer">
  Generated by Daniel's Breakout Portfolio Backtester &nbsp;·&nbsp;
  Universe: S&amp;P 500 &nbsp;·&nbsp;
  Config: PCT_TRAIL {TRAIL_PCT:.0f}% / {MAX_POSITIONS} positions / {RANK_BY} / {REBALANCE} / C4={HIGH_LOOKBACK}d / min_criteria={MIN_CRITERIA}
</div>

</body>
</html>"""

out_path = os.path.join(os.path.dirname(__file__), "sliding_window_streamlit_recommended_pit.html")
with open(out_path, "w") as f:
    f.write(html)

print(f"\nHTML report written to: {out_path}")
