"use client";

import type { WMHistoryPoint } from "@/lib/types";

interface OddsSparklineProps {
  history: WMHistoryPoint[];
  color: string;
  width?: number;
  height?: number;
}

export default function OddsSparkline({
  history,
  color,
  width = 120,
  height = 40,
}: OddsSparklineProps) {
  if (history.length < 2) return null;

  const padding = 2;
  const w = width - padding * 2;
  const h = height - padding * 2;

  const probs = history.map((p) => p.p);
  const minP = Math.min(...probs) - 0.02;
  const maxP = Math.max(...probs) + 0.02;
  const range = maxP - minP || 0.1;

  const points = history.map((point, i) => {
    const x = padding + (i / (history.length - 1)) * w;
    const y = padding + h - ((point.p - minP) / range) * h;
    return `${x},${y}`;
  });

  const lastPoint = history[history.length - 1];
  const firstPoint = history[0];
  const delta = lastPoint.p - firstPoint.p;

  return (
    <div style={{ position: "relative", width, height }}>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        <polyline
          points={points.join(" ")}
          fill="none"
          stroke={color}
          strokeWidth={1.5}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {/* Glow effect */}
        <polyline
          points={points.join(" ")}
          fill="none"
          stroke={color}
          strokeWidth={3}
          strokeLinecap="round"
          strokeLinejoin="round"
          opacity={0.3}
        />
        {/* Current value dot */}
        <circle
          cx={parseFloat(points[points.length - 1].split(",")[0])}
          cy={parseFloat(points[points.length - 1].split(",")[1])}
          r={3}
          fill={color}
        />
      </svg>
      {Math.abs(delta) > 0.005 && (
        <span
          style={{
            position: "absolute",
            bottom: 0,
            right: 0,
            fontSize: "0.55rem",
            color: delta > 0 ? "#00E5FF" : "#FF2E93",
            fontFamily: "'Space Mono', monospace",
          }}
        >
          {delta > 0 ? "▲" : "▼"}
          {Math.abs(Math.round(delta * 100))}%
        </span>
      )}
    </div>
  );
}
