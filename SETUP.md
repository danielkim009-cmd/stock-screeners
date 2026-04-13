# Stock Screener — Setup Guide

## Prerequisites

- Python 3.11+
- Node.js 20+ (install via https://nodejs.org or `brew install node`)

---

## 1. Backend (FastAPI)

```bash
cd backend

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start the API server
uvicorn app.main:app --reload --port 8000
```

API docs available at: http://localhost:8000/docs

---

## 2. Frontend (React + Vite)

```bash
cd frontend

# Install dependencies
npm install

# Start dev server
npm run dev
```

Open: http://localhost:5173

---

## Usage

1. Start the backend (port 8000)
2. Start the frontend (port 5173)
3. Open the browser at http://localhost:5173
4. Select "Turtle" strategy, choose filter (ALL / S1_BUY / S2_BUY)
5. Click **Run Screen** — results appear sortable in the table
6. Click any ticker row to view its candlestick chart

---

## Project Structure

```
stock-screeners/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point
│   │   ├── api/routes.py        # REST endpoints
│   │   ├── data/
│   │   │   ├── russell2000.py   # Ticker list (iShares IWM)
│   │   │   └── market_data.py   # yfinance OHLCV fetcher
│   │   └── strategies/
│   │       └── turtle.py        # Turtle Trading logic
│   └── requirements.txt
└── frontend/
    ├── src/
    │   ├── App.jsx              # Nav shell
    │   ├── api/screener.js      # API calls
    │   ├── components/
    │   │   ├── CandlestickChart.jsx
    │   │   ├── ResultsTable.jsx
    │   │   └── SignalBadge.jsx
    │   └── pages/
    │       └── TurtleScreener.jsx
    ├── package.json
    └── vite.config.js
```

---

## Adding More Strategies

1. Create `backend/app/strategies/minervini.py` (or `hmm.py`)
2. Add a new route in `backend/app/api/routes.py`
3. Create `frontend/src/pages/MinerviniScreener.jsx`
4. Register it in `frontend/src/App.jsx` STRATEGIES array
