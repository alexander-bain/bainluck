/**
 * #10868 — THE MLB GAME SCREEN (web), CORE CHECKPOINT: THE HEADLINE, THE
 * TWO-TEAM HISTORY AND ALL PROPS.
 *
 * PILLARS: FORMATTING / TRUTH / DISCOVER. SHIP: a baseball fan's web event page
 * shows both teams' win chances, the score the page displays and the projected
 * final the page already admits together, with the two-team win history and
 * every original prop's exact Details.
 *
 * THIS IS NOT THE FULL MLB PAGE. Held, not dropped (Design admission
 * 2026-10-31): the live home-run and strikeout player cards
 * (`mlbGamePlayers.ts`, `MlbGameStories.tsx`), the five story families (run
 * totals, home runs, strikeouts, extra innings, series), frozen milestone
 * Details, inning guides, the pregame and final forecast comparisons, the
 * full-size readers and every production binding. See MOUNT-MLB.md.
 *
 * The web port of native `BaseballGamePageAdapter10868` (headline),
 * `BaseballHistoryAdapter10868` (history) and `BaseballOriginalsAdapter10868`
 * (All props), composed from the accepted hockey foundation, READ-ONLY. Every
 * value is the output of the web owner that already decides it, or that slot's
 * own absence words:
 *
 *   - applies         `baseball_mlb` only, and only while `sportPricesADraw`
 *                     says the winner market prices no draw (two competitors);
 *                     a status outside `EventStatus`, a venue void
 *                     (`isVenueVoided`) or an authority stoppage word
 *                     (`authorityStoppageLabel`) is REFUSED with its words,
 *                     never drawn as "before" (football's applicability rule).
 *   - phase           `hockeyJourneyPhase` — status only, the rule native
 *                     `BaseballGamePageAdapter10868.phase` states.
 *   - state words     native baseball's words ("Before first pitch", the inning
 *                     with "Game state from ESPN", "Final"), composed from the
 *                     web owners in the order `footballJourneyState` uses:
 *                     `hasNoReportedResult` with the served
 *                     `started_without_result`, OR'd with the host's REQUIRED
 *                     `liveClaimUnbacked` exactly as page.tsx:753-759 builds
 *                     `isSuspended` → the venue's own summary
 *                     (`venueSettledSummary`) or `suspendedSummary` over the
 *                     DISPLAYED score pair, away first; a `scheduled` row past
 *                     its clock that the server does not hold
 *                     (`serverHeldPastKickoff`) → `startBadgeLabel`'s "Started";
 *                     the inning through `formatLiveClockLabel(…, sport)`, which
 *                     drops baseball's constant `0:00` (#6684). A placeholder
 *                     start (`start_is_tbd`) prints no day: the page's own
 *                     `formatTbdStartLabel` owns a placeholder's UTC day (#4344).
 *   - current chance  `heroPair` — the hero's own resolved pair and integers
 *                     (HOST: page.tsx `resolvedProbability`, its
 *                     `acceptedPriceClock`), titled by `heroReadingIsCurrent`
 *                     with the host's REQUIRED `deliveryInterrupted`; under a
 *                     withdrawn claim (`noReportedResult`) "Current chance"
 *                     reads "Last recorded chance" (football's rule). A game the
 *                     venue has settled while not finished prints NO chance
 *                     (native `EventState.showsVenueSettledVerdict`, mirrored:
 *                     web exports no such predicate). Never read after the
 *                     final: the final detail's hero is the settled 0 / 1.
 *   - pregame chance  `pregamePair` (`prematchReading`) with its served integers.
 *   - runs            the page's DISPLAYED pair (HOST: `bestHomeScore` /
 *                     `bestAwayScore`, its clock `renderedScoreStamp`, null under
 *                     the stoppage filler `heroScoreIsStoppageFiller`) — never
 *                     the raw event row, which can lag it (#8278). There is no
 *                     score arbitration here. Said in `sportVocab`'s unit words.
 *   - projected final D1 = B: the host's `heroProjectedFinal` (page.tsx ~:1872)
 *                     passed through UNCHANGED — no recalculation, rounding, or
 *                     gate of its own, none relaxed — titled
 *                     `projectedFinalLabel`, printed beside the SAME displayed
 *                     score its reachability gate was checked against. Null is
 *                     honest absence ("Projected final unavailable"); under the
 *                     page's own `isSuspended` (this file's `noReportedResult`)
 *                     the page nulls it, said "… for this game state". After the
 *                     final it is never read: the page's gate excludes
 *                     completed/closed, and a final is not a forecast. The
 *                     final's column names what is missing, "Pregame projected
 *                     final", and says "Unavailable": no pregame forecast is
 *                     held for this game, and none is synthesized from history.
 *   - result          `servedOutcome` → "Won" / "Lost", with the displayed pair
 *                     as its score fallback, so Won/Lost never disagrees with
 *                     the final runs shown. Never a chance; baseball has no draw.
 *   - history         `hockeyJourneyHistory` (H2) UNCHANGED over the held
 *                     `/history` body, only when its `event_id` is exactly this
 *                     event's (`ownHockeyHistory`): its gap, clock and
 *                     complement disclosures are H2's. H2 admits no baseball
 *                     half-inning label as a period guide, so no inning guide is
 *                     drawn (held: OB-3); served scoring plays draw at their
 *                     served times.
 *   - All props       `hockeyJourneyOriginals` (H4) UNCHANGED over the held
 *                     `/game-markets` body, only when its `event_id` is exactly
 *                     this event's (`ownHockeyMarkets`), with native
 *                     `BaseballOriginalsAdapter10868`'s scope and its three word
 *                     changes; every reading, grade, id and Details row is H4's.
 *   - names / tints   `teamShortNames`, `teamTextColor`.
 *
 * DISPLAY ORDER: the model is in canonical storage order (home first, every row
 * and series tagged with its `side`); `MlbGamePage` presents AWAY FIRST (D2)
 * through `inDisplayOrder`, picking by side.
 *
 * PURE: no fetch, subscription, SWR key, timer, memo or state; `nowMs` is a
 * parameter. Recompute it on every render from the values the page holds.
 */

import type { GameMarketsResponse } from "@/lib/api";
import type { EventDetailResponse, EventHistoryResponse, EventStatus } from "@/lib/types";
import { sportPricesADraw } from "@/lib/drawPricedWinner";
import { projectedFinalLabel } from "@/lib/projectedFinalPair";
import { sportVocab } from "@/lib/marketMapUtils";
import { authorityStoppageLabel, formatLiveClockLabel } from "@/lib/gameTimeLabel";
import {
  hasNoReportedResult,
  isFinishedStatus,
  isVenueVoided,
  serverHeldPastKickoff,
  startBadgeLabel,
  suspendedSummary,
  VENUE_CLOSED_NO_WINNER_LABEL,
  venueSettledSummary,
} from "@/lib/eventState";
import { teamShortNames } from "@/lib/teamShortName";
import { teamTextColor } from "@/lib/teamColors";
import {
  absentSlot,
  clockWords,
  dayWords,
  hasStartedByClock,
  hockeyJourneyPhase,
  parseMs,
  servedOutcome,
  timeWords,
} from "./hockeyJourneyCore";
import {
  MATRIX_WORDS,
  PAGE_WORDS,
  allPropsLabel,
  heroPair,
  pregamePair,
  type HockeyJourneyHeroPair,
} from "./hockeyJourney";
import { hockeyJourneyHistory, ownHockeyHistory } from "./hockeyJourneyHistory";
import {
  CONTRIBUTION_WORDS,
  ORIGINALS_WORDS,
  hockeyJourneyOriginals,
  ownHockeyMarkets,
  type HockeyJourneyOriginal,
  type HockeyJourneyOriginalReading,
  type HockeyJourneyOriginals,
} from "./hockeyJourneyProps";
import type {
  HockeyJourneyHeadline,
  HockeyJourneyHistory,
  HockeyJourneyMatrix,
  HockeyJourneyPhase,
  HockeyJourneySide,
  HockeyJourneySlot,
} from "./hockeyJourneyTypes";

// ─── Words ─────────────────────────────────────────────────────────────────

/**
 * Native `BaseballGamePageAdapter10868.Words`, where they differ from the
 * foundation's `MATRIX_WORDS` (whose "Win chance", "Current chance", "Last
 * recorded chance", "Pregame chance", "Won", "Lost" and "Game state from ESPN"
 * are the same strings and are used as they are).
 */
export const MLB_WORDS = {
  runs: "Runs",
  finalRuns: "Final runs",
  winChanceUnavailable: "Win chance unavailable",
  pregameChanceUnavailable: "Pregame chance unavailable",
  scoreUnavailable: "Score unavailable",
  beforeFirstPitch: "Before first pitch",
  firstPitch: "First pitch",
  firstPitchToBeAnnounced: "First pitch time to be announced",
  live: "Live",
  inningUnavailable: "Inning unavailable",
  final: "Final",
  scoreObserved: "Score observed",
  finalScore: "Final score",
  projectionUnavailable: "Projected final unavailable",
  projectionWithheld: "Projected final unavailable for this game state",
  /** After the final only: the missing pregame reference, named, and its absence. */
  pregameProjectedFinal: "Pregame projected final",
  unavailable: "Unavailable",
  spokenLabel: "Baseball win chances and runs",
  /** The accessible name of a refused section (its state and words stay its content). */
  refusedLabel: "Baseball game status",
} as const;

/** Native `BaseballOriginalsAdapter10868.Words` that differ from H4's. */
export const MLB_ORIGINALS_WORDS = {
  emptyWords: "No original props recorded for this game",
  pregameUnavailable: "Pregame chance unavailable",
  inGameUnavailable: "In-game chance unavailable",
} as const;

// ─── The host contract ─────────────────────────────────────────────────────

/** The score pair the page DISPLAYS (page.tsx ~:1496-1502, ~:1940). */
export interface MlbDisplayedScore {
  /** `bestHomeScore`. */
  home: number | null;
  /** `bestAwayScore`. */
  away: number | null;
  /** `renderedScoreStamp`: the displayed pair's own observation clock, or null. */
  observedAt: string | null;
}

/** `heroProjectedFinal` (page.tsx ~:1872): the hero's own rounded pair after all of its gates. */
export interface MlbProjectedFinal {
  home: number;
  away: number;
}

/**
 * What the host already holds, passed in unchanged. Every key is REQUIRED and
 * none is defaulted here: a host that cannot supply the owner's answer cannot
 * build the section (MOUNT-MLB.md records the unpaid bindings).
 */
export interface MlbGameHost {
  nowMs: number;
  /** page.tsx `resolvedProbability` for THIS event (~:1946), or null before it resolves. */
  hero: HockeyJourneyHeroPair | null;
  /** page.tsx `acceptedPriceClock` (~:1984). Null is undated: "last recorded", never "current". */
  probabilityObservedAt: string | null;
  /** The page's interrupted-delivery answer. REQUIRED, never defaulted (OB-8: the page names no predicate yet). */
  deliveryInterrupted: boolean;
  /** page.tsx `liveClaimUnbacked` (`pageLiveClaimIsUnbacked`, ~:723). */
  liveClaimUnbacked: boolean;
  /** The displayed pair; null when the page draws no score (no pair, or `heroScoreIsStoppageFiller`). */
  score: MlbDisplayedScore | null;
  /** page.tsx `heroProjectedFinal`, unchanged; null is honest absence. */
  projectedFinal: MlbProjectedFinal | null;
}

export interface MlbGameInput {
  /** The event the page already holds (`["event", id]`). */
  event: EventDetailResponse;
  /** The `/history` body the page already holds; used only when its `event_id` is exactly `event.id`. */
  history: EventHistoryResponse | null | undefined;
  /** The page's `gameMarkets` memo (~:1403); used only when its `event_id` is exactly `event.id`. */
  gameMarkets: GameMarketsResponse | null | undefined;
  host: MlbGameHost;
}

// ─── The view ──────────────────────────────────────────────────────────────

export interface MlbGameView {
  kind: "game";
  eventId: number;
  phase: HockeyJourneyPhase;
  /** `mlb:<event.id>:<phase>` — native `BaseballPageInputAdapter10868.scope`. Changes only with the event or phase. */
  scope: string;
  headline: HockeyJourneyHeadline;
  history: HockeyJourneyHistory;
  /** A `/history` body was held and named another event (or none): not drawn. */
  historyForeign: boolean;
  /** All props, scope `mlb:<event.id>:<phase>:originals`. */
  originals: HockeyJourneyOriginals;
  /** A `/game-markets` body was held and named another event (or none): nothing listed. */
  marketsForeign: boolean;
  /** "All 41 original outcomes"; null when none. */
  allPropsLabel: string | null;
}

export type MlbGameRefusalReason = "notBaseball" | "unknownState" | "stopped" | "voided";

export interface MlbGameRefusal {
  kind: "refused";
  reason: MlbGameRefusalReason;
  /** The words shown instead; null for a row the host should not mount (not MLB). */
  words: string | null;
  /** The authority's own word for a stopped or voided game, when it gave one. */
  state: string | null;
}

export type MlbGameModel = MlbGameView | MlbGameRefusal;

// ─── Applies, and the phase ───────────────────────────────────────────────

const LIFECYCLE: readonly EventStatus[] = ["scheduled", "live", "suspended", "completed", "closed"];

/** Whether the host should mount the section: MLB rows on a two-outcome winner market only. */
export function mlbGameApplies(sportKey: string | null | undefined): boolean {
  const key = (sportKey ?? "").toLowerCase();
  return key === "baseball_mlb" && !sportPricesADraw(key);
}

function refused(reason: MlbGameRefusalReason, state: string | null): MlbGameRefusal {
  return { kind: "refused", reason, words: reason === "notBaseball" ? null : PAGE_WORDS.matrixUnavailable, state };
}

/**
 * Whether the section serves this row, and in which phase (football's rule):
 * not MLB → no words; a status outside `EventStatus` → refused; a venue void →
 * "Ended · no winner"; a scheduled or suspended row whose authority says
 * Postponed / Canceled → that word. `hockeyJourneyPhase` is asked only after.
 */
export function mlbGameApplicability(
  event: EventDetailResponse,
  nowMs: number,
): { kind: "applies"; phase: HockeyJourneyPhase } | MlbGameRefusal {
  if (!mlbGameApplies(event.sport)) return refused("notBaseball", null);
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

// ─── The state words ─────────────────────────────────────────────────────

export interface MlbGameState {
  state: string;
  /** The visible second line, or null. */
  context: string | null;
  /**
   * The page's `isSuspended` answer, composed as page.tsx:753-759 composes it:
   * `hasNoReportedResult(…, started_without_result) || liveClaimUnbacked`, on a
   * row that is not finished. The chance is "last recorded" and the projected
   * final is withheld under it.
   */
  noReportedResult: boolean;
}

export function mlbGameState(event: EventDetailResponse, phase: HockeyJourneyPhase, host: MlbGameHost): MlbGameState {
  const W = MLB_WORDS;
  const start = parseMs(event.commence_time);
  const noResult =
    phase !== "final" &&
    (hasNoReportedResult(event.status, event.commence_time, host.nowMs, event.started_without_result) ||
      host.liveClaimUnbacked);
  if (noResult) {
    const settled = venueSettledSummary(event.venue_settled, event.venue_settled_result, event.venue_closed_no_winner);
    const stoppage = settled ? null : authorityStoppageLabel(event.espn?.period);
    return {
      // "away-home": the section's display order, over the DISPLAYED pair (never the raw row).
      state: settled ?? suspendedSummary(host.score?.away, host.score?.home, "away-home", stoppage),
      context: null,
      noReportedResult: true,
    };
  }
  if (phase === "before") {
    if (start === null) return { state: W.beforeFirstPitch, context: null, noReportedResult: false };
    const held = serverHeldPastKickoff(
      event.status,
      event.commence_time,
      host.nowMs,
      event.started_without_result,
      event.authority_not_started,
    );
    const tbd = event.start_is_tbd === true;
    const started = start <= host.nowMs && !tbd;
    const context = tbd ? W.firstPitchToBeAnnounced : `${dayWords(start)} · ${W.firstPitch} ${timeWords(start)}`;
    return {
      state: started && !held ? startBadgeLabel(true, null, held) : W.beforeFirstPitch,
      context,
      noReportedResult: false,
    };
  }
  if (phase === "live") {
    const inning = formatLiveClockLabel(event.espn?.period, event.espn?.game_clock, " · ", event.sport);
    return inning
      ? { state: inning, context: MATRIX_WORDS.stateSource, noReportedResult: false }
      : { state: W.live, context: W.inningUnavailable, noReportedResult: false };
  }
  return { state: W.final, context: start === null ? null : dayWords(start), noReportedResult: false };
}

// ─── Slots ─────────────────────────────────────────────────────────────────

type Side = HockeyJourneySide;

/** CANONICAL STORAGE ORDER (the foundation's): home first. Display order is the page's. */
function inRowOrder<T>(make: (side: Side) => T): [T, T] {
  return [make("home"), make("away")];
}

/** A count of runs, said in the sport's own unit words (native `runsSlot`). */
export function runsSlot(count: number, sportKey: string | null | undefined): HockeyJourneySlot {
  const vocab = sportVocab(sportKey || undefined);
  return { kind: "value", text: `${count}`, spoken: `${count} ${count === 1 ? vocab.unitSingular : vocab.unit}` };
}

function countable(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

/** The DISPLAYED pair, or null when either side is missing. Never the event row. */
function displayedPair(host: MlbGameHost): { home: number; away: number } | null {
  const s = host.score;
  return s && countable(s.home) && countable(s.away) ? { home: s.home, away: s.away } : null;
}

/** Native `EventState.showsVenueSettledVerdict`: the venue settled a game that has started and is not finished. */
function venueSettledInPlay(event: EventDetailResponse, nowMs: number): boolean {
  return event.venue_settled === true && !isFinishedStatus(event.status) && hasStartedByClock(event.commence_time, nowMs);
}

/**
 * The hero's own pair (`heroPair`), or null: none on a venue-settled game, and
 * "Last recorded chance" in place of "Current chance" under a withdrawn claim.
 * An "Opening line" role is kept.
 */
export function mlbCurrentPair(
  event: EventDetailResponse,
  host: MlbGameHost,
  claimWithdrawn: boolean,
): ReturnType<typeof heroPair> {
  if (venueSettledInPlay(event, host.nowMs)) return null;
  const chance = heroPair(event, host);
  if (!chance || !claimWithdrawn || chance.title !== MATRIX_WORDS.currentChance) return chance;
  return { ...chance, title: MATRIX_WORDS.lastRecordedChance };
}

/** The runs columns from the displayed pair: dated by its own clock during play, "Final score" after it. */
function runSlots(
  event: EventDetailResponse,
  host: MlbGameHost,
  final: boolean,
): { home: HockeyJourneySlot; away: HockeyJourneySlot; provenance: string | null } {
  const pair = displayedPair(host);
  if (!pair) {
    const missing = absentSlot(MLB_WORDS.scoreUnavailable);
    return { home: missing, away: missing, provenance: null };
  }
  const observed = clockWords(host.score?.observedAt ?? null);
  return {
    home: runsSlot(pair.home, event.sport),
    away: runsSlot(pair.away, event.sport),
    provenance: final ? MLB_WORDS.finalScore : observed ? `${MLB_WORDS.scoreObserved} ${observed}` : null,
  };
}

/**
 * The projected-final column (D1 = B): the host's `heroProjectedFinal` exactly
 * as passed, or that slot's absence words. Read only before the start and
 * during play, and not under the page's own `isSuspended`. After the final the
 * column is the missing PREGAME reference, "Pregame projected final", and
 * says "Unavailable" whatever the host passes: nothing is read or synthesized.
 */
export function mlbProjection(
  event: EventDetailResponse,
  phase: HockeyJourneyPhase,
  host: MlbGameHost,
  noReportedResult: boolean,
): { title: string; home: HockeyJourneySlot; away: HockeyJourneySlot; provenance: string | null } {
  if (phase === "final") {
    const missing = absentSlot(MLB_WORDS.unavailable);
    return { title: MLB_WORDS.pregameProjectedFinal, home: missing, away: missing, provenance: null };
  }
  const title = projectedFinalLabel(event.sport);
  const none = (words: string) => ({ title, home: absentSlot(words), away: absentSlot(words), provenance: null });
  if (noReportedResult) return none(MLB_WORDS.projectionWithheld);
  const pair = host.projectedFinal;
  if (!pair || !countable(pair.home) || !countable(pair.away)) return none(MLB_WORDS.projectionUnavailable);
  // No source line: the host's pair carries none and the hero prints none.
  return { title, home: runsSlot(pair.home, event.sport), away: runsSlot(pair.away, event.sport), provenance: null };
}

// ─── The matrix, per phase ─────────────────────────────────────────────────

/**
 * Native baseball's matrix, with the projected final as a team-paired column in
 * every phase (Design: score and projection figures in the headline itself):
 *
 *   before  [chance (lead), projected final]                   groups [[0, 1]]
 *   live    [pregame, current (lead), runs, projected final]   groups [[0, 1], [2, 3]]
 *   final   [pregame, final runs (lead), pregame projected final]  groups [[0], [1, 2]]
 *
 * After the final the last column is the missing pregame reference, "Pregame
 * projected final: Unavailable", which the matrix states once for both teams.
 */
export function mlbGameMatrix(
  event: EventDetailResponse,
  phase: HockeyJourneyPhase,
  host: MlbGameHost,
  noReportedResult: boolean,
): HockeyJourneyMatrix {
  const W = MLB_WORDS;
  const projection = mlbProjection(event, phase, host, noReportedResult);
  const projectionColumn = { title: projection.title, provenance: projection.provenance };
  if (phase === "before") {
    const chance = mlbCurrentPair(event, host, noReportedResult);
    return {
      phase,
      columns: [{ title: chance?.title ?? MATRIX_WORDS.winChance, provenance: chance?.provenance ?? null }, projectionColumn],
      rows: inRowOrder((side) => ({
        side,
        values: [chance?.[side] ?? absentSlot(W.winChanceUnavailable), projection[side]],
        result: null,
      })),
      lead: 0,
      groups: [[0, 1]],
    };
  }
  const pregame = pregamePair(event);
  if (phase === "live") {
    const current = mlbCurrentPair(event, host, noReportedResult);
    const runs = runSlots(event, host, false);
    return {
      phase,
      columns: [
        { title: MATRIX_WORDS.pregameChance, provenance: pregame?.provenance ?? null },
        { title: current?.title ?? MATRIX_WORDS.currentChance, provenance: current?.provenance ?? null },
        { title: W.runs, provenance: runs.provenance },
        projectionColumn,
      ],
      rows: inRowOrder((side) => ({
        side,
        values: [
          pregame?.[side] ?? absentSlot(W.pregameChanceUnavailable),
          current?.[side] ?? absentSlot(W.winChanceUnavailable),
          runs[side],
          projection[side],
        ],
        result: null,
      })),
      lead: 1,
      groups: [
        [0, 1],
        [2, 3],
      ],
    };
  }
  const runs = runSlots(event, host, true);
  const shown = displayedPair(host);
  const outcome = servedOutcome(event.status, shown?.home, shown?.away, event.hero_settled_result);
  const result = (side: Side): string | null =>
    outcome === side ? MATRIX_WORDS.won : outcome === "home" || outcome === "away" ? MATRIX_WORDS.lost : null;
  return {
    phase,
    columns: [
      { title: MATRIX_WORDS.pregameChance, provenance: pregame?.provenance ?? null },
      { title: W.finalRuns, provenance: runs.provenance },
      projectionColumn,
    ],
    rows: inRowOrder((side) => ({
      side,
      values: [pregame?.[side] ?? absentSlot(W.pregameChanceUnavailable), runs[side], projection[side]],
      result: result(side),
    })),
    lead: 1,
    groups: [[0], [1, 2]],
  };
}

export function mlbGameHeadline(
  event: EventDetailResponse,
  state: MlbGameState,
  matrix: HockeyJourneyMatrix,
): HockeyJourneyHeadline {
  const names = teamShortNames(
    { name: event.home_team, abbreviation: event.home_team_data?.abbreviation },
    { name: event.away_team, abbreviation: event.away_team_data?.abbreviation },
    event.sport,
  );
  return {
    state: state.state,
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
    // Baseball draws no historical forecast: `livePregameComparison` refuses the sport (unpaid owner).
    historicalForecast: null,
    spokenLabel: MLB_WORDS.spokenLabel,
  };
}

// ─── All props ─────────────────────────────────────────────────────────────

/** H4's two absence words in native baseball's words; every other reading unchanged. */
function reworded(reading: HockeyJourneyOriginalReading): HockeyJourneyOriginalReading {
  if (reading.kind !== "missing") return reading;
  if (reading.words === ORIGINALS_WORDS.noPregameChance) return { kind: "missing", words: MLB_ORIGINALS_WORDS.pregameUnavailable };
  if (reading.words === CONTRIBUTION_WORDS.noInGameReading) return { kind: "missing", words: MLB_ORIGINALS_WORDS.inGameUnavailable };
  return reading;
}

/**
 * All props: H4 over this event's own `/game-markets` body (another event's
 * body lists nothing), with native `BaseballOriginalsAdapter10868`'s scope
 * (`mlb:<id>:<phase>:originals`), empty words and two reworded absences. Every
 * key, label, reading, grade, id and Details row is H4's.
 */
export function mlbGameOriginals(
  event: EventDetailResponse,
  markets: GameMarketsResponse | null | undefined,
  phase: HockeyJourneyPhase,
  nowMs: number,
): HockeyJourneyOriginals {
  // H4 checks ownership itself (`ownHockeyMarkets`): another event's body lists nothing.
  const base = hockeyJourneyOriginals(event, markets, nowMs);
  return {
    ...base,
    scope: `mlb:${event.id}:${phase}:originals`,
    emptyWords: MLB_ORIGINALS_WORDS.emptyWords,
    originals: base.originals.map(
      (original): HockeyJourneyOriginal => ({
        ...original,
        pregame: reworded(original.pregame),
        later: original.later ? reworded(original.later) : null,
      }),
    ),
  };
}

// ─── The whole section ───────────────────────────────────────────────────

/**
 * The section's view model, or why it is refused. Pure: same inputs, same
 * answer. Ownership of each held body is decided once here, by exact
 * `event_id`; H2 and H4 check it again themselves. A missing history leaves
 * only the chart unavailable; a foreign body reads exactly as a missing one.
 */
export function buildMlbGame({ event, history, gameMarkets, host }: MlbGameInput): MlbGameModel {
  const applies = mlbGameApplicability(event, host.nowMs);
  if (applies.kind === "refused") return applies;
  const { phase } = applies;
  const ownHistory = ownHockeyHistory(history, event);
  const ownMarkets = ownHockeyMarkets(gameMarkets, event);
  const state = mlbGameState(event, phase, host);
  const matrix = mlbGameMatrix(event, phase, host, state.noReportedResult);
  const originals = mlbGameOriginals(event, ownMarkets, phase, host.nowMs);
  return {
    kind: "game",
    eventId: event.id,
    phase,
    scope: `mlb:${event.id}:${phase}`,
    headline: mlbGameHeadline(event, state, matrix),
    history: hockeyJourneyHistory(ownHistory, event, phase, host.nowMs),
    historyForeign: !!history && ownHistory === null,
    originals,
    marketsForeign: !!gameMarkets && ownMarkets === null,
    allPropsLabel: allPropsLabel(originals.originals.length),
  };
}
