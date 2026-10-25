"use client";

import Link from "next/link";
import type { RelatedEvent, RelatedEventLinkedTeam } from "@/lib/types";
import { formatProbabilityPercent } from "@/lib/probabilityDisplay";
import {
  SUSPENDED_DESCRIPTION,
  SUSPENDED_LABEL,
  hasNoReportedResult,
  isFinishedStatus,
  scoresShowPlay,
} from "@/lib/eventState";

/**
 * #7416 — THE ROW DELETED ITS OWN FIXTURE AT PHONE WIDTH.
 *
 * Measured on production 2026-09-20, `https://bainluck.com/futures/129037`
 * ("Pro Football: 2027 Champion") at 390px: every "Games This Week" row rendered
 * as a time, two team names and two percentages, with the second percentage
 * clipped off the right edge of the card. The fixture text — the row's subject
 * and the thing its link goes to — was gone entirely. What a reader was left
 * with was `Atlanta Falcons 0%   Carolina Panthers 0%`: a game one of them must
 * win, with both sides at zero.
 *
 * Three separate things made that sentence, and all three are repaired here.
 *
 * 1. LAYOUT. The fixture was `flex-1 min-w-0` beside an odds block that was
 *    `flex-shrink-0` holding two `max-w-[10rem]` names. A block that cannot
 *    shrink takes its full width first, so inside a 390px viewport the
 *    `flex-1` half was squeezed to nothing and truncated away — while the
 *    unshrinkable half still overflowed the card. Below `sm` the two halves now
 *    STACK, so the fixture always has the row's full content width; the odds
 *    block can shrink at every width and its names ellipsize instead of
 *    clipping. The stacked pair fits the height the row already had, because
 *    the `w-16` time gutter was already wrapping to two lines at that width.
 *
 * 2. THE NUMBERS WERE FALSE, not merely misplaced. They were `Math.round(p *
 *    100)`, which is the exact defect UX-P046 exists to refuse: 9 of this
 *    page's 32 rows print `0%` over a probability the market is actively
 *    pricing above zero (Atlanta 0.0035, Carolina 0.0045). Routed onto
 *    `formatProbabilityPercent`, so they read `<1%` and an exact zero still
 *    reads `0%`.
 *
 * 3. ORDER. `linked_teams` arrives `[home, away]`, the reverse of the "Away at
 *    Home" convention the fixture line beside it uses, so the two halves of one
 *    row named the same two teams in opposite orders. `fixtureOrderedTeams`
 *    puts the odds in the fixture's order.
 *
 * What these percentages ARE is this futures market's own per-team odds
 * (`FuturesOutcome.current_probability`, `backend/app/routes/futures.py`
 * :3714-3722), not a price on the game — which is why the section caption names
 * them. Read as a match price, `Houston Texans 4% Cincinnati Bengals 4%` sums
 * to 8%.
 */

/** `away` first, to match the "Away at Home" fixture line. */
const SIDE_RANK: Record<string, number> = { away: 0, home: 1 };

/**
 * The odds in the fixture's own order.
 *
 * A side this map does not know sorts last and keeps its payload order — `sort`
 * is stable, so an unrecognised pair is left exactly as served rather than
 * being reordered on a rank they tie on.
 */
export function fixtureOrderedTeams(
  teams: RelatedEventLinkedTeam[],
): RelatedEventLinkedTeam[] {
  return [...teams].sort(
    (a, b) => (SIDE_RANK[a.side] ?? 2) - (SIDE_RANK[b.side] ?? 2),
  );
}

/**
 * #11182 — A ROW ONLY DRAWS A SCORE ITS STATE CAN STAND BEHIND.
 *
 * Production 2026-10-17 13:44Z, `/futures/199045` (AL Champion) at 390px:
 * `Fri 5:00 PM · Tampa Bay Rays 0 - 0 Cleveland Guardians`, under "Today" and
 * "Tomorrow" rows for the same two teams. Row 15330795 is `suspended` with
 * both scores `0` and no `status_detail`. The row knew three states (live,
 * completed, closed); everything else got a start time, and any two non-null
 * scores got drawn. Together that reads as a game played on Friday that ended
 * 0-0.
 *
 * - Live or finished: the pair is drawn as served. A live or final 0-0 is a
 *   real score.
 * - No reported result (`hasNoReportedResult`: `suspended`, or `scheduled` well
 *   past its own start): the badge is the shared `SUSPENDED_LABEL`, never a
 *   start time. The pair is drawn only when `scoresShowPlay` (#8960's
 *   scores-only play evidence), so a suspended 2-1 keeps its last score
 *   beside the badge, and a 0-0 placeholder is not taken as proof of play.
 *   No winner is bolded, because nothing reported an end.
 * - Anything else (scheduled, or a status this row has no reading for): no
 *   score. A pre-game pair is filler, not a result.
 *
 * Not "Suspended" and not "Postponed": the row has no `status_detail`, and
 * `SUSPENDED_LABEL`'s own note says why the bare word would invent a stoppage
 * nobody reported. Which neighbouring fixture (if any) replaces this one is
 * the server's question (#11182's Live half), not this row's.
 */
export function rowScoreIsShown(
  event: Pick<RelatedEvent, "status" | "home_score" | "away_score">,
  noReportedResult: boolean,
): boolean {
  if (event.home_score === null || event.away_score === null) return false;
  if (event.status === "live" || isFinishedStatus(event.status)) return true;
  if (noReportedResult) return scoresShowPlay(event.away_score, event.home_score);
  return false;
}

/**
 * Compact row for a related event on the futures detail page
 */
export function RelatedEventRow({
  event,
  showOdds = true,
  now = Date.now(),
}: {
  event: RelatedEvent;
  showOdds?: boolean;
  /** Injected so tests can pin the clock (gotcha #44). */
  now?: number;
}) {
  const isLive = event.status === "live";
  const isFinished = isFinishedStatus(event.status);
  const noReportedResult = hasNoReportedResult(event.status, event.commence_time, now);
  const hasScore = rowScoreIsShown(event, noReportedResult);

  // Format time
  let timeLabel = "";
  if (isLive) {
    timeLabel = "Live";
  } else if (isFinished) {
    timeLabel = "Final";
  } else if (noReportedResult) {
    timeLabel = SUSPENDED_LABEL;
  } else {
    const d = new Date(event.commence_time);
    const nowDate = new Date(now);
    const isToday = d.toDateString() === nowDate.toDateString();
    const tomorrow = new Date(nowDate);
    tomorrow.setDate(tomorrow.getDate() + 1);
    const isTomorrow = d.toDateString() === tomorrow.toDateString();
    const timeStr = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    if (isToday) {
      timeLabel = `Today ${timeStr}`;
    } else if (isTomorrow) {
      timeLabel = `Tomorrow ${timeStr}`;
    } else {
      timeLabel = d.toLocaleDateString([], { weekday: "short" }) + ` ${timeStr}`;
    }
  }

  const oddsTeams = showOdds ? fixtureOrderedTeams(event.linked_teams) : [];

  return (
    <Link
      href={`/events/${event.event_id}`}
      className="flex flex-col gap-1 sm:flex-row sm:items-center sm:gap-3 p-3 rounded-lg bg-charcoal/5 hover:bg-charcoal/10 transition-colors"
    >
      {/* Status indicator */}
      <div className="sm:w-16 sm:flex-shrink-0">
        {isLive ? (
          <span className="flex items-center gap-1 text-xs font-semibold text-accent-live">
            <span className="w-1.5 h-1.5 rounded-full bg-accent-live animate-pulse" />
            LIVE
          </span>
        ) : isFinished ? (
          <span className="text-xs font-semibold text-text-muted">FINAL</span>
        ) : noReportedResult ? (
          <span className="text-xs font-semibold text-text-muted" title={SUSPENDED_DESCRIPTION}>
            {timeLabel}
          </span>
        ) : (
          <span className="text-xs text-text-secondary">{timeLabel}</span>
        )}
      </div>

      {/* #7416: stacked below `sm` so the fixture keeps the full content width. */}
      <div className="min-w-0 sm:flex-1 flex flex-col gap-0.5 sm:flex-row sm:items-center sm:gap-3">
        {/* Teams + score */}
        <div className="min-w-0 sm:flex-1">
          <div className="text-sm text-text-primary truncate">
            {hasScore ? (
              <span>
                <span className={isFinished && event.away_score! > event.home_score! ? "font-semibold" : ""}>
                  {event.away_team}
                </span>
                <span className="font-mono text-text-muted mx-1">
                  {event.away_score} - {event.home_score}
                </span>
                <span className={isFinished && event.home_score! > event.away_score! ? "font-semibold" : ""}>
                  {event.home_team}
                </span>
              </span>
            ) : (
              <span>
                {event.away_team}
                <span className="text-text-muted mx-1.5">at</span>
                {event.home_team}
              </span>
            )}
          </div>
        </div>

        {/* Linked team odds from this market */}
        {oddsTeams.length > 0 && (
          <div className="flex items-center gap-3 min-w-0 sm:flex-shrink-0">
            {oddsTeams.map((lt) => (
              <span
                key={lt.team_name}
                className="flex items-baseline gap-1 min-w-0 text-xs text-text-secondary"
              >
                {/* #2553: this was `lt.team_name.split(" ").pop()` — the last word,
                    on the theory that the last word of a team name is its nickname.
                    It is for "Cincinnati Reds"; it is not for the half of world
                    sport that puts the club type at the END. The same strip printed
                    three favourites as "FC", "City" and "FC" (San Diego FC,
                    Sporting Kansas City, Minnesota United FC), which is not a
                    shortened name, it is no name at all.
                    The whole name, truncated by the box if it has to be: a clipped
                    "Philadelphia Phi…" still says who, and "FC" never did. */}
                <span className="font-medium text-text-primary truncate min-w-0 sm:max-w-[10rem]">
                  {oddsLabel(lt)}
                </span>
                {lt.probability !== null && (
                  <span className="font-mono text-text-muted flex-shrink-0">
                    {formatProbabilityPercent(lt.probability)}
                  </span>
                )}
              </span>
            ))}
          </div>
        )}
      </div>
    </Link>
  );
}

/**
 * #8627 — A FIELD OF PLAYERS HAS NO TEAM PRICE.
 *
 * Production, `/futures/209` (NL MVP): the hero read 100% for Pete
 * Crow-Armstrong while this strip printed "Chicago Cubs 1%" under "Each team's
 * odds" — one arbitrary Cub's price (Nico Hoerner, 0.01) wearing the team's
 * name. The route now serves each team's leading outcome and marks a player
 * field `outcome_is_team: false`; such a row names the player whose price it
 * is. An absent flag (a team field, or an older payload) keeps the team name.
 */
export function oddsLabel(lt: RelatedEventLinkedTeam): string {
  return lt.outcome_is_team === false ? lt.outcome_name : lt.team_name;
}

/** The caption's one claim about every number in the section. */
export function oddsCaption(events: RelatedEvent[]): string {
  const playerField = events.some((e) =>
    e.linked_teams.some((lt) => lt.outcome_is_team === false),
  );
  return playerField
    ? "Each team's leading player in this market."
    : "Each team's odds in this market.";
}

/**
 * The "Games This Week" section of the futures detail page.
 *
 * The caption is here rather than on each row because it is one claim about
 * every number in the section: they are this market's odds, not the game's.
 *
 * #8282 — A SETTLED MARKET HAS NO "THIS WEEK". Every per-team number on a
 * resolved board is a verdict (0% or >99%), not a chance, and printed beside a
 * game that has not been played it reads as that team's odds tomorrow.
 * Production, `/futures/114108` — *Kings vs. Blue Jackets*, a single game that
 * settled in March — listed "Tomorrow · Pittsburgh Penguins at Columbus Blue
 * Jackets · Columbus Blue Jackets >99%". So on a resolved market the section
 * is withheld, silently (notice 34): no heading, no explanation, no hole.
 *
 * #2553 — A DUEL'S PRICE IS ONE CONTEST'S PRICE, NOT A TEAM'S ODDS THIS WEEK.
 * Production 2026-10-02 ~01:40Z, `/futures/61226191` — *Sabres vs. Canadiens*,
 * `market_type: "duel"` — listed four Sabres games, each printed "Buffalo Sabres
 * 42%": beside the live Sabres at Blue Jackets game, and beside three more
 * against Chicago, Minnesota and Dallas. 42% is the Sabres' price to beat
 * Montreal. `/futures/63481323` (*1H Spread: Saints (-5.5)*) printed "New
 * Orleans Saints 34%" beside Falcons at Saints, a first-half spread price read
 * as a chance of winning. A field's per-team number is a title price and the
 * caption says so; a duel's two numbers belong to its one contest, so beside
 * any fixture they are a different game's price. On a duel the rows keep their
 * fixtures and links and print no number, and with no number there is no
 * caption to make a claim about one.
 */
export default function GamesThisWeek({
  events,
  marketResolved = false,
  marketIsDuel = false,
}: {
  events: RelatedEvent[];
  marketResolved?: boolean;
  marketIsDuel?: boolean;
}) {
  if (marketResolved || events.length === 0) return null;
  const showOdds = !marketIsDuel;

  return (
    <div className="bg-surface-card rounded-card shadow-card p-6">
      <h2
        className={`text-title-3 font-semibold text-text-primary flex items-center gap-2 ${showOdds ? "mb-1" : "mb-4"}`}
      >
        <span>📅</span>
        Games This Week
      </h2>
      {showOdds && (
        <p className="text-sm text-text-secondary mb-4">
          {oddsCaption(events)}
        </p>
      )}
      <div className="space-y-2">
        {events.map((event) => (
          <RelatedEventRow key={event.event_id} event={event} showOdds={showOdds} />
        ))}
      </div>
    </div>
  );
}
