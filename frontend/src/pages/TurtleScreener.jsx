import { useState } from "react";
import { runTurtleScreen, runTurtleBacktest, fetchChart } from "../api/screener";
import ResultsTable from "../components/ResultsTable";
import CandlestickChart from "../components/CandlestickChart";
import { exportCsv, today } from "../utils/exportCsv";

const TURTLE_FIELDS = ["ticker","name","signal","rs_rating","last_close","atr_20","high_20","high_55","low_10","low_20","breakout_20","breakout_55","days_since_breakout","price_change_pct","rel_vol","today_vol","market_cap","eps","sector","analyst_rating"];
const TURTLE_HEADERS = { ticker:"Ticker", name:"Name", signal:"Signal", rs_rating:"RS Rating", last_close:"Close", atr_20:"ATR(20)", high_20:"20d High", high_55:"55d High", low_10:"10d Low", low_20:"20d Low", breakout_20:"Breakout 20", breakout_55:"Breakout 55", days_since_breakout:"Days Since BO", price_change_pct:"Chg %", rel_vol:"Rel Vol", today_vol:"Volume", market_cap:"Mkt Cap", eps:"EPS", sector:"Sector", analyst_rating:"Rating" };

const UNIVERSES = [
  { id: "sp500",       label: "S&P 500",      size: "~503" },
  { id: "nasdaq100",   label: "NASDAQ 100",   size: "~101" },
  { id: "russell2000", label: "Russell 2000", size: "~2000" },
];

const VOL_FILTERS = [
  { id: "ALL",       label: "All",    color: "#8b949e" },
  { id: "1000000",   label: "≥ 1M",  color: "#56d364" },
  { id: "500000",    label: "≥ 500K", color: "#3fb950" },
  { id: "100000",    label: "≥ 100K", color: "#e3b341" },
];

const REL_VOL_FILTERS = [
  { id: "ALL", label: "All Vol",  color: "#8b949e" },
  { id: "1.0", label: "≥ 1×",    color: "#e3b341" },
  { id: "1.5", label: "≥ 1.5×",  color: "#3fb950" },
  { id: "2.0", label: "≥ 2×",    color: "#56d364" },
];

const RS_FILTERS = [
  { id: "ALL", label: "All RS",  color: "#8b949e" },
  { id: "70",  label: "≥ 70",   color: "#e3b341" },
  { id: "80",  label: "≥ 80",   color: "#3fb950" },
  { id: "90",  label: "≥ 90",   color: "#56d364" },
];

const RATING_FILTERS = [
  { id: "ALL",        label: "All Ratings", color: "#8b949e" },
  { id: "STRONG_BUY", label: "Strong Buy",  color: "#56d364" },
  { id: "BUY",        label: "Buy+",        color: "#3fb950" },
  { id: "HOLD",       label: "Hold+",       color: "#e3b341" },
];

function ratingMatch(rating, filter) {
  if (filter === "ALL") return true;
  if (!rating) return false;
  const key = rating.toLowerCase().replace(/ /g, "_");
  if (filter === "STRONG_BUY") return key === "strong_buy";
  if (filter === "BUY") return key === "buy" || key === "strong_buy";
  if (filter === "HOLD") return key === "hold" || key === "buy" || key === "strong_buy";
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

function FilterBtn({ active, onClick, children }) {
  return (
    <button onClick={onClick} style={{
      padding: "5px 12px", borderRadius: 6, fontSize: 13, fontWeight: 600,
      cursor: "pointer",
      border: `1px solid ${active ? "#388bfd" : "#30363d"}`,
      background: active ? "#1f3a5f" : "transparent",
      color: active ? "#58a6ff" : "#8b949e",
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

export default function TurtleScreener() {
  const [mode, setMode] = useState("screen");  // "screen" | "backtest"

  // Screen state
  const [universe, setUniverse] = useState("sp500");
  const [filter, setFilter] = useState("ALL");
  const [maxTickers, setMaxTickers] = useState(3000);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [response, setResponse] = useState(null);
  const [selectedTicker, setSelectedTicker] = useState(null);
  const [chartData, setChartData] = useState(null);
  const [chartLoading, setChartLoading] = useState(false);
  const [tickersCopied, setTickersCopied] = useState(false);
  const [viewVol, setViewVol] = useState("ALL");
  const [viewRelVol, setViewRelVol] = useState("ALL");
  const [viewRs, setViewRs] = useState("ALL");
  const [viewRating, setViewRating] = useState("ALL");

  // Backtest state
  const [btTickerInput, setBtTickerInput] = useState("");
  const [btTicker, setBtTicker] = useState(null);
  const [btData, setBtData] = useState(null);
  const [btChartData, setBtChartData] = useState(null);
  const [btLoading, setBtLoading] = useState(false);
  const [btPeriod, setBtPeriod] = useState(730);
  const [btSystem, setBtSystem] = useState("S2");

  const selectedUniverse = UNIVERSES.find(u => u.id === universe);

  const visibleResults = response
    ? response.results.filter(r =>
        (viewVol === "ALL" || (r.today_vol ?? 0) >= Number(viewVol)) &&
        (viewRelVol === "ALL" || (r.rel_vol ?? 0) >= Number(viewRelVol)) &&
        (viewRs === "ALL" || (r.rs_rating ?? 0) >= Number(viewRs)) &&
        ratingMatch(r.analyst_rating, viewRating)
      )
    : [];

  async function run() {
    setLoading(true);
    setError(null);
    setResponse(null);
    setBtTicker(null);
    setViewVol("ALL");
    setViewRelVol("ALL");
    setViewRs("ALL");
    setViewRating("ALL");
    try {
      const data = await runTurtleScreen(universe, filter, maxTickers);
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

  async function startBacktest(ticker, period, system) {
    setBtTicker(ticker);
    setBtData(null);
    setBtChartData(null);
    setBtLoading(true);
    try {
      const [btResult, chartResult] = await Promise.all([
        runTurtleBacktest(ticker, period, system),
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

  const th = {
    padding: "8px 12px", textAlign: "left", borderBottom: "1px solid #30363d",
    color: "#8b949e", fontWeight: 600, fontSize: 11,
    textTransform: "uppercase", letterSpacing: "0.05em", whiteSpace: "nowrap",
  };
  const td = { padding: "8px 12px", borderBottom: "1px solid #21262d", fontSize: 13 };

  const pctColor = v => v > 0 ? "#56d364" : v < 0 ? "#f85149" : "#8b949e";
  const fmtPct = v => `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;

  const exitColor = reason => {
    if (reason === "LOW10" || reason === "LOW20") return "#e3b341";
    if (reason === "ATR_STOP") return "#f85149";
    return "#8b949e";
  };

  const systemBadge = sys => ({
    padding: "1px 6px", borderRadius: 4, fontSize: 11, fontWeight: 700,
    background: sys === "S2" ? "#56d36422" : "#58a6ff22",
    color: sys === "S2" ? "#56d364" : "#58a6ff",
    border: `1px solid ${sys === "S2" ? "#56d36455" : "#58a6ff55"}`,
  });

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
          <select value={btSystem} onChange={e => setBtSystem(e.target.value)} style={selectStyle}>
            <option value="S2">S2 — 55-day breakout</option>
            <option value="S1">S1 — 20-day breakout</option>
            <option value="BOTH">Both (S2 priority)</option>
          </select>
          <button
            onClick={() => startBacktest(btTicker, btPeriod, btSystem)}
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
                    {["#", "Sys", "Entry Date", "Exit Date", "Entry $", "Exit $", "PnL %", "Days", "Exit Reason"].map(h => (
                      <th key={h} style={{ ...th, fontSize: 10 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {btData.trades.map((t, i) => (
                    <tr key={i} style={{ background: t.pnl_pct > 0 ? "#0d2b0d" : t.pnl_pct < 0 ? "#2d1b1b" : "transparent" }}>
                      <td style={td}>{i + 1}</td>
                      <td style={td}>{t.system && <span style={systemBadge(t.system)}>{t.system}</span>}</td>
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
          <h2 style={{ marginBottom: 4 }}>Turtle Trading Screen</h2>
          <p style={{ color: "#8b949e", fontSize: 13, margin: 0 }}>
            Donchian channel breakouts — System 1 (20-day) and System 2 (55-day)
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

          {/* Signal filter + controls */}
          <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", marginBottom: 20 }}>
            <div style={{ display: "flex", gap: 6 }}>
              {["ALL", "S1_BUY", "S2_BUY"].map(f => (
                <FilterBtn key={f} active={filter === f} onClick={() => setFilter(f)}>{f}</FilterBtn>
              ))}
            </div>
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
                <strong style={{ color: "#56d364" }}>{response.matches}</strong> breakout signal{response.matches !== 1 ? "s" : ""},{" "}
                <strong style={{ color: "#e3b341" }}>{visibleResults.length}</strong> shown
              </div>
              {visibleResults.length > 0 && (
                <>
                  <button onClick={() => exportCsv(visibleResults, TURTLE_FIELDS, TURTLE_HEADERS, `turtle-screen-${today()}.csv`)} style={{ padding: "3px 10px", borderRadius: 6, border: "1px solid #30363d", background: "#21262d", color: "#8b949e", fontSize: 12, cursor: "pointer", fontWeight: 600 }}>
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
            <div style={{ display: "flex", gap: 16, alignItems: "center", flexWrap: "wrap", marginBottom: 12 }}>
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <span style={{ fontSize: 11, color: "#8b949e", textTransform: "uppercase", letterSpacing: "0.05em" }}>Vol:</span>
                {VOL_FILTERS.map(f => (
                  <FilterChip key={f.id} label={f.label} active={viewVol === f.id} color={f.color} onClick={() => setViewVol(f.id)} />
                ))}
              </div>
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <span style={{ fontSize: 11, color: "#8b949e", textTransform: "uppercase", letterSpacing: "0.05em" }}>Rel Vol:</span>
                {REL_VOL_FILTERS.map(f => (
                  <FilterChip key={f.id} label={f.label} active={viewRelVol === f.id} color={f.color} onClick={() => setViewRelVol(f.id)} />
                ))}
              </div>
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <span style={{ fontSize: 11, color: "#8b949e", textTransform: "uppercase", letterSpacing: "0.05em" }}>RS:</span>
                {RS_FILTERS.map(f => (
                  <FilterChip key={f.id} label={f.label} active={viewRs === f.id} color={f.color} onClick={() => setViewRs(f.id)} />
                ))}
              </div>
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <span style={{ fontSize: 11, color: "#8b949e", textTransform: "uppercase", letterSpacing: "0.05em" }}>Rating:</span>
                {RATING_FILTERS.map(f => (
                  <FilterChip key={f.id} label={f.label} active={viewRating === f.id} color={f.color} onClick={() => setViewRating(f.id)} />
                ))}
              </div>
              {(viewVol !== "ALL" || viewRelVol !== "ALL" || viewRs !== "ALL" || viewRating !== "ALL") && (
                <button onClick={() => { setViewVol("ALL"); setViewRelVol("ALL"); setViewRs("ALL"); setViewRating("ALL"); }} style={{ background: "none", border: "none", color: "#58a6ff", fontSize: 12, cursor: "pointer", padding: 0 }}>
                  Clear
                </button>
              )}
            </div>
          )}

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

          {/* Backtest panel (triggered from BT button) */}
          <BacktestPanel />

          {/* Results table */}
          {response && visibleResults.length > 0 && (
            <div style={{ background: "#161b22", border: "1px solid #30363d", borderRadius: 8, overflow: "hidden" }}>
              <ResultsTable
                results={visibleResults}
                onSelect={selectTicker}
                onBacktest={r => startBacktest(r.ticker, btPeriod, btSystem)}
                btTicker={btTicker}
                selectedTicker={selectedTicker}
              />
            </div>
          )}
        </>
      )}

      {/* ── BACKTEST MODE ────────────────────────────────────────────────── */}
      {mode === "backtest" && (
        <>
          <div style={{ background: "#161b22", border: "1px solid #30363d", borderRadius: 8, padding: 16, marginBottom: 20 }}>
            <div style={{ fontSize: 11, color: "#8b949e", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 10 }}>
              Backtest Turtle Strategy on Any Ticker
            </div>
            <div style={{ fontSize: 12, color: "#8b949e", marginBottom: 12 }}>
              S1: 20-day breakout entry → 10-day low exit + 2×ATR stop.&nbsp;
              S2: 55-day breakout entry → 20-day low exit + 2×ATR stop.
            </div>
            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
              <input
                value={btTickerInput}
                onChange={e => setBtTickerInput(e.target.value.toUpperCase())}
                onKeyDown={e => { if (e.key === "Enter" && btTickerInput.trim()) startBacktest(btTickerInput.trim(), btPeriod, btSystem); }}
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
              <select value={btSystem} onChange={e => setBtSystem(e.target.value)} style={selectStyle}>
                <option value="S2">S2 — 55-day breakout</option>
                <option value="S1">S1 — 20-day breakout</option>
                <option value="BOTH">Both (S2 priority)</option>
              </select>
              <button
                onClick={() => { if (btTickerInput.trim()) startBacktest(btTickerInput.trim(), btPeriod, btSystem); }}
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
