"use client";

import Link from "next/link";

// ============================================================================
// Types
// ============================================================================

interface TournamentGolfer {
  name: string;
  probability: number;
  rank: number;
  movement_24h?: number;
  sources?: Record<string, number>;
}

interface TournamentCardData {
  name: string;
  slug: string;
  venue?: string | null;
  tour?: string;
  tour_label?: string;
  is_major?: boolean;
  schedule_status?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  golfers: TournamentGolfer[];
  current_round?: number | null;
  /** Optional: leaderboard data for live events */
  leaderboard?: {
    position: string;
    name: string;
    score: string;
    hole: string;
    win_prob: number;
  }[];
  /** Optional: TV channel */
  broadcast?: string | null;
}

interface TournamentCardProps {
  tournament: TournamentCardData;
  /** Override link destination (default: /categories/golf/tournaments/{slug}) */
  href?: string;
}

// ============================================================================
// Main Component — Feed-Native Hero Card
// ============================================================================

export default function TournamentCard({ tournament, href: hrefOverride }: TournamentCardProps) {
  const href = hrefOverride || `/categories/golf/tournaments/${tournament.slug}`;
  const isLive = tournament.schedule_status === "in-progress";
  const leader = tournament.leaderboard?.[0] || (tournament.golfers[0] ? {
    position: "1",
    name: tournament.golfers[0].name,
    score: "—",
    hole: "—",
    win_prob: tournament.golfers[0].probability * 100,
  } : null);

  const chasers = tournament.leaderboard
    ? tournament.leaderboard.slice(1, 5)
    : tournament.golfers.slice(1, 5).map((g) => ({
        position: String(g.rank),
        name: g.name,
        score: "—",
        hole: "—",
        win_prob: g.probability * 100,
      }));

  const tourLabel = tournament.tour_label || tournament.tour?.toUpperCase() || "Golf";
  const movement = tournament.golfers[0]?.movement_24h;

  return (
    <Link href={href} className="block">
      <div className="bg-white border border-border rounded-[10px] overflow-hidden hover:shadow-sm hover:border-gray-300 transition-all cursor-pointer">
        <div className="p-3.5 px-4">
          {/* Header row */}
          <div className="flex justify-between items-start mb-2">
            <div>
              <div className="text-[11px] font-medium text-text-secondary">
                ⛳ {tourLabel}
                {isLive && (
                  <span className="ml-1.5 inline-flex items-center gap-1 text-[11px] font-semibold text-red-500 uppercase tracking-wide">
                    <span className="w-[7px] h-[7px] rounded-full bg-red-500 animate-pulse" />
                    Round {tournament.current_round || "?"}
                  </span>
                )}
                {!isLive && tournament.start_date && (
                  <span className="ml-1.5 text-text-tertiary">
                    {formatTournamentDate(tournament.start_date, tournament.end_date)}
                  </span>
                )}
              </div>
              <div className="text-sm font-bold mt-0.5">{tournament.name}</div>
            </div>
            {tournament.broadcast && (
              <span className="text-[10px] font-semibold text-text-secondary px-1.5 py-0.5 rounded bg-gray-100 tracking-tight shrink-0">
                {tournament.broadcast}
              </span>
            )}
          </div>

          {/* Hero probability */}
          {leader && (
            <div className="flex items-center gap-3 py-2.5 px-3 bg-gray-50 rounded-lg mb-2.5">
              <div className="text-[28px] font-extrabold tabular-nums tracking-tight">
                {leader.win_prob.toFixed(1)}
                <span className="text-base font-semibold">%</span>
              </div>
              <div>
                <div className="text-sm font-semibold">{leader.name}</div>
                <div className="text-xs text-text-secondary">
                  Leader
                  {isLive && <> · {leader.score} · {leader.hole}</>}
                  {movement != null && Math.abs(movement) > 0.001 && (
                    <span className={movement > 0 ? " text-green-600 font-semibold" : " text-red-600 font-semibold"}>
                      {" "}{movement > 0 ? "+" : ""}{(movement * 100).toFixed(1)}% today
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
                    {lastName(c.name)}
                  </div>
                  <div className="text-[15px] font-bold tabular-nums">
                    {c.win_prob.toFixed(1)}%
                  </div>
                  {isLive && (
                    <div className="text-[10px] text-text-tertiary">
                      {c.score} · {c.hole}
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
// Helpers
// ============================================================================

function lastName(name: string): string {
  const parts = name.split(" ");
  return parts.length > 1 ? parts[parts.length - 1] : name;
}

function formatTournamentDate(start: string | null, end: string | null): string {
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

// Re-export types for use by other components
export type { TournamentCardData, TournamentGolfer };
