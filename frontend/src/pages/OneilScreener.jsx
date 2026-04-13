import { useState } from "react";
import { runOneilScreen, fetchChart } from "../api/screener";
import CandlestickChart from "../components/CandlestickChart";
import { exportCsv, today } from "../utils/exportCsv";

const ONEIL_FIELDS = ["ticker","name","rs_rating","pattern","pivot","last_close","pct_from_pivot","breakout","breakout_vol","rel_volume","depth_pct","base_weeks","price_change_pct","rel_vol","today_vol","market_cap","eps","sector","analyst_rating"];
const ONEIL_HEADERS = { ticker:"Ticker", name:"Name", rs_rating:"RS Rating", pattern:"Pattern", pivot:"Pivot", last_close:"Close", pct_from_pivot:"% From Pivot", breakout:"Breakout", breakout_vol:"Breakout w/ Vol", rel_volume:"Rel Vol (Signal)", depth_pct:"Depth %", base_weeks:"Base Weeks", price_change_pct:"Chg %", rel_vol:"Rel Vol 30d", today_vol:"Volume", market_cap:"Mkt Cap", eps:"EPS", sector:"Sector", analyst_rating:"Rating" };
import {
  fmtVol, fmtMarketCap,
  TickerCell, PriceChangePct, RelVolBadge, AnalystBadge,
} from "../components/MetaCells";

const UNIVERSES = [
  { id: "sp500",       label: "S&P 500",      size: "~503" },
  { id: "nasdaq100",   label: "NASDAQ 100",   size: "~101" },
  { id: "russell2000", label: "Russell 2000", size: "~2000" },
];

const PATTERNS = [
  { id: "ALL",            label: "All Patterns" },
  { id: "CUP_HANDLE",    label: "Cup-with-Handle" },
  { id: "FLAT_BASE",     label: "Flat Base" },
  { id: "DOUBLE_BOTTOM", label: "Double Bottom" },
  { id: "SAUCER",        label: "Saucer" },
  { id: "ASCENDING_BASE",label: "Ascending Base" },
];

const PATTERN_META = {
  CUP_HANDLE:     { label: "Cup-w-Handle",   color: "#58a6ff", desc: "7–52 wk U-shape + handle; buy on handle breakout" },
  FLAT_BASE:      { label: "Flat Base",       color: "#56d364", desc: "5+ wk tight sideways (≤15% correction); buy on high breakout" },
  DOUBLE_BOTTOM:  { label: "Double Bottom",   color: "#e3b341", desc: "W-shape; 2nd low undercuts 1st; buy on mid-peak breakout" },
  SAUCER:         { label: "Saucer",          color: "#f0883e", desc: "12 wk–2 yr gradual rounding base; flat extended bottom (12–35% depth); buy on handle breakout" },
  ASCENDING_BASE: { label: "Ascending Base",  color: "#bc8cff", desc: "9–16 wk staircase: 3 waves of higher highs + higher lows, 10–20% each pullback" },
};

const selectStyle = {
  background: "#161b22", color: "#e6edf3", border: "1px solid #30363d",
  borderRadius: 6, padding: "4px 8px", fontSize: 13,
};

const RATING_FILTERS = [
  { id: "ALL",        label: "All Ratings" },
  { id: "STRONG_BUY", label: "Strong Buy" },
  { id: "BUY",        label: "Buy" },
  { id: "HOLD",       label: "Hold" },
];

const RS_FILTERS = [
  { id: "ALL", label: "All" },
  { id: "70",  label: "RS 70+" },
  { id: "80",  label: "RS 80+" },
  { id: "90",  label: "RS 90+" },
];

const REL_VOL_FILTERS = [
  { id: "ALL", label: "All" },
  { id: "1.0", label: "≥ 1×" },
  { id: "1.5", label: "≥ 1.5×" },
  { id: "2.0", label: "≥ 2×" },
];

function ratingMatch(rating, filter) {
  if (filter === "ALL") return true;
  if (!rating) return false;
  const r = rating.toLowerCase();
  if (filter === "STRONG_BUY") return r.includes("strong buy") || r.includes("outperform") || r.includes("overweight");
  if (filter === "BUY")        return r.includes("buy") && !r.includes("strong");
  if (filter === "HOLD")       return r.includes("hold") || r.includes("neutral") || r.includes("equal");
  return true;
}

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

function FilterChip({ active, color, onClick, children }) {
  return (
    <button onClick={onClick} style={{
      padding: "4px 12px", borderRadius: 20, fontSize: 12, fontWeight: 600,
      cursor: "pointer",
      border: `1px solid ${active ? (color || "#388bfd") : "#30363d"}`,
      background: active ? (color || "#388bfd") + "22" : "transparent",
      color: active ? (color || "#58a6ff") : "#8b949e",
    }}>
      {children}
    </button>
  );
}

function PatternBadge({ pattern }) {
  const meta = PATTERN_META[pattern] || { label: pattern, color: "#8b949e" };
  return (
    <span style={{
      padding: "2px 7px", borderRadius: 4, fontSize: 11, fontWeight: 700,
      background: meta.color + "22", color: meta.color,
      border: `1px solid ${meta.color}55`, whiteSpace: "nowrap",
    }}>
      {meta.label}
    </span>
  );
}

function PivotBadge({ pct, breakout, breakoutVol }) {
  if (breakout && breakoutVol) {
    return <span style={{ color: "#56d364", fontWeight: 700 }}>▲ BREAKOUT</span>;
  }
  if (breakout) {
    return <span style={{ color: "#3fb950", fontWeight: 700 }}>▲ {pct > 0 ? "+" : ""}{pct.toFixed(1)}%</span>;
  }
  const color = Math.abs(pct) < 2 ? "#e3b341" : "#8b949e";
  return <span style={{ color, fontWeight: 600 }}>{pct.toFixed(1)}%</span>;
}

export default function OneilScreener() {
  const [universe, setUniverse] = useState("sp500");
  const [patternFilter, setPatternFilter] = useState("ALL");
  const [breakoutOnly, setBreakoutOnly] = useState(false);
  const [maxTickers, setMaxTickers] = useState(3000);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [response, setResponse] = useState(null);
  const [selectedTicker, setSelectedTicker] = useState(null);
  const [chartData, setChartData] = useState(null);
  const [chartLoading, setChartLoading] = useState(false);
  const [tickersCopied, setTickersCopied] = useState(false);

  // Client-side CAN SLIM filters (no re-fetch needed)
  const [viewPattern, setViewPattern] = useState("ALL");
  const [viewRating, setViewRating] = useState("ALL");
  const [viewRs, setViewRs] = useState("ALL");           // L — Leader
  const [viewRelVol, setViewRelVol] = useState("ALL");   // S — Supply/Demand
  const [epsPositive, setEpsPositive] = useState(false); // C — Current Earnings

  const selectedUniverse = UNIVERSES.find(u => u.id === universe);

  const visibleResults = response?.results.filter(r =>
    (viewPattern === "ALL" || r.pattern === viewPattern) &&
    ratingMatch(r.analyst_rating, viewRating) &&
    (viewRs === "ALL" || (r.rs_rating ?? 0) >= Number(viewRs)) &&
    (viewRelVol === "ALL" || (r.rel_vol ?? r.rel_volume ?? 0) >= Number(viewRelVol)) &&
    (!epsPositive || (r.eps != null && r.eps > 0))
  ) ?? [];

  async function run() {
    setLoading(true);
    setError(null);
    setResponse(null);
    setSelectedTicker(null);
    setViewPattern("ALL");
    setViewRating("ALL");
    setViewRs("ALL");
    setViewRelVol("ALL");
    setEpsPositive(false);
    try {
      const data = await runOneilScreen(universe, patternFilter, breakoutOnly, maxTickers);
      setResponse(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function selectTicker(ticker, periodDays = 365) {
    setSelectedTicker(ticker);
    setChartLoading(true);
    try {
      const data = await fetchChart(ticker, periodDays + 70);   // +70 cal days ≈ 50 trading days SMA warm-up
      setChartData(data);
    } catch {
      setChartData(null);
    } finally {
      setChartLoading(false);
    }
  }

  const th = {
    padding: "8px 12px", textAlign: "left", borderBottom: "1px solid #30363d",
    color: "#8b949e", fontWeight: 600, fontSize: 11,
    textTransform: "uppercase", letterSpacing: "0.05em", whiteSpace: "nowrap",
  };
  const td = { padding: "8px 12px", borderBottom: "1px solid #21262d", fontSize: 13 };

  return (
    <div>
      <h2 style={{ marginBottom: 4 }}>O'Neil CAN SLIM Patterns</h2>
      <p style={{ color: "#8b949e", fontSize: 13, marginBottom: 20 }}>
        William O'Neil's three primary base patterns — Cup-with-Handle, Flat Base, Double Bottom
      </p>

      {/* Pattern legend */}
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 20, padding: "10px 14px", background: "#161b22", border: "1px solid #21262d", borderRadius: 8 }}>
        {Object.entries(PATTERN_META).map(([key, meta]) => (
          <div key={key} style={{ fontSize: 12 }}>
            <PatternBadge pattern={key} />
            <span style={{ color: "#8b949e", marginLeft: 8 }}>{meta.desc}</span>
          </div>
        ))}
      </div>

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
          Pattern:
          <select value={patternFilter} onChange={e => setPatternFilter(e.target.value)} style={selectStyle}>
            {PATTERNS.map(p => (
              <option key={p.id} value={p.id}>{p.label}</option>
            ))}
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

        <label style={{ fontSize: 13, color: "#8b949e", display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={breakoutOnly}
            onChange={e => setBreakoutOnly(e.target.checked)}
            style={{ accentColor: "#58a6ff" }}
          />
          Breakout only
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
        {loading && <span style={{ fontSize: 12, color: "#8b949e" }}>Detecting base patterns…</span>}
      </div>

      {error && (
        <div style={{ color: "#f85149", background: "#2d1b1b", border: "1px solid #f85149", borderRadius: 6, padding: 12, marginBottom: 16 }}>
          {error}
        </div>
      )}

      {response && (
        <>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12, flexWrap: "wrap", gap: 8 }}>
            <div style={{ fontSize: 13, color: "#8b949e" }}>
              <strong style={{ color: "#e6edf3" }}>{selectedUniverse?.label}</strong>
              {" — "}Screened <strong style={{ color: "#e6edf3" }}>{response.total_screened}</strong> tickers,{" "}
              <strong style={{ color: "#56d364" }}>{response.matches}</strong> breakout{response.matches !== 1 ? "s" : ""},{" "}
              <strong style={{ color: "#e3b341" }}>{response.results.length}</strong> near pivot
              {(viewPattern !== "ALL" || viewRating !== "ALL" || viewRs !== "ALL" || viewRelVol !== "ALL" || epsPositive) && (
                <span style={{ marginLeft: 8 }}>
                  → showing <strong style={{ color: "#e6edf3" }}>{visibleResults.length}</strong>
                </span>
              )}
            </div>
            {visibleResults.length > 0 && (
              <>
                <button onClick={() => exportCsv(visibleResults, ONEIL_FIELDS, ONEIL_HEADERS, `oneil-screen-${today()}.csv`)} style={{ padding: "3px 10px", borderRadius: 6, border: "1px solid #30363d", background: "#21262d", color: "#8b949e", fontSize: 12, cursor: "pointer", fontWeight: 600 }}>
                  ↓ CSV
                </button>
                <button onClick={() => { navigator.clipboard.writeText(visibleResults.map(r => r.ticker).join(",")); setTickersCopied(true); setTimeout(() => setTickersCopied(false), 2000); }} style={{ padding: "3px 10px", borderRadius: 6, border: "1px solid #30363d", background: "#21262d", color: tickersCopied ? "#56d364" : "#8b949e", fontSize: 12, cursor: "pointer", fontWeight: 600 }}>
                  {tickersCopied ? "✓ Copied" : "↓ Tickers"}
                </button>
              </>
            )}
          </div>

          {/* Client-side CAN SLIM filter bars */}
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 14, padding: "10px 14px", background: "#161b22", border: "1px solid #21262d", borderRadius: 8 }}>
            <div style={{ fontSize: 11, color: "#58a6ff", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 700, marginBottom: 2 }}>
              CAN SLIM Filters
            </div>
            {/* N — Pattern */}
            <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
              <span style={{ fontSize: 11, color: "#8b949e", textTransform: "uppercase", letterSpacing: "0.06em", width: 60 }}>N — Pattern</span>
              {[{ id: "ALL", label: "All" }, ...Object.entries(PATTERN_META).map(([id, m]) => ({ id, label: m.label }))].map(p => (
                <FilterChip
                  key={p.id}
                  active={viewPattern === p.id}
                  color={p.id !== "ALL" ? PATTERN_META[p.id]?.color : undefined}
                  onClick={() => setViewPattern(p.id)}
                >
                  {p.label}
                </FilterChip>
              ))}
            </div>
            {/* L — Leader (RS Rating) */}
            <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
              <span style={{ fontSize: 11, color: "#8b949e", textTransform: "uppercase", letterSpacing: "0.06em", width: 60 }}>L — Leader</span>
              {RS_FILTERS.map(f => (
                <FilterChip key={f.id} active={viewRs === f.id} color="#e3b341" onClick={() => setViewRs(f.id)}>
                  {f.label}
                </FilterChip>
              ))}
            </div>
            {/* S — Supply/Demand (Rel Vol) */}
            <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
              <span style={{ fontSize: 11, color: "#8b949e", textTransform: "uppercase", letterSpacing: "0.06em", width: 60 }}>S — Demand</span>
              {REL_VOL_FILTERS.map(f => (
                <FilterChip key={f.id} active={viewRelVol === f.id} color="#56d364" onClick={() => setViewRelVol(f.id)}>
                  {f.label}
                </FilterChip>
              ))}
            </div>
            {/* C — Current Earnings + I — Rating */}
            <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
              <span style={{ fontSize: 11, color: "#8b949e", textTransform: "uppercase", letterSpacing: "0.06em", width: 60 }}>C — EPS</span>
              <FilterChip active={!epsPositive} onClick={() => setEpsPositive(false)}>All</FilterChip>
              <FilterChip active={epsPositive} color="#56d364" onClick={() => setEpsPositive(true)}>EPS &gt; 0</FilterChip>
              <span style={{ fontSize: 11, color: "#8b949e", textTransform: "uppercase", letterSpacing: "0.06em", marginLeft: 16, marginRight: 4 }}>I — Rating</span>
              {RATING_FILTERS.map(rf => (
                <FilterChip key={rf.id} active={viewRating === rf.id} onClick={() => setViewRating(rf.id)}>
                  {rf.label}
                </FilterChip>
              ))}
              {(viewPattern !== "ALL" || viewRating !== "ALL" || viewRs !== "ALL" || viewRelVol !== "ALL" || epsPositive) && (
                <button
                  onClick={() => { setViewPattern("ALL"); setViewRating("ALL"); setViewRs("ALL"); setViewRelVol("ALL"); setEpsPositive(false); }}
                  style={{ marginLeft: 8, fontSize: 12, color: "#8b949e", background: "none", border: "none", cursor: "pointer", textDecoration: "underline" }}
                >
                  Clear filters
                </button>
              )}
            </div>
          </div>
        </>
      )}

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

      {/* Results table */}
      {response && visibleResults.length > 0 && (
        <div style={{ background: "#161b22", border: "1px solid #30363d", borderRadius: 8, overflow: "hidden" }}>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  {["Ticker", "RS", "Pattern", "Chg %", "Rel Vol", "Vol", "Mkt Cap", "EPS", "Sector", "Rating", "Close", "Pivot", "vs Pivot", "Depth", "Wks"].map(h => (
                    <th key={h} style={th}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visibleResults.map(r => (
                  <tr
                    key={r.ticker}
                    onClick={() => selectTicker(r.ticker, 365)}
                    style={{
                      cursor: "pointer",
                      background: selectedTicker === r.ticker
                        ? "#0d2b0d"
                        : r.breakout && r.breakout_vol
                          ? "#0d1a0d"
                          : "transparent",
                    }}
                    onMouseEnter={e => { if (selectedTicker !== r.ticker) e.currentTarget.style.background = "#161b22"; }}
                    onMouseLeave={e => {
                      if (selectedTicker !== r.ticker)
                        e.currentTarget.style.background =
                          r.breakout && r.breakout_vol ? "#0d1a0d" : "transparent";
                    }}
                  >
                    <TickerCell ticker={r.ticker} name={r.name} passes={r.breakout && r.breakout_vol} tdStyle={td} />
                    <td style={{ ...td, fontWeight: 700, color: (r.rs_rating ?? 0) >= 90 ? "#56d364" : (r.rs_rating ?? 0) >= 70 ? "#e3b341" : "#8b949e" }}>
                      {r.rs_rating != null ? Math.round(r.rs_rating) : "—"}
                    </td>
                    <td style={td}><PatternBadge pattern={r.pattern} /></td>
                    <td style={td}><PriceChangePct pct={r.price_change_pct} /></td>
                    <td style={td}><RelVolBadge rv={r.rel_vol ?? r.rel_volume} /></td>
                    <td style={{ ...td, fontSize: 12, color: "#8b949e" }}>{fmtVol(r.today_vol)}</td>
                    <td style={{ ...td, fontSize: 12, color: "#8b949e" }}>{fmtMarketCap(r.market_cap)}</td>
                    <td style={{ ...td, fontSize: 12, color: "#8b949e" }}>{r.eps != null ? r.eps.toFixed(2) : "—"}</td>
                    <td style={{ ...td, fontSize: 12, color: "#8b949e" }}>{r.sector ?? "—"}</td>
                    <td style={td}><AnalystBadge rating={r.analyst_rating} /></td>
                    <td style={td}>${r.last_close.toFixed(2)}</td>
                    <td style={{ ...td, fontWeight: 700 }}>${r.pivot.toFixed(2)}</td>
                    <td style={td}>
                      <PivotBadge pct={r.pct_from_pivot} breakout={r.breakout} breakoutVol={r.breakout_vol} />
                    </td>
                    <td style={{ ...td, color: r.depth_pct > 30 ? "#f85149" : r.depth_pct > 20 ? "#e3b341" : "#56d364" }}>
                      {r.depth_pct.toFixed(1)}%
                    </td>
                    <td style={{ ...td, color: "#8b949e" }}>{r.base_weeks}w</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {response && visibleResults.length === 0 && (
        <div style={{ background: "#161b22", border: "1px solid #30363d", borderRadius: 8, padding: 24, textAlign: "center", color: "#8b949e" }}>
          {response.results.length === 0
            ? <>No {patternFilter === "ALL" ? "" : PATTERN_META[patternFilter]?.label + " "}patterns found near pivot in this batch.{breakoutOnly && " Try unchecking 'Breakout only'."}</>
            : <>No results match the current filters. <button onClick={() => { setViewPattern("ALL"); setViewRating("ALL"); setViewRs("ALL"); setViewRelVol("ALL"); setEpsPositive(false); }} style={{ color: "#58a6ff", background: "none", border: "none", cursor: "pointer", textDecoration: "underline", fontSize: "inherit" }}>Clear filters</button></>
          }
        </div>
      )}
    </div>
  );
}
