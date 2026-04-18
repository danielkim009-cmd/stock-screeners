# Stock Screener

A multi-strategy stock screening and backtesting app. Available in two flavours — a **Streamlit** single-file app (simpler, no Node required) and a **React + FastAPI** app (polished UI with TradingView charts). Both use the same Python strategy backend.

**Live app:** [daniel-stock-screeners.streamlit.app](https://daniel-stock-screeners.streamlit.app/)


## Strategies

| Strategy | Description |
|---|---|
| **Daniel's Breakout** | EMA momentum stack (21/50/100) + volume-confirmed 6-month high breakout. Includes single-ticker and portfolio backtesting. |
| **Turtle Trading** | Classic Donchian channel breakout system (20-day S1, 55-day S2) with ATR(20) trailing stop. |
| **Minervini SEPA** | Stan Minervini's 8-criteria Specific Entry Point Analysis trend template with RS rating vs universe. |

## Portfolio Backtester (Daniel's Breakout)

The most fully-featured component. Runs a walk-forward simulation on the S&P 500, NASDAQ 100, or Russell 2000 with:

- **Exit modes:** SMA50 cross, 2×ATR(20) trailing stop, percentage trailing stop
- **Ranking:** Relative Volume, Relative Strength vs benchmark (RS_20 / RS_63 / RS_126 / RS_VOL)
- **Rebalancing:** None / Monthly / Quarterly
- **Custom date range:** Specify exact start and end dates (up to 20 years)
- **Benchmark comparison:** SPY/QQQ/IWM buy-and-hold equity curve, CAGR, max drawdown
- **Metrics:** CAGR, Sharpe ratio, max drawdown (% and $), win rate, avg win/loss %, trade log with filters
- **Animated equity curve** rendered with TradingView Lightweight Charts

### Recommended Settings (from 11-window sliding backtest, 2006–2026)

| Universe | Trailing Stop | Max Positions | Ranking | Rebalance | Avg CAGR (10yr) |
|---|---|---|---|---|---|
| S&P 500 | 25% | 9 | RS_20 | Quarterly | +16.6% vs SPY +11.8% |
| NASDAQ 100 | 24% | 2 | Rel Vol | Quarterly | +26.6% vs QQQ +17.3% |
| Russell 2000 | 30% | 10 | — | Quarterly | — |

> Sliding window backtest reports are in [`backend/sliding_window_results_quarterly.html`](https://danielkim009-cmd.github.io/stock-screeners/backend/sliding_window_results_quarterly.html) and [`backend/sliding_window_results_nasdaq100.html`](https://danielkim009-cmd.github.io/stock-screeners/backend/sliding_window_results_nasdaq100.html).

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
| Charts | Plotly (interactive, zoom/pan) |
| Candlestick | ✓ with EMA overlays |
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
| Candlestick | ✓ with EMA overlays |
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
MAX_POSITIONS  = 9
REBALANCE      = "QUARTERLY"
RANK_BY        = "RS_20"       # REL_VOL | RS_20 | RS_63 | RS_126 | RS_VOL
```

## Notes

- **Survivorship bias:** The backtester uses the current index composition, which excludes delisted stocks. Past performance will be overstated to some degree.
- **Data source:** All price data is fetched from Yahoo Finance via yfinance. Data quality depends on Yahoo's availability.
- **Cache:** Universe ticker lists are cached to disk for 24 hours to avoid repeated network calls.
