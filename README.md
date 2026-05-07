# Stock Screener

A multi-strategy stock screening and backtesting app. Available in two flavours — a **Streamlit** single-file app (simpler, no Node required) and a **React + FastAPI** app (polished UI with TradingView charts). Both use the same Python strategy backend.

**Live app:** [daniel-stock-screeners.streamlit.app](https://daniel-stock-screeners.streamlit.app/)

**Video Overview:** [Breakout Strategy & Backtesting Results](https://www.youtube.com/watch?v=ChSFzaS-zFo) *(generated with Google NotebookLM)*


## Strategies

| Strategy | Description |
|---|---|
| **Daniel's Breakout** | EMA momentum stack (21/50/100) + volume-confirmed breakout to a new high. EMA150 and EMA200 are displayed on charts as informational overlays. Includes single-ticker and portfolio backtesting. |
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

> EMA150 and EMA200 are computed and shown on charts for visual reference but are not part of the pass/fail criteria.

## Portfolio Backtester (Daniel's Breakout)

The most fully-featured component. Runs a walk-forward simulation on the S&P 500, NASDAQ 100, or Russell 2000 with:

- **Exit modes:** SMA50 cross, 2×ATR(20) trailing stop, percentage trailing stop
- **Ranking:** Relative Volume, Relative Strength vs benchmark (RS_20 / RS_63 / RS_126 / RS_VOL)
- **Rebalancing:** None / Monthly / Quarterly
- **C4 High Lookback:** Configurable new-high window — 3 months (63 bars), 6 months, 9 months, or 12 months
- **Custom date range:** Specify exact start and end dates (up to 20 years)
- **Point-in-time composition:** For S&P 500 and NASDAQ 100, reconstructs historical index membership using Wikipedia's recorded additions/removals. This reduces survivorship bias by only trading stocks that were actually in the index on each date. Enabled by default for S&P 500 and NASDAQ 100.
- **Benchmark comparison:** SPY/QQQ/IWM buy-and-hold equity curve, CAGR, max drawdown
- **Metrics:** CAGR, Sharpe ratio, max drawdown (% and $), win rate, avg win/loss %, trade log with filters
- **Animated equity curve** rendered with TradingView Lightweight Charts

### Recommended Settings

| Universe | Trailing Stop | Max Positions | Ranking | Rebalance | C4 Lookback |
|---|---|---|---|---|---|
| S&P 500 | 25% | 6 | RS_126 | Monthly | 3 months |
| NASDAQ 100 | 24% | 3 | RS_126 | Monthly | 3 months |
| Russell 2000 | 25% | 10 | Rel Vol | Quarterly | 6 months |

> 10-year sliding window backtest of Nasdaq 100 with maximum of 2 stocks at a time: [`backend/sliding_window_results_nasdaq100.html`](https://danielkim009-cmd.github.io/stock-screeners/backend/sliding_window_results_nasdaq100.html).
>
> 10-year sliding window testing of S&P 500 with maximum of 3 stocks at a time: [`backend/sliding_window_results_3pos.html`](https://danielkim009-cmd.github.io/stock-screeners/backend/sliding_window_results_3pos.html).

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
| Candlestick | ✓ with EMA21/50/100/200 overlays |
| Equity curve | ✓ strategy vs benchmark |
| Trade log filters | ✓ |
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
| Candlestick | ✓ with EMA21/50/100/200 overlays |
| Equity curve | ✓ strategy vs benchmark |
| Trade log filters | ✓ |
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
│   │       ├── daniels_breakout.py          # Screener signal logic
│   │       ├── daniels_backtest.py          # Single-ticker backtester
│   │       ├── daniels_portfolio_backtest.py# Walk-forward portfolio backtester
│   │       ├── turtle.py                    # Turtle 20/55-day Donchian + ATR
│   │       ├── turtle_backtest.py
│   │       ├── minervini.py                 # SEPA 8-criteria trend template
│   │       ├── minervini_backtest.py
│   ├── sliding_window_test.py               # 10-year sliding window batch runner
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

The `backend/sliding_window_test.py` script runs 11 overlapping 10-year windows (2006→2016 through 2016→2026) to stress-test a strategy across different market regimes without look-ahead bias.

```bash
cd backend
source .venv/bin/activate
python sliding_window_test.py
```

Configure the test at the top of the file:

```python
EXIT_MODE      = "PCT_TRAIL"
TRAIL_PCT      = 25.0
MAX_POSITIONS  = 6
REBALANCE      = "MONTHLY"
RANK_BY        = "RS_126"      # REL_VOL | RS_20 | RS_63 | RS_126 | RS_VOL
HIGH_LOOKBACK  = 63            # trading bars: 63=3m, 126=6m, 189=9m, 252=12m
```

## Notes

- **Survivorship bias:** By default the backtester uses the current index composition, which excludes delisted stocks. For S&P 500 and NASDAQ 100, enabling "Use point-in-time composition" (on by default) reconstructs historical membership to reduce this bias.
- **Data source:** All price data is fetched from Yahoo Finance via yfinance. Data quality depends on Yahoo's availability.
- **Cache:** Universe ticker lists are cached to disk for 24 hours to avoid repeated network calls.

## ⚠️ Disclaimer

This project is for educational and research purposes only. Nothing in this app constitutes financial advice or a recommendation to buy or sell any security. Backtested results are based on historical data with known limitations — including survivorship bias from current index composition and data quality constraints from Yahoo Finance. The sliding window CAGR figures are in-sample results across historical periods and do not guarantee future returns. The market regime indicator is a simple technical filter and is not a predictive model. Always do your own research before making any investment decisions.
