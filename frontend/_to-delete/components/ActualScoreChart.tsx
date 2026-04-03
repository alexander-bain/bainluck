"use client";

import { useMemo } from "react";
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
  /** Event ID for analytics tracking */
  eventId?: number;
}

interface ChartDataPoint {
  timestamp: string;
  time: string;
  homeScore: number;
  awayScore: number;
}

/**
 * Line chart showing actual game score progression over time.
 * Displays how the score changed throughout the game.
 * Shows all available data - no filtering.
 */
export default function ActualScoreChart({
  scoreHistory,
  homeTeam,
  awayTeam,
  currentHomeScore,
  currentAwayScore,
  isLive = false,
}: ActualScoreChartProps) {
  // Transform all score history data for chart
  const chartData: ChartDataPoint[] = useMemo(() => {
    if (!scoreHistory || scoreHistory.length === 0) return [];
    return scoreHistory.map((point) => ({
      timestamp: point.timestamp,
      time: format(parseISO(point.timestamp), "h:mm"),
      homeScore: point.home_score,
      awayScore: point.away_score,
    }));
  }, [scoreHistory]);

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
            <div className="text-xl text-text-muted">—</div>
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

        {/* Message about score history */}
        <div className="text-center py-4 text-sm text-gray-500">
          Score progression tracking is not yet available for this event.
          <span className="block mt-1 text-text-muted">
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
        <div className="bg-surface-card p-3 rounded-lg shadow-lg border border-gray-200">
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
            <p className="text-xs text-text-muted mt-1 pt-1 border-t border-gray-100">
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
          <span className="text-text-muted">—</span>
          <span className="font-mono font-bold text-blue-600">{currentAwayScore}</span>
          {Math.abs(currentHomeScore - currentAwayScore) > 0 && (
            <span className="text-xs text-text-muted">
              ({currentHomeScore > currentAwayScore ? homeTeam.split(" ").pop() : awayTeam.split(" ").pop()} +{Math.abs(currentHomeScore - currentAwayScore)})
            </span>
          )}
        </div>
      )}
    </div>
  );
}
