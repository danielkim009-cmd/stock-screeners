import { useState } from "react";
import TurtleScreener from "./pages/TurtleScreener";
import MinerviniScreener from "./pages/MinerviniScreener";
import DanielsBreakoutScreener from "./pages/DanielsBreakoutScreener";
const STRATEGIES = [
  { id: "daniels",   label: "Daniel's Breakout" },
  { id: "turtle",    label: "Turtle" },
  { id: "minervini", label: "Minervini SEPA" },
  // { id: "hmm", label: "GMM-HMM" },
];

export default function App() {
  const [active, setActive] = useState("daniels");

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      {/* Header */}
      <header style={{
        borderBottom: "1px solid #21262d",
        padding: "12px 24px",
        display: "flex",
        alignItems: "center",
        gap: 24,
      }}>
        <span style={{ fontWeight: 800, fontSize: 18, color: "#58a6ff" }}>
          Stock Screener
        </span>
        <span style={{ color: "#444", fontSize: 13 }}>Multi-Strategy Screener</span>
        <nav style={{ display: "flex", gap: 4, marginLeft: "auto" }}>
          {STRATEGIES.map(s => (
            <button
              key={s.id}
              onClick={() => setActive(s.id)}
              style={{
                padding: "5px 14px",
                borderRadius: 6,
                border: "none",
                background: active === s.id ? "#21262d" : "transparent",
                color: active === s.id ? "#e6edf3" : "#8b949e",
                cursor: "pointer",
                fontWeight: 600,
                fontSize: 13,
              }}
            >
              {s.label}
            </button>
          ))}
        </nav>
      </header>

      {/* Main */}
      <main style={{ flex: 1, padding: "24px", maxWidth: 1200, width: "100%", margin: "0 auto" }}>
        {active === "turtle"    && <TurtleScreener />}
        {active === "minervini" && <MinerviniScreener />}
        {active === "daniels"   && <DanielsBreakoutScreener />}
      </main>
    </div>
  );
}
