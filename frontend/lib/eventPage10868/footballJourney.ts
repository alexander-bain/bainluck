/**
 * #10868 — THE FOOTBALL HEADLINE AND WIN HISTORY (web), on the accepted hockey
 * journey foundation.
 *
 * PILLARS: FORMATTING / TRUTH / DISCOVER. SHIP: on the six NFL routes (`nfl`,
 * `nfl-live`, `nfl-stories`, `nfl-team-stats`, `nfl-combined`, `nfl-replay`) a
 * reader compares both teams' earlier and current win chances, the score and
 * the projected final with the two-team win history, and after the final
 * compares the actual result with the pregame forecast. Headline and history
 * ONLY: props, stories and full-reader destinations are not built here.
 *
 * Every value is the output of the web authority that owns it, reached through
 * the hockey journey's exported pieces, or that slot's own absence words:
 *
 *   - phase           `hockeyJourneyPhase` (status only), behind an explicit
 *                     applies check: NFL only (`nflCardsApply`), a status in the
 *                     `EventStatus` vocabulary, no venue void (`isVenueVoided`)
 *                     and no authority stoppage word (`authorityStoppageLabel`).
 *                     A cancelled, void, unknown or non-NFL row is REFUSED, never
 *                     quietly drawn as "before".
 *   - state words     `footballJourneyState`, composing eventState's own answers
 *                     ahead of `hockeyJourneyState` (whose suspended and
 *                     past-kickoff words differ from production's):
 *                     `hasNoReportedResult` (with the served
 *                     `started_without_result`, #9634) → the venue's grade
 *                     (`venueSettledSummary`) or `suspendedSummary` ("No result
 *                     reported", never a raw old period, never "Play suspended"),
 *                     and on such a row NO forecast and NO forecast control (the
 *                     event page's own suppression); a `scheduled` row past its
 *                     clock that the server does not hold (`serverHeldPastKickoff`)
 *                     → `startBadgeLabel`'s "Started", never a "Before game · …
 *                     start" cue. Nothing is settled from time. Chances, known
 *                     scores and the own history stay where their authority
 *                     admits them.
 *   - current chance  `heroPair` — the hero's own pair and integers, titled by
 *                     its own currentness role (Current chance / Last recorded
 *                     chance / Opening line). HOST CONTRACT: `host.hero` must be
 *                     the hero pair page.tsx resolved for THIS event
 *                     (`resolveProbability(event, …)`) and `probabilityObservedAt`
 *                     its `acceptedPriceClock`. The pair carries no event id, so
 *                     this file cannot check it; a host that passes another
 *                     event's pair breaks the screen's truth.
 *   - earlier chance  `pregamePair` (`prematchReading`). Its role stays visible in
 *                     the column title, from `pregamePair`'s own decision (its
 *                     provenance word): a served pre-match reading is "Pregame
 *                     chance", the `opening_odds` fallback is "Opened chance".
 *                     The two are different source readings and never relabelled.
 *   - score           `goalSlots` (the event's scores, dated by
 *                     `score_observed_at`), said in points.
 *   - forecasts       before: `beforeForecast` (`eventPageProjectedPair` under the
 *                     hero line's gates); during play: `liveForecast` (the
 *                     producer's admitted in-play pair, `liveCardProjectedFinal`)
 *                     and, beneath it, `livePregameComparison` with the top-level
 *                     `pregame_projection`; after the final: `finalForecast`
 *                     (`finalForecastComparison`). All printed at their own
 *                     precision (`formatPoints`), said in points. A refused
 *                     earlier forecast never removes a valid current one.
 *   - vs forecast     after the final only, and only on `finalForecastComparison`'s
 *                     positive admission: the team's actual final minus the RAW
 *                     `pregame_projection` half for the same team (never the
 *                     card-rounded pair, never `current_odds`). Magnitude through
 *                     `formatPoints` and an explicit sign ("+1.2", "−3"), the
 *                     points unit visible in the column title "vs forecast
 *                     (pts)" and spoken in full; exact zero prints "0", said "At
 *                     forecast"; a nonzero difference that prints as 0.0 says
 *                     "<0.1 above/below" — native
 *                     `FinalComparisonHeadline9483.differenceCell`. No colour,
 *                     winner, hit or miss is read from it.
 *   - withdrawn claim the host's REQUIRED `liveClaimUnbacked` (the page's own
 *                     `pageLiveClaimIsUnbacked`), OR'd with `hasNoReportedResult`
 *                     exactly as page.tsx:753-759 builds `isSuspended`: the
 *                     state says "No result reported", the chance keeps its
 *                     figures as "Last recorded chance" (never "Current
 *                     chance"; an "Opening line" role stays), and the current
 *                     forecast, the earlier forecast and the forecast control
 *                     are withdrawn. Score, own history and dated observations
 *                     stay.
 *   - result          `servedOutcome` → `MATRIX_WORDS.won` / `lost`.
 *   - history         `hockeyJourneyHistory`, unchanged, over the held `/history`
 *                     body — ONLY when its `event_id` is exactly this event's id.
 *                     OWNERSHIP IS DECIDED ONCE (`ownFootballHistory`), up front,
 *                     and only the proven `OwnFootballHistory | null` reaches any
 *                     reader: the chart AND the before-the-start forecast, whose
 *                     prediction-market fallback reads the body's
 *                     `pm_spread_data.projected_final`. A foreign body supplies
 *                     nothing: the chart says "History unavailable", the forecast
 *                     falls to the game's own sportsbook pair or its absence
 *                     words, and no control points at either. No name or time
 *                     matching.
 *
 * Provenance (sources and clocks) moves into the section's Info disclosure;
 * every comparison role and every absence stays in the headline itself.
 *
 * CONTROLS. `forecastAction` / `historyAction` say only that a meaningful
 * admitted destination exists (an admitted forecast; a drawn history). The
 * component offers a control only when the host ALSO passes a callback. The host
 * owns the full reader, Back, focus and held context: a callback is not reader
 * parity.
 *
 * PURE: no fetch, subscription, timer or state. `nowMs` is a parameter.
 */

import type { EventDetailResponse, EventHistoryResponse, EventStatus } from "@/lib/types";
import { livePregameComparison } from "@/lib/livePregameComparison";
import { projectedFinalLabel, type SportsbookProjectionFields } from "@/lib/projectedFinalPair";
import {
  authorityStoppageDescription,
  hasNoReportedResult,
  isFinishedStatus,
  isVenueVoided,
  serverHeldPastKickoff,
  startBadgeLabel,
  suspendedSummary,
  SUSPENDED_DESCRIPTION,
  VENUE_CLOSED_NO_WINNER_LABEL,
  VENUE_SETTLED_DESCRIPTION,
  venueSettledSummary,
} from "@/lib/eventState";
import { authorityStoppageLabel } from "@/lib/gameTimeLabel";
import { formatPoints, nflCardsApply } from "@/lib/nflEventCardDeck";
import { teamShortNames } from "@/lib/teamShortName";
import { teamTextColor } from "@/lib/teamColors";
import { absentSlot, hockeyJourneyPhase, parseMs, servedOutcome } from "./hockeyJourneyCore";
import {
  MATRIX_WORDS,
  PAGE_WORDS,
  beforeForecast,
  finalForecast,
  goalSlots,
  heroPair,
  hockeyJourneyState,
  liveForecast,
  matrixProvenanceLine,
  pregamePair,
  type HockeyJourneyHost,
} from "./hockeyJourney";
import { hockeyJourneyHistory, unavailableHistory } from "./hockeyJourneyHistory";
import type {
  HockeyJourneyColumn,
  HockeyJourneyHeadline,
  HockeyJourneyHistory,
  HockeyJourneyMatrix,
  HockeyJourneyPhase,
  HockeyJourneySlot,
} from "./hockeyJourneyTypes";

/**
 * The football host contract: the hockey host plus the event page's OWN answer to
 * "is the live claim unbacked" — `pageLiveClaimIsUnbacked` (lib/eventLivePush.ts:349),
 * computed by its existing owner on page.tsx (:723-729, from `hasStarted`,
 * `live_probability_pinned` and the freshest source's age). REQUIRED and never
 * defaulted: this file does not re-derive source ages or the pinned policy and
 * fetches nothing, so a host that cannot supply the owner's answer cannot build
 * the section. Composed exactly as page.tsx composes it (see `footballJourneyState`).
 * The app mount that supplies it is NOT built here.
 */
export interface FootballJourneyHost extends HockeyJourneyHost {
  liveClaimUnbacked: boolean;
}

/** The football words this section adds; everything else is the foundation's. */
export const FOOTBALL_WORDS = {
  /** The earlier column over the `opening_odds` fallback (native "Opened" + " chance"). */
  openedChance: "Opened chance",
  score: "Score",
  finalScore: "Final score",
  /** The column carries the unit, so each difference prints as a compact signed figure. */
  vsForecast: "vs forecast (pts)",
  point: "point",
  points: "points",
  above: "above",
  below: "below",
  atForecast: "At forecast",
  /** A nonzero difference too small for one decimal (native `differenceCell`). */
  underOneTenth: "<0.1",
  differenceBasis: "final score minus the pregame forecast, in points",
  spokenLabel: "Football win chances, score and forecast",
  openForecast: "Open forecast comparison",
  openHistory: "Open win history",
} as const;

/** The section's view model when it applies. */
export interface FootballJourneyEarlierForecast {
  /** "Pregame forecast". */
  title: string;
  home: HockeyJourneySlot;
  away: HockeyJourneySlot;
}

export interface FootballJourneyAction {
  label: string;
}

export interface FootballJourneyView {
  kind: "journey";
  eventId: number;
  phase: HockeyJourneyPhase;
  headline: HockeyJourneyHeadline;
  /** During play only, under an admitted current forecast. Shown visibly, not in Info. */
  earlierForecast: FootballJourneyEarlierForecast | null;
  history: HockeyJourneyHistory;
  /** True when a held `/history` body named another event and was not drawn. */
  historyForeign: boolean;
  info: { label: string; lines: string[] };
  /** An admitted forecast exists to open; the component still needs the host's callback. */
  forecastAction: FootballJourneyAction | null;
  /** A drawn history exists to open; the component still needs the host's callback. */
  historyAction: FootballJourneyAction | null;
}

/** Why the section does not draw a journey for this row. */
export type FootballJourneyRefusalReason = "notFootball" | "unknownState" | "stopped" | "voided";

export interface FootballJourneyRefusal {
  kind: "refused";
  reason: FootballJourneyRefusalReason;
  /** The words to show instead (null for a non-NFL row, which the host should not mount). */
  words: string | null;
  /** The authority's own word for a stopped or voided game, when it gave one. */
  state: string | null;
}

export type FootballJourneyModel = FootballJourneyView | FootballJourneyRefusal;

export interface FootballJourneyInput {
  /** The event the page already holds. */
  event: EventDetailResponse;
  /** The `/history` body the page already holds; null/undefined when none is held. */
  history: EventHistoryResponse | null | undefined;
  host: FootballJourneyHost;
}

// ─── Applies, and the phase ───────────────────────────────────────────────

/** `EventStatus`, the whole lifecycle vocabulary (types.ts). Anything else is unknown. */
const LIFECYCLE: readonly EventStatus[] = ["scheduled", "live", "suspended", "completed", "closed"];

function refused(reason: FootballJourneyRefusalReason, state: string | null): FootballJourneyRefusal {
  return {
    kind: "refused",
    reason,
    words: reason === "notFootball" ? null : PAGE_WORDS.matrixUnavailable,
    state,
  };
}

/**
 * Whether the section serves this row, and in which phase. `hockeyJourneyPhase`
 * answers "before" for anything not finished or live, so it is asked only after
 * the row is known to be an NFL game in a known, unstopped, unvoided state:
 *
 *   - not NFL (`nflCardsApply`)                         → refused, no words
 *   - a status outside `EventStatus`                    → refused ("unknownState")
 *   - the venue closed it with no winner (`isVenueVoided`) → refused, "Ended · no winner"
 *   - a scheduled or suspended row whose authority says
 *     Postponed / Canceled (`authorityStoppageLabel`)     → refused, that word
 */
export function footballJourneyApplicability(
  event: EventDetailResponse,
  nowMs: number,
): { kind: "applies"; phase: HockeyJourneyPhase } | FootballJourneyRefusal {
  if (!nflCardsApply(event.sport)) return refused("notFootball", null);
  const status: string | null | undefined = event.status;
  if (typeof status !== "string" || !(LIFECYCLE as readonly string[]).includes(status)) {
    return refused("unknownState", null);
  }
  if (isVenueVoided(event.venue_settled, event.venue_closed_no_winner)) {
    return refused("voided", VENUE_CLOSED_NO_WINNER_LABEL);
  }
  if (!isFinishedStatus(status) && status !== "live") {
    const stoppage = authorityStoppageLabel(event.espn?.period);
    if (stoppage) return refused("stopped", stoppage);
  }
  return { kind: "applies", phase: hockeyJourneyPhase(event, nowMs) };
}

/** Whether the host should mount the section at all: NFL rows only. */
export function footballJourneyApplies(sportKey: string | null | undefined): boolean {
  return nflCardsApply(sportKey);
}

// ─── Whose history this is ───────────────────────────────────────────────

declare const OWN_HISTORY: unique symbol;

/**
 * A held `/history` body PROVEN to be this event's: its `event_id` is exactly
 * `event.id`. Only {@link ownFootballHistory} makes one. Every reader of the body
 * in this file — the chart, and the before-the-start forecast's
 * prediction-market ladder (`pm_spread_data.projected_final`, through
 * `beforeForecast` → `eventPageProjectedPair`) — takes this type, never the raw
 * response, so a foreign body cannot reach any of them.
 */
export type OwnFootballHistory = EventHistoryResponse & { readonly [OWN_HISTORY]: true };

export interface FootballHistoryOwnership {
  /** The body, when it is this event's; otherwise null. */
  own: OwnFootballHistory | null;
  /** A body was held and it named another event (or no event at all). */
  foreign: boolean;
}

/** The one ownership check: exact `event_id`, no name or time matching. */
export function ownFootballHistory(
  history: EventHistoryResponse | null | undefined,
  event: EventDetailResponse,
): FootballHistoryOwnership {
  if (!history) return { own: null, foreign: false };
  if (typeof history.event_id !== "number" || history.event_id !== event.id) return { own: null, foreign: true };
  return { own: history as OwnFootballHistory, foreign: false };
}

// ─── The state words ─────────────────────────────────────────────────────

export interface FootballJourneyState {
  /** The state line the section prints. */
  state: string;
  /** A visible second line (the day), or null. */
  context: string | null;
  /** The sentence behind the state, for Info only (its source, or the longer description), or null. */
  about: string | null;
  /**
   * `hasNoReportedResult` with the served `started_without_result`: the game
   * should have happened and nothing reported how it went. Such a row offers no
   * forecast and no forecast control, as the event page suppresses its own.
   */
  noReportedResult: boolean;
}

/**
 * The state words, from eventState's own answers first and `hockeyJourneyState`
 * only where those leave it to the clock-free hockey words:
 *
 *   - `hasNoReportedResult(status, commence_time, now, started_without_result)`
 *     on a row that is not finished → the venue's grade (`venueSettledSummary`)
 *     or `suspendedSummary(away, home, "away-home", authorityStoppageLabel(...))`
 *     — "No result reported", with the last score when both sides have one, in
 *     the SECTION's surface order (#2786: the caller passes its own order), which
 *     presents away first (`FOOTBALL_DISPLAY_ORDER` in FootballJourneySection.tsx).
 *     The venue's named result is printed verbatim. Never a raw period from a source that went
 *     quiet, never "Play suspended" (status `suspended` can be a silent source,
 *     not a pause). Info carries `SUSPENDED_DESCRIPTION`.
 *   - a `scheduled` row past its clock, not held by the server
 *     (`serverHeldPastKickoff`, which honours a served `false` past the grace and
 *     `authority_not_started` inside it), with a dated start → `startBadgeLabel`
 *     ("Started") and the day, not "Before game · … start". A held row keeps the
 *     before-game words, and a row the clock alone calls over-due but the server
 *     answered `false` is NOT "No result reported" (#9634).
 *   - otherwise `hockeyJourneyState`; during play its "Game state from ESPN"
 *     source moves to Info.
 *
 * Nothing here settles a game from time; `completed`/`closed` stay the only Final.
 */
export function footballJourneyState(
  event: EventDetailResponse,
  phase: HockeyJourneyPhase,
  nowMs: number,
  liveClaimUnbacked: boolean,
): FootballJourneyState {
  const base = hockeyJourneyState(event, phase);
  // page.tsx:753-759 — `isSuspended = hasNoReportedResult(status, commence_time, now,
  // started_without_result) || liveClaimUnbacked`, the page's ONE answer for its badge,
  // projected-final suppression and live claims. A finished status outranks it, as the
  // badge's `isFinished ?` branch does (page.tsx:2886-2888).
  const noResult =
    hasNoReportedResult(event.status, event.commence_time, nowMs, event.started_without_result) || liveClaimUnbacked;
  if (phase !== "final" && noResult) {
    // page.tsx:772-796 + 2888-2925: the venue's sentence, else `suspendedSummary` with
    // the authority's stoppage word; the badge's title sentence goes to Info.
    const settled = venueSettledSummary(event.venue_settled, event.venue_settled_result, event.venue_closed_no_winner);
    const stoppage = settled ? null : authorityStoppageLabel(event.espn?.period);
    return {
      // "away-home": the section's display order (away first), so the bare score reads as its rows do.
      state: settled ?? suspendedSummary(event.away_score, event.home_score, "away-home", stoppage),
      context: null,
      about: settled ? VENUE_SETTLED_DESCRIPTION : authorityStoppageDescription(stoppage) ?? SUSPENDED_DESCRIPTION,
      noReportedResult: true,
    };
  }
  if (phase === "before") {
    const start = parseMs(event.commence_time);
    const held = serverHeldPastKickoff(
      event.status,
      event.commence_time,
      nowMs,
      event.started_without_result,
      event.authority_not_started,
    );
    const started = start !== null && start <= nowMs && event.start_is_tbd !== true;
    return {
      state: started && !held ? startBadgeLabel(true, null, held) : base.state,
      context: base.context,
      about: null,
      noReportedResult: false,
    };
  }
  if (phase === "live") return { state: base.state, context: null, about: base.context, noReportedResult: false };
  return { state: base.state, context: base.context, about: null, noReportedResult: false };
}

// ─── Points, and the earlier chance's role ───────────────────────────────

/** A points figure said in words; the figure itself is unchanged. */
export function pointsSpoken(text: string): string {
  return text === "1" ? `1 ${FOOTBALL_WORDS.point}` : `${text} ${FOOTBALL_WORDS.points}`;
}

/** A foundation slot whose figure is a score or a forecast, said in points. Absence words stay. */
export function asPoints(slot: HockeyJourneySlot): HockeyJourneySlot {
  return slot.kind === "value" ? { kind: "value", text: slot.text, spoken: pointsSpoken(slot.text) } : slot;
}

/**
 * The earlier column's title, from `pregamePair`'s own decision: its provenance
 * begins "Pre-match" for a served pre-match reading and "Opened" for the
 * `opening_odds` fallback (hockeyJourney.ts `pregamePair`). No reading: the
 * foundation's title with its absence words.
 */
export function earlierChanceTitle(pregame: ReturnType<typeof pregamePair>): string {
  const word = pregame?.provenance?.split(" · ")[0] ?? null;
  return word === "Opened" ? FOOTBALL_WORDS.openedChance : MATRIX_WORDS.pregameChance;
}

/** A points figure at its own precision (`formatPoints`), said in points. */
export function pointsSlot(value: number): HockeyJourneySlot {
  const text = formatPoints(value);
  return { kind: "value", text, spoken: pointsSpoken(text) };
}

// ─── vs forecast (after the final) ─────────────────────────────────────────

/**
 * One team's actual final minus its RAW pregame forecast half, as native
 * `FinalComparisonHeadline9483.differenceCell` decides it. The unit is in the
 * column title ("vs forecast (pts)"), so the visible figure is compact:
 *   - exact zero prints "0", said "At forecast";
 *   - a nonzero difference whose `formatPoints` magnitude prints as zero prints
 *     "<0.1 above" / "<0.1 below" (never ±0.0), said "less than 0.1 points
 *     above/below forecast";
 *   - every other difference prints an explicit sign ("+", or the Unicode minus
 *     "−") and the `formatPoints` magnitude, said in full: "1.2 points above
 *     forecast", "1 point below forecast".
 * No colour, winner or hit/miss is decided here.
 */
export function forecastDifference(actual: number, rawForecast: number): HockeyJourneySlot {
  const W = FOOTBALL_WORDS;
  const difference = actual - rawForecast;
  if (difference === 0) return { kind: "value", text: "0", spoken: W.atForecast };
  const direction = difference > 0 ? W.above : W.below;
  const magnitude = formatPoints(Math.abs(difference));
  if (Number(magnitude) === 0) {
    return {
      kind: "value",
      text: `${W.underOneTenth} ${direction}`,
      spoken: `less than 0.1 ${W.points} ${direction} forecast`,
    };
  }
  const sign = difference > 0 ? "+" : "−";
  return {
    kind: "value",
    text: `${sign}${magnitude}`,
    spoken: `${pointsSpoken(magnitude)} ${direction} forecast`,
  };
}

// ─── The matrix, per phase ─────────────────────────────────────────────────

type Side = "home" | "away";

/**
 * CANONICAL STORAGE ORDER: home first, the hockey foundation's model order
 * (`HockeyJourneyMatrix.rows`). Every row carries its explicit `side`. This is
 * NOT the display order: the section presents away first (Design 2026-10-31,
 * native football's order) through its own presentation copies, keyed by side.
 */
const CANONICAL_ROW_ORDER: readonly [Side, Side] = ["home", "away"];

function inRowOrder<T>(make: (side: Side) => T): [T, T] {
  return [make(CANONICAL_ROW_ORDER[0]), make(CANONICAL_ROW_ORDER[1])];
}

/**
 * The hero's pair under the page's withdrawn live claim (`noReportedResult`, the
 * page's `isSuspended`, which carries `liveClaimUnbacked`): the SAME figures and
 * provenance, but "Last recorded chance" where it would say "Current chance" — a
 * fresh dated number can still be unbacked (page.tsx:737, `effectivelyLive = isLive
 * && !liveClaimUnbacked`). An "Opening line" role is kept as it is.
 */
function footballHeroPair(
  event: EventDetailResponse,
  host: FootballJourneyHost,
  claimWithdrawn: boolean,
): ReturnType<typeof heroPair> {
  const chance = heroPair(event, host);
  if (!chance || !claimWithdrawn || chance.title !== MATRIX_WORDS.currentChance) return chance;
  return { ...chance, title: MATRIX_WORDS.lastRecordedChance };
}

/**
 * The before-the-start forecast: `beforeForecast` over the OWN history only (its
 * prediction-market fallback reads that body's ladder), and none at all on a row
 * with no reported result.
 */
function footballBeforeForecast(
  event: EventDetailResponse,
  own: OwnFootballHistory | null,
  noReportedResult: boolean,
): ReturnType<typeof beforeForecast> {
  return noReportedResult ? null : beforeForecast(event, own);
}

/**
 * Before the start: the hero's chance and the projected final. INTERNAL: its
 * only caller is `buildFootballJourney`, which passes the ownership it decided
 * for this same event and the state it composed for it.
 */
function footballBeforeMatrix(
  event: EventDetailResponse,
  own: OwnFootballHistory | null,
  host: FootballJourneyHost,
  noReportedResult: boolean,
): HockeyJourneyMatrix {
  const W = MATRIX_WORDS;
  const chance = footballHeroPair(event, host, noReportedResult);
  const forecast = footballBeforeForecast(event, own, noReportedResult);
  const rows = inRowOrder((side) => ({
    side,
    values: [
      chance?.[side] ?? absentSlot(W.noChance),
      forecast
        ? asPoints(forecast[side])
        : absentSlot(noReportedResult ? W.forecastWithheld : W.noPregameForecast),
    ],
    result: null,
  }));
  return {
    phase: "before",
    columns: [
      { title: chance?.title ?? W.winChance, provenance: chance?.provenance ?? null },
      { title: projectedFinalLabel(event.sport), provenance: forecast?.provenance ?? null },
    ],
    rows,
    lead: 0,
    groups: [[0, 1]],
  };
}

/**
 * During play, the eight values: the earlier chance (its role in its title),
 * the hero's chance under its own currentness role, the score, and the admitted
 * in-play projected final.
 */
export function footballLiveMatrix(
  event: EventDetailResponse,
  host: FootballJourneyHost,
  noReportedResult: boolean,
): HockeyJourneyMatrix {
  const W = MATRIX_WORDS;
  const pregame = pregamePair(event);
  const current = footballHeroPair(event, host, noReportedResult);
  const score = goalSlots(event);
  // Withdrawn claim: no current forecast (page.tsx:1854-1866 gates the hero's projected final on `!isSuspended`).
  const projected = noReportedResult
    ? { home: absentSlot(W.forecastWithheld), away: absentSlot(W.forecastWithheld), provenance: null }
    : liveForecast(event, host.nowMs);
  const rows = inRowOrder((side) => ({
    side,
    values: [
      pregame?.[side] ?? absentSlot(W.noChance),
      current?.[side] ?? absentSlot(W.noChance),
      asPoints(score[side]),
      asPoints(projected[side]),
    ],
    result: null,
  }));
  return {
    phase: "live",
    columns: [
      { title: earlierChanceTitle(pregame), provenance: pregame?.provenance ?? null },
      { title: current?.title ?? W.lastRecordedChance, provenance: current?.provenance ?? null },
      { title: FOOTBALL_WORDS.score, provenance: score.provenance },
      { title: projectedFinalLabel(event.sport), provenance: projected.provenance },
    ],
    rows,
    lead: 1,
    groups: [
      [0, 1],
      [2, 3],
    ],
  };
}

/**
 * After the final: earlier chance → pregame forecast → actual final → vs
 * forecast, in that reading order (two labelled pairs: chance/forecast,
 * final/difference). The forecast and its difference exist only on
 * `finalForecastComparison`'s positive admission (`finalForecast`); a missing
 * or refused forecast leaves those two slots to their words and nothing else.
 */
export function footballFinalMatrix(event: EventDetailResponse): HockeyJourneyMatrix {
  const W = MATRIX_WORDS;
  const pregame = pregamePair(event);
  const forecast = finalForecast(event);
  const score = goalSlots(event);
  // Read only under the positive admission, which also proved both scores finite and >= 0.
  const projection = forecast ? event.pregame_projection ?? null : null;
  const difference = (side: Side): HockeyJourneySlot => {
    const actual = side === "home" ? event.home_score : event.away_score;
    if (!projection || typeof actual !== "number") return absentSlot(W.noPregameForecast);
    const raw = side === "home" ? projection.projected_home_score : projection.projected_away_score;
    return forecastDifference(actual, raw);
  };
  const outcome = servedOutcome(event.status, event.home_score, event.away_score, event.hero_settled_result);
  const result = (side: Side): string | null =>
    outcome === side ? W.won : outcome === "home" || outcome === "away" ? W.lost : null;
  const rows = inRowOrder((side) => ({
    side,
    values: [
      pregame?.[side] ?? absentSlot(W.noChance),
      forecast ? asPoints(forecast[side]) : absentSlot(W.noPregameForecast),
      asPoints(score[side]),
      difference(side),
    ],
    result: result(side),
  }));
  return {
    phase: "final",
    columns: [
      { title: earlierChanceTitle(pregame), provenance: pregame?.provenance ?? null },
      { title: W.pregameForecast, provenance: forecast?.provenance ?? null },
      { title: FOOTBALL_WORDS.finalScore, provenance: score.provenance },
      { title: FOOTBALL_WORDS.vsForecast, provenance: projection ? FOOTBALL_WORDS.differenceBasis : null },
    ],
    rows,
    lead: 2,
    groups: [
      [0, 1],
      [2, 3],
    ],
  };
}

// ─── The earlier forecast beneath the current one (during play) ─────────────

/**
 * During play: the retained pregame projected final, through
 * `livePregameComparison` with the top-level `pregame_projection`, beside the
 * printed current one. Null whenever it refuses — and then only this line is
 * missing: the current forecast in the matrix stays. `liveForecast` admits a
 * pair only while page.tsx's live predicate holds (status live, start passed),
 * so an admitted pair is that predicate's answer, passed on as `isLive`.
 */
export function footballEarlierForecast(
  event: EventDetailResponse,
  nowMs: number,
): { view: FootballJourneyEarlierForecast; provenance: string } | null {
  const admitted = liveForecast(event, nowMs).admitted;
  if (!admitted) return null;
  const comparison = livePregameComparison({
    sportKey: event.sport,
    status: event.status,
    isLive: true,
    commenceTime: event.commence_time,
    odds: event.current_odds as SportsbookProjectionFields | undefined,
    heroProjected: admitted,
    projection: event.pregame_projection,
  });
  if (!comparison) return null;
  const n = comparison.details.bookmakerCount;
  return {
    view: {
      title: MATRIX_WORDS.pregameForecast,
      home: pointsSlot(comparison.baseline.home),
      away: pointsSlot(comparison.baseline.away),
    },
    provenance: `${comparison.label} · ${n} ${n === 1 ? "sportsbook" : "sportsbooks"}`,
  };
}

// ─── The history ─────────────────────────────────────────────────────────

/** The hockey helper over an OWN body, or the chart's absence. INTERNAL: callers decide ownership first. */
function drawOwnHistory(
  own: OwnFootballHistory | null,
  event: EventDetailResponse,
  phase: HockeyJourneyPhase,
  nowMs: number,
): HockeyJourneyHistory {
  return own ? hockeyJourneyHistory(own, event, phase, nowMs) : unavailableHistory(event, phase);
}

/**
 * The held `/history` body through the unchanged hockey helper, only when its
 * `event_id` is exactly this event's id (`ownFootballHistory`). A body for
 * another event (or with no id to check) is not drawn: the chart reads "History
 * unavailable".
 */
export function footballJourneyHistory(
  history: EventHistoryResponse | null | undefined,
  event: EventDetailResponse,
  phase: HockeyJourneyPhase,
  nowMs: number,
): { history: HockeyJourneyHistory; foreign: boolean } {
  const { own, foreign } = ownFootballHistory(history, event);
  return { history: drawOwnHistory(own, event, phase, nowMs), foreign };
}

// ─── The headline and the whole section ──────────────────────────────────

export function footballJourneyHeadline(
  event: EventDetailResponse,
  state: FootballJourneyState,
  matrix: HockeyJourneyMatrix,
): HockeyJourneyHeadline {
  const names = teamShortNames(
    { name: event.home_team, abbreviation: event.home_team_data?.abbreviation },
    { name: event.away_team, abbreviation: event.away_team_data?.abbreviation },
    event.sport,
  );
  return {
    state: state.state,
    // Visible only; a source or a longer description goes to Info (`state.about`).
    stateContext: state.context,
    home: {
      side: "home",
      name: event.home_team,
      short: names.home && names.home !== event.home_team ? names.home : null,
      tint: teamTextColor(event.home_team_data?.primary_color) ?? null,
    },
    away: {
      side: "away",
      name: event.away_team,
      short: names.away && names.away !== event.away_team ? names.away : null,
      tint: teamTextColor(event.away_team_data?.primary_color) ?? null,
    },
    matrix,
    // The matrix does not draw this field; the section draws `earlierForecast` itself.
    historicalForecast: null,
    spokenLabel: FOOTBALL_WORDS.spokenLabel,
  };
}

/** Each column's source and clock as Info prints it; a provenance that only repeats its title says nothing. */
export function footballInfoLines(
  columns: HockeyJourneyColumn[],
  earlier: string | null,
  stateAbout: string | null,
): string[] {
  return [
    ...columns.flatMap((c) => (c.provenance && c.provenance !== c.title ? [matrixProvenanceLine(c)] : [])),
    ...(earlier ? [`${MATRIX_WORDS.pregameForecast}: ${earlier}`] : []),
    ...(stateAbout ? [stateAbout] : []),
  ];
}

/**
 * The section's view model, or why it is refused. Pure: same inputs, same
 * answer. Ownership of the held history is decided ONCE here and only the own
 * body (or null) reaches the forecast and the chart, so a foreign body changes
 * nothing but the chart's absence. A row with no reported result keeps its
 * chances, score and own history, and offers no forecast and no forecast control.
 */
export function buildFootballJourney({ event, history, host }: FootballJourneyInput): FootballJourneyModel {
  const applies = footballJourneyApplicability(event, host.nowMs);
  if (applies.kind === "refused") return applies;
  const { phase } = applies;
  const { own, foreign } = ownFootballHistory(history, event);
  const state = footballJourneyState(event, phase, host.nowMs, host.liveClaimUnbacked);
  const noResult = state.noReportedResult;
  const matrix =
    phase === "before"
      ? footballBeforeMatrix(event, own, host, noResult)
      : phase === "live"
        ? footballLiveMatrix(event, host, noResult)
        : footballFinalMatrix(event);
  const headline = footballJourneyHeadline(event, state, matrix);
  const earlier = phase === "live" && !noResult ? footballEarlierForecast(event, host.nowMs) : null;
  const drawn = drawOwnHistory(own, event, phase, host.nowMs);
  const forecastAdmitted =
    !noResult &&
    (phase === "before"
      ? footballBeforeForecast(event, own, noResult) !== null
      : phase === "live"
        ? liveForecast(event, host.nowMs).admitted !== null
        : finalForecast(event) !== null);
  const historyDrawn = drawn.domain !== null && drawn.absence === null;
  return {
    kind: "journey",
    eventId: event.id,
    phase,
    headline,
    earlierForecast: earlier?.view ?? null,
    history: drawn,
    historyForeign: foreign,
    info: {
      label: MATRIX_WORDS.aboutLabel,
      lines: footballInfoLines(matrix.columns, earlier?.provenance ?? null, state.about),
    },
    forecastAction: forecastAdmitted ? { label: FOOTBALL_WORDS.openForecast } : null,
    historyAction: historyDrawn ? { label: FOOTBALL_WORDS.openHistory } : null,
  };
}
