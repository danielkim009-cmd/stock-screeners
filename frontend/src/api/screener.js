const BASE = "/api";

export async function fetchUniverses() {
  const res = await fetch(`${BASE}/universes`);
  if (!res.ok) throw new Error(`Universes error: ${res.status}`);
  return res.json();
}

export async function runTurtleScreen(universe = "russell2000", signalFilter = "ALL", maxTickers = 200) {
  const params = new URLSearchParams({
    universe,
    signal_filter: signalFilter,
    max_tickers: maxTickers,
  });
  const res = await fetch(`${BASE}/screen/turtle?${params}`);
  if (!res.ok) throw new Error(`Screener error: ${res.status}`);
  return res.json();
}

export async function runMinerviniScreen(universe = "russell2000", minCriteria = 8, maxTickers = 200) {
  const params = new URLSearchParams({
    universe,
    min_criteria: minCriteria,
    max_tickers: maxTickers,
  });
  const res = await fetch(`${BASE}/screen/minervini?${params}`);
  if (!res.ok) throw new Error(`Screener error: ${res.status}`);
  return res.json();
}

export async function runDanielsScreen(universe = "sp500", minCriteria = 6, maxTickers = 200, minRelVol = 1.5, minAvgVol = 1000000, highLookback = 125) {
  const params = new URLSearchParams({
    universe,
    min_criteria: minCriteria,
    max_tickers: maxTickers,
    min_rel_vol: minRelVol,
    min_avg_vol: minAvgVol,
    high_lookback: highLookback,
  });
  const res = await fetch(`${BASE}/screen/daniels?${params}`);
  if (!res.ok) throw new Error(`Screener error: ${res.status}`);
  return res.json();
}

export async function runDanielsBacktest(ticker, periodDays = 730, exitMode = "SMA50", trailPct = 10) {
  const params = new URLSearchParams({
    ticker,
    period_days: periodDays,
    exit_mode: exitMode,
    trail_pct: trailPct,
  });
  const res = await fetch(`${BASE}/backtest/daniels?${params}`);
  if (!res.ok) throw new Error(`Backtest error: ${res.status}`);
  return res.json();
}

export async function runDanielsPortfolioBacktest(periodDays = 730, exitMode = "BOTH", trailPct = 10, maxPositions = 10, rebalance = "NONE", initialCapital = 100000, universe = "sp500", startDate = "", endDate = "", rankBy = "REL_VOL") {
  const params = new URLSearchParams({
    period_days: periodDays,
    exit_mode: exitMode,
    trail_pct: trailPct,
    max_positions: maxPositions,
    rebalance,
    initial_capital: initialCapital,
    universe,
    rank_by: rankBy,
  });
  if (startDate) params.set("start_date", startDate);
  if (endDate)   params.set("end_date",   endDate);
  const res = await fetch(`${BASE}/backtest/daniels/portfolio?${params}`);
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `Portfolio backtest error: ${res.status}`);
  }
  return res.json();
}

export async function runOneilScreen(universe = "sp500", patternFilter = "ALL", breakoutOnly = false, maxTickers = 200) {
  const params = new URLSearchParams({
    universe,
    pattern_filter: patternFilter,
    breakout_only: breakoutOnly,
    max_tickers: maxTickers,
  });
  const res = await fetch(`${BASE}/screen/oneil?${params}`);
  if (!res.ok) throw new Error(`Screener error: ${res.status}`);
  return res.json();
}

export async function runTurtleBacktest(ticker, periodDays = 730, system = "S2") {
  const params = new URLSearchParams({
    ticker,
    period_days: periodDays,
    system,
  });
  const res = await fetch(`${BASE}/backtest/turtle?${params}`);
  if (!res.ok) throw new Error(`Backtest error: ${res.status}`);
  return res.json();
}

export async function runMinerviniBacktest(ticker, periodDays = 730, exitMode = "SMA50", trailPct = 8.0) {
  const params = new URLSearchParams({
    ticker,
    period_days: periodDays,
    exit_mode: exitMode,
    trail_pct: trailPct,
  });
  const res = await fetch(`${BASE}/backtest/minervini?${params}`);
  if (!res.ok) throw new Error(`Backtest error: ${res.status}`);
  return res.json();
}

export async function fetchChart(ticker, periodDays = 120) {
  const res = await fetch(`${BASE}/chart/${ticker}?period_days=${periodDays}`);
  if (!res.ok) throw new Error(`Chart error: ${res.status}`);
  return res.json();
}
