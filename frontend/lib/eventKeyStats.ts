/**
 * Extracted helpers for the event detail page (events/[id]/page.tsx).
 *
 * Pure functions and constants that were previously inlined in the
 * EventPage component.  Keeping them here makes the page component a
 * thin orchestrator and each helper independently testable.
 */

import { format as fmtDate } from "date-fns";
import type {
  EventHistoryResponse,
  EventDetailResponse,
  ActiveChartPoint,
  CurrentOdds,
  ScoringPlay,
} from "@/lib/types";
import {
  categoryLabelFormat,
  CATEGORY_LABEL_FORMAT,
} from "@/lib/chartTimeline";
import {
  hasProbabilitySourceReading,
  readProbabilitySourceValues,
  shouldWithholdProbability,
} from "@/lib/probabilityEvidence";
import type { WinProbabilitySources } from "@/lib/probabilityEvidence";
import { PROBABILITY_SOURCE_KEYS } from "@/lib/confidence";
import { renderedDuelPercents, renderedPercent } from "@/lib/renderedPercent";
import { formatProbabilityPercent } from "@/lib/probabilityDisplay";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Maps Odds API sport keys to sport hierarchy paths */
export const SPORT_KEY_TO_LEAGUE_PATH: Record<
  string,
  { path: string; label: string }
> = {
  basketball_nba: { path: "/sport/basketball/nba", label: "NBA" },
  americanfootball_nfl: { path: "/sport/football/nfl", label: "NFL" },
  baseball_mlb: { path: "/sport/baseball/mlb", label: "MLB" },
  icehockey_nhl: { path: "/sport/hockey/nhl", label: "NHL" },
  basketball_ncaab: {
    path: "/sport/basketball/ncaab",
    label: "NCAA Basketball",
  },
  americanfootball_ncaaf: {
    path: "/sport/football/ncaaf",
    label: "NCAA Football",
  },
  basketball_wnba: { path: "/sport/basketball/wnba", label: "WNBA" },
  soccer_usa_mls: { path: "/sport/soccer/mls", label: "MLS" },
  soccer_epl: { path: "/sport/soccer/epl", label: "EPL" },
  soccer_spain_la_liga: { path: "/sport/soccer/laliga", label: "La Liga" },
  soccer_uefa_champs_league: {
    path: "/sport/soccer/ucl",
    label: "Champions League",
  },
  soccer_germany_bundesliga: {
    path: "/sport/soccer/bundesliga",
    label: "Bundesliga",
  },
  basketball_wncaab: {
    path: "/sport/basketball/wncaab",
    label: "NCAA Basketball",
  },
};

/** Human-readable labels for event tags (namespace:value → display) */
export const TAG_LABELS: Record<string, string> = {
  "importance:championship": "Championship",
  "importance:playoff": "Playoff",
  "importance:exhibition": "Exhibition",
  "signal:close_matchup": "Close Game",
  "signal:upset": "Upset",
  "signal:line_moving": "Line Moving",
  "signal:blowout": "Blowout",
  "timing:primetime": "Primetime",
  "timing:national_tv": "National TV",
  "timing:weekend": "Weekend",
  "tier:1": "Major",
  "tier:2": "Tier 2",
  "ei:must_watch": "Must-Watch",
  "ei:incredible": "Incredible",
  "ei:exciting": "Exciting",
  "stakes:elimination": "Elimination",
  "stakes:clinch": "Clinch Scenario",
  "stakes:playoff_race": "Playoff Race",
  "stakes:title_defense": "Title Defense",
  "stakes:must_win": "Must-Win",
  "stakes:record_chase": "Record Chase",
  "stakes:seeding": "Seeding",
  "stakes:streak": "Streak",
  "narrative:rivalry": "Rivalry",
  "narrative:historic_rivalry": "Historic Rivalry",
  "narrative:revenge_game": "Revenge Game",
  "narrative:cinderella": "Cinderella",
  "narrative:upset_alert": "Upset Alert",
  "narrative:comeback": "Comeback",
  "narrative:rematch": "Rematch",
  "narrative:david_vs_goliath": "David vs. Goliath",
  "narrative:farewell_tour": "Farewell Tour",
  "narrative:winning_streak": "Winning Streak",
  "narrative:losing_streak": "Losing Streak",
  "narrative:debut": "Debut",
  "narrative:return_from_injury": "Return from Injury",
  "audience:national_interest": "National Interest",
  "audience:crossover_appeal": "Crossover Appeal",
  "audience:viral_potential": "Viral Potential",
  "audience:casual_friendly": "Casual-Friendly",
  "competitive_structure:knockout": "Knockout",
  "competitive_structure:single_elimination": "Single Elimination",
  "competitive_structure:bracket": "Bracket",
  "competitive_structure:series": "Series",
  "competitive_structure:best_of_7": "Best of 7",
  "competitive_structure:group_stage": "Group Stage",
};

/** CSS classes per tag namespace */
export const TAG_COLORS: Record<string, string> = {
  importance: "bg-purple-50 text-purple-600",
  signal: "bg-orange-50 text-orange-600",
  timing: "bg-yellow-50 text-yellow-700",
  tier: "bg-blue-50 text-blue-600",
  ei: "bg-emerald-50 text-emerald-600",
  stakes: "bg-red-50 text-red-600",
  narrative: "bg-amber-50 text-amber-600",
  audience: "bg-cyan-50 text-cyan-600",
  competitive_structure: "bg-indigo-50 text-indigo-600",
};

/** Tag namespace allowlist for the hero section */
const DISPLAY_TAG_NAMESPACES = new Set([
  "importance",
  "signal",
  "timing",
  "tier",
  "ei",
  "stakes",
  "narrative",
  "audience",
  "competitive_structure",
]);

/** Tags suppressed from display even when their namespace qualifies */
const SUPPRESSED_TAGS = new Set([
  "competitive_structure:head_to_head",
  "audience:local_interest",
  "stakes:meaningless",
]);

// ---------------------------------------------------------------------------
// Pure helpers
// ---------------------------------------------------------------------------

/** Pick key season stats to display based on sport */
export function getKeyStats(
  stats: Record<string, number | string> | null | undefined,
  sportKey: string | undefined,
): Array<{ label: string; value: string | number }> {
  if (!stats) return [];
  const result: Array<{ label: string; value: string | number }> = [];
  const s = sportKey?.toLowerCase() || "";

  if (s.includes("basketball")) {
    if (stats.ppg != null) result.push({ label: "PPG", value: stats.ppg });
    if (stats.rpg != null) result.push({ label: "RPG", value: stats.rpg });
    if (stats.apg != null) result.push({ label: "APG", value: stats.apg });
    if (stats.opp_ppg != null)
      result.push({ label: "Opp PPG", value: stats.opp_ppg });
  } else if (s.includes("football")) {
    if (stats.points_per_game != null)
      result.push({ label: "PTS/G", value: stats.points_per_game });
    if (stats.yards_per_game != null)
      result.push({ label: "YDS/G", value: stats.yards_per_game });
    if (stats.opp_points_per_game != null)
      result.push({ label: "Opp PTS/G", value: stats.opp_points_per_game });
  } else if (s.includes("baseball")) {
    if (stats.batting_avg != null)
      result.push({ label: "AVG", value: stats.batting_avg });
    if (stats.era != null) result.push({ label: "ERA", value: stats.era });
    if (stats.runs_per_game != null)
      result.push({ label: "R/G", value: stats.runs_per_game });
  } else if (s.includes("hockey")) {
    if (stats.goals_for_per_game != null)
      result.push({ label: "GF/G", value: stats.goals_for_per_game });
    if (stats.goals_against_per_game != null)
      result.push({ label: "GA/G", value: stats.goals_against_per_game });
    if (stats.power_play_pct != null)
      result.push({ label: "PP%", value: stats.power_play_pct });
  } else if (s.includes("soccer")) {
    if (stats.goals_per_game != null)
      result.push({ label: "G/G", value: stats.goals_per_game });
    if (stats.clean_sheets != null)
      result.push({ label: "CS", value: stats.clean_sheets });
    if (stats.goals_against_per_game != null)
      result.push({ label: "GA/G", value: stats.goals_against_per_game });
  } else {
    // Generic: show first 3 numeric stats
    for (const [key, val] of Object.entries(stats)) {
      if (result.length >= 3) break;
      if (
        typeof val === "number" ||
        (typeof val === "string" && !isNaN(Number(val)))
      ) {
        result.push({
          label: key
            .replace(/_/g, " ")
            .replace(/\b\w/g, (c) => c.toUpperCase()),
          value: val,
        });
      }
    }
  }
  return result.slice(0, 4);
}

/** Check if history response has ANY win probability data beyond sportsbook odds. */
export function hasAnyWinProbData(data: EventHistoryResponse | null | undefined): boolean {
  if (!data) return false;
  if (data.espn_history && data.espn_history.length > 0) return true;
  if (data.win_prob_history) {
    for (const points of Object.values(data.win_prob_history)) {
      if (Array.isArray(points) && points.length > 0) return true;
    }
  }
  return false;
}

/** Format a future timestamp as a human-readable countdown (e.g. "2d 5h"). */
export function formatCountdown(targetTime: string): string {
  const target = new Date(targetTime);
  const now = new Date();
  const diff = target.getTime() - now.getTime();

  if (diff <= 0) return "";

  const days = Math.floor(diff / (1000 * 60 * 60 * 24));
  const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
  const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));

  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

/**
 * How close to its start an event has to be before the header's poll countdown
 * is worth showing. Reuses the window `sportCategories.ts` already ships as
 * "starting soon" (`hoursUntil <= 3`) rather than inventing a second one, so
 * the two surfaces cannot drift into disagreeing about what "soon" means.
 */
export const REFRESH_COUNTDOWN_WINDOW_MS = 3 * 60 * 60 * 1000;

/**
 * How long PAST its own kickoff an event with no reported result can still
 * promise an update. (#6381, from live/266's reading)
 *
 * ── WHY THE OTHER END OF THE WINDOW WAS MISSING ──
 *
 * `REFRESH_COUNTDOWN_WINDOW_MS` above bounds the ring BEFORE a match. Nothing
 * bounded it after: `isSuspended` is
 * `hasNoReportedResult(status, commence_time)`, whose `startedWithoutResult`
 * disjunct fires from {@link UPCOMING_GRACE_MS} past kickoff *onwards, forever*,
 * and whose `isSuspendedStatus` disjunct reads the literal status with no clock
 * at all. So `/events/15310639` (Liverpool–Fulham, 3.6 days past kickoff) and
 * `/events/15304840` (Sabalenka, 9.6 days) each ran a live `Next update: 105`
 * dial — a true sentence about our poll and a false one about the match, which
 * is the same lie #3802 removed from the pregame end.
 *
 * ── WHERE 12 HOURS COMES FROM ──
 *
 * The longest a match on this site can plausibly still be running is the
 * largest entry in the backend's own `SPORT_MAX_DURATIONS`
 * (`app/tasks/config.py`) — golf, 8 hours — and a result can lag the final
 * whistle by a few more. 12h is that maximum plus a deliberate reporting
 * margin, so no in-progress event loses its ring, and every row in #6381's
 * 426-event census (all ≥6h past kickoff, most days past it) is well outside.
 * `__tests__/lib/countdownReachClearsTheLongestSport6381.test.ts` reads the
 * Python and fails if a sport is ever given a maximum this does not clear,
 * because a comment asking two languages to stay in step is not a mechanism
 * (the #3211 guard's rule).
 *
 * 🔴 THIS DOES NOT BOUND A `live` EVENT, deliberately. A cricket Test or a golf
 * round genuinely delivers updates for days, and a stale LIVE claim is already
 * withdrawn one branch above by #5459's `liveClaimUnbacked`. The defect is a
 * page with NO result promising one, not a long event.
 */
export const REFRESH_COUNTDOWN_MAX_AGE_MS = 12 * 60 * 60 * 1000;

/**
 * Is this event recent enough that a poll could still bring its result? (#6381)
 *
 * Only ever narrows: a start time we cannot read is not a licence to promise an
 * update (the same call this function's caller makes three branches below), and
 * a start still ahead of us is left alone — a row can call itself `suspended`
 * before its own kickoff, and that is the pregame case, not this one.
 */
function startedWithinCountdownReach(
  commenceTime: string | null | undefined,
  now?: Date,
): boolean {
  if (!commenceTime) return false;
  const startMs = new Date(commenceTime).getTime();
  if (isNaN(startMs)) return false;
  return (now ?? new Date()).getTime() - startMs <= REFRESH_COUNTDOWN_MAX_AGE_MS;
}

/**
 * Should the event header draw its "Next update: NN" ring? (#3802, #6381)
 *
 * The ring counts down the page's own poll, and the page polls every two
 * minutes whether the match is in ten minutes or in three days. Gated only on
 * `!isFinished && !streamConnected`, it therefore promised "next update in 109
 * seconds" over a US Open quarter-final **34 hours away** — a true sentence
 * about our poll that reads as a false one about the match, on the page a
 * reader opens precisely to find out when something will happen. It is also
 * the third element in a `justify-between` row that only has space for two at
 * 390px, so the same countdown wrapped the header into three ragged lines.
 *
 * A countdown earns its place when an update could plausibly land while the
 * reader is looking: the event is live, it is past its start with no reported
 * result *and still within {@link REFRESH_COUNTDOWN_MAX_AGE_MS} of it* (#6381),
 * or it starts within the window above — and in no case once the VENUE HAS
 * GRADED the match (#6381's second half; see the `venueSettled` argument). A pregame match days out is told when
 * it starts by the hero ("Starts in 1d 10h") — the poll clock adds nothing
 * there and costs the header its layout; a fixture days PAST its kickoff with
 * no result is the same sentence told backwards, and #6381 photographed it on
 * a 3.6-day-old EPL fixture whose own markets were graded one screen below.
 *
 * Pure and exported because a Next.js page may not carry named exports, so
 * this is the only seam a guard can hold.
 */
export function shouldShowRefreshCountdown(args: {
  isFinished: boolean;
  streamConnected: boolean;
  isLive: boolean;
  isSuspended: boolean;
  commenceTime: string | null | undefined;
  /**
   * #5459 — the page's LIVE claim has been withdrawn (`liveClaimIsUnbacked`).
   *
   * Optional, and absent means "not withdrawn": every existing caller and every
   * case below is unchanged by this argument, which is what keeps #3802's own
   * table honest about what it is still measuring.
   */
  liveClaimUnbacked?: boolean;
  /**
   * #6381 (second half) — THE VENUE HAS GRADED THIS MATCH.
   *
   * `venue_settled` / `venue_settled_result` are on the payload today, and since
   * #6739 the hero prints the winner's name off them — so `/events/15313807`
   * read **"Next update: 108"** in the header and **"Settled · Crawley wins"**
   * two lines below, at 390px, one page and two answers (live/354, production
   * 2026-09-17 18:13Z). **777 of the 1,121** graded `suspended` rows now carry a
   * winner sentence, and every one inside countdown reach drew this ring.
   *
   * Neither existing guard can see it, by construction: `isFinished` is false
   * because the row is `suspended` rather than `completed`, and
   * `liveClaimUnbacked` measures how old OUR NUMBER is — the blend on these rows
   * is fresh, because their markets are still being polled.
   *
   * Optional, and absent means "not graded", so every existing caller and every
   * case below is unchanged by this argument (the shape `liveClaimUnbacked`
   * established for the same reason).
   */
  venueSettled?: boolean;
  now?: Date;
}): boolean {
  const { isFinished, streamConnected, isLive, isSuspended, commenceTime } = args;

  // Unchanged: a finished event has nothing to refresh, and a pushed event
  // shows its age stamp instead (live/034 S2).
  if (isFinished || streamConnected) return false;

  // #6381 — BESIDE the finished arm, and deliberately not inside the
  // `isSuspended` branch below. A venue-graded match has nothing to refresh for
  // the same reason a Final does not: it is a STATE, and the bound below is a
  // CLOCK. Written as a clock rule it would read as "the ring expires" on a row
  // where the answer is already known, and it would keep promising an update on
  // a match graded inside the window — which is every one of them for the first
  // hours after the whistle.
  if (args.venueSettled) return false;

  // #5459 — and BEFORE the two cases below, deliberately. This ring's whole
  // promise is that the next tick brings a new number; on a page whose number
  // has not moved in hours, the polls keep landing and keep writing the same
  // value, so the promise is true about our poll and false about the match.
  // Placed above `isLive || isSuspended` because those are precisely the two
  // states an unbacked page is in — checked after them it would never fire.
  if (args.liveClaimUnbacked) return false;

  // An event that is live is exactly the case the ring was written for, and it
  // keeps it however long it runs (see REFRESH_COUNTDOWN_MAX_AGE_MS).
  if (isLive) return true;

  // #6381 — past its start with no result reported is the OTHER case the ring
  // was written for, but only while an update could still plausibly land. Read
  // the bound rather than returning `true`: on a fixture days past its kickoff
  // the dial promises something that is never coming, and this population is
  // precisely the one #5459's `liveClaimUnbacked` guard cannot reach — that
  // one measures how old OUR NUMBER is, and a dead fixture whose markets are
  // still being polled has a perfectly fresh blend.
  //
  // 🔴 Bounded HERE and not inside `hasNoReportedResult`, which answers a
  // different question — "print a start time or print *No result reported*?" —
  // and whose answer stays right forever. #3211 rescued 171 US Open matches
  // onto the league rails with that predicate; teaching it a clock un-rescues
  // them into the both-rails hole. Only the ring needs to stop promising.
  if (isSuspended) return startedWithinCountdownReach(commenceTime, args.now);

  // No start time is not a licence to promise an update — an event we cannot
  // place in time is the last one that should carry a confident clock.
  if (!commenceTime) return false;

  const startMs = new Date(commenceTime).getTime();
  if (isNaN(startMs)) return false;

  const nowMs = (args.now ?? new Date()).getTime();
  return startMs - nowMs <= REFRESH_COUNTDOWN_WINDOW_MS;
}

/**
 * Does the header say HOW OLD its number is? (#5039 / #5049 — ship 5, "honest
 * about its age")
 *
 * ═══ THE DEFECT ═══
 *
 * The age badge was written for the PUSHED path and given to it alone: on a
 * polled page the header showed `LIVE` and a `Next update: 27` ring instead.
 * Shopped on SF@LAR (2026-09-10, notice 42) that swap is visible on one page
 * that was never reloaded — `live · 4s ago` at 6:56pm, and at halftime, with
 * the same tab open, `LIVE   Next update: (27)`.
 *
 * It is the wrong way round twice over. A countdown answers *"when will we next
 * try?"* — our plumbing, which a reader cannot act on (notice 34 / D102). The
 * age answers *"how old is this number?"*, which is the reader's question, and
 * it is worth most exactly where it was withheld: during a twelve-minute
 * halftime nothing else on the page moves, so the age is the only thing that
 * can distinguish a working page from a frozen one.
 *
 * ═══ WHY IT IS NOT SIMPLY "ALWAYS SHOW IT" ═══
 *
 * The badge's fresh presentation says the word *live* (`live · 8s ago`). The
 * ring, since #3802, also draws on a PREGAME page up to three hours out, where
 * the price stamp is seconds old and a green `live · 8s ago` would be a true
 * sentence about our write and a false one about the match. So the polled arm
 * is gated on the same liveness the pill it replaces was gated on, not on the
 * ring's own window.
 *
 * `feedStalled` stays as its own arm rather than folding into the two above:
 * #4861 earned the badge for a page that has stopped being fed whatever its
 * state, including that pregame case, and there the age is by construction past
 * its stale boundary, so it prints a grey `4m ago` and claims nothing.
 *
 * ═══ WHAT THIS RETIRES ═══
 *
 * The header's `LIVE` pill rendered only inside the ring group and only when
 * `effectivelyLive` — and every one of those inputs returns true here, so the
 * badge is present wherever the pill was. Two green live claims side by side is
 * two answers to one question, and the pill was the worse of the two: it was
 * keyed on the event's STATUS, so it stayed green and pulsing over a number of
 * any age (#5049), while this badge drops the green and the word "live" as soon
 * as its own fact goes stale. `headerAgeSubsumesLivePill` below is that
 * argument as an assertion, so nobody has to take it on trust.
 *
 * Pure and exported for the same reason `shouldShowRefreshCountdown` is: a
 * Next.js page may not carry named exports, so this is the only seam a guard
 * can hold.
 */
export function headerShowsAge(args: {
  isFinished: boolean;
  /** The SSE stream is delivering — the original, pushed case. */
  streamConnected: boolean;
  /** `shouldShowRefreshCountdown` WITHOUT the #5459 withdrawal. */
  onVisiblePoll: boolean;
  /** #4861 — the page's own fetches have stopped landing. */
  feedStalled: boolean;
  /** The page's one motion answer: `isLive && !liveClaimUnbacked`. */
  effectivelyLive: boolean;
  /** `hasNoReportedResult(...) || liveClaimUnbacked`. */
  isSuspended: boolean;
}): boolean {
  const {
    isFinished,
    streamConnected,
    onVisiblePoll,
    feedStalled,
    effectivelyLive,
    isSuspended,
  } = args;

  // A finished page has no age to disclose — it has a result (settled means
  // settled), and this badge is about a number that is still supposed to move.
  if (isFinished) return false;

  if (streamConnected) return true;
  if (!onVisiblePoll) return false;

  return effectivelyLive || isSuspended || feedStalled;
}

/**
 * The pill's retirement, stated as a predicate so a test can hold it (#5039).
 *
 * True when the header's old `LIVE` pill WOULD have drawn — the ring group is
 * on screen and the page is effectively live — and the age badge is not there
 * to carry the claim instead. It must be false for every reachable input, which
 * is what makes deleting the pill a reduction rather than a loss: wherever it
 * spoke, `live · Ns ago` now speaks, and says one true thing more.
 */
export function headerAgeSubsumesLivePill(args: {
  isFinished: boolean;
  streamConnected: boolean;
  onVisiblePoll: boolean;
  feedStalled: boolean;
  effectivelyLive: boolean;
  isSuspended: boolean;
  /** `showRefreshCountdown && !feedStalled` — the ring group is rendered. */
  ringVisible: boolean;
}): boolean {
  return args.ringVisible && args.effectivelyLive && !headerShowsAge(args);
}

/**
 * Does the authority actually KNOW when this event starts? (#3829)
 *
 * ═══ THE DEFECT ═══
 *
 * ESPN files a tennis fixture on the scoreboard the moment its round is drawn
 * and withholds the hour until the courts are assigned, saying which of the two
 * you hold in `start_is_tbd`. On 2026-09-07 all four US Open quarter-finals
 * shared one fabricated `2026-09-08T15:30:00Z`, and `/events/{id}` printed
 * "Sep 8, 2026 · 11:30 AM EDT" and counted down to it — while the hub row for
 * the same match, which has honoured the flag since Q463, said "TOMORROW · TBD".
 * Four matches cannot start at 11:30 on two courts.
 *
 * ═══ THREE STATES, BECAUSE TWO IS WHAT CAUSED IT ═══
 *
 * `"tbd"`     — the authority listed the fixture and said there is no time yet.
 * `"pending"` — this is a tournament sport and the answer is still in flight.
 *               We do not yet know, so we say nothing. A clock that renders
 *               confidently and is then yanked is the same lie told briefly,
 *               and "unknown" must never render as "known".
 * `"clock"`   — everything else, and it is deliberately the default. A `null`
 *               flag means the fixture is not on today's order of play, which
 *               is the ordinary state of every FINISHED match — and a finished
 *               match's start time is perfectly well known. Only positive
 *               evidence removes a clock.
 *
 * Pure and exported because a Next.js page may not carry named exports, so this
 * is the only seam a guard can hold — the same reason
 * `shouldShowRefreshCountdown` lives here.
 */
export type StartClockState = "clock" | "tbd" | "pending";

export function startClockState(args: {
  /** `EventTournamentResponse.start_is_tbd` — `undefined` while unresolved. */
  startIsTbd: boolean | null | undefined;
  /** Did this page even ask? False for every non-tournament sport. */
  isTournamentSport: boolean;
  /** Has the `by-event` answer arrived (whatever it said)? */
  tournamentResolved: boolean;
}): StartClockState {
  const { startIsTbd, isTournamentSport, tournamentResolved } = args;
  if (startIsTbd === true) return "tbd";
  // The hold is scoped to sports that actually ask. An MLB page never issues
  // the request, so `tournamentResolved` is permanently false for it and an
  // unscoped hold would blank the clock on the whole site.
  if (isTournamentSport && !tournamentResolved) return "pending";
  return "clock";
}

/**
 * The event header's start line — "Sep 8, 2026 · 11:30 AM EDT" (#3829).
 *
 * THE DAY SURVIVES THE PLACEHOLDER AND THE HOUR DOES NOT. ESPN files a fixture
 * on the day it will be played and withholds only the time, so a reader keeps
 * the fact we hold and loses the one we invented. `"TBD"` is the hub's own word
 * for this state — `TournamentMatches.formatMatchTime` has printed it since
 * Q463 — so the two surfaces now say the same thing about the same match.
 */
export function formatEventStartLabel(
  commenceTime: string,
  state: StartClockState = "clock",
): string {
  const at = new Date(commenceTime);
  if (isNaN(at.getTime())) return "";
  const day = at.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
  if (state === "pending") return day;
  if (state === "tbd") return `${day} · TBD`;
  const clock = at.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  });
  return `${day} · ${clock}`;
}

/** Format a start time as a relative label (Today/Tomorrow) or short date. */
export function formatStartTime(commenceTime: string): string {
  const date = new Date(commenceTime);
  const today = new Date();
  const tomorrow = new Date(today);
  tomorrow.setDate(tomorrow.getDate() + 1);

  const timeStr = date.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
  });

  if (date.toDateString() === today.toDateString()) {
    return `Today at ${timeStr}`;
  } else if (date.toDateString() === tomorrow.toDateString()) {
    return `Tomorrow at ${timeStr}`;
  } else {
    const dateStr = date.toLocaleDateString("en-US", {
      weekday: "short",
      month: "short",
      day: "numeric",
    });
    return `${dateStr} at ${timeStr}`;
  }
}

/** Filter event tags to the displayable subset for the hero section. */
export function filterDisplayTags(
  tags: string[] | undefined,
): string[] | null {
  if (!tags || tags.length === 0) return null;
  const display = tags.filter((t) => {
    const ns = t.split(":")[0];
    return DISPLAY_TAG_NAMESPACES.has(ns);
  });
  const filtered = display.filter((t) => !SUPPRESSED_TAGS.has(t));
  return filtered.length > 0 ? filtered : null;
}

// ---------------------------------------------------------------------------
// Probability resolution
// ---------------------------------------------------------------------------

export interface ResolvedProbability {
  homeProb: number | null;
  awayProb: number | null;
  probSourceLabel: string | null;
  openingHomeProb: number | null;
  openingAwayProb: number | null;
  // #2085 — the WHOLE PERCENTS the hero prints for the pair above, decided
  // together. Every pair this function can return is an exact complement by
  // construction on the backend (`1 - home`, at four separate sites), so
  // rounding the two sides independently prints 101 whenever `home * 100` lands
  // on a half-percent — 34 of 414 scheduled/live events, measured 2026-08-21.
  // It can print 101; it can never print 99.
  //
  // These are the numbers to PRINT. `homeProb`/`awayProb` are unchanged and
  // remain the numbers to reason with — the chart's right edge, the trend
  // delta and `data-probability` all still read them.
  homePct: number | null;
  awayPct: number | null;
  // The same decision for the "Opened away – home" line, which draws
  // `opening_odds` and derives its away side the same way (routes/events.py's
  // `opening_away_probability or round(1 - home, 4)`).
  openingHomePct: number | null;
  openingAwayPct: number | null;
}

/**
 * The most recent valid home-win probability from the backend blend line
 * (aggregate_line — the weighted-median "Bain Luck" line the chart draws).
 * Returns null when there is no usable blend point yet. Walks backwards so a
 * trailing null/undefined doesn't hide a good earlier value.
 */
export function latestBlendPoint(
  aggregateLine: Array<{ timestamp: string; home_probability: number }> | null | undefined,
): number | null {
  if (!aggregateLine || aggregateLine.length === 0) return null;
  for (let i = aggregateLine.length - 1; i >= 0; i--) {
    const p = aggregateLine[i]?.home_probability;
    if (typeof p === "number" && !isNaN(p)) return p;
  }
  return null;
}

/**
 * The ONE conversion between a 0–1 home win-probability — the scale of every
 * payload field (current_odds, opening_odds, history[], win_prob_history,
 * aggregate_line) and every non-chart surface (hero, discover card, readout) —
 * and the chart's internal 0–100 axis.
 *
 * #1003 was a stray `/100` at exactly this boundary: OddsChart multiplies
 * `home_probability` by 100 to plot and to feed its tooltip, then divides the
 * axis value by 100 when it hands a scrubbed point back to the hero/readout.
 * When those two conversions drift (an added/removed `*100` or `/100`) the
 * tooltip and the headline show different numbers for the same game. Routing
 * BOTH directions through these named helpers makes the boundary one tested
 * contract (probabilityInvariant.test.ts) — a regression fails a unit test
 * instead of only surfacing as a live visual mismatch. The arithmetic is
 * unchanged; this is a guard, not a behavior change.
 */
export function homeProbToChartAxis(homeProb: number): number {
  return homeProb * 100;
}

export function chartAxisToHomeProb(axisValue: number): number {
  return axisValue / 100;
}

/**
 * The whole percents a CHART surface prints for one 0–100 axis value (#3892).
 *
 * ═══ WHY THIS IS A FUNCTION AND NOT TWO LINES AT THE CALL SITE ═══
 *
 * `OddsChart` printed whole percents off the axis value directly —
 * `Math.round(homeProb)` in the edge callout, `.toFixed(0)` in the sportsbook
 * tooltip. The axis value is `probability * 100`, and that product is not the
 * decimal the venue quoted: `0.575 * 100` is `57.49999999999999`. So the
 * callout drew **57%** underneath a **58%** hero on `/events/15307463` during
 * the 2026 US Open quarter-finals, for one probability, on one card.
 *
 * The rule for "what whole percent does this probability print" is
 * `renderedPercent`, and the only way a chart can obey it is to come back
 * across this boundary first. Putting that here rather than inline is the same
 * argument `homeProbToChartAxis` was extracted on, one floor up: an expression
 * repeated at two call sites is a rule that can drift at one of them, and
 * `probabilityInvariant.test.ts` was green through this entire bug precisely
 * because it re-implemented the arithmetic instead of calling it.
 *
 * ═══ THE SECOND END IS DERIVED — AND WHICH END IS THE SECOND IS THE RULE ═══
 *
 * Never rounded on its own. On the half-percent grid both ends can land on
 * `.5` at once, so independent rounding prints 101 — the card-level half of the
 * same contract (`renderedCardPercents`). Deriving one end from the other keeps
 * a complement pair summing to 100 by construction.
 *
 * #4154 — GETTING THE SUM RIGHT IS NOT ENOUGH; THE HERO AND THE CHART HAVE TO
 * DERIVE THE *SAME* END. The first version of this function always rounded
 * `home` and derived `away`. The hero does not: `renderedDuelPercents` rounds
 * the LARGER side and derives the smaller, so that the number a card leads with
 * is the one that survives untouched. The two rules agree whenever home is the
 * larger side and disagree whenever it is not — and `0.275` is not a rounding
 * edge case, it is half of every duel on the board.
 *
 * Read on production 2026-09-08 on `/events/15307331` (Zheng v Rybakina, a US
 * Open quarter-final): `hero_probability: 0.275` printed a **27%** hero — 100
 * minus a rounded 73 — above a **28%** callout, because this function rounded
 * `0.275` on its own. One card, one number, two answers, and both arms were
 * individually obeying a contract. #3892 closed the mirror image of this
 * (`0.575`, hero 58 / callout 57) by fixing HOW the chart rounds; it could not
 * see this one, because there the charted side was the side the hero rounds.
 *
 * So the chart does not have a rounding rule of its own any more. It rebuilds
 * the pair the axis value implies and asks `renderedDuelPercents` — the hero's
 * own function — which end to anchor. Agreement is then structural rather than
 * a coincidence re-established at each call site, which is the only form of it
 * that survives the next change to either arm.
 *
 * Returns `null`s for a non-finite axis value, which is `renderedPercent`'s own
 * answer for "no number here". A caller rendering into JSX must supply its own
 * fallback rather than interpolating the null.
 *
 * ═══ #6858 — THE INTEGER IS NOT THE PRINTABLE ANSWER AT THE BOUNDARY ═══
 *
 * #4154 made the hero and the chart round the same end of the same pair, and
 * they have agreed across `[0.01, 0.99]` ever since. They still disagreed at the
 * two ends, because agreeing on the INTEGER is not the same as agreeing on what
 * gets PRINTED: the hero prints through `probabilityParts`, which substitutes a
 * marked form whenever rounding would claim a boundary the probability is
 * strictly inside of — and a `number` cannot carry a marker at all. So this
 * function handed back a faithful `0`, the callout interpolated it, and the
 * chart told the reader a team still playing had exactly no chance.
 *
 * (The two spellings deliberately do not appear here. `probabilityDisplay` is
 * their one home, and `probabilityDisplay.test.ts` fails any second module that
 * writes them down — a guard this comment tripped on its first draft.)
 *
 * Read on production 2026-09-18 03:50Z on `/events/15298678` (Aces at Storm,
 * live, ten minutes left in the fourth, served `home_probability: 0.001`): the
 * hero printed the marked form and the callout printed a bare `0%`, both inside
 * one phone screenful.
 *
 * The labels are returned from HERE rather than formatted at the two call sites
 * for the reason the whole function exists: an expression repeated at two call
 * sites is a rule that can drift at one of them. It also keeps the call count
 * the `#3892` source guard pins at two.
 *
 * 🔴 That rule is STRICT on the probability, so a settled game's genuine `1` /
 * `0` still prints the literal `100%` / `0%`. That is *settled means settled*,
 * it is the wider regression a careless fix here would cause — an edge check on
 * the ROUNDED integer would convert every finished game on the site — and it is
 * pinned by its own case in `chartCalloutHonoursTheBoundaryRule6858`.
 */
export function chartAxisPercents(axisValue: number): {
  home: number | null;
  away: number | null;
  homeLabel: string | null;
  awayLabel: string | null;
} {
  const homeProb = chartAxisToHomeProb(axisValue);
  // The axis carries ONE end, and this function has always answered for both by
  // treating the other as its complement. Making that reconstruction explicit is
  // what lets the hero's rule decide the anchor; a non-finite axis value falls
  // out as a non-complement pair and yields the nulls documented above.
  const [away, home] = renderedDuelPercents(1 - homeProb, homeProb);
  if (home === null || away === null) {
    return { home: null, away: null, homeLabel: null, awayLabel: null };
  }
  // The DERIVED integer is passed as `rendered` so the boundary rule is applied
  // on top of the pair this function already resolved — never re-rounded from
  // the probability, which would reintroduce the 101 that deriving prevents.
  return {
    home,
    away,
    homeLabel: formatProbabilityPercent(homeProb, { rendered: home }),
    awayLabel: formatProbabilityPercent(1 - homeProb, { rendered: away }),
  };
}

/**
 * #2085 — fold the printed percents onto a resolved pair, at the ONE place that
 * knows which source the pair actually came from.
 *
 * 🔴 THE SERVED PERCENTS DESCRIBE `current_odds` AND NOTHING ELSE, AND ON THIS
 * PAGE THAT IS USUALLY NOT THE PAIR ON SCREEN. `FeedCard` may read
 * `current_odds.{home,away}_rendered_percent` unconditionally, and says so in a
 * comment, because the feed card renders `current_odds` whenever it renders a
 * pair at all. The event page does not: a LIVE game's hero is
 * `hero_probability` / `hero_probability_away`, a settled one is `opening_odds`,
 * and a blend-less live game falls through to `history[]`. Copying the feed's
 * one-liner here would print `current_odds`' rounding beside the BLEND's
 * probability — a mismatched pair, served confidently. So the served values are
 * taken only on the branches that read `odds`, and `fromCurrentOdds` records
 * that at the branch rather than being inferred afterwards.
 *
 * BOTH SERVED VALUES OR NEITHER. They are one decision; taking a served away
 * beside a locally-derived home re-opens the 101 from the other direction. An
 * older deploy that carries one and not the other therefore falls back whole.
 */
function withRenderedPercents(
  resolved: Omit<
    ResolvedProbability,
    "homePct" | "awayPct" | "openingHomePct" | "openingAwayPct"
  >,
  odds: CurrentOdds | undefined,
  fromCurrentOdds: boolean,
): ResolvedProbability {
  const [localAwayPct, localHomePct] = renderedDuelPercents(
    resolved.awayProb,
    resolved.homeProb,
  );
  const servedAway = fromCurrentOdds ? odds?.away_rendered_percent : null;
  const servedHome = fromCurrentOdds ? odds?.home_rendered_percent : null;
  const bothServed = servedAway != null && servedHome != null;

  // The opening line has no served pair at any deploy — `opening_odds` carries
  // only the two probabilities — so it is always decided locally.
  const [openingAwayPct, openingHomePct] = renderedDuelPercents(
    resolved.openingAwayProb,
    resolved.openingHomeProb,
  );

  return {
    ...resolved,
    awayPct: bothServed ? servedAway : localAwayPct,
    homePct: bothServed ? servedHome : localHomePct,
    openingAwayPct,
    openingHomePct,
  };
}

/**
 * Which of the chart's rail series does the live bag still stand behind?
 *
 * #6563. `historyData.win_prob_sources` is the RAIL's own list — every source
 * with rows in `win_prob_snapshots`, which is immutable history. The event's
 * `win_probability_sources` is the LIVE CLAIM, and every backend withdrawal
 * works by taking a key out of it. So the two lists come apart the moment a
 * source is withdrawn, and their difference is exactly "who has stopped
 * speaking while their line is still on the chart".
 *
 * Filtered to `PROBABILITY_SOURCE_KEYS` on the rail side for the same reason
 * `readProbabilitySourceValues` filters the bag side: one definition of "a
 * source" serves both halves of the comparison, so a non-source key present on
 * one side and absent from the other can never read as a withdrawal.
 */
export function railSourceStanding(
  historyData: EventHistoryResponse | null | undefined,
  sources: WinProbabilitySources,
): { living: string[]; withdrawn: string[] } {
  const railKeys = Object.keys(historyData?.win_prob_sources ?? {}).filter(
    (key) => PROBABILITY_SOURCE_KEYS.has(key),
  );
  const bag = new Set(readProbabilitySourceValues(sources).map(([name]) => name));
  return {
    living: railKeys.filter((key) => bag.has(key)),
    withdrawn: railKeys.filter((key) => !bag.has(key)),
  };
}

/**
 * The newest reading on a rail the bag still stands behind.
 *
 * #6563 — the substitute for the chart's own last point when that point cannot
 * be trusted. `aggregate_line` is computed BACKEND-SIDE from `win_prob_history`
 * (`routes/events.py`, the `agg_sources` block), so it blends every rail
 * including the withdrawn ones; its right edge is therefore not attributable to
 * any one source and cannot be cleared by naming one. Reading the living rails
 * directly is the only reading here that has a name attached to it.
 *
 * Newest-wins across the living rails, on the series' own timestamps. Points
 * with no `home_probability` are skipped rather than ending the scan — a
 * series' tail can carry a null reading (a row written before the price
 * arrived), and that is an absence, not a stop.
 */
export function livingRailReading(
  historyData: EventHistoryResponse | null | undefined,
  living: string[],
): { homeProb: number; source: string; timestamp: string } | null {
  const wpHistory = historyData?.win_prob_history;
  if (!wpHistory) return null;
  let best: { homeProb: number; source: string; timestamp: string } | null = null;
  for (const source of living) {
    const points = wpHistory[source];
    if (!points?.length) continue;
    for (let i = points.length - 1; i >= 0; i--) {
      const home = points[i].home_probability;
      if (home === null || home === undefined) continue;
      const timestamp = points[i].timestamp;
      if (!best || timestamp > best.timestamp) {
        best = { homeProb: home, source, timestamp };
      }
      break;
    }
  }
  return best;
}

/**
 * Determine the probability to display based on game status.
 *
 *   - Scheduled: current betting consensus
 *   - Live: current live odds (history cross-check for reliability) + opening
 *   - Completed/Closed: opening odds ("what was expected before the game")
 *   - No reported result: the chart's last point — see `noReportedResult`
 */
export function resolveProbability(
  event: EventDetailResponse,
  historyData: EventHistoryResponse | undefined,
  lastChartPoint: ActiveChartPoint | null,
  isLive: boolean,
  isFinished: boolean,
  /**
   * #4015 — the match started and nobody reported how it ended
   * (`hasNoReportedResult`: `suspended`, or `scheduled` long past its kickoff).
   *
   * Passed IN rather than derived from `event` here on purpose: the broad test
   * reads the clock, and this function is otherwise a pure function of its
   * arguments — the property `probabilityInvariant.test.ts` and the twelve-clock
   * sweep both lean on. `app/events/[id]/page.tsx` already computes it once for
   * the rest of the page, so there is one answer, not two.
   *
   * Defaults false, so every caller that predates this keeps its exact
   * behaviour.
   */
  noReportedResult: boolean = false,
  /**
   * #5069 — the blend is past its own freshness boundary, so the caption must
   * not call it "Live".
   *
   * Passed IN for the same reason `noReportedResult` is, and the reason is
   * sharper here: the page already owns exactly one answer to "how old is this
   * number" (`freshestSourceStamp`, the MAX across sources, which is the
   * blend's own age), and the badge two lines above the caption is already
   * rendered from it. Deriving a second age here would let the caption and the
   * badge disagree — which IS this bug: Sabalenka–Pegula showed a grey
   * `189m ago` above the words "Live · Bain Luck blend" in one viewport.
   *
   * The boundary is not re-invented either; the caller spends
   * `LiveAgeStamp.heroStampIsStale`, the same predicate that greys the badge.
   *
   * Defaults false, so every caller that predates this keeps its exact
   * behaviour.
   */
  blendIsStale: boolean = false,
): ResolvedProbability {
  const odds = event.current_odds;
  const opening = event.opening_odds;

  let homeProb: number | null = null;
  let awayProb: number | null = null;
  let probSourceLabel: string | null = null;
  const openingHomeProb = opening?.home_probability ?? null;
  const openingAwayProb = opening?.away_probability ?? null;
  // #2085 — set by the branch that reads `odds`, so `withRenderedPercents` can
  // tell whether the served pair describes the pair being returned. A later
  // branch that OVERRIDES the pair must clear it; that is the whole reason this
  // is a mutable flag beside the values rather than a test on the values.
  let fromCurrentOdds = false;

  // UX-P042 (#1640). Decided ONCE, up front, so the win_prob_history fallback below
  // cannot quietly re-introduce the number this branch declined to assert.
  const withheld = shouldWithholdProbability(event);

  if (isFinished) {
    // Completed/closed: show opening odds
    homeProb = openingHomeProb;
    awayProb = openingAwayProb;
    if (homeProb !== null) {
      probSourceLabel = "Pre-game odds";
    } else {
      homeProb = odds?.home_probability ?? null;
      awayProb = odds?.away_probability ?? null;
      fromCurrentOdds = true;
    }
  } else if (isLive) {
    // Live: THE BLEND IS THE HERO (L2-163 Item 2b, Alex ruling). The chart draws
    // the aggregated Bain Luck line (historyData.aggregate_line); the hero must
    // read the SAME number so a lagged sportsbook consensus never contradicts the
    // chart on screen (the 57%-hero vs 20%-chart bug).
    //
    // UX-P003 — read `hero_probability` FIRST. This branch used to lead with
    // `latestBlendPoint(aggregate_line)`, which bound the hero to a DIFFERENT
    // blend than the Discover card: the card renders
    // `compute_aggregate_probability(event)` (the point-in-time weighted median
    // over win_probability_sources), while `aggregate_line` is the time-series
    // blend — different inputs, per-bucket staleness decay, and formerly an
    // α=0.3 EMA on top. So the card and the hero it links to disagreed on the
    // same live game. Measured on production 2026-08-05:
    //
    //     Giants @ Rangers    card 60%  hero/chart 78%
    //     Dodgers @ Cubs      card 89%  hero/chart 99%
    //     Blue Jays @ Astros  card 99%  hero/chart 100%
    //
    // `hero_probability` IS `compute_aggregate_probability(event)` — literally
    // the same backend call the card uses — so binding here makes card == hero
    // by construction rather than by two paths happening to agree. The backend
    // now also pins the live edge of `aggregate_line` to that same value
    // (`_pin_live_blend_edge`), which brings the chart to the same number; the
    // aggregate_line read stays as the fallback for a cached/older payload that
    // predates the `hero_probability` field.
    // Gate on the source: `hero_probability` degrades to the OPENING line when
    // no blend exists, and an opening line is not a live blend — labelling it
    // "Bain Luck blend" would be a lie and would pre-empt the sportsbook
    // cross-check below. Only "blend" is the one number.
    const heroBlend =
      event.hero_probability_source === "blend" &&
      typeof event.hero_probability === "number"
        ? event.hero_probability
        : null;
    const blendPoint =
      heroBlend ?? latestBlendPoint(historyData?.aggregate_line);
    if (blendPoint !== null) {
      homeProb = blendPoint;
      awayProb =
        heroBlend !== null && typeof event.hero_probability_away === "number"
          ? event.hero_probability_away
          : 1 - blendPoint;
      // #5069 — "Live" describes WHEN, not WHICH. It reads to a person as "this
      // number is current", so on a blend that stopped being written it is
      // simply false, and standing notice 34 says the fix is removing a word
      // rather than adding a sentence explaining it. The number still shows;
      // only the claim about its currency goes, and the grey age badge above
      // is already saying how old it is.
      probSourceLabel = blendIsStale
        ? "Bain Luck blend"
        : "Live · Bain Luck blend";
      // 🔴 #2085 — `fromCurrentOdds` stays FALSE here on purpose. This pair is
      // the BLEND (`hero_probability` / `hero_probability_away`), which the
      // backend derives as `round(1 - agg, 6)` and serves with no rendered
      // percents of its own. `current_odds` is a different, lagging pair.
      return withRenderedPercents(
        {
          homeProb,
          awayProb,
          probSourceLabel,
          openingHomeProb,
          openingAwayProb,
        },
        odds,
        false,
      );
    }

    // No blend yet — show current odds, cross-checked against history
    homeProb = odds?.home_probability ?? null;
    awayProb = odds?.away_probability ?? null;
    fromCurrentOdds = true;
    const count = odds?.bookmaker_count ?? 0;

    if (historyData?.history && historyData.history.length > 0) {
      let latestValidHistory: (typeof historyData.history)[0] | null = null;
      for (let i = historyData.history.length - 1; i >= 0; i--) {
        if (
          historyData.history[i].home_probability !== null &&
          historyData.history[i].home_probability !== undefined
        ) {
          latestValidHistory = historyData.history[i];
          break;
        }
      }
      if (latestValidHistory) {
        const historyHome = latestValidHistory.home_probability!;
        const historyBookmakers = latestValidHistory.bookmaker_count ?? 0;
        if (homeProb === null || Math.abs(historyHome - homeProb) > 0.05) {
          homeProb = historyHome;
          awayProb =
            latestValidHistory.away_probability ?? 1 - historyHome;
          // #2085 — the pair has been REPLACED by a history row. The served
          // percents describe the `current_odds` pair this branch just
          // overrode, and the override only fires when the two differ by more
          // than 5 points, so keeping them would print a number off by five.
          fromCurrentOdds = false;
          if (historyBookmakers > 0) {
            probSourceLabel = `Live · ${historyBookmakers} sportsbook${historyBookmakers !== 1 ? "s" : ""}`;
          }
        }
      }
    }
    if (!probSourceLabel && count > 0) {
      probSourceLabel = `Live · ${count} sportsbook${count !== 1 ? "s" : ""}`;
    }
    if (!probSourceLabel && homeProb !== null && odds?.source === "aggregate") {
      probSourceLabel = "Live · Aggregate";
    }
  } else if (withheld) {
    // UX-P042 (#1640) — scheduled, but there is no probability to show. The event's
    // entire evidence base is an untraded Polymarket book at its default midpoint, and
    // `current_odds` still presents that as a confident 0.5/0.5 "aggregate" with
    // bookmaker_count 0. Assert nothing rather than invent a coin flip; the callers
    // already render a no-probability state.
    homeProb = null;
    awayProb = null;
  } else if (noReportedResult && lastChartPoint && lastChartPoint.probKnown !== false) {
    // #4015 — THE MATCH STARTED AND NOBODY REPORTED HOW IT ENDED, so leave the
    // pair null and let the win_prob_history fallback below fill it from the
    // chart's own last point.
    //
    // This state is not "scheduled". `current_odds` is a point-in-time snapshot
    // that the live poller stops rewriting the moment a match goes dark, while
    // the snapshot SERIES behind the chart keeps being extended — by the Kalshi
    // candlestick backfill, hours later. So the two drift apart, and the hero
    // ends up printing a reading OLDER than the chart directly beneath it.
    //
    // Measured on production 2026-09-08, /events/15300276 (Jodar v Bu), where
    // both numbers come from the SAME source:
    //
    //   win_probability_sources.kalshi  0.895  @ 2026-09-02T00:00:54Z  -> hero  90%
    //   win_prob_history.kalshi (last)  0.01   @ 2026-09-02T21:03:00Z  -> chart  1%
    //
    // 21 hours apart, on one screen at 390px without scrolling, with the hero
    // captioned "Aggregate" and the chart captioned "Jodar 1% — Bu 99%".
    //
    // The live branch above already settles which one wins — "the hero must read
    // the SAME number so a lagged sportsbook consensus never contradicts the
    // chart on screen". A match that has gone dark is the same defect with a
    // slower clock, so it gets the same answer rather than a second rule.
    //
    // Deliberately NOT suppressing the hero instead: the chart still draws the
    // whole journey to 1%, so blanking the number removes information without
    // removing the contradiction. The fallback labels the pair by SOURCE
    // ("Kalshi"), which attributes the reading rather than asserting a Bain Luck
    // verdict, and the header still says "No result reported" — so the page says
    // "the market last had Bu at 99%; nobody reported the finish", which is the
    // whole honest statement.
    //
    // Gated on there BEING a usable chart point: with no series to fall back to,
    // a stale `current_odds` still beats an empty hero, so such an event keeps
    // exactly the behaviour it has today.
  } else {
    // Scheduled: current betting consensus
    homeProb = odds?.home_probability ?? null;
    awayProb = odds?.away_probability ?? null;
    fromCurrentOdds = true;
    const count = odds?.bookmaker_count ?? 0;
    if (count > 0) {
      probSourceLabel = `${count} sportsbook${count !== 1 ? "s" : ""}`;
    } else if (homeProb !== null && odds?.source === "aggregate") {
      probSourceLabel = "Aggregate";
    }
  }

  // Fallback: use win_prob_history (ESPN/stat_model/Kalshi)
  // `!withheld` (UX-P042): when the only source is an untraded placeholder, its
  // history is that same placeholder.
  //
  // #3459: this used to read `lastChartPoint.homeProb !== 0.5`, testing the VALUE
  // to infer whether there was a value at all. That was the right judgment made
  // on the wrong evidence — it also refused every market that is genuinely
  // pick-'em, so a real dead-even game lost its hero for looking like an absence.
  // `probKnown` is the same judgment made on the fact itself, and it is
  // absent-means-true, so a scrub point (which always carries a real reading)
  // behaves exactly as before.
  // #5890 — AND THE EVENT MUST STILL HAVE A SOURCE. The snapshot rail is
  // immutable history; `win_probability_sources` is the live claim. When the
  // backend WITHDRAWS a source (#5820 pulls a speaker whose market we have
  // already settled, `_retire_unpriced_legs` pulls a leg that stopped trading)
  // the bag empties and the API serves the event with no `hero_probability` at
  // all — but the withdrawn price is still the last point on the rail, so this
  // arm handed it straight back and the withdrawal never reached the reader.
  //
  // Measured on production 2026-09-13, /events/15310861 (Liu v Blinkova,
  // suspended, no result): bag `{}`, no `hero_probability` and no
  // `win_probability_sources` key in the payload, chart tail 0.9945 — and the
  // hero printed `99% – 1%` captioned "Kalshi, Polymarket" under a "No result
  // reported" badge. 0.99 was a SETTLED Kalshi market's price; the caption is
  // the tell, since a row carrying no sources cannot name two.
  //
  // Driven through this function over a 40-event production sample the same
  // morning: 17 reached this arm, all 17 with an empty bag, 11 of them at a
  // settlement-shaped 0.99/0.01 tail. Nothing with a live source changed.
  //
  // NOT the value test. The `isFinished` extreme-value clause below refuses a
  // settled-looking tail; that catches 11 of the 17 and misses the six whose
  // withdrawn price is unremarkable (0.645, 0.43, 0.245), while blanking real
  // near-certain readings that a live source still stands behind. The honest
  // question is not "is this number extreme" but "does anyone still say it".
  //
  // The rule is uniform across states on purpose — a withdrawn price is no more
  // sayable on a live match than a dark one, and UX-P042 above already refuses
  // an untraded placeholder the row DOES carry. The callers render
  // "No price"/"No price yet", which is what the API is already saying.
  // #6563 — AND "STILL HAS A SOURCE" IS ASKED PER SOURCE, NOT OF THE BAG.
  //
  // #5890's gate is bag-level: it refuses when NOBODY still speaks. It cannot
  // see the case where somebody else does. On production 2026-09-16,
  // /events/15307696 (Port FC v Kobe, AFC Champions League):
  //
  //   win_probability_sources   polymarket only — kalshi WITHDRAWN at 14:18:34Z
  //   win_prob_snapshots        kalshi 461 rows, last 0.0100 @ 14:17:57Z
  //   GET /api/events/15307696  hero_probability 0.0005, source "blend"
  //   the page at 390px         1 % · "Kalshi"
  //
  // A LIVING POLYMARKET SOURCE AUTHORISED A WITHDRAWN KALSHI POINT. The bag
  // passed the #5890 test with one key in it, and the number that came back up
  // the rail belonged to the key that had been taken out — and the caption then
  // named it, which is the same tell #5890 read the other way round (a row with
  // no sources cannot name two; a row that has dropped Kalshi cannot name it).
  //
  // The reading is not re-attributed by inspecting `lastChartPoint`, because it
  // cannot be: with two or more rails the backend serves an `aggregate_line`
  // blended from `win_prob_history` — withdrawn series included — and
  // `computeLastChartPoint` reads that edge first. It is one number derived from
  // several sources, so no amount of looking at it says whose it is.
  //
  // So the rule is scoped by the only fact that IS decidable here: has anything
  // been withdrawn at all?
  //
  //   nothing withdrawn  -> unchanged, to the byte. The rail list and the bag
  //                         agree, the blend edge is a blend of living sources,
  //                         and #4015's dark-match fallback keeps its number and
  //                         its caption. This is the overwhelming majority.
  //   something withdrawn -> the blend edge is contaminated by a price nobody
  //                         stands behind, so it is replaced by the newest
  //                         reading from a rail that IS still speaking, captioned
  //                         with the living sources only. No living reading ->
  //                         no number, which is #5890's answer to the same
  //                         question one degree further along.
  //
  // On the specimen that resolves to Polymarket's own last point, 0.0005 — which
  // is exactly the `hero_probability` the payload was already serving, so the
  // page stops disagreeing with its own API as a side effect of telling the
  // truth about the source.
  const standing = railSourceStanding(historyData, event.win_probability_sources);
  const contaminated = standing.withdrawn.length > 0;
  const livingReading = contaminated
    ? livingRailReading(historyData, standing.living)
    : null;
  const fallbackHome = contaminated
    ? (livingReading?.homeProb ?? null)
    : (lastChartPoint?.homeProb ?? null);
  const fallbackAway = contaminated
    ? livingReading
      ? 1 - livingReading.homeProb
      : null
    : (lastChartPoint?.awayProb ?? null);

  if (
    !withheld &&
    homeProb === null &&
    hasProbabilitySourceReading(event.win_probability_sources) &&
    lastChartPoint &&
    lastChartPoint.probKnown !== false &&
    fallbackHome !== null &&
    fallbackAway !== null &&
    !(isFinished && (fallbackHome > 0.95 || fallbackHome < 0.05))
  ) {
    homeProb = fallbackHome;
    awayProb = fallbackAway;
    // #2085 — a chart point, not `current_odds`. Same override rule as the
    // history branch above.
    fromCurrentOdds = false;
    // #6563 — the caption names who is still speaking. On an uncontaminated
    // event that is the rail list verbatim, which is what it has always been.
    const captionSources = contaminated
      ? standing.living
      : Object.keys(historyData?.win_prob_sources ?? {});
    if (captionSources.length > 0) {
      const sourceNames = captionSources.map((s) =>
        s === "stat_model"
          ? "Model"
          : s === "espn"
            ? "ESPN"
            : s.charAt(0).toUpperCase() + s.slice(1),
      );
      probSourceLabel = isLive
        ? `Live · ${sourceNames.join(", ")}`
        : sourceNames.join(", ");
    }
  }

  return withRenderedPercents(
    { homeProb, awayProb, probSourceLabel, openingHomeProb, openingAwayProb },
    odds,
    fromCurrentOdds,
  );
}

// ---------------------------------------------------------------------------
// Chart domain computation
// ---------------------------------------------------------------------------

export interface SharedChartDomain {
  start: string;
  end: string;
  ticks: string[];
  /**
   * The date-fns format the `ticks` were built with (#3419). The charts MUST
   * format their minute categories and period-marker keys with this exact
   * string: the XAxis is categorical, so a tick only lands on a real column
   * when the two spellings match character for character.
   */
  labelFormat: string;
}

/**
 * Compute the shared x-axis domain for OddsChart and ScoreDifferentialChart.
 *
 * Collects all timestamps from every history source, computes start/end
 * based on `timeRange`, and generates evenly-spaced tick labels so both
 * charts render identical axes.
 */
export function computeSharedChartDomain(
  historyData: EventHistoryResponse | null | undefined,
  chartTimeRange: "all" | "live",
  eventStatus: string | undefined,
  commenceTime: string | undefined,
  sport: string | undefined,
): SharedChartDomain | null {
  if (!historyData) return null;

  const timestamps: number[] = [];
  for (const pt of historyData.history ?? []) {
    const t = new Date(pt.timestamp).getTime();
    if (!isNaN(t)) timestamps.push(t);
  }
  for (const pts of Object.values(historyData.win_prob_history ?? {})) {
    for (const pt of pts) {
      const t = new Date(pt.timestamp).getTime();
      if (!isNaN(t)) timestamps.push(t);
    }
  }
  for (const pt of historyData.espn_history ?? []) {
    const t = new Date(pt.timestamp).getTime();
    if (!isNaN(t)) timestamps.push(t);
  }
  for (const pts of Object.values(historyData.bookmaker_history ?? {})) {
    for (const pt of pts) {
      const t = new Date(pt.timestamp).getTime();
      if (!isNaN(t)) timestamps.push(t);
    }
  }
  if (timestamps.length === 0) return null;

  const allStart = new Date(Math.min(...timestamps));
  const allEnd = new Date(Math.max(...timestamps));
  let end = new Date(allEnd);

  // For completed games, derive end from game-end sources only.
  // If sportsbook data extends slightly beyond (within 10 min), include it
  // to avoid premature chart cutoff when ESPN data is sparse.
  const isCompleted = eventStatus === "completed" || eventStatus === "closed";
  if (isCompleted) {
    const GAME_END_SOURCES = new Set([
      "espn",
      "stat_model",
      "fangraphs",
      "mlb",
    ]);
    // A completed game's end cannot precede its start. Drop game-end timestamps
    // that fall before commence_time (minus a small pregame margin): a
    // mis-attributed earlier game's snapshots (gotcha #32 / inverted completed_at)
    // otherwise drag `end` to before `start`, inverting the domain and rendering
    // an EMPTY settled chart (Queue #189). With them gone we fall through to the
    // commence-based window and the real journey renders.
    const ctMs = commenceTime ? new Date(commenceTime).getTime() : NaN;
    const endFloorMs = !isNaN(ctMs) ? ctMs - 60 * 60 * 1000 : -Infinity;

    // #7315 — CEILING, AND IT IS THE FLOOR'S TWIN. A game-end source cannot see
    // the end of a game six hours after the game ended; a row stamped there is
    // a later write, and it drags `end` with it. The two specimens in #7315 —
    // `score_snapshots` rows written 51.7 h and 68.4 h after `completed_at` —
    // stretched the Score Differential domain three days past the whistle,
    // which is the 2026-09-14 chart-duration ruling as well as a wrong hero.
    //
    // Same failure mode as the floor, so the same shape: drop the rows, and if
    // that leaves nothing, `gameEndTs.length > 0` falls through to the
    // betting/commence branches below and the real journey still renders. Null
    // or unparseable `completed_at` ⇒ no ceiling, i.e. today's behaviour.
    //
    // Scoped to the grace measured on `score_snapshots` (see
    // POST_FULL_TIME_WRITE_GRACE_MS) but applied to every game-end series: the
    // claim "nothing observed this game six hours after it finished" is about
    // the game, not about one writer, and a ceiling that only one series obeyed
    // would just wait for the next series to be poisoned.
    const caMs = historyData.completed_at
      ? new Date(historyData.completed_at).getTime()
      : NaN;
    const endCeilMs = !isNaN(caMs)
      ? caMs + POST_FULL_TIME_WRITE_GRACE_MS
      : Infinity;
    const inGameWindow = (t: number) =>
      !isNaN(t) && t >= endFloorMs && t <= endCeilMs;

    const gameEndTs: number[] = [];

    for (const pt of historyData.espn_history ?? []) {
      const t = new Date(pt.timestamp).getTime();
      if (inGameWindow(t)) gameEndTs.push(t);
    }
    for (const [source, pts] of Object.entries(
      historyData.win_prob_history ?? {},
    )) {
      if (!GAME_END_SOURCES.has(source)) continue;
      for (const pt of pts) {
        const t = new Date(pt.timestamp).getTime();
        if (inGameWindow(t)) gameEndTs.push(t);
      }
    }
    // #6349 — THE SCORE IS A GAME-END SOURCE, AND LEAVING IT OUT INVERTED THE
    // WINDOW. `score_history` is StatPal's livescore series: the most direct
    // evidence this page holds of when the game was actually being played, and
    // one of the four series `maxPostStartSeriesPoints` counts when it picks
    // "Since Start" for the page. This ladder counted the other three and not
    // this one, so a game whose odds stopped before kickoff chose "Since Start"
    // on the strength of its score points and then derived `end` from the
    // sportsbook tail — an end BEFORE the start it had just chosen.
    //
    // Measured on /events/15296797 (Banfield 1-1 Barracas Central, FINAL,
    // 2026-09-15): commence 22:00:00Z, every one of 1,907 betting points, 2,741
    // aggregate points, 638 Polymarket and 497 Kalshi points ends 02:08Z — 19h52m
    // BEFORE kickoff, zero post-start points on every series the ladder could
    // see. Only `score_history` was in the game: 22:03Z 0-0, 22:49Z 1-0, 23:26Z
    // 1-1. The window came out 22:00Z → 02:08Z, `fillMinuteGaps` no-opped on it,
    // and the reader got a Win Probability grid whose three `<path>` elements
    // carried an EMPTY `d`, over a "Score Differential" heading with no SVG
    // under it at all.
    //
    // The `endFloorMs` guard above applies to these the same as to the rest: a
    // score row stamped before the pregame margin is the mis-attribution case,
    // not a game end. (#7315: and `endCeilMs` the same at the other end — this
    // is the series both of its specimens came out of.)
    for (const pt of historyData.score_history ?? []) {
      const t = new Date(pt.timestamp).getTime();
      if (inGameWindow(t)) gameEndTs.push(t);
    }

    if (gameEndTs.length > 0) {
      const lastGameEnd = Math.max(...gameEndTs);

      // Check if sportsbook data extends slightly beyond game-end sources.
      // This prevents premature cutoff when ESPN data is sparse (e.g.,
      // baseball chart cutting off at 8th inning).
      let endMs = lastGameEnd;
      const MAX_EXTENSION_MS = 10 * 60 * 1000; // 10 min max extension
      const bettingTs: number[] = [];
      for (const pt of historyData.history ?? []) {
        const t = new Date(pt.timestamp).getTime();
        if (!isNaN(t)) bettingTs.push(t);
      }
      if (bettingTs.length > 0) {
        const lastBetting = Math.max(...bettingTs);
        if (lastBetting > lastGameEnd && lastBetting - lastGameEnd <= MAX_EXTENSION_MS) {
          endMs = lastBetting;
        }
      }

      // End AT the final snapshot — no trailing buffer (L2-131 / gotcha #22).
      // The old +5 min pad left a flat forward-filled tail that read as if the
      // game continued after it ended.
      end = new Date(endMs);
    } else if (historyData.history && historyData.history.length > 0) {
      // No game-end sources — end at the last sportsbook snapshot.
      const bettingTs: number[] = [];
      for (const pt of historyData.history) {
        const t = new Date(pt.timestamp).getTime();
        if (!isNaN(t)) bettingTs.push(t);
      }
      if (bettingTs.length > 0) {
        end = new Date(Math.max(...bettingTs));
      }
    } else if (commenceTime) {
      const ct = new Date(commenceTime);
      if (!isNaN(ct.getTime())) {
        const sportStr = sport || "";
        const isSoccer = sportStr.startsWith("soccer");
        const isTennis = sportStr.startsWith("tennis");
        const isCricket = sportStr.startsWith("cricket");
        const durationMin = isSoccer
          ? 110
          : isTennis
            ? 180
            : isCricket
              ? 240
              : 150;
        const estimated = new Date(ct.getTime() + durationMin * 60_000);
        end = estimated < end ? estimated : end;
      }
    } else if (historyData.completed_at) {
      const ca = new Date(historyData.completed_at);
      if (!isNaN(ca.getTime())) {
        end = ca;
      }
    }

    // FLOOR (#3419): a completed game's window may not end before its own data
    // begins. Every branch above derives `end` from a field that can be wrong
    // in a way `end` cannot absorb — a ticker-derived midnight `commence_time`
    // plus a flat duration estimate, an inverted `completed_at`, a game-end
    // source belonging to a different game. When the derived end lands before
    // the FIRST point we are drawing, it is not trimming a trailing tail (what
    // this block is for), it is deleting the whole series: "Since Start" cuts
    // to a window the match was not played in, and "All" comes out INVERTED,
    // where fillMinuteGaps no-ops and the chart renders empty.
    //
    // Measured on /events/15300276 (Jodar v Bu, US Open, FINAL, Kalshi-only):
    // commence_time 2026-09-01T00:00Z + 180 tennis minutes = an end of 03:00Z,
    // 12h56m BEFORE the first of its 559 points. Discard a derived end that
    // fails this test and keep the honest maximum — a visible journey beats a
    // precisely-trimmed empty one.
    if (end.getTime() < allStart.getTime()) {
      end = new Date(allEnd);
    }
  }

  // "Since Start" mode: start from commenceTime
  const gameStart = commenceTime ? new Date(commenceTime) : null;

  // #8215 — "SINCE START" MAY NOT CUT AT AN HOUR THAT IS NOT A START.
  //
  // For a Kalshi-clocked dated fixture we store the venue's `occurrence_datetime`, which is
  // byte-identical to `expected_expiration_time`: when the CONTRACT is expected to resolve, about
  // two hours after a tennis match is over. Kalshi publishes no kick-off field at all.
  //
  // Measured on /events/15317314 (Basilashvili v Cina, ATP, 2026-09-23): commence_time 09:10Z, and
  // the 525 Kalshi+Polymarket points run 2026-09-22 17:45Z → 2026-09-23 09:19Z. Exactly 4 of those
  // 525 fall at or after 09:10Z, so "Since Start" drew a nine-minute dead-flat tail at 99% and
  // called it the match.
  //
  // 🔴 THE FLOOR BELOW CANNOT CATCH THIS, which is why the flag is needed at all. Every existing
  // escape hatch here and in `OddsChart.rangeStartTime` is "nothing survives the cut" — and this
  // population sits just PAST it, on a handful of post-settlement quotes. Four surviving points is
  // not an empty window; it is a wrong one, and no test on the series can tell the two apart.
  //
  // ⚠️ Read the served flag; never re-derive it. It is a statement about which venue column the
  // hour came from, not about the shape of the points (see `EventHistoryResponse`). `undefined` —
  // an older payload — keeps today's behaviour; only an explicit `false` declines the cut, and
  // then the honest full extent is the window, the same remedy as the floor and the inversion
  // backstop below.
  const commenceIsKickoff = historyData.commence_time_is_kickoff;
  const liveStart =
    gameStart && !isNaN(gameStart.getTime()) && commenceIsKickoff !== false
      ? gameStart
      : allStart;

  // "All" mode: cap the start to at most 2 hours before commenceTime once a game
  // is in-game (live) or finished. Prevents charts from showing many hours of
  // flat pre-game odds data that makes the in-game chart unreadable — AND keeps
  // the rendered window under 12h so the "h:mm a" categorical inning markers
  // can't collide across a day boundary and render out of order (L2-163 Item 2c;
  // the "T9 left of T1" collision). Scheduled/pregame is left uncapped — there
  // the multi-hour odds-drift IS the story.
  //
  // The cap is anchored on commence_time, which is exactly the field that is
  // untrustworthy when a start was never reported. Applying it blind can move
  // the window PAST every point the event has and leave "All" as empty as
  // "Since Start" was. Only cap when something survives the cap.
  const isInGame = isCompleted || eventStatus === "live";
  let allModeStart = allStart;
  if (isInGame && gameStart && !isNaN(gameStart.getTime())) {
    const twoHoursBefore = new Date(gameStart.getTime() - 2 * 60 * 60 * 1000);
    if (
      allModeStart < twoHoursBefore &&
      timestamps.some((t) => t >= twoHoursBefore.getTime())
    ) {
      allModeStart = twoHoursBefore;
    }
  }

  // #6349 — THE START SNAPS DOWN, THE END SNAPS UP, SO THE LAST OBSERVATION IS
  // INSIDE THE WINDOW IT DEFINED. Both used to truncate, which silently drops
  // any point in the final partial minute — including, now, the very row the
  // game-end ladder above derived `end` FROM. On 15296797 the equaliser is
  // stamped 23:26:54Z; truncating to 23:26:00Z put it outside the window and
  // left a 1-1 match drawing a score line that ends 1-0. Ceiling is at most 59
  // seconds of extra window and is not the trailing buffer L2-131 removed — it
  // is the difference between including the final snapshot and excluding it.
  const snapEndUp = (d: Date): Date => {
    const snapped = new Date(d);
    snapped.setSeconds(0, 0);
    if (snapped.getTime() < d.getTime()) snapped.setTime(snapped.getTime() + 60_000);
    return snapped;
  };
  let start = chartTimeRange === "live" ? liveStart : allModeStart;
  start.setSeconds(0, 0);
  end = snapEndUp(end);

  // #6349 — A WINDOW MAY NOT END BEFORE IT STARTS. The FLOOR above is the same
  // invariant measured against `allStart`, the first point of the whole event;
  // it cannot see this one, because the end that inverts "Since Start" is a
  // real, later timestamp that simply falls before the chosen start. On
  // 15296797 `end` (02:08Z, the last sportsbook tick) was 15 days AFTER
  // `allStart` and 19h52m BEFORE `start` — the earlier floor passed, and the
  // chart drew nothing.
  //
  // The score-history clause above is the honest repair for the case we
  // measured. This is the backstop for the arm it does not reach: a completed
  // game whose only post-kickoff series is a win-prob source deliberately kept
  // OUT of `GAME_END_SOURCES` (Kalshi and Polymarket keep quoting past the
  // final whistle, which is exactly why they are excluded), and which holds no
  // score rows. There `gameEndTs` is still empty, `end` still comes off the
  // sportsbook tail, and the window still inverts.
  //
  // An inverted window is never a narrower truth — it is a window the match was
  // not played in. Fall back to the honest full extent, the same remedy and the
  // same reasoning as the floor above: a visible journey beats a precisely
  // trimmed empty one.
  if (end.getTime() <= start.getTime() && allEnd.getTime() > allStart.getTime()) {
    start = new Date(allStart);
    start.setSeconds(0, 0);
    end = snapEndUp(allEnd);
  }

  // Compute explicit X-axis ticks at clean time boundaries.
  //
  // UX-P022: the interval used to FLOOR at 30 minutes
  // (`durationMin < 180 ? 30 : 60`, then doubled while it produced >10 ticks).
  // That only ever coarsened, never refined, so a chart shorter than ~an hour
  // got no interior tick at all. A live game 21 minutes old rendered exactly
  // "1:10 PM" and "1:31 PM" across a full-width chart — the reader cannot tell
  // whether a move happened two minutes ago or twenty.
  //
  // The ladder below refines as well as coarsens: it picks the smallest clean
  // interval that keeps the tick count at or under the target. A 21-minute
  // window now steps by 5 minutes.
  const durationMs = end.getTime() - start.getTime();
  const durationMin = durationMs / 60000;
  // #3419: a window at or beyond a day needs its labels date-qualified to stay
  // unique, and a date-qualified label is ~40% wider ("Tue 6:00 AM" vs
  // "6:00 AM"), so it has to buy that width from the tick budget. Same total
  // ink, fewer and more informative labels.
  const labelFormat = categoryLabelFormat(start.getTime(), end.getTime());
  const MAX_TICKS = labelFormat === CATEGORY_LABEL_FORMAT ? 8 : 5;
  const INTERVAL_LADDER_MIN = [1, 2, 5, 10, 15, 30, 60, 120, 180, 360, 720, 1440];
  let intervalMin =
    INTERVAL_LADDER_MIN.find((step) => durationMin / step <= MAX_TICKS) ??
    INTERVAL_LADDER_MIN[INTERVAL_LADDER_MIN.length - 1];
  // Degenerate window (everything inside one step): keep the endpoints only.
  while (durationMin / intervalMin > MAX_TICKS) intervalMin *= 2;

  const ticks: string[] = [];
  ticks.push(fmtDate(start, labelFormat));

  // A boundary tick landing right next to the end label collides with it and
  // Recharts silently drops one of the pair — which is how a 3-tick axis
  // rendered as 2. Reserve a slice of the window for the end label instead.
  const endMs = end.getTime();
  const minGapMs = Math.max(durationMs * 0.06, 30_000);

  const cursor = new Date(start);
  const curMins = cursor.getMinutes();
  const nextBoundary = Math.ceil((curMins + 1) / intervalMin) * intervalMin;
  cursor.setMinutes(nextBoundary, 0, 0);
  while (cursor.getTime() < endMs) {
    if (endMs - cursor.getTime() >= minGapMs) {
      ticks.push(fmtDate(cursor, labelFormat));
    }
    cursor.setMinutes(cursor.getMinutes() + intervalMin);
  }

  const endLabel = fmtDate(end, labelFormat);
  if (ticks[ticks.length - 1] !== endLabel) {
    ticks.push(endLabel);
  }

  return {
    start: start.toISOString(),
    end: end.toISOString(),
    ticks,
    labelFormat,
  };
}

// ---------------------------------------------------------------------------
// Win-probability Y axis
// ---------------------------------------------------------------------------

/** The 0–100 axis every win-probability chart used before #3973. */
export const FULL_WIN_PROB_Y_AXIS: WinProbYAxis = {
  domain: [0, 100],
  ticks: [0, 25, 50, 75, 100],
};

export interface WinProbYAxis {
  domain: [number, number];
  ticks: number[];
}

/** Below this many samples a percentile is not a percentile — keep the full axis. */
const WIN_PROB_Y_MIN_SAMPLES = 12;
/** Narrowest window we will ever show, so a 2-point wobble is not magnified into drama. */
const WIN_PROB_Y_MIN_SPAN = 20;
/**
 * Share of the plot's height the p2..p98 core must keep before we prefer the
 * true extremes over the percentile window (#7837). See rule 1b.
 */
const WIN_PROB_Y_MIN_CORE_SHARE = 0.5;
/** Grid the axis snaps to; 50 is a multiple of all three, so it is always ON the grid. */
const WIN_PROB_Y_STEPS = [5, 10, 25];
const WIN_PROB_Y_MAX_INTERVALS = 5;

function percentile(sorted: number[], q: number): number {
  const i = q * (sorted.length - 1);
  const lo = Math.floor(i);
  const hi = Math.min(lo + 1, sorted.length - 1);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (i - lo);
}

/**
 * The Y axis for the win-probability chart: the window the line actually lives
 * in, rather than the whole 0–100 range (#3973).
 *
 * ═══ WHY THIS IS NOT JUST `[0, 100]` ANY MORE ═══
 *
 * A tennis match page measured on production: 1,588 plotted samples on
 * `/events/15306813`, of which 98% sit between 21.5% and 27.8%. On a fixed
 * 0–100 axis that entire market — every move a reader opened the page to see —
 * is 6.8% of the plot's height, and renders as a horizontal line. Its sibling
 * `/events/15306225` is the same shape: 98% of 2,000 samples inside 56.5–61.0.
 *
 * NOTE THE FILING'S CAUSE WAS WRONG AND THE FIX IS NOT WHAT IT ASKED FOR.
 * #3973 is titled "a single early outlier stretches the chart to 0–100%".
 * It does not: `yDomain` was a hardcoded literal, so the outlier stretched
 * nothing. The flat line is what a fixed 0–100 axis does to any narrow market,
 * outlier or none. The outlier matters only because it defeats the obvious
 * repair — a plain min/max domain on `/events/15306813` is [21, 92], which is
 * as flat as what it replaces. Hence percentiles, not extremes.
 *
 * ═══ THE FOUR RULES, AND WHAT EACH ONE IS PAYING FOR ═══
 *
 * 1. `p2..p98`, not min/max. 10 of those 1,588 samples (0.63%) are the early
 *    spike; they are still DRAWN — the caller sets `allowDataOverflow`, which
 *    fits a clip path confining them to the plot instead of letting them paint
 *    over the card — but they no longer set the scale for the other 99.4%. At
 *    0.6% of the series that is ~2px at the left edge, against a whole chart
 *    flattened today.
 *
 * 1b. …BUT ONLY WHERE THE EXTREMES WOULD ACTUALLY FLATTEN THE CORE (#7837).
 *    "Confined to the plot by a clip path" means a point outside the domain is
 *    drawn as a line running off the frame, and rule 1 applied unconditionally
 *    spends that on series whose extremes are not noise but the story. Measured
 *    over the whole NFL slate of 2026-09-20 (14 games, blend series inside each
 *    chart's own rendered window), two came out clipped AFTER rule 4's outward
 *    snap, and they are the two games a reader would open:
 *
 *      14780544  KC 33–30 IND (OT)   216 pts  true 24.2–100.0  axis [40, 90]
 *      14782150  TB–CLE              219 pts  true  0.0– 91.6  axis [25, 100]
 *
 *    On the first, Kansas City's two near-losses (24.2%) ran off the bottom and
 *    the win ran off the top — while the trailing callout printed `100%` against
 *    an axis whose highest tick said 90%. The label and the scale contradicted
 *    each other on the decisive moment of the game.
 *
 *    The separator is not sample count (3.2% of that series was outside, vs
 *    0.63% on the tennis page) but how much of the plot the core would give up:
 *    the core band is 63% of the full range on both NFL specimens and 8.9% on
 *    15306813, whose 21–92 spike is the case rule 1 exists for. So we take the
 *    true extremes whenever the core keeps at least `WIN_PROB_Y_MIN_CORE_SHARE`
 *    of the height, and keep the percentile window when it would not. The other
 *    12 games of that slate are unchanged — rule 4's snap had already absorbed
 *    their extremes — so this moves exactly the domains that were clipping.
 *
 * 2. 50 is forced in IF THE SERIES TOUCHES IT, and only then. The chart stamps
 *    its crossing diamonds at y=50 and draws a dashed reference line there,
 *    so a domain that excluded 50 while the line crossed it would clip a marker
 *    the "Crossed 50% (N)" chip is still counting (#4882 renamed that chip from
 *    "Lead changes", which is not what it counts; the coupling is unchanged).
 *    Conversely a market that
 *    never approaches 50 has no crossings and no reason to spend axis on it;
 *    the caller leaves recharts' `ifOverflow="discard"` to drop the reference
 *    line, because a reference line outside the plot is not a reference.
 *    The test is raw min/max, not the percentiles: a SINGLE crossing print is
 *    exactly the one that mints a marker, and p2 would throw it away.
 *
 * 3. A minimum span of 20 points. Without it a market that sat at 49–51 all
 *    week would be magnified into a full-height thriller — the same lie as
 *    today's flat line, pointing the other way.
 *
 * 4. Snap outward to a 5/10/25 grid anchored at 0. Anchoring at zero (rather
 *    than at the domain's low end) is what keeps 50 on the tick set whenever it
 *    is in range, which is what #3525 leaned on when it deleted the 50% line's
 *    own label: "the left axis already prints 50% on this exact line".
 *
 * A market that genuinely uses the range is UNCHANGED: 10%–90% snaps to
 * [0, 100] with ticks 0/25/50/75/100, byte for byte the old axis.
 */
export function computeWinProbYAxis(values: number[]): WinProbYAxis {
  const finite = values.filter((v) => typeof v === "number" && Number.isFinite(v));
  if (finite.length < WIN_PROB_Y_MIN_SAMPLES) return FULL_WIN_PROB_Y_AXIS;

  const sorted = [...finite].sort((a, b) => a - b);
  let lo = percentile(sorted, 0.02);
  let hi = percentile(sorted, 0.98);

  // Rule 1b — the zoom is for extremes that would FLATTEN the core, not for
  // extremes that describe it. Compared BEFORE any of the widening rules below,
  // so the comparison is core-vs-full and not core-vs-whatever-rule-3-imposed.
  const fullLo = sorted[0];
  const fullHi = sorted[sorted.length - 1];
  const fullSpan = fullHi - fullLo;
  if (fullSpan > 0 && (hi - lo) / fullSpan >= WIN_PROB_Y_MIN_CORE_SHARE) {
    lo = fullLo;
    hi = fullHi;
  }

  // Rule 2 — decided on the extremes, because one crossing print is one marker.
  const touchesEven = sorted[0] <= 50 && sorted[sorted.length - 1] >= 50;
  if (touchesEven) {
    lo = Math.min(lo, 50);
    hi = Math.max(hi, 50);
  }

  // Rule 3.
  if (hi - lo < WIN_PROB_Y_MIN_SPAN) {
    const mid = (lo + hi) / 2;
    lo = mid - WIN_PROB_Y_MIN_SPAN / 2;
    hi = mid + WIN_PROB_Y_MIN_SPAN / 2;
  }

  // Rule 4.
  const step =
    WIN_PROB_Y_STEPS.find((s) => (hi - lo) / s <= WIN_PROB_Y_MAX_INTERVALS) ??
    WIN_PROB_Y_STEPS[WIN_PROB_Y_STEPS.length - 1];
  let snappedLo = Math.max(0, Math.floor(lo / step) * step);
  let snappedHi = Math.min(100, Math.ceil(hi / step) * step);

  // Never leave 50 welded to the frame: a dashed line and a diamond drawn ON
  // the top or bottom axis read as chart furniture, not as the even mark.
  if (touchesEven && snappedHi === 50) snappedHi = Math.min(100, 50 + step);
  if (touchesEven && snappedLo === 50) snappedLo = Math.max(0, 50 - step);

  // Clamping at 0/100 can eat rule 3's floor back off (a market at 2–4% expands
  // to [-7, 13] and then to [0, 13]); give the span back at the other end.
  if (snappedHi - snappedLo < WIN_PROB_Y_MIN_SPAN) {
    if (snappedLo === 0) snappedHi = Math.min(100, snappedLo + WIN_PROB_Y_MIN_SPAN);
    else snappedLo = Math.max(0, snappedHi - WIN_PROB_Y_MIN_SPAN);
  }

  const ticks: number[] = [];
  for (let t = snappedLo; t <= snappedHi; t += step) ticks.push(t);

  return { domain: [snappedLo, snappedHi], ticks };
}

// ---------------------------------------------------------------------------
// Shared chart time range
// ---------------------------------------------------------------------------

/**
 * The largest number of post-`commenceTime` points held by any ONE chart
 * series (sportsbook history, score history, ESPN history, or a single
 * win-prob source).
 *
 * Per-series, not pooled: the charts draw one `<Line>` per series and a line
 * needs two points of its OWN. Pooling would let four series with one point
 * each read as four points and re-select a range that draws nothing.
 *
 * Why the page needs this at all. Both charts already compute a
 * `hasPostStartData` and refuse "Since Start" when it would be empty —
 * OddsChart even disables the toggle. But the event page passes
 * `externalTimeRange`, and `timeRange = externalTimeRange ?? internalTimeRange`
 * means the parent's value wins outright, so each child's own fallback is dead
 * code on this page. Pinned to "live" by the parent, an event whose
 * `commence_time` is a stand-in rather than a reported first serve renders BOTH
 * charts as an empty grid.
 *
 * The exhibit — US Open Jodar v Kokkinakis (15293847), measured live on
 * production 2026-09-01 22:18Z: `commence_time` 16:00:00Z, an exact top of the
 * hour written by the Odds API's session-start default, while the last
 * sportsbook quote is 15:44Z — sixteen minutes BEFORE the "start". Zero
 * post-start odds points, one post-start score point, one post-start Kalshi
 * point. Win Probability rendered a bare grid with a single dot at the right
 * edge; Score Differential rendered nothing at all; and "Since Start" showed as
 * the selected pill on a button OddsChart had itself disabled.
 *
 * Note the counting rule is what makes that exhibit come out right. A
 * has-any test passes on it — one score point IS post-start — and the chart is
 * still blank, because one point with `dot={false}` draws no segment.
 */
export function maxPostStartSeriesPoints(
  historyData: EventHistoryResponse | null | undefined,
  commenceTime: string | undefined,
): number {
  if (!historyData || !commenceTime) return 0;
  const cutoff = new Date(commenceTime).getTime();
  if (isNaN(cutoff)) return 0;

  const countAtOrAfter = (
    points: { timestamp?: string }[] | null | undefined,
  ): number => {
    let n = 0;
    for (const p of points ?? []) {
      if (!p?.timestamp) continue;
      const t = new Date(p.timestamp).getTime();
      if (!isNaN(t) && t >= cutoff) n += 1;
    }
    return n;
  };

  let most = 0;
  most = Math.max(most, countAtOrAfter(historyData.history));
  most = Math.max(most, countAtOrAfter(historyData.score_history));
  most = Math.max(most, countAtOrAfter(historyData.espn_history));
  for (const pts of Object.values(historyData.win_prob_history ?? {})) {
    most = Math.max(most, countAtOrAfter(pts));
  }
  return most;
}

/** Two points make a line; one point with `dot={false}` makes an empty grid. */
export const MIN_POINTS_TO_DRAW_A_LINE = 2;

/**
 * The shared "All" / "Since Start" range the page should hold before the
 * reader has picked one. "Since Start" only when some series can actually
 * draw inside it — otherwise "All", which is what each chart would have
 * chosen on its own.
 */
export function defaultChartTimeRange(
  historyData: EventHistoryResponse | null | undefined,
  commenceTime: string | undefined,
): "all" | "live" {
  return maxPostStartSeriesPoints(historyData, commenceTime) >=
    MIN_POINTS_TO_DRAW_A_LINE
    ? "live"
    : "all";
}

// ---------------------------------------------------------------------------
// Last chart point computation
// ---------------------------------------------------------------------------

/**
 * #7315 — HOW LONG AFTER FULL TIME A SERIES MAY STILL BE OBSERVING THE GAME.
 *
 * Past this, a row stamped after `completed_at` is a later WRITE, not a later
 * reading: the game is over, so there is no newer information about it, only
 * newer rows about it.
 *
 * Six hours is not a taste call — it sits in a measured gap. Over every event
 * completed in the five days to 2026-09-19, `score_snapshots` rows stamped
 * after their event's `completed_at` fall into two populations and nothing
 * lies between them:
 *
 *   54 events  ≤ 21 minutes after (50 of them sub-second) — the ordinary
 *              trailing write as a game is marked final
 *    2 events  51.7 h and 68.4 h after — #7315's own two specimens
 *
 * So the threshold has ~17× clearance above the honest tail and ~8× below the
 * nearest defect. It is deliberately far from both edges: a grace tight enough
 * to be precise would start adjudicating the ordinary case, which is not what
 * this rule is for.
 */
export const POST_FULL_TIME_WRITE_GRACE_MS = 6 * 60 * 60 * 1000;

/**
 * #5521 — DOES THE StatPal SNAPSHOT ARM OUTRANK THE ESPN-SHAPED HISTORY ARM?
 *
 * Strictly newer wins. A tie keeps the ESPN arm, and so does any comparison
 * either side of which cannot be parsed: *"we cannot say which is newer"* and
 * *"the snapshot is newer"* are different claims, and only the second may move
 * a number a reader is looking at. That is the same rule `heroStampIsStale` and
 * `liveClaimIsUnbacked` (#5459) are written to, one helper further in.
 *
 * Pure and exported so a guard can hold the comparison itself rather than
 * re-deriving it from a rendered score — the seam, not the symptom.
 *
 * ═══ 🔴 #7315 — A CLOCK COMPARISON IS THE RIGHT RULE WHILE A GAME IS BEING
 * PLAYED AND THE WRONG ONE AFTER THE WHISTLE ═══
 *
 * #5521 made this pick clock-based, correctly, for the live case. What it has
 * no notion of is *the game is over*, and the ladder beneath it ends at the
 * event row — so a `score_snapshots` row stamped three days after full time
 * outranked an ESPN point that said `Final`, and the hero printed a score the
 * event row did not hold and could not hold:
 *
 *   /events/15313231  printed 5 – 5 · FINAL · TIED   (event row + ESPN: 5 – 6)
 *   /events/15313146  printed 7 – 2                  (event row + ESPN: 7 – 3)
 *
 * An MLB regular-season game cannot end level, so the first one is visibly
 * impossible — photographed on production at 390px after #7147's data repair
 * had already corrected both rows. The data half (#7314) deletes the offending
 * rows; this is what stops the next writer re-creating the symptom.
 *
 * THE TEST IS `completed_at`, NOT A PERIOD LABEL. The tempting version reads
 * the history point's own `period` and lets a `Final` row win regardless of
 * clock. Measured, that rule would be a dud: `espn_snapshots.period` holds zero
 * rows matching `final`/`full`/`ft` in 30 days — every terminal spelling a
 * reader sees comes in through `routes/events.py`'s MLB/`stat_model` supplement
 * (`game_state.period`), so the rule would fire on the feeders that happen to
 * write that English word and silently never fire anywhere else. `completed_at`
 * is a column with one meaning, is served in this very payload, and is null
 * while a game is live — which is exactly when this rule must not exist.
 *
 * So: absent or unparseable `completed_at` ⇒ #5521 unchanged, to the byte.
 *
 * The asymmetry is deliberate. This disables the snapshot arm's OVERRIDE, it
 * does not drop poisoned points from both series: the history arm is already
 * the default, so a rule about it would be a different change with a different
 * blast radius, and nothing measured asks for one yet.
 */
export function scoreSnapshotOutranksHistory(
  snapshotStamp: string | null | undefined,
  historyStamp: string | null | undefined,
  /**
   * #7315 — `EventHistoryResponse.completed_at`. Optional, so every existing
   * caller keeps #5521's behaviour exactly.
   */
  completedAt?: string | null,
): boolean {
  const snap = snapshotStamp ? Date.parse(snapshotStamp) : NaN;
  const hist = historyStamp ? Date.parse(historyStamp) : NaN;
  if (Number.isNaN(snap) || Number.isNaN(hist)) return false;
  const done = completedAt ? Date.parse(completedAt) : NaN;
  if (!Number.isNaN(done) && snap > done + POST_FULL_TIME_WRITE_GRACE_MS) {
    return false;
  }
  return snap > hist;
}

/**
 * #5521 — resolve ONE side of the score from the two observation series.
 *
 * ═══ 🔴 THE SNAPSHOT ARM MAY REPLACE AN ESPN READING, NEVER FILL IN FOR AN
 * ABSENT ONE — AND THAT BOUNDARY IS MEASURED, NOT TASTE ═══
 *
 * The tempting version of this fix makes `score_history` a third fallback, so
 * it supplies the score wherever `espn_history` is silent. Censused on
 * production 2026-09-12 06:55Z over a 72-hour window, that is 134 events (45
 * competitions, overwhelmingly soccer) — and on 132 of them the last snapshot
 * equals the event row, so the change would be inert. On the two where it does
 * NOT, it is a REGRESSION, and on exactly the pages that matter most:
 *
 *   15307525 Zverev v van de Zandschulp (US Open, completed) — event row 3–0,
 *            last snapshot 2–0, captured 32 min before `completed_at`
 *   15308966 Gauff v Rybakina (US Open, completed) — event row 1–2,
 *            last snapshot 1–1, captured 48 min before `completed_at`
 *
 * The snapshot series simply STOPS before the final set; the event row is
 * overwritten in place and is therefore the current value by construction. So a
 * series that lags cannot outrank a value that does not. It may only argue with
 * the OTHER series — where the argument is decidable, because both sides carry
 * their own clock.
 *
 * Where the argument IS decidable the fix is right every time it fires: of 41
 * events carrying both series in the same window, 10 change, and on 10 of 10
 * the new number matches the event row (0 of 10 break agreement with it).
 *
 * Rates in this comment are the population deltas, not a live percentage — a
 * rate written into a durable artifact decays and then invents a regression.
 */
function pickHistorySide(
  espnValue: number | null | undefined,
  espnStamp: string | null,
  snapValue: number | null | undefined,
  snapStamp: string | null,
  snapWins: boolean,
): { value: number | null; stamp: string | null } {
  // `== null` on the VALUE, not on the row: an ESPN row present but holding a
  // null score is a side ESPN did not speak for, and #4571 already falls it
  // through to the event row with its stamp. The snapshot does not get to
  // intercept that fall — see the boundary above.
  if (espnValue == null) return { value: null, stamp: null };
  if (snapWins && snapValue != null) return { value: snapValue, stamp: snapStamp };
  return { value: espnValue, stamp: espnStamp };
}

/**
 * Compute the most recent chart point for GamePlayCard default display.
 */
export function computeLastChartPoint(
  historyData: EventHistoryResponse | null | undefined,
  homeScore: number | null | undefined,
  awayScore: number | null | undefined,
  /**
   * #4571 — `event.score_observed_at`: when a writer last READ the event row's
   * score. Optional, so every existing caller keeps its current behaviour and
   * simply gets `scoreStamp: null` on the event-row arm.
   */
  eventScoreObservedAt?: string | null,
): ActiveChartPoint | null {
  if (!historyData) return null;

  const espn = historyData.espn_history;
  const lastEspn = espn?.length ? espn[espn.length - 1] : null;

  const wpHistory = historyData.win_prob_history;
  let lastWp: { home_probability: number | null; timestamp: string } | null =
    null;
  if (wpHistory) {
    for (const pts of Object.values(wpHistory)) {
      if (pts.length) {
        const last = pts[pts.length - 1];
        if (!lastWp || last.timestamp > lastWp.timestamp) {
          lastWp = last;
        }
      }
    }
  }

  const hist = historyData.history;
  const lastHist = hist?.length ? hist[hist.length - 1] : null;

  // L2-174 Item 1 — THE READOUT INVERSION. The resting readout must agree with
  // the hero. The hero (resolveProbability, live branch) and the scrub tooltip
  // (OddsChart `bainLuckDelta`) both read the aggregate_line BLEND — the weighted
  // "Bain Luck" line the chart draws. The at-rest readout was instead trusting a
  // SINGLE win_prob_history source's `home_probability`, whose orientation can be
  // opposite the blend (a source's home-field is actually the away side). That
  // rendered "Cardinals 99% — Diamondbacks 1%" under a hero that correctly showed
  // the inverse. Read the blend FIRST so the strip-at-rest, the scrub, and the
  // hero all speak one orientation-consistent number; the win_prob_history/history
  // fallbacks only fire when there is no blend point yet.
  //
  // #1003: `history[].home_probability` is a 0–1 FRACTION (API-verified — same as
  // win_prob_history, current_odds, bookmaker_odds), NOT 0–100. The old `/ 100`
  // here made the headline fallback show ~1% while the chart tooltip (OddsChart
  // multiplies the same field by 100) correctly showed ~81% — the reported
  // tooltip-vs-headline mismatch. It fired whenever win_prob_history was empty
  // (any live sport without an ESPN/stat win-prob source, e.g. cricket/soccer).
  // #3459 — SAY WHEN THERE IS NO READING, instead of inventing a pick-'em one.
  //
  // The `?? 0.5` on the end of this cascade was load-bearing for layout (the
  // point's prob fields are not nullable) and a lie for meaning: on production
  // event 15305801 — Ram/Salisbury v Arribage/Olivetti, US Open doubles, LIVE,
  // with **0 rows in `futures_markets` and 0 in `odds_snapshots`** — all three
  // sources were absent, this returned 0.5, and `GamePlayCard` printed
  // "Ram/Salisbury 50% — Arribage/Olivetti 50%" three inches under a chart
  // correctly reading "Tracking will begin when odds are available".
  //
  // The hero escaped only because `resolveProbability` sniffed for the literal
  // `lastChartPoint.homeProb !== 0.5` — which also threw away every market that
  // is honestly dead even. Absence and evenness cannot share a value domain;
  // `probKnown` gives absence its own, so no consumer has to guess again.
  const measuredHomeProb =
    latestBlendPoint(historyData.aggregate_line) ??
    lastWp?.home_probability ??
    lastHist?.home_probability ??
    null;
  const probKnown = measuredHomeProb !== null;
  const homeProb = measuredHomeProb ?? 0.5;

  // L2-163 Item 3 — moments readout scaffold. Surface the most recent scoring
  // play so the below-chart readout (GamePlayCard) shows the CURRENT moment at
  // rest, not just a static win-prob line: for a live game that is the play that
  // just happened; for a settled game it is "what hit" last. On-chart dots wait
  // for #1168 — this is the socket the moments engine plugs into. Scored by
  // timestamp so an out-of-order plays array can't surface a stale play.
  const plays = historyData.scoring_plays;
  let latestPlay: ScoringPlay | null = null;
  if (plays && plays.length > 0) {
    for (const play of plays) {
      if (!play?.timestamp) continue;
      if (!latestPlay || play.timestamp > latestPlay.timestamp) {
        latestPlay = play;
      }
    }
  }

  // #4571 — THE SCORE'S CLOCK FOLLOWS ITS PROVENANCE, NOT ITS POSITION.
  //
  // The two score fields below each fall through `lastEspn -> event row`, and
  // `timestamp` above falls through `lastEspn -> lastWp -> lastHist`. Those are
  // INDEPENDENT cascades, so on an event with no ESPN rows the score is the
  // event row's while `timestamp` is a price snapshot's — live/146 proved it on
  // production event 15298476 (0 espn_history rows, score 2 off the event row,
  // `timestamp` = Kalshi's price clock). Returning `timestamp` as the score's
  // age would re-commit #4571's own defect in a form that reads as precise, so
  // each side is dated by the arm that actually supplied it.
  //
  // A side that resolved to `null` renders no number and therefore contributes
  // no age. A side that rendered a number whose arm has no stamp makes the whole
  // pair undatable — an absence must not be dated (#3473), and a pair is only as
  // current as its oldest half, the same rule `heroFreshness` applies one level
  // up. Note the arm test is `!= null` on the ESPN VALUE, not on `lastEspn`
  // itself: an ESPN row present but holding a null score falls through to the
  // event row, and its stamp must fall through with it.
  //
  // AND THE ARM IS CALLED `"history"`, NOT `"espn"`, DELIBERATELY. `espn_history`
  // is not all ESPN: `routes/events.py:15649` appends MLB Stats API and
  // `stat_model` rows into it with no origin key, shaped like ESPN rows, then
  // sorts by timestamp — and the supplement is dense where ESPN is sparse, so on
  // 8 of 15 recent scoring MLB events the LAST row (the one read here) is a
  // supplement (live/147, measured). The stamp stays correct, because each row
  // carries its own timestamp; it is only a LABEL naming ESPN that would lie. So
  // the field says which array the number came out of, which is all this layer
  // can honestly know, and `scoreFrom` is not an attribution — see its docstring.
  // #5521 — AND BETWEEN THE TWO OBSERVATION SERIES, THE NEWER ONE SPEAKS.
  //
  // `espn_history` was the only series this cascade read. `score_history` — the
  // StatPal `score_snapshots` series, in the SAME payload — was never consulted
  // at all, and a sibling helper in this file (`computeRealStartTime`, removed
  // in #7901) documented its own priority as *"StatPal score_history > ESPN >
  // win_prob"*. One helper in this file called that array the most authoritative
  // and the one picking the number a reader sees did not look at it.
  //
  // #7901 POSTSCRIPT: that sibling never implemented the priority it documented
  // — it took a flat `min` over all three arrays, so the ordering the comment
  // above leans on was prose only. The lesson survives its source and gets
  // sharper: a stated priority is a claim about code, and this one was false in
  // the same file that cited it.
  //
  // Production 15304937 (Athletics v Mariners, MLB, 06:02Z): `espn_history[-1]`
  // at 04:50:54Z said 4–5, `score_history[-1]` at 04:55:24Z said 6–5, and the
  // event row said 6–5. The hero printed 4–5 for over an hour — the WRONG TEAM
  // AHEAD on a game it was calling live — while "Runs pace" three inches below
  // read `11 scored` off the other arm. The page held its own refutation twice.
  //
  // So the pick is by AGE, not by arm. `page.tsx:622` states the old premise out
  // loud — *"prefer latest ESPN history (more frequent updates)"* — which is an
  // empirical claim about relative freshness that nothing re-checked at runtime.
  const scoreSnaps = historyData.score_history;
  const lastScoreSnap = scoreSnaps?.length ? scoreSnaps[scoreSnaps.length - 1] : null;
  const espnStamp = lastEspn?.timestamp || null;
  const snapStamp = lastScoreSnap?.timestamp || null;
  // #7315 — the third argument is what stops a write days after full time from
  // outranking a point that is the last reading of the game. It comes out of
  // the same payload, so no caller changes.
  const snapWins = scoreSnapshotOutranksHistory(
    snapStamp,
    espnStamp,
    historyData.completed_at,
  );

  const homeHist = pickHistorySide(
    lastEspn?.home_score,
    espnStamp,
    lastScoreSnap?.home_score,
    snapStamp,
    snapWins,
  );
  const awayHist = pickHistorySide(
    lastEspn?.away_score,
    espnStamp,
    lastScoreSnap?.away_score,
    snapStamp,
    snapWins,
  );

  const resolvedHomeScore = homeHist.value ?? homeScore ?? null;
  const resolvedAwayScore = awayHist.value ?? awayScore ?? null;
  const eventStamp = eventScoreObservedAt ?? null;

  // `period` and `clock` below stay ESPN's, because `score_history` carries
  // neither. A snapshot-supplied score can therefore sit beside an ESPN period,
  // which is the honest shape: each field is the newest reading OF THAT FIELD.
  const arms: Array<{ from: "history" | "event"; stamp: string | null }> = [];
  if (resolvedHomeScore !== null) {
    const fromHistory = homeHist.value !== null;
    arms.push({ from: fromHistory ? "history" : "event", stamp: fromHistory ? homeHist.stamp : eventStamp });
  }
  if (resolvedAwayScore !== null) {
    const fromHistory = awayHist.value !== null;
    arms.push({ from: fromHistory ? "history" : "event", stamp: fromHistory ? awayHist.stamp : eventStamp });
  }

  let scoreStamp: string | null = null;
  let scoreFrom: "history" | "event" | "mixed" | null = null;
  if (arms.length > 0) {
    scoreFrom = arms.every((a) => a.from === arms[0].from) ? arms[0].from : "mixed";
    let oldestMs = Infinity;
    let datable = true;
    for (const arm of arms) {
      const ms = arm.stamp ? Date.parse(arm.stamp) : NaN;
      if (Number.isNaN(ms)) {
        datable = false;
        break;
      }
      if (ms < oldestMs) {
        oldestMs = ms;
        scoreStamp = arm.stamp;
      }
    }
    if (!datable) scoreStamp = null;
  }

  return {
    timestamp:
      lastEspn?.timestamp ||
      lastWp?.timestamp ||
      lastHist?.timestamp ||
      "",
    homeProb,
    awayProb: 1 - homeProb,
    probKnown,
    homeScore: resolvedHomeScore,
    awayScore: resolvedAwayScore,
    period: lastEspn?.period?.toString() ?? null,
    clock: lastEspn?.game_clock ?? null,
    scoringPlay: latestPlay,
    scoreStamp,
    scoreFrom,
  };
}
