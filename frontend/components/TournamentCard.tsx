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
  const tour = tournament.tour?.toLowerCase() || "pga";
  const tourSlug = tour === "dp_world" ? "dpworld" : tour === "korn_ferry" ? "kft" : tour;
  const href = hrefOverride || `/sport/golf/${tourSlug}/${slug}`;

  // Cup events (Ryder Cup, Presidents Cup, etc.) with exactly 2 teams
  // get a head-to-head layout instead of leader + chasers
  const isCupH2H = _isCupEvent(tournament) && tournament.golfers.length === 2;

  if (isCupH2H) {
    return <CupCard tournament={tournament} href={href} />;
  }

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

          {/* Prop markets — captain picks, "will they play", etc. */}
          {tournament.prop_markets && tournament.prop_markets.length > 0 && (
            <div className="border-t border-border-light pt-2 mt-1 space-y-1.5">
              {tournament.prop_markets.slice(0, 3).map((pm) => (
                <div key={pm.name} className="px-0.5">
                  <div className="text-[10px] font-semibold text-text-tertiary uppercase tracking-wider mb-0.5">
                    {_cleanPropLabel(pm.name, tournament.name)}
                  </div>
                  <div className="flex gap-2 flex-wrap">
                    {pm.outcomes.slice(0, 3).map((o) => (
                      <span key={o.name} className="text-[11px] text-text-primary">
                        {o.name}{" "}
                        <span className="font-semibold tabular-nums">
                          {(o.probability * 100).toFixed(0)}%
                        </span>
                      </span>
                    ))}
                  </div>
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
// Cup / Head-to-Head Card (Ryder Cup, Presidents Cup, etc.)
// ============================================================================

function CupCard({ tournament, href }: { tournament: GolfTournament; href: string }) {
  const isLive = _isLive(tournament);
  const [teamA, teamB] = tournament.golfers;
  const probA = teamA.probability * 100;
  const probB = teamB.probability * 100;

  // Color mapping for known cup teams
  const teamColors: Record<string, { bg: string; text: string; bar: string }> = {
    "usa": { bg: "bg-blue-50", text: "text-blue-800", bar: "bg-blue-500" },
    "united states": { bg: "bg-blue-50", text: "text-blue-800", bar: "bg-blue-500" },
    "u.s.": { bg: "bg-blue-50", text: "text-blue-800", bar: "bg-blue-500" },
    "europe": { bg: "bg-amber-50", text: "text-amber-800", bar: "bg-amber-500" },
    "international": { bg: "bg-emerald-50", text: "text-emerald-800", bar: "bg-emerald-500" },
    "great britain & ireland": { bg: "bg-red-50", text: "text-red-800", bar: "bg-red-500" },
  };
  const defaultColor = { bg: "bg-gray-50", text: "text-gray-800", bar: "bg-gray-500" };
  const colorA = teamColors[teamA.name.toLowerCase()] || defaultColor;
  const colorB = teamColors[teamB.name.toLowerCase()] || defaultColor;

  return (
    <Link href={href} className="block">
      <div className="bg-white border border-border rounded-[10px] overflow-hidden hover:shadow-sm hover:border-gray-300 transition-all cursor-pointer">
        <div className="p-3.5 px-4">
          {/* Header */}
          <div className="mb-3">
            <div className="text-[11px] font-medium text-text-secondary flex items-center gap-1.5">
              <span>⛳ Cup</span>
              {isLive && (
                <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-red-500 uppercase tracking-wide">
                  <span className="w-[7px] h-[7px] rounded-full bg-red-500 animate-pulse" />
                  LIVE
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

          {/* Head-to-head: Team A — bar — Team B */}
          <div className="flex items-center gap-3 mb-1">
            {/* Team A (left) */}
            <div className="flex-1 text-left">
              <div className={`text-xs font-semibold ${colorA.text}`}>{teamA.name}</div>
              <div className="text-[22px] font-extrabold tabular-nums tracking-tight">
                {probA.toFixed(1)}<span className="text-sm font-semibold">%</span>
              </div>
            </div>

            {/* VS divider */}
            <div className="text-[10px] font-bold text-text-tertiary uppercase">vs</div>

            {/* Team B (right) */}
            <div className="flex-1 text-right">
              <div className={`text-xs font-semibold ${colorB.text}`}>{teamB.name}</div>
              <div className="text-[22px] font-extrabold tabular-nums tracking-tight">
                {probB.toFixed(1)}<span className="text-sm font-semibold">%</span>
              </div>
            </div>
          </div>

          {/* Probability bar */}
          <div className="flex h-2 rounded-full overflow-hidden">
            <div className={`${colorA.bar} transition-all`} style={{ width: `${probA}%` }} />
            <div className={`${colorB.bar} transition-all`} style={{ width: `${probB}%` }} />
          </div>

          {/* Prop markets below */}
          {tournament.prop_markets && tournament.prop_markets.length > 0 && (
            <div className="border-t border-border-light pt-2 mt-3 space-y-1.5">
              {tournament.prop_markets.slice(0, 3).map((pm) => (
                <div key={pm.name} className="px-0.5">
                  <div className="text-[10px] font-semibold text-text-tertiary uppercase tracking-wider mb-0.5">
                    {_cleanPropLabel(pm.name, tournament.name)}
                  </div>
                  <div className="flex gap-2 flex-wrap">
                    {pm.outcomes.slice(0, 3).map((o) => (
                      <span key={o.name} className="text-[11px] text-text-primary">
                        {o.name}{" "}
                        <span className="font-semibold tabular-nums">
                          {(o.probability * 100).toFixed(0)}%
                        </span>
                      </span>
                    ))}
                  </div>
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

function _isCupEvent(tournament: GolfTournament): boolean {
  const key = tournament.key.toLowerCase();
  return key.includes("ryder") || key.includes("presidents") ||
    key.includes("walker") || key.includes("solheim");
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

function _cleanPropLabel(marketName: string, tournamentName: string): string {
  // Strip tournament name from the market label for brevity
  let label = marketName;
  // Remove "at 2027 Ryder Cup", "in 2026", "in the 2026 Masters" etc.
  label = label.replace(/\s+(?:at|in|for)\s+(?:the\s+)?(?:20\d{2}\s+)?/i, " · ");
  // Remove trailing "?"
  label = label.replace(/\s*\?\s*$/, "");
  // Remove leading year
  label = label.replace(/^20\d{2}\s+/, "");
  // If the label still contains the tournament name, strip it
  if (tournamentName) {
    const tn = tournamentName.replace(/^The\s+/i, "");
    label = label.replace(new RegExp(tn.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i"), "").trim();
    // Clean up leftover separators
    label = label.replace(/^\s*·\s*/, "").replace(/\s*·\s*$/, "").trim();
  }
  return label || marketName;
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
