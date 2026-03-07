"use client";

/**
 * PlayerStatCard — Compact grouped display for player prop markets.
 * Designed to be similar in size/style to FuturesCard.
 */

import { motion } from "framer-motion";
import { staggerItem } from "@/lib/animations";
import { cn } from "@/lib/utils";

interface StatLine {
  id: number;
  name: string;
  probability: number | null;
  threshold_value: number;
  threshold_direction: string;
  source?: string;
}

interface PlayerStatCardProps {
  playerName: string;
  statCategory: string;
  lines: StatLine[];
  headshotUrl?: string;
  onLineClick?: (line: StatLine) => void;
  compact?: boolean;
  /** Event context - e.g. "vs Lakers" or "LAL @ BOS" */
  eventMatchup?: string;
  /** Event start time (ISO string) */
  eventTime?: string;
}

const STAT_LABELS: Record<string, { abbr: string; full: string }> = {
  points:        { abbr: "PTS",  full: "Points" },
  rebounds:      { abbr: "REB",  full: "Rebounds" },
  assists:       { abbr: "AST",  full: "Assists" },
  steals:        { abbr: "STL",  full: "Steals" },
  blocks:        { abbr: "BLK",  full: "Blocks" },
  threes:        { abbr: "3PM",  full: "3-Pointers Made" },
  strikeouts:    { abbr: "K",    full: "Strikeouts" },
  hits:          { abbr: "H",    full: "Hits" },
  home_runs:     { abbr: "HR",   full: "Home Runs" },
  rbis:          { abbr: "RBI",  full: "RBIs" },
  goals:         { abbr: "G",    full: "Goals" },
  touchdowns:    { abbr: "TD",   full: "Touchdowns" },
  passing_yards: { abbr: "PASS", full: "Passing Yards" },
  rushing_yards: { abbr: "RUSH", full: "Rushing Yards" },
};

function getStatInfo(cat: string): { abbr: string; full: string } {
  return STAT_LABELS[cat] || { abbr: cat.toUpperCase().slice(0, 4), full: cat };
}

function probColor(p: number): string {
  if (p >= 0.7) return "text-green-400";
  if (p >= 0.4) return "text-text-primary";
  if (p >= 0.15) return "text-orange-400";
  return "text-red-400";
}

export default function PlayerStatCard({
  playerName,
  statCategory,
  lines,
  headshotUrl,
  onLineClick,
  eventMatchup,
  eventTime,
}: PlayerStatCardProps) {
  // Format event time
  const eventTimeStr = eventTime ? (() => {
    const d = new Date(eventTime);
    const now = new Date();
    const isToday = d.toDateString() === now.toDateString();
    const time = d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
    return isToday ? time : `${d.toLocaleDateString("en-US", { month: "short", day: "numeric" })} ${time}`;
  })() : null;
  const stat = getStatInfo(statCategory);
  const sorted = [...lines].sort((a, b) => a.threshold_value - b.threshold_value);
  const display = sorted.slice(0, 4);

  return (
    <motion.div
      className="bg-surface-card border border-surface-border rounded-lg p-3 hover:bg-surface-elevated transition-colors"
      variants={staggerItem}
    >
      {/* Header: Stat name prominent, player name secondary */}
      <div className="flex items-start justify-between gap-2 mb-1">
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-2">
            <span className="text-sm font-semibold text-text-primary">{stat.full}</span>
            <span className="text-[10px] font-mono text-text-muted">{stat.abbr}</span>
          </div>
          <div className="flex items-center gap-1 mt-0.5">
            {headshotUrl && (
              <img src={headshotUrl} alt="" className="w-4 h-4 rounded-full object-cover" />
            )}
            <span className="text-[11px] text-text-muted truncate">{playerName}</span>
          </div>
        </div>
      </div>

      {/* Event context */}
      {(eventMatchup || eventTimeStr) && (
        <div className="text-[10px] text-text-muted mb-2 flex items-center gap-1 border-t border-surface-border/40 pt-1.5 mt-1.5">
          {eventMatchup && <span className="font-medium text-text-secondary">{eventMatchup}</span>}
          {eventMatchup && eventTimeStr && <span className="opacity-40">·</span>}
          {eventTimeStr && <span>{eventTimeStr}</span>}
        </div>
      )}

      {/* Lines as simple rows */}
      <div className="space-y-1">
        {display.map((line, i) => {
          const prob = line.probability ?? 0;
          return (
            <button
              key={line.id}
              onClick={() => onLineClick?.(line)}
              className="w-full flex items-center gap-2 text-xs hover:bg-surface-elevated/50 rounded px-1 py-0.5 transition-colors"
            >
              <span className={cn(
                "w-4 h-4 flex items-center justify-center rounded text-[10px]",
                i === 0 ? "bg-accent-warning/15 text-accent-warning font-bold" : "text-text-muted"
              )}>
                {i + 1}
              </span>
              <span className="text-text-secondary flex-1 text-left">
                {line.threshold_value}+
              </span>
              <div className="w-12 h-1 bg-surface-border rounded-full overflow-hidden">
                <div
                  className="h-full bg-text-muted/50 rounded-full"
                  style={{ width: `${prob * 100}%`, opacity: i === 0 ? 0.8 : 0.4 }}
                />
              </div>
              <span className={cn("font-mono font-medium min-w-[32px] text-right", probColor(prob))}>
                {(prob * 100).toFixed(0)}%
              </span>
            </button>
          );
        })}
      </div>
    </motion.div>
  );
}
