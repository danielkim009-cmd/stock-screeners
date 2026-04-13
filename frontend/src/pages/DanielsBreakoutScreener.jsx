import { useState, useEffect } from "react";
import { runDanielsScreen, fetchChart, runDanielsBacktest, runDanielsPortfolioBacktest } from "../api/screener";
import CandlestickChart from "../components/CandlestickChart";
import EquityChart from "../components/EquityChart";
import { exportCsv, today } from "../utils/exportCsv";

const DANIELS_FIELDS = ["ticker","name","criteria_met","passes","last_close","ema21","ema50","ema100","high_6m","rel_volume","avg_vol_10d","c1","c2","c3","c4","c5","c6","price_change_pct","rel_vol","today_vol","market_cap","eps","sector","analyst_rating"];
const DANIELS_HEADERS = { ticker:"Ticker", name:"Name", criteria_met:"Criteria Met", passes:"Passes", last_close:"Close", ema21:"EMA21", ema50:"EMA50", ema100:"EMA100", high_6m:"6m High", rel_volume:"Rel Vol (Signal)", avg_vol_10d:"Avg Vol 10d", c1:"C1", c2:"C2", c3:"C3", c4:"C4", c5:"C5", c6:"C6", price_change_pct:"Chg %", rel_vol:"Rel Vol 30d", today_vol:"Volume", market_cap:"Mkt Cap", eps:"EPS", sector:"Sector", analyst_rating:"Rating" };
import {
  fmtVol, fmtMarketCap,
  TickerCell, PriceChangePct, RelVolBadge, AnalystBadge,
} from "../components/MetaCells";

const UNIVERSES = [
  { id: "sp500",       label: "S&P 500",      size: "~503" },
  { id: "nasdaq100",   label: "NASDAQ 100",   size: "~101" },
  { id: "russell2000", label: "Russell 2000", size: "~2000" },
  { id: "futures",     label: "Futures",      size: "~37" },
  { id: "crypto",      label: "Crypto",       size: "~48" },
];

const RATING_FILTERS = [
  { id: "ALL",        label: "All Ratings", color: "#8b949e" },
  { id: "STRONG_BUY", label: "Strong Buy",  color: "#56d364" },
  { id: "BUY",        label: "Buy",         color: "#3fb950" },
  { id: "HOLD",       label: "Hold",        color: "#e3b341" },
];

const REL_VOL_FILTERS = [
  { id: "ALL", label: "All",   color: "#8b949e" },
  { id: "2",   label: "≥ 2×",  color: "#56d364" },
  { id: "1.5", label: "≥ 1.5×", color: "#3fb950" },
  { id: "1",   label: "≥ 1×",  color: "#e3b341" },
];

function ratingMatch(rating, filter) {
  if (filter === "ALL") return true;
  if (!rating) return false;
  const key = rating.toLowerCase().replace(/ /g, "_");
  if (filter === "STRONG_BUY") return key === "strong_buy";
  if (filter === "BUY") return key === "buy";
  if (filter === "HOLD") return key === "hold";
  return true;
}

const CRITERIA_LABELS = [
  { key: "c1", label: "Price > EMA21" },
  { key: "c2", label: "EMA21 ≥ EMA50" },
  { key: "c3", label: "EMA50 ≥ EMA100" },
  { key: "c4", label: "New 6-month high" },
  { key: "c5", label: "Rel Vol ≥ 1.5×" },
  { key: "c6", label: "10d avg vol ≥ 1M" },
];

const selectStyle = {
  background: "#161b22", color: "#e6edf3", border: "1px solid #30363d",
  borderRadius: 6, padding: "4px 8px", fontSize: 13,
};

function TabBtn({ active, onClick, children }) {
  return (
    <button onClick={onClick} style={{
      padding: "5px 14px", borderRadius: 6, border: "none",
      background: active ? "#21262d" : "transparent",
      color: active ? "#e6edf3" : "#8b949e",
      cursor: "pointer", fontWeight: 600, fontSize: 13,
    }}>
      {children}
    </button>
  );
}

function ModeTab({ active, onClick, children }) {
  return (
    <button onClick={onClick} style={{
      padding: "7px 20px", borderRadius: 6,
      border: active ? "1px solid #388bfd" : "1px solid #30363d",
      background: active ? "#1f3a5f" : "transparent",
      color: active ? "#58a6ff" : "#8b949e",
      cursor: "pointer", fontWeight: 700, fontSize: 13,
    }}>
      {children}
    </button>
  );
}

function CriteriaBadge({ met }) {
  const color = met === 6 ? "#56d364" : met >= 4 ? "#e3b341" : "#8b949e";
  return <span style={{ color, fontWeight: 700 }}>{met}/6</span>;
}

function FilterChip({ label, active, color, onClick }) {
  return (
    <button onClick={onClick} style={{
      padding: "3px 10px", borderRadius: 12, fontSize: 12, fontWeight: 600,
      cursor: "pointer", border: active ? `1px solid ${color}` : "1px solid #30363d",
      background: active ? color + "22" : "transparent",
      color: active ? color : "#8b949e",
    }}>
      {label}
    </button>
  );
}

function MetricCard({ label, value, color }) {
  return (
    <div style={{
      background: "#0d1117", border: "1px solid #21262d", borderRadius: 8,
      padding: "10px 14px", minWidth: 100, flex: "1 1 100px",
    }}>
      <div style={{ fontSize: 10, color: "#8b949e", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ fontSize: 18, fontWeight: 700, color: color || "#e6edf3" }}>
        {value}
      </div>
    </div>
  );
}

export default function DanielsBreakoutScreener() {
  const [mode, setMode] = useState("screen");  // "screen" | "backtest" | "portfolio"

  // Screen state
  const [universe, setUniverse] = useState("sp500");
  const [minCriteria, setMinCriteria] = useState(6);
  const [maxTickers, setMaxTickers] = useState(3000);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [response, setResponse] = useState(null);
  const [selectedTicker, setSelectedTicker] = useState(null);
  const [chartData, setChartData] = useState(null);
  const [chartLoading, setChartLoading] = useState(false);
  const [tickersCopied, setTickersCopied] = useState(false);
  const [viewRating, setViewRating] = useState("ALL");
  const [viewRelVol, setViewRelVol] = useState("ALL");

  // Backtest state
  const [btTickerInput, setBtTickerInput] = useState("");
  const [btTicker, setBtTicker] = useState(null);
  const [btData, setBtData] = useState(null);
  const [btChartData, setBtChartData] = useState(null);
  const [btLoading, setBtLoading] = useState(false);
  const [btPeriod, setBtPeriod] = useState(730);
  const [btExitMode, setBtExitMode] = useState("SMA50");
  const [btTrailPct, setBtTrailPct] = useState(10);
  const [btError, setBtError] = useState(null);
  const [btExitReasonFilter, setBtExitReasonFilter] = useState("ALL");

  // Portfolio backtest state
  const [pfPeriod, setPfPeriod] = useState(730);
  const [pfStartDate, setPfStartDate] = useState("");
  const [pfEndDate, setPfEndDate] = useState("");
  const [pfRankBy, setPfRankBy] = useState("REL_VOL");
  const [pfTradeFilter, setPfTradeFilter] = useState({ ticker: "", exitReason: "ALL", result: "ALL" });
  const [pfExitMode, setPfExitMode] = useState("BOTH");
  const [pfTrailPct, setPfTrailPct] = useState(10);
  const [pfMaxPos, setPfMaxPos] = useState(10);
  const [pfRebalance, setPfRebalance] = useState("NONE");
  const [pfCapital, setPfCapital] = useState(100000);
  const [pfUniverse, setPfUniverse] = useState("sp500");
  const [pfLoading, setPfLoading] = useState(false);
  const [pfData, setPfData] = useState(null);
  const [pfError, setPfError] = useState(null);

  const selectedUniverse = UNIVERSES.find(u => u.id === universe);

  async function run() {
    setLoading(true);
    setError(null);
    setResponse(null);
    setSelectedTicker(null);
    setBtTicker(null);
    setViewRating("ALL");
    setViewRelVol("ALL");
    try {
      const data = await runDanielsScreen(universe, minCriteria, maxTickers);
      setResponse(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function selectTicker(ticker) {
    setSelectedTicker(ticker);
    setChartLoading(true);
    try {
      const data = await fetchChart(ticker, 435);   // 365 + 70 cal days SMA warm-up ≈ 1 year visible
      setChartData(data);
    } catch {
      setChartData(null);
    } finally {
      setChartLoading(false);
    }
  }

  async function startBacktest(ticker, period, exitMode, trailPct) {
    setBtTicker(ticker);
    setBtData(null);
    setBtChartData(null);
    setBtError(null);
    setBtExitReasonFilter("ALL");
    setBtLoading(true);
    try {
      const [btResult, chartResult] = await Promise.all([
        runDanielsBacktest(ticker, period, exitMode, trailPct),
        fetchChart(ticker, period + 70),   // +70 cal days ≈ 50 trading days SMA warm-up
      ]);
      setBtData(btResult);
      setBtChartData(chartResult);
    } catch (e) {
      setBtData(null);
      setBtChartData(null);
      setBtError(e.message || "Backtest failed");
    } finally {
      setBtLoading(false);
    }
  }

  async function runPortfolioBacktest() {
    setPfData(null);
    setPfError(null);
    setPfLoading(true);
    try {
      const data = await runDanielsPortfolioBacktest(pfPeriod, pfExitMode, pfTrailPct, pfMaxPos, pfRebalance, pfCapital, pfUniverse, pfStartDate, pfEndDate, pfRankBy);
      setPfData(data);
    } catch (e) {
      setPfError(e.message || "Portfolio backtest failed");
    } finally {
      setPfLoading(false);
    }
  }

  const visibleResults = response
    ? response.results.filter(r =>
        ratingMatch(r.analyst_rating, viewRating) &&
        (viewRelVol === "ALL" || (r.rel_vol ?? r.rel_volume ?? 0) >= Number(viewRelVol))
      )
    : [];

  const th = {
    padding: "8px 12px", textAlign: "left", borderBottom: "1px solid #30363d",
    color: "#8b949e", fontWeight: 600, fontSize: 11,
    textTransform: "uppercase", letterSpacing: "0.05em", whiteSpace: "nowrap",
  };
  const td = { padding: "8px 12px", borderBottom: "1px solid #21262d", fontSize: 13 };

  const pctColor = v => v > 0 ? "#56d364" : v < 0 ? "#f85149" : "#8b949e";
  const fmtPct = v => `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
  const fmtDollars = v => {
    const abs = Math.abs(v);
    if (abs >= 1_000_000) return `$${(v / 1_000_000).toFixed(2)}M`;
    if (abs >= 1_000)     return `$${(v / 1_000).toFixed(1)}K`;
    return `$${v.toFixed(0)}`;
  };
  const exitColor = reason => {
    if (reason === "SMA50") return "#e3b341";
    if (reason === "ATR_STOP" || reason === "SMA50+ATR") return "#f85149";
    if (reason === "PCT_TRAIL") return "#f0883e";
    if (reason === "REBALANCE") return "#58a6ff";
    return "#8b949e";
  };

  const exitModeLabel = (mode, pct) => {
    if (mode === "SMA50")     return "Exit: Close below SMA50";
    if (mode === "ATR_TRAIL") return "Exit: 2× ATR(20) trailing stop";
    if (mode === "PCT_TRAIL") return `Exit: ${pct}% trailing stop from peak`;
    if (mode === "BOTH")      return "Exit: SMA50 or ATR(20) trailing stop (first hit)";
    return mode;
  };

  // ── CSS for three-dot pulse animation ──
  const runnerStyle = `
    @keyframes pf-dot-pulse {
      0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
      40%            { transform: scale(1.0); opacity: 1.0; }
    }
    .pf-spinner {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      vertical-align: middle;
    }
    .pf-spinner span {
      display: inline-block;
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: #58a6ff;
      animation: pf-dot-pulse 1.2s ease-in-out infinite;
    }
    .pf-spinner span:nth-child(2) { animation-delay: 0.2s; }
    .pf-spinner span:nth-child(3) { animation-delay: 0.4s; }
  `;

  // ── Backtest results panel (shared between Screen BT button & Backtest mode) ──
  const BacktestPanel = () => !btTicker ? null : (
    <div style={{ background: "#161b22", border: "1px solid #30363d", borderRadius: 8, padding: 16, marginBottom: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14, flexWrap: "wrap", gap: 8 }}>
        <h3 style={{ margin: 0 }}>Backtest — {btTicker}</h3>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <select value={btPeriod} onChange={e => setBtPeriod(Number(e.target.value))} style={selectStyle}>
            <option value={365}>1 year</option>
            <option value={730}>2 years</option>
            <option value={1095}>3 years</option>
            <option value={1825}>5 years</option>
          </select>
          <select value={btExitMode} onChange={e => setBtExitMode(e.target.value)} style={selectStyle}>
            <option value="BOTH">SMA50 + ATR Stop</option>
            <option value="SMA50">SMA50 only</option>
            <option value="ATR_TRAIL">ATR Stop only</option>
            <option value="PCT_TRAIL">Trailing Stop (%)</option>
          </select>
          {btExitMode === "PCT_TRAIL" && (
            <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <input
                type="number"
                min={1} max={50} step={1}
                value={btTrailPct}
                onChange={e => setBtTrailPct(Number(e.target.value))}
                style={{ ...selectStyle, width: 54, textAlign: "center" }}
              />
              <span style={{ color: "#8b949e", fontSize: 13 }}>%</span>
            </div>
          )}
          <button
            onClick={() => startBacktest(btTicker, btPeriod, btExitMode, btTrailPct)}
            disabled={btLoading}
            style={{
              padding: "4px 12px", borderRadius: 6, border: "none",
              background: btLoading ? "#388bfd88" : "#1f6feb", color: "#fff",
              fontWeight: 700, fontSize: 13, cursor: btLoading ? "not-allowed" : "pointer",
            }}
          >
            {btLoading ? "Running…" : "Re-run"}
          </button>
          <button onClick={() => setBtTicker(null)} style={{ background: "none", border: "none", color: "#8b949e", cursor: "pointer", fontSize: 18 }}>×</button>
        </div>
      </div>

      {btLoading && <p style={{ color: "#8b949e" }}>Running backtest…</p>}
      {btError && !btLoading && (
        <p style={{ color: "#f85149", fontSize: 13 }}>Error: {btError}</p>
      )}

      {btData && !btLoading && (
        <>
          <div style={{ marginBottom: 12, padding: "6px 10px", background: "#0d1117", borderRadius: 6, border: "1px solid #21262d", fontSize: 12, color: "#58a6ff" }}>
            {exitModeLabel(btData.exit_mode, btTrailPct)}
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 16 }}>
            <MetricCard label="Total Return" value={fmtPct(btData.total_return_pct)} color={pctColor(btData.total_return_pct)} />
            <MetricCard label="B&H Return"   value={fmtPct(btData.bh_return_pct)}    color={pctColor(btData.bh_return_pct)} />
            <MetricCard label="Alpha"        value={fmtPct(btData.total_return_pct - btData.bh_return_pct)} color={pctColor(btData.total_return_pct - btData.bh_return_pct)} />
            <MetricCard label="Max Drawdown" value={`${btData.max_drawdown_pct.toFixed(1)}%`} color={btData.max_drawdown_pct < -20 ? "#f85149" : btData.max_drawdown_pct < -10 ? "#e3b341" : "#8b949e"} />
            <MetricCard label="Win Rate"     value={`${btData.win_rate_pct.toFixed(1)}%`}    color={btData.win_rate_pct >= 50 ? "#56d364" : "#f85149"} />
            <MetricCard label="Sharpe"       value={btData.sharpe_ratio.toFixed(2)}           color={btData.sharpe_ratio >= 1 ? "#56d364" : btData.sharpe_ratio >= 0 ? "#e3b341" : "#f85149"} />
            <MetricCard label="Trades"       value={btData.n_trades} />
            <MetricCard label="Avg Trade"    value={fmtPct(btData.avg_trade_pnl_pct)} color={pctColor(btData.avg_trade_pnl_pct)} />
          </div>

          {/* Candlestick chart with entry (B) / exit (S) markers */}
          {btChartData && btChartData.length > 0 && (() => {
            const markers = btData.trades.flatMap(t => [
              { date: t.entry_date, type: "entry", pnl: t.pnl_pct },
              { date: t.exit_date,  type: "exit",  pnl: t.pnl_pct },
            ]);
            return (
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 11, color: "#8b949e", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>
                  Price Chart — <span style={{ color: "#58a6ff" }}>B</span> entry &nbsp;
                  <span style={{ color: "#56d364" }}>S</span> exit (win) &nbsp;
                  <span style={{ color: "#f85149" }}>S</span> exit (loss)
                </div>
                <CandlestickChart data={btChartData} markers={markers} showVolume trimStart={50} />
              </div>
            );
          })()}

          {btData.trades.length === 0 ? (
            <p style={{ color: "#8b949e", fontSize: 13 }}>No trades triggered in this period.</p>
          ) : (() => {
            const btExitReasons = ["ALL", ...Array.from(new Set(btData.trades.map(t => t.exit_reason))).sort()];
            const btFiltered = btData.trades.filter(t =>
              btExitReasonFilter === "ALL" || t.exit_reason === btExitReasonFilter
            );
            return (
            <div style={{ background: "#161b22", border: "1px solid #30363d", borderRadius: 8, overflow: "hidden" }}>
              <div style={{ display: "flex", gap: 8, alignItems: "center", padding: "10px 12px 8px", flexWrap: "wrap", borderBottom: "1px solid #21262d" }}>
                <span style={{ fontSize: 11, color: "#8b949e", textTransform: "uppercase", letterSpacing: "0.08em" }}>
                  Trade Log ({btFiltered.length}/{btData.trades.length})
                </span>
                <select value={btExitReasonFilter} onChange={e => setBtExitReasonFilter(e.target.value)} style={{ ...selectStyle, fontSize: 12, padding: "3px 8px" }}>
                  {btExitReasons.map(r => <option key={r} value={r}>{r === "ALL" ? "All exits" : r}</option>)}
                </select>
                {btExitReasonFilter !== "ALL" && (
                  <button onClick={() => setBtExitReasonFilter("ALL")}
                    style={{ fontSize: 11, padding: "2px 8px", borderRadius: 4, border: "1px solid #30363d", background: "transparent", color: "#8b949e", cursor: "pointer" }}>
                    Clear
                  </button>
                )}
              </div>
              <div style={{ overflowX: "auto", overflowY: "auto", maxHeight: 693 }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr>
                    {["#", "Entry Date", "Exit Date", "Entry $", "Exit $", "PnL %", "Days", "Exit Reason"].map(h => (
                      <th key={h} style={{ ...th, fontSize: 10, position: "sticky", top: 0, zIndex: 1, background: "#161b22" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {btFiltered.map((t, i) => (
                    <tr key={i} style={{ background: t.pnl_pct > 0 ? "#0d2b0d" : t.pnl_pct < 0 ? "#2d1b1b" : "transparent" }}>
                      <td style={td}>{i + 1}</td>
                      <td style={{ ...td, color: "#8b949e" }}>{t.entry_date}</td>
                      <td style={{ ...td, color: "#8b949e" }}>{t.exit_date}</td>
                      <td style={td}>${t.entry_price.toFixed(2)}</td>
                      <td style={td}>${t.exit_price.toFixed(2)}</td>
                      <td style={{ ...td, fontWeight: 700, color: pctColor(t.pnl_pct) }}>{fmtPct(t.pnl_pct)}</td>
                      <td style={{ ...td, color: "#8b949e" }}>{t.days_held}d</td>
                      <td style={td}>
                        <span style={{
                          padding: "2px 6px", borderRadius: 4, fontSize: 11, fontWeight: 700,
                          color: exitColor(t.exit_reason),
                          background: exitColor(t.exit_reason) + "22",
                          border: `1px solid ${exitColor(t.exit_reason)}55`,
                        }}>
                          {t.exit_reason}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            </div>
            );
          })()}
        </>
      )}

      {!btData && !btLoading && (
        <p style={{ color: "#f85149", fontSize: 13 }}>Failed to load backtest data.</p>
      )}
    </div>
  );

  return (
    <div>
      <style>{runnerStyle}</style>
      {/* Page header + mode tabs */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20, flexWrap: "wrap", gap: 12 }}>
        <div>
          <h2 style={{ marginBottom: 4 }}>Daniel's Breakout Screen</h2>
          <p style={{ color: "#8b949e", fontSize: 13, margin: 0 }}>
            EMA momentum stack + volume surge breakout to a new 6-month high
          </p>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          <ModeTab active={mode === "screen"}    onClick={() => setMode("screen")}>Screen</ModeTab>
          <ModeTab active={mode === "backtest"}  onClick={() => setMode("backtest")}>Backtest</ModeTab>
          <ModeTab active={mode === "portfolio"} onClick={() => setMode("portfolio")}>Portfolio BT</ModeTab>
        </div>
      </div>

      {/* ── SCREEN MODE ──────────────────────────────────────────────────── */}
      {mode === "screen" && (
        <>
          {/* Universe selector */}
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 11, color: "#8b949e", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>
              Universe
            </div>
            <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
              {UNIVERSES.map(u => (
                <TabBtn key={u.id} active={universe === u.id} onClick={() => setUniverse(u.id)}>
                  {u.label}
                  <span style={{ marginLeft: 5, fontSize: 11, color: universe === u.id ? "#58a6ff88" : "#666" }}>
                    {u.size}
                  </span>
                </TabBtn>
              ))}
            </div>
          </div>

          {/* Controls */}
          <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", marginBottom: 20 }}>
            <label style={{ fontSize: 13, color: "#8b949e", display: "flex", alignItems: "center", gap: 8 }}>
              Min criteria:
              <select value={minCriteria} onChange={e => setMinCriteria(Number(e.target.value))} style={selectStyle}>
                <option value={6}>6/6 — strict pass</option>
                <option value={5}>5+ criteria</option>
                <option value={4}>4+ criteria</option>
                <option value={3}>3+ criteria</option>
              </select>
            </label>
            <label style={{ fontSize: 13, color: "#8b949e", display: "flex", alignItems: "center", gap: 8 }}>
              Max tickers:
              <select value={maxTickers} onChange={e => setMaxTickers(Number(e.target.value))} style={selectStyle}>
                <option value={50}>50 (fast)</option>
                <option value={200}>200</option>
                <option value={500}>500</option>
                <option value={1000}>1000</option>
                <option value={3000}>All ({selectedUniverse?.size})</option>
              </select>
            </label>
            <button
              onClick={run}
              disabled={loading}
              style={{
                padding: "6px 18px", borderRadius: 6, border: "none",
                background: loading ? "#388bfd88" : "#238636", color: "#fff",
                fontWeight: 700, fontSize: 14, cursor: loading ? "not-allowed" : "pointer",
              }}
            >
              {loading ? "Scanning…" : "Run Screen"}
            </button>
            {loading && <span style={{ fontSize: 12, color: "#8b949e" }}>Fetching 200 days of history + computing EMAs…</span>}
          </div>

          {error && (
            <div style={{ color: "#f85149", background: "#2d1b1b", border: "1px solid #f85149", borderRadius: 6, padding: 12, marginBottom: 16 }}>
              {error}
            </div>
          )}

          {response && (
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, flexWrap: "wrap", gap: 8 }}>
              <div style={{ fontSize: 13, color: "#8b949e" }}>
                <strong style={{ color: "#e6edf3" }}>{selectedUniverse?.label}</strong>
                {" — "}Screened <strong style={{ color: "#e6edf3" }}>{response.total_screened}</strong> tickers,{" "}
                <strong style={{ color: "#56d364" }}>{response.matches}</strong> full pass{response.matches !== 1 ? "es" : ""},{" "}
                <strong style={{ color: "#e3b341" }}>{visibleResults.length}</strong> shown
              </div>
              {visibleResults.length > 0 && (
                <>
                  <button onClick={() => exportCsv(visibleResults, DANIELS_FIELDS, DANIELS_HEADERS, `daniels-screen-${today()}.csv`)} style={{ padding: "3px 10px", borderRadius: 6, border: "1px solid #30363d", background: "#21262d", color: "#8b949e", fontSize: 12, cursor: "pointer", fontWeight: 600 }}>
                    ↓ CSV
                  </button>
                  <button onClick={() => { navigator.clipboard.writeText(visibleResults.map(r => r.ticker).join(",")); setTickersCopied(true); setTimeout(() => setTickersCopied(false), 2000); }} style={{ padding: "3px 10px", borderRadius: 6, border: "1px solid #30363d", background: "#21262d", color: tickersCopied ? "#56d364" : "#8b949e", fontSize: 12, cursor: "pointer", fontWeight: 600 }}>
                    {tickersCopied ? "✓ Copied" : "↓ Tickers"}
                  </button>
                </>
              )}
            </div>
          )}

          {response && response.results.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 12 }}>
              <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                <span style={{ fontSize: 11, color: "#8b949e", textTransform: "uppercase", letterSpacing: "0.05em", minWidth: 60 }}>Rel Vol:</span>
                {REL_VOL_FILTERS.map(f => (
                  <FilterChip key={f.id} label={f.label} active={viewRelVol === f.id} color={f.color} onClick={() => setViewRelVol(f.id)} />
                ))}
              </div>
              <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                <span style={{ fontSize: 11, color: "#8b949e", textTransform: "uppercase", letterSpacing: "0.05em", minWidth: 60 }}>Rating:</span>
                {RATING_FILTERS.map(f => (
                  <FilterChip key={f.id} label={f.label} active={viewRating === f.id} color={f.color} onClick={() => setViewRating(f.id)} />
                ))}
                {(viewRating !== "ALL" || viewRelVol !== "ALL") && (
                  <button onClick={() => { setViewRating("ALL"); setViewRelVol("ALL"); }} style={{ background: "none", border: "none", color: "#58a6ff", fontSize: 12, cursor: "pointer", padding: 0 }}>
                    Clear
                  </button>
                )}
              </div>
            </div>
          )}

          {/* Criteria legend */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 16px", marginBottom: 20, padding: "10px 14px", background: "#161b22", border: "1px solid #21262d", borderRadius: 8, fontSize: 12, color: "#8b949e" }}>
            {CRITERIA_LABELS.map((c, i) => (
              <span key={c.key}><strong style={{ color: "#58a6ff" }}>C{i + 1}</strong> {c.label}</span>
            ))}
          </div>

          {/* Chart panel */}
          {selectedTicker && (
            <div style={{ background: "#161b22", border: "1px solid #30363d", borderRadius: 8, padding: 16, marginBottom: 20 }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 10 }}>
                <h3 style={{ margin: 0 }}>{selectedTicker}</h3>
                <button onClick={() => setSelectedTicker(null)} style={{ background: "none", border: "none", color: "#8b949e", cursor: "pointer", fontSize: 18 }}>×</button>
              </div>
              {chartLoading ? <p style={{ color: "#8b949e" }}>Loading chart…</p> : <CandlestickChart data={chartData} showVolume trimStart={50} />}
            </div>
          )}

          {/* Backtest panel (triggered from BT button in results table) */}
          <BacktestPanel />

          {/* Results table */}
          {response && visibleResults.length > 0 && (
            <div style={{ background: "#161b22", border: "1px solid #30363d", borderRadius: 8, overflow: "hidden" }}>
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr>
                      {["Ticker", "Chg %", "Rel Vol", "Vol", "Mkt Cap", "EPS", "Sector", "Rating", "Met", "Close", "EMA21", "EMA50", "EMA100", "6m High", "Avg Vol 10d", "BT"].map(h => (
                        <th key={h} style={th}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {visibleResults.map(r => (
                      <tr
                        key={r.ticker}
                        onClick={() => selectTicker(r.ticker)}
                        style={{ cursor: "pointer", background: selectedTicker === r.ticker ? "#0d2b0d" : "transparent" }}
                        onMouseEnter={e => { if (selectedTicker !== r.ticker) e.currentTarget.style.background = "#161b22"; }}
                        onMouseLeave={e => { if (selectedTicker !== r.ticker) e.currentTarget.style.background = "transparent"; }}
                      >
                        <TickerCell ticker={r.ticker} name={r.name} passes={r.passes} tdStyle={td} />
                        <td style={td}><PriceChangePct pct={r.price_change_pct} /></td>
                        <td style={td}><RelVolBadge rv={r.rel_vol ?? r.rel_volume} /></td>
                        <td style={{ ...td, fontSize: 12, color: "#8b949e" }}>{fmtVol(r.today_vol)}</td>
                        <td style={{ ...td, fontSize: 12, color: "#8b949e" }}>{fmtMarketCap(r.market_cap)}</td>
                        <td style={{ ...td, fontSize: 12, color: "#8b949e" }}>{r.eps != null ? r.eps.toFixed(2) : "—"}</td>
                        <td style={{ ...td, fontSize: 12, color: "#8b949e" }}>{r.sector ?? "—"}</td>
                        <td style={td}><AnalystBadge rating={r.analyst_rating} /></td>
                        <td style={td}><CriteriaBadge met={r.criteria_met} /></td>
                        <td style={td}>${r.last_close.toFixed(2)}</td>
                        <td style={{ ...td, color: r.c1 ? "#56d364" : "#8b949e" }}>${r.ema21.toFixed(2)}</td>
                        <td style={{ ...td, color: r.c2 ? "#56d364" : "#8b949e" }}>${r.ema50.toFixed(2)}</td>
                        <td style={{ ...td, color: r.c3 ? "#56d364" : "#8b949e" }}>${r.ema100.toFixed(2)}</td>
                        <td style={{ ...td, color: r.c4 ? "#56d364" : "#e3b341" }}>${r.high_6m.toFixed(2)}</td>
                        <td style={{ ...td, color: r.c6 ? "#56d364" : "#f85149", fontSize: 12 }}>{fmtVol(r.avg_vol_10d)}</td>
                        <td style={{ ...td, textAlign: "center" }}>
                          <button
                            onClick={e => { e.stopPropagation(); startBacktest(r.ticker, btPeriod, btExitMode, btTrailPct); }}
                            title={`Backtest ${r.ticker}`}
                            style={{
                              padding: "3px 8px", borderRadius: 5, border: "1px solid #30363d",
                              background: btTicker === r.ticker ? "#1f3a5f" : "#21262d",
                              color: btTicker === r.ticker ? "#58a6ff" : "#8b949e",
                              cursor: "pointer", fontSize: 12, fontWeight: 700,
                            }}
                          >
                            BT
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {response && visibleResults.length === 0 && (
            <div style={{ background: "#161b22", border: "1px solid #30363d", borderRadius: 8, padding: 24, textAlign: "center", color: "#8b949e" }}>
              No stocks met {minCriteria}/6 criteria in this batch.{minCriteria === 6 && " Try lowering the minimum criteria or increasing the ticker count."}
            </div>
          )}
        </>
      )}

      {/* ── BACKTEST MODE ────────────────────────────────────────────────── */}
      {mode === "backtest" && (
        <>
          {/* Ticker input + controls */}
          <div style={{ background: "#161b22", border: "1px solid #30363d", borderRadius: 8, padding: 16, marginBottom: 20 }}>
            <div style={{ fontSize: 11, color: "#8b949e", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 10 }}>
              Backtest Daniel's Strategy on Any Ticker
            </div>
            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
              <input
                value={btTickerInput}
                onChange={e => setBtTickerInput(e.target.value.toUpperCase())}
                onKeyDown={e => { if (e.key === "Enter" && btTickerInput.trim()) startBacktest(btTickerInput.trim(), btPeriod, btExitMode, btTrailPct); }}
                placeholder="Ticker (e.g. AAPL)"
                style={{
                  background: "#0d1117", color: "#e6edf3", border: "1px solid #30363d",
                  borderRadius: 6, padding: "6px 10px", fontSize: 14, width: 140,
                  fontFamily: "inherit",
                }}
              />
              <select value={btPeriod} onChange={e => setBtPeriod(Number(e.target.value))} style={selectStyle}>
                <option value={365}>1 year</option>
                <option value={730}>2 years</option>
                <option value={1095}>3 years</option>
                <option value={1825}>5 years</option>
              </select>
              <select value={btExitMode} onChange={e => setBtExitMode(e.target.value)} style={selectStyle}>
                <option value="BOTH">SMA50 + ATR Stop</option>
                <option value="SMA50">SMA50 only</option>
                <option value="ATR_TRAIL">ATR Stop only</option>
                <option value="PCT_TRAIL">Trailing Stop (%)</option>
              </select>
              {btExitMode === "PCT_TRAIL" && (
                <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                  <input
                    type="number"
                    min={1} max={50} step={1}
                    value={btTrailPct}
                    onChange={e => setBtTrailPct(Number(e.target.value))}
                    style={{ ...selectStyle, width: 54, textAlign: "center" }}
                  />
                  <span style={{ color: "#8b949e", fontSize: 13 }}>%</span>
                </div>
              )}
              <button
                onClick={() => { if (btTickerInput.trim()) startBacktest(btTickerInput.trim(), btPeriod, btExitMode, btTrailPct); }}
                disabled={btLoading || !btTickerInput.trim()}
                style={{
                  padding: "6px 18px", borderRadius: 6, border: "none",
                  background: (btLoading || !btTickerInput.trim()) ? "#388bfd88" : "#238636", color: "#fff",
                  fontWeight: 700, fontSize: 14, cursor: (btLoading || !btTickerInput.trim()) ? "not-allowed" : "pointer",
                }}
              >
                {btLoading ? "Running…" : "Run Backtest"}
              </button>
            </div>
          </div>

          {/* Reuse the same backtest results panel */}
          <BacktestPanel />
        </>
      )}

      {/* ── PORTFOLIO BACKTEST MODE ───────────────────────────────────────── */}
      {mode === "portfolio" && (
        <>
          {/* Recommendation notes */}
          {pfUniverse === "sp500" && (
            <div style={{ background: "#0d2b0d", border: "1px solid #2ea04366", borderRadius: 8, padding: "10px 14px", marginBottom: 14, fontSize: 13, color: "#7ee787", display: "flex", alignItems: "flex-start", gap: 10 }}>
              <span style={{ fontSize: 16, lineHeight: 1 }}>💡</span>
              <span>
                <strong>S&P 500 recommended settings:</strong> Trailing Stop 25% · Max Positions 9 · Rank by Rel Strength 20d · Rebalance Quarterly
                <button onClick={() => { setPfExitMode("PCT_TRAIL"); setPfTrailPct(25); setPfMaxPos(9); setPfRankBy("RS_20"); setPfRebalance("QUARTERLY"); }}
                  style={{ marginLeft: 12, padding: "2px 10px", borderRadius: 5, border: "1px solid #2ea04366", background: "#238636", color: "#fff", fontSize: 12, fontWeight: 700, cursor: "pointer" }}>
                  Apply
                </button>
              </span>
            </div>
          )}
          {pfUniverse === "nasdaq100" && (
            <div style={{ background: "#0d1f3c", border: "1px solid #388bfd66", borderRadius: 8, padding: "10px 14px", marginBottom: 14, fontSize: 13, color: "#79c0ff", display: "flex", alignItems: "flex-start", gap: 10 }}>
              <span style={{ fontSize: 16, lineHeight: 1 }}>💡</span>
              <span>
                <strong>NASDAQ 100 recommended settings:</strong> Trailing Stop 24% · Max Positions 2 · Rebalance Quarterly
                <button onClick={() => { setPfExitMode("PCT_TRAIL"); setPfTrailPct(24); setPfMaxPos(2); setPfRebalance("QUARTERLY"); }}
                  style={{ marginLeft: 12, padding: "2px 10px", borderRadius: 5, border: "1px solid #388bfd66", background: "#1f6feb", color: "#fff", fontSize: 12, fontWeight: 700, cursor: "pointer" }}>
                  Apply
                </button>
              </span>
            </div>
          )}
          {pfUniverse === "russell2000" && (
            <div style={{ background: "#2d1f0d", border: "1px solid #f0883e66", borderRadius: 8, padding: "10px 14px", marginBottom: 14, fontSize: 13, color: "#f0883e", display: "flex", alignItems: "flex-start", gap: 10 }}>
              <span style={{ fontSize: 16, lineHeight: 1 }}>💡</span>
              <span>
                <strong>Russell 2000 recommended settings:</strong> Trailing Stop 30% · Max Positions 10 · Rebalance Quarterly
                <button onClick={() => { setPfExitMode("PCT_TRAIL"); setPfTrailPct(30); setPfMaxPos(10); setPfRebalance("QUARTERLY"); }}
                  style={{ marginLeft: 12, padding: "2px 10px", borderRadius: 5, border: "1px solid #f0883e66", background: "#b94c00", color: "#fff", fontSize: 12, fontWeight: 700, cursor: "pointer" }}>
                  Apply
                </button>
              </span>
            </div>
          )}

          {/* Config panel */}
          <div style={{ background: "#161b22", border: "1px solid #30363d", borderRadius: 8, padding: 16, marginBottom: 20 }}>
            <div style={{ fontSize: 11, color: "#8b949e", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 10 }}>
              Portfolio Backtest — up to {pfMaxPos} positions · ranked by rel vol
            </div>
            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginBottom: 10 }}>
              <select value={pfUniverse} onChange={e => setPfUniverse(e.target.value)} style={selectStyle}>
                <option value="sp500">S&amp;P 500 (~500)</option>
                <option value="nasdaq100">NASDAQ 100 (~100)</option>
                <option value="russell2000">Russell 2000 (~2000)</option>
              </select>
              <select value={pfStartDate ? "" : pfPeriod} onChange={e => { setPfPeriod(Number(e.target.value)); setPfStartDate(""); setPfEndDate(""); }} style={{ ...selectStyle, opacity: pfStartDate ? 0.4 : 1 }}>
                <option value="" disabled>Duration</option>
                <option value={365}>1 year</option>
                <option value={730}>2 years</option>
                <option value={1095}>3 years</option>
                <option value={1825}>5 years</option>
                <option value={2555}>7 years</option>
                <option value={3650}>10 years</option>
                <option value={5475}>15 years</option>
                <option value={7300}>20 years</option>
              </select>
              <label style={{ fontSize: 12, color: "#8b949e", display: "flex", alignItems: "center", gap: 5 }}>
                Start
                <input
                  type="date"
                  value={pfStartDate}
                  max={pfEndDate || new Date(Date.now() - 86400000 * 365).toISOString().slice(0, 10)}
                  onChange={e => setPfStartDate(e.target.value)}
                  style={{ ...selectStyle, width: 135 }}
                />
              </label>
              <label style={{ fontSize: 12, color: "#8b949e", display: "flex", alignItems: "center", gap: 5 }}>
                End
                <input
                  type="date"
                  value={pfEndDate}
                  min={pfStartDate || undefined}
                  max={new Date().toISOString().slice(0, 10)}
                  onChange={e => setPfEndDate(e.target.value)}
                  style={{ ...selectStyle, width: 135 }}
                />
              </label>
              <select value={pfExitMode} onChange={e => setPfExitMode(e.target.value)} style={selectStyle}>
                <option value="BOTH">SMA50 + ATR Stop</option>
                <option value="SMA50">SMA50 only</option>
                <option value="ATR_TRAIL">ATR Stop only</option>
                <option value="PCT_TRAIL">Trailing Stop (%)</option>
              </select>
              {pfExitMode === "PCT_TRAIL" && (
                <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                  <input
                    type="number" min={1} max={50} step={1}
                    value={pfTrailPct}
                    onChange={e => setPfTrailPct(Number(e.target.value))}
                    style={{ ...selectStyle, width: 54, textAlign: "center" }}
                  />
                  <span style={{ color: "#8b949e", fontSize: 13 }}>%</span>
                </div>
              )}
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ color: "#8b949e", fontSize: 13 }}>Max positions:</span>
                <input
                  type="number" min={1} max={50} step={1}
                  value={pfMaxPos}
                  onChange={e => setPfMaxPos(Number(e.target.value))}
                  style={{ ...selectStyle, width: 54, textAlign: "center" }}
                />
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ color: "#8b949e", fontSize: 13 }}>Rank by:</span>
                <select value={pfRankBy} onChange={e => setPfRankBy(e.target.value)} style={selectStyle}>
                  <option value="REL_VOL">Rel Vol</option>
                  <option value="RS_20">Rel Strength 20d</option>
                  <option value="RS_63">Rel Strength 63d</option>
                  <option value="RS_126">Rel Strength 126d</option>
                  <option value="RS_VOL">Rel Strength × Rel Vol</option>
                </select>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ color: "#8b949e", fontSize: 13 }}>Rebalance:</span>
                <select value={pfRebalance} onChange={e => setPfRebalance(e.target.value)} style={selectStyle}>
                  <option value="NONE">None (hold until stop)</option>
                  <option value="DAILY">Daily</option>
                  <option value="WEEKLY">Weekly</option>
                  <option value="MONTHLY">Monthly</option>
                  <option value="QUARTERLY">Quarterly</option>
                </select>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ color: "#8b949e", fontSize: 13 }}>Starting $:</span>
                <input
                  type="number" min={1000} step={1000}
                  value={pfCapital}
                  onChange={e => setPfCapital(Number(e.target.value))}
                  style={{ ...selectStyle, width: 110, textAlign: "right" }}
                />
              </div>
              <button
                onClick={runPortfolioBacktest}
                disabled={pfLoading}
                style={{
                  padding: "6px 18px", borderRadius: 6, border: "none",
                  background: pfLoading ? "#388bfd88" : "#238636", color: "#fff",
                  fontWeight: 700, fontSize: 14, cursor: pfLoading ? "not-allowed" : "pointer",
                }}
              >
                Run Portfolio Backtest
              </button>
              {pfLoading && <span className="pf-spinner"><span/><span/><span/></span>}
            </div>
            <div style={{ fontSize: 12, color: "#8b949e" }}>
              Screens all ~500 S&amp;P 500 stocks daily · equal-weight sizing · benchmark: SPY B&amp;H
              {" · "}⚠ First run fetches ~500 tickers and may take 30–60 seconds
            </div>
          </div>

          {pfError && <p style={{ color: "#f85149", fontSize: 13, marginBottom: 16 }}>Error: {pfError}</p>}

          {pfData && !pfLoading && (
            <>
              {/* Exit criteria label */}
              <div style={{ marginBottom: 12, padding: "6px 10px", background: "#0d1117", borderRadius: 6, border: "1px solid #21262d", fontSize: 12, color: "#58a6ff" }}>
                {exitModeLabel(pfData.exit_mode, pfTrailPct)}
                {" · "}Max {pfData.max_positions} positions · avg {pfData.avg_positions} held · {pfData.n_bars} trading bars
                {" · "}Ranked by {{"REL_VOL":"Rel Vol","RS_20":"Rel Strength 20d","RS_63":"Rel Strength 63d","RS_126":"Rel Strength 126d","RS_VOL":"Rel Strength × Rel Vol"}[pfRankBy] || pfRankBy}
                {pfRebalance !== "NONE" && ` · Rebalance: ${pfRebalance.charAt(0).toUpperCase() + pfRebalance.slice(1).toLowerCase()}`}
                {pfData.equity_curve.length > 0 && (
                  <span style={{ color: "#8b949e" }}>
                    {" · "}
                    {pfData.equity_curve[0].date}
                    {" → "}
                    {pfData.equity_curve[pfData.equity_curve.length - 1].date}
                  </span>
                )}
              </div>

              {/* Metric cards */}
              {(() => {
                // Compute max drawdown dollar amounts from the curves
                let maxDdDollar = 0, bhMaxDdDollar = 0;
                if (pfData.equity_curve.length > 1) {
                  let peak = pfData.equity_curve[0].value;
                  for (const { value } of pfData.equity_curve) {
                    if (value > peak) peak = value;
                    const dd = value - peak;
                    if (dd < maxDdDollar) maxDdDollar = dd;
                  }
                }
                if (pfData.bh_curve.length > 1) {
                  let peak = pfData.bh_curve[0].value;
                  for (const { value } of pfData.bh_curve) {
                    if (value > peak) peak = value;
                    const dd = value - peak;
                    if (dd < bhMaxDdDollar) bhMaxDdDollar = dd;
                  }
                }
                const ddColor = pct => pct < -20 ? "#f85149" : pct < -10 ? "#e3b341" : "#8b949e";
                return (
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 16 }}>
                <MetricCard label="Starting Capital" value={fmtDollars(pfData.initial_capital)} />
                <MetricCard label="Final Value"      value={fmtDollars(pfData.final_value)}      color={pctColor(pfData.dollar_gain)} />
                <MetricCard label="Dollar Gain"      value={(pfData.dollar_gain >= 0 ? "+" : "") + fmtDollars(pfData.dollar_gain)} color={pctColor(pfData.dollar_gain)} />
                <MetricCard label="Total Return"     value={fmtPct(pfData.total_return_pct)}     color={pctColor(pfData.total_return_pct)} />
                <MetricCard label="CAGR"             value={fmtPct(pfData.cagr)}                 color={pctColor(pfData.cagr)} />
                <MetricCard label={`${pfData.benchmark_ticker} B&H`} value={fmtPct(pfData.bh_return_pct)} color={pctColor(pfData.bh_return_pct)} />
                <MetricCard label={`${pfData.benchmark_ticker} Final`} value={fmtDollars(pfData.bh_curve.length > 0 ? pfData.bh_curve[pfData.bh_curve.length - 1].value : 0)} color={pctColor(pfData.bh_return_pct)} />
                <MetricCard label={`${pfData.benchmark_ticker} CAGR`} value={fmtPct(pfData.bh_cagr)}     color={pctColor(pfData.bh_cagr)} />
                <MetricCard label="Alpha"            value={fmtPct(pfData.total_return_pct - pfData.bh_return_pct)} color={pctColor(pfData.total_return_pct - pfData.bh_return_pct)} />
                <MetricCard label="Max Drawdown"     value={`${pfData.max_drawdown_pct.toFixed(1)}%`} color={ddColor(pfData.max_drawdown_pct)} />
                <MetricCard label="Max DD ($)"       value={fmtDollars(maxDdDollar)}              color={ddColor(pfData.max_drawdown_pct)} />
                <MetricCard label={`${pfData.benchmark_ticker} Max DD`} value={`${pfData.bh_max_drawdown_pct.toFixed(1)}%`} color={ddColor(pfData.bh_max_drawdown_pct)} />
                <MetricCard label={`${pfData.benchmark_ticker} Max DD ($)`} value={fmtDollars(bhMaxDdDollar)} color={ddColor(pfData.bh_max_drawdown_pct)} />
                <MetricCard label="Win Rate"         value={`${pfData.win_rate_pct.toFixed(1)}%`}     color={pfData.win_rate_pct >= 50 ? "#56d364" : "#f85149"} />
                <MetricCard label="Avg Win"          value={fmtPct(pfData.avg_win_pct)}               color="#56d364" />
                <MetricCard label="Avg Loss"         value={fmtPct(pfData.avg_loss_pct)}              color="#f85149" />
                <MetricCard label="Sharpe"           value={pfData.sharpe_ratio.toFixed(2)}            color={pfData.sharpe_ratio >= 1 ? "#56d364" : pfData.sharpe_ratio >= 0 ? "#e3b341" : "#f85149"} />
                <MetricCard label="Trades"           value={pfData.n_trades} />
                <MetricCard label="Avg Trade"        value={fmtPct(pfData.avg_trade_pnl_pct)}   color={pctColor(pfData.avg_trade_pnl_pct)} />
              </div>
                );
              })()}

              {/* Portfolio equity curve */}
              <div style={{ background: "#161b22", border: "1px solid #30363d", borderRadius: 8, padding: 16, marginBottom: 16 }}>
                <div style={{ fontSize: 12, color: "#8b949e", marginBottom: 8 }}>Portfolio equity curve vs {pfData.benchmark_ticker} B&amp;H</div>
                <EquityChart data={pfData.equity_curve} bhReturnPct={pfData.bh_return_pct} bhCurve={pfData.bh_curve} height={240} />
              </div>

              {/* Exit reason breakdown */}
              {pfData.trades.length > 0 && (() => {
                const EXIT_COLORS = {
                  SMA50:      "#e3b341",
                  ATR_STOP:   "#f85149",
                  "SMA50+ATR":"#f85149",
                  PCT_TRAIL:  "#f0883e",
                  REBALANCE:  "#58a6ff",
                  END:        "#8b949e",
                };
                const counts = {};
                pfData.trades.forEach(t => { counts[t.exit_reason] = (counts[t.exit_reason] || 0) + 1; });
                const total  = pfData.trades.length;
                const rows   = Object.entries(counts).sort((a, b) => b[1] - a[1]);

                // Donut geometry
                const R = 54, r = 34, cx = 70, cy = 70;
                let cumAngle = -Math.PI / 2;
                const slices = rows.map(([reason, count]) => {
                  const angle  = (count / total) * 2 * Math.PI;
                  const start  = cumAngle;
                  cumAngle    += angle;
                  const x1 = cx + R * Math.cos(start),  y1 = cy + R * Math.sin(start);
                  const x2 = cx + R * Math.cos(cumAngle), y2 = cy + R * Math.sin(cumAngle);
                  const ix1= cx + r * Math.cos(start),  iy1= cy + r * Math.sin(start);
                  const ix2= cx + r * Math.cos(cumAngle),iy2= cy + r * Math.sin(cumAngle);
                  const large = angle > Math.PI ? 1 : 0;
                  const d = `M${x1},${y1} A${R},${R} 0 ${large},1 ${x2},${y2} L${ix2},${iy2} A${r},${r} 0 ${large},0 ${ix1},${iy1} Z`;
                  return { reason, count, pct: (count / total * 100).toFixed(1), color: EXIT_COLORS[reason] || "#8b949e", d };
                });

                return (
                  <div style={{ background: "#161b22", border: "1px solid #30363d", borderRadius: 8, padding: 16, marginBottom: 16, display: "flex", gap: 24, flexWrap: "wrap", alignItems: "center" }}>
                    <div>
                      <div style={{ fontSize: 11, color: "#8b949e", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 10 }}>Exit Reason Breakdown</div>
                      <svg width={140} height={140}>
                        {slices.map(s => (
                          <path key={s.reason} d={s.d} fill={s.color} opacity={0.9}>
                            <title>{s.reason}: {s.count} ({s.pct}%)</title>
                          </path>
                        ))}
                        <text x={cx} y={cy - 6} textAnchor="middle" fill="#e6edf3" fontSize={13} fontWeight={700}>{total}</text>
                        <text x={cx} y={cy + 10} textAnchor="middle" fill="#8b949e" fontSize={10}>trades</text>
                      </svg>
                    </div>
                    <div style={{ flex: 1, minWidth: 200 }}>
                      {slices.map(s => (
                        <div key={s.reason} style={{ marginBottom: 8 }}>
                          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 3 }}>
                            <span style={{ color: s.color, fontWeight: 600 }}>{s.reason}</span>
                            <span style={{ color: "#8b949e" }}>{s.count} &nbsp;<strong style={{ color: "#e6edf3" }}>{s.pct}%</strong></span>
                          </div>
                          <div style={{ background: "#21262d", borderRadius: 3, height: 6 }}>
                            <div style={{ width: `${s.pct}%`, background: s.color, borderRadius: 3, height: 6 }} />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })()}

              {/* Trades table */}
              {pfData.trades.length === 0 ? (
                <p style={{ color: "#8b949e", fontSize: 13 }}>No trades triggered in this period.</p>
              ) : (() => {
                const exitReasons = ["ALL", ...Array.from(new Set(pfData.trades.map(t => t.exit_reason))).sort()];
                const filtered = pfData.trades.filter(t => {
                  if (pfTradeFilter.ticker && !t.ticker.toLowerCase().includes(pfTradeFilter.ticker.toLowerCase())) return false;
                  if (pfTradeFilter.exitReason !== "ALL" && t.exit_reason !== pfTradeFilter.exitReason) return false;
                  if (pfTradeFilter.result === "WIN"  && t.pnl_pct <= 0) return false;
                  if (pfTradeFilter.result === "LOSS" && t.pnl_pct >= 0) return false;
                  return true;
                });
                return (
                <div style={{ background: "#161b22", border: "1px solid #30363d", borderRadius: 8, overflow: "hidden" }}>
                  {/* Filter bar */}
                  <div style={{ display: "flex", gap: 8, alignItems: "center", padding: "10px 12px 8px", flexWrap: "wrap", borderBottom: "1px solid #21262d" }}>
                    <span style={{ fontSize: 11, color: "#8b949e", textTransform: "uppercase", letterSpacing: "0.08em" }}>
                      Trade Log ({filtered.length}/{pfData.trades.length})
                    </span>
                    <input
                      type="text"
                      placeholder="Ticker…"
                      value={pfTradeFilter.ticker}
                      onChange={e => setPfTradeFilter(f => ({ ...f, ticker: e.target.value }))}
                      style={{ ...selectStyle, width: 90, fontSize: 12, padding: "3px 8px" }}
                    />
                    <select value={pfTradeFilter.exitReason} onChange={e => setPfTradeFilter(f => ({ ...f, exitReason: e.target.value }))} style={{ ...selectStyle, fontSize: 12, padding: "3px 8px" }}>
                      {exitReasons.map(r => <option key={r} value={r}>{r === "ALL" ? "All exits" : r}</option>)}
                    </select>
                    <select value={pfTradeFilter.result} onChange={e => setPfTradeFilter(f => ({ ...f, result: e.target.value }))} style={{ ...selectStyle, fontSize: 12, padding: "3px 8px" }}>
                      <option value="ALL">Win + Loss</option>
                      <option value="WIN">Winners only</option>
                      <option value="LOSS">Losers only</option>
                    </select>
                    {(pfTradeFilter.ticker || pfTradeFilter.exitReason !== "ALL" || pfTradeFilter.result !== "ALL") && (
                      <button onClick={() => setPfTradeFilter({ ticker: "", exitReason: "ALL", result: "ALL" })}
                        style={{ fontSize: 11, padding: "2px 8px", borderRadius: 4, border: "1px solid #30363d", background: "transparent", color: "#8b949e", cursor: "pointer" }}>
                        Clear
                      </button>
                    )}
                  </div>
                  <div style={{ overflowX: "auto", overflowY: "auto", maxHeight: 693 }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                      <thead>
                        <tr>
                          {["#", "Ticker", "Entry Date", "Exit Date", "Entry $", "Exit $", "PnL %", "Days", "Exit Reason"].map(h => (
                            <th key={h} style={{ ...th, fontSize: 10, position: "sticky", top: 0, zIndex: 1, background: "#161b22" }}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {filtered.map((t, i) => (
                          <tr key={i} style={{ background: t.pnl_pct > 0 ? "#0d2b0d" : t.pnl_pct < 0 ? "#2d1b1b" : "transparent" }}>
                            <td style={td}>{i + 1}</td>
                            <td style={{ ...td, fontWeight: 700, color: "#58a6ff" }}>{t.ticker}</td>
                            <td style={{ ...td, color: "#8b949e" }}>{t.entry_date}</td>
                            <td style={{ ...td, color: "#8b949e" }}>{t.exit_date}</td>
                            <td style={td}>${t.entry_price.toFixed(2)}</td>
                            <td style={td}>${t.exit_price.toFixed(2)}</td>
                            <td style={{ ...td, fontWeight: 700, color: pctColor(t.pnl_pct) }}>{fmtPct(t.pnl_pct)}</td>
                            <td style={{ ...td, color: "#8b949e" }}>{t.days_held}d</td>
                            <td style={td}>
                              <span style={{
                                padding: "2px 6px", borderRadius: 4, fontSize: 11, fontWeight: 700,
                                color: exitColor(t.exit_reason),
                                background: exitColor(t.exit_reason) + "22",
                                border: `1px solid ${exitColor(t.exit_reason)}55`,
                              }}>
                                {t.exit_reason}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
                );
              })()}
            </>
          )}
        </>
      )}
    </div>
  );
}
