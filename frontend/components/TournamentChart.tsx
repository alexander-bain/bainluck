"use client";

import { useState, useMemo } from "react";
import useSWR from "swr";
import { fetchProbabilityTimeline } from "@/lib/api";
import type { ProbabilityTimelineResponse, TimelineEntry } from "@/lib/types";

/** Position-based color palette: leader vivid, others progressively lighter */
const POSITION_COLORS = [
  "#2563eb", // 1st — vivid blue
  "#dc2626", // 2nd — red
  "#16a34a", // 3rd — green
  "#9333ea", // 4th — purple
  "#ea580c", // 5th — orange
  "#0891b2", // 6th — cyan
  "#be185d", // 7th — pink
  "#4f46e5", // 8th — indigo
  "#ca8a04", // 9th — amber
  "#0d9488", // 10th — teal
];

const FIELD_COLOR = "#6b7280"; // gray-500

type TopFilter = 5 | 10 | "all";

interface TournamentChartProps {
  marketId: number;
  /** Hours of history to fetch (default 168 = 7 days) */
  hours?: number;
  /** Chart height in px (default 280) */
  height?: number;
  /** Optional CSS class */
  className?: string;
  /** Anchor ID for deep-linking from category pages */
  id?: string;
}

export default function TournamentChart({
  marketId,
  hours = 168,
  height = 280,
  className,
  id,
}: TournamentChartProps) {
  const [topFilter, setTopFilter] = useState<TopFilter>(5);

  // Fetch with top=50 to get all outcomes, then filter client-side
  const { data, error, isLoading } = useSWR(
    `tournament-timeline-${marketId}-${hours}`,
    () => fetchProbabilityTimeline(marketId, 50, hours),
    { revalidateOnFocus: false, dedupingInterval: 60_000 }
  );

  // Derive the filtered outcomes and timeline based on topFilter
  const { displayedNames, hasField, chartData } = useMemo(() => {
    if (!data || data.timeline.length === 0) {
      return { displayedNames: [] as string[], hasField: false, chartData: [] as TimelineEntry[] };
    }

    const allOutcomes = data.outcomes;
    const topN = topFilter === "all" ? allOutcomes.length : topFilter;
    const topOutcomes = allOutcomes.filter((o) => o.name !== "Field").slice(0, topN);
    const topNames = new Set(topOutcomes.map((o) => o.name));
    const showField = topFilter !== "all" && allOutcomes.length > topN;

    // Re-aggregate timeline: keep top N + compute Field from the rest
    const filteredTimeline: TimelineEntry[] = data.timeline.map((entry) => {
      const outcomes: Record<string, number> = {};
      let fieldProb = 0;

      for (const [name, prob] of Object.entries(entry.outcomes)) {
        if (name === "Field") {
          // If the server already computed Field for different top, we need
          // to re-aggregate from scratch. But we fetched top=50, so most
          // outcomes are individually available.
          continue;
        }
        if (topNames.has(name)) {
          outcomes[name] = prob;
        } else if (showField) {
          fieldProb += prob;
        }
      }

      // Also include server-side Field probabilities for outcomes beyond top 50
      if (showField && entry.outcomes.Field !== undefined) {
        // Server Field covers outcomes #51+, add to our client Field
        fieldProb += entry.outcomes.Field;
      }

      if (showField && fieldProb > 0) {
        outcomes["Field"] = fieldProb;
      }

      return { timestamp: entry.timestamp, outcomes };
    });

    return {
      displayedNames: topOutcomes.map((o) => o.name),
      hasField: showField,
      chartData: filteredTimeline,
    };
  }, [data, topFilter]);

  // SVG chart dimensions
  const chartWidth = 800;
  const padding = { top: 20, right: 120, bottom: 40, left: 55 };
  const innerWidth = chartWidth - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;

  // Compute time and probability ranges
  const { minTime, maxTime, maxProb, xScale, yScale } = useMemo(() => {
    if (chartData.length === 0) {
      return {
        minTime: 0,
        maxTime: 1,
        maxProb: 1,
        xScale: () => 0,
        yScale: () => 0,
      };
    }

    let mn = Infinity;
    let mx = -Infinity;
    let mp = 0;

    for (const entry of chartData) {
      const t = new Date(entry.timestamp).getTime();
      if (t < mn) mn = t;
      if (t > mx) mx = t;
      for (const prob of Object.values(entry.outcomes)) {
        if (prob > mp) mp = prob;
      }
    }

    // Pad the max probability by 10%
    mp = Math.min(1, mp * 1.1);
    if (mp < 0.05) mp = 0.05; // minimum ceiling

    const xs = (time: number) =>
      padding.left + ((time - mn) / (mx - mn || 1)) * innerWidth;
    const ys = (prob: number) =>
      padding.top + (1 - prob / mp) * innerHeight;

    return { minTime: mn, maxTime: mx, maxProb: mp, xScale: xs, yScale: ys };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chartData, innerWidth, innerHeight]);

  // Hover state
  const [hoverInfo, setHoverInfo] = useState<{
    svgX: number;
    time: number;
    values: { name: string; prob: number; color: string }[];
  } | null>(null);

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

    // Find closest time bucket
    let closestEntry: TimelineEntry | null = null;
    let closestDist = Infinity;
    for (const entry of chartData) {
      const d = Math.abs(new Date(entry.timestamp).getTime() - time);
      if (d < closestDist) {
        closestDist = d;
        closestEntry = entry;
      }
    }

    if (!closestEntry) {
      setHoverInfo(null);
      return;
    }

    const values: { name: string; prob: number; color: string }[] = [];
    for (let i = 0; i < displayedNames.length; i++) {
      const name = displayedNames[i];
      const prob = closestEntry.outcomes[name];
      if (prob !== undefined) {
        values.push({
          name,
          prob,
          color: POSITION_COLORS[i % POSITION_COLORS.length],
        });
      }
    }
    if (hasField && closestEntry.outcomes.Field !== undefined) {
      values.push({
        name: "Field",
        prob: closestEntry.outcomes.Field,
        color: FIELD_COLOR,
      });
    }

    values.sort((a, b) => b.prob - a.prob);
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

  // Render
  if (isLoading) {
    return (
      <div className={`h-48 flex items-center justify-center text-sm text-text-secondary ${className ?? ""}`}>
        Loading timeline...
      </div>
    );
  }

  if (error || !data) {
    return null; // Silently hide if endpoint fails or no data
  }

  if (chartData.length < 2 || displayedNames.length === 0) {
    return null; // Not enough data to chart
  }

  // Build SVG path data for each outcome
  const allNames = [...displayedNames, ...(hasField ? ["Field"] : [])];

  function buildPath(name: string): string | null {
    const points: { x: number; y: number }[] = [];
    for (const entry of chartData) {
      const prob = entry.outcomes[name];
      if (prob !== undefined) {
        points.push({
          x: xScale(new Date(entry.timestamp).getTime()),
          y: yScale(prob),
        });
      }
    }
    if (points.length < 2) return null;
    return points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ");
  }

  // Build Field area path (fill under the line)
  function buildFieldAreaPath(): string | null {
    if (!hasField) return null;
    const points: { x: number; y: number }[] = [];
    for (const entry of chartData) {
      const prob = entry.outcomes.Field;
      if (prob !== undefined) {
        points.push({
          x: xScale(new Date(entry.timestamp).getTime()),
          y: yScale(prob),
        });
      }
    }
    if (points.length < 2) return null;
    const baseline = yScale(0);
    const linePath = points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ");
    const closePath = ` L ${points[points.length - 1].x} ${baseline} L ${points[0].x} ${baseline} Z`;
    return linePath + closePath;
  }

  return (
    <div id={id} className={`space-y-3 ${className ?? ""}`}>
      {/* Top filter toggle */}
      <div className="flex items-center gap-2">
        <span className="text-xs text-text-secondary">Show:</span>
        {([5, 10, "all"] as TopFilter[]).map((f) => (
          <button
            key={String(f)}
            onClick={() => setTopFilter(f)}
            className={`px-2.5 py-1 text-xs rounded-md transition-all duration-200 ${
              topFilter === f
                ? "bg-blue-600 text-white shadow-sm scale-105"
                : "bg-surface-elevated text-text-secondary hover:text-text-primary hover:bg-surface-border"
            }`}
          >
            {f === "all" ? "All" : `Top ${f}`}
          </button>
        ))}
      </div>

      {/* Chart */}
      <div className="overflow-x-auto relative">
        <svg
          viewBox={`0 0 ${chartWidth} ${height}`}
          className="w-full min-w-[600px]"
          style={{ maxHeight: `${height}px`, cursor: "crosshair" }}
          onMouseMove={handleChartHover}
          onMouseLeave={() => setHoverInfo(null)}
        >
          {/* Y-axis grid lines */}
          {[0, 0.25, 0.5, 0.75, 1].map((pct) => (
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
          {(() => {
            const timeRange = maxTime - minTime;
            const tickCount = Math.min(5, Math.max(2, Math.floor(innerWidth / 150)));
            const ticks: number[] = [];
            for (let i = 0; i <= tickCount; i++) {
              ticks.push(minTime + (timeRange * i) / tickCount);
            }

            const formatTime = (ts: number) => {
              const d = new Date(ts);
              if (timeRange < 24 * 60 * 60 * 1000) {
                return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
              } else if (timeRange < 7 * 24 * 60 * 60 * 1000) {
                return (
                  d.toLocaleDateString("en-US", { month: "short", day: "numeric" }) +
                  " " +
                  d.toLocaleTimeString("en-US", { hour: "numeric" })
                );
              } else {
                return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
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

          {/* Field area fill (dashed gray) */}
          {hasField && (() => {
            const areaPath = buildFieldAreaPath();
            if (!areaPath) return null;
            return (
              <path
                d={areaPath}
                fill={FIELD_COLOR}
                fillOpacity={0.08}
                stroke="none"
              />
            );
          })()}

          {/* Field line (dashed) */}
          {hasField && (() => {
            const d = buildPath("Field");
            if (!d) return null;
            return (
              <path
                d={d}
                fill="none"
                stroke={FIELD_COLOR}
                strokeWidth={1.5}
                strokeDasharray="6 3"
                strokeLinecap="round"
                opacity={0.5}
              />
            );
          })()}

          {/* Outcome lines (from last to first so leader renders on top) */}
          {[...displayedNames].reverse().map((name, reverseIdx) => {
            const idx = displayedNames.length - 1 - reverseIdx;
            const d = buildPath(name);
            if (!d) return null;
            return (
              <path
                key={name}
                d={d}
                fill="none"
                stroke={POSITION_COLORS[idx % POSITION_COLORS.length]}
                strokeWidth={idx === 0 ? 2.5 : 2}
                strokeLinecap="round"
                strokeLinejoin="round"
                opacity={idx < 3 ? 1 : 0.7}
              />
            );
          })}

          {/* End-of-line name labels for top 3 outcomes */}
          {displayedNames.slice(0, 3).map((name, idx) => {
            // Find the last data point with a value for this outcome
            let lastProb: number | undefined;
            let lastTime: number | undefined;
            for (let i = chartData.length - 1; i >= 0; i--) {
              const prob = chartData[i].outcomes[name];
              if (prob !== undefined) {
                lastProb = prob;
                lastTime = new Date(chartData[i].timestamp).getTime();
                break;
              }
            }
            if (lastProb === undefined || lastTime === undefined) return null;
            const x = xScale(lastTime);
            const y = yScale(lastProb);
            const color = POSITION_COLORS[idx % POSITION_COLORS.length];
            // Truncate long names
            const label = name.length > 14 ? name.slice(0, 12) + "…" : name;
            return (
              <g key={`label-${name}`}>
                <circle cx={x} cy={y} r={3} fill={color} stroke="#0C0F14" strokeWidth={1.5} />
                <text
                  x={x + 6}
                  y={y}
                  textAnchor="start"
                  dominantBaseline="central"
                  fill={color}
                  fontSize={idx === 0 ? 11 : 10}
                  fontWeight={idx === 0 ? 700 : 600}
                  style={{ textShadow: "0 0 4px rgba(0,0,0,0.8)" }}
                >
                  {label} {Math.round(lastProb * 100)}%
                </text>
              </g>
            );
          })}

          {/* Hover crosshair and dots */}
          {hoverInfo && (
            <>
              <line
                x1={hoverInfo.svgX}
                y1={padding.top}
                x2={hoverInfo.svgX}
                y2={padding.top + innerHeight}
                stroke="#94a3b8"
                strokeWidth={1}
                strokeDasharray="4 2"
                opacity={0.6}
              />
              {hoverInfo.values.slice(0, 10).map((v, i) => (
                <circle
                  key={i}
                  cx={hoverInfo.svgX}
                  cy={yScale(v.prob)}
                  r={4}
                  fill={v.color}
                  stroke="#0C0F14"
                  strokeWidth={2}
                />
              ))}
            </>
          )}
        </svg>

        {/* Hover tooltip */}
        {hoverInfo && (
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
            <div className="bg-surface-deep/95 backdrop-blur-sm rounded-lg px-3 py-2 border border-surface-border shadow-lg min-w-[160px]">
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
      <div className="flex flex-wrap gap-x-4 gap-y-1.5">
        {displayedNames.map((name, idx) => {
          // Find current probability for legend display
          let currentProb: number | undefined;
          for (let i = chartData.length - 1; i >= 0; i--) {
            const prob = chartData[i].outcomes[name];
            if (prob !== undefined) {
              currentProb = prob;
              break;
            }
          }
          return (
            <div key={name} className="flex items-center gap-1.5 text-xs">
              <span
                className={`rounded-full ${idx === 0 ? "w-3 h-3" : "w-2.5 h-2.5"}`}
                style={{ backgroundColor: POSITION_COLORS[idx % POSITION_COLORS.length] }}
              />
              <span className={idx === 0 ? "text-text-primary font-semibold" : "text-text-secondary"}>
                {name}
              </span>
              {currentProb !== undefined && (
                <span className="text-text-muted font-mono">
                  {Math.round(currentProb * 100)}%
                </span>
              )}
            </div>
          );
        })}
        {hasField && (
          <div className="flex items-center gap-1.5 text-xs">
            <span
              className="w-2.5 h-2.5 rounded-full"
              style={{ backgroundColor: FIELD_COLOR, opacity: 0.5 }}
            />
            <span className="text-text-muted">Field</span>
          </div>
        )}
      </div>
    </div>
  );
}
