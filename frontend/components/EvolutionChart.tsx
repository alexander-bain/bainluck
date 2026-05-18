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

const COMBINED_PROBABILITY_KEY = "combined_probability";
const COMBINED_PROBABILITY_COLOR = "#111827";

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
  /** Show the summed probability of all currently selected outcome lines */
  showCombinedProbability?: boolean;
}

/** Merge all outcome histories into unified time-bucketed chart data */
function buildChartData(
  historyData: FuturesOutcomeHistory[],
  selectedIds: Set<number>,
  timeRange: TimeRange,
  tournamentStart?: string | null,
  showCombinedProbability = false
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
  const latestKnownProbabilities = new Map<number, number>();

  const data = sortedTs.map((ts) => {
    const row: Record<string, number | string | null> = {
      timestamp: new Date(ts).toISOString(),
      _ts: ts,
    };
    for (const [oid, map] of outcomeMaps) {
      const val = map.get(ts) ?? null;
      row[`outcome_${oid}`] = val;
      if (val !== null) {
        latestKnownProbabilities.set(oid, val);
        if (val < minProb) minProb = val;
        if (val > maxProb) maxProb = val;
      }
    }
    if (showCombinedProbability && outcomeMaps.size > 1) {
      let combined = 0;
      for (const val of latestKnownProbabilities.values()) {
        combined += val;
      }
      const combinedValue = latestKnownProbabilities.size > 0 ? Math.min(1, combined) : null;
      row[COMBINED_PROBABILITY_KEY] = combinedValue;
      if (combinedValue !== null) {
        if (combinedValue < minProb) minProb = combinedValue;
        if (combinedValue > maxProb) maxProb = combinedValue;
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
  showCombinedProbability = false,
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
    () => buildChartData(
      historyData,
      selectedOutcomeIds,
      timeRange,
      tournamentStart,
      showCombinedProbability
    ),
    [historyData, selectedOutcomeIds, timeRange, tournamentStart, showCombinedProbability]
  );

  const shouldShowCombinedProbability = showCombinedProbability && selectedOutcomeIds.size > 1;

  const formatXAxis = useCallback(
    (value: string) => {
      try {
        const d = parseISO(value);
        if (timeRange === "today" || timeRange === "24h") {
          return format(d, "h:mm a");
        }
        if (timeRange === "tournament") {
          // Use "Thu 10" format to avoid duplicate day names (e.g. "Wed" appearing twice)
          return format(d, "EEE d");
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

  // Compute explicit tick positions: one per unique day to prevent duplicate date labels.
  // For intraday ranges (today/24h), let Recharts auto-tick.
  const explicitTicks = useMemo(() => {
    if (timeRange === "today" || timeRange === "24h" || data.length === 0) return undefined;
    const seen = new Set<string>();
    const ticks: string[] = [];
    for (const row of data) {
      const ts = row.timestamp as string;
      const dayKey = ts.slice(0, 10); // "2026-04-09"
      if (!seen.has(dayKey)) {
        seen.add(dayKey);
        ticks.push(ts); // Use first data point of each day as the tick
      }
    }
    return ticks;
  }, [data, timeRange]);

  if (data.length === 0) {
    return (
      <div className={`flex items-center justify-center h-48 text-text-muted text-sm ${className || ""}`}>
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
              if (!entry.dataKey?.toString().startsWith("outcome_")) continue;
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
            ticks={explicitTicks}
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
                <div className="bg-surface-card border border-surface-border rounded-lg p-3 text-sm shadow-lg max-w-[240px]">
                  <div className="text-text-muted mb-2 text-xs">
                    {(() => {
                      try {
                        return format(parseISO(label as string), "MMM d, h:mm a");
                      } catch {
                        return label;
                      }
                    })()}
                  </div>
                  {sorted.map((entry) => {
                    const isCombined = entry.dataKey === COMBINED_PROBABILITY_KEY;
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
                          style={{
                            backgroundColor: isCombined
                              ? COMBINED_PROBABILITY_COLOR
                              : info?.color ?? "var(--text-muted)",
                          }}
                        />
                        <span className="text-text-secondary truncate max-w-[140px] text-xs font-medium">
                          {isCombined ? "Combined" : info?.name ?? "Unknown"}
                        </span>
                        <span className="text-text-primary font-mono text-xs font-semibold ml-auto tabular-nums">
                          {((entry.value as number) * 100).toFixed(1)}%
                        </span>
                      </div>
                    );
                  })}
                </div>
              );
            }}
          />

          {/* Round boundary markers — dashed lines with label pills.
              Snap boundary timestamps to nearest data point since ReferenceLine x
              must exactly match a data row's timestamp value. */}
          {roundBoundaries?.map((rb) => {
            const rbMs = new Date(rb.timestamp).getTime();
            // Find closest data point timestamp
            let closest = rb.timestamp;
            let minDist = Infinity;
            for (const row of data) {
              const rowMs = row._ts as number;
              const dist = Math.abs(rowMs - rbMs);
              if (dist < minDist) {
                minDist = dist;
                closest = row.timestamp as string;
              }
            }
            // Don't render if nearest point is more than 12 hours away
            if (minDist > 12 * 60 * 60 * 1000) return null;
            return (
              <ReferenceLine
                key={rb.timestamp}
                x={closest}
                stroke="#9ca3af"
                strokeDasharray="4 3"
                strokeWidth={1}
                label={{
                  value: rb.label,
                  position: "top",
                  fill: "#6b7280",
                  fontSize: 10,
                  fontWeight: 600,
                }}
              />
            );
          })}

          {/* Combined selected-outcome probability */}
          {shouldShowCombinedProbability && (
            <Line
              key={COMBINED_PROBABILITY_KEY}
              type="monotone"
              dataKey={COMBINED_PROBABILITY_KEY}
              stroke={COMBINED_PROBABILITY_COLOR}
              strokeWidth={2.2}
              strokeOpacity={highlightedOutcomeId ? 0.45 : 0.9}
              strokeDasharray="7 4"
              dot={false}
              connectNulls
              name="Combined"
            />
          )}

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
