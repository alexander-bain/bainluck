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
import type { PeriodBoundary } from "@/lib/periodMarkers";

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
  /** When true, chart fills its parent container height instead of using fixed h-40 */
  fillContainer?: boolean;
  /** Period boundaries for vertical divider annotations */
  periodBoundaries?: PeriodBoundary[];
  /** Home team primary color (hex) for team label styling */
  homeTeamColor?: string;
  /** Away team primary color (hex) for team label styling */
  awayTeamColor?: string;
  /** Home team logo URL (small) */
  homeTeamLogo?: string;
  /** Away team logo URL (small) */
  awayTeamLogo?: string;
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
  periodBoundaries,
  homeTeamColor,
  awayTeamColor,
  homeTeamLogo,
  awayTeamLogo,
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

  // Compute smart start time: find first significant odds movement after commence_time
  // This skips flat pre-game data that persists after the scheduled tip time
  const smartStartTime = useMemo(() => {
    if (!commenceTime || !history || history.length === 0) return null;
    const cutoff = parseISO(commenceTime);
    const postStart = history.filter((p) => parseISO(p.timestamp) >= cutoff);
    if (postStart.length <= 2) return cutoff;

    const baseline = postStart[0].home_probability;
    const firstChangeIdx = postStart.findIndex(
      (p) => Math.abs(p.home_probability - baseline) > 0.02
    );
    if (firstChangeIdx > 0) {
      return parseISO(postStart[Math.max(0, firstChangeIdx - 1)].timestamp);
    }
    return cutoff;
  }, [history, commenceTime]);

  // Filter projected history based on time range
  const filteredHistory = useMemo(() => {
    if (!history || history.length === 0) return [];
    if (timeRange === "all") return history;
    const cutoffTime = smartStartTime || (commenceTime ? parseISO(commenceTime) : new Date());
    return history.filter((point) => parseISO(point.timestamp) >= cutoffTime);
  }, [history, timeRange, commenceTime, smartStartTime]);

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
    const cutoffTime = smartStartTime || (commenceTime ? parseISO(commenceTime) : new Date());
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
  }, [bookmakerHistory, timeRange, commenceTime, smartStartTime]);

  // Filter score history based on time range
  const filteredScoreHistory = useMemo(() => {
    if (!scoreHistory || scoreHistory.length === 0) return [];
    if (timeRange === "all") return scoreHistory;
    const cutoffTime = smartStartTime || (commenceTime ? parseISO(commenceTime) : new Date());
    return scoreHistory.filter(
      (point) => parseISO(point.timestamp) >= cutoffTime
    );
  }, [scoreHistory, timeRange, commenceTime, smartStartTime]);

  const bookmakers = useMemo(
    () => Object.keys(filteredBookmakerHistory),
    [filteredBookmakerHistory]
  );

  const hasProjectedScoreData = useMemo(() => {
    if (!history || history.length === 0) return false;
    return history.some(
      (point) =>
        point.projected_home_score !== null &&
        point.projected_away_score !== null
    );
  }, [history]);

  const hasActualScoreData = filteredScoreHistory.length > 0;

  // Build chart data by merging projected and actual score data on timeline.
  // Bucket by minute so each "h:mm a" label is unique — required for
  // ReferenceLine period markers to match categorical XAxis values.
  const chartData: ChartDataPoint[] = useMemo(() => {
    const dataMap = new Map<string, ChartDataPoint>();

    /** Round an ISO timestamp to the start of its minute. */
    const toMinuteKey = (timestamp: string): string => {
      const d = parseISO(timestamp);
      d.setSeconds(0, 0);
      return d.toISOString();
    };

    const ensurePoint = (timestamp: string): ChartDataPoint => {
      const minuteKey = toMinuteKey(timestamp);
      let point = dataMap.get(minuteKey);
      if (!point) {
        point = {
          timestamp: minuteKey,
          time: format(parseISO(minuteKey), "h:mm a"),
          projectedDiff: null,
          actualDiff: null,
        };
        dataMap.set(minuteKey, point);
      }
      return point;
    };

    // Add projected score differentials from aggregate history
    for (const point of filteredHistory) {
      if (
        point.projected_home_score === null ||
        point.projected_away_score === null
      )
        continue;

      const diff = point.projected_home_score - point.projected_away_score;
      const dp = ensurePoint(point.timestamp);
      dp.projectedDiff = Math.round(diff * 10) / 10;

      // Expand valid_until for flat-line rendering
      if (point.valid_until) {
        const endTime = parseISO(point.valid_until);
        const startTime = parseISO(point.timestamp);
        if (endTime.getTime() - startTime.getTime() > 60000) {
          const endDp = ensurePoint(point.valid_until);
          if (endDp.projectedDiff === null) endDp.projectedDiff = Math.round(diff * 10) / 10;
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

        const dp = ensurePoint(point.timestamp);
        dp[`${bookmaker}_diff`] = diff;

        // Expand valid_until
        if (point.valid_until) {
          const endTime = parseISO(point.valid_until);
          const startTime = parseISO(point.timestamp);
          if (endTime.getTime() - startTime.getTime() > 60000) {
            const endDp = ensurePoint(point.valid_until);
            if (endDp[`${bookmaker}_diff`] === undefined) {
              endDp[`${bookmaker}_diff`] = diff;
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
      const dp = ensurePoint(point.timestamp);
      dp.actualDiff = diff;
    }

    return Array.from(dataMap.values()).sort(
      (a, b) =>
        parseISO(a.timestamp).getTime() - parseISO(b.timestamp).getTime()
    );
  }, [filteredHistory, filteredBookmakerHistory, filteredScoreHistory]);

  // Filter period boundaries to match chart time range
  const filteredPeriodBoundaries = useMemo(() => {
    if (!periodBoundaries || periodBoundaries.length === 0 || chartData.length === 0) return [];
    const chartStart = parseISO(chartData[0].timestamp).getTime();
    const chartEnd = parseISO(chartData[chartData.length - 1].timestamp).getTime();

    return periodBoundaries
      .filter((b) => {
        const t = parseISO(b.timestamp).getTime();
        return t >= chartStart && t <= chartEnd;
      })
      .map((b) => ({
        ...b,
        time: format(parseISO(b.timestamp), "h:mm a"),
      }));
  }, [periodBoundaries, chartData]);

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
      ? Math.max(...allDiffValues.map(Math.abs)) + 1
      : 5;
  // Make symmetric around 0, rounding up to nearest 2 for a tighter fit
  const domainMax = Math.max(2, Math.ceil(maxAbs / 2) * 2);

  // Short team names for axis labels
  const homeShort = homeTeam.split(" ").pop() || homeTeam;
  const awayShort = awayTeam.split(" ").pop() || awayTeam;

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
    if (active && payload && payload.length) {
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

      const formatDiff = (val: number) => {
        if (val === 0) return "Even";
        const leader = val > 0 ? homeShort : awayShort;
        return `${leader} +${Math.abs(val).toFixed(1)}`;
      };

      return (
        <div className="bg-surface-card p-3 rounded-lg shadow-lg border border-gray-200 max-w-xs">
          <p className="text-xs text-gray-500 mb-2">{label}</p>
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
            <div className="mt-2 pt-2 border-t border-gray-100">
              <p className="text-xs text-text-muted mb-1">By sportsbook:</p>
              {bookmakerEntries.map((entry) => {
                const bookmaker = entry.dataKey.replace("_diff", "");
                return (
                  <p key={bookmaker} className="text-xs text-gray-500">
                    {bookmaker}: {formatDiff(entry.value)}
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

      {/* Team labels above chart (which side = which team) */}
      <div className="flex items-center justify-between text-sm font-semibold px-8 shrink-0">
        <span className="flex items-center gap-1" style={{ color: homeTeamColor || "#16a34a" }}>
          {homeTeamLogo && (
            <img src={homeTeamLogo} alt="" width={16} height={16} className="w-4 h-4 object-contain" />
          )}
          + {homeShort} leading
        </span>
        <span className="flex items-center gap-1" style={{ color: awayTeamColor || "#2563eb" }}>
          {awayTeamLogo && (
            <img src={awayTeamLogo} alt="" width={16} height={16} className="w-4 h-4 object-contain" />
          )}
          − {awayShort} leading
        </span>
      </div>

      {/* Chart */}
      <div className={fillContainer ? "w-full flex-1 min-h-0" : "w-full h-40"}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={chartData}
            margin={{ top: 5, right: 10, left: fillContainer ? 5 : 0, bottom: 5 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis
              dataKey="time"
              tick={{ fontSize: 10, fill: "#6b7280" }}
              tickLine={false}
              axisLine={{ stroke: "#e5e7eb" }}
              interval="preserveStartEnd"
              minTickGap={50}
            />
            <YAxis
              domain={[-domainMax, domainMax]}
              tick={{ fontSize: 10, fill: "#6b7280" }}
              tickLine={false}
              axisLine={{ stroke: "#e5e7eb" }}
              tickFormatter={(value: number) => {
                if (value === 0) return "0";
                return value > 0 ? `+${value}` : `${value}`;
              }}
            />
            <ReferenceLine
              y={0}
              stroke="#6b7280"
              strokeWidth={2}
              label={{
                value: "0",
                position: "right",
                style: { fontSize: 10, fill: "#6b7280" },
              }}
            />
            {/* Period boundary markers — rendered in front of data area */}
            {filteredPeriodBoundaries.map((b) => (
              <ReferenceLine
                key={`period-${b.label}-${b.timestamp}`}
                x={b.time}
                stroke="#6b7280"
                strokeWidth={1.5}
                strokeDasharray="6 4"
                isFront
                label={{
                  value: b.label,
                  position: "insideTopLeft",
                  style: { fontSize: 11, fill: "#374151", fontWeight: 700 },
                }}
              />
            ))}
            <Tooltip content={<CustomTooltip />} />
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

            {/* Individual bookmaker lines */}
            {bookmakers.map((bookmaker) => (
              <Line
                key={`${bookmaker}_diff`}
                type="monotone"
                dataKey={`${bookmaker}_diff`}
                stroke="rgba(156, 163, 175, 0.4)"
                strokeWidth={1}
                dot={false}
                activeDot={{ r: 3, fill: "#9ca3af" }}
                connectNulls
                legendType="none"
              />
            ))}

            {/* Projected score differential (spread) */}
            {hasProjectedScoreData && (
              <Line
                type="monotone"
                dataKey="projectedDiff"
                name="Projected Spread"
                stroke="#10b981"
                strokeWidth={2.5}
                dot={false}
                activeDot={{ r: 5 }}
                connectNulls
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
                dot={false}
                activeDot={{ r: 5 }}
                connectNulls
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Info about gray lines */}
      {bookmakers.length > 0 && (
        <p className="text-xs text-text-muted text-center shrink-0">
          Gray lines show individual sportsbooks
        </p>
      )}
    </div>
  );
}
