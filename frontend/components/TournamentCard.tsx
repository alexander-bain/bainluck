"use client";

import Link from "next/link";
import type { GolfTournament, GolfLeaderboardPlayer } from "@/lib/types";

// ============================================================================
// Types
// ============================================================================

interface TournamentCardProps {
  tournament: GolfTournament;
  /** Optional leaderboard data (score, hole, position) from DataGolf */
  leaderboard?: GolfLeaderboardPlayer[];
  /** Override link destination */
  href?: string;
}

// ============================================================================
// Main Component — Feed-Native Hero (Variant 3)
// ============================================================================

export default function TournamentCard({ tournament, leaderboard, href: hrefOverride }: TournamentCardProps) {
  const slug = tournament.slug || tournament.key.replace(/_/g, "-");
  const href = hrefOverride || `/categories/golf/tournaments/${slug}`;

  // Determine live status
  const isLive = _isLive(tournament);
  const tourLabel = tournament.tour_label || tournament.tour?.toUpperCase() || "Golf";

  // Build leader + chasers from leaderboard (preferred) or golfers (fallback)
  const leader = _buildLeader(tournament, leaderboard);
  const chasers = _buildChasers(tournament, leaderboard);

  return (
    <Link href={href} className="block">
      <div className="bg-white border border-border rounded-[10px] overflow-hidden hover:shadow-sm hover:border-gray-300 transition-all cursor-pointer">
        <div className="p-3.5 px-4">
          {/* Header row */}
          <div className="flex justify-between items-start mb-2">
            <div>
              <div className="text-[11px] font-medium text-text-secondary flex items-center gap-1.5">
                <span>⛳ {tourLabel}</span>
                {isLive && (
                  <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-red-500 uppercase tracking-wide">
                    <span className="w-[7px] h-[7px] rounded-full bg-red-500 animate-pulse" />
                    {tournament.schedule_status === "in-progress" && tournament.start_date
                      ? `Round ${_currentRound(tournament)}`
                      : "LIVE"}
                  </span>
                )}
                {!isLive && (tournament.start_date || tournament.commence_time) && (
                  <span className="text-text-tertiary">
                    {_formatTournamentDate(tournament.start_date || tournament.commence_time, tournament.end_date)}
                  </span>
                )}
              </div>
              <div className="text-sm font-bold mt-0.5">{tournament.name}</div>
              {tournament.venue && (
                <div className="text-[11px] text-text-tertiary">{tournament.venue}</div>
              )}
            </div>
            {/* TV badge placeholder — would come from ESPN data */}
          </div>

          {/* Hero probability — leader */}
          {leader && (
            <div className="flex items-center gap-3 py-2.5 px-3 bg-gray-50 rounded-lg mb-2.5">
              <div className="text-[28px] font-extrabold tabular-nums tracking-tight">
                {leader.winProb.toFixed(1)}
                <span className="text-base font-semibold">%</span>
              </div>
              <div>
                <div className="text-sm font-semibold">{leader.name}</div>
                <div className="text-xs text-text-secondary">
                  Leader
                  {leader.score && <> · {leader.score}</>}
                  {leader.hole && <> · {leader.hole}</>}
                  {leader.movement != null && Math.abs(leader.movement) > 0.001 && (
                    <span className={leader.movement > 0 ? " text-green-600 font-semibold" : " text-red-600 font-semibold"}>
                      {" "}{leader.movement > 0 ? "+" : ""}{(leader.movement * 100).toFixed(1)}% today
                    </span>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Chasers strip */}
          {chasers.length > 0 && (
            <div className="flex border-t border-border-light pt-2">
              {chasers.map((c, i) => (
                <div
                  key={c.name}
                  className={`flex-1 text-center py-1 ${i < chasers.length - 1 ? "border-r border-border-light" : ""}`}
                >
                  <div className="text-[11px] font-medium text-text-secondary truncate px-1">
                    {_lastName(c.name)}
                  </div>
                  <div className="text-[15px] font-bold tabular-nums">
                    {c.winProb.toFixed(1)}%
                  </div>
                  {(c.score || c.hole) && (
                    <div className="text-[10px] text-text-tertiary">
                      {c.score}{c.score && c.hole ? " · " : ""}{c.hole}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </Link>
  );
}

// ============================================================================
// Internal helpers
// ============================================================================

interface CardGolfer {
  name: string;
  winProb: number;
  score?: string | null;
  hole?: string | null;
  movement?: number | null;
}

function _buildLeader(tournament: GolfTournament, leaderboard?: GolfLeaderboardPlayer[]): CardGolfer | null {
  if (leaderboard?.length) {
    const lb = leaderboard[0];
    return {
      name: lb.name,
      winProb: lb.win_prob,
      score: lb.score,
      hole: lb.thru && lb.thru !== "F" ? `H${lb.thru}` : (lb.thru === "F" ? "F" : undefined),
      movement: lb.win_prob_change,
    };
  }
  const g = tournament.golfers[0];
  if (!g) return null;
  return {
    name: g.name,
    winProb: g.probability * 100,
    movement: g.movement_24h,
  };
}

function _buildChasers(tournament: GolfTournament, leaderboard?: GolfLeaderboardPlayer[]): CardGolfer[] {
  if (leaderboard && leaderboard.length > 1) {
    return leaderboard.slice(1, 5).map((lb) => ({
      name: lb.name,
      winProb: lb.win_prob,
      score: lb.score,
      hole: lb.thru && lb.thru !== "F" ? `H${lb.thru}` : (lb.thru === "F" ? "F" : undefined),
    }));
  }
  return tournament.golfers.slice(1, 5).map((g) => ({
    name: g.name,
    winProb: g.probability * 100,
  }));
}

function _isLive(tournament: GolfTournament): boolean {
  if (tournament.schedule_status === "in-progress") return true;
  // Fallback: significant movement = in progress
  if (tournament.golfers.some((g) => g.movement_24h !== null && Math.abs(g.movement_24h) >= 0.01)) return true;
  // Fallback: between start_date and end_date
  if (tournament.start_date && tournament.end_date) {
    const now = new Date();
    return now >= new Date(tournament.start_date) && now <= new Date(tournament.end_date);
  }
  return false;
}

function _currentRound(tournament: GolfTournament): string {
  if (!tournament.start_date) return "?";
  const start = new Date(tournament.start_date);
  const now = new Date();
  const daysDiff = Math.floor((now.getTime() - start.getTime()) / 86400000) + 1;
  return String(Math.min(Math.max(daysDiff, 1), 4));
}

function _lastName(name: string): string {
  const parts = name.split(" ");
  return parts.length > 1 ? parts[parts.length - 1] : name;
}

function _formatTournamentDate(start: string | null, end: string | null): string {
  if (!start) return "";
  try {
    const s = new Date(start);
    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    const sStr = `${months[s.getUTCMonth()]} ${s.getUTCDate()}`;
    if (!end) return sStr;
    const e = new Date(end);
    if (s.getUTCMonth() === e.getUTCMonth()) {
      return `${sStr}–${e.getUTCDate()}`;
    }
    return `${sStr}–${months[e.getUTCMonth()]} ${e.getUTCDate()}`;
  } catch {
    return "";
  }
}
