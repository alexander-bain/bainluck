"use client";

import { useMemo, useCallback } from "react";
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
import type { FuturesOutcomeHistory } from "@/lib/types";

/**
 * 10-color palette optimized for light (white) backgrounds.
 * Distinct hues with enough saturation to read on white.
 */
const EVOLUTION_COLORS = [
  "#c41e3a", // red (leader)
  "#005eb8", // blue
  "#1d4ed8", // indigo
  "#0e7490", // teal
  "#b91c1c", // dark red
  "#0369a1", // sky
  "#92400e", // amber
  "#4338ca", // violet
  "#be185d", // pink
  "#065f46", // emerald
];

type TimeRange = "full" | "tournament" | "7d" | "24h" | "today";

interface RoundBoundary {
  timestamp: string;
  label: string;
}

interface EvolutionChartProps {
  historyData: FuturesOutcomeHistory[];
  selectedOutcomeIds: Set<number>;
  highlightedOutcomeId?: number | null;
  onHoverOutcome?: (outcomeId: number | null) => void;
  roundBoundaries?: RoundBoundary[] | null;
  height?: number;
  className?: string;
  timeRange: TimeRange;
  /** ISO start date — required cutoff for the "tournament" time range */
  tournamentStart?: string | null;
}

/** Merge all outcome histories into unified time-bucketed chart data */
function buildChartData(
  historyData: FuturesOutcomeHistory[],
  selectedIds: Set<number>,
  timeRange: TimeRange,
  tournamentStart?: string | null
): { data: Record<string, number | string | null>[]; domain: [number, number] } {
  let cutoff = 0;
  if (timeRange === "7d") cutoff = subDays(new Date(), 7).getTime();
  else if (timeRange === "24h") cutoff = subHours(new Date(), 24).getTime();
  else if (timeRange === "today") {
    const todayStart = new Date();
    todayStart.setHours(0, 0, 0, 0);
    cutoff = todayStart.getTime();
  } else if (timeRange === "tournament" && tournamentStart) {
    // Start a little before the first round so the viewer sees the pre-event baseline
    try {
      cutoff = new Date(tournamentStart).getTime() - 12 * 60 * 60 * 1000;
    } catch {
      cutoff = 0;
    }
  }

  const allTimestamps = new Set<number>();
  const outcomeMaps = new Map<number, Map<number, number>>();

  for (const outcome of historyData) {
    if (!selectedIds.has(outcome.outcome_id)) continue;
    const map = new Map<number, number>();
    for (const point of outcome.history) {
      const ts = parseISO(point.timestamp).getTime();
      if (cutoff && ts < cutoff) continue;
      const bucketMs = timeRange === "full"
        ? 15 * 60 * 1000
        : timeRange === "tournament"
          ? 15 * 60 * 1000
          : 5 * 60 * 1000;
      const bucket = Math.floor(ts / bucketMs) * bucketMs;
      map.set(bucket, point.probability ?? 0);
      allTimestamps.add(bucket);
    }
    outcomeMaps.set(outcome.outcome_id, map);
  }

  const sortedTs = Array.from(allTimestamps).sort((a, b) => a - b);

  let minProb = 1;
  let maxProb = 0;

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
  height = 300,
  className,
  timeRange,
  tournamentStart,
}: EvolutionChartProps) {
  // Build name lookup and color assignment
  const outcomeInfo = useMemo(() => {
    const info = new Map<number, { name: string; color: string; eliminated: boolean }>();
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
        color: o.eliminated ? "#b5b9c3" : EVOLUTION_COLORS[i % EVOLUTION_COLORS.length],
        eliminated: !!o.eliminated,
      });
    });
    return info;
  }, [historyData, selectedOutcomeIds]);

  const { data, domain } = useMemo(
    () => buildChartData(historyData, selectedOutcomeIds, timeRange, tournamentStart),
    [historyData, selectedOutcomeIds, timeRange, tournamentStart]
  );

  const formatXAxis = useCallback(
    (value: string) => {
      try {
        const d = parseISO(value);
        if (timeRange === "today" || timeRange === "24h") {
          return format(d, "h:mm a");
        }
        if (timeRange === "tournament") {
          return format(d, "EEE");
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
      <div className={`flex items-center justify-center h-48 text-gray-400 text-sm ${className || ""}`}>
        No history data available
      </div>
    );
  }

  return (
    <div className={className}>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart
          data={data}
          margin={{ top: 16, right: 12, left: 4, bottom: 5 }}
          onMouseMove={(state) => {
            if (!onHoverOutcome || !state?.activePayload) return;
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
            strokeDasharray="none"
            stroke="#eef0f3"
            vertical={false}
          />
          <XAxis
            dataKey="timestamp"
            tickFormatter={formatXAxis}
            stroke="#dde0e5"
            tick={{ fontSize: 10, fill: "#9ca3af" }}
            interval={Math.max(0, Math.ceil(data.length / 7) - 1)}
            tickLine={false}
          />
          <YAxis
            domain={domain}
            tickFormatter={formatYAxis}
            stroke="#dde0e5"
            tick={{ fontSize: 10, fill: "#9ca3af" }}
            width={42}
            tickLine={false}
            axisLine={false}
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
                <div className="bg-white border border-gray-200 rounded-lg p-3 text-sm shadow-lg">
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
                          className="w-[7px] h-[7px] rounded-full flex-shrink-0"
                          style={{ backgroundColor: info?.color ?? "#9ca3af" }}
                        />
                        <span className="text-gray-700 truncate max-w-[140px] text-xs font-medium">
                          {info?.name ?? "Unknown"}
                        </span>
                        <span className="text-gray-900 font-mono text-xs font-semibold ml-auto tabular-nums">
                          {((entry.value as number) * 100).toFixed(1)}%
                        </span>
                      </div>
                    );
                  })}
                </div>
              );
            }}
          />

          {/* Round boundary markers — dashed lines with label pills */}
          {roundBoundaries?.map((rb) => (
            <ReferenceLine
              key={rb.timestamp}
              x={rb.timestamp}
              stroke="#9ca3af55"
              strokeDasharray="4 3"
              label={{
                value: rb.label,
                position: "top",
                fill: "#6b7280",
                fontSize: 9,
                fontWeight: 600,
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
                  ? 2.5
                  : highlightedOutcomeId
                    ? 0.8
                    : info.eliminated ? 0.8 : 1.5
              }
              strokeOpacity={
                highlightedOutcomeId && highlightedOutcomeId !== oid
                  ? 0.2
                  : info.eliminated ? 0.35 : 1
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
