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
      className="bg-[var(--surface-card)] border border-[var(--surface-border)] rounded-lg overflow-hidden"
      style={
        teamColors
          ? {
              borderTopColor: `rgb(${teamColors.primary})`,
              borderTopWidth: "2px",
            }
          : undefined
      }
      variants={staggerItem}
    >
      {/* Compact Header */}
      <div className="px-3 py-2 flex items-center gap-2 border-b border-[var(--surface-border)]/50">
        {headshotUrl && (
          <img
            src={headshotUrl}
            alt={playerName}
            className="w-7 h-7 rounded-full object-cover bg-[var(--surface-elevated)]"
          />
        )}
        <h3 className="text-sm font-semibold text-[var(--text-primary)] truncate flex-1">
          {playerName}
        </h3>
        <span
          className={`px-1.5 py-0.5 text-[10px] font-mono font-semibold rounded ${getStatColorClass(statCategory)}`}
        >
          {getStatLabel(statCategory)}
        </span>
      </div>

      {/* Compact sparkline */}
      <div className="px-3 py-1.5">
        <ThresholdSparkline
          points={sparklinePoints}
          highlightValue={sweetSpotLine.threshold_value}
          height={28}
          showLabels
        />
      </div>

      {/* Compact lines grid - 2 columns */}
      <div className="px-2 pb-2 grid grid-cols-2 gap-1">
        {sortedLines.slice(0, 6).map((line) => {
          const prob = line.probability ?? 0;
          const isSweet = line.id === sweetSpotLine.id;

          return (
            <button
              key={line.id}
              onClick={() => onLineClick?.(line)}
              className={`
                flex items-center justify-between gap-1 px-2 py-1 rounded text-xs
                transition-colors duration-[var(--duration-fast)]
                ${isSweet ? "bg-[var(--accent-brand)]/15" : "bg-[var(--surface-elevated)]/50 hover:bg-[var(--surface-elevated)]"}
              `}
            >
              <span className="font-mono text-[var(--text-secondary)]">
                {line.threshold_value}+
              </span>
              <span className={`font-mono font-bold ${probabilityColor(prob)}`}>
                {(prob * 100).toFixed(0)}%
              </span>
            </button>
          );
        })}
      </div>
    </motion.div>
  );
}
