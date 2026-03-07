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

const STAT_LABELS: Record<string, string> = {
  points: "PTS", rebounds: "REB", assists: "AST", steals: "STL", blocks: "BLK",
  threes: "3PM", strikeouts: "K", hits: "H", home_runs: "HR", goals: "G",
  touchdowns: "TD", passing_yards: "PASS", rushing_yards: "RUSH",
};

function getStatLabel(cat: string): string {
  return STAT_LABELS[cat] || cat.toUpperCase().slice(0, 3);
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
  const sorted = [...lines].sort((a, b) => a.threshold_value - b.threshold_value);
  // Show max 4 lines
  const display = sorted.slice(0, 4);

  return (
    <motion.div
      className="bg-surface-card border border-surface-border rounded-lg p-3 hover:bg-surface-elevated transition-colors"
      variants={staggerItem}
    >
      {/* Header: Player + Stat */}
      <div className="flex items-center gap-2 mb-1.5">
        {headshotUrl && (
          <img src={headshotUrl} alt="" className="w-6 h-6 rounded-full object-cover" />
        )}
        <span className="text-sm font-medium text-text-primary truncate flex-1">
          {playerName}
        </span>
        <span className="text-[10px] font-mono text-text-muted bg-surface-elevated px-1.5 py-0.5 rounded">
          {getStatLabel(statCategory)}
        </span>
      </div>
      
      {/* Event context */}
      {(eventMatchup || eventTimeStr) && (
        <div className="text-[10px] text-text-muted mb-2 flex items-center gap-1.5">
          {eventMatchup && <span>{eventMatchup}</span>}
          {eventMatchup && eventTimeStr && <span className="opacity-50">·</span>}
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
