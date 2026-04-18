import { useState } from "react";
import { runMinerviniScreen, runMinerviniBacktest, fetchChart } from "../api/screener";
import CandlestickChart from "../components/CandlestickChart";
import { exportCsv, today } from "../utils/exportCsv";

const MINERVINI_FIELDS = ["ticker","name","criteria_met","passes","rs_rating","last_close","ma50","ma150","ma200","ma200_trend","high_52w","low_52w","pct_from_high","pct_from_low","c1","c2","c3","c4","c5","c6","c7","c8","c9","price_change_pct","rel_vol","today_vol","market_cap","eps","sector","analyst_rating"];
const MINERVINI_HEADERS = { ticker:"Ticker", name:"Name", criteria_met:"Criteria Met", passes:"Passes", rs_rating:"RS Rating", last_close:"Close", ma50:"MA50", ma150:"MA150", ma200:"MA200", ma200_trend:"MA200 Trend", high_52w:"52w High", low_52w:"52w Low", pct_from_high:"% From High", pct_from_low:"% From Low", c1:"C1", c2:"C2", c3:"C3", c4:"C4", c5:"C5", c6:"C6", c7:"C7", c8:"C8 (RS)", c9:"C9 (RelVol)", price_change_pct:"Chg %", rel_vol:"Rel Vol", today_vol:"Volume", market_cap:"Mkt Cap", eps:"EPS", sector:"Sector", analyst_rating:"Rating" };
import {
  fmtVol, fmtMarketCap,
  TickerCell, PriceChangePct, RelVolBadge, AnalystBadge,
} from "../components/MetaCells";

const UNIVERSES = [
  { id: "sp500",       label: "S&P 500",      size: "~503" },
  { id: "nasdaq100",   label: "NASDAQ 100",   size: "~101" },
  { id: "russell2000", label: "Russell 2000", size: "~2000" },
];

const CRITERIA_LABELS = [
  { key: "c1", label: "Price > MA150 & MA200" },
  { key: "c2", label: "MA150 > MA200" },
  { key: "c3", label: "MA200 trending up" },
  { key: "c4", label: "MA50 > MA150 & MA200" },
  { key: "c5", label: "Price > MA50" },
  { key: "c6", label: "Within 25% of 52w high" },
  { key: "c7", label: "≥30% above 52w low" },
  { key: "c8",  label: "RS Rating > 85" },
  { key: "c9",  label: "Rel Vol ≥ 1.5×" },
  { key: "c10", label: "Avg Vol (10d) ≥ 1M" },
];

const RATING_FILTERS = [
  { id: "ALL",        label: "All Ratings", color: "#8b949e" },
  { id: "STRONG_BUY", label: "Strong Buy",  color: "#56d364" },
  { id: "BUY",        label: "Buy",         color: "#3fb950" },
  { id: "HOLD",       label: "Hold",        color: "#e3b341" },
];

const RS_FILTERS = [
  { id: "ALL", label: "All RS",  color: "#8b949e" },
  { id: "90",  label: "RS > 90", color: "#56d364" },
  { id: "85",  label: "RS > 85", color: "#3fb950" },
  { id: "75",  label: "RS > 75", color: "#e3b341" },
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

function Check({ pass }) {
  return (
    <span style={{ color: pass ? "#56d364" : "#f85149", fontWeight: 700, fontSize: 14 }}>
      {pass ? "✓" : "✗"}
    </span>
  );
}

function RsBadge({ rating }) {
  const color = rating > 85 ? "#56d364" : rating >= 75 ? "#3fb950" : rating >= 60 ? "#e3b341" : "#f85149";
  return (
    <span style={{
      padding: "2px 7px", borderRadius: 4, fontWeight: 700, fontSize: 12,
      background: color + "22", color, border: `1px solid ${color}55`,
    }}>
      {rating.toFixed(0)}
    </span>
  );
}

function CriteriaBadge({ met }) {
  const color = met === 10 ? "#56d364" : met >= 8 ? "#e3b341" : "#8b949e";
  return <span style={{ color, fontWeight: 700 }}>{met}/10</span>;
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

export default function MinerviniScreener() {
  const [mode, setMode] = useState("screen");  // "screen" | "backtest"

  // Screen state
  const [universe, setUniverse] = useState("sp500");
  const [minCriteria, setMinCriteria] = useState(8);
  const [maxTickers, setMaxTickers] = useState(3000);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [response, setResponse] = useState(null);
  const [expandedRow, setExpandedRow] = useState(null);
  const [selectedTicker, setSelectedTicker] = useState(null);
  const [chartData, setChartData] = useState(null);
  const [chartLoading, setChartLoading] = useState(false);
  const [viewRating, setViewRating] = useState("ALL");
  const [viewRs, setViewRs] = useState("ALL");
  const [tickersCopied, setTickersCopied] = useState(false);

  // Backtest state
  const [btTickerInput, setBtTickerInput] = useState("");
  const [btTicker, setBtTicker] = useState(null);
  const [btData, setBtData] = useState(null);
  const [btChartData, setBtChartData] = useState(null);
  const [btLoading, setBtLoading] = useState(false);
  const [btPeriod, setBtPeriod] = useState(730);
  const [btExitMode, setBtExitMode] = useState("SMA50");
  const [btTrailPct, setBtTrailPct] = useState(8);

  const selectedUniverse = UNIVERSES.find(u => u.id === universe);

  async function run() {
    setLoading(true);
    setError(null);
    setResponse(null);
    setExpandedRow(null);
    setSelectedTicker(null);
    setBtTicker(null);
    setViewRating("ALL");
    setViewRs("ALL");
    try {
      const data = await runMinerviniScreen(universe, minCriteria, maxTickers);
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
      const data = await fetchChart(ticker, 505);   // ~350 trading days; trimStart=100 leaves ~250 bars (1 year) visible
      setChartData(data);
    } catch {
      setChartData(null);
    } finally {
      setChartLoading(false);
    }
  }

  function toggleRow(ticker) {
    setExpandedRow(prev => prev === ticker ? null : ticker);
  }

  async function startBacktest(ticker, period, exitMode, trailPct) {
    setBtTicker(ticker);
    setBtData(null);
    setBtChartData(null);
    setBtLoading(true);
    try {
      const [btResult, chartResult] = await Promise.all([
        runMinerviniBacktest(ticker, period, exitMode, trailPct),
        fetchChart(ticker, period + 70),   // +70 cal days ≈ 50 trading days SMA warm-up
      ]);
      setBtData(btResult);
      setBtChartData(chartResult);
    } catch {
      setBtData(null);
      setBtChartData(null);
    } finally {
      setBtLoading(false);
    }
  }

  const visibleResults = response
    ? response.results.filter(r =>
        ratingMatch(r.analyst_rating, viewRating) &&
        (viewRs === "ALL" || r.rs_rating > Number(viewRs))
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
  const exitColor = reason => {
    if (reason === "SMA50") return "#e3b341";
    if (reason === "ATR_STOP" || reason === "SMA50+ATR") return "#f85149";
    if (reason === "PCT_STOP") return "#f0883e";
    return "#8b949e";
  };

  // ── Backtest results panel ──────────────────────────────────────────────── //
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
            <option value="PCT_TRAIL">Trailing % Stop</option>
          </select>
          {btExitMode === "PCT_TRAIL" && (
            <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, color: "#8b949e" }}>
              Trail %:
              <input
                type="number"
                value={btTrailPct}
                min={1} max={50} step={0.5}
                onChange={e => setBtTrailPct(Number(e.target.value))}
                style={{
                  width: 60, background: "#0d1117", color: "#e6edf3",
                  border: "1px solid #30363d", borderRadius: 6,
                  padding: "4px 8px", fontSize: 13, fontFamily: "inherit",
                }}
              />
            </label>
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

      {btData && !btLoading && (
        <>
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
          ) : (
            <div style={{ overflowX: "auto" }}>
              <div style={{ fontSize: 11, color: "#8b949e", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>
                Trade Log ({btData.trades.length} trade{btData.trades.length !== 1 ? "s" : ""})
              </div>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr>
                    {["#", "Entry Date", "Exit Date", "Entry $", "Exit $", "PnL %", "Days", "Exit Reason"].map(h => (
                      <th key={h} style={{ ...th, fontSize: 10 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {btData.trades.map((t, i) => (
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
          )}
        </>
      )}

      {!btData && !btLoading && (
        <p style={{ color: "#f85149", fontSize: 13 }}>Failed to load backtest data.</p>
      )}
    </div>
  );

  return (
    <div>
      {/* Page header + mode tabs */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20, flexWrap: "wrap", gap: 12 }}>
        <div>
          <h2 style={{ marginBottom: 4 }}>Minervini SEPA Screen</h2>
          <p style={{ color: "#8b949e", fontSize: 13, margin: 0 }}>
            Mark Minervini's Trend Template — 8-criteria Stage 2 uptrend filter
          </p>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          <ModeTab active={mode === "screen"}   onClick={() => setMode("screen")}>Screen</ModeTab>
          <ModeTab active={mode === "backtest"} onClick={() => setMode("backtest")}>Backtest</ModeTab>
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
                <option value={10}>10/10 — strict SEPA pass</option>
                <option value={9}>9+ criteria</option>
                <option value={8}>8+ criteria</option>
                <option value={7}>7+ criteria</option>
                <option value={6}>6+ criteria</option>
                <option value={5}>5+ criteria</option>
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
            {loading && <span style={{ fontSize: 12, color: "#8b949e" }}>Fetching 300 days of history + computing RS ratings…</span>}
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
                <strong style={{ color: "#56d364" }}>{response.matches}</strong> full SEPA pass{response.matches !== 1 ? "es" : ""},{" "}
                <strong style={{ color: "#e3b341" }}>{visibleResults.length}</strong> shown
              </div>
              {visibleResults.length > 0 && (
                <>
                  <button onClick={() => exportCsv(visibleResults, MINERVINI_FIELDS, MINERVINI_HEADERS, `minervini-screen-${today()}.csv`)} style={{ padding: "3px 10px", borderRadius: 6, border: "1px solid #30363d", background: "#21262d", color: "#8b949e", fontSize: 12, cursor: "pointer", fontWeight: 600 }}>
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
            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 12 }}>
              <div style={{ display: "flex", gap: 16, alignItems: "center", flexWrap: "wrap" }}>
                <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                  <span style={{ fontSize: 11, color: "#8b949e", textTransform: "uppercase", letterSpacing: "0.05em", minWidth: 46 }}>Rating:</span>
                  {RATING_FILTERS.map(f => (
                    <FilterChip key={f.id} label={f.label} active={viewRating === f.id} color={f.color} onClick={() => setViewRating(f.id)} />
                  ))}
                </div>
              </div>
              <div style={{ display: "flex", gap: 16, alignItems: "center", flexWrap: "wrap" }}>
                <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                  <span style={{ fontSize: 11, color: "#8b949e", textTransform: "uppercase", letterSpacing: "0.05em", minWidth: 46 }}>RS:</span>
                  {RS_FILTERS.map(f => (
                    <FilterChip key={f.id} label={f.label} active={viewRs === f.id} color={f.color} onClick={() => setViewRs(f.id)} />
                  ))}
                </div>
                {(viewRating !== "ALL" || viewRs !== "ALL") && (
                  <button onClick={() => { setViewRating("ALL"); setViewRs("ALL"); }} style={{ background: "none", border: "none", color: "#58a6ff", fontSize: 12, cursor: "pointer", padding: 0 }}>
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
              {chartLoading ? <p style={{ color: "#8b949e" }}>Loading chart…</p> : <CandlestickChart data={chartData} showVolume trimStart={100} />}
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
                      {["Ticker", "Chg %", "Rel Vol", "Vol", "Mkt Cap", "EPS", "Sector", "Rating", "Met", "RS", "Close", "% from High", "% from Low", "MA50", "MA200", "C1","C2","C3","C4","C5","C6","C7","C8","C9","C10", "BT"].map(h => (
                        <th key={h} style={th}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {visibleResults.map(r => (
                      <tr
                        key={r.ticker}
                        onClick={() => { toggleRow(r.ticker); selectTicker(r.ticker); }}
                        style={{ cursor: "pointer", background: selectedTicker === r.ticker ? "#1f3a5f" : "transparent" }}
                        onMouseEnter={e => { if (selectedTicker !== r.ticker) e.currentTarget.style.background = "#161b22"; }}
                        onMouseLeave={e => { if (selectedTicker !== r.ticker) e.currentTarget.style.background = "transparent"; }}
                      >
                        <TickerCell ticker={r.ticker} name={r.name} passes={r.passes} tdStyle={td} />
                        <td style={td}><PriceChangePct pct={r.price_change_pct} /></td>
                        <td style={td}><RelVolBadge rv={r.rel_vol} /></td>
                        <td style={{ ...td, fontSize: 12, color: "#8b949e" }}>{fmtVol(r.today_vol)}</td>
                        <td style={{ ...td, fontSize: 12, color: "#8b949e" }}>{fmtMarketCap(r.market_cap)}</td>
                        <td style={{ ...td, fontSize: 12, color: "#8b949e" }}>{r.eps != null ? r.eps.toFixed(2) : "—"}</td>
                        <td style={{ ...td, fontSize: 12, color: "#8b949e" }}>{r.sector ?? "—"}</td>
                        <td style={td}><AnalystBadge rating={r.analyst_rating} /></td>
                        <td style={td}><CriteriaBadge met={r.criteria_met} /></td>
                        <td style={td}><RsBadge rating={r.rs_rating} /></td>
                        <td style={td}>${r.last_close.toFixed(2)}</td>
                        <td style={{ ...td, color: r.pct_from_high >= -10 ? "#56d364" : r.pct_from_high >= -25 ? "#e3b341" : "#f85149" }}>
                          {r.pct_from_high.toFixed(1)}%
                        </td>
                        <td style={{ ...td, color: r.pct_from_low >= 30 ? "#56d364" : "#f85149" }}>
                          +{r.pct_from_low.toFixed(1)}%
                        </td>
                        <td style={td}>${r.ma50.toFixed(2)}</td>
                        <td style={td}>
                          ${r.ma200.toFixed(2)}
                          <span style={{ marginLeft: 4, fontSize: 11, color: r.ma200_trend > 0 ? "#56d364" : "#f85149" }}>
                            {r.ma200_trend > 0 ? "▲" : "▼"}{Math.abs(r.ma200_trend).toFixed(1)}%
                          </span>
                        </td>
                        {["c1","c2","c3","c4","c5","c6","c7","c8","c9","c10"].map(c => (
                          <td key={c} style={{ ...td, textAlign: "center" }}><Check pass={r[c]} /></td>
                        ))}
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
              No stocks met {minCriteria}/10 criteria in this batch.{minCriteria === 10 && " Try lowering the minimum criteria or increasing the ticker count."}
            </div>
          )}
        </>
      )}

      {/* ── BACKTEST MODE ────────────────────────────────────────────────── */}
      {mode === "backtest" && (
        <>
          <div style={{ background: "#161b22", border: "1px solid #30363d", borderRadius: 8, padding: 16, marginBottom: 20 }}>
            <div style={{ fontSize: 11, color: "#8b949e", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 10 }}>
              Backtest SEPA Strategy on Any Ticker
            </div>
            <div style={{ fontSize: 12, color: "#8b949e", marginBottom: 12 }}>
              Entry uses C1–C7 (MA stack, 52-week range). C8 RS Rating is omitted for single-ticker backtests.
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
                <option value="PCT_TRAIL">Trailing % Stop</option>
              </select>
              {btExitMode === "PCT_TRAIL" && (
                <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, color: "#8b949e" }}>
                  Trail %:
                  <input
                    type="number"
                    value={btTrailPct}
                    min={1} max={50} step={0.5}
                    onChange={e => setBtTrailPct(Number(e.target.value))}
                    style={{
                      width: 60, background: "#0d1117", color: "#e6edf3",
                      border: "1px solid #30363d", borderRadius: 6,
                      padding: "4px 8px", fontSize: 13, fontFamily: "inherit",
                    }}
                  />
                </label>
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

          <BacktestPanel />
        </>
      )}
    </div>
  );
}
