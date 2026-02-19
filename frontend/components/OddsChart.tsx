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

/** Fallback source configs when win_prob_sources metadata isn't available */
const FALLBACK_SOURCE_CONFIG: Record<string, { display_name: string; color: string; dash_pattern: string | null; type: "model" | "market" }> = {
  betting: { display_name: "Betting Odds", color: "#374151", dash_pattern: null, type: "market" },
  espn: { display_name: "ESPN", color: "#f97316", dash_pattern: "6 3", type: "model" },
  stat_model: { display_name: "OddsTracker Model", color: "#8b5cf6", dash_pattern: "4 4", type: "model" },
  kalshi: { display_name: "Kalshi", color: "#22c55e", dash_pattern: "8 4", type: "market" },
  polymarket: { display_name: "Polymarket", color: "#3b82f6", dash_pattern: "8 4", type: "market" },
  moneypuck: { display_name: "MoneyPuck", color: "#10b981", dash_pattern: "4 4", type: "model" },
  fangraphs: { display_name: "FanGraphs", color: "#06b6d4", dash_pattern: "4 4", type: "model" },
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
 * Each source (Betting Odds, ESPN, Statistical Model, etc.) gets its own
 * clearly labeled line. Market sources use solid lines, model sources use
 * dashed lines. The betting odds line also gets an area fill.
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
  // Betting odds always included as first source when history data exists.
  // Model sources come from winProbHistory (new) or espnHistory (legacy).
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
      // Use the new multi-source data
      for (const [key, points] of Object.entries(winProbHistory)) {
        if (points.length === 0) continue;
        const meta = winProbSources?.[key];
        const fallback = FALLBACK_SOURCE_CONFIG[key];
        sources.push({
          key,
          dataKey: `wp_${key}_delta`,
          displayName: meta?.display_name ?? fallback?.display_name ?? key,
          color: meta?.color ?? fallback?.color ?? "#6b7280",
          dashPattern: meta?.dash_pattern ?? fallback?.dash_pattern ?? "4 4",
          type: meta?.type ?? fallback?.type ?? "model",
          snapshotCount: points.length,
        });
      }
    } else if (espnHistory && espnHistory.length > 0) {
      // Legacy: use espnHistory directly
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

  // Non-betting sources (model sources rendered as separate chart lines)
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

  // Custom Y-axis tick formatter: shows probability for each team
  const formatYTick = (value: number): string => {
    const prob = 50 + Math.abs(value);
    return `${prob}%`;
  };

  // Custom tooltip showing actual probabilities
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
    if (active && payload && payload.length) {
      const formatProb = (delta: number) => {
        const homeProb = delta + 50;
        const awayProb = 100 - homeProb;
        return `${homeTeam}: ${homeProb.toFixed(1)}% | ${awayTeam}: ${awayProb.toFixed(1)}%`;
      };

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
        <div className="bg-white p-3 rounded-lg shadow-lg border border-gray-200 max-w-sm">
          <p className="text-xs text-gray-500 mb-2">{label}</p>
          {/* All sources, grouped */}
          {sourceEntries.length > 0 && (
            <div className="space-y-1">
              {sourceEntries.map((source) => (
                <div key={source.key}>
                  <p className="text-xs text-gray-400 mb-0.5">
                    {source.displayName}
                    <span className="text-gray-300 ml-1">
                      ({source.type})
                    </span>
                  </p>
                  <p
                    className={`text-xs font-medium ${source.key === "betting" ? "text-sm font-semibold text-gray-800" : ""}`}
                    style={source.key !== "betting" ? { color: source.color } : undefined}
                  >
                    {formatProb(source.value)}
                  </p>
                </div>
              ))}
            </div>
          )}
          {bookmakerEntries.length > 0 && (
            <div className="mt-2 pt-2 border-t border-gray-100">
              <p className="text-xs text-gray-400 mb-1">By sportsbook:</p>
              {bookmakerEntries.map((entry) => {
                const bookmaker = entry.dataKey.replace("_delta", "");
                const homeProb = entry.value + 50;
                const awayProb = 100 - homeProb;
                return (
                  <p key={bookmaker} className="text-xs text-gray-500">
                    {bookmaker}: {homeProb.toFixed(0)}% /{" "}
                    {awayProb.toFixed(0)}%
                  </p>
                );
              })}
            </div>
          )}
        </div>
      );
    }
    return null;
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
                      ? "bg-white/10 text-white/40"
                      : "text-white/15 hover:text-white/25"
                  }`
                : `px-3 py-1.5 text-xs ${
                    timeRange === option.value
                      ? "bg-gray-900 text-white"
                      : "bg-gray-100 text-gray-600 hover:bg-gray-200"
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
                  stopOpacity={0.25}
                />
                <stop
                  offset={gradientOffset}
                  stopColor="#3b82f6"
                  stopOpacity={0.25}
                />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis
              dataKey="time"
              tick={{ fontSize: 10, fill: "#6b7280" }}
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
              tick={{ fontSize: 10, fill: "#6b7280" }}
              tickLine={false}
              axisLine={{ stroke: "#e5e7eb" }}
              tickFormatter={formatYTick}
            />
            {/* 50% reference line */}
            <ReferenceLine
              y={0}
              stroke="#9ca3af"
              strokeWidth={1.5}
              strokeDasharray="4 4"
              label={{
                value: "50%",
                position: "right",
                style: { fontSize: 10, fill: "#9ca3af" },
              }}
            />
            <Tooltip content={<CustomTooltip />} />

            {/* Individual bookmaker lines - thin grey */}
            {bookmakers.map((bookmaker) => (
              <Line
                key={`${bookmaker}_delta`}
                type="monotone"
                dataKey={`${bookmaker}_delta`}
                stroke="rgba(156, 163, 175, 0.4)"
                strokeWidth={1}
                dot={false}
                activeDot={{ r: 3, fill: "#9ca3af" }}
                connectNulls
                legendType="none"
              />
            ))}

            {/* Model source lines (ESPN, stat model, etc.) — dashed */}
            {modelSources.map((source) => (
              <Line
                key={source.dataKey}
                type="monotone"
                dataKey={source.dataKey}
                name={source.displayName}
                stroke={source.color}
                strokeWidth={2.5}
                strokeDasharray={source.dashPattern ?? undefined}
                dot={false}
                activeDot={{ r: 4, fill: source.color }}
                connectNulls
              />
            ))}

            {/* Legacy ESPN line (when winProbHistory not available) */}
            {!useNewWinProbData && filteredEspnHistory.length > 0 && (
              <Line
                type="monotone"
                dataKey="espnDelta"
                name="ESPN Model"
                stroke="#f97316"
                strokeWidth={2.5}
                strokeDasharray="6 3"
                dot={false}
                activeDot={{ r: 4, fill: "#f97316" }}
                connectNulls
              />
            )}

            {/* Area fill between betting odds line and 50% */}
            <Area
              type="monotone"
              dataKey="homeDelta"
              stroke="none"
              fill="url(#probFillGradient)"
              connectNulls
              legendType="none"
              isAnimationActive={false}
            />

            {/* Betting odds line — solid, on top */}
            <Line
              type="monotone"
              dataKey="homeDelta"
              name="Betting Odds"
              stroke="#374151"
              strokeWidth={2.5}
              dot={false}
              activeDot={{ r: 5, fill: "#374151" }}
              connectNulls
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Source legend — always shown, all sources labeled, links to models page */}
      {resolvedSources.length > 0 && (
        <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1 shrink-0">
          {resolvedSources.map((source) => {
            const inner = (
              <>
                <svg width="20" height="4" className="shrink-0">
                  <line
                    x1="0" y1="2" x2="20" y2="2"
                    stroke={source.color}
                    strokeWidth="2.5"
                    strokeDasharray={source.dashPattern ?? undefined}
                  />
                </svg>
                <span className="text-xs text-gray-500 hover:text-gray-700">
                  {source.displayName}
                  <span className="text-gray-400 ml-0.5">({source.type})</span>
                </span>
              </>
            );
            return eventId ? (
              <Link
                key={source.key}
                href={`/events/${eventId}/models`}
                className="flex items-center gap-1.5 hover:underline"
              >
                {inner}
              </Link>
            ) : (
              <div key={source.key} className="flex items-center gap-1.5">
                {inner}
              </div>
            );
          })}
          {bookmakers.length > 0 && (
            <div className="flex items-center gap-1.5">
              <svg width="20" height="4" className="shrink-0">
                <line
                  x1="0" y1="2" x2="20" y2="2"
                  stroke="rgba(156, 163, 175, 0.4)"
                  strokeWidth="1"
                />
              </svg>
              <span className="text-xs text-gray-400">
                Individual sportsbooks
              </span>
            </div>
          )}
        </div>
      )}

      {/* Tap for details */}
      <p className="text-xs text-gray-400 text-center shrink-0">
        Tap/hover for details
      </p>
    </div>
  );
}
