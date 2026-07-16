"use client";

import { useMemo, useState } from "react";
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

const GREEN_COLORS = [
  "#006747", // Augusta green (leader)
  "#2d8659", // lighter green
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
  greenTheme?: boolean;
  className?: string;
  /** Use step interpolation (hold value until next point) for sparse data */
  stepInterpolation?: boolean;
  /** Pin the y-axis to a fixed 0–100% domain (#883 blend-line principle: the
   *  futures-detail blend chart never rescales to the data max — movement stays
   *  honestly proportional). Default false preserves the auto-scaled behavior
   *  other surfaces (e.g. golf) rely on. */
  fixedYAxis?: boolean;
  /** L2-135: vertical state markers giving the time axis a real sense of time —
   *  golf round boundaries (R1/R2/R3/R4), the settled-page state-marker language
   *  applied to the evolution chart. Each marker is a dashed line + top label,
   *  clipped to the chart's visible [minTime, maxTime] window. Opt-in: undefined
   *  = no markers (every non-golf surface is unaffected). Times are epoch ms. */
  timeMarkers?: { time: number; label: string }[];
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
  greenTheme = false,
  className,
  stepInterpolation = false,
  fixedYAxis = false,
  timeMarkers,
}: FuturesChartProps) {
  const effectiveShowLegend = showLegend ?? !mini;
  const effectiveShowAxes = showAxes ?? !mini;
  const colors = greenTheme ? GREEN_COLORS : goldTheme ? GOLD_COLORS : DEFAULT_COLORS;

  // Filter to selected outcomes, or show top 5 if none selected
  const displayedOutcomes = useMemo(() => {
    if (selectedOutcomes && selectedOutcomes.size > 0) {
      return historyData.filter((o) => selectedOutcomes.has(o.outcome_id));
    }
    return historyData.slice(0, 5);
  }, [historyData, selectedOutcomes]);

  // Hover tooltip state (non-mini only) — must be before any early returns
  const [hoverInfo, setHoverInfo] = useState<{
    svgX: number;
    time: number;
    values: { name: string; prob: number; color: string }[];
  } | null>(null);

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

  // Check total data points across all displayed outcomes
  const totalPoints = displayedOutcomes.reduce(
    (sum, o) => sum + o.history.filter((p) => p.probability !== null).length,
    0
  );

  if (minTime === Infinity || maxTime === -Infinity || maxTime === minTime || totalPoints < 2) {
    if (mini) return null;
    return (
      <div className="h-32 flex flex-col items-center justify-center gap-2 text-sm text-text-secondary">
        <svg className="w-5 h-5 text-text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
        </svg>
        <span>Limited price history available</span>
        <span className="text-xs text-text-muted">
          Prices update every 1{"–"}2 hours for this market
        </span>
      </div>
    );
  }

  maxProb = fixedYAxis ? 1 : Math.min(1, maxProb * 1.1);

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

  // Hover handler for interactive tooltip
  function handleChartHover(e: React.MouseEvent<SVGSVGElement>) {
    const svg = e.currentTarget;
    const rect = svg.getBoundingClientRect();
    const svgX = ((e.clientX - rect.left) / rect.width) * chartWidth;
    if (svgX < padding.left || svgX > chartWidth - padding.right) {
      setHoverInfo(null);
      return;
    }
    const time =
      minTime + ((svgX - padding.left) / innerWidth) * (maxTime - minTime);
    const values = displayedOutcomes
      .map((outcome, idx) => {
        let best: number | null = null;
        let bestDist = Infinity;
        for (const pt of outcome.history) {
          if (pt.probability === null) continue;
          const d = Math.abs(new Date(pt.timestamp).getTime() - time);
          if (d < bestDist) {
            bestDist = d;
            best = pt.probability;
          }
        }
        return best !== null
          ? {
              name: outcome.name,
              prob: best,
              color: colors[idx % colors.length],
            }
          : null;
      })
      .filter((v): v is NonNullable<typeof v> => v !== null)
      .sort((a, b) => b.prob - a.prob);
    setHoverInfo({ svgX, time, values });
  }

  function formatTooltipTime(ts: number): string {
    const d = new Date(ts);
    const range = maxTime - minTime;
    if (range < 24 * 60 * 60 * 1000) {
      return d.toLocaleTimeString("en-US", {
        hour: "numeric",
        minute: "2-digit",
      });
    }
    return (
      d.toLocaleDateString("en-US", { month: "short", day: "numeric" }) +
      " " +
      d.toLocaleTimeString("en-US", { hour: "numeric" })
    );
  }

  return (
    <div className={`${mini ? "" : "space-y-4"} ${className ?? ""}`}>
      <div className={mini ? "" : "overflow-x-auto relative"}>
        <svg
          viewBox={`0 0 ${chartWidth} ${effectiveHeight}`}
          className={mini ? "w-full" : "w-full min-w-[600px]"}
          style={{
            maxHeight: mini ? `${effectiveHeight}px` : "250px",
            cursor: mini ? undefined : "crosshair",
          }}
          onMouseMove={mini ? undefined : handleChartHover}
          onMouseLeave={mini ? undefined : () => setHoverInfo(null)}
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

          {/* L2-135: round/state boundary markers — dashed verticals + top labels
              (R1/R2/R3/R4) giving the axis a real sense of time. Clipped to the
              visible window; skipped in mini mode. */}
          {!mini &&
            effectiveShowAxes &&
            timeMarkers?.map((m, i) =>
              m.time < minTime || m.time > maxTime ? null : (
                <g key={`marker-${i}`}>
                  <line
                    x1={xScale(m.time)}
                    y1={padding.top}
                    x2={xScale(m.time)}
                    y2={padding.top + innerHeight}
                    stroke="#cbd5e1"
                    strokeDasharray="4 3"
                    strokeWidth={1}
                  />
                  <text
                    x={xScale(m.time) + 3}
                    y={padding.top + 10}
                    textAnchor="start"
                    className="fill-slate"
                    style={{ fontSize: "9px", fontWeight: 600 }}
                  >
                    {m.label}
                  </text>
                </g>
              ),
            )}

          {/* Lines */}
          {displayedOutcomes.map((outcome, idx) => {
            const points = outcome.history
              .filter((p) => p.probability !== null)
              .map((p) => ({
                x: xScale(new Date(p.timestamp).getTime()),
                y: yScale(p.probability!),
              }));

            if (points.length < 2) return null;

            const pathD = stepInterpolation
              ? points
                  .map((p, i) =>
                    i === 0
                      ? `M ${p.x} ${p.y}`
                      : `H ${p.x} V ${p.y}`
                  )
                  .join(" ")
              : points
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

          {/* Hover crosshair and dots */}
          {hoverInfo && !mini && (
            <>
              <line
                x1={hoverInfo.svgX}
                y1={padding.top}
                x2={hoverInfo.svgX}
                y2={padding.top + innerHeight}
                stroke={greenTheme ? "#006747" : goldTheme ? "#D4AF37" : "#94a3b8"}
                strokeWidth={1}
                strokeDasharray="4 2"
                opacity={0.6}
              />
              {hoverInfo.values.map((v, i) => (
                <circle
                  key={i}
                  cx={hoverInfo.svgX}
                  cy={yScale(v.prob)}
                  r={4}
                  fill={v.color}
                  stroke={greenTheme ? "#e6f7ef" : goldTheme ? "#fef9e7" : "#FFFFFF"}
                  strokeWidth={2}
                />
              ))}
            </>
          )}
        </svg>

        {/* Hover tooltip */}
        {hoverInfo && !mini && (
          <div
            className="absolute pointer-events-none z-50"
            style={{
              left: `${(hoverInfo.svgX / chartWidth) * 100}%`,
              top: 0,
              transform:
                hoverInfo.svgX > chartWidth * 0.6
                  ? "translateX(-105%)"
                  : "translateX(5%)",
            }}
          >
            <div className="bg-surface-deep/95 backdrop-blur-sm rounded-lg px-3 py-2 border border-surface-border shadow-lg min-w-[140px]">
              <div className="text-[10px] text-text-muted mb-1 font-mono">
                {formatTooltipTime(hoverInfo.time)}
              </div>
              {hoverInfo.values.map((v, i) => (
                <div key={i} className="flex items-center gap-2 py-0.5">
                  <span
                    className="w-2 h-2 rounded-full flex-shrink-0"
                    style={{ backgroundColor: v.color }}
                  />
                  <span className="text-[11px] text-text-secondary truncate max-w-[120px]">
                    {v.name}
                  </span>
                  <span className="text-[11px] font-mono font-bold text-text-primary ml-auto pl-2">
                    {Math.round(v.prob * 100)}%
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
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
