"use client";

import { useMemo } from "react";
import type {
  FuturesOutcomeHistory,
  DataGolfLeaderboardEntry,
} from "@/lib/types";

interface EvolutionLeaderboardProps {
  /** History data per outcome */
  historyData: FuturesOutcomeHistory[];
  /** IDs of outcomes currently shown on chart */
  selectedOutcomeIds: Set<number>;
  /** Callback to toggle outcome on/off chart */
  onToggleOutcome: (outcomeId: number) => void;
  /** ID of outcome being hovered */
  highlightedOutcomeId?: number | null;
  /** Callback when user hovers a row */
  onHoverOutcome?: (outcomeId: number | null) => void;
  /** Optional leaderboard data from DataGolf (position, score, round, thru) */
  leaderboard?: DataGolfLeaderboardEntry[] | null;
  /** Optional class name */
  className?: string;
}

interface LeaderboardRow {
  outcomeId: number;
  name: string;
  currentProbability: number;
  change24h: number;
  /** DataGolf leaderboard position (e.g., "1", "T3") */
  position?: string | null;
  /** DataGolf total score (e.g., -12) */
  totalScore?: number | null;
  /** DataGolf today score (e.g., -3) */
  todayScore?: number | null;
  /** DataGolf thru holes (e.g., "14", "F") */
  thru?: string | null;
}

function formatScore(score: number | null | undefined): string {
  if (score == null) return "";
  if (score === 0) return "E";
  return score > 0 ? `+${score}` : `${score}`;
}

export function EvolutionLeaderboard({
  historyData,
  selectedOutcomeIds,
  onToggleOutcome,
  highlightedOutcomeId,
  onHoverOutcome,
  leaderboard,
  className,
}: EvolutionLeaderboardProps) {
  // Build leaderboard rows by merging history data with DataGolf leaderboard
  const rows = useMemo(() => {
    // Build a lookup from player name to leaderboard entry
    const lbLookup = new Map<string, DataGolfLeaderboardEntry>();
    if (leaderboard) {
      for (const entry of leaderboard) {
        lbLookup.set(entry.name.toLowerCase(), entry);
      }
    }

    return historyData
      .map((outcome): LeaderboardRow => {
        const history = outcome.history;
        const latest = history[history.length - 1]?.probability ?? 0;

        // Compute 24h change
        const now = Date.now();
        const cutoff24h = now - 24 * 60 * 60 * 1000;
        let oldest24h = latest;
        for (const point of history) {
          const ts = new Date(point.timestamp).getTime();
          if (ts >= cutoff24h) {
            oldest24h = point.probability ?? latest;
            break;
          }
        }
        const change24h = latest - oldest24h;

        // Try to match DataGolf leaderboard
        const lb = lbLookup.get(outcome.name.toLowerCase());

        return {
          outcomeId: outcome.outcome_id,
          name: outcome.name,
          currentProbability: latest,
          change24h,
          position: lb?.position,
          totalScore: lb?.total_score,
          todayScore: lb?.today_score,
          thru: lb?.thru,
        };
      })
      .sort((a, b) => b.currentProbability - a.currentProbability);
  }, [historyData, leaderboard]);

  const hasLeaderboardData = rows.some((r) => r.position != null);

  return (
    <div className={`text-sm ${className || ""}`}>
      {/* Header */}
      <div className="grid gap-2 px-2 py-1.5 text-xs text-gray-500 font-medium border-b border-gray-800"
        style={{
          gridTemplateColumns: hasLeaderboardData
            ? "28px 1fr 60px 50px 40px 40px 60px"
            : "28px 1fr 60px 60px",
        }}
      >
        <span></span>
        <span className="flex items-center gap-1.5">
          Player
          {hasLeaderboardData && (
            <span className="text-[9px] text-amber-400/70 bg-amber-400/10 px-1 py-0.5 rounded font-medium">
              DataGolf
            </span>
          )}
        </span>
        {hasLeaderboardData && (
          <>
            <span className="text-right">Pos</span>
            <span className="text-right">Score</span>
            <span className="text-right">Today</span>
            <span className="text-right">Thru</span>
          </>
        )}
        <span className="text-right">Prob</span>
        <span className="text-right">24h</span>
      </div>

      {/* Rows */}
      <div className="max-h-[480px] overflow-y-auto">
        {rows.map((row) => {
          const isSelected = selectedOutcomeIds.has(row.outcomeId);
          const isHighlighted = highlightedOutcomeId === row.outcomeId;

          return (
            <div
              key={row.outcomeId}
              className={`grid gap-2 px-2 py-2 cursor-pointer transition-colors border-b border-gray-800/50 ${
                isHighlighted
                  ? "bg-white/10"
                  : "hover:bg-white/5"
              }`}
              style={{
                gridTemplateColumns: hasLeaderboardData
                  ? "28px 1fr 60px 50px 40px 40px 60px"
                  : "28px 1fr 60px 60px",
              }}
              onClick={() => onToggleOutcome(row.outcomeId)}
              onMouseEnter={() => onHoverOutcome?.(row.outcomeId)}
              onMouseLeave={() => onHoverOutcome?.(null)}
            >
              {/* Toggle checkbox */}
              <div className="flex items-center justify-center">
                <div
                  className={`w-4 h-4 rounded border-2 flex items-center justify-center text-[10px] ${
                    isSelected
                      ? "border-yellow-400 bg-yellow-400/20 text-yellow-400"
                      : "border-gray-600 text-transparent"
                  }`}
                >
                  ✓
                </div>
              </div>

              {/* Name */}
              <span
                className={`truncate ${
                  isSelected ? "text-white" : "text-gray-400"
                }`}
              >
                {row.name}
              </span>

              {/* DataGolf leaderboard columns */}
              {hasLeaderboardData && (
                <>
                  <span className="text-right text-gray-300 font-mono">
                    {row.position ?? "—"}
                  </span>
                  <span className="text-right text-gray-300 font-mono">
                    {formatScore(row.totalScore)}
                  </span>
                  <span className="text-right text-gray-400 font-mono text-xs">
                    {formatScore(row.todayScore)}
                  </span>
                  <span className="text-right text-gray-400 font-mono text-xs">
                    {row.thru ?? "—"}
                  </span>
                </>
              )}

              {/* Probability */}
              <span className="text-right text-white font-mono">
                {(row.currentProbability * 100).toFixed(1)}%
              </span>

              {/* 24h change */}
              <span
                className={`text-right font-mono text-xs ${
                  row.change24h > 0.005
                    ? "text-green-400"
                    : row.change24h < -0.005
                      ? "text-red-400"
                      : "text-gray-500"
                }`}
              >
                {row.change24h > 0 ? "+" : ""}
                {(row.change24h * 100).toFixed(1)}%
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
