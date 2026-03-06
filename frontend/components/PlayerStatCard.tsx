"use client";

/**
 * PlayerStatCard — Grouped display for player prop markets.
 *
 * Shows all threshold lines for a single player + stat category in one card.
 * E.g., "Jayson Tatum Points" with 20+, 25+, 30+, 35+ lines displayed
 * as a mini distribution chart with probability bars.
 *
 * Visual design:
 * - Player name prominent at top with optional headshot
 * - Stat category badge (Points, Rebounds, Assists, etc.)
 * - Horizontal threshold distribution with sparkline
 * - Individual lines listed below with odds
 */

import { motion } from "framer-motion";
import { staggerContainer, staggerItem, transitionNormal } from "@/lib/animations";
import ThresholdSparkline from "./ThresholdSparkline";

interface StatLine {
  id: number;
  name: string;
  probability: number | null;
  threshold_value: number;
  threshold_direction: string;
  source?: string;
}

interface PlayerStatCardProps {
  /** Player name (e.g., "Jayson Tatum") */
  playerName: string;
  /** Stat category (e.g., "points", "rebounds") */
  statCategory: string;
  /** Array of threshold lines for this player/stat combo */
  lines: StatLine[];
  /** Optional player headshot URL */
  headshotUrl?: string;
  /** Optional team colors for styling */
  teamColors?: { primary: string; secondary: string };
  /** Optional click handler for individual lines */
  onLineClick?: (line: StatLine) => void;
  /** Compact mode for feed display */
  compact?: boolean;
}

const STAT_LABELS: Record<string, string> = {
  points: "PTS",
  rebounds: "REB",
  assists: "AST",
  steals: "STL",
  blocks: "BLK",
  threes: "3PM",
  strikeouts: "K",
  hits: "H",
  home_runs: "HR",
  rbis: "RBI",
  runs: "R",
  goals: "G",
  saves: "SV",
  shots: "SOG",
  sacks: "SACK",
  passing_yards: "PASS",
  rushing_yards: "RUSH",
  receiving_yards: "REC",
  touchdowns: "TD",
  completions: "CMP",
  interceptions: "INT",
  aces: "ACE",
  double_faults: "DF",
  kills: "K",
};

const STAT_COLORS: Record<string, string> = {
  points: "bg-blue-500/15 text-blue-400 border-blue-500/30",
  rebounds: "bg-amber-500/15 text-amber-400 border-amber-500/30",
  assists: "bg-green-500/15 text-green-400 border-green-500/30",
  steals: "bg-purple-500/15 text-purple-400 border-purple-500/30",
  blocks: "bg-red-500/15 text-red-400 border-red-500/30",
  threes: "bg-cyan-500/15 text-cyan-400 border-cyan-500/30",
  strikeouts: "bg-orange-500/15 text-orange-400 border-orange-500/30",
  goals: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  touchdowns: "bg-yellow-500/15 text-yellow-400 border-yellow-500/30",
};

function getStatLabel(category: string): string {
  return STAT_LABELS[category] || category.toUpperCase().slice(0, 4);
}

function getStatColorClass(category: string): string {
  return STAT_COLORS[category] || "bg-gray-500/15 text-gray-400 border-gray-500/30";
}

function probabilityColor(prob: number): string {
  if (prob >= 0.7) return "text-green-400";
  if (prob >= 0.4) return "text-amber-400";
  if (prob >= 0.15) return "text-orange-400";
  return "text-red-400";
}

export default function PlayerStatCard({
  playerName,
  statCategory,
  lines,
  headshotUrl,
  teamColors,
  onLineClick,
  compact = false,
}: PlayerStatCardProps) {
  // Sort lines by threshold value
  const sortedLines = [...lines].sort((a, b) => a.threshold_value - b.threshold_value);

  // Find the "sweet spot" line (closest to 50% probability)
  const sweetSpotLine = sortedLines.reduce((closest, line) => {
    const prob = line.probability ?? 0;
    const closestProb = closest.probability ?? 0;
    return Math.abs(prob - 0.5) < Math.abs(closestProb - 0.5) ? line : closest;
  }, sortedLines[0]);

  // Sparkline points
  const sparklinePoints = sortedLines.map((line) => ({
    id: line.id,
    name: line.name,
    probability: line.probability,
    threshold_value: line.threshold_value,
  }));

  if (compact) {
    return (
      <motion.div
        className="bg-[var(--surface-card)] border border-[var(--surface-border)] rounded-lg p-3 hover:border-[var(--accent-brand)]/30 transition-colors duration-[var(--duration-fast)]"
        variants={staggerItem}
      >
        <div className="flex items-center gap-3">
          {/* Player info */}
          <div className="flex items-center gap-2 min-w-0 flex-1">
            {headshotUrl && (
              <img
                src={headshotUrl}
                alt={playerName}
                className="w-8 h-8 rounded-full object-cover bg-[var(--surface-elevated)]"
              />
            )}
            <div className="min-w-0">
              <div className="text-sm font-medium text-[var(--text-primary)] truncate">
                {playerName}
              </div>
            </div>
          </div>

          {/* Stat badge */}
          <span
            className={`px-2 py-0.5 text-xs font-mono font-semibold rounded border ${getStatColorClass(statCategory)}`}
          >
            {getStatLabel(statCategory)}
          </span>

          {/* Sweet spot line */}
          <div className="text-right">
            <div className="text-xs text-[var(--text-muted)]">
              {sweetSpotLine.threshold_value}+
            </div>
            <div
              className={`text-sm font-mono font-bold ${probabilityColor(sweetSpotLine.probability ?? 0)}`}
            >
              {((sweetSpotLine.probability ?? 0) * 100).toFixed(0)}%
            </div>
          </div>
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      className="bg-[var(--surface-card)] border border-[var(--surface-border)] rounded-xl overflow-hidden"
      style={
        teamColors
          ? {
              borderTopColor: `rgb(${teamColors.primary})`,
              borderTopWidth: "3px",
            }
          : undefined
      }
      variants={staggerItem}
    >
      {/* Header */}
      <div className="p-4 pb-2 flex items-center gap-3">
        {/* Player headshot */}
        {headshotUrl && (
          <div className="relative">
            <img
              src={headshotUrl}
              alt={playerName}
              className="w-12 h-12 rounded-full object-cover bg-[var(--surface-elevated)]"
            />
          </div>
        )}

        {/* Player name + stat */}
        <div className="flex-1 min-w-0">
          <h3 className="text-base font-semibold text-[var(--text-primary)] truncate">
            {playerName}
          </h3>
          <span
            className={`inline-block mt-1 px-2 py-0.5 text-xs font-mono font-semibold rounded border ${getStatColorClass(statCategory)}`}
          >
            {getStatLabel(statCategory)}
          </span>
        </div>

        {/* Line count */}
        <div className="text-right">
          <div className="text-xs text-[var(--text-muted)]">Lines</div>
          <div className="text-lg font-mono font-bold text-[var(--text-primary)]">
            {lines.length}
          </div>
        </div>
      </div>

      {/* Sparkline */}
      <div className="px-4 py-2">
        <ThresholdSparkline
          points={sparklinePoints}
          highlightValue={sweetSpotLine.threshold_value}
          height={40}
          showLabels
        />
      </div>

      {/* Lines list */}
      <motion.div
        className="px-4 pb-4 pt-2 space-y-1"
        variants={staggerContainer}
        initial="hidden"
        animate="visible"
      >
        {sortedLines.map((line) => {
          const prob = line.probability ?? 0;
          const isSweet = line.id === sweetSpotLine.id;

          return (
            <motion.button
              key={line.id}
              variants={staggerItem}
              onClick={() => onLineClick?.(line)}
              className={`
                w-full flex items-center justify-between gap-2 px-3 py-2 rounded-lg
                transition-colors duration-[var(--duration-fast)]
                ${
                  isSweet
                    ? "bg-[var(--accent-brand)]/10 border border-[var(--accent-brand)]/30"
                    : "bg-[var(--surface-elevated)] hover:bg-[var(--surface-elevated)]/80"
                }
              `}
            >
              {/* Threshold */}
              <div className="flex items-center gap-2">
                <span className="text-xs text-[var(--text-muted)]">
                  {line.threshold_direction === "below" ? "U" : "O"}
                </span>
                <span className="text-sm font-mono font-semibold text-[var(--text-primary)]">
                  {line.threshold_value}
                </span>
              </div>

              {/* Probability bar + value */}
              <div className="flex items-center gap-2 flex-1 max-w-[120px]">
                <div className="flex-1 h-1.5 bg-[var(--surface-base)] rounded-full overflow-hidden">
                  <motion.div
                    className={`h-full rounded-full ${
                      prob >= 0.7
                        ? "bg-green-500"
                        : prob >= 0.4
                          ? "bg-amber-500"
                          : prob >= 0.15
                            ? "bg-orange-500"
                            : "bg-red-500"
                    }`}
                    initial={{ width: 0 }}
                    animate={{ width: `${prob * 100}%` }}
                    transition={transitionNormal}
                  />
                </div>
                <span className={`text-sm font-mono font-bold min-w-[36px] text-right ${probabilityColor(prob)}`}>
                  {(prob * 100).toFixed(0)}%
                </span>
              </div>
            </motion.button>
          );
        })}
      </motion.div>
    </motion.div>
  );
}
