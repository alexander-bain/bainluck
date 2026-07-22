"use client";

import { useMemo } from "react";
import { plotDims, scaleX, scaleY } from "@/lib/chartScale";

const SOURCE_COLORS: Record<string, string> = {
  betting: "#374151",
  espn: "#f97316",
  stat_model: "#8b5cf6",
  kalshi: "#22c55e",
  polymarket: "#3b82f6",
  mlb: "#06b6d4",
};

const SOURCE_LABELS: Record<string, string> = {
  betting: "Betting",
  espn: "ESPN",
  stat_model: "Model",
  kalshi: "Kalshi",
  polymarket: "Polymarket",
  mlb: "MLB",
};

interface DisagreementChartProps {
  timeSeries: Record<string, { t: string; p: number }[]>;
  homeWon: boolean;
  homeTeam: string;
  awayTeam: string;
  width?: number;
  height?: number;
}

export default function DisagreementChart({
  timeSeries,
  homeWon,
  homeTeam,
  awayTeam,
  width = 560,
  height = 280,
}: DisagreementChartProps) {
  const padL = 50, padR = 20, padT = 20, padB = 50;
  const { plotW, plotH } = plotDims(width, height, { padL, padR, padT, padB });

  const { sources, tMin, tMax } = useMemo(() => {
    const entries = Object.entries(timeSeries).filter(([, pts]) => pts.length > 0);
    let min = Infinity, max = -Infinity;
    for (const [, pts] of entries) {
      for (const pt of pts) {
        const t = new Date(pt.t).getTime();
        if (t < min) min = t;
        if (t > max) max = t;
      }
    }
    return { sources: entries, tMin: min, tMax: max };
  }, [timeSeries]);

  if (sources.length === 0 || tMin === tMax) return null;

  // X is time (tMin→tMax), Y is fixed 0–1 probability. Shared px/py skeleton — see lib/chartScale.ts.
  const px = scaleX(tMin, tMax, padL, plotW);
  const py = scaleY(0, 1, padT, plotH);

  const durationHrs = (tMax - tMin) / 3600000;
  const tickCount = Math.min(6, Math.max(3, Math.floor(durationHrs)));
  const tTicks = Array.from({ length: tickCount + 1 }, (_, i) =>
    tMin + (i / tickCount) * (tMax - tMin)
  );

  const formatTime = (t: number) => {
    const d = new Date(t);
    return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
  };

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="block mx-auto"
      style={{ fontFamily: "-apple-system, system-ui, sans-serif", maxWidth: "100%" }}
    >
      <rect width={width} height={height} fill="white" rx="8" />

      {/* Horizontal grid lines */}
      {[0, 0.25, 0.5, 0.75, 1].map(v => (
        <g key={v}>
          <line x1={padL} y1={py(v)} x2={width - padR} y2={py(v)}
            stroke={v === 0.5 ? "#e2e8f0" : "#f0f0f0"} strokeWidth={v === 0.5 ? 1.5 : 1}
            strokeDasharray={v === 0.5 ? "4,3" : undefined} />
          <text x={padL - 8} y={py(v) + 4} textAnchor="end" fill="#a8a29e" fontSize="10">
            {Math.round(v * 100)}%
          </text>
        </g>
      ))}

      {/* Time axis */}
      {tTicks.map((t, i) => (
        <g key={i}>
          <line x1={px(t)} y1={padT} x2={px(t)} y2={height - padB} stroke="#f5f5f4" strokeWidth="1" />
          <text x={px(t)} y={height - padB + 16} textAnchor="middle" fill="#a8a29e" fontSize="10">
            {formatTime(t)}
          </text>
        </g>
      ))}

      {/* Outcome indicator */}
      <line
        x1={padL} y1={py(homeWon ? 1 : 0)} x2={width - padR} y2={py(homeWon ? 1 : 0)}
        stroke="#10b981" strokeWidth="1.5" strokeDasharray="6,4" opacity="0.5"
      />
      <text x={width - padR - 4} y={py(homeWon ? 1 : 0) + (homeWon ? -6 : 14)}
        textAnchor="end" fill="#10b981" fontSize="9" fontWeight="600">
        {homeWon ? homeTeam : awayTeam} won
      </text>

      {/* Source lines */}
      {sources.map(([source, pts]) => {
        const color = SOURCE_COLORS[source] || "#6b7280";
        const points = pts.map(pt => {
          const t = new Date(pt.t).getTime();
          return `${px(t)},${py(pt.p)}`;
        }).join(" ");
        return (
          <polyline
            key={source}
            points={points}
            fill="none"
            stroke={color}
            strokeWidth="2"
            strokeLinejoin="round"
            strokeLinecap="round"
            opacity="0.85"
          />
        );
      })}

      {/* Y-axis labels */}
      <text
        x="12" y={height / 2} textAnchor="middle" fill="#78716c" fontSize="10" fontWeight="600"
        transform={`rotate(-90,12,${height / 2})`}
      >
        {homeTeam} Win Prob
      </text>

      {/* Legend */}
      <g>
        {sources.map(([source], i) => {
          const color = SOURCE_COLORS[source] || "#6b7280";
          const lx = padL + 8 + i * 90;
          const ly = height - 6;
          return (
            <g key={source}>
              <line x1={lx} y1={ly} x2={lx + 14} y2={ly} stroke={color} strokeWidth="2.5" />
              <text x={lx + 18} y={ly + 3.5} fill="#57534e" fontSize="9">
                {SOURCE_LABELS[source] || source}
              </text>
            </g>
          );
        })}
      </g>
    </svg>
  );
}
