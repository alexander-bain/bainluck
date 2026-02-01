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

interface OddsChartProps {
  history: OddsHistoryPoint[];
  homeTeam: string;
  awayTeam: string;
  commenceTime?: string;
  isLive?: boolean;
  bookmakerHistory?: Record<string, BookmakerHistoryPoint[]>;
  /** Event ID for analytics tracking */
  eventId?: number;
  /** Event status - determines default filter: closed/completed defaults to "Since Start", open defaults to "All" */
  eventStatus?: string;
}

type TimeRange = "all" | "live";

const TIME_RANGE_OPTIONS: { value: TimeRange; label: string }[] = [
  { value: "all", label: "All" },
  { value: "live", label: "Since Start" },
];

interface ChartDataPoint {
  timestamp: string;
  time: string;
  homeProb: number | null;
  awayProb: number | null;
  [key: string]: string | number | null; // For dynamic bookmaker keys
}

/**
 * Line chart showing probability changes over time.
 * Focused on win probability trend only.
 */
export default function OddsChart({
  history,
  homeTeam,
  awayTeam,
  commenceTime,
  isLive = false,
  bookmakerHistory,
  eventStatus,
}: OddsChartProps) {
  // Determine default time range based on event status:
  // - Closed/completed/live events: default to "Since Start"
  // - Open/scheduled events: default to "All"
  const isClosed = eventStatus === "closed" || eventStatus === "completed";
  const defaultTimeRange: TimeRange = isClosed || isLive ? "live" : "all";

  const [timeRange, setTimeRange] = useState<TimeRange>(defaultTimeRange);

  // Filter history based on time range
  const filteredHistory = useMemo(() => {
    if (!history || history.length === 0) return [];

    // "all" mode: show full history
    if (timeRange === "all") return history;

    // "live" mode: show from game start time
    const cutoffTime = commenceTime ? parseISO(commenceTime) : new Date();
    return history.filter((point) => parseISO(point.timestamp) >= cutoffTime);
  }, [history, timeRange, commenceTime]);

  // Filter bookmaker history based on time range
  const filteredBookmakerHistory = useMemo(() => {
    if (!bookmakerHistory || Object.keys(bookmakerHistory).length === 0) return {};

    // "all" mode: show full history
    if (timeRange === "all") return bookmakerHistory;

    // "live" mode: show from game start time only
    const cutoffTime = commenceTime ? parseISO(commenceTime) : new Date();

    const filtered: Record<string, BookmakerHistoryPoint[]> = {};
    for (const [bookmaker, points] of Object.entries(bookmakerHistory)) {
      filtered[bookmaker] = points.filter((point) => {
        const pointTime = parseISO(point.timestamp);
        return pointTime >= cutoffTime;
      });
    }
    return filtered;
  }, [bookmakerHistory, timeRange, commenceTime]);

  // Get list of bookmakers for rendering individual lines
  const bookmakers = useMemo(() => {
    return Object.keys(filteredBookmakerHistory);
  }, [filteredBookmakerHistory]);

  // Transform data for chart
  // Expand points with valid_until into two points for flat line display
  const chartData: ChartDataPoint[] = useMemo(() => {
    // Create a map of timestamp -> chart data point
    const dataMap = new Map<string, ChartDataPoint>();

    // First pass: add aggregate data points
    for (const point of filteredHistory) {
      const startPoint: ChartDataPoint = {
        timestamp: point.timestamp,
        time: format(parseISO(point.timestamp), "h:mm a"),
        homeProb: point.home_probability !== null ? point.home_probability * 100 : null,
        awayProb: point.away_probability !== null ? point.away_probability * 100 : null,
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
            homeProb: point.home_probability !== null ? point.home_probability * 100 : null,
            awayProb: point.away_probability !== null ? point.away_probability * 100 : null,
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
        const homeProb = point.home_probability !== null ? point.home_probability * 100 : null;
        const awayProb = point.away_probability !== null ? point.away_probability * 100 : null;

        // Add start point
        const existing = dataMap.get(point.timestamp);
        if (existing) {
          // Add bookmaker data to existing point
          existing[`${bookmaker}_home`] = homeProb;
          existing[`${bookmaker}_away`] = awayProb;
        } else {
          // Create new point with bookmaker data
          const newPoint: ChartDataPoint = {
            timestamp: point.timestamp,
            time: format(parseISO(point.timestamp), "h:mm a"),
            homeProb: null,
            awayProb: null,
            [`${bookmaker}_home`]: homeProb,
            [`${bookmaker}_away`]: awayProb,
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
              existingEnd[`${bookmaker}_home`] = homeProb;
              existingEnd[`${bookmaker}_away`] = awayProb;
            } else {
              const endPoint: ChartDataPoint = {
                timestamp: point.valid_until,
                time: format(endTime, "h:mm a"),
                homeProb: null,
                awayProb: null,
                [`${bookmaker}_home`]: homeProb,
                [`${bookmaker}_away`]: awayProb,
              };
              dataMap.set(point.valid_until, endPoint);
            }
          }
        }
      }
    }

    // Third pass: ensure all bookmaker keys exist on all data points (as null if missing)
    // This is required for connectNulls to work - undefined values don't connect
    const allBookmakers = Object.keys(filteredBookmakerHistory);
    const allPoints = Array.from(dataMap.values());
    for (const point of allPoints) {
      for (const bookmaker of allBookmakers) {
        if (point[`${bookmaker}_home`] === undefined) {
          point[`${bookmaker}_home`] = null;
        }
        if (point[`${bookmaker}_away`] === undefined) {
          point[`${bookmaker}_away`] = null;
        }
      }
    }

    // Sort by timestamp and return as array
    return Array.from(dataMap.values()).sort(
      (a, b) => parseISO(a.timestamp).getTime() - parseISO(b.timestamp).getTime()
    );
  }, [filteredHistory, filteredBookmakerHistory]);

  // Early return for empty history - must be after all hooks
  if (!history || history.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center bg-gray-50 rounded-lg text-gray-500">
        No history data available
      </div>
    );
  }

  // Calculate Y-axis domain for probability (with some padding around actual values)
  const probValues = chartData
    .flatMap((d) => [d.homeProb, d.awayProb])
    .filter((v): v is number => v !== null);

  const minProb = probValues.length > 0 ? Math.floor(Math.min(...probValues) / 5) * 5 : 0;
  const maxProb = probValues.length > 0 ? Math.ceil(Math.max(...probValues) / 5) * 5 : 100;

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
        (e) => e.dataKey === "homeProb" || e.dataKey === "awayProb"
      );
      const bookmakerEntries = payload.filter(
        (e) => e.dataKey !== "homeProb" && e.dataKey !== "awayProb" && e.value !== null
      );

      // Group bookmaker entries by bookmaker name
      const bookmakerGroups: Record<string, { home?: number; away?: number }> = {};
      for (const entry of bookmakerEntries) {
        const parts = entry.dataKey.split("_");
        const type = parts.pop(); // 'home' or 'away'
        const bookmaker = parts.join("_");
        if (!bookmakerGroups[bookmaker]) {
          bookmakerGroups[bookmaker] = {};
        }
        if (type === "home") {
          bookmakerGroups[bookmaker].home = entry.value;
        } else {
          bookmakerGroups[bookmaker].away = entry.value;
        }
      }

      return (
        <div className="bg-white p-3 rounded-lg shadow-lg border border-gray-200 max-w-xs">
          <p className="text-xs text-gray-500 mb-2">{label}</p>
          {/* Aggregate probabilities */}
          {aggregateEntries.map((entry, index) => (
            <p
              key={index}
              className="text-sm font-semibold"
              style={{ color: entry.color }}
            >
              {entry.name}: {entry.value?.toFixed(1)}%
            </p>
          ))}
          {/* Bookmaker breakdown */}
          {Object.keys(bookmakerGroups).length > 0 && (
            <div className="mt-2 pt-2 border-t border-gray-100">
              <p className="text-xs text-gray-400 mb-1">By sportsbook:</p>
              {Object.entries(bookmakerGroups).map(([bookmaker, probs]) => (
                <p key={bookmaker} className="text-xs text-gray-500">
                  {bookmaker}: {probs.home?.toFixed(0)}% / {probs.away?.toFixed(0)}%
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
      {/* Time range selector - only All and Since Start */}
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

      {/* Probability Chart */}
      <div className="w-full h-80">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis
              dataKey="time"
              tick={{ fontSize: 10, fill: "#6b7280" }}
              tickLine={false}
              axisLine={{ stroke: "#e5e7eb" }}
              interval={chartData.length <= 10 ? 0 : "preserveStartEnd"}
              minTickGap={50}
            />
            <YAxis
              domain={[Math.max(0, minProb - 5), Math.min(100, maxProb + 5)]}
              tick={{ fontSize: 10, fill: "#6b7280" }}
              tickLine={false}
              axisLine={{ stroke: "#e5e7eb" }}
              tickFormatter={(value) => `${value}%`}
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend
              wrapperStyle={{ fontSize: "12px" }}
              iconType="circle"
              payload={[
                { value: homeTeam, type: 'circle', color: '#22c55e' },
                { value: awayTeam, type: 'circle', color: '#3b82f6' },
              ]}
            />
            {/* Individual bookmaker lines - thin grey, rendered first so they appear behind aggregate */}
            {bookmakers.map((bookmaker) => (
              <Line
                key={`${bookmaker}_home`}
                type="monotone"
                dataKey={`${bookmaker}_home`}
                stroke="rgba(156, 163, 175, 0.5)"
                strokeWidth={1}
                dot={false}
                activeDot={{ r: 3, fill: "#9ca3af" }}
                connectNulls
                legendType="none"
              />
            ))}
            {bookmakers.map((bookmaker) => (
              <Line
                key={`${bookmaker}_away`}
                type="monotone"
                dataKey={`${bookmaker}_away`}
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
              dataKey="homeProb"
              name={homeTeam}
              stroke="#22c55e"
              strokeWidth={3}
              strokeOpacity={1}
              dot={false}
              activeDot={{ r: 5 }}
              connectNulls
            />
            <Line
              type="monotone"
              dataKey="awayProb"
              name={awayTeam}
              stroke="#3b82f6"
              strokeWidth={3}
              strokeOpacity={1}
              dot={false}
              activeDot={{ r: 5 }}
              connectNulls
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Info about gray lines */}
      {bookmakers.length > 0 && (
        <p className="text-xs text-gray-400 text-center">
          Gray lines show individual sportsbooks • Tap/hover for details
        </p>
      )}
    </div>
  );
}
