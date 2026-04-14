"""
Stock Screener — Streamlit App
Covers: Daniel's Breakout, Turtle Trading, Minervini SEPA
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

# Add backend package to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from app.data.market_data import (
    compute_ohlcv_extras,
    fetch_bulk_ohlcv,
    fetch_ohlcv,
    fetch_ticker_info,
)
from app.data.universes import fetch_tickers
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
def equity_chart(equity_curve, bh_curve=None, bm_label="Benchmark"):
    dates  = [p["date"]  for p in equity_curve]
    values = [p["value"] for p in equity_curve]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=values, name="Strategy",
        line=dict(color="#56d364", width=2),
        hovertemplate="%{x}<br>$%{y:,.0f}<extra>Strategy</extra>",
    ))
    if bh_curve:
        bh_dates  = [p["date"]  for p in bh_curve]
        bh_values = [p["value"] for p in bh_curve]
        fig.add_trace(go.Scatter(
            x=bh_dates, y=bh_values, name=bm_label,
            line=dict(color="#58a6ff", width=1.5, dash="dot"),
            hovertemplate="%{x}<br>$%{y:,.0f}<extra>" + bm_label + "</extra>",
        ))
    fig.update_layout(
        template="plotly_dark",
        margin=dict(l=0, r=0, t=30, b=0),
        height=380,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        yaxis=dict(tickprefix="$", tickformat=",.0f"),
        hovermode="x unified",
    )
    return fig


def candlestick_chart(df, ticker, ema21=None, ema50=None, ema100=None):
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.75, 0.25],
    )
    fig.add_trace(go.Candlestick(
        x=df.index.astype(str),
        open=df["Open"], high=df["High"],
        low=df["Low"], close=df["Close"],
        name=ticker,
        increasing_line_color="#56d364",
        decreasing_line_color="#f85149",
        showlegend=False,
    ), row=1, col=1)
    if ema21 is not None:
        fig.add_trace(go.Scatter(x=df.index.astype(str), y=ema21,
            name="EMA21", line=dict(color="#f8c518", width=1)), row=1, col=1)
    if ema50 is not None:
        fig.add_trace(go.Scatter(x=df.index.astype(str), y=ema50,
            name="EMA50", line=dict(color="#58a6ff", width=1)), row=1, col=1)
    if ema100 is not None:
        fig.add_trace(go.Scatter(x=df.index.astype(str), y=ema100,
            name="EMA100", line=dict(color="#e3b341", width=1)), row=1, col=1)
    vol_colors = [
        "#56d364" if c >= o else "#f85149"
        for c, o in zip(df["Close"], df["Open"])
    ]
    fig.add_trace(go.Bar(
        x=df.index.astype(str), y=df["Volume"],
        name="Volume", marker_color=vol_colors, showlegend=False,
    ), row=2, col=1)
    fig.update_layout(
        template="plotly_dark",
        margin=dict(l=0, r=0, t=30, b=0),
        height=520,
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


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

PF_UNIVERSES = ["S&P 500", "NASDAQ 100", "Russell 2000"]

BENCHMARK_MAP = {
    "sp500":      "SPY",
    "nasdaq100":  "QQQ",
    "russell2000":"IWM",
}

RECOMMENDATIONS = {
    "S&P 500":      dict(trail=25.0, pos=9,  rank="RS_20",   rebal="QUARTERLY"),
    "NASDAQ 100":   dict(trail=24.0, pos=2,  rank="REL_VOL", rebal="QUARTERLY"),
    "Russell 2000": dict(trail=30.0, pos=10, rank="REL_VOL", rebal="QUARTERLY"),
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
    tab_screen, tab_bt, tab_pf = st.tabs([
        "📊  Screener",
        "📈  Single-Ticker Backtest",
        "💼  Portfolio Backtest",
    ])

    # ── Screener ─────────────────────────────────────────────────────────────
    with tab_screen:
        col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
        with col1:
            d_uni_lbl = st.selectbox("Universe", list(UNIVERSE_OPTIONS), key="d_uni")
            d_uni = UNIVERSE_OPTIONS[d_uni_lbl]
        with col2:
            d_min = st.selectbox("Min Criteria", [6, 5, 4, 3, 2, 1], key="d_min")
        with col3:
            d_max = st.number_input("Max Tickers", 50, 3000, 500, 50, key="d_max")
        with col4:
            st.write(""); st.write("")
            d_run = st.button("Run Screen", type="primary", key="d_run", use_container_width=True)

        if d_run:
            with st.spinner(f"Screening {d_uni_lbl}…"):
                tickers = fetch_tickers(d_uni)[:d_max]
                data    = fetch_bulk_ohlcv(tickers, period_days=200)
                raw = []
                for t in tickers:
                    df = data.get(t)
                    if df is None or df.empty:
                        continue
                    sig = screen_daniels_breakout(df, t)
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
                        "6m High":   round(sig.high_6m, 2),
                        "C1": "✓" if sig.c1 else "✗",
                        "C2": "✓" if sig.c2 else "✗",
                        "C3": "✓" if sig.c3 else "✗",
                        "C4": "✓" if sig.c4 else "✗",
                        "C5": "✓" if sig.c5 else "✗",
                        "C6": "✓" if sig.c6 else "✗",
                        "Mkt Cap":   fmt_mktcap(m.get("market_cap")),
                        "Sector":    m.get("sector", ""),
                        "Rating":    m.get("analyst_rating", ""),
                    })
                rows.sort(key=lambda r: (-int(r["Passes"] == "✓"), -r["Criteria"], -r["Rel Vol"]))
                st.session_state["d_rows"] = rows
                st.session_state["d_data"] = data

        if "d_rows" in st.session_state:
            rows = st.session_state["d_rows"]
            passes = sum(1 for r in rows if r["Passes"] == "✓")
            st.caption(f"**{passes}** full passes · **{len(rows)}** total matches")
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=400)

            st.subheader("Candlestick Chart")
            tickers_list = [r["Ticker"] for r in rows]
            sel = st.selectbox("Select ticker to chart", tickers_list, key="d_sel")
            if sel:
                df_c = st.session_state["d_data"].get(sel)
                if df_c is not None and not df_c.empty:
                    close = df_c["Close"]
                    st.plotly_chart(
                        candlestick_chart(
                            df_c, sel,
                            ema21=close.ewm(span=21,  adjust=False).mean(),
                            ema50=close.ewm(span=50,  adjust=False).mean(),
                            ema100=close.ewm(span=100, adjust=False).mean(),
                        ),
                        use_container_width=True,
                    )

    # ── Single-Ticker Backtest ────────────────────────────────────────────────
    with tab_bt:
        col1, col2, col3, col4, col5 = st.columns([1.5, 1, 1.5, 1, 1])
        with col1:
            d_bt_tkr = st.text_input("Ticker", "AAPL", key="d_bt_tkr").upper().strip()
        with col2:
            d_bt_per = st.selectbox("Period", list(PERIOD_LABELS.values()),
                                     index=1, key="d_bt_per")
            d_bt_days = next(d for d, l in PERIOD_LABELS.items() if l == d_bt_per)
        with col3:
            d_bt_exit = st.selectbox("Exit Mode", ["PCT_TRAIL", "SMA50", "ATR_TRAIL", "BOTH"], key="d_bt_exit")
        with col4:
            d_bt_trl = st.number_input("Trail %", 1.0, 50.0, 10.0, 0.5, key="d_bt_trl")
        with col5:
            st.write(""); st.write("")
            d_bt_run = st.button("Run Backtest", type="primary", key="d_bt_run", use_container_width=True)

        if d_bt_run:
            with st.spinner(f"Backtesting {d_bt_tkr}…"):
                df = fetch_ohlcv(d_bt_tkr, period_days=d_bt_days)
                if df is None or df.empty or len(df) < 200:
                    st.error(f"Insufficient data for {d_bt_tkr}")
                else:
                    res = run_daniels_backtest(df, d_bt_tkr, exit_mode=d_bt_exit, trail_pct=d_bt_trl)
                    if res is None:
                        st.error("Not enough trading bars to run backtest")
                    else:
                        st.session_state["d_bt_res"] = res

        if "d_bt_res" in st.session_state:
            r = st.session_state["d_bt_res"]
            m1, m2, m3, m4, m5, m6 = st.columns(6)
            m1.metric("Total Return",   fmt_pct(r.total_return_pct))
            m2.metric("Buy & Hold",     fmt_pct(r.bh_return_pct))
            m3.metric("Max Drawdown",   fmt_pct(r.max_drawdown_pct))
            m4.metric("Win Rate",       fmt_pct(r.win_rate_pct))
            m5.metric("Sharpe",         f"{r.sharpe_ratio:.2f}")
            m6.metric("# Trades",       str(r.n_trades))

            m2a, m2b, m2c = st.columns(3)
            m2a.metric("Avg Win",   fmt_pct(getattr(r, "avg_win_pct",  None)))
            m2b.metric("Avg Loss",  fmt_pct(getattr(r, "avg_loss_pct", None)))
            m2c.metric("BH Max DD", fmt_pct(getattr(r, "bh_max_drawdown_pct", None)))

            st.plotly_chart(equity_chart(r.equity_curve), use_container_width=True)

            if r.trades:
                # Filters
                fc1, fc2 = st.columns(2)
                with fc1:
                    f_reason = st.selectbox(
                        "Exit Reason",
                        ["ALL"] + sorted({t.exit_reason for t in r.trades}),
                        key="d_bt_f_reason",
                    )
                with fc2:
                    f_result = st.selectbox("Result", ["ALL", "Win", "Loss"], key="d_bt_f_result")

                trade_rows = []
                for t in r.trades:
                    if f_reason != "ALL" and t.exit_reason != f_reason:
                        continue
                    if f_result == "Win"  and t.pnl_pct <= 0:
                        continue
                    if f_result == "Loss" and t.pnl_pct >= 0:
                        continue
                    trade_rows.append({
                        "Entry Date":  t.entry_date,
                        "Exit Date":   t.exit_date,
                        "Entry Price": t.entry_price,
                        "Exit Price":  t.exit_price,
                        "P&L %":       round(t.pnl_pct, 2),
                        "Days Held":   t.days_held,
                        "Exit Reason": t.exit_reason,
                    })
                st.subheader(f"Trade Log ({len(trade_rows)} shown)")
                st.dataframe(pd.DataFrame(trade_rows), use_container_width=True,
                             hide_index=True, height=350)

    # ── Portfolio Backtest ────────────────────────────────────────────────────
    with tab_pf:
        pf_uni_lbl = st.selectbox("Universe", PF_UNIVERSES, key="pf_uni_lbl")
        pf_uni     = UNIVERSE_OPTIONS[pf_uni_lbl]
        bm_ticker  = BENCHMARK_MAP[pf_uni]
        rec        = RECOMMENDATIONS[pf_uni_lbl]

        rec_color = {"S&P 500": "green", "NASDAQ 100": "blue", "Russell 2000": "orange"}[pf_uni_lbl]
        st.info(
            f"**💡 Recommended for {pf_uni_lbl}:** "
            f"Trailing Stop {rec['trail']:.0f}% · "
            f"Max Positions {rec['pos']} · "
            f"Rank by {rec['rank']} · "
            f"Rebalance {rec['rebal'].capitalize()}"
        )

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            pf_exit    = st.selectbox("Exit Mode",     ["PCT_TRAIL", "SMA50", "ATR_TRAIL", "BOTH"], key="pf_exit")
            pf_trail   = st.number_input("Trail %",    1.0, 50.0, float(rec["trail"]), 0.5, key="pf_trail")
        with col2:
            pf_maxpos  = st.number_input("Max Positions", 1, 50, rec["pos"], 1, key="pf_maxpos")
            pf_rank    = st.selectbox("Rank By",
                                       ["REL_VOL", "RS_20", "RS_63", "RS_126", "RS_VOL"],
                                       index=["REL_VOL","RS_20","RS_63","RS_126","RS_VOL"].index(rec["rank"]),
                                       key="pf_rank")
        with col3:
            pf_rebal   = st.selectbox("Rebalance",    ["NONE", "MONTHLY", "QUARTERLY"],
                                       index=["NONE","MONTHLY","QUARTERLY"].index(rec["rebal"]),
                                       key="pf_rebal")
            pf_capital = st.number_input("Initial Capital ($)", 1_000, 10_000_000, 100_000, 1_000, key="pf_capital")
        with col4:
            pf_start   = st.date_input("Start Date", date.today() - timedelta(days=730), key="pf_start")
            pf_end     = st.date_input("End Date",   date.today(), key="pf_end")

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

                    tickers    = fetch_tickers(pf_uni)
                    all_tkrs   = list(set(tickers + [bm_ticker]))
                    raw_dfs    = fetch_bulk_ohlcv(all_tkrs, period_days=fetch_days)

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
                            backtest_start=str(t_start.date()),
                            rank_by=pf_rank,
                            rebalance=pf_rebal,
                            initial_capital=pf_capital,
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

            st.plotly_chart(equity_chart(r.equity_curve, r.bh_curve, bm),
                            use_container_width=True)

            # Trade log with filters
            if r.trades:
                st.subheader("Trade Log")
                fc1, fc2, fc3, fc4 = st.columns([2, 2, 2, 1])
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
                    st.write(""); st.write("")
                    st.caption(f"{r.n_trades} total")

                trade_rows = []
                for t in r.trades:
                    if pf_f_tkr and pf_f_tkr not in t.ticker:
                        continue
                    if pf_f_reas != "ALL" and t.exit_reason != pf_f_reas:
                        continue
                    if pf_f_res == "Win"  and t.pnl_pct <= 0:
                        continue
                    if pf_f_res == "Loss" and t.pnl_pct >= 0:
                        continue
                    trade_rows.append({
                        "Ticker":      t.ticker,
                        "Entry Date":  t.entry_date,
                        "Exit Date":   t.exit_date,
                        "Entry Price": t.entry_price,
                        "Exit Price":  t.exit_price,
                        "P&L %":       round(t.pnl_pct, 2),
                        "Days Held":   t.days_held,
                        "Exit Reason": t.exit_reason,
                    })
                st.dataframe(pd.DataFrame(trade_rows), use_container_width=True,
                             hide_index=True, height=400)


# ═════════════════════════════════════════════════════════════════════════════
# TURTLE TRADING
# ═════════════════════════════════════════════════════════════════════════════
elif page == "Turtle Trading":
    st.title("Turtle Trading")
    tab_screen, tab_bt = st.tabs(["📊  Screener", "📈  Backtest"])

    with tab_screen:
        col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
        with col1:
            t_uni_lbl = st.selectbox("Universe", list(UNIVERSE_OPTIONS), key="t_uni")
            t_uni = UNIVERSE_OPTIONS[t_uni_lbl]
        with col2:
            t_sig = st.selectbox("Signal", ["ALL", "S1_BUY", "S2_BUY"], key="t_sig")
        with col3:
            t_max = st.number_input("Max Tickers", 50, 3000, 500, 50, key="t_max")
        with col4:
            st.write(""); st.write("")
            t_run = st.button("Run Screen", type="primary", key="t_run", use_container_width=True)

        if t_run:
            with st.spinner(f"Screening {t_uni_lbl}…"):
                tickers = fetch_tickers(t_uni)[:t_max]
                data    = fetch_bulk_ohlcv(tickers, period_days=400)
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

        if "t_rows" in st.session_state:
            rows    = st.session_state["t_rows"]
            signals = sum(1 for r in rows if r["Signal"] != "NONE")
            st.caption(f"**{signals}** signals · **{len(rows)}** total")
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=500)

    with tab_bt:
        col1, col2, col3, col4 = st.columns([1.5, 1, 1, 1])
        with col1:
            t_bt_tkr = st.text_input("Ticker", "AAPL", key="t_bt_tkr").upper().strip()
        with col2:
            t_bt_per = st.selectbox("Period", list(PERIOD_LABELS.values()), index=1, key="t_bt_per")
            t_bt_days = next(d for d, l in PERIOD_LABELS.items() if l == t_bt_per)
        with col3:
            t_bt_sys = st.selectbox("System", ["S2", "S1", "BOTH"], key="t_bt_sys")
        with col4:
            st.write(""); st.write("")
            t_bt_run = st.button("Run Backtest", type="primary", key="t_bt_run", use_container_width=True)

        if t_bt_run:
            with st.spinner(f"Backtesting {t_bt_tkr}…"):
                df = fetch_ohlcv(t_bt_tkr, period_days=t_bt_days)
                if df is None or df.empty or len(df) < 120:
                    st.error(f"Insufficient data for {t_bt_tkr}")
                else:
                    res = run_turtle_backtest(df, t_bt_tkr, system=t_bt_sys)
                    if res is None:
                        st.error("Not enough trading bars")
                    else:
                        st.session_state["t_bt_res"] = res

        if "t_bt_res" in st.session_state:
            r = st.session_state["t_bt_res"]
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Total Return",  fmt_pct(r.total_return_pct))
            m2.metric("Buy & Hold",    fmt_pct(r.bh_return_pct))
            m3.metric("Max Drawdown",  fmt_pct(r.max_drawdown_pct))
            m4.metric("Win Rate",      fmt_pct(r.win_rate_pct))
            m5.metric("Sharpe",        f"{r.sharpe_ratio:.2f}")
            st.plotly_chart(equity_chart(r.equity_curve), use_container_width=True)
            if r.trades:
                trade_rows = [{
                    "Entry Date":  t.entry_date,
                    "Exit Date":   t.exit_date,
                    "Entry Price": t.entry_price,
                    "Exit Price":  t.exit_price,
                    "P&L %":       round(t.pnl_pct, 2),
                    "Days Held":   t.days_held,
                    "System":      getattr(t, "system", ""),
                    "Exit Reason": t.exit_reason,
                } for t in r.trades]
                st.dataframe(pd.DataFrame(trade_rows), use_container_width=True,
                             hide_index=True, height=350)


# ═════════════════════════════════════════════════════════════════════════════
# MINERVINI SEPA
# ═════════════════════════════════════════════════════════════════════════════
elif page == "Minervini SEPA":
    st.title("Minervini SEPA")
    tab_screen, tab_bt = st.tabs(["📊  Screener", "📈  Backtest"])

    with tab_screen:
        col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
        with col1:
            mv_uni_lbl = st.selectbox("Universe", list(UNIVERSE_OPTIONS), key="mv_uni")
            mv_uni = UNIVERSE_OPTIONS[mv_uni_lbl]
        with col2:
            mv_min = st.selectbox("Min Criteria", [10, 9, 8, 7, 6, 5], key="mv_min")
        with col3:
            mv_max = st.number_input("Max Tickers", 50, 3000, 500, 50, key="mv_max")
        with col4:
            st.write(""); st.write("")
            mv_run = st.button("Run Screen", type="primary", key="mv_run", use_container_width=True)

        if mv_run:
            with st.spinner(f"Screening {mv_uni_lbl}…"):
                tickers = fetch_tickers(mv_uni)[:mv_max]
                data    = fetch_bulk_ohlcv(tickers, period_days=400)
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

        if "mv_rows" in st.session_state:
            rows   = st.session_state["mv_rows"]
            passes = sum(1 for r in rows if r["Passes"] == "✓")
            st.caption(f"**{passes}** full passes · **{len(rows)}** total")
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=500)

    with tab_bt:
        col1, col2, col3, col4, col5 = st.columns([1.5, 1, 1.5, 1, 1])
        with col1:
            mv_bt_tkr = st.text_input("Ticker", "AAPL", key="mv_bt_tkr").upper().strip()
        with col2:
            mv_bt_per = st.selectbox("Period", list(PERIOD_LABELS.values()), index=1, key="mv_bt_per")
            mv_bt_days = next(d for d, l in PERIOD_LABELS.items() if l == mv_bt_per)
        with col3:
            mv_bt_exit = st.selectbox("Exit Mode", ["SMA50", "PCT_TRAIL", "ATR_TRAIL", "BOTH"], key="mv_bt_exit")
        with col4:
            mv_bt_trl = st.number_input("Trail %", 1.0, 50.0, 8.0, 0.5, key="mv_bt_trl")
        with col5:
            st.write(""); st.write("")
            mv_bt_run = st.button("Run Backtest", type="primary", key="mv_bt_run", use_container_width=True)

        if mv_bt_run:
            with st.spinner(f"Backtesting {mv_bt_tkr}…"):
                df = fetch_ohlcv(mv_bt_tkr, period_days=mv_bt_days)
                if df is None or df.empty or len(df) < 300:
                    st.error(f"Insufficient data for {mv_bt_tkr}")
                else:
                    res = run_minervini_backtest(df, mv_bt_tkr, exit_mode=mv_bt_exit, trail_pct=mv_bt_trl)
                    if res is None:
                        st.error("Not enough trading bars")
                    else:
                        st.session_state["mv_bt_res"] = res

        if "mv_bt_res" in st.session_state:
            r = st.session_state["mv_bt_res"]
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Total Return",  fmt_pct(r.total_return_pct))
            m2.metric("Buy & Hold",    fmt_pct(r.bh_return_pct))
            m3.metric("Max Drawdown",  fmt_pct(r.max_drawdown_pct))
            m4.metric("Win Rate",      fmt_pct(r.win_rate_pct))
            m5.metric("Sharpe",        f"{r.sharpe_ratio:.2f}")
            st.plotly_chart(equity_chart(r.equity_curve), use_container_width=True)
            if r.trades:
                trade_rows = [{
                    "Entry Date":  t.entry_date,
                    "Exit Date":   t.exit_date,
                    "Entry Price": t.entry_price,
                    "Exit Price":  t.exit_price,
                    "P&L %":       round(t.pnl_pct, 2),
                    "Days Held":   t.days_held,
                    "Exit Reason": t.exit_reason,
                } for t in r.trades]
                st.dataframe(pd.DataFrame(trade_rows), use_container_width=True,
                             hide_index=True, height=350)

