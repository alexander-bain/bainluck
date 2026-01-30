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
import type { OddsHistoryPoint } from "@/lib/types";

interface OddsChartProps {
  history: OddsHistoryPoint[];
  homeTeam: string;
  awayTeam: string;
  commenceTime?: string;
  isLive?: boolean;
}

type TimeRange = "all" | "24h" | "12h" | "6h" | "3h" | "1h" | "live";

interface ChartDataPoint {
  timestamp: string;
  time: string;
  homeProb: number | null;
  awayProb: number | null;
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
 * Line chart showing probability changes over time.
 * Focused on win probability trend only.
 */
export default function OddsChart({
  history,
  homeTeam,
  awayTeam,
  commenceTime,
  isLive = false,
}: OddsChartProps) {
  const [timeRange, setTimeRange] = useState<TimeRange>(isLive ? "live" : "24h");

  // Filter history based on time range
  const filteredHistory = useMemo(() => {
    if (!history || history.length === 0) return [];

    const now = new Date();
    let cutoffTime: Date;

    switch (timeRange) {
      case "live":
        // Show from game start time
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

  if (!history || history.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center bg-gray-50 rounded-lg text-gray-500">
        No history data available
      </div>
    );
  }

  // Transform data for chart
  // Expand points with valid_until into two points for flat line display
  const chartData: ChartDataPoint[] = filteredHistory.flatMap((point) => {
    const startPoint: ChartDataPoint = {
      timestamp: point.timestamp,
      time: format(parseISO(point.timestamp), "h:mm a"),
      homeProb: point.home_probability !== null ? point.home_probability * 100 : null,
      awayProb: point.away_probability !== null ? point.away_probability * 100 : null,
    };

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
        return [startPoint, endPoint];
      }
    }

    return [startPoint];
  });

  // Calculate Y-axis domain for probability (with some padding around actual values)
  const probValues = chartData
    .flatMap((d) => [d.homeProb, d.awayProb])
    .filter((v): v is number => v !== null);

  const minProb = probValues.length > 0 ? Math.floor(Math.min(...probValues) / 5) * 5 : 0;
  const maxProb = probValues.length > 0 ? Math.ceil(Math.max(...probValues) / 5) * 5 : 100;

  // Custom tooltip
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
      return (
        <div className="bg-white p-3 rounded-lg shadow-lg border border-gray-200">
          <p className="text-xs text-gray-500 mb-2">{label}</p>
          {payload.map((entry, index) => (
            <p
              key={index}
              className="text-sm font-semibold"
              style={{ color: entry.color }}
            >
              {entry.name}: {entry.value?.toFixed(1)}%
            </p>
          ))}
        </div>
      );
    }
    return null;
  };

  return (
    <div className="space-y-4">
      {/* Time range selector */}
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
              interval="preserveStartEnd"
            />
            <YAxis
              domain={[Math.max(0, minProb - 5), Math.min(100, maxProb + 5)]}
              tick={{ fontSize: 10, fill: "#6b7280" }}
              tickLine={false}
              axisLine={{ stroke: "#e5e7eb" }}
              tickFormatter={(value) => `${value}%`}
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend wrapperStyle={{ fontSize: "12px" }} iconType="circle" />
            <Line
              type="monotone"
              dataKey="homeProb"
              name={homeTeam}
              stroke="#22c55e"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
              connectNulls
            />
            <Line
              type="monotone"
              dataKey="awayProb"
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
