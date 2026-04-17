import { useEffect, useRef } from "react";
import { createChart, CrosshairMode } from "lightweight-charts";

function fmtVolLocal(v) {
  if (v == null) return "—";
  if (v >= 1e9) return (v / 1e9).toFixed(1) + "B";
  if (v >= 1e6) return (v / 1e6).toFixed(1) + "M";
  if (v >= 1e3) return (v / 1e3).toFixed(1) + "K";
  return String(Math.round(v));
}

// markers:   optional array of { date, type: 'entry'|'exit', pnl }
// showVolume: render volume histogram in lower pane
// trimStart:  leading bars used only for SMA warm-up; candles/volume start after them
export default function CandlestickChart({ data, markers, showVolume = false, trimStart = 0 }) {
  const containerRef = useRef(null);
  const chartRef = useRef(null);
  const tooltipRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current || !data || data.length === 0) return;

    const chart = createChart(containerRef.current, {
      layout: { background: { color: "#0d1117" }, textColor: "#e6edf3" },
      grid: {
        vertLines: { color: "#21262d" },
        horzLines: { color: "#21262d" },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: "#30363d" },
      timeScale: { borderColor: "#30363d", timeVisible: true },
      width: containerRef.current.clientWidth,
      height: showVolume ? 380 : 320,
    });

    chartRef.current = chart;

    const candleSeries = chart.addCandlestickSeries({
      upColor: "#56d364",
      downColor: "#f85149",
      borderUpColor: "#56d364",
      borderDownColor: "#f85149",
      wickUpColor: "#56d364",
      wickDownColor: "#f85149",
    });

    if (showVolume) {
      candleSeries.priceScale().applyOptions({
        scaleMargins: { top: 0.05, bottom: 0.25 },
      });
    }

    const formatted = data.map(d => ({
      time: d.date,
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    }));

    // Candles only shown from trimStart onwards; all data used for SMA warm-up
    candleSeries.setData(formatted.slice(trimStart));

    // Build date → volume and date → previous close lookups (used by tooltip)
    const volumeMap = {};
    const prevCloseMap = {};
    data.forEach((d, i) => {
      volumeMap[d.date] = d.volume;
      if (i > 0) prevCloseMap[d.date] = data[i - 1].close;
    });

    if (showVolume) {
      const volSeries = chart.addHistogramSeries({
        priceFormat: { type: "volume" },
        priceScaleId: "vol",
        lastValueVisible: false,
        priceLineVisible: false,
      });
      volSeries.priceScale().applyOptions({
        scaleMargins: { top: 0.8, bottom: 0 },
      });
      volSeries.setData(data.slice(trimStart).map(d => ({
        time: d.date,
        value: d.volume,
        color: d.close >= d.open ? "#56d36466" : "#f8514966",
      })));
    }

    // Trade markers (entry / exit)
    if (markers && markers.length > 0) {
      const sorted = [...markers].sort((a, b) => a.date.localeCompare(b.date));
      candleSeries.setMarkers(sorted.map(m => ({
        time: m.date,
        position: m.type === "entry" ? "belowBar" : "aboveBar",
        shape:    m.type === "entry" ? "arrowUp"  : "arrowDown",
        color:    m.type === "entry" ? "#58a6ff"  : (m.pnl > 0 ? "#56d364" : "#f85149"),
        text:     m.type === "entry" ? "B"        : "S",
        size: 1,
      })));
    }

    // ── Helper: compute EMA series ─────────────────────────────────────────────
    function computeEma(period, visibleFrom) {
      const k = 2 / (period + 1);
      const result = [];
      let ema = null;
      for (let i = 0; i < formatted.length; i++) {
        const close = formatted[i].close;
        ema = ema === null ? close : close * k + ema * (1 - k);
        if (i >= visibleFrom) {
          result.push({ time: formatted[i].time, value: ema });
        }
      }
      return result;
    }

    // EMA50
    const sma50Series = chart.addLineSeries({
      color: "#e3b341",
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    sma50Series.setData(computeEma(50, Math.max(49, trimStart)));

    // EMA21
    const ema21Series = chart.addLineSeries({
      color: "#58a6ff",
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    const ema21Data = computeEma(21, Math.max(20, trimStart));
    ema21Series.setData(ema21Data);

    // EMA100
    const ema100Series = chart.addLineSeries({
      color: "#bc8cff",
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    const ema100Data = computeEma(100, Math.max(99, trimStart));
    ema100Series.setData(ema100Data);

    chart.timeScale().fitContent();

    // ── Crosshair tooltip ──────────────────────────────────────────────────────
    const tooltip = tooltipRef.current;

    chart.subscribeCrosshairMove(param => {
      if (!tooltip) return;
      if (!param.point || !param.time) {
        tooltip.style.display = "none";
        return;
      }
      const candle = param.seriesData.get(candleSeries);
      if (!candle) {
        tooltip.style.display = "none";
        return;
      }

      const prevClose = prevCloseMap[param.time];
      const base = prevClose ?? candle.open;
      const chg = candle.close - base;
      const chgPct = base !== 0 ? (chg / base) * 100 : 0;
      const isUp = chg >= 0;
      const priceColor = isUp ? "#56d364" : "#f85149";
      const vol = volumeMap[param.time];

      const ema21Val = param.seriesData.get(ema21Series);
      const ema50Val = param.seriesData.get(sma50Series);
      const ema100Val = param.seriesData.get(ema100Series);

      tooltip.innerHTML =
        `<span style="color:#8b949e;margin-right:10px">${param.time}</span>` +
        `<span style="color:#8b949e;margin-right:3px">O</span><span style="margin-right:10px">${candle.open.toFixed(2)}</span>` +
        `<span style="color:#8b949e;margin-right:3px">H</span><span style="margin-right:10px">${candle.high.toFixed(2)}</span>` +
        `<span style="color:#8b949e;margin-right:3px">L</span><span style="margin-right:10px">${candle.low.toFixed(2)}</span>` +
        `<span style="color:#8b949e;margin-right:3px">C</span><span style="color:${priceColor};font-weight:700;margin-right:10px">${candle.close.toFixed(2)}</span>` +
        `<span style="color:${priceColor};margin-right:10px">${chg >= 0 ? "+" : ""}${chg.toFixed(2)} (${chg >= 0 ? "+" : ""}${chgPct.toFixed(2)}%)</span>` +
        (vol != null ? `<span style="color:#8b949e;margin-right:3px">Vol</span><span style="margin-right:10px">${fmtVolLocal(vol)}</span>` : "") +
        (ema21Val != null ? `<span style="color:#58a6ff;margin-right:3px">EMA21</span><span style="color:#58a6ff;margin-right:10px">${ema21Val.value.toFixed(2)}</span>` : "") +
        (ema50Val != null ? `<span style="color:#e3b341;margin-right:3px">EMA50</span><span style="color:#e3b341;margin-right:10px">${ema50Val.value.toFixed(2)}</span>` : "") +
        (ema100Val != null ? `<span style="color:#bc8cff;margin-right:3px">EMA100</span><span style="color:#bc8cff">${ema100Val.value.toFixed(2)}</span>` : "");

      tooltip.style.left = "0";
      tooltip.style.top = "0";
      tooltip.style.width = "100%";
      tooltip.style.display = "flex";
      tooltip.style.alignItems = "center";
    });
    // ──────────────────────────────────────────────────────────────────────────

    const handleResize = () => {
      chart.applyOptions({ width: containerRef.current.clientWidth });
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, [data, markers]);

  return (
    <div ref={containerRef} style={{ position: "relative", width: "100%", borderRadius: 6, overflow: "hidden" }}>
      <div
        ref={tooltipRef}
        style={{
          display: "none",
          position: "absolute",
          top: 0,
          left: 0,
          width: "100%",
          zIndex: 10,
          background: "#0d1117cc",
          borderBottom: "1px solid #21262d",
          padding: "4px 10px",
          fontSize: 12,
          pointerEvents: "none",
          flexWrap: "wrap",
          gap: "0 4px",
        }}
      />
    </div>
  );
}
