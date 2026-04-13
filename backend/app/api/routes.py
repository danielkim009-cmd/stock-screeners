"""
FastAPI routes for the stock screener.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.data.market_data import (
    fetch_ohlcv, fetch_bulk_ohlcv,
    compute_ohlcv_extras, fetch_ticker_info,
)
from app.data.universes import fetch_tickers, UNIVERSES
from app.strategies.turtle import screen_turtle, TurtleSignal
from app.strategies.minervini import (
    screen_minervini, compute_rs_ratings, calc_12m_return,
)
from app.strategies.daniels_breakout import screen_daniels_breakout
from app.strategies.daniels_backtest import run_daniels_backtest
from app.strategies.daniels_portfolio_backtest import run_daniels_portfolio_backtest
from app.strategies.minervini_backtest import run_minervini_backtest
from app.strategies.turtle_backtest import run_turtle_backtest
from app.strategies.oneil import screen_oneil

router = APIRouter()
executor = ThreadPoolExecutor(max_workers=8)


# --------------------------------------------------------------------------- #
#  Response models
# --------------------------------------------------------------------------- #

class _MetaMixin(BaseModel):
    """Common metadata fields added to every screener result."""
    name:             Optional[str]   = None
    price_change_pct: Optional[float] = None   # 1-day price change %
    today_vol:        Optional[float] = None   # today's share volume
    rel_vol:          Optional[float] = None   # today vol / 30d avg vol
    market_cap:       Optional[float] = None
    eps:              Optional[float] = None   # trailing EPS
    sector:           Optional[str]   = None
    analyst_rating:   Optional[str]   = None


class TurtleResult(_MetaMixin):
    ticker: str
    last_close: float
    atr_20: float
    high_20: float
    high_55: float
    low_10: float
    low_20: float
    signal: str
    breakout_20: bool
    breakout_55: bool
    days_since_breakout: Optional[int]
    rs_rating: float = 0.0


class ScreenerResponse(BaseModel):
    strategy: str
    universe: str
    total_screened: int
    matches: int
    results: list[Any]


class MinerviniResult(_MetaMixin):
    ticker: str
    last_close: float
    ma50: float
    ma150: float
    ma200: float
    ma200_trend: float
    high_52w: float
    low_52w: float
    pct_from_high: float
    pct_from_low: float
    rs_rating: float
    c1: bool
    c2: bool
    c3: bool
    c4: bool
    c5: bool
    c6: bool
    c7: bool
    c8: bool
    c9: bool
    c10: bool
    criteria_met: int
    passes: bool


class DanielsResult(_MetaMixin):
    ticker: str
    last_close: float
    ema21: float
    ema50: float
    ema100: float
    high_6m: float
    rel_volume: float
    avg_vol_10d: float
    c1: bool
    c2: bool
    c3: bool
    c4: bool
    c5: bool
    c6: bool
    criteria_met: int
    passes: bool


class BacktestTradeOut(BaseModel):
    entry_date:  str
    exit_date:   str
    entry_price: float
    exit_price:  float
    pnl_pct:     float
    days_held:   int
    exit_reason: str
    system:      Optional[str] = None   # "S1" | "S2" — Turtle only


class BacktestResponse(BaseModel):
    ticker:            str
    n_bars:            int
    exit_mode:         str
    trades:            list[BacktestTradeOut]
    equity_curve:      list[dict]
    total_return_pct:  float
    bh_return_pct:     float
    max_drawdown_pct:  float
    win_rate_pct:      float
    n_trades:          int
    sharpe_ratio:      float
    avg_trade_pnl_pct: float


class PortfolioTradeOut(BaseModel):
    ticker:      str
    entry_date:  str
    exit_date:   str
    entry_price: float
    exit_price:  float
    pnl_pct:     float
    days_held:   int
    exit_reason: str


class PortfolioBacktestResponse(BaseModel):
    n_bars:            int
    exit_mode:         str
    max_positions:     int
    benchmark_ticker:  str
    initial_capital:   float
    final_value:       float
    dollar_gain:       float
    cagr:              float
    trades:            list[PortfolioTradeOut]
    equity_curve:      list[dict]
    bh_curve:          list[dict]
    total_return_pct:  float
    bh_return_pct:     float
    bh_cagr:           float
    max_drawdown_pct:    float
    bh_max_drawdown_pct: float
    win_rate_pct:        float
    avg_win_pct:         float
    avg_loss_pct:        float
    n_trades:            int
    sharpe_ratio:        float
    avg_trade_pnl_pct:   float
    avg_positions:       float


class OneilResult(_MetaMixin):
    ticker:          str
    pattern:         str      # "CUP_HANDLE" | "FLAT_BASE" | "DOUBLE_BOTTOM"
    pivot:           float
    last_close:      float
    breakout:        bool
    breakout_vol:    bool
    rel_volume:      float
    depth_pct:       float
    base_weeks:      int
    pct_from_pivot:  float
    rs_rating:       float = 0.0   # 0–99 relative-strength vs screened universe


class OHLCVPoint(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


# --------------------------------------------------------------------------- #
#  Endpoints
# --------------------------------------------------------------------------- #

@router.get("/universes")
def get_universes():
    """Return available universe options."""
    return [{"id": k, **v} for k, v in UNIVERSES.items()]


@router.get("/tickers", response_model=list[str])
def get_tickers(universe: str = Query(default="russell2000")):
    """Return the ticker list for the given universe."""
    return fetch_tickers(universe)


@router.get("/screen/turtle", response_model=ScreenerResponse)
def screen_turtle_strategy(
    universe: str = Query(
        default="russell2000",
        description="Universe: sp500 | nasdaq100 | russell2000 | russell3000",
    ),
    signal_filter: str = Query(
        default="ALL",
        description="Filter: ALL | S1_BUY | S2_BUY",
    ),
    max_tickers: int = Query(
        default=200,
        le=3000,
        description="Limit tickers screened per run",
    ),
):
    """
    Run the Turtle Trading screen against a selected universe.

    - S1_BUY: 20-day Donchian channel breakout
    - S2_BUY: 55-day Donchian channel breakout
    - ALL: return everything (including NONE signals)
    """
    tickers = fetch_tickers(universe)[:max_tickers]
    data    = fetch_bulk_ohlcv(tickers, period_days=400)

    # Step 1: compute RS ratings for the full universe
    returns: dict[str, float] = {}
    for ticker in tickers:
        df = data.get(ticker)
        if df is not None and not df.empty:
            ret = calc_12m_return(df)
            if ret is not None:
                returns[ticker] = ret
    rs_ratings = compute_rs_ratings(returns)

    # Pass 1: screen + collect raw (sig, df) pairs
    raw: list[tuple] = []
    for ticker in tickers:
        df = data.get(ticker)
        if df is None or df.empty:
            continue
        sig = screen_turtle(df, ticker)
        if sig is None:
            continue
        if signal_filter == "ALL" or sig.signal == signal_filter:
            raw.append((sig, df))

    # Fetch metadata only for tickers with an actual breakout signal
    signal_tickers = [sig.ticker for sig, _ in raw if sig.signal != "NONE"]
    meta = fetch_ticker_info(signal_tickers)

    # Pass 2: build result objects
    results = []
    for sig, df in raw:
        extras = compute_ohlcv_extras(df)
        m = meta.get(sig.ticker, {})
        results.append(TurtleResult(
            ticker=sig.ticker,
            last_close=sig.last_close,
            atr_20=sig.atr_20,
            high_20=sig.high_20,
            high_55=sig.high_55,
            low_10=sig.low_10,
            low_20=sig.low_20,
            signal=sig.signal,
            breakout_20=sig.breakout_20,
            breakout_55=sig.breakout_55,
            days_since_breakout=sig.days_since_breakout,
            rs_rating=rs_ratings.get(sig.ticker, 0.0),
            name=m.get("name"),
            price_change_pct=extras["price_change_pct"],
            today_vol=extras["today_vol"],
            rel_vol=extras["rel_vol"],
            market_cap=m.get("market_cap"),
            eps=m.get("eps"),
            sector=m.get("sector"),
            analyst_rating=m.get("analyst_rating"),
        ))

    # Sort: S2_BUY first, then S1_BUY, then NONE; then by ATR desc
    order = {"S2_BUY": 0, "S1_BUY": 1, "NONE": 2}
    results.sort(key=lambda r: (order.get(r.signal, 3), -r.atr_20))

    return ScreenerResponse(
        strategy="turtle",
        universe=universe,
        total_screened=len(tickers),
        matches=len([r for r in results if r.signal != "NONE"]),
        results=results,
    )


@router.get("/screen/minervini", response_model=ScreenerResponse)
def screen_minervini_strategy(
    universe: str = Query(
        default="russell2000",
        description="Universe: sp500 | nasdaq100 | russell2000 | russell3000",
    ),
    min_criteria: int = Query(
        default=10,
        ge=1,
        le=10,
        description="Minimum number of criteria that must be met (1–10). 10 = strict SEPA pass.",
    ),
    max_tickers: int = Query(
        default=200,
        le=3000,
        description="Limit tickers screened per run",
    ),
):
    """
    Run Minervini's SEPA Trend Template screen against a selected universe.

    Requires 300 days of price history to compute 200-day MA + 52-week range.
    RS Rating is computed relative to all tickers in the screened batch.
    """
    tickers = fetch_tickers(universe)[:max_tickers]
    data    = fetch_bulk_ohlcv(tickers, period_days=400)

    # Step 1: compute 12-month returns for RS Rating
    returns: dict[str, float] = {}
    for ticker in tickers:
        df = data.get(ticker)
        if df is not None and not df.empty:
            ret = calc_12m_return(df)
            if ret is not None:
                returns[ticker] = ret

    rs_ratings = compute_rs_ratings(returns)

    # Step 2: screen + collect raw (sig, df) pairs
    raw: list[tuple] = []
    for ticker in tickers:
        df = data.get(ticker)
        if df is None or df.empty:
            continue
        rs  = rs_ratings.get(ticker, 0.0)
        if rs <= 85.0:
            continue
        vol = df["Volume"].values
        n_v = len(vol)
        today_vol = float(vol[-1])
        avg_10 = float(vol[max(0, n_v - 11):n_v - 1].mean()) if n_v >= 2 else today_vol
        if avg_10 < 1_000_000:
            continue
        avg_30 = float(vol[max(0, n_v - 31):n_v - 1].mean()) if n_v >= 2 else today_vol
        actual_rel_vol = today_vol / avg_30 if avg_30 > 0 else 0.0
        if actual_rel_vol < 1.5:
            continue
        sig = screen_minervini(df, ticker, rs, rel_vol=actual_rel_vol, avg_vol_10d=avg_10)
        if sig is None:
            continue
        if sig.criteria_met >= min_criteria:
            raw.append((sig, df))

    # Fetch metadata for result tickers
    result_tickers = [sig.ticker for sig, _ in raw]
    meta = fetch_ticker_info(result_tickers)

    # Step 3: build result objects
    results = []
    for sig, df in raw:
        extras = compute_ohlcv_extras(df)
        m = meta.get(sig.ticker, {})
        results.append(MinerviniResult(
            ticker=sig.ticker,
            last_close=sig.last_close,
            ma50=sig.ma50,
            ma150=sig.ma150,
            ma200=sig.ma200,
            ma200_trend=sig.ma200_trend,
            high_52w=sig.high_52w,
            low_52w=sig.low_52w,
            pct_from_high=sig.pct_from_high,
            pct_from_low=sig.pct_from_low,
            rs_rating=sig.rs_rating,
            c1=sig.c1, c2=sig.c2, c3=sig.c3, c4=sig.c4,
            c5=sig.c5, c6=sig.c6, c7=sig.c7, c8=sig.c8, c9=sig.c9, c10=sig.c10,
            criteria_met=sig.criteria_met,
            passes=sig.passes,
            name=m.get("name"),
            price_change_pct=extras["price_change_pct"],
            today_vol=extras["today_vol"],
            rel_vol=extras["rel_vol"],
            market_cap=m.get("market_cap"),
            eps=m.get("eps"),
            sector=m.get("sector"),
            analyst_rating=m.get("analyst_rating"),
        ))

    # Sort: full passes first, then by criteria_met desc, then RS Rating desc
    results.sort(key=lambda r: (-int(r.passes), -r.criteria_met, -r.rs_rating))

    return ScreenerResponse(
        strategy="minervini",
        universe=universe,
        total_screened=len(tickers),
        matches=len([r for r in results if r.passes]),
        results=results,
    )


@router.get("/screen/daniels", response_model=ScreenerResponse)
def screen_daniels_strategy(
    universe: str = Query(
        default="sp500",
        description="Universe: sp500 | nasdaq100 | russell2000 | russell3000",
    ),
    min_criteria: int = Query(
        default=6,
        ge=1,
        le=6,
        description="Minimum number of criteria that must be met (1–6). 6 = strict pass.",
    ),
    max_tickers: int = Query(
        default=200,
        le=3000,
        description="Limit tickers screened per run",
    ),
):
    """
    Run Daniel's Breakout screen: EMA stack + volume surge + new 6-month high.

    Requires ~200 calendar days of price history for EMA100 and 6-month high.
    """
    tickers = fetch_tickers(universe)[:max_tickers]
    data    = fetch_bulk_ohlcv(tickers, period_days=200)

    # Pass 1: screen + collect raw (sig, df) pairs
    raw: list[tuple] = []
    for ticker in tickers:
        df = data.get(ticker)
        if df is None or df.empty:
            continue
        sig = screen_daniels_breakout(df, ticker)
        if sig is None:
            continue
        if sig.criteria_met >= min_criteria:
            raw.append((sig, df))

    # Fetch metadata for result tickers
    result_tickers = [sig.ticker for sig, _ in raw]
    meta = fetch_ticker_info(result_tickers)

    # Pass 2: build result objects
    results = []
    for sig, df in raw:
        extras = compute_ohlcv_extras(df)
        m = meta.get(sig.ticker, {})
        results.append(DanielsResult(
            ticker=sig.ticker,
            last_close=sig.last_close,
            ema21=sig.ema21,
            ema50=sig.ema50,
            ema100=sig.ema100,
            high_6m=sig.high_6m,
            rel_volume=sig.rel_volume,
            avg_vol_10d=sig.avg_vol_10d,
            c1=sig.c1, c2=sig.c2, c3=sig.c3,
            c4=sig.c4, c5=sig.c5, c6=sig.c6,
            criteria_met=sig.criteria_met,
            passes=sig.passes,
            name=m.get("name"),
            price_change_pct=extras["price_change_pct"],
            today_vol=extras["today_vol"],
            rel_vol=extras["rel_vol"],
            market_cap=m.get("market_cap"),
            eps=m.get("eps"),
            sector=m.get("sector"),
            analyst_rating=m.get("analyst_rating"),
        ))

    # Sort: full passes first, then by rel_volume desc (biggest surge first)
    results.sort(key=lambda r: (-int(r.passes), -r.criteria_met, -r.rel_volume))

    return ScreenerResponse(
        strategy="daniels",
        universe=universe,
        total_screened=len(tickers),
        matches=len([r for r in results if r.passes]),
        results=results,
    )


@router.get("/backtest/daniels", response_model=BacktestResponse)
def backtest_daniels(
    ticker:      str   = Query(..., description="Ticker symbol to backtest"),
    period_days: int   = Query(default=730, ge=200, le=1825, description="Calendar days of history"),
    exit_mode:   str   = Query(default="SMA50", description="SMA50 | ATR_TRAIL | PCT_TRAIL | BOTH"),
    trail_pct:   float = Query(default=10.0, ge=1.0, le=50.0, description="% drop from peak to trigger PCT_TRAIL exit"),
):
    """
    Walk-forward backtest of Daniel's breakout strategy on a single ticker.

    Entry: all 6 criteria satisfied → enter next bar's open.
    Exit:  SMA50 close-below | 2×ATR(20) trailing stop | PCT trailing stop | first to trigger (BOTH).
    """
    df = fetch_ohlcv(ticker.upper(), period_days=period_days)
    if df is None or df.empty or len(df) < 200:
        raise HTTPException(status_code=404, detail=f"Insufficient data for {ticker}")

    result = run_daniels_backtest(df, ticker.upper(), exit_mode=exit_mode.upper(), trail_pct=trail_pct)
    if result is None:
        raise HTTPException(status_code=422, detail="Not enough trading bars to run backtest")

    return BacktestResponse(
        ticker=result.ticker,
        n_bars=result.n_bars,
        exit_mode=result.exit_mode,
        trades=[BacktestTradeOut(**t.__dict__) for t in result.trades],
        equity_curve=result.equity_curve,
        total_return_pct=result.total_return_pct,
        bh_return_pct=result.bh_return_pct,
        max_drawdown_pct=result.max_drawdown_pct,
        bh_max_drawdown_pct=result.bh_max_drawdown_pct,
        win_rate_pct=result.win_rate_pct,
        avg_win_pct=result.avg_win_pct,
        avg_loss_pct=result.avg_loss_pct,
        n_trades=result.n_trades,
        sharpe_ratio=result.sharpe_ratio,
        avg_trade_pnl_pct=result.avg_trade_pnl_pct,
    )


@router.get("/backtest/daniels/portfolio", response_model=PortfolioBacktestResponse)
def backtest_daniels_portfolio(
    period_days:      int   = Query(default=730,      ge=365,  le=7300,         description="Calendar days of history"),
    exit_mode:        str   = Query(default="BOTH",              description="SMA50 | ATR_TRAIL | PCT_TRAIL | BOTH"),
    trail_pct:        float = Query(default=10.0,    ge=1.0,  le=50.0,          description="% drop from peak for PCT_TRAIL"),
    max_positions:    int   = Query(default=10,       ge=1,    le=50,            description="Max concurrent positions"),
    rebalance:        str   = Query(default="NONE",              description="NONE | DAILY | WEEKLY | MONTHLY | QUARTERLY"),
    initial_capital:  float = Query(default=100_000, ge=1_000, le=100_000_000,  description="Starting portfolio value in USD"),
    universe:         str   = Query(default="sp500",             description="sp500 | nasdaq100 | russell2000"),
    start_date:       Optional[str] = Query(default=None,        description="Backtest start date YYYY-MM-DD (overrides period_days)"),
    end_date:         Optional[str] = Query(default=None,        description="Backtest end date YYYY-MM-DD (default: today)"),
    rank_by:          str           = Query(default="REL_VOL",   description="REL_VOL | RS_20 | RS_63 | RS_126 | RS_VOL"),
):
    """
    Portfolio walk-forward backtest of Daniel's breakout strategy.

    Screens the selected universe daily, holds up to max_positions simultaneously,
    ranked by relative volume (largest surge gets priority).
    Benchmark: SPY buy-and-hold over the same window.

    WARNING: fetches all universe tickers — expect 30-60s for large universes.
    """
    allowed = {"sp500", "nasdaq100", "russell2000"}
    if universe not in allowed:
        raise HTTPException(status_code=400, detail=f"universe must be one of {sorted(allowed)}")

    tickers = fetch_tickers(universe)
    if not tickers:
        raise HTTPException(status_code=503, detail=f"Could not fetch {universe} tickers")

    # Choose benchmark ETF based on universe
    benchmark_map = {"sp500": "SPY", "nasdaq100": "QQQ", "russell2000": "IWM"}
    benchmark_ticker = benchmark_map.get(universe, "SPY")

    # Resolve date window
    import pandas as _pd
    today = _pd.Timestamp.today().normalize()
    if start_date:
        try:
            t_start = _pd.Timestamp(start_date)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid start_date format; use YYYY-MM-DD")
    else:
        t_start = today - _pd.Timedelta(days=period_days)
    if end_date:
        try:
            t_end = _pd.Timestamp(end_date)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid end_date format; use YYYY-MM-DD")
    else:
        t_end = today
    if t_start >= t_end:
        raise HTTPException(status_code=400, detail="start_date must be before end_date")

    # Fetch enough data: window + warmup buffer
    fetch_days = int((today - t_start).days) + 220
    all_tickers = list(set(tickers + [benchmark_ticker]))
    raw_dfs = fetch_bulk_ohlcv(all_tickers, period_days=fetch_days)

    # Trim each df to the requested window (keep warmup before t_start for indicators,
    # but hard-cap the end at t_end so the backtest doesn't peek beyond end_date)
    def _trim(df):
        if df is None or df.empty:
            return df
        return df[df.index <= t_end]

    spy_df    = _trim(raw_dfs.pop(benchmark_ticker, None))
    stock_dfs = {t: _trim(df) for t, df in raw_dfs.items() if df is not None and not df.empty}

    if len(stock_dfs) < 10:
        raise HTTPException(status_code=503, detail="Insufficient stock data fetched")

    result = run_daniels_portfolio_backtest(
        stock_dfs=stock_dfs,
        spy_df=spy_df,
        exit_mode=exit_mode.upper(),
        trail_pct=trail_pct,
        max_positions=max_positions,
        backtest_start=str(t_start.date()),
        rank_by=rank_by.upper(),
        rebalance=rebalance.upper(),
        initial_capital=initial_capital,
    )
    if result is None:
        raise HTTPException(status_code=422, detail="Not enough data to run portfolio backtest")

    return PortfolioBacktestResponse(
        n_bars=result.n_bars,
        exit_mode=result.exit_mode,
        max_positions=result.max_positions,
        benchmark_ticker=benchmark_ticker,
        trades=[PortfolioTradeOut(**t.__dict__) for t in result.trades],
        initial_capital=result.initial_capital,
        final_value=result.final_value,
        dollar_gain=result.dollar_gain,
        cagr=result.cagr,
        equity_curve=result.equity_curve,
        bh_curve=result.bh_curve,
        total_return_pct=result.total_return_pct,
        bh_return_pct=result.bh_return_pct,
        bh_cagr=result.bh_cagr,
        max_drawdown_pct=result.max_drawdown_pct,
        bh_max_drawdown_pct=result.bh_max_drawdown_pct,
        win_rate_pct=result.win_rate_pct,
        avg_win_pct=result.avg_win_pct,
        avg_loss_pct=result.avg_loss_pct,
        n_trades=result.n_trades,
        sharpe_ratio=result.sharpe_ratio,
        avg_trade_pnl_pct=result.avg_trade_pnl_pct,
        avg_positions=result.avg_positions,
    )


@router.get("/backtest/turtle", response_model=BacktestResponse)
def backtest_turtle(
    ticker:      str = Query(..., description="Ticker symbol to backtest"),
    period_days: int = Query(default=730, ge=120, le=1825, description="Calendar days of history"),
    system:      str = Query(default="S2", description="S1 | S2 | BOTH"),
):
    """
    Walk-forward backtest of the Turtle Trading strategy on a single ticker.

    Entry: S1 = 20-day Donchian high breakout; S2 = 55-day Donchian high breakout.
    Exit:  S1 → 10-day Donchian low; S2 → 20-day Donchian low; both + 2×ATR(20) hard stop.
    """
    df = fetch_ohlcv(ticker.upper(), period_days=period_days)
    if df is None or df.empty or len(df) < 120:
        raise HTTPException(status_code=404, detail=f"Insufficient data for {ticker}")

    result = run_turtle_backtest(df, ticker.upper(), system=system.upper())
    if result is None:
        raise HTTPException(status_code=422, detail="Not enough trading bars to run backtest")

    return BacktestResponse(
        ticker=result.ticker,
        n_bars=result.n_bars,
        exit_mode=result.exit_mode,
        trades=[BacktestTradeOut(**t.__dict__) for t in result.trades],
        equity_curve=result.equity_curve,
        total_return_pct=result.total_return_pct,
        bh_return_pct=result.bh_return_pct,
        max_drawdown_pct=result.max_drawdown_pct,
        bh_max_drawdown_pct=result.bh_max_drawdown_pct,
        win_rate_pct=result.win_rate_pct,
        avg_win_pct=result.avg_win_pct,
        avg_loss_pct=result.avg_loss_pct,
        n_trades=result.n_trades,
        sharpe_ratio=result.sharpe_ratio,
        avg_trade_pnl_pct=result.avg_trade_pnl_pct,
    )


@router.get("/backtest/minervini", response_model=BacktestResponse)
def backtest_minervini(
    ticker:      str   = Query(..., description="Ticker symbol to backtest"),
    period_days: int   = Query(default=730, ge=300, le=1825, description="Calendar days of history"),
    exit_mode:   str   = Query(default="SMA50", description="SMA50 | ATR_TRAIL | PCT_TRAIL | BOTH"),
    trail_pct:   float = Query(default=8.0, ge=1.0, le=50.0, description="Trailing stop % (used when exit_mode=PCT_TRAIL)"),
):
    """
    Walk-forward backtest of Minervini SEPA strategy on a single ticker.

    Entry: C1–C7 all satisfied → enter next bar's open.
    Exit:  SMA50 close-below | 2×ATR(20) trailing stop | trail_pct% trailing stop | BOTH (SMA50+ATR).
    Note:  C8 (RS Rating) is omitted — it requires universe-wide comparison.
    """
    df = fetch_ohlcv(ticker.upper(), period_days=period_days)
    if df is None or df.empty or len(df) < 300:
        raise HTTPException(status_code=404, detail=f"Insufficient data for {ticker}")

    result = run_minervini_backtest(
        df, ticker.upper(),
        exit_mode=exit_mode.upper(),
        trail_pct=trail_pct,
    )
    if result is None:
        raise HTTPException(status_code=422, detail="Not enough trading bars to run backtest")

    return BacktestResponse(
        ticker=result.ticker,
        n_bars=result.n_bars,
        exit_mode=result.exit_mode,
        trades=[BacktestTradeOut(**t.__dict__) for t in result.trades],
        equity_curve=result.equity_curve,
        total_return_pct=result.total_return_pct,
        bh_return_pct=result.bh_return_pct,
        max_drawdown_pct=result.max_drawdown_pct,
        bh_max_drawdown_pct=result.bh_max_drawdown_pct,
        win_rate_pct=result.win_rate_pct,
        avg_win_pct=result.avg_win_pct,
        avg_loss_pct=result.avg_loss_pct,
        n_trades=result.n_trades,
        sharpe_ratio=result.sharpe_ratio,
        avg_trade_pnl_pct=result.avg_trade_pnl_pct,
    )


@router.get("/screen/oneil", response_model=ScreenerResponse)
def screen_oneil_patterns(
    universe: str = Query(
        default="sp500",
        description="Universe: sp500 | nasdaq100 | russell2000 | russell3000",
    ),
    pattern_filter: str = Query(
        default="ALL",
        description="Filter: ALL | CUP_HANDLE | FLAT_BASE | DOUBLE_BOTTOM",
    ),
    breakout_only: bool = Query(
        default=False,
        description="If true, only return tickers already breaking above their pivot",
    ),
    max_tickers: int = Query(
        default=200,
        le=3000,
        description="Limit tickers screened per run",
    ),
):
    """
    Scan for O'Neil CAN SLIM base patterns: Cup-with-Handle, Flat Base, Double Bottom.

    Returns stocks near or at their pivot buy point.
    Pattern priority: Cup-with-Handle > Flat Base > Double Bottom.
    RS Rating (0–99) is computed relative to all tickers in the screened batch,
    mirroring the CAN SLIM "L — Leader" criterion.
    """
    tickers = fetch_tickers(universe)[:max_tickers]
    data    = fetch_bulk_ohlcv(tickers, period_days=400)

    # Compute RS ratings across the full batch (L — Leader criterion)
    returns: dict[str, float] = {}
    for ticker in tickers:
        df = data.get(ticker)
        if df is not None and not df.empty:
            ret = calc_12m_return(df)
            if ret is not None:
                returns[ticker] = ret
    rs_ratings = compute_rs_ratings(returns)

    raw: list[tuple] = []
    for ticker in tickers:
        df = data.get(ticker)
        if df is None or df.empty:
            continue
        sig = screen_oneil(df, ticker)
        if sig is None:
            continue
        if pattern_filter != "ALL" and sig.pattern != pattern_filter:
            continue
        if breakout_only and not sig.breakout:
            continue
        raw.append((sig, df))

    result_tickers = [sig.ticker for sig, _ in raw]
    meta = fetch_ticker_info(result_tickers)

    results = []
    for sig, df in raw:
        extras = compute_ohlcv_extras(df)
        m = meta.get(sig.ticker, {})
        results.append(OneilResult(
            ticker=sig.ticker,
            pattern=sig.pattern,
            pivot=sig.pivot,
            last_close=sig.last_close,
            breakout=sig.breakout,
            breakout_vol=sig.breakout_vol,
            rel_volume=sig.rel_volume,
            depth_pct=sig.depth_pct,
            base_weeks=sig.base_weeks,
            pct_from_pivot=sig.pct_from_pivot,
            rs_rating=round(rs_ratings.get(sig.ticker, 0.0), 1),
            name=m.get("name"),
            price_change_pct=extras["price_change_pct"],
            today_vol=extras["today_vol"],
            rel_vol=extras["rel_vol"],
            market_cap=m.get("market_cap"),
            eps=m.get("eps"),
            sector=m.get("sector"),
            analyst_rating=m.get("analyst_rating"),
        ))

    # Sort: breakouts first, then by pct_from_pivot ascending (closest to pivot)
    results.sort(key=lambda r: (-int(r.breakout and r.breakout_vol), -int(r.breakout), r.pct_from_pivot))

    return ScreenerResponse(
        strategy="oneil",
        universe=universe,
        total_screened=len(tickers),
        matches=len([r for r in results if r.breakout]),
        results=results,
    )


@router.get("/chart/{ticker}", response_model=list[OHLCVPoint])
def get_chart(ticker: str, period_days: int = Query(default=120, le=3870)):
    """Return OHLCV data for a single ticker."""
    df = fetch_ohlcv(ticker.upper(), period_days=period_days)
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail=f"No data for {ticker}")

    return [
        OHLCVPoint(
            date=str(idx.date()),
            open=round(float(row["Open"]), 2),
            high=round(float(row["High"]), 2),
            low=round(float(row["Low"]), 2),
            close=round(float(row["Close"]), 2),
            volume=float(row["Volume"]),
        )
        for idx, row in df.iterrows()
    ]
