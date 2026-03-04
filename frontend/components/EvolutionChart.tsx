"use client";

import { useState, useMemo, useCallback } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import { format, parseISO, subDays, subHours } from "date-fns";
import type {
  FuturesOutcomeHistory,
  FuturesHistoryPoint,
} from "@/lib/types";

/**
 * 10-color palette with good contrast on dark backgrounds.
 * First color (leader) is more vivid; rest are distinct hues.
 */
const EVOLUTION_COLORS = [
  "#facc15", // yellow (leader)
  "#3b82f6", // blue
  "#ef4444", // red
  "#22c55e", // green
  "#a855f7", // purple
  "#f97316", // orange
  "#06b6d4", // cyan
  "#ec4899", // pink
  "#84cc16", // lime
  "#f43f5e", // rose
];

type TimeRange = "full" | "7d" | "24h" | "today";

interface RoundBoundary {
  timestamp: string;
  label: string;
}

interface EvolutionChartProps {
  /** History data per outcome (from /api/futures/{id}/history) */
  historyData: FuturesOutcomeHistory[];
  /** IDs of outcomes currently shown on chart */
  selectedOutcomeIds: Set<number>;
  /** ID of outcome being hovered (for highlighting) */
  highlightedOutcomeId?: number | null;
  /** Callback when user hovers over a data point */
  onHoverOutcome?: (outcomeId: number | null) => void;
  /** Round/phase boundary markers */
  roundBoundaries?: RoundBoundary[] | null;
  /** Chart height in px */
  height?: number;
  /** Optional class name */
  className?: string;
}

/** Merge all outcome histories into unified time-bucketed chart data */
function buildChartData(
  historyData: FuturesOutcomeHistory[],
  selectedIds: Set<number>,
  timeRange: TimeRange
): { data: Record<string, number | string | null>[]; domain: [number, number] } {
  const now = Date.now();
  let cutoff = 0;
  if (timeRange === "7d") cutoff = subDays(new Date(), 7).getTime();
  else if (timeRange === "24h") cutoff = subHours(new Date(), 24).getTime();
  else if (timeRange === "today") {
    const todayStart = new Date();
    todayStart.setHours(0, 0, 0, 0);
    cutoff = todayStart.getTime();
  }

  // Collect all unique timestamps and build per-outcome maps
  const allTimestamps = new Set<number>();
  const outcomeMaps = new Map<number, Map<number, number>>();

  for (const outcome of historyData) {
    if (!selectedIds.has(outcome.outcome_id)) continue;
    const map = new Map<number, number>();
    for (const point of outcome.history) {
      const ts = parseISO(point.timestamp).getTime();
      if (cutoff && ts < cutoff) continue;
      // Time-bucket to 15-min intervals for "full" view to limit data points
      const bucketMs = timeRange === "full" ? 15 * 60 * 1000 : 5 * 60 * 1000;
      const bucket = Math.floor(ts / bucketMs) * bucketMs;
      map.set(bucket, point.probability ?? 0);
      allTimestamps.add(bucket);
    }
    outcomeMaps.set(outcome.outcome_id, map);
  }

  // Sort timestamps
  const sortedTs = Array.from(allTimestamps).sort((a, b) => a - b);

  // Track min/max for Y-axis domain
  let minProb = 1;
  let maxProb = 0;

  // Build chart data array
  const data = sortedTs.map((ts) => {
    const row: Record<string, number | string | null> = {
      timestamp: new Date(ts).toISOString(),
      _ts: ts,
    };
    for (const [oid, map] of outcomeMaps) {
      const val = map.get(ts) ?? null;
      row[`outcome_${oid}`] = val;
      if (val !== null) {
        if (val < minProb) minProb = val;
        if (val > maxProb) maxProb = val;
      }
    }
    return row;
  });

  // Add padding to Y domain
  const padding = Math.max(0.02, (maxProb - minProb) * 0.1);
  const domain: [number, number] = [
    Math.max(0, minProb - padding),
    Math.min(1, maxProb + padding),
  ];

  return { data, domain };
}

export function EvolutionChart({
  historyData,
  selectedOutcomeIds,
  highlightedOutcomeId,
  onHoverOutcome,
  roundBoundaries,
  height = 400,
  className,
}: EvolutionChartProps) {
  const [timeRange, setTimeRange] = useState<TimeRange>("full");

  // Build name lookup and color assignment
  const outcomeInfo = useMemo(() => {
    const info = new Map<number, { name: string; color: string; eliminated: boolean }>();
    // Sort selected by current probability (highest first) for color assignment
    const sorted = historyData
      .filter((o) => selectedOutcomeIds.has(o.outcome_id))
      .sort((a, b) => {
        const aLast = a.history[a.history.length - 1]?.probability ?? 0;
        const bLast = b.history[b.history.length - 1]?.probability ?? 0;
        return bLast - aLast;
      });
    sorted.forEach((o, i) => {
      info.set(o.outcome_id, {
        name: o.name,
        color: o.eliminated ? "#4b5563" : EVOLUTION_COLORS[i % EVOLUTION_COLORS.length],
        eliminated: !!o.eliminated,
      });
    });
    return info;
  }, [historyData, selectedOutcomeIds]);

  const { data, domain } = useMemo(
    () => buildChartData(historyData, selectedOutcomeIds, timeRange),
    [historyData, selectedOutcomeIds, timeRange]
  );

  const formatXAxis = useCallback(
    (value: string) => {
      try {
        const d = parseISO(value);
        if (timeRange === "today" || timeRange === "24h") {
          return format(d, "h:mm a");
        }
        return format(d, "MMM d");
      } catch {
        return "";
      }
    },
    [timeRange]
  );

  const formatYAxis = useCallback((value: number) => {
    return `${(value * 100).toFixed(0)}%`;
  }, []);

  if (data.length === 0) {
    return (
      <div className={`flex items-center justify-center h-48 text-gray-500 ${className || ""}`}>
        No history data available
      </div>
    );
  }

  return (
    <div className={className}>
      {/* Time range toggle */}
      <div className="flex gap-1 mb-3">
        {(["full", "7d", "24h", "today"] as TimeRange[]).map((range) => (
          <button
            key={range}
            onClick={() => setTimeRange(range)}
            className={`px-3 py-1 text-xs rounded-full transition-colors ${
              timeRange === range
                ? "bg-white/20 text-white font-medium"
                : "text-gray-400 hover:text-white hover:bg-white/10"
            }`}
          >
            {range === "full"
              ? "Full Event"
              : range === "7d"
                ? "7 Days"
                : range === "24h"
                  ? "24 Hours"
                  : "Today"}
          </button>
        ))}
      </div>

      <ResponsiveContainer width="100%" height={height}>
        <LineChart
          data={data}
          margin={{ top: 5, right: 10, left: 5, bottom: 5 }}
          onMouseMove={(state) => {
            if (!onHoverOutcome || !state?.activePayload) return;
            // Find which outcome has the highest value at cursor position
            let maxVal = -1;
            let maxId: number | null = null;
            for (const entry of state.activePayload) {
              const val = entry.value as number;
              if (val != null && val > maxVal) {
                maxVal = val;
                const match = entry.dataKey?.toString().match(/outcome_(\d+)/);
                if (match) maxId = parseInt(match[1], 10);
              }
            }
            onHoverOutcome(maxId);
          }}
          onMouseLeave={() => onHoverOutcome?.(null)}
        >
          <CartesianGrid
            strokeDasharray="3 3"
            stroke="rgba(255,255,255,0.06)"
          />
          <XAxis
            dataKey="timestamp"
            tickFormatter={formatXAxis}
            stroke="#6b7280"
            tick={{ fontSize: 11 }}
            tickCount={6}
          />
          <YAxis
            domain={domain}
            tickFormatter={formatYAxis}
            stroke="#6b7280"
            tick={{ fontSize: 11 }}
            width={45}
          />
          <Tooltip
            content={({ active, payload, label }) => {
              if (!active || !payload?.length) return null;
              const sorted = [...payload]
                .filter((p) => p.value != null)
                .sort(
                  (a, b) => ((b.value as number) ?? 0) - ((a.value as number) ?? 0)
                );
              return (
                <div className="bg-gray-900 border border-gray-700 rounded-lg p-3 text-sm shadow-xl">
                  <div className="text-gray-400 mb-2 text-xs">
                    {(() => {
                      try {
                        return format(parseISO(label as string), "MMM d, h:mm a");
                      } catch {
                        return label;
                      }
                    })()}
                  </div>
                  {sorted.map((entry) => {
                    const match = entry.dataKey?.toString().match(/outcome_(\d+)/);
                    const oid = match ? parseInt(match[1], 10) : 0;
                    const info = outcomeInfo.get(oid);
                    return (
                      <div
                        key={entry.dataKey}
                        className="flex items-center gap-2 py-0.5"
                      >
                        <div
                          className="w-2 h-2 rounded-full flex-shrink-0"
                          style={{ backgroundColor: info?.color ?? "#999" }}
                        />
                        <span className="text-gray-300 truncate max-w-[140px]">
                          {info?.name ?? "Unknown"}
                        </span>
                        <span className="text-white font-mono ml-auto">
                          {((entry.value as number) * 100).toFixed(1)}%
                        </span>
                      </div>
                    );
                  })}
                </div>
              );
            }}
          />

          {/* Round boundary markers */}
          {roundBoundaries?.map((rb) => (
            <ReferenceLine
              key={rb.timestamp}
              x={rb.timestamp}
              stroke="rgba(255,255,255,0.2)"
              strokeDasharray="4 4"
              label={{
                value: rb.label,
                position: "top",
                fill: "#9ca3af",
                fontSize: 10,
              }}
            />
          ))}

          {/* One line per selected outcome */}
          {Array.from(outcomeInfo.entries()).map(([oid, info]) => (
            <Line
              key={oid}
              type="monotone"
              dataKey={`outcome_${oid}`}
              stroke={info.color}
              strokeWidth={
                highlightedOutcomeId === oid
                  ? 3
                  : highlightedOutcomeId
                    ? 1
                    : info.eliminated ? 1 : 2
              }
              strokeOpacity={
                highlightedOutcomeId && highlightedOutcomeId !== oid
                  ? 0.3
                  : info.eliminated ? 0.4 : 1
              }
              strokeDasharray={info.eliminated ? "4 3" : undefined}
              dot={false}
              connectNulls
              name={info.name}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
