"use client";

import { useMemo } from "react";
import type { FuturesOutcomeHistory } from "@/lib/types";

const DEFAULT_COLORS = [
  "#2563eb", // blue
  "#dc2626", // red
  "#16a34a", // green
  "#9333ea", // purple
  "#ea580c", // orange
  "#0891b2", // cyan
  "#be185d", // pink
  "#4f46e5", // indigo
];

const GOLD_COLORS = [
  "#D4AF37", // gold (leader)
  "#B8860B", // dark goldenrod
  "#6b7280", // gray-500
  "#9ca3af", // gray-400
  "#d1d5db", // gray-300
  "#6b7280",
  "#9ca3af",
  "#d1d5db",
];

interface FuturesChartProps {
  historyData: FuturesOutcomeHistory[];
  selectedOutcomes?: Set<number>;
  onToggleOutcome?: (id: number) => void;
  mini?: boolean;
  height?: number;
  showLegend?: boolean;
  showAxes?: boolean;
  goldTheme?: boolean;
  className?: string;
}

export function FuturesChart({
  historyData,
  selectedOutcomes,
  onToggleOutcome,
  mini = false,
  height,
  showLegend,
  showAxes,
  goldTheme = false,
  className,
}: FuturesChartProps) {
  const effectiveShowLegend = showLegend ?? !mini;
  const effectiveShowAxes = showAxes ?? !mini;
  const colors = goldTheme ? GOLD_COLORS : DEFAULT_COLORS;

  // Filter to selected outcomes, or show top 5 if none selected
  const displayedOutcomes = useMemo(() => {
    if (selectedOutcomes && selectedOutcomes.size > 0) {
      return historyData.filter((o) => selectedOutcomes.has(o.outcome_id));
    }
    return historyData.slice(0, 5);
  }, [historyData, selectedOutcomes]);

  if (displayedOutcomes.length === 0) {
    if (mini) return null;
    return (
      <div className="h-48 flex items-center justify-center text-sm text-text-secondary">
        Select outcomes below to see their probability trends
      </div>
    );
  }

  // Find time range and probability range
  let minTime = Infinity;
  let maxTime = -Infinity;
  let maxProb = 0;

  for (const outcome of displayedOutcomes) {
    for (const point of outcome.history) {
      const time = new Date(point.timestamp).getTime();
      if (time < minTime) minTime = time;
      if (time > maxTime) maxTime = time;
      if (point.probability !== null && point.probability > maxProb) {
        maxProb = point.probability;
      }
    }
  }

  if (minTime === Infinity || maxTime === -Infinity || maxTime === minTime) {
    return null;
  }

  maxProb = Math.min(1, maxProb * 1.1);

  const chartWidth = mini ? 400 : 800;
  const effectiveHeight = height ?? (mini ? 80 : 200);
  const padding = mini
    ? { top: 4, right: 4, bottom: 4, left: 4 }
    : { top: 20, right: 20, bottom: 40, left: 50 };
  const innerWidth = chartWidth - padding.left - padding.right;
  const innerHeight = effectiveHeight - padding.top - padding.bottom;

  const xScale = (time: number) =>
    padding.left + ((time - minTime) / (maxTime - minTime)) * innerWidth;

  const yScale = (prob: number) =>
    padding.top + (1 - prob / maxProb) * innerHeight;

  return (
    <div className={`${mini ? "" : "space-y-4"} ${className ?? ""}`}>
      <div className={mini ? "" : "overflow-x-auto"}>
        <svg
          viewBox={`0 0 ${chartWidth} ${effectiveHeight}`}
          className={mini ? "w-full" : "w-full min-w-[600px]"}
          style={{ maxHeight: mini ? `${effectiveHeight}px` : "250px" }}
        >
          {/* Y-axis grid lines */}
          {effectiveShowAxes &&
            [0, 0.25, 0.5, 0.75, 1].map((pct) => (
              <g key={pct}>
                <line
                  x1={padding.left}
                  y1={yScale(maxProb * pct)}
                  x2={chartWidth - padding.right}
                  y2={yScale(maxProb * pct)}
                  stroke="#e5e7eb"
                  strokeDasharray="4"
                />
                <text
                  x={padding.left - 8}
                  y={yScale(maxProb * pct)}
                  textAnchor="end"
                  dominantBaseline="middle"
                  className="text-xs fill-slate"
                >
                  {Math.round(maxProb * pct * 100)}%
                </text>
              </g>
            ))}

          {/* X-axis time labels */}
          {effectiveShowAxes &&
            (() => {
              const timeRange = maxTime - minTime;
              const tickCount = Math.min(
                5,
                Math.max(2, Math.floor(innerWidth / 150))
              );
              const ticks: number[] = [];
              for (let i = 0; i <= tickCount; i++) {
                ticks.push(minTime + (timeRange * i) / tickCount);
              }

              const formatTime = (ts: number) => {
                const d = new Date(ts);
                if (timeRange < 24 * 60 * 60 * 1000) {
                  return d.toLocaleTimeString("en-US", {
                    hour: "numeric",
                    minute: "2-digit",
                  });
                } else if (timeRange < 7 * 24 * 60 * 60 * 1000) {
                  return (
                    d.toLocaleDateString("en-US", {
                      month: "short",
                      day: "numeric",
                    }) +
                    " " +
                    d.toLocaleTimeString("en-US", { hour: "numeric" })
                  );
                } else {
                  return d.toLocaleDateString("en-US", {
                    month: "short",
                    day: "numeric",
                  });
                }
              };

              return ticks.map((t, i) => (
                <g key={`x-${i}`}>
                  <line
                    x1={xScale(t)}
                    y1={padding.top + innerHeight}
                    x2={xScale(t)}
                    y2={padding.top + innerHeight + 4}
                    stroke="#94a3b8"
                  />
                  <text
                    x={xScale(t)}
                    y={padding.top + innerHeight + 16}
                    textAnchor="middle"
                    className="text-xs fill-slate"
                    style={{ fontSize: "9px" }}
                  >
                    {formatTime(t)}
                  </text>
                </g>
              ));
            })()}

          {/* Lines */}
          {displayedOutcomes.map((outcome, idx) => {
            const points = outcome.history
              .filter((p) => p.probability !== null)
              .map((p) => ({
                x: xScale(new Date(p.timestamp).getTime()),
                y: yScale(p.probability!),
              }));

            if (points.length < 2) return null;

            const pathD = points
              .map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`)
              .join(" ");

            return (
              <path
                key={outcome.outcome_id}
                d={pathD}
                fill="none"
                stroke={colors[idx % colors.length]}
                strokeWidth={mini ? 1.5 : 2}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            );
          })}
        </svg>
      </div>

      {/* Legend */}
      {effectiveShowLegend && onToggleOutcome && (
        <div className="flex flex-wrap gap-3">
          {displayedOutcomes.map((outcome, idx) => (
            <button
              key={outcome.outcome_id}
              onClick={() => onToggleOutcome(outcome.outcome_id)}
              className="flex items-center gap-2 text-sm hover:opacity-80 transition-opacity"
            >
              <span
                className="w-3 h-3 rounded-full"
                style={{ backgroundColor: colors[idx % colors.length] }}
              />
              <span className="text-text-primary">{outcome.name}</span>
            </button>
          ))}
        </div>
      )}

      {effectiveShowLegend &&
        selectedOutcomes &&
        selectedOutcomes.size === 0 && (
          <p className="text-xs text-text-secondary text-center">
            Showing top 5 outcomes. Check boxes below to compare specific
            outcomes.
          </p>
        )}
    </div>
  );
}
