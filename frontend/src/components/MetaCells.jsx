/**
 * Shared display helpers for the metadata columns that appear in every screener:
 * Description, Price Change %, Rel Vol, Volume, Market Cap, EPS, Sector, Analyst Rating.
 */

export function fmtVol(v) {
  if (v == null) return "—";
  if (v >= 1e9) return (v / 1e9).toFixed(1) + "B";
  if (v >= 1e6) return (v / 1e6).toFixed(1) + "M";
  if (v >= 1e3) return (v / 1e3).toFixed(0) + "K";
  return String(v);
}

export function fmtMarketCap(v) {
  if (v == null) return "—";
  if (v >= 1e12) return (v / 1e12).toFixed(2) + "T";
  if (v >= 1e9)  return (v / 1e9).toFixed(1)  + "B";
  if (v >= 1e6)  return (v / 1e6).toFixed(0)  + "M";
  return String(v);
}

export function PriceChangePct({ pct, style }) {
  if (pct == null) return <span style={{ color: "#8b949e", ...style }}>—</span>;
  const color = pct > 0 ? "#56d364" : pct < 0 ? "#f85149" : "#8b949e";
  return (
    <span style={{ color, ...style }}>
      {pct > 0 ? "+" : ""}{pct.toFixed(2)}%
    </span>
  );
}

export function RelVolBadge({ rv }) {
  if (rv == null) return <span style={{ color: "#8b949e" }}>—</span>;
  const color = rv >= 2.0 ? "#56d364" : rv >= 1.5 ? "#e3b341" : "#8b949e";
  return (
    <span style={{
      padding: "2px 7px", borderRadius: 4, fontWeight: 700, fontSize: 12,
      background: color + "22", color, border: `1px solid ${color}55`,
    }}>
      {rv.toFixed(2)}×
    </span>
  );
}

const RATING_MAP = {
  strong_buy:   ["Strong Buy",  "#56d364"],
  buy:          ["Buy",         "#3fb950"],
  hold:         ["Hold",        "#e3b341"],
  neutral:      ["Hold",        "#e3b341"],
  underperform: ["Underpfm",    "#f0883e"],
  sell:         ["Sell",        "#f85149"],
  strong_sell:  ["Strong Sell", "#f85149"],
};

export function AnalystBadge({ rating }) {
  if (!rating) return <span style={{ color: "#8b949e" }}>—</span>;
  const key = rating.toLowerCase().replace(/ /g, "_");
  const [label, color] = RATING_MAP[key] ?? [rating, "#8b949e"];
  return (
    <span style={{
      padding: "2px 6px", borderRadius: 4, fontWeight: 700, fontSize: 11,
      background: color + "22", color, border: `1px solid ${color}55`,
      whiteSpace: "nowrap",
    }}>
      {label}
    </span>
  );
}

export function SectorBadge({ sector }) {
  if (!sector) return <span style={{ color: "#8b949e" }}>—</span>;
  return (
    <span style={{ fontSize: 11, color: "#8b949e", whiteSpace: "nowrap" }}>
      {sector}
    </span>
  );
}

/**
 * Ticker cell: symbol in bold + company name on a second line.
 */
export function TickerCell({ ticker, name, passes, tdStyle }) {
  const color = passes !== undefined
    ? (passes ? "#58a6ff" : "#8b949e")
    : "#58a6ff";
  return (
    <td style={tdStyle}>
      <div style={{ fontWeight: 700, color }}>{ticker}</div>
      {name && <div style={{ fontSize: 11, color: "#8b949e", marginTop: 1 }}>{name}</div>}
    </td>
  );
}
