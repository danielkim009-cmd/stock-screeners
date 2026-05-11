# Stock Screener

A multi-strategy stock screening and backtesting app. Available in two flavours — a **Streamlit** single-file app (simpler, no Node required) and a **React + FastAPI** app (polished UI with TradingView charts). Both use the same Python strategy backend.

**Live app:** [daniel-stock-screeners.streamlit.app](https://daniel-stock-screeners.streamlit.app/)

**Video Overview:** [Breakout Strategy & Backtesting Results](https://www.youtube.com/watch?v=ChSFzaS-zFo) *(generated with Google NotebookLM)*


## Strategies

| Strategy | Description |
|---|---|
| **Daniel's Breakout** | 8-criteria EMA momentum stack (21/50/100/150/200) + volume-confirmed breakout to a new high. Includes single-ticker and portfolio backtesting with configurable exit modes. |
| **Turtle Trading** | Classic Donchian channel breakout system (20-day S1, 55-day S2) with ATR(20) trailing stop. |
| **Minervini SEPA** | Stan Minervini's 8-criteria Specific Entry Point Analysis trend template with RS rating vs universe. |

### Daniel's Breakout — Screening Criteria

| # | Criterion | Description |
|---|---|---|
| C1 | Price > EMA21 | Price above the 21-day EMA |
| C2 | EMA21 ≥ EMA50 | Short-term EMA above mid-term EMA |
| C3 | EMA50 ≥ EMA100 | Mid-term EMA above long-term EMA |
| C4 | New N-month high | Price at or above highest close in prior N months (adjustable: 3/6/9/12) |
| C5 | Rel Vol ≥ 1.5× | Today's volume at least 1.5× the 30-day average |
| C6 | Avg Vol ≥ 1M | 10-day average volume ≥ 1,000,000 shares |
| C7 | EMA100 ≥ EMA150 | Long-term EMA stack confirmation |
| C8 | EMA150 ≥ EMA200 | Full EMA stack alignment |

The screener passes a stock when all 8 criteria are met. The portfolio backtester has a configurable **Min Criteria** threshold (1–8) so you can relax the filter to generate more signals.

## Portfolio Backtester (Daniel's Breakout)

The most fully-featured component. Runs a walk-forward simulation on the S&P 500, NASDAQ 100, or Russell 2000 with:

- **Exit modes:**
  - `SMA50` — exit when price closes below the 50-day simple moving average
  - `ATR_TRAIL` — 2× ATR(20) trailing stop below the highest close since entry
  - `PCT_TRAIL` — percentage trailing stop below the highest close since entry
  - `BOTH` — SMA50 + ATR_TRAIL, whichever triggers first
  - `REBALANCE` — no intra-bar stops; hold until the next rebalance date or end of backtest
- **Trail %** — only active when exit mode is `PCT_TRAIL`; sets the drawdown percentage from peak that triggers an exit
- **Ranking:** Relative Volume, Relative Strength vs benchmark (RS_20 / RS_63 / RS_126 / RS_VOL)
- **Rebalancing:** None / Monthly / Quarterly
- **Min Criteria:** Configurable minimum criteria count (of 8) to trigger a signal
- **C4 High Lookback:** Configurable new-high window — 3 months (63 bars), 6 months, 9 months, or 12 months
- **Custom date range:** Specify exact start and end dates (up to 20 years)
- **Point-in-time composition:** For S&P 500 and NASDAQ 100, reconstructs historical index membership using Wikipedia's recorded additions/removals. Enabled by default for S&P 500 and NASDAQ 100.
- **Benchmark comparison:** SPY/QQQ/IWM buy-and-hold equity curve, CAGR, max drawdown
- **Metrics:** CAGR, Sharpe ratio, max drawdown (% and $), win rate, avg win/loss %, trade log with C1–C8 columns and filters
- **Animated equity curve** rendered with TradingView Lightweight Charts

### Recommended Settings

| Universe | Trailing Stop | Max Positions | Ranking | Rebalance | C4 Lookback |
|---|---|---|---|---|---|
| S&P 500 | 25% | 5 | RS_126 | Quarterly | 3 months |
| NASDAQ 100 | 20% | 3 | RS_126 | Monthly | 3 months |
| Russell 2000 | 25% | 10 | Rel Vol | Quarterly | 6 months |

### Latest Sliding 10-Year Window Results (PIT, recommended settings)

Eleven overlapping 10-year windows starting on the first trading day of each year from 2006 through 2016 (e.g. 2006-01-03 → 2016-01-03, ..., 2016-01-03 → 2026-01-03). Each run uses point-in-time index composition to avoid survivorship bias.

**S&P 500** — PCT_TRAIL 25%, 5 positions, RS_126, Quarterly rebalance, C4=63d:

| | Strategy | SPY |
|---|---|---|
| Avg CAGR | +11.1% | +11.9% |
| Best window CAGR | +23.1% (2016→2026) | — |
| Worst window CAGR | +0.8% (2008→2018) | — |
| Avg Max Drawdown | -47.4% | -37.3% |
| Windows beating SPY | 5 / 11 | — |

> Full report: [`backend/sliding_window_streamlit_recommended_pit.html`](https://danielkim009-cmd.github.io/stock-screeners/backend/sliding_window_streamlit_recommended_pit.html)

**NASDAQ 100** — PCT_TRAIL 20%, 3 positions, RS_126, Monthly rebalance, C4=63d:

| | Strategy | QQQ |
|---|---|---|
| Avg CAGR | +25.5% | +17.1% |
| Best window CAGR | +35.7% (2012→2022) | — |
| Worst window CAGR | +13.3% (2006→2016) | — |
| Avg Max Drawdown | -40.9% | -36.3% |
| Windows beating QQQ | 11 / 11 | — |

> Full report: [`backend/sliding_window_nasdaq100_recommended_pit.html`](https://danielkim009-cmd.github.io/stock-screeners/backend/sliding_window_nasdaq100_recommended_pit.html)

The strategy is far more effective on the NASDAQ 100 than on the S&P 500. On the broader S&P 500 universe, the strategy struggles in windows containing the 2008 GFC (CAGRs of +0.8% to +5.9% from 2006–2010 starts) but significantly outperforms SPY in windows beginning from 2012 onwards. On the more tech-heavy NASDAQ 100, the strategy beats QQQ across every single window, with the best window producing a 35.7% CAGR.

### Earlier sliding window experiments

> Nasdaq 100, max 2 stocks: [`backend/sliding_window_results_nasdaq100.html`](https://danielkim009-cmd.github.io/stock-screeners/backend/sliding_window_results_nasdaq100.html)
>
> S&P 500, max 3 stocks: [`backend/sliding_window_results_3pos.html`](https://danielkim009-cmd.github.io/stock-screeners/backend/sliding_window_results_3pos.html)

> Trading education curriculum map: [`Trading_Education_Curriculum_Map.html`](https://danielkim009-cmd.github.io/stock-screeners/Trading_Education_Curriculum_Map.html).

## Tech Stack

| Layer | Tech |
|---|---|
| Strategy backend | Python 3.11+, FastAPI, uvicorn |
| Data | yfinance 0.2.66, pandas, numpy |
| Streamlit frontend | Streamlit ≥ 1.32, Plotly |
| React frontend | React 18, Vite, TradingView Lightweight Charts |
| Universes | S&P 500 (Wikipedia), NASDAQ 100 (Wikipedia), Russell 2000 (iShares IWM CSV), Futures, Crypto |

## Running the App

There are two independent frontends. Both use the same Python strategy code — pick whichever suits you.

---

### Option 1 — Streamlit (recommended for simplicity)

No Node.js required. Everything runs in a single Python process.

```bash
# 1. Create and activate virtual environment (first time only)
cd backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Run from the project root
cd ..
source backend/.venv/bin/activate
streamlit run streamlit_app.py
```

Open: **http://localhost:8501**

| Feature | Streamlit |
|---|---|
| Charts | TradingView Lightweight Charts |
| Candlestick | ✓ with EMA21/50/100/150/200 overlays |
| Equity curve | ✓ strategy vs benchmark |
| Trade log filters | ✓ with C1–C8 criteria columns |
| Portfolio backtest | ✓ |
| Node.js required | ✗ |

---

### Option 2 — React + FastAPI (polished UI)

Requires Node.js 20+. Runs two separate processes.

```bash
# Terminal 1 — API backend
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000

# Terminal 2 — React frontend
cd frontend
npm install       # first time only
npm run dev
```

Open: **http://localhost:5173**

| Feature | React + FastAPI |
|---|---|
| Charts | TradingView Lightweight Charts |
| Candlestick | ✓ with EMA21/50/100/150/200 overlays |
| Equity curve | ✓ strategy vs benchmark |
| Trade log filters | ✓ with C1–C8 criteria columns |
| Portfolio backtest | ✓ |
| Node.js required | ✓ |

> The Vite dev server proxies all `/api` requests to `localhost:8000` automatically.

API docs: **http://localhost:8000/docs**

---

## Project Structure

```
stock-screeners/
├── streamlit_app.py                     # Streamlit app (Option 1)
├── backend/
│   ├── app/
│   │   ├── main.py                          # FastAPI entry point, CORS
│   │   ├── api/routes.py                    # REST endpoints
│   │   ├── data/
│   │   │   ├── universes.py                 # Ticker list fetchers (SP500/NDX/Russell/Futures/Crypto)
│   │   │   ├── russell2000.py               # iShares IWM CSV fetcher, 24h cache
│   │   │   └── market_data.py               # yfinance OHLCV, single + bulk fetch
│   │   └── strategies/
│   │       ├── daniels_breakout.py          # Screener signal logic (8 criteria)
│   │       ├── daniels_backtest.py          # Single-ticker backtester
│   │       ├── daniels_portfolio_backtest.py# Walk-forward portfolio backtester
│   │       ├── turtle.py                    # Turtle 20/55-day Donchian + ATR
│   │       ├── turtle_backtest.py
│   │       ├── minervini.py                 # SEPA 8-criteria trend template
│   │       ├── minervini_backtest.py
│   ├── sliding_window_test.py               # 10-year sliding window batch runner
│   ├── sliding_window_streamlit_recommended.py  # PIT sliding window runner
│   ├── sliding_window_results_quarterly.html
│   ├── sliding_window_results_nasdaq100.html
│   ├── sliding_window_results_relvol.html
├── Trading_Education_Curriculum_Map.html
│   └── requirements.txt
└── frontend/
    ├── src/
    │   ├── App.jsx                          # Nav shell, strategy tabs
    │   ├── api/screener.js                  # API client
    │   ├── components/
    │   │   ├── CandlestickChart.jsx         # TradingView chart wrapper
    │   │   ├── EquityChart.jsx              # Equity curve chart
    │   │   ├── MetaCells.jsx                # Shared table cell renderers
    │   │   ├── ResultsTable.jsx
    │   │   └── SignalBadge.jsx
    │   ├── pages/
    │   │   ├── DanielsBreakoutScreener.jsx  # Main screener + portfolio backtest UI
    │   │   ├── TurtleScreener.jsx
    │   │   ├── MinerviniScreener.jsx
        │   └── utils/exportCsv.js
    ├── package.json
    └── vite.config.js
```

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/screen/daniels` | Run Daniel's breakout screener |
| `GET` | `/api/backtest/daniels` | Single-ticker backtest |
| `GET` | `/api/portfolio/daniels` | Walk-forward portfolio backtest |
| `GET` | `/api/screen/turtle` | Run Turtle screener |
| `GET` | `/api/chart/{ticker}` | OHLCV candlestick data |
| `GET` | `/api/tickers` | List tickers for a universe |

## Sliding Window Backtests

Two scripts run 11 overlapping 10-year windows (2006→2016 through 2016→2026) to stress-test the strategy across different market regimes without look-ahead bias.

**`backend/sliding_window_test.py`** — original script, current index composition (survivorship bias applies):
```bash
cd backend && source .venv/bin/activate && python sliding_window_test.py
```

**`backend/sliding_window_streamlit_recommended.py`** — recommended settings with point-in-time composition (preferred):
```bash
cd backend && source .venv/bin/activate && python sliding_window_streamlit_recommended.py
```

Configure at the top of either file:

```python
EXIT_MODE      = "PCT_TRAIL"
TRAIL_PCT      = 25.0
MAX_POSITIONS  = 5
REBALANCE      = "QUARTERLY"
RANK_BY        = "RS_126"      # REL_VOL | RS_20 | RS_63 | RS_126 | RS_VOL
HIGH_LOOKBACK  = 63            # trading bars: 63=3m, 126=6m, 189=9m, 252=12m
MIN_CRITERIA   = 6             # minimum criteria (of 8) to trigger a signal
```

## Survivorship Bias

Survivorship bias is a well-known pitfall in backtesting index-based strategies. There are two distinct forms of this bias, and the more damaging one is often overlooked:

### The real problem: trading stocks before they joined the index

The most serious form of survivorship bias when using today's index composition is **forward-looking inclusion bias**. Many stocks in the current S&P 500 or NASDAQ 100 were added to the index *after* they had already experienced massive price appreciation — their breakout and run-up is precisely what qualified them for inclusion. Using today's roster to backtest from 2006 means the strategy can "discover" and trade these stocks years before they were actually part of the index, capturing gains that no real-time index-based screener would have found.

For example, a stock added to the S&P 500 in 2020 after a 500% run from 2015–2020 would appear in a naive backtest starting in 2006. The backtester would trade its breakout signals in 2015–2019 as if it were an S&P 500 stock the whole time — but in reality, it was a mid-cap or small-cap that no S&P 500 screener would have surfaced. This artificially inflates returns because the backtest is cherry-picking future winners and pretending they were available in the past.

### The secondary problem: missing removed stocks

The more commonly discussed form of survivorship bias — ignoring stocks that were removed from the index due to bankruptcy, acquisition, or decline — also inflates returns, but to a lesser degree. Removed stocks that declined would have generated losing trades, and their absence makes the simulation look better than reality. However, this effect is smaller because:

1. Most removed stocks are replaced precisely when they decline below a threshold, so the actual losses from holding them until removal tend to be moderate.
2. A momentum-based screener with trailing stops would have exited many of these declining stocks before their worst losses anyway.

### How we attempt to address both

The `sliding_window_streamlit_recommended.py` script (and the Streamlit app's "Use point-in-time composition" toggle) reconstructs the S&P 500 or NASDAQ 100 membership as it existed on each day of the backtest:

1. Scraping the current constituent list from Wikipedia.
2. Scraping Wikipedia's recorded table of historical additions and removals.
3. Walking backwards through those changes to infer the composition at any past date.
4. For each 10-year window, fetching price data for **all tickers that were ever in the index during that period** — not just current members.
5. Passing both the initial composition and the dated change events to the backtester, which updates the eligible universe on each rebalance date.

This addresses both problems: stocks are only eligible for signals during the period they were actually in the index, and removed stocks are included during the period when they were members.

### Sliding window comparison — with vs without point-in-time composition

The difference in results across the eleven 10-year windows (2006→2016 through 2016→2026) is significant — but more so for the S&P 500 than for the NASDAQ 100.

**S&P 500** (PCT_TRAIL 25%, 5 positions, RS_126, Quarterly):

| | Without PIT (survivorship bias) | With PIT |
|---|---|---|
| Avg CAGR | ~27% | +11.1% |
| Windows beating SPY | 11/11 | 5/11 |
| Worst window CAGR | +12.6% | +0.8% |

> Reports: [non-PIT](https://danielkim009-cmd.github.io/stock-screeners/backend/sliding_window_results_3pos.html) · [PIT](https://danielkim009-cmd.github.io/stock-screeners/backend/sliding_window_streamlit_recommended_pit.html)

**NASDAQ 100** (PCT_TRAIL 20%, 3 positions, RS_126, Monthly for PIT; PCT_TRAIL 24%, 2 positions, Rel Vol, Quarterly for the existing non-PIT report):

| | Without PIT (survivorship bias) | With PIT |
|---|---|---|
| Avg CAGR | +26.6% | +25.5% |
| Windows beating QQQ | 10/11 | 11/11 |
| Worst window CAGR | +9.2% | +13.3% |
| Avg Max Drawdown | -32.5% | -40.9% |

> Reports: [non-PIT](https://danielkim009-cmd.github.io/stock-screeners/backend/sliding_window_results_nasdaq100.html) · [PIT](https://danielkim009-cmd.github.io/stock-screeners/backend/sliding_window_nasdaq100_recommended_pit.html)

> Note: the two NASDAQ 100 runs use slightly different parameter sets, so the comparison isn't perfectly apples-to-apples. Nevertheless the direction is clear: survivorship bias has a much smaller impact on NASDAQ 100 backtests than on S&P 500 backtests. NASDAQ 100 has a smaller universe (~100 vs ~500), lower historical turnover, and the new additions tend to be growth-to-growth substitutions rather than replacements of failing companies. The S&P 500, by contrast, churns out under-performers regularly, so a non-PIT backtest is much more flattered by hindsight.

### Limitations of the PIT approach

Despite best efforts, the PIT reconstruction is not perfect. Several stocks that were in the S&P 500 at some point between 2006 and 2026 are **no longer available from Yahoo Finance** — because they were delisted, acquired, renamed, or simply removed from Yahoo's database. In a typical full-range run (~844 unique tickers), roughly 150–175 fail to download. Examples include: `LEH` (Lehman Brothers), `WFM` (Whole Foods), `CELG` (Celgene), `MON` (Monsanto), `RAI` (Reynolds American), and many others.

This creates a residual form of survivorship bias that cannot be fully eliminated using free data sources:

- **Bankruptcies and delistings** (e.g. Lehman Brothers) often have no historical data at all, so their losses are simply absent from the simulation.
- **Acquired companies** (e.g. Whole Foods, Celgene) sometimes retain partial history but are missing data around the acquisition date.
- **Renamed/restructured tickers** may appear under a different symbol with incomplete history.

The practical effect is that the PIT results are still **slightly optimistic** compared to true real-world performance, but they are far more honest than the survivorship-biased numbers.

## Notes

- **Data source:** All price data is fetched from Yahoo Finance via yfinance. Data quality and historical depth depend on Yahoo's availability.
- **Cache:** Universe ticker lists are cached to disk for 24 hours to avoid repeated network calls.

## Disclaimer

This project is for educational and research purposes only. Nothing in this app constitutes financial advice or a recommendation to buy or sell any security. Backtested results are based on historical data with known limitations — including residual survivorship bias from missing historical data on delisted stocks, and data quality constraints from Yahoo Finance. Even with point-in-time composition enabled, roughly 150–175 historically removed S&P 500 constituents are unavailable from Yahoo Finance, meaning their losses are absent from the simulation. The sliding window CAGR figures are in-sample results across historical periods and do not guarantee future returns. Always do your own research before making any investment decisions.
