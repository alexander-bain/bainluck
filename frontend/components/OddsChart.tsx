"use client";

import { useState, useMemo } from "react";
import {
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import Link from "next/link";
import { format, parseISO } from "date-fns";
import type {
  OddsHistoryPoint,
  BookmakerHistoryPoint,
  ESPNHistoryPoint,
  WinProbHistoryPoint,
  WinProbSourceMeta,
} from "@/lib/types";

/**
 * Soft color palette for individual sportsbook lines.
 * Each book gets a distinct pastel so you can trace it across the chart.
 * Ordered to maximize contrast between adjacent books.
 */
const BOOKMAKER_COLORS = [
  "#93c5fd", // light blue
  "#fca5a5", // light red
  "#86efac", // light green
  "#c4b5fd", // light purple
  "#fdba74", // light orange
  "#67e8f9", // light cyan
  "#f9a8d4", // light pink
  "#fde047", // light yellow
  "#a5b4fc", // light indigo
  "#6ee7b7", // light emerald
  "#fda4af", // light rose
  "#a5f3fc", // light teal
];

/** Fallback source configs — frontend overrides to avoid team color conflicts */
const FALLBACK_SOURCE_CONFIG: Record<string, { display_name: string; color: string; dash_pattern: string | null; type: "model" | "market" }> = {
  betting: { display_name: "Betting Odds", color: "#1f2937", dash_pattern: null, type: "market" },
  espn: { display_name: "ESPN", color: "#f97316", dash_pattern: "6 3", type: "model" },
  stat_model: { display_name: "Bain Luck Model", color: "#8b5cf6", dash_pattern: "4 4", type: "model" },
  kalshi: { display_name: "Kalshi", color: "#06b6d4", dash_pattern: "8 4", type: "market" },
  polymarket: { display_name: "Polymarket", color: "#ec4899", dash_pattern: "8 4", type: "market" },
  moneypuck: { display_name: "MoneyPuck", color: "#eab308", dash_pattern: "4 4", type: "model" },
  fangraphs: { display_name: "MLB Model", color: "#14b8a6", dash_pattern: "4 4", type: "model" },
};

interface OddsChartProps {
  history: OddsHistoryPoint[];
  homeTeam: string;
  awayTeam: string;
  commenceTime?: string;
  isLive?: boolean;
  bookmakerHistory?: Record<string, BookmakerHistoryPoint[]>;
  /** ESPN win probability history (legacy, used as fallback) */
  espnHistory?: ESPNHistoryPoint[];
  /** Multi-source win probability history */
  winProbHistory?: Record<string, WinProbHistoryPoint[]>;
  /** Source metadata (display names, colors, types) */
  winProbSources?: Record<string, WinProbSourceMeta>;
  /** Event ID for analytics tracking */
  eventId?: number;
  /** Event status - determines default filter: closed/completed defaults to "Since Start", open defaults to "All" */
  eventStatus?: string;
  /** When true, chart fills its parent container height instead of using fixed h-80 */
  fillContainer?: boolean;
}

type TimeRange = "all" | "live";

const TIME_RANGE_OPTIONS: { value: TimeRange; label: string }[] = [
  { value: "all", label: "All" },
  { value: "live", label: "Since Start" },
];

interface ChartDataPoint {
  timestamp: string;
  time: string;
  /** Home probability delta from 50% (range: -50 to +50) */
  homeDelta: number | null;
  /** ESPN home probability delta from 50% (legacy) */
  espnDelta: number | null;
  [key: string]: string | number | null | undefined;
}

/** Resolved source info used for rendering */
interface ResolvedSource {
  key: string;
  dataKey: string;
  displayName: string;
  color: string;
  dashPattern: string | null;
  type: "model" | "market";
  snapshotCount: number;
}

/**
 * Win probability chart showing multiple labeled sources.
 *
 * All lines always visible — sportsbooks get distinct pastel colors,
 * model/market sources get bold saturated colors. Hover-to-highlight:
 * clicking a legend item highlights that line and dims everything else.
 * Crosshair + tooltip on hover for precise reading.
 */
export default function OddsChart({
  history,
  homeTeam,
  awayTeam,
  commenceTime,
  isLive = false,
  bookmakerHistory,
  espnHistory,
  winProbHistory,
  winProbSources,
  eventId,
  eventStatus,
  fillContainer = false,
}: OddsChartProps) {
  const isClosed = eventStatus === "closed" || eventStatus === "completed";

  const hasPostStartData = useMemo(() => {
    if (!history || history.length === 0 || !commenceTime) return false;
    const cutoffTime = parseISO(commenceTime);
    return history.some((point) => parseISO(point.timestamp) >= cutoffTime);
  }, [history, commenceTime]);

  const defaultTimeRange: TimeRange =
    (isClosed || isLive) && hasPostStartData ? "live" : "all";
  const [timeRange, setTimeRange] = useState<TimeRange>(defaultTimeRange);

  // (highlight state removed — labels were taking too much space)

  // Filter history based on time range
  const filteredHistory = useMemo(() => {
    if (!history || history.length === 0) return [];
    if (timeRange === "all") return history;
    const cutoffTime = commenceTime ? parseISO(commenceTime) : new Date();
    return history.filter((point) => parseISO(point.timestamp) >= cutoffTime);
  }, [history, timeRange, commenceTime]);

  // Filter bookmaker history
  const filteredBookmakerHistory = useMemo(() => {
    if (!bookmakerHistory || Object.keys(bookmakerHistory).length === 0)
      return {};
    if (timeRange === "all") return bookmakerHistory;
    const cutoffTime = commenceTime ? parseISO(commenceTime) : new Date();
    const filtered: Record<string, BookmakerHistoryPoint[]> = {};
    for (const [bookmaker, points] of Object.entries(bookmakerHistory)) {
      filtered[bookmaker] = points.filter(
        (point) => parseISO(point.timestamp) >= cutoffTime
      );
    }
    return filtered;
  }, [bookmakerHistory, timeRange, commenceTime]);

  // Build the list of all sources to display (betting + model sources)
  const resolvedSources = useMemo((): ResolvedSource[] => {
    const sources: ResolvedSource[] = [];

    // Always include betting odds as a labeled source
    if (history && history.length > 0) {
      const bettingConfig = FALLBACK_SOURCE_CONFIG.betting;
      sources.push({
        key: "betting",
        dataKey: "homeDelta",
        displayName: bettingConfig.display_name,
        color: bettingConfig.color,
        dashPattern: bettingConfig.dash_pattern,
        type: bettingConfig.type,
        snapshotCount: history.length,
      });
    }

    if (winProbHistory && Object.keys(winProbHistory).length > 0) {
      for (const [key, points] of Object.entries(winProbHistory)) {
        if (points.length === 0) continue;
        const meta = winProbSources?.[key];
        const fallback = FALLBACK_SOURCE_CONFIG[key];
        sources.push({
          key,
          dataKey: `wp_${key}_delta`,
          displayName: meta?.display_name ?? fallback?.display_name ?? key,
          // Frontend fallback colors take precedence to avoid team color conflicts
          color: fallback?.color ?? meta?.color ?? "#6b7280",
          dashPattern: fallback?.dash_pattern ?? meta?.dash_pattern ?? "4 4",
          type: meta?.type ?? fallback?.type ?? "model",
          snapshotCount: points.length,
        });
      }
    } else if (espnHistory && espnHistory.length > 0) {
      sources.push({
        key: "espn",
        dataKey: "espnDelta",
        displayName: "ESPN",
        color: "#f97316",
        dashPattern: "6 3",
        type: "model",
        snapshotCount: espnHistory.length,
      });
    }

    return sources;
  }, [history, winProbHistory, winProbSources, espnHistory]);

  // Non-betting sources
  const modelSources = useMemo(
    () => resolvedSources.filter((s) => s.key !== "betting"),
    [resolvedSources]
  );

  // Filter win prob history based on time range
  const filteredWinProbHistory = useMemo(() => {
    if (!winProbHistory || Object.keys(winProbHistory).length === 0) return {};
    if (timeRange === "all") return winProbHistory;
    const cutoffTime = commenceTime ? parseISO(commenceTime) : new Date();
    const filtered: Record<string, WinProbHistoryPoint[]> = {};
    for (const [source, points] of Object.entries(winProbHistory)) {
      filtered[source] = points.filter(
        (point) => parseISO(point.timestamp) >= cutoffTime
      );
    }
    return filtered;
  }, [winProbHistory, timeRange, commenceTime]);

  // Filter ESPN history (legacy fallback)
  const filteredEspnHistory = useMemo(() => {
    if (!espnHistory || espnHistory.length === 0) return [];
    if (timeRange === "all") return espnHistory;
    const cutoffTime = commenceTime ? parseISO(commenceTime) : new Date();
    return espnHistory.filter(
      (point) => parseISO(point.timestamp) >= cutoffTime
    );
  }, [espnHistory, timeRange, commenceTime]);

  const useNewWinProbData = Object.keys(filteredWinProbHistory).length > 0;
  const bookmakers = useMemo(
    () => Object.keys(filteredBookmakerHistory),
    [filteredBookmakerHistory]
  );

  // Assign each bookmaker a stable color from the palette
  const bookmakerColorMap = useMemo(() => {
    const map: Record<string, string> = {};
    // Use ALL bookmakers (not just filtered) for stable color assignment
    const allBooks = Object.keys(bookmakerHistory ?? {});
    allBooks.forEach((bk, i) => {
      map[bk] = BOOKMAKER_COLORS[i % BOOKMAKER_COLORS.length];
    });
    return map;
  }, [bookmakerHistory]);

  // Transform data: convert probabilities to delta from 50%
  const chartData: ChartDataPoint[] = useMemo(() => {
    const dataMap = new Map<string, ChartDataPoint>();

    const ensurePoint = (timestamp: string): ChartDataPoint => {
      let point = dataMap.get(timestamp);
      if (!point) {
        point = {
          timestamp,
          time: format(parseISO(timestamp), "h:mm a"),
          homeDelta: null,
          espnDelta: null,
        };
        dataMap.set(timestamp, point);
      }
      return point;
    };

    // Add aggregate data points (betting odds consensus)
    for (const point of filteredHistory) {
      const homeProb =
        point.home_probability !== null ? point.home_probability * 100 : null;
      const delta = homeProb !== null ? homeProb - 50 : null;

      const dp = ensurePoint(point.timestamp);
      dp.homeDelta = delta;

      // Expand valid_until
      if (point.valid_until) {
        const endTime = parseISO(point.valid_until);
        const startTime = parseISO(point.timestamp);
        if (endTime.getTime() - startTime.getTime() > 60000) {
          const endDp = ensurePoint(point.valid_until);
          if (endDp.homeDelta === null) endDp.homeDelta = delta;
        }
      }
    }

    // Add bookmaker lines (single line per bookmaker - home prob delta)
    for (const [bookmaker, points] of Object.entries(
      filteredBookmakerHistory
    )) {
      for (const point of points) {
        const homeProb =
          point.home_probability !== null
            ? point.home_probability * 100
            : null;
        const delta = homeProb !== null ? homeProb - 50 : null;

        const dp = ensurePoint(point.timestamp);
        dp[`${bookmaker}_delta`] = delta;

        // Expand valid_until
        if (point.valid_until) {
          const endTime = parseISO(point.valid_until);
          const startTime = parseISO(point.timestamp);
          if (endTime.getTime() - startTime.getTime() > 60000) {
            const endDp = ensurePoint(point.valid_until);
            if (endDp[`${bookmaker}_delta`] === undefined) {
              endDp[`${bookmaker}_delta`] = delta;
            }
          }
        }
      }
    }

    // Ensure all bookmaker keys exist on all data points
    const allBookmakers = Object.keys(filteredBookmakerHistory);
    const allPoints = Array.from(dataMap.values());
    for (const point of allPoints) {
      for (const bookmaker of allBookmakers) {
        if (point[`${bookmaker}_delta`] === undefined) {
          point[`${bookmaker}_delta`] = null;
        }
      }
    }

    // Add win probability source data (new multi-source or legacy ESPN)
    if (useNewWinProbData) {
      for (const [sourceKey, points] of Object.entries(filteredWinProbHistory)) {
        const dataKey = `wp_${sourceKey}_delta`;
        for (const point of points) {
          const homeProb =
            point.home_probability !== null ? point.home_probability * 100 : null;
          const delta = homeProb !== null ? homeProb - 50 : null;

          const dp = ensurePoint(point.timestamp);
          dp[dataKey] = delta;
        }
      }

      // Ensure all source keys exist on all data points
      const allDataPoints = Array.from(dataMap.values());
      for (const point of allDataPoints) {
        for (const source of modelSources) {
          if (point[source.dataKey] === undefined) {
            point[source.dataKey] = null;
          }
        }
      }
    } else {
      // Legacy ESPN data
      for (const point of filteredEspnHistory) {
        const espnHome =
          point.home_probability !== null ? point.home_probability * 100 : null;
        const delta = espnHome !== null ? espnHome - 50 : null;

        const dp = ensurePoint(point.timestamp);
        dp.espnDelta = delta;
      }
    }

    return Array.from(dataMap.values()).sort(
      (a, b) =>
        parseISO(a.timestamp).getTime() - parseISO(b.timestamp).getTime()
    );
  }, [filteredHistory, filteredBookmakerHistory, filteredWinProbHistory, filteredEspnHistory, useNewWinProbData, modelSources]);

  // Early return for empty history
  if (!history || history.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center bg-gray-50 rounded-lg text-gray-500">
        No history data available
      </div>
    );
  }

  // Compute gradient offset for area fill-by-value
  const gradientOffset = (() => {
    const deltas = chartData
      .map((d) => d.homeDelta)
      .filter((v): v is number => v !== null);
    if (deltas.length === 0) return 0.5;
    const dataMax = Math.max(...deltas);
    const dataMin = Math.min(...deltas);
    if (dataMax <= 0) return 0;
    if (dataMin >= 0) return 1;
    return dataMax / (dataMax - dataMin);
  })();

  // Short team names
  const homeShort = homeTeam.split(" ").pop() || homeTeam;
  const awayShort = awayTeam.split(" ").pop() || awayTeam;

  // Custom Y-axis tick formatter
  const formatYTick = (value: number): string => {
    const prob = 50 + Math.abs(value);
    return `${prob}%`;
  };

  // (no highlight logic — all lines at base visual weight)

  // Custom tooltip
  const CustomTooltip = ({
    active,
    payload,
    label,
  }: {
    active?: boolean;
    payload?: Array<{
      value: number;
      name: string;
      color: string;
      dataKey: string;
    }>;
    label?: string;
  }) => {
    if (!active || !payload || payload.length === 0) return null;

    // Find entries for each resolved source
    const sourceEntries = resolvedSources
      .map((source) => {
        const entry = payload.find(
          (e) => e.dataKey === source.dataKey && e.value !== null
        );
        return entry ? { ...source, value: entry.value } : null;
      })
      .filter((e): e is ResolvedSource & { value: number } => e !== null);

    const bookmakerEntries = payload.filter(
      (e) =>
        e.dataKey !== "homeDelta" &&
        !e.dataKey.startsWith("wp_") &&
        e.dataKey !== "espnDelta" &&
        e.value !== null
    );

    return (
      <div className="bg-white/95 backdrop-blur-sm p-3 rounded-lg shadow-xl border border-gray-200 max-w-sm">
        <p className="text-xs font-medium text-gray-500 mb-2">{label}</p>
        {/* Sources — betting first, bold */}
        {sourceEntries.length > 0 && (
          <div className={bookmakerEntries.length > 0 ? "pb-2 mb-2 border-b border-gray-100" : ""}>
            {sourceEntries.map((source) => {
              const homeProb = source.value + 50;
              const isBetting = source.key === "betting";
              return (
                <div key={source.key} className="flex items-center justify-between gap-3 mb-0.5">
                  <span className={`text-xs flex items-center gap-1.5 ${isBetting ? "text-gray-800 font-semibold" : "text-gray-500"}`}>
                    <span
                      className="inline-block w-2 h-2 rounded-full shrink-0"
                      style={{ backgroundColor: source.color }}
                    />
                    {source.displayName}
                  </span>
                  <span
                    className={`text-xs ${isBetting ? "font-bold text-gray-900" : "font-semibold"}`}
                    style={!isBetting ? { color: source.color } : undefined}
                  >
                    {homeProb.toFixed(1)}% / {(100 - homeProb).toFixed(1)}%
                  </span>
                </div>
              );
            })}
          </div>
        )}
        {/* Bookmaker entries with their individual colors */}
        {bookmakerEntries.length > 0 && (
          <div className="space-y-0.5 max-h-40 overflow-y-auto">
            {bookmakerEntries.map((entry) => {
              const bookmaker = entry.dataKey.replace("_delta", "");
              const homeProb = entry.value + 50;
              const color = bookmakerColorMap[bookmaker] ?? "#9ca3af";
              return (
                <div key={bookmaker} className="flex items-center justify-between gap-3">
                  <span className="text-xs text-gray-500 flex items-center gap-1.5">
                    <span
                      className="inline-block w-2 h-2 rounded-full shrink-0"
                      style={{ backgroundColor: color }}
                    />
                    {bookmaker}
                  </span>
                  <span className="text-xs text-gray-500">
                    {homeProb.toFixed(0)}% / {(100 - homeProb).toFixed(0)}%
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className={fillContainer ? "flex flex-col h-full gap-1" : "space-y-3"}>
      {/* Time range selector */}
      <div className="flex flex-wrap items-center gap-1 shrink-0">
        {TIME_RANGE_OPTIONS.map((option) => (
          <button
            key={option.value}
            onClick={() => setTimeRange(option.value)}
            className={`font-medium rounded-full transition-colors ${
              fillContainer
                ? `px-[0.4vw] py-[0.1vh] text-[0.9vh] ${
                    timeRange === option.value
                      ? "bg-surface-card/10 text-white/40"
                      : "text-white/15 hover:text-white/25"
                  }`
                : `px-3 py-1.5 text-xs ${
                    timeRange === option.value
                      ? "bg-text-primary text-surface-deep"
                      : "bg-surface-elevated text-text-secondary hover:bg-surface-border"
                  }`
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>

      {/* Team labels flanking the chart */}
      <div className="flex items-center justify-between text-xs font-medium px-8 shrink-0">
        <span className="text-green-600">{homeShort} favored ↑</span>
        <span className="text-blue-600">{awayShort} favored ↓</span>
      </div>

      {/* Probability Chart */}
      <div className={fillContainer ? "w-full flex-1 min-h-0" : "w-full h-80"}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={chartData}
            margin={{ top: 5, right: 10, left: fillContainer ? 5 : 0, bottom: 5 }}
          >
            <defs>
              <linearGradient id="probFillGradient" x1="0" y1="0" x2="0" y2="1">
                <stop
                  offset={gradientOffset}
                  stopColor="#22c55e"
                  stopOpacity={0.15}
                />
                <stop
                  offset={gradientOffset}
                  stopColor="#3b82f6"
                  stopOpacity={0.15}
                />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
            <XAxis
              dataKey="time"
              tick={{ fontSize: 10, fill: "#9ca3af" }}
              tickLine={false}
              axisLine={{ stroke: "#e5e7eb" }}
              interval={
                chartData.length <= 10 ? 0 : "preserveStartEnd"
              }
              minTickGap={50}
            />
            <YAxis
              domain={[-50, 50]}
              ticks={[-50, -25, 0, 25, 50]}
              tick={{ fontSize: 10, fill: "#9ca3af" }}
              tickLine={false}
              axisLine={{ stroke: "#e5e7eb" }}
              tickFormatter={formatYTick}
            />
            {/* 50% reference line */}
            <ReferenceLine
              y={0}
              stroke="#d1d5db"
              strokeWidth={1}
              strokeDasharray="4 4"
              label={{
                value: "50%",
                position: "right",
                style: { fontSize: 10, fill: "#d1d5db" },
              }}
            />
            <Tooltip
              content={<CustomTooltip />}
              cursor={{ stroke: "#d1d5db", strokeWidth: 1, strokeDasharray: "3 3" }}
            />

            {/* Individual bookmaker lines — distinct pastel colors, always visible */}
            {bookmakers.map((bookmaker) => {
              const color = bookmakerColorMap[bookmaker] ?? "#d1d5db";
              return (
                <Line
                  key={`${bookmaker}_delta`}
                  type="monotone"
                  dataKey={`${bookmaker}_delta`}
                  stroke={color}
                  strokeWidth={1.25}
                  opacity={0.5}
                  dot={false}
                  activeDot={{ r: 4, fill: color, stroke: "#fff", strokeWidth: 1 }}
                  connectNulls
                  legendType="none"
                  isAnimationActive={false}
                />
              );
            })}

            {/* Model/market source lines — saturated colors, dashed */}
            {modelSources.map((source) => (
              <Line
                key={source.dataKey}
                type="monotone"
                dataKey={source.dataKey}
                name={source.displayName}
                stroke={source.color}
                strokeWidth={2}
                strokeDasharray={source.dashPattern ?? undefined}
                opacity={0.75}
                dot={false}
                activeDot={{ r: 5, fill: source.color, stroke: "#fff", strokeWidth: 1.5 }}
                connectNulls
                isAnimationActive={false}
              />
            ))}

            {/* Legacy ESPN line (when winProbHistory not available) */}
            {!useNewWinProbData && filteredEspnHistory.length > 0 && (
              <Line
                type="monotone"
                dataKey="espnDelta"
                name="ESPN Model"
                stroke="#f97316"
                strokeWidth={2}
                strokeDasharray="6 3"
                opacity={0.75}
                dot={false}
                activeDot={{ r: 5, fill: "#f97316", stroke: "#fff", strokeWidth: 1.5 }}
                connectNulls
                isAnimationActive={false}
              />
            )}

            {/* Area fill — very subtle, fades more when highlighting */}
            <Area
              type="monotone"
              dataKey="homeDelta"
              stroke="none"
              fill="url(#probFillGradient)"
              connectNulls
              legendType="none"
              isAnimationActive={false}
            />

            {/* Betting odds line — hero: thickest, darkest, always on top */}
            <Line
              type="monotone"
              dataKey="homeDelta"
              name="Betting Odds"
              stroke="#1f2937"
              strokeWidth={3}
              opacity={1}
              dot={false}
              activeDot={{ r: 6, fill: "#1f2937", stroke: "#fff", strokeWidth: 2 }}
              connectNulls
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Compact legend — named sources only, sportsbooks identified via tooltip */}
      {resolvedSources.length > 0 && (
        <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1 shrink-0">
          {resolvedSources.map((source) => {
            const inner = (
              <span className="flex items-center gap-1.5">
                <svg width="20" height="4" className="shrink-0">
                  <line
                    x1="0" y1="2" x2="20" y2="2"
                    stroke={source.color}
                    strokeWidth={source.key === "betting" ? "3" : "2"}
                    strokeDasharray={source.dashPattern ?? undefined}
                  />
                </svg>
                <span className="text-xs text-gray-500">
                  {source.displayName}
                  <span className="text-text-muted ml-0.5">({source.type})</span>
                </span>
              </span>
            );
            return eventId ? (
              <Link key={source.key} href={`/events/${eventId}/models`} className="hover:opacity-70 transition-opacity">
                {inner}
              </Link>
            ) : (
              <div key={source.key}>{inner}</div>
            );
          })}
        </div>
      )}
    </div>
  );
}
