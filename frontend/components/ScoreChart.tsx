"use client";

import { useState, useMemo } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { format, parseISO } from "date-fns";
import type { OddsHistoryPoint, BookmakerHistoryPoint } from "@/lib/types";

interface ScoreChartProps {
  history: OddsHistoryPoint[];
  homeTeam: string;
  awayTeam: string;
  commenceTime?: string;
  isLive?: boolean;
  bookmakerHistory?: Record<string, BookmakerHistoryPoint[]>;
}

type TimeRange = "all" | "24h" | "12h" | "6h" | "3h" | "1h" | "live";

interface ChartDataPoint {
  timestamp: string;
  time: string;
  homeScore: number | null;
  awayScore: number | null;
  [key: string]: string | number | null; // For dynamic bookmaker keys
}

const TIME_RANGE_OPTIONS: { value: TimeRange; label: string }[] = [
  { value: "all", label: "All" },
  { value: "24h", label: "24h" },
  { value: "12h", label: "12h" },
  { value: "6h", label: "6h" },
  { value: "3h", label: "3h" },
  { value: "1h", label: "1h" },
  { value: "live", label: "Live" },
];

/**
 * Line chart showing projected score changes over time.
 * Y-axis is dynamically scaled to min/max values for better readability.
 */
export default function ScoreChart({
  history,
  homeTeam,
  awayTeam,
  commenceTime,
  isLive = false,
  bookmakerHistory,
}: ScoreChartProps) {
  const [timeRange, setTimeRange] = useState<TimeRange>(isLive ? "live" : "24h");
  const [showBookmakerLines, setShowBookmakerLines] = useState<boolean>(true);

  // Filter history based on time range
  const filteredHistory = useMemo(() => {
    if (!history || history.length === 0) return [];

    const now = new Date();
    let cutoffTime: Date;

    switch (timeRange) {
      case "live":
        cutoffTime = commenceTime ? parseISO(commenceTime) : now;
        break;
      case "1h":
        cutoffTime = new Date(now.getTime() - 1 * 60 * 60 * 1000);
        break;
      case "3h":
        cutoffTime = new Date(now.getTime() - 3 * 60 * 60 * 1000);
        break;
      case "6h":
        cutoffTime = new Date(now.getTime() - 6 * 60 * 60 * 1000);
        break;
      case "12h":
        cutoffTime = new Date(now.getTime() - 12 * 60 * 60 * 1000);
        break;
      case "24h":
        cutoffTime = new Date(now.getTime() - 24 * 60 * 60 * 1000);
        break;
      default:
        return history;
    }

    return history.filter((point) => parseISO(point.timestamp) >= cutoffTime);
  }, [history, timeRange, commenceTime]);

  // Filter bookmaker history based on time range
  const filteredBookmakerHistory = useMemo(() => {
    if (!bookmakerHistory || Object.keys(bookmakerHistory).length === 0) return {};

    const now = new Date();
    let cutoffTime: Date;

    switch (timeRange) {
      case "live":
        cutoffTime = commenceTime ? parseISO(commenceTime) : now;
        break;
      case "1h":
        cutoffTime = new Date(now.getTime() - 1 * 60 * 60 * 1000);
        break;
      case "3h":
        cutoffTime = new Date(now.getTime() - 3 * 60 * 60 * 1000);
        break;
      case "6h":
        cutoffTime = new Date(now.getTime() - 6 * 60 * 60 * 1000);
        break;
      case "12h":
        cutoffTime = new Date(now.getTime() - 12 * 60 * 60 * 1000);
        break;
      case "24h":
        cutoffTime = new Date(now.getTime() - 24 * 60 * 60 * 1000);
        break;
      default:
        return bookmakerHistory;
    }

    const filtered: Record<string, BookmakerHistoryPoint[]> = {};
    for (const [bookmaker, points] of Object.entries(bookmakerHistory)) {
      // Only include bookmakers that have projected score data
      const withScores = points.filter((point) => {
        const hasScores = point.projected_home_score !== null && point.projected_home_score !== undefined;
        if (!hasScores) return false;

        const pointTime = parseISO(point.timestamp);
        // Include if point starts after cutoff
        if (pointTime >= cutoffTime) return true;
        // Also include if point has valid_until that extends into the range
        if (point.valid_until) {
          const validUntil = parseISO(point.valid_until);
          if (validUntil >= cutoffTime) return true;
        }
        return false;
      });
      if (withScores.length > 0) {
        filtered[bookmaker] = withScores;
      }
    }
    return filtered;
  }, [bookmakerHistory, timeRange, commenceTime]);

  // Get list of bookmakers that have score data
  const bookmakers = useMemo(() => {
    return Object.keys(filteredBookmakerHistory);
  }, [filteredBookmakerHistory]);

  // Check if we have any projected score data
  const hasScoreData = useMemo(() => {
    if (!history || history.length === 0) return false;
    return history.some(
      (point) => point.projected_home_score !== null && point.projected_away_score !== null
    );
  }, [history]);

  // Check if any history points have over/under data (which is needed for score projection)
  const hasOverUnder = useMemo(() => {
    if (!history || history.length === 0) return false;
    return history.some((point) => point.over_under !== null);
  }, [history]);

  // Transform data for chart
  // Expand points with valid_until into two points for flat line display
  const chartData: ChartDataPoint[] = useMemo(() => {
    // Create a map of timestamp -> chart data point
    const dataMap = new Map<string, ChartDataPoint>();

    // First pass: add aggregate data points
    for (const point of filteredHistory) {
      if (point.projected_home_score === null || point.projected_away_score === null) continue;

      const startPoint: ChartDataPoint = {
        timestamp: point.timestamp,
        time: format(parseISO(point.timestamp), "h:mm a"),
        homeScore: point.projected_home_score,
        awayScore: point.projected_away_score,
      };
      dataMap.set(point.timestamp, startPoint);

      // If valid_until exists and is different from timestamp, add end point for flat line
      if (point.valid_until) {
        const endTime = parseISO(point.valid_until);
        const startTime = parseISO(point.timestamp);
        // Only add if valid_until is significantly later (>1 min)
        if (endTime.getTime() - startTime.getTime() > 60000) {
          const endPoint: ChartDataPoint = {
            timestamp: point.valid_until,
            time: format(endTime, "h:mm a"),
            homeScore: point.projected_home_score,
            awayScore: point.projected_away_score,
          };
          if (!dataMap.has(point.valid_until)) {
            dataMap.set(point.valid_until, endPoint);
          }
        }
      }
    }

    // Second pass: add bookmaker-specific data with valid_until expansion
    for (const [bookmaker, points] of Object.entries(filteredBookmakerHistory)) {
      for (const point of points) {
        if (point.projected_home_score === null || point.projected_home_score === undefined) continue;

        const homeScore = point.projected_home_score;
        const awayScore = point.projected_away_score ?? null;

        // Add start point
        const existing = dataMap.get(point.timestamp);
        if (existing) {
          // Add bookmaker data to existing point
          existing[`${bookmaker}_homeScore`] = homeScore;
          existing[`${bookmaker}_awayScore`] = awayScore;
        } else {
          // Create new point with bookmaker data
          const newPoint: ChartDataPoint = {
            timestamp: point.timestamp,
            time: format(parseISO(point.timestamp), "h:mm a"),
            homeScore: null,
            awayScore: null,
            [`${bookmaker}_homeScore`]: homeScore,
            [`${bookmaker}_awayScore`]: awayScore,
          };
          dataMap.set(point.timestamp, newPoint);
        }

        // If valid_until exists, add end point for continuous line
        if (point.valid_until) {
          const endTime = parseISO(point.valid_until);
          const startTime = parseISO(point.timestamp);
          // Only add if valid_until is significantly later (>1 min)
          if (endTime.getTime() - startTime.getTime() > 60000) {
            const existingEnd = dataMap.get(point.valid_until);
            if (existingEnd) {
              existingEnd[`${bookmaker}_homeScore`] = homeScore;
              existingEnd[`${bookmaker}_awayScore`] = awayScore;
            } else {
              const endPoint: ChartDataPoint = {
                timestamp: point.valid_until,
                time: format(endTime, "h:mm a"),
                homeScore: null,
                awayScore: null,
                [`${bookmaker}_homeScore`]: homeScore,
                [`${bookmaker}_awayScore`]: awayScore,
              };
              dataMap.set(point.valid_until, endPoint);
            }
          }
        }
      }
    }

    // Third pass: ensure all bookmaker keys exist on all data points (as null if missing)
    const allBookmakers = Object.keys(filteredBookmakerHistory);
    const allPoints = Array.from(dataMap.values());
    for (const point of allPoints) {
      for (const bookmaker of allBookmakers) {
        if (point[`${bookmaker}_homeScore`] === undefined) {
          point[`${bookmaker}_homeScore`] = null;
        }
        if (point[`${bookmaker}_awayScore`] === undefined) {
          point[`${bookmaker}_awayScore`] = null;
        }
      }
    }

    // Sort by timestamp and return as array
    return Array.from(dataMap.values()).sort(
      (a, b) => parseISO(a.timestamp).getTime() - parseISO(b.timestamp).getTime()
    );
  }, [filteredHistory, filteredBookmakerHistory]);

  // Early returns - placed after all hooks to satisfy React rules
  if (!history || history.length === 0) {
    return null; // Don't render if no history at all
  }

  // Show message if history exists but no projected scores
  // This happens when the event doesn't have spread/totals markets (e.g., tennis)
  if (!hasScoreData) {
    return (
      <div className="text-center py-4 text-sm text-gray-500">
        {hasOverUnder
          ? "Projected score history not yet available for this event."
          : "Score projections require spread/totals data which is not available for this event type."}
      </div>
    );
  }

  if (chartData.length === 0) {
    return null;
  }

  // Calculate Y-axis domain with padding (min-5 to max+5, but never below 0)
  const scoreValues = chartData
    .flatMap((d) => [d.homeScore, d.awayScore])
    .filter((v): v is number => v !== null);

  const minScore = Math.max(0, Math.floor(Math.min(...scoreValues) - 5));
  const maxScore = Math.ceil(Math.max(...scoreValues) + 5);

  // Custom tooltip with bookmaker grouping
  const CustomTooltip = ({
    active,
    payload,
    label,
  }: {
    active?: boolean;
    payload?: Array<{ value: number; name: string; color: string; dataKey: string }>;
    label?: string;
  }) => {
    if (active && payload && payload.length) {
      // Separate aggregate lines from bookmaker lines
      const aggregateEntries = payload.filter(
        (e) => e.dataKey === "homeScore" || e.dataKey === "awayScore"
      );
      const bookmakerEntries = payload.filter(
        (e) => e.dataKey !== "homeScore" && e.dataKey !== "awayScore" && e.value !== null
      );

      // Group bookmaker entries by bookmaker name
      const bookmakerGroups: Record<string, { home?: number; away?: number }> = {};
      for (const entry of bookmakerEntries) {
        const parts = entry.dataKey.split("_");
        const type = parts.pop(); // 'homeScore' or 'awayScore'
        const bookmaker = parts.join("_");
        if (!bookmakerGroups[bookmaker]) {
          bookmakerGroups[bookmaker] = {};
        }
        if (type === "homeScore") {
          bookmakerGroups[bookmaker].home = entry.value;
        } else {
          bookmakerGroups[bookmaker].away = entry.value;
        }
      }

      return (
        <div className="bg-white p-3 rounded-lg shadow-lg border border-gray-200 max-w-xs">
          <p className="text-xs text-gray-500 mb-2">{label}</p>
          {/* Aggregate scores */}
          {aggregateEntries.map((entry, index) => (
            <p
              key={index}
              className="text-sm font-semibold"
              style={{ color: entry.color }}
            >
              {entry.name}: {Math.round(entry.value)}
            </p>
          ))}
          {/* Bookmaker breakdown */}
          {Object.keys(bookmakerGroups).length > 0 && (
            <div className="mt-2 pt-2 border-t border-gray-100">
              <p className="text-xs text-gray-400 mb-1">By sportsbook:</p>
              {Object.entries(bookmakerGroups).map(([bookmaker, scores]) => (
                <p key={bookmaker} className="text-xs text-gray-500">
                  {bookmaker}: {scores.home !== undefined ? Math.round(scores.home) : "?"} - {scores.away !== undefined ? Math.round(scores.away) : "?"}
                </p>
              ))}
            </div>
          )}
        </div>
      );
    }
    return null;
  };

  return (
    <div className="space-y-4">
      {/* Time range selector and bookmaker toggle */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1">
          {TIME_RANGE_OPTIONS.map((option) => (
            <button
              key={option.value}
              onClick={() => setTimeRange(option.value)}
              className={`px-3 py-1.5 text-xs font-medium rounded-full transition-colors ${
                timeRange === option.value
                  ? "bg-gray-900 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
        {/* Bookmaker lines toggle - only show if there are multiple bookmakers */}
        {bookmakers.length > 0 && (
          <button
            onClick={() => setShowBookmakerLines(!showBookmakerLines)}
            className={`px-3 py-1.5 text-xs font-medium rounded-full transition-colors flex items-center gap-1.5 ${
              showBookmakerLines
                ? "bg-gray-200 text-gray-700"
                : "bg-gray-100 text-gray-500"
            }`}
            title={showBookmakerLines ? "Hide individual sportsbook lines" : "Show individual sportsbook lines"}
          >
            <span className="w-3 h-0.5 bg-gray-400 rounded"></span>
            <span className="hidden sm:inline">{showBookmakerLines ? "Hide" : "Show"} sources</span>
            <span className="sm:hidden">{bookmakers.length}</span>
          </button>
        )}
      </div>

      {/* Score Chart */}
      <div className="w-full h-64">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis
              dataKey="time"
              tick={{ fontSize: 10, fill: "#6b7280" }}
              tickLine={false}
              axisLine={{ stroke: "#e5e7eb" }}
              interval="preserveStartEnd"
            />
            <YAxis
              domain={[minScore, maxScore]}
              tick={{ fontSize: 10, fill: "#6b7280" }}
              tickLine={false}
              axisLine={{ stroke: "#e5e7eb" }}
              tickFormatter={(value) => Math.round(value).toString()}
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend wrapperStyle={{ fontSize: "12px" }} iconType="circle" />
            {/* Individual bookmaker lines - thin grey, rendered first so they appear behind aggregate */}
            {showBookmakerLines && bookmakers.map((bookmaker) => (
              <Line
                key={`${bookmaker}_homeScore`}
                type="monotone"
                dataKey={`${bookmaker}_homeScore`}
                stroke="rgba(156, 163, 175, 0.5)"
                strokeWidth={1}
                dot={false}
                activeDot={{ r: 3, fill: "#9ca3af" }}
                connectNulls
                legendType="none"
              />
            ))}
            {showBookmakerLines && bookmakers.map((bookmaker) => (
              <Line
                key={`${bookmaker}_awayScore`}
                type="monotone"
                dataKey={`${bookmaker}_awayScore`}
                stroke="rgba(156, 163, 175, 0.5)"
                strokeWidth={1}
                dot={false}
                activeDot={{ r: 3, fill: "#9ca3af" }}
                connectNulls
                legendType="none"
              />
            ))}
            {/* Aggregate lines - bold, rendered last so they appear on top */}
            <Line
              type="monotone"
              dataKey="homeScore"
              name={homeTeam}
              stroke="#22c55e"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
              connectNulls
            />
            <Line
              type="monotone"
              dataKey="awayScore"
              name={awayTeam}
              stroke="#3b82f6"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
              connectNulls
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Info about gray lines */}
      {showBookmakerLines && bookmakers.length > 0 && (
        <p className="text-xs text-gray-400 text-center">
          Gray lines show individual sportsbooks • Tap/hover for details
        </p>
      )}

      {/* No data message for filtered range */}
      {filteredHistory.length === 0 && history.length > 0 && (
        <div className="text-center py-4 text-sm text-gray-500">
          No data available for the selected time range.
          <button
            onClick={() => setTimeRange("all")}
            className="ml-2 text-blue-600 hover:underline"
          >
            Show all data
          </button>
        </div>
      )}
    </div>
  );
}
