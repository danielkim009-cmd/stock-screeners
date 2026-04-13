import SignalBadge from "./SignalBadge";
import {
  fmtVol, fmtMarketCap,
  TickerCell, PriceChangePct, RelVolBadge, AnalystBadge,
} from "./MetaCells";

const th = {
  padding: "8px 12px",
  textAlign: "left",
  borderBottom: "1px solid #30363d",
  color: "#8b949e",
  fontWeight: 600,
  fontSize: 12,
  textTransform: "uppercase",
  letterSpacing: "0.05em",
  whiteSpace: "nowrap",
};

const td = {
  padding: "8px 12px",
  borderBottom: "1px solid #21262d",
  fontSize: 13,
};

const HEADERS = [
  "Ticker", "Signal", "Chg %", "Rel Vol", "Vol", "Mkt Cap",
  "EPS", "Sector", "Rating",
  "Close", "ATR(20)", "20d High", "55d High", "Stop (10d)", "BT",
];

export default function ResultsTable({ results, onSelect, onBacktest, btTicker, selectedTicker }) {
  if (!results || results.length === 0) {
    return <p style={{ color: "#8b949e", padding: 16 }}>No results.</p>;
  }

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            {HEADERS.map(h => <th key={h} style={th}>{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {results.map(r => (
            <tr
              key={r.ticker}
              onClick={() => onSelect(r.ticker)}
              style={{ cursor: "pointer", background: selectedTicker === r.ticker ? "#1f3a5f" : "transparent" }}
              onMouseEnter={e => { if (selectedTicker !== r.ticker) e.currentTarget.style.background = "#161b22"; }}
              onMouseLeave={e => { if (selectedTicker !== r.ticker) e.currentTarget.style.background = "transparent"; }}
            >
              <TickerCell ticker={r.ticker} name={r.name} tdStyle={td} />
              <td style={td}><SignalBadge signal={r.signal} /></td>
              <td style={td}><PriceChangePct pct={r.price_change_pct} /></td>
              <td style={td}><RelVolBadge rv={r.rel_vol} /></td>
              <td style={{ ...td, fontSize: 12, color: "#8b949e" }}>{fmtVol(r.today_vol)}</td>
              <td style={{ ...td, fontSize: 12, color: "#8b949e" }}>{fmtMarketCap(r.market_cap)}</td>
              <td style={{ ...td, fontSize: 12, color: "#8b949e" }}>
                {r.eps != null ? r.eps.toFixed(2) : "—"}
              </td>
              <td style={{ ...td, fontSize: 12, color: "#8b949e" }}>{r.sector ?? "—"}</td>
              <td style={td}><AnalystBadge rating={r.analyst_rating} /></td>
              <td style={td}>${r.last_close.toFixed(2)}</td>
              <td style={td}>{r.atr_20.toFixed(2)}</td>
              <td style={{ ...td, color: r.breakout_20 ? "#56d364" : "inherit" }}>
                ${r.high_20.toFixed(2)}
              </td>
              <td style={{ ...td, color: r.breakout_55 ? "#56d364" : "inherit" }}>
                ${r.high_55.toFixed(2)}
              </td>
              <td style={{ ...td, color: "#f85149" }}>${r.low_10.toFixed(2)}</td>
              <td style={{ ...td, textAlign: "center" }}>
                {onBacktest && (
                  <button
                    onClick={e => { e.stopPropagation(); onBacktest(r); }}
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
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
