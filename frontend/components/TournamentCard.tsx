"use client";

import Link from "next/link";
import { tournamentEventKey, eventPath } from "@/lib/eventKey";
import { formatProbability } from "@/lib/api";
import { formatMovementPoints, isRenderedMove } from "@/lib/probabilityDisplay";
import type { GolfTournament, GolfLeaderboardPlayer } from "@/lib/types";

// L2-78 Item 2 — golf-default flip. FLIPPED TRUE in Queue #213: Alex ruled the
// Event Concept page canonical (the URL law; concept = canonical) after his
// live-day side-by-side on The Open, so golf tournament rows now route to the
// unified /event/<domain>/<slug> surface instead of the bespoke golf tournament
// detail page. The old /categories/golf/tournaments/<slug> route 308s to the
// concept slug (see next.config.mjs) so bookmarks/indexed links follow. hrefOverride
// still wins.
const GOLF_DEFAULT_TO_EVENT_PAGE = true;

// ============================================================================
// Types
// ============================================================================

interface TournamentCardProps {
  tournament: GolfTournament;
  /** Optional leaderboard data (score, hole, position) from DataGolf */
  leaderboard?: GolfLeaderboardPlayer[];
  /** Override link destination */
  href?: string;
  /**
   * L2-159 / #235 Item 4: just-settled marquee tournament (T+36h WHAT-HIT
   * window). Leads result-first — the leader row becomes the CHAMPION, the live
   * pulse is suppressed, settled-means-settled grammar ("cards show results").
   */
  whatHit?: boolean;
}

// ============================================================================
// Main Component — Feed-Native Hero (Variant 3)
// ============================================================================

export default function TournamentCard({ tournament, leaderboard, href: hrefOverride, whatHit = false }: TournamentCardProps) {
  const slug = tournament.slug || tournament.key.replace(/_/g, "-");
  // Golf tournament rows land on the bespoke golf tournament detail surface
  // (/categories/golf/tournaments/[slug]) — it carries the live DataGolf
  // leaderboard/scores. NOT the generic /sport market page (#926), and — during
  // OPEN-SPRINT-1 (L2-66) — NOT /event/[key] either, until that surface's fused
  // live leaderboard clears the "leave-it-open-during-The-Open" bar. hrefOverride
  // still wins. The GOLF_DEFAULT_TO_EVENT_PAGE flip (above) redirects the default
  // to the Event Concept page when Alex greenlights it.
  const eventKey = tournamentEventKey(tournament);
  const defaultHref =
    GOLF_DEFAULT_TO_EVENT_PAGE && eventKey
      ? eventPath(eventKey)
      : `/categories/golf/tournaments/${slug}`;
  const href = hrefOverride || defaultHref;

  // Cup events (Ryder Cup, Presidents Cup, etc.) with exactly 2 teams
  // get a head-to-head layout instead of leader + chasers
  const isCupH2H = _isCupEvent(tournament) && tournament.golfers.length === 2;

  if (isCupH2H) {
    return <CupCard tournament={tournament} href={href} />;
  }

  // Determine live status. A just-settled WHAT-HIT card is never "live" (even if
  // residual 24h movement lingers) — it leads with the champion, not a pulse.
  const isLive = !whatHit && _isLive(tournament);
  const tourLabel = tournament.tour_label || tournament.tour?.toUpperCase() || "Golf";

  // Build leader + chasers from leaderboard (preferred) or golfers (fallback)
  const leader = _buildLeader(tournament, leaderboard);
  const chasers = _buildChasers(tournament, leaderboard);

  return (
    <Link href={href} className="block">
      <div className="bg-surface-card border border-border rounded-[10px] overflow-hidden hover:shadow-sm hover:border-text-muted transition-all cursor-pointer">
        <div className="p-3.5 px-4">
          {/* Header row */}
          <div className="flex justify-between items-start mb-2">
            <div>
              <div className="text-[11px] font-medium text-text-secondary flex items-center gap-1.5">
                <span>⛳ {tourLabel}</span>
                {whatHit && (
                  <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-accent-brand uppercase tracking-wide">
                    <span aria-hidden>🏁</span>
                    Final
                  </span>
                )}
                {isLive && (
                  <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-red-500 uppercase tracking-wide">
                    <span className="w-[7px] h-[7px] rounded-full bg-red-500 animate-pulse" />
                    {tournament.schedule_status === "in-progress" && tournament.start_date
                      ? `Round ${_currentRound(tournament)}`
                      : "LIVE"}
                  </span>
                )}
                {!isLive && !whatHit && (tournament.start_date || tournament.commence_time) && (
                  <span className="text-text-tertiary">
                    {_formatTournamentDate(tournament.start_date || (tournament.commence_time ?? null), tournament.end_date ?? null)}
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
            <div className="flex items-center gap-3 py-2.5 px-3 bg-surface-secondary rounded-lg mb-2.5">
              <div className="text-[28px] font-extrabold tabular-nums tracking-tight">
                {leader.winProb.toFixed(1)}
                <span className="text-base font-semibold">%</span>
              </div>
              <div>
                <div className="flex items-center gap-1.5">
                  <span className="text-sm font-semibold">{leader.name}</span>
                  {whatHit && (
                    <span className="bg-accent-brand/15 text-accent-brand px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide flex-shrink-0">
                      Won
                    </span>
                  )}
                </div>
                <div className="text-xs text-text-secondary">
                  {whatHit ? "Champion" : "Leader"}
                  {leader.score && <> · {leader.score}</>}
                  {/* No live "% today" movement once settled — the result is fixed. */}
                  {!whatHit && leader.hole && <> · {leader.hole}</>}
                  {/* #5623 — `movement` is a probability DELTA, so `* 100` is
                      percentage POINTS and this line called them `%`. A leader who
                      went 37.8% -> 47.8% read "+10.0%", which a reader takes as a
                      tenth more than he had (~4.8 points): under half the real move,
                      in a unit the number was never in. Same family as the Discover
                      pill (#4066) and the eight backend sentences (#5619).

                      TWO HOUSE RULES MEET HERE AND THEY PULL OPPOSITE WAYS ON PURPOSE
                      (ux/1217, Sat 2026-09-12). (a) The noun is the ABBREVIATION:
                      a badge takes `pts`, a sentence takes the word — the backend
                      prose says "moved up 38 points today", this compact caption
                      beside a name on a 390px card says `pts`, same as the Discover
                      pill. (b) The trailing zero is KEPT here and DROPPED by the
                      backend formatter, because this number's consistency is
                      INTERNAL to the card: it stands in a column with five sibling
                      `.toFixed(1)` probabilities (the hero at :112, both chasers at
                      :151, the two-outcome pair at :246/:257), 40px away, whereas
                      the backend sentence has no numbers beside it. Neither is drift
                      and neither should be "harmonised" to the other.

                      `formatMovementPoints` returns the ABSOLUTE magnitude, so the
                      sign is composed here — and it must be an explicit "-", not the
                      old `: ""`. The old empty branch worked only because
                      `(m * 100).toFixed(1)` carried its own minus; with an absolute
                      helper it would render a fall as a rise wearing red. */}
                  {!whatHit && leader.movement != null && isRenderedMove(leader.movement) && (
                    <span className={leader.movement > 0 ? " text-green-600 font-semibold" : " text-red-600 font-semibold"}>
                      {" "}{leader.movement > 0 ? "+" : "-"}{formatMovementPoints(leader.movement)} pts today
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
                          {formatProbability(o.probability)}
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
  const defaultColor = { bg: "bg-surface-secondary", text: "text-text-primary", bar: "bg-text-secondary" };
  const colorA = teamColors[teamA.name.toLowerCase()] || defaultColor;
  const colorB = teamColors[teamB.name.toLowerCase()] || defaultColor;

  return (
    <Link href={href} className="block">
      <div className="bg-surface-card border border-border rounded-[10px] overflow-hidden hover:shadow-sm hover:border-text-muted transition-all cursor-pointer">
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
                  {_formatTournamentDate(tournament.start_date || (tournament.commence_time ?? null), tournament.end_date ?? null)}
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
                          {formatProbability(o.probability)}
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
      // 🔴 #5690 — THE TWO ARMS OF THIS FUNCTION DISAGREE ABOUT UNITS, AND ONLY
      // ONE OF THEM USED TO SAY SO. `CardGolfer.movement` is consumed as a 0-1
      // probability DELTA: the render multiplies it by 100 (via
      // `formatMovementPoints`). The `golfers` arm below supplies exactly that.
      // `GET /api/golf/leaderboard` does NOT — it serves percent-scaled numbers,
      // `{"win_prob": 76.5, "win_prob_change": 28.2}` — so passing
      // `win_prob_change` straight through fed a 28.2 into a `* 100` and the
      // live Amgen Irish Open card read **"+2820.0 pts today"** beside a 76.5%
      // hero, on production, during the final round.
      //
      // The tell was already in this object: `winProb` is taken raw here and
      // `* 100`-ed on the other arm, because whoever wrote it knew the two
      // sources disagree about probability. The same fact about `movement` one
      // line down was missed.
      //
      // ⚠️ NORMALISE HERE, NOT AT THE RENDER. Dropping the `* 100` downstream
      // would fix this arm and break the `golfers` arm, which is the COMMON
      // path and is currently correct. The units have to be reconciled where
      // the two sources meet.
      movement: lb.win_prob_change == null ? null : lb.win_prob_change / 100,
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
  const now = new Date();

  // ⚠️ `start_date` / `end_date` are CALENDAR DATES stamped at midnight UTC —
  // the first and LAST DAY of the tournament, not the instants it starts and
  // stops. Measured on the served payload: 188 of 188 `pga_schedule` stamps and
  // 6 of 6 tournament windows are exactly `T00:00:00+00:00`. Comparing `now`
  // against the raw `end_date` instant retired the tournament at the START of
  // its final day, so the card went dark for the whole of the final round — in
  // every timezone, UTC included. The window closes when that day is OVER.
  //
  // And the window is a VETO, not a last-resort fallback. The sibling deciders
  // of this same boundary already treat it that way: `isTournamentLive` (end +1d)
  // and `isCompleted` (end +24h) in app/categories/golf/tournaments/[slug]/page.tsx.
  // As a fallback it was unreachable whenever `movement_24h` was non-zero, and
  // residual 24h movement outlives a tournament by a day — which left a pulsing
  // LIVE dot on a card whose champion had already been decided.
  if (tournament.start_date && tournament.end_date) {
    const start = new Date(tournament.start_date);
    const endOfLastDay = new Date(new Date(tournament.end_date).getTime() + 86400000);
    return now >= start && now < endOfLastDay;
  }

  if (tournament.schedule_status === "in-progress") return true;
  // No schedule window to veto against — fall back to the price signal.
  return tournament.golfers.some(
    (g) => g.movement_24h !== null && Math.abs(g.movement_24h) >= 0.01,
  );
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
