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
import type { ScoreHistoryPoint } from "@/lib/types";

interface ActualScoreChartProps {
  scoreHistory?: ScoreHistoryPoint[];
  homeTeam: string;
  awayTeam: string;
  currentHomeScore?: number | null;
  currentAwayScore?: number | null;
  commenceTime?: string;
  isLive?: boolean;
  lastScoreUpdate?: string;
}

type TimeRange = "all" | "1h" | "30m" | "15m";

interface ChartDataPoint {
  timestamp: string;
  time: string;
  homeScore: number;
  awayScore: number;
}

const TIME_RANGE_OPTIONS: { value: TimeRange; label: string }[] = [
  { value: "all", label: "Full Game" },
  { value: "1h", label: "1h" },
  { value: "30m", label: "30m" },
  { value: "15m", label: "15m" },
];

/**
 * Line chart showing actual game score progression over time.
 * Displays how the score changed throughout the game.
 */
export default function ActualScoreChart({
  scoreHistory,
  homeTeam,
  awayTeam,
  currentHomeScore,
  currentAwayScore,
  commenceTime,
  isLive = false,
  lastScoreUpdate,
}: ActualScoreChartProps) {
  const [timeRange, setTimeRange] = useState<TimeRange>("all");

  // Filter history based on time range
  const filteredHistory = useMemo(() => {
    if (!scoreHistory || scoreHistory.length === 0) return [];

    const now = new Date();
    let cutoffTime: Date;

    switch (timeRange) {
      case "15m":
        cutoffTime = new Date(now.getTime() - 15 * 60 * 1000);
        break;
      case "30m":
        cutoffTime = new Date(now.getTime() - 30 * 60 * 1000);
        break;
      case "1h":
        cutoffTime = new Date(now.getTime() - 60 * 60 * 1000);
        break;
      default:
        return scoreHistory;
    }

    return scoreHistory.filter((point) => parseISO(point.timestamp) >= cutoffTime);
  }, [scoreHistory, timeRange]);

  // Transform data for chart
  const chartData: ChartDataPoint[] = useMemo(() => {
    return filteredHistory.map((point) => ({
      timestamp: point.timestamp,
      time: format(parseISO(point.timestamp), "h:mm"),
      homeScore: point.home_score,
      awayScore: point.away_score,
    }));
  }, [filteredHistory]);

  // Check staleness of score data
  const scoreStaleMinutes = useMemo(() => {
    if (!lastScoreUpdate) return null;
    const lastUpdate = new Date(lastScoreUpdate);
    const now = new Date();
    return Math.round((now.getTime() - lastUpdate.getTime()) / (1000 * 60));
  }, [lastScoreUpdate]);

  const isScoreStale = scoreStaleMinutes !== null && scoreStaleMinutes > 10;

  // If no score history, show placeholder with current score if available
  if (!scoreHistory || scoreHistory.length === 0) {
    return (
      <div className="space-y-4">
        {/* Show current score if available */}
        {currentHomeScore != null && currentAwayScore != null && (
          <div className="flex items-center justify-center gap-6 py-6 bg-gray-50 rounded-lg">
            <div className="text-center">
              <div className="text-3xl font-bold font-mono text-gray-800">
                {currentHomeScore}
              </div>
              <div className="text-sm text-gray-500 mt-1">
                {homeTeam.split(" ").pop()}
              </div>
            </div>
            <div className="text-xl text-gray-400">—</div>
            <div className="text-center">
              <div className="text-3xl font-bold font-mono text-gray-800">
                {currentAwayScore}
              </div>
              <div className="text-sm text-gray-500 mt-1">
                {awayTeam.split(" ").pop()}
              </div>
            </div>
          </div>
        )}

        {/* Staleness warning */}
        {isScoreStale && (
          <div className="flex items-center justify-center gap-2 text-amber-600 bg-amber-50 px-4 py-2 rounded-lg text-sm">
            <span>⚠️</span>
            <span>Score last updated {scoreStaleMinutes} minutes ago</span>
          </div>
        )}

        {/* Message about score history */}
        <div className="text-center py-4 text-sm text-gray-500">
          Score progression tracking is not yet available for this event.
          <span className="block mt-1 text-gray-400">
            {isLive ? "Live score updates are provided by sportsbooks." : "Score shown is from when books closed."}
          </span>
        </div>
      </div>
    );
  }

  // Calculate Y-axis domain with padding
  const allScores = chartData.flatMap((d) => [d.homeScore, d.awayScore]);
  const minScore = Math.max(0, Math.min(...allScores) - 2);
  const maxScore = Math.max(...allScores) + 5;

  // Custom tooltip
  const CustomTooltip = ({
    active,
    payload,
    label,
  }: {
    active?: boolean;
    payload?: Array<{ value: number; name: string; color: string }>;
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
              {entry.name}: {entry.value}
            </p>
          ))}
          {payload.length === 2 && (
            <p className="text-xs text-gray-400 mt-1 pt-1 border-t border-gray-100">
              Margin: {Math.abs(payload[0].value - payload[1].value)}
            </p>
          )}
        </div>
      );
    }
    return null;
  };

  return (
    <div className="space-y-4">
      {/* Time range selector */}
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

        {/* Staleness indicator */}
        {isScoreStale && (
          <span className="text-xs text-amber-600 bg-amber-50 px-2 py-1 rounded-full">
            ⚠️ {scoreStaleMinutes}m ago
          </span>
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
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend wrapperStyle={{ fontSize: "12px" }} iconType="circle" />
            <Line
              type="stepAfter"
              dataKey="homeScore"
              name={homeTeam}
              stroke="#22c55e"
              strokeWidth={2}
              dot={{ fill: "#22c55e", r: 2 }}
              activeDot={{ r: 5 }}
            />
            <Line
              type="stepAfter"
              dataKey="awayScore"
              name={awayTeam}
              stroke="#3b82f6"
              strokeWidth={2}
              dot={{ fill: "#3b82f6", r: 2 }}
              activeDot={{ r: 5 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Current score summary */}
      {currentHomeScore != null && currentAwayScore != null && (
        <div className="flex items-center justify-center gap-4 text-sm">
          <span className="text-gray-500">Current:</span>
          <span className="font-mono font-bold text-green-600">{currentHomeScore}</span>
          <span className="text-gray-400">—</span>
          <span className="font-mono font-bold text-blue-600">{currentAwayScore}</span>
          {Math.abs(currentHomeScore - currentAwayScore) > 0 && (
            <span className="text-xs text-gray-400">
              ({currentHomeScore > currentAwayScore ? homeTeam.split(" ").pop() : awayTeam.split(" ").pop()} +{Math.abs(currentHomeScore - currentAwayScore)})
            </span>
          )}
        </div>
      )}

      {/* No data message for filtered range */}
      {filteredHistory.length === 0 && scoreHistory && scoreHistory.length > 0 && (
        <div className="text-center py-4 text-sm text-gray-500">
          No score changes in the selected time range.
          <button
            onClick={() => setTimeRange("all")}
            className="ml-2 text-blue-600 hover:underline"
          >
            Show full game
          </button>
        </div>
      )}
    </div>
  );
}
