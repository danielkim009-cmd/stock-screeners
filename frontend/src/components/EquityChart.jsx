import { useEffect, useRef } from "react";
import { createChart } from "lightweight-charts";

export default function EquityChart({ data, bhReturnPct, bhCurve, height = 220 }) {
  const containerRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current || !data || data.length === 0) return;

    const chart = createChart(containerRef.current, {
      layout: { background: { color: "#0d1117" }, textColor: "#e6edf3" },
      grid: { vertLines: { color: "#21262d" }, horzLines: { color: "#21262d" } },
      rightPriceScale: { borderColor: "#30363d" },
      timeScale: { borderColor: "#30363d", timeVisible: true },
      width: containerRef.current.clientWidth,
      height,
    });

    // Strategy equity curve
    const strategySeries = chart.addLineSeries({
      color: "#58a6ff",
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
      title: "Strategy",
    });
    strategySeries.setData(data.map(d => ({ time: d.date, value: d.value })));

    // Buy & hold reference line
    if (bhCurve && bhCurve.length >= 2) {
      // Real daily curve (e.g. SPY) passed from the portfolio backtest
      const bhSeries = chart.addLineSeries({
        color: "#8b949e",
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: true,
        title: "B&H",
      });
      bhSeries.setData(bhCurve.map(d => ({ time: d.date, value: d.value })));
    } else if (bhReturnPct != null && data.length >= 2) {
      // Fallback: straight line from start to end
      const startVal = data[0].value;
      const endVal   = startVal * (1 + bhReturnPct / 100);
      const bhSeries = chart.addLineSeries({
        color: "#8b949e",
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
        title: "B&H",
      });
      bhSeries.setData([
        { time: data[0].date,               value: startVal },
        { time: data[data.length - 1].date, value: endVal },
      ]);
    }

    chart.timeScale().fitContent();

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, [data, bhReturnPct, bhCurve, height]);

  return <div ref={containerRef} style={{ width: "100%", borderRadius: 6, overflow: "hidden" }} />;
}
