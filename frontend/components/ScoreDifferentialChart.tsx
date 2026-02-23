"use client";

import { useState, useMemo } from "react";
import {
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import { format, parseISO } from "date-fns";
import type {
  OddsHistoryPoint,
  BookmakerHistoryPoint,
  ScoreHistoryPoint,
} from "@/lib/types";

/**
 * Same pastel palette as OddsChart for consistent bookmaker colors.
 */
const BOOKMAKER_COLORS = [
  "#93c5fd", "#fca5a5", "#86efac", "#c4b5fd", "#fdba74", "#67e8f9",
  "#f9a8d4", "#fde047", "#a5b4fc", "#6ee7b7", "#fda4af", "#a5f3fc",
];

interface ScoreDifferentialChartProps {
  history: OddsHistoryPoint[];
  homeTeam: string;
  awayTeam: string;
  commenceTime?: string;
  isLive?: boolean;
  bookmakerHistory?: Record<string, BookmakerHistoryPoint[]>;
  scoreHistory?: ScoreHistoryPoint[];
  currentHomeScore?: number | null;
  currentAwayScore?: number | null;
  eventStatus?: string;
  /** When true, chart fills its parent container height instead of using fixed h-48 */
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
  projectedDiff: number | null;
  actualDiff: number | null;
  [key: string]: string | number | null | undefined;
}

/**
 * Combined chart showing projected score differential (spread) and actual score difference.
 * Y-axis centered at 0. Positive = home team leading, negative = away team leading.
 * Bookmaker lines use distinct pastel colors with click-to-highlight.
 */
export default function ScoreDifferentialChart({
  history,
  homeTeam,
  awayTeam,
  commenceTime,
  isLive = false,
  bookmakerHistory,
  scoreHistory,
  currentHomeScore,
  currentAwayScore,
  eventStatus,
  fillContainer = false,
}: ScoreDifferentialChartProps) {
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

  // Filter projected history based on time range
  const filteredHistory = useMemo(() => {
    if (!history || history.length === 0) return [];
    if (timeRange === "all") return history;
    const cutoffTime = commenceTime ? parseISO(commenceTime) : new Date();
    return history.filter((point) => parseISO(point.timestamp) >= cutoffTime);
  }, [history, timeRange, commenceTime]);

  // Filter bookmaker history based on time range
  const filteredBookmakerHistory = useMemo(() => {
    if (!bookmakerHistory || Object.keys(bookmakerHistory).length === 0)
      return {};
    const entries = Object.entries(bookmakerHistory);
    if (timeRange === "all") {
      const filtered: Record<string, BookmakerHistoryPoint[]> = {};
      for (const [bookmaker, points] of entries) {
        const withScores = points.filter(
          (point) =>
            point.projected_home_score !== null &&
            point.projected_home_score !== undefined
        );
        if (withScores.length > 0) filtered[bookmaker] = withScores;
      }
      return filtered;
    }
    const cutoffTime = commenceTime ? parseISO(commenceTime) : new Date();
    const filtered: Record<string, BookmakerHistoryPoint[]> = {};
    for (const [bookmaker, points] of entries) {
      const withScores = points.filter((point) => {
        const hasScores =
          point.projected_home_score !== null &&
          point.projected_home_score !== undefined;
        if (!hasScores) return false;
        return parseISO(point.timestamp) >= cutoffTime;
      });
      if (withScores.length > 0) filtered[bookmaker] = withScores;
    }
    return filtered;
  }, [bookmakerHistory, timeRange, commenceTime]);

  // Filter score history based on time range
  const filteredScoreHistory = useMemo(() => {
    if (!scoreHistory || scoreHistory.length === 0) return [];
    if (timeRange === "all") return scoreHistory;
    const cutoffTime = commenceTime ? parseISO(commenceTime) : new Date();
    return scoreHistory.filter(
      (point) => parseISO(point.timestamp) >= cutoffTime
    );
  }, [scoreHistory, timeRange, commenceTime]);

  const bookmakers = useMemo(
    () => Object.keys(filteredBookmakerHistory),
    [filteredBookmakerHistory]
  );

  // Stable bookmaker color assignment
  const bookmakerColorMap = useMemo(() => {
    const map: Record<string, string> = {};
    const allBooks = Object.keys(bookmakerHistory ?? {});
    allBooks.forEach((bk, i) => {
      map[bk] = BOOKMAKER_COLORS[i % BOOKMAKER_COLORS.length];
    });
    return map;
  }, [bookmakerHistory]);

  const hasProjectedScoreData = useMemo(() => {
    if (!history || history.length === 0) return false;
    return history.some(
      (point) =>
        point.projected_home_score !== null &&
        point.projected_away_score !== null
    );
  }, [history]);

  const hasActualScoreData = filteredScoreHistory.length > 0;

  // Build chart data by merging projected and actual score data on timeline
  const chartData: ChartDataPoint[] = useMemo(() => {
    const dataMap = new Map<string, ChartDataPoint>();

    // Add projected score differentials from aggregate history
    for (const point of filteredHistory) {
      if (
        point.projected_home_score === null ||
        point.projected_away_score === null
      )
        continue;

      const diff = point.projected_home_score - point.projected_away_score;
      const dp: ChartDataPoint = {
        timestamp: point.timestamp,
        time: format(parseISO(point.timestamp), "h:mm a"),
        projectedDiff: Math.round(diff * 10) / 10,
        actualDiff: null,
      };
      dataMap.set(point.timestamp, dp);

      // Expand valid_until for flat-line rendering
      if (point.valid_until) {
        const endTime = parseISO(point.valid_until);
        const startTime = parseISO(point.timestamp);
        if (endTime.getTime() - startTime.getTime() > 60000) {
          if (!dataMap.has(point.valid_until)) {
            dataMap.set(point.valid_until, {
              timestamp: point.valid_until,
              time: format(endTime, "h:mm a"),
              projectedDiff: Math.round(diff * 10) / 10,
              actualDiff: null,
            });
          }
        }
      }
    }

    // Add bookmaker differential lines
    for (const [bookmaker, points] of Object.entries(
      filteredBookmakerHistory
    )) {
      for (const point of points) {
        if (
          point.projected_home_score === null ||
          point.projected_home_score === undefined
        )
          continue;
        const awayScore = point.projected_away_score ?? 0;
        const diff =
          Math.round((point.projected_home_score - awayScore) * 10) / 10;

        const existing = dataMap.get(point.timestamp);
        if (existing) {
          existing[`${bookmaker}_diff`] = diff;
        } else {
          const newPoint: ChartDataPoint = {
            timestamp: point.timestamp,
            time: format(parseISO(point.timestamp), "h:mm a"),
            projectedDiff: null,
            actualDiff: null,
            [`${bookmaker}_diff`]: diff,
          };
          dataMap.set(point.timestamp, newPoint);
        }

        // Expand valid_until
        if (point.valid_until) {
          const endTime = parseISO(point.valid_until);
          const startTime = parseISO(point.timestamp);
          if (endTime.getTime() - startTime.getTime() > 60000) {
            const existingEnd = dataMap.get(point.valid_until);
            if (existingEnd) {
              existingEnd[`${bookmaker}_diff`] = diff;
            } else {
              dataMap.set(point.valid_until, {
                timestamp: point.valid_until,
                time: format(endTime, "h:mm a"),
                projectedDiff: null,
                actualDiff: null,
                [`${bookmaker}_diff`]: diff,
              });
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
        if (point[`${bookmaker}_diff`] === undefined) {
          point[`${bookmaker}_diff`] = null;
        }
      }
    }

    // Add actual score differences
    for (const point of filteredScoreHistory) {
      const diff = point.home_score - point.away_score;
      const existing = dataMap.get(point.timestamp);
      if (existing) {
        existing.actualDiff = diff;
      } else {
        const newPoint: ChartDataPoint = {
          timestamp: point.timestamp,
          time: format(parseISO(point.timestamp), "h:mm a"),
          projectedDiff: null,
          actualDiff: diff,
        };
        for (const bookmaker of allBookmakers) {
          newPoint[`${bookmaker}_diff`] = null;
        }
        dataMap.set(point.timestamp, newPoint);
      }
    }

    return Array.from(dataMap.values()).sort(
      (a, b) =>
        parseISO(a.timestamp).getTime() - parseISO(b.timestamp).getTime()
    );
  }, [filteredHistory, filteredBookmakerHistory, filteredScoreHistory]);

  // Early returns
  if (!history || history.length === 0) return null;
  if (!hasProjectedScoreData && !hasActualScoreData) {
    return (
      <div className="text-center py-4 text-sm text-gray-500">
        Score data is not available for this event.
      </div>
    );
  }
  if (chartData.length === 0) return null;

  // Calculate Y-axis domain symmetrically around 0
  const allDiffValues = chartData
    .flatMap((d) => {
      const values: number[] = [];
      if (d.projectedDiff !== null) values.push(d.projectedDiff);
      if (d.actualDiff !== null) values.push(d.actualDiff);
      return values;
    })
    .filter((v): v is number => v !== null);

  const maxAbs =
    allDiffValues.length > 0
      ? Math.ceil(Math.max(...allDiffValues.map(Math.abs)) + 2)
      : 10;
  const domainMax = Math.ceil(maxAbs / 5) * 5;

  const homeShort = homeTeam.split(" ").pop() || homeTeam;
  const awayShort = awayTeam.split(" ").pop() || awayTeam;

  // (no highlight logic — all lines at base visual weight)

  const formatDiff = (val: number) => {
    if (val === 0) return "Even";
    const leader = val > 0 ? homeShort : awayShort;
    return `${leader} +${Math.abs(val).toFixed(1)}`;
  };

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

    const projectedEntry = payload.find(
      (e) => e.dataKey === "projectedDiff" && e.value !== null
    );
    const actualEntry = payload.find(
      (e) => e.dataKey === "actualDiff" && e.value !== null
    );
    const bookmakerEntries = payload.filter(
      (e) =>
        e.dataKey !== "projectedDiff" &&
        e.dataKey !== "actualDiff" &&
        e.value !== null
    );

    return (
      <div className="bg-white/95 backdrop-blur-sm p-3 rounded-lg shadow-xl border border-gray-200 max-w-xs">
        <p className="text-xs font-medium text-gray-500 mb-2">{label}</p>
        {projectedEntry && (
          <p className="text-sm font-semibold text-emerald-600">
            Projected: {formatDiff(projectedEntry.value)}
          </p>
        )}
        {actualEntry && (
          <p className="text-sm font-semibold text-orange-600">
            Actual: {formatDiff(actualEntry.value)}
          </p>
        )}
        {bookmakerEntries.length > 0 && (
          <div className="mt-2 pt-2 border-t border-gray-100 space-y-0.5">
            {bookmakerEntries.map((entry) => {
              const bookmaker = entry.dataKey.replace("_diff", "");
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
                    {formatDiff(entry.value)}
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

      {/* Chart */}
      <div className={fillContainer ? "w-full flex-1 min-h-0" : "w-full h-48"}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={chartData}
            margin={{ top: 5, right: 10, left: fillContainer ? 5 : 0, bottom: 5 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
            <XAxis
              dataKey="time"
              tick={{ fontSize: 10, fill: "#9ca3af" }}
              tickLine={false}
              axisLine={{ stroke: "#e5e7eb" }}
              interval="preserveStartEnd"
              minTickGap={50}
            />
            <YAxis
              domain={[-domainMax, domainMax]}
              tick={{ fontSize: 10, fill: "#9ca3af" }}
              tickLine={false}
              axisLine={{ stroke: "#e5e7eb" }}
              tickFormatter={(value: number) => {
                if (value === 0) return "0";
                return value > 0 ? `+${value}` : `${value}`;
              }}
            />
            <ReferenceLine
              y={0}
              stroke="#d1d5db"
              strokeWidth={1}
              strokeDasharray="4 4"
            />
            <Tooltip
              content={<CustomTooltip />}
              cursor={{ stroke: "#d1d5db", strokeWidth: 1, strokeDasharray: "3 3" }}
            />
            <Legend
              wrapperStyle={{ fontSize: "12px" }}
              iconType="circle"
              payload={[
                ...(hasProjectedScoreData
                  ? [
                      {
                        value: "Projected Spread" as string,
                        type: "circle" as const,
                        color: "#10b981",
                      },
                    ]
                  : []),
                ...(hasActualScoreData
                  ? [
                      {
                        value: "Actual Score Diff" as string,
                        type: "circle" as const,
                        color: "#f97316",
                      },
                    ]
                  : []),
              ]}
            />

            {/* Individual bookmaker lines — distinct pastel colors */}
            {bookmakers.map((bookmaker) => {
              const color = bookmakerColorMap[bookmaker] ?? "#d1d5db";
              return (
                <Line
                  key={`${bookmaker}_diff`}
                  type="monotone"
                  dataKey={`${bookmaker}_diff`}
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

            {/* Projected score differential (spread) */}
            {hasProjectedScoreData && (
              <Line
                type="monotone"
                dataKey="projectedDiff"
                name="Projected Spread"
                stroke="#10b981"
                strokeWidth={2.5}
                opacity={1}
                dot={false}
                activeDot={{ r: 5, fill: "#10b981", stroke: "#fff", strokeWidth: 1.5 }}
                connectNulls
                isAnimationActive={false}
              />
            )}

            {/* Actual score difference */}
            {hasActualScoreData && (
              <Line
                type="stepAfter"
                dataKey="actualDiff"
                name="Actual Score Diff"
                stroke="#f97316"
                strokeWidth={2.5}
                opacity={1}
                dot={false}
                activeDot={{ r: 5, fill: "#f97316", stroke: "#fff", strokeWidth: 1.5 }}
                connectNulls
                isAnimationActive={false}
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Legend + axis labels */}
      <div className="flex flex-wrap items-center justify-between text-xs text-text-muted px-2 shrink-0">
        <span>+ = {homeShort} leading</span>
        <span>- = {awayShort} leading</span>
      </div>
      {/* Sportsbooks identified via tooltip on hover — no legend labels needed */}
    </div>
  );
}
