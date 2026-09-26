"use client";

import Link from "next/link";
import { tournamentEventKey, eventPath } from "@/lib/eventKey";
import { formatProbability } from "@/lib/api";
import { formatMovementPoints, isRenderedMove } from "@/lib/probabilityDisplay";
import { isTournamentLive } from "@/lib/tournamentLive";
import { resolveCupSideColors } from "@/lib/cupTeamSides";
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
  const eyebrowDate = _eyebrowDate(tournament);

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
                {!isLive && !whatHit && eyebrowDate && (
                  <span className="text-text-tertiary">
                    {eyebrowDate}
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

  // #8028 — the two sides' colours, resolved TOGETHER so the bar's two segments
  // can never paint the same value. The map used to be keyed on the raw
  // lowercased name, which no served side ever matches ("Team USA", "Team
  // World", "Team Europe" all carry the prefix), so every cup card on
  // production drew one grey block. Vocabulary and folding are shared with
  // `backend/app/utils/golf_event_format.py`; see `lib/cupTeamSides.ts`.
  const [colorA, colorB] = resolveCupSideColors(teamA.name, teamB.name);
  const eyebrowDate = _eyebrowDate(tournament);

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
              {!isLive && eyebrowDate && (
                <span className="text-text-tertiary">
                  {eyebrowDate}
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

          {/* Probability bar. Widths are the printed figures to one decimal, not
              the raw product: `0.145 * 100` emits `14.499999999999998%`. */}
          <div className="flex h-2 rounded-full overflow-hidden">
            <div className={`${colorA.bar} transition-all`} style={{ width: `${probA.toFixed(1)}%` }} />
            <div className={`${colorB.bar} transition-all`} style={{ width: `${probB.toFixed(1)}%` }} />
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
      // 🔴 #5713 — DO NOT DROP THESE TWO LINES AGAIN. #5690's fix replaced them
      // with the comment block below and shipped, so the live Amgen Irish Open
      // card read "Leader +32.4 pts today" where it had read
      // "Leader · -16 · H18 +32.4 pts today" — the leader lost its score and
      // hole while `_buildChasers` kept both, so one card showed the chasers'
      // positions and not the leader's. The guard arm named in this file's test
      // asserts both survive.
      score: lb.score,
      hole: lb.thru && lb.thru !== "F" ? `H${lb.thru}` : (lb.thru === "F" ? "F" : undefined),
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

// #7065 — THE BODY OF THIS DECISION MOVED TO `lib/tournamentLive.ts`, UNCHANGED.
// It is not the card's private business: `lib/feedSections.ts` and
// `app/my-stuff/page.tsx` decide which SECTION the same tournament is filed
// under, and they used to do it from `schedule_status` alone — a string measured
// as never occurring — so a card drawing the LIVE badge below was filed under
// `📅 Upcoming`. They now call the same function this does, so the badge and the
// heading above it cannot disagree. The reasoning behind each arm (UX-P180's
// midnight-UTC calendar dates, the window-as-veto) travelled with the code.
function _isLive(tournament: GolfTournament): boolean {
  return isTournamentLive(tournament);
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
    // Clean up leftover separators. #8782: Kalshi writes "Presidents Cup:
    // Hole-in-One", so a colon (or dash) is left behind as often as a "·". A
    // leading hyphen is only a separator when a space follows it — "-3.5" keeps
    // its sign.
    label = label
      .replace(/^\s*(?:[·:–—]|-(?=\s))\s*/, "")
      .replace(/\s*[·:–—-]\s*$/, "")
      .trim();
  }
  return label || marketName;
}

/**
 * #8123 — the eyebrow date, or "" when no date can be stated honestly.
 *
 * `start_date` is a date of play; `commence_time` is not. For a cup or a
 * long-horizon future carrying no schedule, `commence_time` is the moment the
 * market was first captured — the Ryder Cup was served
 * `2026-08-28T20:16:51+00:00` for an event whose own prop markets say 2027, and
 * a Ryder Cup session does not start at 20:16:51. The old `||` treated the two
 * fields as interchangeable, which is what turned a backend gap into a false
 * statement on the card: a date almost a month in the PAST on an upcoming event.
 *
 * So the fallback is refused in exactly the case where it is provably not a date
 * of play — no `start_date`, a `commence_time` already gone, and a
 * `resolution_date` still ahead. An event that has not resolved yet cannot have
 * been played on a date that has already passed. There print nothing, rather
 * than explain the emptiness (notice 34).
 *
 * Deliberately narrow; every other shape renders exactly as before. A real
 * `start_date` still wins, a FUTURE `commence_time` still shows, and a row with
 * no `resolution_date` is not second-guessed — we cannot prove those wrong, so
 * we do not suppress them. Deriving the missing year from `resolution_date` is a
 * product call and a backend one (`routes/golf.py` serves the nulls); this half
 * only stops the page asserting something false.
 */
function _eyebrowDate(tournament: GolfTournament): string {
  const { start_date, commence_time, resolution_date, end_date } = tournament;
  if (!start_date && commence_time && resolution_date) {
    const now = Date.now();
    const captured = new Date(commence_time).getTime();
    const resolves = new Date(resolution_date).getTime();
    if (
      !Number.isNaN(captured) &&
      !Number.isNaN(resolves) &&
      captured < now &&
      resolves > now
    ) {
      return "";
    }
  }
  return _formatTournamentDate(start_date || (commence_time ?? null), end_date ?? null);
}

/**
 * #8139 — a date outside the season on screen is printed WITH its year.
 *
 * A bare `Sep 17–19` is only unambiguous while every other row in the list is
 * this season. It is not: the archived 2026-08-29 payload served
 * `golfers_to_win_a_pga_tour_major_in_2027` with a `commence_time` of
 * 2028-01-14 and this function printed `Jan 14` — a date sixteen months away,
 * rendered as if it were next week, between two tournaments that started that
 * Thursday.
 *
 * It is also the precondition for #8139's producer half. `/api/golf` serves the
 * Ryder Cup with `start_date: null` today, so #8123 suppresses the row's date
 * rather than print a capture stamp (`_eyebrowDate` above). When that route
 * starts serving the calendar's real `2027-09-17`, the date lands on this
 * function with no further deploy — and a yearless `Sep 17–19` in a list of
 * 2026 tournaments is a worse answer than today's honest blank, not a better
 * one. The year has to be renderable BEFORE the payload can change.
 *
 * "Outside the season" is the CALENDAR YEAR, compared in UTC like every other
 * field here: golf's tours run to the calendar, the served dates are
 * midnight-UTC stamps, and a rule a reader can restate ("it says the year when
 * it isn't this year") beats one tuned to a tour's own season boundaries.
 * In-season rows — every row `/api/golf` serves today — render exactly the
 * bytes they rendered before.
 */
function _formatTournamentDate(start: string | null, end: string | null): string {
  if (!start) return "";
  try {
    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    const s = new Date(start);
    // An unparseable stamp used to reach the formatting and print the literal
    // "undefined NaN" on the card; with a year appended it would have become
    // "undefined NaN, NaN". A date we cannot read is a date we do not state
    // (notice 34: leave the space empty, never explain the emptiness).
    if (Number.isNaN(s.getTime())) return "";
    const eRaw = end ? new Date(end) : null;
    const e = eRaw && !Number.isNaN(eRaw.getTime()) ? eRaw : null;

    const thisYear = new Date().getUTCFullYear();
    const sYear = s.getUTCFullYear();
    const eYear = e ? e.getUTCFullYear() : sYear;
    const inSeason = sYear === thisYear && eYear === thisYear;

    const sStr = `${months[s.getUTCMonth()]} ${s.getUTCDate()}`;
    if (!e) return inSeason ? sStr : `${sStr}, ${sYear}`;

    // The end collapses to a bare day ONLY inside one month of one year —
    // without the year test a Sep 2026 → Sep 2027 window would read "Sep 17–19"
    // and hide the twelve months between its two halves.
    const eStr =
      s.getUTCMonth() === e.getUTCMonth() && sYear === eYear
        ? String(e.getUTCDate())
        : `${months[e.getUTCMonth()]} ${e.getUTCDate()}`;
    if (inSeason) return `${sStr}–${eStr}`;
    if (sYear === eYear) return `${sStr}–${eStr}, ${sYear}`;
    // A window that crosses New Year's needs both years or one of them is a lie.
    return `${sStr}, ${sYear}–${eStr}, ${eYear}`;
  } catch {
    return "";
  }
}
