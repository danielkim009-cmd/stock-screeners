# Stock Screener

A multi-strategy stock screening and backtesting app built with a FastAPI backend and a React + Vite frontend. Screens S&P 500, NASDAQ 100, Russell 2000, Futures, and Crypto universes using institutional momentum strategies.

![Dark-themed UI with strategy tabs, screener results, and equity curve charts]

## Strategies

| Strategy | Description |
|---|---|
| **Daniel's Breakout** | EMA momentum stack (21/50/100) + volume-confirmed 6-month high breakout. Includes single-ticker and portfolio backtesting. |
| **Turtle Trading** | Classic Donchian channel breakout system (20-day S1, 55-day S2) with ATR(20) trailing stop. |
| **Minervini SEPA** | Stan Minervini's 8-criteria Specific Entry Point Analysis trend template with RS rating vs universe. |
| **O'Neil Patterns** | William O'Neil-style cup-with-handle and base pattern detection. |

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

> Sliding window backtest reports are in [`backend/sliding_window_results_quarterly.html`](backend/sliding_window_results_quarterly.html) and [`backend/sliding_window_results_nasdaq100.html`](backend/sliding_window_results_nasdaq100.html).

## Tech Stack

| Layer | Tech |
|---|---|
| Backend | Python 3.11+, FastAPI, uvicorn |
| Data | yfinance 0.2.66, pandas, numpy |
| Frontend | React 18, Vite, TradingView Lightweight Charts |
| Universes | S&P 500 (Wikipedia), NASDAQ 100 (Wikipedia), Russell 2000 (iShares IWM CSV), Futures, Crypto |

## Project Structure

```
stock-screeners/
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
│   │       └── oneil.py                     # O'Neil cup/base patterns
│   ├── sliding_window_test.py               # 10-year sliding window batch runner
│   ├── sliding_window_results_quarterly.html
│   ├── sliding_window_results_nasdaq100.html
│   ├── sliding_window_results_relvol.html
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
    │   │   └── OneilScreener.jsx
    │   └── utils/exportCsv.js
    ├── package.json
    └── vite.config.js
```

## Setup

### Prerequisites

- Python 3.11+
- Node.js 20+

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

### Frontend

```bash
cd frontend
npm install
npm run dev
```

App: http://localhost:5173

> The Vite dev server proxies all `/api` requests to `localhost:8000` — no CORS setup needed in development.

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
