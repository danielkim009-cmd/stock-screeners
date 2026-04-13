const colors = {
  S2_BUY: { bg: "#1a3a1a", border: "#2ea043", text: "#56d364" },
  S1_BUY: { bg: "#1a2d1a", border: "#3fb950", text: "#7ee787" },
  NONE:   { bg: "#1c1c1c", border: "#444", text: "#888" },
};

export default function SignalBadge({ signal }) {
  const c = colors[signal] ?? colors.NONE;
  return (
    <span style={{
      padding: "2px 8px",
      borderRadius: 4,
      border: `1px solid ${c.border}`,
      background: c.bg,
      color: c.text,
      fontWeight: 600,
      fontSize: 12,
    }}>
      {signal}
    </span>
  );
}
