"""
Stock Screener — Streamlit App
Covers: Daniel's Breakout, Turtle Trading, Minervini SEPA
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# Add backend package to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from app.data.market_data import (
    compute_ohlcv_extras,
    fetch_bulk_ohlcv,
    fetch_bulk_ohlcv_tiingo,
    fetch_ohlcv,
    fetch_ticker_info,
)
from app.data.universes import fetch_tickers
from app.data.sp500_history import get_sp500_at_date, get_sp500_pit_data
from app.data.nasdaq100_history import get_nasdaq100_at_date, get_nasdaq100_pit_data
from app.strategies.daniels_backtest import run_daniels_backtest
from app.strategies.daniels_breakout import screen_daniels_breakout
from app.strategies.daniels_portfolio_backtest import run_daniels_portfolio_backtest
from app.strategies.minervini import (
    calc_12m_return,
    compute_rs_ratings,
    screen_minervini,
)
from app.strategies.minervini_backtest import run_minervini_backtest
from app.strategies.turtle import screen_turtle
from app.strategies.turtle_backtest import run_turtle_backtest

# ─────────────────────────────────────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Stock Screener",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# Formatting helpers
# ─────────────────────────────────────────────────────────────────────────────
def fmt_pct(v, decimals=1):
    if v is None:
        return "—"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.{decimals}f}%"

def fmt_dollar(v):
    if v is None:
        return "—"
    return f"${v:,.0f}"

def fmt_vol(v):
    if not v:
        return "—"
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f}M"
    if v >= 1_000:
        return f"{v / 1_000:.0f}K"
    return str(int(v))

def style_trade_log(df):
    """Apply green/red text to the P&L % column."""
    def _color(val):
        if val > 0:
            return "color: #56d364; font-weight: 600"
        if val < 0:
            return "color: #f85149; font-weight: 600"
        return ""
    return df.style.map(_color, subset=["P&L %"])

def fmt_mktcap(v):
    if not v:
        return "—"
    if v >= 1e12:
        return f"${v/1e12:.1f}T"
    if v >= 1e9:
        return f"${v/1e9:.1f}B"
    if v >= 1e6:
        return f"${v/1e6:.0f}M"
    return f"${v:,.0f}"

# ─────────────────────────────────────────────────────────────────────────────
# Chart helpers
# ─────────────────────────────────────────────────────────────────────────────
def equity_chart_html(equity_curve, bh_curve=None, bm_label="Benchmark", height=380):
    """TradingView Lightweight Charts equity curve — returns embeddable HTML."""
    strat_data = [{"time": p["date"][:10], "value": round(float(p["value"]), 2)}
                  for p in equity_curve]
    bh_data    = [{"time": p["date"][:10], "value": round(float(p["value"]), 2)}
                  for p in bh_curve] if bh_curve else []

    # Default tooltip values (last point)
    last_strat = strat_data[-1]["value"] if strat_data else 0
    last_bh    = bh_data[-1]["value"]    if bh_data    else None
    last_date  = strat_data[-1]["time"]  if strat_data else ""

    def fmt(v):
        if v >= 1_000_000: return f"${v/1_000_000:.2f}M"
        if v >= 1_000:     return f"${v/1_000:.1f}K"
        return f"${v:,.0f}"

    d_strat = fmt(last_strat)
    d_bh    = fmt(last_bh) if last_bh is not None else "—"

    bm_js   = json.dumps(bm_label)
    has_bh  = "true" if bh_data else "false"

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
html, body {{ background:#0d1117; overflow:hidden; font-family:'Courier New',monospace; }}
#info {{ background:#161b22; border-bottom:1px solid #30363d;
         padding:6px 14px; height:40px; display:flex; align-items:center;
         gap:20px; font-size:12px; color:#e6edf3; white-space:nowrap; }}
.lbl {{ color:#8b949e; margin-right:3px; }}
#chart {{ width:100%; height:{height - 40}px; }}
</style></head><body>
<div id="info">
  <span id="idate" style="color:#8b949e">{last_date}</span>
  <span><span class="lbl">Strategy</span><span id="istrat" style="color:#56d364;font-weight:700">{d_strat}</span></span>
  <span id="bh-span"><span class="lbl" id="bm-lbl">{bm_label}</span><span id="ibh" style="color:#58a6ff;font-weight:700">{d_bh}</span></span>
</div>
<div id="chart"></div>
<script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
<script>
const stratData = {json.dumps(strat_data)};
const bhData    = {json.dumps(bh_data)};
const bmLabel   = {bm_js};
const hasBh     = {has_bh};

function fmtVal(v) {{
  if (v >= 1e6) return '$' + (v/1e6).toFixed(2) + 'M';
  if (v >= 1e3) return '$' + (v/1e3).toFixed(1) + 'K';
  return '$' + v.toFixed(0).replace(/\\B(?=(\\d{{3}})+(?!\\d))/g, ',');
}}

const chart = LightweightCharts.createChart(document.getElementById('chart'), {{
  width:  document.getElementById('chart').clientWidth,
  height: {height - 40},
  layout: {{ background: {{type:'solid', color:'#0d1117'}}, textColor:'#e6edf3', fontSize:12 }},
  grid:   {{ vertLines:{{color:'#21262d'}}, horzLines:{{color:'#21262d'}} }},
  crosshair: {{
    mode: LightweightCharts.CrosshairMode.Normal,
    vertLine: {{ color:'#58a6ff', width:1, style:LightweightCharts.LineStyle.Dashed, labelBackgroundColor:'#21262d' }},
    horzLine: {{ color:'#58a6ff', width:1, style:LightweightCharts.LineStyle.Dashed, labelBackgroundColor:'#21262d' }},
  }},
  rightPriceScale: {{ borderColor:'#30363d' }},
  timeScale: {{ borderColor:'#30363d', timeVisible:true, secondsVisible:false }},
  localization: {{ priceFormatter: v => fmtVal(v) }},
}});

const stratSeries = chart.addAreaSeries({{
  lineColor:    '#56d364',
  topColor:     'rgba(86,211,100,0.15)',
  bottomColor:  'rgba(86,211,100,0.0)',
  lineWidth:    2,
  priceLineVisible:   false,
  lastValueVisible:   false,
  crosshairMarkerVisible: true,
}});
stratSeries.setData(stratData);

let bhSeries;
if (hasBh && bhData.length) {{
  bhSeries = chart.addLineSeries({{
    color:    '#58a6ff',
    lineWidth: 1,
    lineStyle: LightweightCharts.LineStyle.Dashed,
    priceLineVisible:   false,
    lastValueVisible:   false,
    crosshairMarkerVisible: true,
  }});
  bhSeries.setData(bhData);
}}

if (!hasBh) document.getElementById('bh-span').style.display = 'none';

chart.subscribeCrosshairMove(param => {{
  const sv = param.seriesData && param.seriesData.get(stratSeries);
  if (!sv || !param.time) return;
  document.getElementById('idate').textContent  = param.time;
  document.getElementById('istrat').textContent = fmtVal(sv.value);
  if (bhSeries) {{
    const bv = param.seriesData.get(bhSeries);
    document.getElementById('ibh').textContent = bv ? fmtVal(bv.value) : '—';
  }}
}});

chart.timeScale().fitContent();
new ResizeObserver(() => {{
  chart.applyOptions({{ width: document.getElementById('chart').clientWidth }});
}}).observe(document.getElementById('chart'));
</script></body></html>"""


def candlestick_chart_html(df, ticker, ema21=None, ema50=None, ema100=None, ema200=None, height=550):
    """TradingView Lightweight Charts — returns embeddable HTML string."""
    candle_data, vol_data, prev_close_map = [], [], {}
    prev_c = None
    for idx, row in df.iterrows():
        t = str(idx)[:10]
        o, h, l, c = float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"])
        v = int(row["Volume"])
        candle_data.append({"time": t, "open": round(o, 4), "high": round(h, 4),
                             "low": round(l, 4), "close": round(c, 4)})
        color = "rgba(86,211,100,0.4)" if c >= o else "rgba(248,81,73,0.4)"
        vol_data.append({"time": t, "value": v, "color": color})
        if prev_c is not None:
            prev_close_map[t] = prev_c
        prev_c = c

    def to_tv(series):
        if series is None:
            return []
        return [{"time": str(idx)[:10], "value": round(float(v), 4)}
                for idx, v in series.items() if v == v]  # skip NaN

    ema21_data  = to_tv(ema21)
    ema50_data  = to_tv(ema50)
    ema100_data = to_tv(ema100)
    ema200_data = to_tv(ema200)

    # Default info bar (last bar)
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last
    d_chg = float(last["Close"]) - float(prev["Close"])
    d_pct = (d_chg / float(prev["Close"]) * 100) if float(prev["Close"]) else 0
    d_clr = "#56d364" if d_chg >= 0 else "#f85149"
    d_sign = "+" if d_chg >= 0 else ""
    lv = int(last["Volume"])
    d_vol = f"{lv/1e6:.1f}M" if lv >= 1e6 else (f"{lv/1e3:.0f}K" if lv >= 1e3 else str(lv))
    d_e21  = f"{ema21.iloc[-1]:.2f}"  if ema21  is not None else "—"
    d_e50  = f"{ema50.iloc[-1]:.2f}"  if ema50  is not None else "—"
    d_e100 = f"{ema100.iloc[-1]:.2f}" if ema100 is not None else "—"
    d_e200 = f"{ema200.iloc[-1]:.2f}" if ema200 is not None else "—"
    d_chg_txt = f"{d_sign}{d_chg:.2f} ({d_sign}{d_pct:.2f}%)"

    chart_h = height - 40  # leave 40 px for info bar

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
html, body {{ background:#0d1117; overflow:hidden; font-family:'Courier New',monospace; }}
#info {{ background:#161b22; border-bottom:1px solid #30363d;
         padding:6px 14px; height:40px; display:flex; align-items:center;
         gap:18px; font-size:12px; color:#e6edf3; white-space:nowrap; overflow:hidden; }}
.lbl {{ color:#8b949e; margin-right:3px; }}
#chart {{ width:100%; height:{chart_h}px; }}
</style></head><body>
<div id="info">
  <span style="font-weight:700;font-size:13px;color:#e6edf3;margin-right:4px">{ticker}</span>
  <span><span class="lbl">O</span><span id="io">{last['Open']:.2f}</span></span>
  <span><span class="lbl">H</span><span id="ih" style="color:#56d364">{last['High']:.2f}</span></span>
  <span><span class="lbl">L</span><span id="il" style="color:#f85149">{last['Low']:.2f}</span></span>
  <span><span class="lbl">C</span><span id="ic" style="color:{d_clr};font-weight:700">{last['Close']:.2f}</span></span>
  <span id="ig" style="color:{d_clr};font-weight:700">{d_chg_txt}</span>
  <span><span class="lbl">Vol</span><span id="iv">{d_vol}</span></span>
  <span><span class="lbl">EMA21</span><span id="ie21" style="color:#f8c518;font-weight:700">{d_e21}</span></span>
  <span><span class="lbl">EMA50</span><span id="ie50" style="color:#58a6ff;font-weight:700">{d_e50}</span></span>
  <span><span class="lbl">EMA100</span><span id="ie100" style="color:#bc8cff;font-weight:700">{d_e100}</span></span>
  <span><span class="lbl">EMA200</span><span id="ie200" style="color:#ff7b72;font-weight:700">{d_e200}</span></span>
</div>
<div id="chart"></div>
<script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
<script>
const candleData   = {json.dumps(candle_data)};
const volData      = {json.dumps(vol_data)};
const ema21Data    = {json.dumps(ema21_data)};
const ema50Data    = {json.dumps(ema50_data)};
const ema100Data   = {json.dumps(ema100_data)};
const ema200Data   = {json.dumps(ema200_data)};
const prevCloseMap = {json.dumps(prev_close_map)};

function fmtVol(v) {{
  if (v >= 1e6) return (v/1e6).toFixed(1)+'M';
  if (v >= 1e3) return (v/1e3).toFixed(0)+'K';
  return String(Math.round(v));
}}

const chart = LightweightCharts.createChart(document.getElementById('chart'), {{
  width: document.getElementById('chart').clientWidth,
  height: {chart_h},
  layout: {{ background: {{type:'solid', color:'#0d1117'}}, textColor:'#e6edf3', fontSize:12 }},
  grid: {{ vertLines:{{color:'#21262d'}}, horzLines:{{color:'#21262d'}} }},
  crosshair: {{
    mode: LightweightCharts.CrosshairMode.Normal,
    vertLine: {{ color:'#58a6ff', width:1, style:LightweightCharts.LineStyle.Dashed, labelBackgroundColor:'#21262d' }},
    horzLine: {{ color:'#58a6ff', width:1, style:LightweightCharts.LineStyle.Dashed, labelBackgroundColor:'#21262d' }},
  }},
  rightPriceScale: {{ borderColor:'#30363d', scaleMargins:{{top:0.08, bottom:0.22}} }},
  timeScale: {{ borderColor:'#30363d', timeVisible:true, secondsVisible:false }},
}});

const cSeries = chart.addCandlestickSeries({{
  upColor:'#56d364', downColor:'#f85149',
  borderUpColor:'#56d364', borderDownColor:'#f85149',
  wickUpColor:'#56d364', wickDownColor:'#f85149',
}});
cSeries.setData(candleData);

const vSeries = chart.addHistogramSeries({{ priceFormat:{{type:'volume'}}, priceScaleId:'vol' }});
chart.priceScale('vol').applyOptions({{ scaleMargins:{{top:0.78, bottom:0}}, visible:false }});
vSeries.setData(volData);

let s21, s50, s100, s200;
if (ema21Data.length) {{
  s21 = chart.addLineSeries({{ color:'#f8c518', lineWidth:1, priceLineVisible:false, lastValueVisible:false, crosshairMarkerVisible:false }});
  s21.setData(ema21Data);
}}
if (ema50Data.length) {{
  s50 = chart.addLineSeries({{ color:'#58a6ff', lineWidth:1, priceLineVisible:false, lastValueVisible:false, crosshairMarkerVisible:false }});
  s50.setData(ema50Data);
}}
if (ema100Data.length) {{
  s100 = chart.addLineSeries({{ color:'#bc8cff', lineWidth:1.5, priceLineVisible:false, lastValueVisible:false, crosshairMarkerVisible:false }});
  s100.setData(ema100Data);
}}
if (ema200Data.length) {{
  s200 = chart.addLineSeries({{ color:'#ff7b72', lineWidth:2, priceLineVisible:false, lastValueVisible:false, crosshairMarkerVisible:false }});
  s200.setData(ema200Data);
}}

chart.subscribeCrosshairMove(param => {{
  const bar = param.seriesData && param.seriesData.get(cSeries);
  if (!bar || !param.time) return;
  const pc  = prevCloseMap[param.time];
  const chg = pc !== undefined ? bar.close - pc : 0;
  const pct = pc ? chg / pc * 100 : 0;
  const clr = chg >= 0 ? '#56d364' : '#f85149';
  const sgn = chg >= 0 ? '+' : '';
  const vb  = param.seriesData.get(vSeries);
  const e21  = s21  ? (param.seriesData.get(s21)?.value?.toFixed(2)  ?? '—') : '—';
  const e50  = s50  ? (param.seriesData.get(s50)?.value?.toFixed(2)  ?? '—') : '—';
  const e100 = s100 ? (param.seriesData.get(s100)?.value?.toFixed(2) ?? '—') : '—';
  const e200 = s200 ? (param.seriesData.get(s200)?.value?.toFixed(2) ?? '—') : '—';
  document.getElementById('io').textContent  = bar.open.toFixed(2);
  document.getElementById('ih').textContent  = bar.high.toFixed(2);
  document.getElementById('il').textContent  = bar.low.toFixed(2);
  const ce = document.getElementById('ic'); ce.textContent = bar.close.toFixed(2); ce.style.color = clr;
  const ge = document.getElementById('ig'); ge.textContent = sgn+chg.toFixed(2)+' ('+sgn+pct.toFixed(2)+'%)'; ge.style.color = clr;
  document.getElementById('iv').textContent   = vb ? fmtVol(vb.value) : '—';
  document.getElementById('ie21').textContent  = e21;
  document.getElementById('ie50').textContent  = e50;
  document.getElementById('ie100').textContent = e100;
  document.getElementById('ie200').textContent = e200;
}});

chart.timeScale().fitContent();
new ResizeObserver(() => {{
  const w = document.getElementById('chart').clientWidth;
  chart.applyOptions({{ width: w }});
}}).observe(document.getElementById('chart'));
</script></body></html>"""


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
UNIVERSE_OPTIONS = {
    "S&P 500":      "sp500",
    "NASDAQ 100":   "nasdaq100",
    "Russell 2000": "russell2000",
    "Futures":      "futures",
    "Crypto":       "crypto",
}

UNIVERSE_MAX = {
    "sp500":      503,
    "nasdaq100":  100,
    "russell2000": 2000,
    "russell3000": 3000,
    "futures":    50,
    "crypto":     50,
}

PF_UNIVERSES = ["S&P 500", "NASDAQ 100", "Russell 2000"]

BENCHMARK_MAP = {
    "sp500":      "SPY",
    "nasdaq100":  "QQQ",
    "russell2000":"IWM",
}

RECOMMENDATIONS = {
    "S&P 500":      dict(exit="PCT_TRAIL", trail=23.5, pos=5,  rank="RS_126",  rebal="QUARTERLY", lookback=63,  min_criteria=6),
    "NASDAQ 100":   dict(exit="PCT_TRAIL", trail=15.0, pos=3,  rank="RS_126",  rebal="MONTHLY",   lookback=63,  min_criteria=6),
    "Russell 2000": dict(exit="PCT_TRAIL", trail=25.0, pos=10, rank="REL_VOL", rebal="QUARTERLY", lookback=126, min_criteria=6),
}

PERIOD_OPTIONS  = {1: 365, 2: 730, 3: 1095, 5: 1825, 10: 3650, 20: 7300}
PERIOD_LABELS   = {v: f"{k}yr" for k, v in PERIOD_OPTIONS.items()}

# ─────────────────────────────────────────────────────────────────────────────
# Sidebar navigation
# ─────────────────────────────────────────────────────────────────────────────
st.sidebar.title("📈 Stock Screener")
st.sidebar.markdown("---")
page = st.sidebar.radio(
    "Strategy",
    ["Daniel's Breakout", "Turtle Trading", "Minervini SEPA"],
    label_visibility="collapsed",
)
st.sidebar.markdown("---")
st.sidebar.caption("Data: Yahoo Finance via yfinance · Walk-forward, no look-ahead bias")


# ═════════════════════════════════════════════════════════════════════════════
# DANIEL'S BREAKOUT
# ═════════════════════════════════════════════════════════════════════════════
if page == "Daniel's Breakout":
    st.title("Daniel's Breakout")
    tab_screen, tab_pf = st.tabs([
        "📊  Screener",
        "💼  Portfolio Backtest",
    ])

    # ── Screener ─────────────────────────────────────────────────────────────
    with tab_screen:
        with st.expander("📋 Screening Criteria", expanded=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown("""
**EMA Momentum Stack**
- **C1** Price > 21-day EMA
- **C2** 21-day EMA ≥ 50-day EMA
- **C3** 50-day EMA ≥ 100-day EMA
""")
            with c2:
                st.markdown("""
**Breakout & Volume**
- **C4** Price at or above new high (adjustable lookback)
- **C5** Today's volume ≥ N× 30-day average (adjustable)
- **C6** 10-day average volume ≥ N shares (adjustable)
""")
            with c3:
                st.markdown("""
**Long-Term Trend**
- **C7** 100-day EMA ≥ 150-day EMA
- **C8** 150-day EMA ≥ 200-day EMA
""")

        col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
        with col1:
            d_uni_lbl = st.selectbox("Universe", list(UNIVERSE_OPTIONS), key="d_uni")
            d_uni = UNIVERSE_OPTIONS[d_uni_lbl]
        with col2:
            d_min = st.selectbox("Min Criteria (of 8)", list(range(1, 9)), index=5, key="d_min")
        with col3:
            d_max_n = UNIVERSE_MAX.get(d_uni, 500)
            d_max_opts = sorted({v for v in (100, 200, 300, 400) if v <= d_max_n} | {d_max_n})
            d_max = st.selectbox("Max Tickers", d_max_opts, index=len(d_max_opts) - 1, key=f"d_max_{d_uni}")
        with col4:
            st.write(""); st.write("")
            d_run = st.button("Run Screen", type="primary", key="d_run", use_container_width=True)

        col5, col6, col7 = st.columns(3)
        with col5:
            d_rel_vol = st.selectbox(
                "C5 — Min Rel Vol",
                [1.0, 1.25, 1.5, 2.0, 3.0],
                index=2,
                format_func=lambda v: f"≥ {v}×",
                key="d_rel_vol",
            )
        with col6:
            d_avg_vol = st.selectbox(
                "C6 — Min Avg Vol (10d)",
                [100_000, 250_000, 500_000, 1_000_000, 2_000_000],
                index=3,
                format_func=lambda v: f"{v/1_000_000:.1f}M" if v >= 1_000_000 else f"{v//1000}K",
                key="d_avg_vol",
            )
        with col7:
            d_lookback = st.selectbox(
                "C4 — High Lookback",
                [63, 125, 189, 252],
                index=1,
                format_func=lambda v: {63: "3 months", 125: "6 months", 189: "9 months", 252: "1 year"}[v],
                key="d_lookback",
            )

        if d_run:
            with st.spinner(f"Screening {d_uni_lbl}…"):
                tickers = fetch_tickers(d_uni)[:d_max]
                data    = fetch_bulk_ohlcv(tickers, period_days=505)  # 365 display + 140 EMA100 warmup
                raw = []
                for t in tickers:
                    df = data.get(t)
                    if df is None or df.empty:
                        continue
                    sig = screen_daniels_breakout(df, t, min_rel_vol=d_rel_vol, min_avg_vol=d_avg_vol, high_lookback=d_lookback)
                    if sig and sig.criteria_met >= d_min:
                        raw.append((sig, df))
                meta = fetch_ticker_info([s.ticker for s, _ in raw])
                rows = []
                for sig, df in raw:
                    ex = compute_ohlcv_extras(df)
                    m  = meta.get(sig.ticker, {})
                    rows.append({
                        "Ticker":    sig.ticker,
                        "Name":      m.get("name", ""),
                        "Close":     round(sig.last_close, 2),
                        "Chg%":      round(ex["price_change_pct"] or 0, 2),
                        "Criteria":  sig.criteria_met,
                        "Passes":    "✓" if sig.passes else "",
                        "Rel Vol":   round(sig.rel_volume, 2),
                        "Avg Vol 10d": fmt_vol(sig.avg_vol_10d),
                        "EMA21":     round(sig.ema21, 2),
                        "EMA50":     round(sig.ema50, 2),
                        "EMA100":    round(sig.ema100, 2),
                        "EMA150":    round(sig.ema150, 2),
                        "EMA200":    round(sig.ema200, 2),
                        "6m High":   round(sig.high_6m, 2),
                        "C1": "✓" if sig.c1 else "✗",
                        "C2": "✓" if sig.c2 else "✗",
                        "C3": "✓" if sig.c3 else "✗",
                        "C4": "✓" if sig.c4 else "✗",
                        "C5": "✓" if sig.c5 else "✗",
                        "C6": "✓" if sig.c6 else "✗",
                        "C7": "✓" if sig.c7 else "✗",
                        "C8": "✓" if sig.c8 else "✗",
                        "Mkt Cap": float(m["market_cap"]) if m.get("market_cap") else 0.0,
                        "Sector":    m.get("sector", ""),
                        "Rating":    m.get("analyst_rating", ""),
                    })
                rows.sort(key=lambda r: (-int(r["Passes"] == "✓"), -r["Criteria"], -r["Rel Vol"], -r["Mkt Cap"]))
                st.session_state["d_rows"] = rows
                st.session_state["d_data"] = data

        if "d_rows" in st.session_state:
            rows = st.session_state["d_rows"]
            passes = sum(1 for r in rows if r["Passes"] == "✓")
            if not rows:
                st.warning(
                    f"No stocks met ≥ {d_min}/8 criteria. "
                    "Try lowering **Min Criteria** — in a broad market downturn "
                    "C4 (new 6-month high) often fails across the board."
                )
            else:
                st.caption(f"**{passes}** full passes · **{len(rows)}** total matches")
                df_display = pd.DataFrame(rows)
                df_display["Mkt Cap"] = df_display["Mkt Cap"].astype(float)
                st.dataframe(df_display, use_container_width=True, hide_index=True, height=400,
                             column_config={"Mkt Cap": st.column_config.NumberColumn("Mkt Cap", format="compact")})

            if rows:
                st.subheader("Candlestick Chart")
                sort_col, ticker_col = st.columns([1, 3])
                with sort_col:
                    d_sort_order = st.selectbox("Sort tickers by", ["Table Order", "Alphabetical"], key="d_sort_order")
                ticker_name_map = {r["Ticker"]: r["Name"] for r in rows}
                tickers_table_order = [r["Ticker"] for r in rows]
                tickers_list = sorted(tickers_table_order) if d_sort_order == "Alphabetical" else tickers_table_order
                with ticker_col:
                    sel = st.selectbox(
                        "Select ticker to chart", tickers_list, key="d_sel",
                        format_func=lambda t: f"{t} — {ticker_name_map[t]}" if ticker_name_map.get(t) else t,
                    )
                if sel:
                    df_c = st.session_state["d_data"].get(sel)
                    if df_c is not None and not df_c.empty:
                        close  = df_c["Close"]
                        # Compute EMAs on full history for accuracy, then trim to 1 year for display
                        ema21  = close.ewm(span=21,  adjust=False).mean()
                        ema50  = close.ewm(span=50,  adjust=False).mean()
                        ema100 = close.ewm(span=100, adjust=False).mean()
                        ema200 = close.ewm(span=200, adjust=False).mean()
                        cutoff = df_c.index[-1] - pd.Timedelta(days=365)
                        df_show     = df_c[df_c.index >= cutoff]
                        ema21_show  = ema21[ema21.index >= cutoff]
                        ema50_show  = ema50[ema50.index >= cutoff]
                        ema100_show = ema100[ema100.index >= cutoff]
                        ema200_show = ema200[ema200.index >= cutoff]
                        components.html(
                            candlestick_chart_html(df_show, sel, ema21_show, ema50_show, ema100_show, ema200_show),
                            height=550,
                            scrolling=False,
                        )

    # ── Portfolio Backtest ────────────────────────────────────────────────────
    with tab_pf:
        with st.expander("📋 Entry Criteria & Exit Conditions", expanded=False):
            e1, e2, e3 = st.columns(3)
            with e1:
                st.markdown("""
**Entry Criteria (all must be true)**
- **C1** Price > 21-day EMA
- **C2** 21-day EMA ≥ 50-day EMA
- **C3** 50-day EMA ≥ 100-day EMA
- **C4** Price at new 6-month high
- **C5** Today's volume ≥ 1.5× 30-day avg
- **C6** 10-day avg volume ≥ 500K shares
- **C7** 100-day EMA ≥ 150-day EMA
- **C8** 150-day EMA ≥ 200-day EMA
""")
            with e2:
                st.markdown("""
**Exit Conditions (configurable)**
- **PCT_TRAIL** — Exit when price drops N% from peak
- **SMA50** — Exit when price closes below 50-day SMA
- **ATR_TRAIL** — Exit when price drops N× ATR(20) from peak
- **BOTH** — Exit on SMA50 cross OR ATR trailing stop
""")
            with e3:
                st.markdown("""
**Position Sizing & Ranking**
- Equal-weight: each position = equity / max positions
- Entry next bar's open after signal
- Ties broken by ranking metric (RS or Rel Vol)
- Rebalance forces exit of non-top-N positions
""")

        def _on_pf_universe_change():
            lbl = st.session_state["pf_uni_lbl"]
            r   = RECOMMENDATIONS[lbl]
            st.session_state["pf_exit"]          = r["exit"]
            st.session_state["pf_trail"]         = float(r["trail"])
            st.session_state["pf_maxpos"]        = r["pos"]
            st.session_state["pf_rank"]          = r["rank"]
            st.session_state["pf_rebal"]         = r["rebal"]
            st.session_state["pf_high_lookback"] = r["lookback"]
            st.session_state["pf_min_crit"]      = r["min_criteria"]

        _top1, _top2 = st.columns(2)
        with _top1:
            pf_uni_lbl = st.selectbox("Universe", PF_UNIVERSES, key="pf_uni_lbl", on_change=_on_pf_universe_change)
        with _top2:
            pf_capital = st.number_input("Initial Capital ($)", 1_000, 10_000_000, 10_000, 1_000, key="pf_capital")
        pf_uni     = UNIVERSE_OPTIONS[pf_uni_lbl]
        bm_ticker  = BENCHMARK_MAP[pf_uni]
        rec        = RECOMMENDATIONS[pf_uni_lbl]

        rec_color = {"S&P 500": "green", "NASDAQ 100": "blue", "Russell 2000": "orange"}[pf_uni_lbl]
        _LOOKBACK_LABEL = {63: "3 months", 126: "6 months", 189: "9 months", 252: "12 months"}
        _rec_lookback_lbl = _LOOKBACK_LABEL.get(rec["lookback"], f"{rec['lookback']}d")
        st.info(
            f"**💡 Recommended for {pf_uni_lbl}:** "
            f"Exit {rec['exit']} · "
            f"Trailing Stop {rec['trail']:.0f}% · "
            f"Max Positions {rec['pos']} · "
            f"Rank by {rec['rank']} · "
            f"Rebalance {rec['rebal'].capitalize()} · "
            f"Min Criteria {rec['min_criteria']}/8 · "
            f"C4 High Lookback {_rec_lookback_lbl}"
        )

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            pf_exit    = st.selectbox("Exit Mode",     ["PCT_TRAIL", "SMA50", "ATR_TRAIL", "BOTH", "REBALANCE"],
                                       index=["PCT_TRAIL","SMA50","ATR_TRAIL","BOTH","REBALANCE"].index(rec["exit"]),
                                       key="pf_exit",
                                       help="REBALANCE: no intra-bar stops — hold until the next rebalance date (or end of backtest)")
            if pf_exit == "PCT_TRAIL":
                pf_trail = st.number_input("Trail %", 1.0, 50.0, float(rec["trail"]), 0.5, key="pf_trail")
            else:
                pf_trail = float(rec["trail"])  # default value, not shown
        with col2:
            pf_maxpos  = st.number_input("Max Positions", 1, 50, rec["pos"], 1, key="pf_maxpos")
            pf_min_crit = st.selectbox("Min Criteria (of 8)", list(range(1, 9)), index=rec["min_criteria"] - 1, key="pf_min_crit")
            _LOOKBACK_OPTIONS = [63, 126, 189, 252]
            pf_high_lookback = st.selectbox(
                "C4 — High Lookback",
                _LOOKBACK_OPTIONS,
                index=_LOOKBACK_OPTIONS.index(rec["lookback"]),
                format_func=lambda v: {63: "3 months", 126: "6 months", 189: "9 months", 252: "12 months"}[v],
                key="pf_high_lookback",
            )
            pf_rank    = st.selectbox("Rank By",
                                       ["REL_VOL", "RS_20", "RS_63", "RS_126", "RS_VOL"],
                                       index=["REL_VOL","RS_20","RS_63","RS_126","RS_VOL"].index(rec["rank"]),
                                       key="pf_rank")
        with col3:
            _REBAL_OPTIONS = ["NONE", "MONTHLY", "QUARTERLY", "SEMI-ANNUAL", "ANNUAL"]
            pf_rebal   = st.selectbox("Rebalance", _REBAL_OPTIONS,
                                       index=_REBAL_OPTIONS.index(rec["rebal"]),
                                       key="pf_rebal")
            _CYCLE_OPTIONS = {
                "QUARTERLY": {
                    "Jan / Apr / Jul / Oct": (1, 4, 7, 10),
                    "Feb / May / Aug / Nov": (2, 5, 8, 11),
                    "Mar / Jun / Sep / Dec": (3, 6, 9, 12),
                },
                "SEMI-ANNUAL": {
                    "Jan / Jul": (1, 7),
                    "Feb / Aug": (2, 8),
                    "Mar / Sep": (3, 9),
                    "Apr / Oct": (4, 10),
                    "May / Nov": (5, 11),
                    "Jun / Dec": (6, 12),
                },
                "ANNUAL": {
                    "January": (1,), "February": (2,), "March": (3,),
                    "April": (4,), "May": (5,), "June": (6,),
                    "July": (7,), "August": (8,), "September": (9,),
                    "October": (10,), "November": (11,), "December": (12,),
                },
            }
            _has_cycle = pf_rebal in _CYCLE_OPTIONS
            _cycle_choices = list(_CYCLE_OPTIONS.get(pf_rebal, {"—": ()}).keys())
            pf_cycle_lbl = st.selectbox(
                "Rebalance Cycle",
                _cycle_choices,
                index=0,
                key="pf_cycle",
                disabled=(not _has_cycle),
            )
            pf_rebal_months = _CYCLE_OPTIONS.get(pf_rebal, {}).get(pf_cycle_lbl, ())
            _TIMING_OPTIONS = {
                "First Trading Day": "FIRST",
                "Mid-Month":         "MID",
                "Last Trading Day":  "LAST",
            }
            pf_timing = st.selectbox(
                "Rebalance Timing",
                list(_TIMING_OPTIONS.keys()),
                index=0,
                key="pf_timing",
                disabled=(pf_rebal == "NONE"),
            )
        with col4:
            pf_start   = st.date_input("Start Date", date(2016, 1, 4), key="pf_start")
            pf_end     = st.date_input("End Date",   date.today(), key="pf_end")

        pf_pit = st.checkbox(
            "Use point-in-time composition (reduces survivorship bias)",
            value=(pf_uni in ("sp500", "nasdaq100")),
            key="pf_pit",
            disabled=(pf_uni not in ("sp500", "nasdaq100")),
            help="Reconstruct the index membership as of the start date using Wikipedia's historical changes. Available for S&P 500 and NASDAQ 100.",
        )
        # Data source selector — hidden until TIINGO_API_KEY is configured
        # pf_data_src = st.selectbox(
        #     "Data Source",
        #     ["Yahoo Finance", "Tiingo"],
        #     index=0,
        #     key="pf_data_src",
        #     help="Tiingo includes delisted/removed stocks — better for point-in-time backtests. Requires TIINGO_API_KEY.",
        # )
        pf_data_src = "Yahoo Finance"

        if st.button("Run Portfolio Backtest", type="primary", key="pf_run", use_container_width=False):
            if pf_start >= pf_end:
                st.error("Start date must be before end date.")
            else:
                with st.spinner(f"Running portfolio backtest on {pf_uni_lbl}… (30–90s for large universes)"):
                    import pandas as _pd
                    today_ts  = _pd.Timestamp.today().normalize()
                    t_start   = _pd.Timestamp(str(pf_start))
                    t_end     = _pd.Timestamp(str(pf_end))
                    fetch_days = int((today_ts - t_start).days) + 220

                    pit_initial_set = None
                    pit_changes_list = None
                    if pf_pit and pf_uni == "sp500":
                        pit_initial, pit_all, pit_changes_list = get_sp500_pit_data(str(pf_start), str(pf_end))
                        pit_initial_set = set(pit_initial)
                        tickers = pit_all
                        st.info(f"Using rolling point-in-time S&P 500 composition: {len(pit_initial)} tickers at start, {len(tickers)} total across range, {len(pit_changes_list)} changes")
                    elif pf_pit and pf_uni == "nasdaq100":
                        pit_initial, pit_all, pit_changes_list = get_nasdaq100_pit_data(str(pf_start), str(pf_end))
                        pit_initial_set = set(pit_initial)
                        tickers = pit_all
                        st.info(f"Using rolling point-in-time NASDAQ 100 composition: {len(pit_initial)} tickers at start, {len(tickers)} total across range, {len(pit_changes_list)} changes")
                    else:
                        tickers = fetch_tickers(pf_uni)
                    all_tkrs   = list(set(tickers + [bm_ticker]))
                    if pf_data_src == "Tiingo":
                        try:
                            raw_dfs = fetch_bulk_ohlcv_tiingo(all_tkrs, period_days=fetch_days)
                        except ValueError as e:
                            st.error(str(e))
                            st.stop()
                    else:
                        raw_dfs = fetch_bulk_ohlcv(all_tkrs, period_days=fetch_days)

                    spy_df     = raw_dfs.pop(bm_ticker, None)
                    if spy_df is not None and not spy_df.empty:
                        spy_df = spy_df[spy_df.index <= t_end]
                    stock_dfs  = {
                        t: df[df.index <= t_end]
                        for t, df in raw_dfs.items()
                        if df is not None and not df.empty
                    }

                    if len(stock_dfs) < 10:
                        st.error("Insufficient stock data fetched — try a shorter date range.")
                    else:
                        res = run_daniels_portfolio_backtest(
                            stock_dfs=stock_dfs,
                            spy_df=spy_df,
                            exit_mode=pf_exit,
                            trail_pct=pf_trail,
                            max_positions=pf_maxpos,
                            min_criteria=pf_min_crit,
                            high_lookback=pf_high_lookback,
                            backtest_start=str(t_start.date()),
                            rank_by=pf_rank,
                            rebalance=pf_rebal if pf_rebal in ("NONE", "MONTHLY") else "QUARTERLY",
                            quarterly_months=pf_rebal_months if pf_rebal_months else (1, 4, 7, 10),
                            rebalance_timing=_TIMING_OPTIONS[pf_timing],
                            initial_capital=pf_capital,
                            pit_initial=pit_initial_set,
                            pit_changes=pit_changes_list,
                        )
                        if res is None:
                            st.error("Not enough data to run portfolio backtest.")
                        else:
                            st.session_state["pf_res"] = res
                            st.session_state["pf_bm"]  = bm_ticker

        if "pf_res" in st.session_state:
            r  = st.session_state["pf_res"]
            bm = st.session_state["pf_bm"]

            # Metrics row 1
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Strategy CAGR",  fmt_pct(r.cagr),
                      delta=f"{r.cagr - r.bh_cagr:+.1f}% vs {bm}")
            m2.metric(f"{bm} CAGR",     fmt_pct(r.bh_cagr))
            m3.metric("Final Value",    fmt_dollar(r.final_value),
                      delta=fmt_dollar(r.dollar_gain))
            m4.metric(f"{bm} Final",    fmt_dollar(r.bh_curve[-1]["value"] if r.bh_curve else 0))
            m5.metric("Sharpe",         f"{r.sharpe_ratio:.2f}")

            # Metrics row 2
            m6, m7, m8, m9, m10 = st.columns(5)
            m6.metric("Max Drawdown",   fmt_pct(r.max_drawdown_pct))
            m7.metric(f"{bm} Max DD",   fmt_pct(r.bh_max_drawdown_pct))
            m8.metric("Win Rate",       fmt_pct(r.win_rate_pct))
            m9.metric("Avg Win",        fmt_pct(r.avg_win_pct))
            m10.metric("Avg Loss",      fmt_pct(r.avg_loss_pct))

            # Date range info
            if r.equity_curve:
                st.caption(
                    f"Period: **{r.equity_curve[0]['date']}** → **{r.equity_curve[-1]['date']}** · "
                    f"{r.n_trades} trades · Ranked by {pf_rank}"
                )

            components.html(
                equity_chart_html(r.equity_curve, r.bh_curve, bm),
                height=380,
                scrolling=False,
            )

            # Annual P&L table
            if r.equity_curve and len(r.equity_curve) > 1:
                import pandas as _pd2
                ec = _pd2.DataFrame(r.equity_curve)
                ec["date"] = _pd2.to_datetime(ec["date"])
                ec = ec.set_index("date").sort_index()
                bh = _pd2.DataFrame(r.bh_curve)
                bh["date"] = _pd2.to_datetime(bh["date"])
                bh = bh.set_index("date").sort_index()
                annual_rows = []
                for year in sorted(ec.index.year.unique()):
                    yr = ec[ec.index.year == year]
                    if yr.empty:
                        continue
                    prev = ec[ec.index.year < year]
                    start = prev["value"].iloc[-1] if not prev.empty else yr["value"].iloc[0]
                    strat_ret = (yr["value"].iloc[-1] / start - 1) * 100
                    bh_yr   = bh[bh.index.year == year]
                    bh_prev = bh[bh.index.year < year]
                    bh_start = bh_prev["value"].iloc[-1] if not bh_prev.empty else (bh_yr["value"].iloc[0] if not bh_yr.empty else None)
                    bh_ret = ((bh_yr["value"].iloc[-1] / bh_start - 1) * 100) if (bh_start is not None and not bh_yr.empty) else None
                    partial = yr.index[0].month > 1 or yr.index[-1].month < 12
                    annual_rows.append({
                        "Year":       str(year) + (" *" if partial else ""),
                        "Strategy %": round(strat_ret, 1),
                        f"{bm} %":    round(bh_ret, 1) if bh_ret is not None else None,
                        "Alpha %":    round(strat_ret - bh_ret, 1) if bh_ret is not None else None,
                    })

                def _color_annual(val):
                    if isinstance(val, (int, float)):
                        if val > 0: return "color: #56d364; font-weight: 600"
                        if val < 0: return "color: #f85149; font-weight: 600"
                    return ""

                ann_df = pd.DataFrame(annual_rows)
                styled_ann = ann_df.style.map(_color_annual, subset=["Strategy %", f"{bm} %", "Alpha %"])
                st.subheader("Annual P&L")
                st.dataframe(styled_ann, use_container_width=True, hide_index=True,
                             height=min(len(annual_rows), 20) * 35 + 38)
                if any("*" in str(row["Year"]) for row in annual_rows):
                    st.caption("\\* Partial year (strategy started or ended mid-year)")

            # Trade log with filters
            if r.trades:
                st.subheader("Trade Log")
                fc1, fc2, fc3, fc4, fc5 = st.columns([2, 2, 2, 2, 1])
                with fc1:
                    pf_f_tkr = st.text_input("Ticker filter", key="pf_f_tkr").upper().strip()
                with fc2:
                    pf_f_reas = st.selectbox(
                        "Exit Reason",
                        ["ALL"] + sorted({t.exit_reason for t in r.trades}),
                        key="pf_f_reas",
                    )
                with fc3:
                    pf_f_res = st.selectbox("Result", ["ALL", "Win", "Loss"], key="pf_f_res")
                with fc4:
                    trade_years = sorted({t.entry_date[:4] for t in r.trades})
                    pf_f_year = st.selectbox("Year", ["ALL"] + trade_years, key="pf_f_year")
                with fc5:
                    st.write(""); st.write("")
                    st.caption(f"{r.n_trades} total")

                trade_rows = []
                for i, t in enumerate(r.trades, 1):
                    if pf_f_tkr and pf_f_tkr not in t.ticker:
                        continue
                    if pf_f_reas != "ALL" and t.exit_reason != pf_f_reas:
                        continue
                    if pf_f_res == "Win"  and t.pnl_pct <= 0:
                        continue
                    if pf_f_res == "Loss" and t.pnl_pct >= 0:
                        continue
                    if pf_f_year != "ALL" and not t.entry_date.startswith(pf_f_year):
                        continue
                    trade_rows.append({
                        "#":           i,
                        "Ticker":      t.ticker,
                        "Entry Date":  t.entry_date,
                        "Exit Date":   t.exit_date,
                        "Entry Price": t.entry_price,
                        "Exit Price":  t.exit_price,
                        "P&L %":       round(t.pnl_pct, 2),
                        "Days Held":   t.days_held,
                        "Exit Reason": t.exit_reason,
                        "C1":  "✓" if t.c1 else "✗",
                        "C2":  "✓" if t.c2 else "✗",
                        "C3":  "✓" if t.c3 else "✗",
                        "C4":  "✓" if t.c4 else "✗",
                        "C5":  "✓" if t.c5 else "✗",
                        "C6":  "✓" if t.c6 else "✗",
                        "C7":  "✓" if t.c7 else "✗",
                        "C8":  "✓" if t.c8 else "✗",
                        "Met": sum([t.c1, t.c2, t.c3, t.c4, t.c5, t.c6, t.c7, t.c8]),
                    })
                if trade_rows:
                    st.dataframe(style_trade_log(pd.DataFrame(trade_rows)), use_container_width=True,
                                 hide_index=True, height=min(len(trade_rows), 20) * 35 + 38)
                else:
                    st.caption("No trades match the current filters.")


# ═════════════════════════════════════════════════════════════════════════════
# TURTLE TRADING
# ═════════════════════════════════════════════════════════════════════════════
elif page == "Turtle Trading":
    st.title("Turtle Trading")
    tab_screen, = st.tabs(["📊  Screener"])

    with tab_screen:
        with st.expander("📋 Screening Criteria", expanded=True):
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("""
**Entry Signals**
- **S1** Price breaks above the 20-day Donchian high *(short-term)*
- **S2** Price breaks above the 55-day Donchian high *(long-term)*
""")
            with c2:
                st.markdown("""
**Exit Rules**
- **S1** Exit when price drops below the 10-day Donchian low
- **S2** Exit when price drops below the 20-day Donchian low
- Both systems use ATR(20) as a hard stop reference
""")

        col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
        with col1:
            t_uni_lbl = st.selectbox("Universe", list(UNIVERSE_OPTIONS), key="t_uni")
            t_uni = UNIVERSE_OPTIONS[t_uni_lbl]
        with col2:
            t_sig = st.selectbox("Signal", ["S2_BUY", "S1_BUY", "ALL"], key="t_sig")
        with col3:
            t_max_n = UNIVERSE_MAX.get(t_uni, 500)
            t_max_opts = sorted({v for v in (100, 200, 300, 400) if v <= t_max_n} | {t_max_n})
            t_max = st.selectbox("Max Tickers", t_max_opts, index=len(t_max_opts) - 1, key=f"t_max_{t_uni}")
        with col4:
            st.write(""); st.write("")
            t_run = st.button("Run Screen", type="primary", key="t_run", use_container_width=True)

        if t_run:
            with st.spinner(f"Screening {t_uni_lbl}…"):
                tickers = fetch_tickers(t_uni)[:t_max]
                data    = fetch_bulk_ohlcv(tickers, period_days=505)  # 365 display + 140 EMA100 warmup
                returns = {
                    tk: r for tk in tickers
                    if (df := data.get(tk)) is not None and not df.empty
                    and (r := calc_12m_return(df)) is not None
                }
                rs_ratings = compute_rs_ratings(returns)
                raw = []
                for tk in tickers:
                    df = data.get(tk)
                    if df is None or df.empty:
                        continue
                    sig = screen_turtle(df, tk)
                    if sig and (t_sig == "ALL" or sig.signal == t_sig):
                        raw.append((sig, df))
                meta = fetch_ticker_info([s.ticker for s, _ in raw if s.signal != "NONE"])
                rows = []
                for sig, df in raw:
                    ex = compute_ohlcv_extras(df)
                    m  = meta.get(sig.ticker, {})
                    rows.append({
                        "Ticker":  sig.ticker,
                        "Name":    m.get("name", ""),
                        "Signal":  sig.signal,
                        "Close":   round(sig.last_close, 2),
                        "ATR20":   round(sig.atr_20, 2),
                        "High20":  round(sig.high_20, 2),
                        "High55":  round(sig.high_55, 2),
                        "Low10":   round(sig.low_10, 2),
                        "RS Rating": round(rs_ratings.get(sig.ticker, 0), 1),
                        "Chg%":    round(ex["price_change_pct"] or 0, 2),
                        "Rel Vol": round(ex["rel_vol"] or 0, 2),
                        "Sector":  m.get("sector", ""),
                    })
                order = {"S2_BUY": 0, "S1_BUY": 1, "NONE": 2}
                rows.sort(key=lambda r: (order.get(r["Signal"], 3), -r["ATR20"]))
                st.session_state["t_rows"] = rows
                st.session_state["t_data"] = data

        if "t_rows" in st.session_state:
            rows    = st.session_state["t_rows"]
            signals = sum(1 for r in rows if r["Signal"] != "NONE")
            st.caption(f"**{signals}** signals · **{len(rows)}** total")
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=500)

            if rows:
                st.subheader("Candlestick Chart")
                tickers_list = sorted(r["Ticker"] for r in rows)
                sel = st.selectbox("Select ticker to chart", tickers_list, key="t_sel")
                if sel:
                    df_c = st.session_state["t_data"].get(sel)
                    if df_c is not None and not df_c.empty:
                        close  = df_c["Close"]
                        ema21  = close.ewm(span=21,  adjust=False).mean()
                        ema50  = close.ewm(span=50,  adjust=False).mean()
                        ema100 = close.ewm(span=100, adjust=False).mean()
                        cutoff = df_c.index[-1] - pd.Timedelta(days=365)
                        df_show     = df_c[df_c.index >= cutoff]
                        ema21_show  = ema21[ema21.index >= cutoff]
                        ema50_show  = ema50[ema50.index >= cutoff]
                        ema100_show = ema100[ema100.index >= cutoff]
                        components.html(
                            candlestick_chart_html(df_show, sel, ema21_show, ema50_show, ema100_show),
                            height=550,
                            scrolling=False,
                        )


# ═════════════════════════════════════════════════════════════════════════════
# MINERVINI SEPA
# ═════════════════════════════════════════════════════════════════════════════
elif page == "Minervini SEPA":
    st.title("Minervini SEPA")
    tab_screen, = st.tabs(["📊  Screener"])

    with tab_screen:
        with st.expander("📋 Screening Criteria", expanded=True):
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("""
**Trend Template (C1–C5)**
- **C1** Price > 150-day MA and Price > 200-day MA
- **C2** 150-day MA > 200-day MA
- **C3** 200-day MA trending up (above level 1 month ago)
- **C4** 50-day MA > 150-day MA and 50-day MA > 200-day MA
- **C5** Price > 50-day MA
""")
            with c2:
                st.markdown("""
**Price Structure & Strength (C6–C9)**
- **C6** Price within 25% of 52-week high (≥ 75% of high)
- **C7** Price at least 30% above 52-week low
- **C8** RS Rating > 85 (top 15% of universe by 12-month return)
- **C9** Relative Volume ≥ 1.5× (today vs 30-day average)
- **Pre-filter** 10-day avg volume ≥ 1,000,000 shares
""")

        col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
        with col1:
            mv_uni_lbl = st.selectbox("Universe", list(UNIVERSE_OPTIONS), key="mv_uni")
            mv_uni = UNIVERSE_OPTIONS[mv_uni_lbl]
        with col2:
            mv_min = st.selectbox("Min Criteria", [10, 9, 8, 7, 6, 5], key="mv_min")
        with col3:
            mv_max_n = UNIVERSE_MAX.get(mv_uni, 500)
            mv_max_opts = sorted({v for v in (100, 200, 300, 400) if v <= mv_max_n} | {mv_max_n})
            mv_max = st.selectbox("Max Tickers", mv_max_opts, index=len(mv_max_opts) - 1, key=f"mv_max_{mv_uni}")
        with col4:
            st.write(""); st.write("")
            mv_run = st.button("Run Screen", type="primary", key="mv_run", use_container_width=True)

        if mv_run:
            with st.spinner(f"Screening {mv_uni_lbl}…"):
                tickers = fetch_tickers(mv_uni)[:mv_max]
                data    = fetch_bulk_ohlcv(tickers, period_days=505)  # 365 display + 140 EMA100 warmup
                returns = {
                    tk: r for tk in tickers
                    if (df := data.get(tk)) is not None and not df.empty
                    and (r := calc_12m_return(df)) is not None
                }
                rs_ratings = compute_rs_ratings(returns)
                raw = []
                for tk in tickers:
                    df = data.get(tk)
                    if df is None or df.empty:
                        continue
                    rs  = rs_ratings.get(tk, 0.0)
                    if rs <= 85.0:
                        continue
                    vol = df["Volume"].values
                    n_v = len(vol)
                    tv  = float(vol[-1])
                    avg10 = float(vol[max(0, n_v-11):n_v-1].mean()) if n_v >= 2 else tv
                    if avg10 < 1_000_000:
                        continue
                    avg30 = float(vol[max(0, n_v-31):n_v-1].mean()) if n_v >= 2 else tv
                    rv = tv / avg30 if avg30 > 0 else 0.0
                    if rv < 1.5:
                        continue
                    sig = screen_minervini(df, tk, rs, rel_vol=rv, avg_vol_10d=avg10)
                    if sig and sig.criteria_met >= mv_min:
                        raw.append((sig, df))
                meta = fetch_ticker_info([s.ticker for s, _ in raw])
                rows = []
                for sig, df in raw:
                    ex = compute_ohlcv_extras(df)
                    m  = meta.get(sig.ticker, {})
                    rows.append({
                        "Ticker":       sig.ticker,
                        "Name":         m.get("name", ""),
                        "Close":        round(sig.last_close, 2),
                        "Criteria":     sig.criteria_met,
                        "Passes":       "✓" if sig.passes else "",
                        "RS Rating":    round(sig.rs_rating, 1),
                        "MA50":         round(sig.ma50, 2),
                        "MA150":        round(sig.ma150, 2),
                        "MA200":        round(sig.ma200, 2),
                        "52w High":     round(sig.high_52w, 2),
                        "52w Low":      round(sig.low_52w, 2),
                        "% from High":  round(sig.pct_from_high, 1),
                        "% from Low":   round(sig.pct_from_low, 1),
                        "Chg%":         round(ex["price_change_pct"] or 0, 2),
                        "Sector":       m.get("sector", ""),
                        "Rating":       m.get("analyst_rating", ""),
                    })
                rows.sort(key=lambda r: (-int(r["Passes"] == "✓"), -r["Criteria"], -r["RS Rating"]))
                st.session_state["mv_rows"] = rows
                st.session_state["mv_data"] = data

        if "mv_rows" in st.session_state:
            rows   = st.session_state["mv_rows"]
            passes = sum(1 for r in rows if r["Passes"] == "✓")
            st.caption(f"**{passes}** full passes · **{len(rows)}** total")
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=500)

            if rows:
                st.subheader("Candlestick Chart")
                tickers_list = sorted(r["Ticker"] for r in rows)
                sel = st.selectbox("Select ticker to chart", tickers_list, key="mv_sel")
                if sel:
                    df_c = st.session_state["mv_data"].get(sel)
                    if df_c is not None and not df_c.empty:
                        close  = df_c["Close"]
                        ema21  = close.ewm(span=21,  adjust=False).mean()
                        ema50  = close.ewm(span=50,  adjust=False).mean()
                        ema100 = close.ewm(span=100, adjust=False).mean()
                        cutoff = df_c.index[-1] - pd.Timedelta(days=365)
                        df_show     = df_c[df_c.index >= cutoff]
                        ema21_show  = ema21[ema21.index >= cutoff]
                        ema50_show  = ema50[ema50.index >= cutoff]
                        ema100_show = ema100[ema100.index >= cutoff]
                        components.html(
                            candlestick_chart_html(df_show, sel, ema21_show, ema50_show, ema100_show),
                            height=550,
                            scrolling=False,
                        )


