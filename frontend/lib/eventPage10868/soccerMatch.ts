/**
 * #10868 — THE SOCCER MATCH SCREEN (web): PHASE, HEADER, THE THREE-OUTCOME
 * HEADLINE, THE HOME-ONLY HISTORY, ALL PROPS, THE STORY STREAM, AND THE
 * COMPOSED VIEW MODEL.
 *
 * PILLARS: FORMATTING / TRUTH / DISCOVER. SHIP: a soccer fan's web event page
 * opens on the three-outcome chances (home / draw / away), the match's history
 * and the stories the match has content for, with All props and exact Details,
 * and prints the same answers as the iPhone screen.
 *
 * The web port of native `SoccerMatchPageAdapter10868` (phase, header,
 * headline), `SoccerHistoryAdapter10868`, `SoccerOriginalsAdapter10868`,
 * `SoccerPageInputAdapter10868` and `SoccerEventPageHostAdapter10868.build`,
 * at 274369bc. Read their headers for the full reasoning. Each slot is the web
 * authority that owns it, or that slot's own absence words:
 *
 *   - applies         `soccer_` and a sport that prices a draw (`sportPricesADraw`,
 *                     drawPricedWinner.ts:88) — native host `applies` (L112-114).
 *   - phase           `hockeyJourneyPhase` (core): status only, as native `phase`
 *                     (L138-145); a started suspended match is during play.
 *   - names / tints   `teamShortNames` with no served abbreviation (native
 *                     `TeamShortName.shortPair(away:home:sportKey:)`, L148-150);
 *                     `teamTextColor` per side (native `TeamTextContrast`). The
 *                     Draw has no team colour.
 *   - current home    THE HERO'S OWN PAIR as the host holds it (`hero`, page.tsx
 *                     `resolveProbability`), HOME ONLY, rounded alone as native's
 *                     draw-priced hero (L320-325). "Current" versus "last
 *                     recorded" is `heroReadingIsCurrent` (hockeyJourney.ts), the
 *                     web twin of `EventHeadlinePhase9483.resolve`; an opening
 *                     line is named "Opening line". The hero's away value is
 *                     never read: on a draw sport it is a complement or a
 *                     generic two-way number, not the away WIN chance.
 *   - pre-match       `prematchReading` (prematchReading.ts) with the served /
 *                     opening split native `PrematchReading` makes; home printed
 *                     alone; the away only from the OPENING object's own usable
 *                     away (native `openingAway`, L347-352). The draw is never
 *                     derived from the other two.
 *   - header          native `header` (L154-262): kickoff words, the score with
 *                     its own observation clock, `formatLiveClockLabel`
 *                     (gameTimeLabel.ts:811) for the match clock, the served
 *                     verdict (`servedOutcome`) after the final, and the
 *                     projection through web's `eventPageProjectedPair` /
 *                     `admittedLiveProjection` / `liveCardProjectedFinal` /
 *                     `finalForecastComparison`.
 *   - history         `hockeyJourneyHistory` over this match's OWN body, read for
 *                     the home win chance only (native draws home only, L110-112);
 *                     Draw and the away win keep their absence words.
 *   - All props       `catalogueMatches` (the web twin of H4 `matched`) with the
 *                     soccer readings of native `SoccerOriginalsAdapter10868`.
 *   - stories         `soccerMatchStories.ts`, gated by the owner's admission —
 *                     which NO PRODUCTION OWNER SUPPLIES YET (see that file).
 *
 * PURE: no fetch, no SWR, no subscription, no timer, no ranking, no cache. The
 * host passes what page.tsx already holds and `nowMs`; recomputed every render.
 */

import type { GameMarketsResponse } from "@/lib/api";
import type { EventDetailResponse, EventHistoryResponse } from "@/lib/types";
import { sportPricesADraw } from "@/lib/drawPricedWinner";
import { prematchReading } from "@/lib/prematchReading";
import {
  admittedLiveProjection,
  eventPageProjectedPair,
  liveCardProjectedFinal,
  projectedFinalLabel,
  type SportsbookProjectionFields,
} from "@/lib/projectedFinalPair";
import { finalForecastComparison, finalScorePeriod } from "@/lib/finalForecastComparison";
import { sportVocab } from "@/lib/marketMapUtils";
import { authorityStoppageLabel, formatLiveClockLabel } from "@/lib/gameTimeLabel";
import { SUSPENDED_LABEL, isSuspendedStatus } from "@/lib/eventState";
import { isRecentQuote, statFamily, statLabel, targetLabel } from "@/lib/nflEventCardDeck";
import { catalogQuote } from "@/lib/questionCatalog";
import { isPregameStatus } from "@/lib/settledQuote";
import { sourceIsStale } from "@/lib/sourceAge";
import { sourceLabel } from "@/lib/sourceLabels";
import { formatProbabilityPercent } from "@/lib/probabilityDisplay";
import { propVerdictLabel } from "@/lib/propGrade";
import { teamShortNames } from "@/lib/teamShortName";
import { teamTextColor } from "@/lib/teamColors";
import {
  admissible,
  clockWords,
  dayWords,
  hasStartedByClock,
  hockeyJourneyPhase,
  joined,
  parseMs,
  servedOutcome,
  servedSettlement,
  timeWords,
} from "./hockeyJourneyCore";
import {
  HISTORY_WORDS,
  historyKickoff,
  hockeyJourneyHistory,
  ownHockeyHistory,
} from "./hockeyJourneyHistory";
import {
  ORIGINALS_WORDS,
  catalogueMatches,
  ownHockeyMarkets,
  propContractResult,
  propSubject,
  propsHaveStarted,
  type HockeyJourneyCatalogueMatch,
  type HockeyJourneyHistoricalQuote,
  type HockeyJourneyOriginal,
  type HockeyJourneyOriginalIdentity,
  type HockeyJourneyOriginalReading,
  type HockeyJourneyOriginals,
} from "./hockeyJourneyProps";
import { heroReadingIsCurrent, type HockeyJourneyHeroPair } from "./hockeyJourney";
import {
  NO_SOCCER_ADMISSION,
  STORY_WORDS,
  READING_WORDS,
  lineSide,
  matrixOption,
  offersStory,
  periodMarketIds,
  preMatchAbsence,
  soccerBothCard,
  soccerExactCard,
  soccerFirstCard,
  soccerGoalsCard,
  soccerHalvesCard,
  soccerPin,
  type SoccerHalvesAdmission,
  type SoccerMatchAdmission,
} from "./soccerMatchStories";
import type {
  SoccerHistoryAbsentEntry,
  SoccerMatchHeader,
  SoccerMatchHeadline,
  SoccerMatchHistory,
  SoccerMatchPageModel,
  SoccerMatchPhase,
  SoccerMatchProjection,
  SoccerMatchScore,
  SoccerOutcomeSlot,
  SoccerReadingHeading,
  SoccerSlot,
  SoccerStoryCard,
  SoccerStoryId,
  SoccerStoryStream,
} from "./soccerMatchTypes";

export * from "./soccerMatchStories";

// ─── Words ─────────────────────────────────────────────────────────────────

/** Native `SoccerMatchPageAdapter10868.Words` (L104-131). */
export const MATCH_WORDS = {
  beforeKickoff: "Before kickoff",
  kickoff: "Kickoff",
  kickoffToBeAnnounced: "Kickoff time to be announced",
  inPlay: "In play",
  final: "Final",
  draw: "Draw",
  won: "won",
  preMatchChance: "Pre-match chance",
  openingChance: "Opening chance",
  winChanceUnavailable: "Win chance unavailable",
  preMatchUnavailable: "Pre-match chance unavailable",
  drawChanceUnavailable: "Draw chance unavailable",
  awayChanceUnavailable: "Away win chance unavailable",
  recorded: "Recorded",
  scoreObserved: "Score observed",
  finalScore: "Final score",
  scoreUnavailable: "Score unavailable",
  clockUnavailable: "Match clock unavailable",
  projectedFinal: "Projected final",
  projectionUnavailable: "Projected final unavailable",
  projectionWithheld: "Projected final unavailable for this match state",
  /** `EventHeadlinePhase9483.label` (EventHeadlinePhase9483.swift:35-36); web has no shared twin. */
  currentWinChance: "Current win chance",
  lastRecordedWinChance: "Last recorded win chance",
  /** `OpeningLineHero.caption` (OpeningLineHero.swift:43). */
  openingLine: "Opening line",
  outcome: (team: string) => `${team} win`,
} as const;

/** Native `SoccerHistoryAdapter10868.Words` (L64-87). */
export const SOCCER_HISTORY_WORDS = {
  title: "Win probability",
  beforeCaption: "Before kickoff",
  gameCaption: "Match history",
  preMatch: "Pre-match",
  recorded: "Recorded",
  draw: "Draw",
  notRecorded: "Not recorded",
  noHistory: "No recorded history",
  historyUnavailable: "History unavailable",
  drawHistoryUnavailable: "Draw chance history unavailable",
  awayHistoryUnavailable: "Away win chance history unavailable",
  hollowKey: "Hollow · last pre-match",
  lastPreMatch: "Last pre-match",
  unconfirmedKickoff: "Kickoff time not confirmed",
  unconfirmedKickoffWords: "Pre-match and match readings are split at a confirmed kickoff, and this match has none yet.",
  drawAndAwayNote: (away: string) => `Draw and ${away} win chance history unavailable.`,
} as const;

/** Native `SoccerOriginalsAdapter10868.Words` (SoccerOriginalsAdapter10868.swift:61-75). */
export const SOCCER_ORIGINALS_WORDS = {
  heading: "All props",
  emptyWords: "No original props recorded for this match",
  savedBeforeStart: "Saved before kickoff",
  recorded: "Recorded",
  context: (count: number) => (count === 1 ? "1 original" : `${count} originals`),
} as const;

// ─── Host ──────────────────────────────────────────────────────────────────

/** What the host already holds, passed in unchanged (the hockey host's shape). */
export interface SoccerMatchHost {
  nowMs: number;
  /** page.tsx `resolvedProbability` (the hero's own pair), or null before it resolves. Only its home value is read. */
  hero: HockeyJourneyHeroPair | null;
  /** page.tsx `acceptedPriceClock`. Null is undated: "last recorded", never "current". */
  probabilityObservedAt: string | null;
  /** True while the page says live delivery is interrupted. */
  deliveryInterrupted?: boolean;
}

export interface SoccerMatchInputs {
  event: EventDetailResponse;
  /** The page's SWR `/history` body; another match's body reads as none. */
  history: EventHistoryResponse | null | undefined;
  /** The page's `gameMarkets` memo; another match's body reads as none. */
  gameMarkets: GameMarketsResponse | null | undefined;
  /** The owner's story admission. No production owner supplies one: omit it. */
  admitted?: SoccerMatchAdmission;
  halvesAdmission?: SoccerHalvesAdmission;
  admittedCards?: readonly SoccerStoryId[];
  host: SoccerMatchHost;
}

export interface SoccerMatchViewModel extends SoccerMatchPageModel {
  originals: HockeyJourneyOriginals;
}

// ─── Applies, phase, names ─────────────────────────────────────────────────

export function soccerMatchApplies(sport: string | null | undefined): boolean {
  return (sport ?? "").toLowerCase().startsWith("soccer_") && sportPricesADraw(sport);
}

export function soccerMatchPhase(event: EventDetailResponse, nowMs: number): SoccerMatchPhase {
  return hockeyJourneyPhase(event, nowMs);
}

export function soccerNames(event: EventDetailResponse): { home: string; away: string } {
  const pair = teamShortNames({ name: event.home_team }, { name: event.away_team }, event.sport);
  return { home: pair.home, away: pair.away };
}

function scorePair(event: EventDetailResponse): { home: number; away: number } | null {
  const { home_score: home, away_score: away } = event;
  return typeof home === "number" && typeof away === "number" && home >= 0 && away >= 0 ? { home, away } : null;
}

// ─── Header ────────────────────────────────────────────────────────────────

function stateWords(event: EventDetailResponse, phase: SoccerMatchPhase, names: { home: string; away: string }, nowMs: number): string {
  if (phase === "before") return MATCH_WORDS.beforeKickoff;
  if (phase === "live") {
    if (isSuspendedStatus(event.status) && hasStartedByClock(event.commence_time, nowMs)) {
      // Native `EventState.suspendedLabel(authorityPeriod:)`: the authority's own stoppage word, else the one label.
      return authorityStoppageLabel(event.espn?.period) ?? SUSPENDED_LABEL;
    }
    return MATCH_WORDS.inPlay;
  }
  const outcome = servedOutcome(event.status, event.home_score, event.away_score, event.hero_settled_result);
  if (outcome === "home") return `${MATCH_WORDS.final} · ${names.home} ${MATCH_WORDS.won}`;
  if (outcome === "away") return `${MATCH_WORDS.final} · ${names.away} ${MATCH_WORDS.won}`;
  if (outcome === "draw") return `${MATCH_WORDS.final} · ${MATCH_WORDS.draw}`;
  return MATCH_WORDS.final;
}

function dateWords(event: EventDetailResponse, phase: SoccerMatchPhase): string | null {
  const start = parseMs(event.commence_time);
  if (start === null) return null;
  const day = dayWords(start);
  if (phase !== "before") return day;
  if (event.start_is_tbd === true) return `${day} · ${MATCH_WORDS.kickoffToBeAnnounced}`;
  return `${day} · ${MATCH_WORDS.kickoff} ${timeWords(start)}`;
}

function scoreOf(event: EventDetailResponse, phase: SoccerMatchPhase, names: { home: string; away: string }): SoccerMatchScore {
  const pair = scorePair(event);
  if (!pair) return { kind: "unavailable", text: MATCH_WORDS.scoreUnavailable };
  const spoken = `${names.home} ${pair.home}, ${names.away} ${pair.away}`;
  if (phase === "final") {
    return { kind: "actual", home: `${pair.home}`, away: `${pair.away}`, context: MATCH_WORDS.finalScore, spoken: `${MATCH_WORDS.final}: ${spoken}` };
  }
  const observed = clockWords(event.score_observed_at);
  return {
    kind: "actual",
    home: `${pair.home}`,
    away: `${pair.away}`,
    context: observed ? `${MATCH_WORDS.scoreObserved} ${observed}` : null,
    spoken,
  };
}

function clockOf(event: EventDetailResponse): SoccerSlot {
  const text = formatLiveClockLabel(event.espn?.period, event.espn?.game_clock, " ", event.sport);
  return text ? { kind: "value", text } : { kind: "unavailable", text: MATCH_WORDS.clockUnavailable };
}

function liveOdds(event: EventDetailResponse): SportsbookProjectionFields | undefined {
  return event.current_odds as SportsbookProjectionFields | undefined;
}

const unavailableProjection = (words: string): SoccerMatchProjection => ({
  title: MATCH_WORDS.projectedFinal,
  reading: { kind: "unavailable", text: words },
});

/** "Albacete 0 · Real Valladolid 5", each score glued to its team (native `pairText`). */
const pairText = (names: { home: string; away: string }, pair: { home: number; away: number }) =>
  `${names.away} ${pair.away} · ${names.home} ${pair.home}`;

/**
 * Native `projection` (L224-257). Before kickoff: web's page pair
 * (`eventPageProjectedPair`) under the line's gates — not once the clock has
 * passed the start (native `showsProjection` with no score), a derived spread,
 * both halves above zero, and no level final where the sport cannot end level —
 * printed as native's "Proj. <away>-<home>" (EventDetailView.swift:1353-1390).
 * During play: the producer's admitted in-play pair only. After the final: the
 * admitted pre-match comparison only.
 */
function projectionOf(
  event: EventDetailResponse,
  phase: SoccerMatchPhase,
  names: { home: string; away: string },
  history: EventHistoryResponse | null,
  nowMs: number,
): SoccerMatchProjection {
  const title = projectedFinalLabel(event.sport);
  if (phase === "before") {
    if (hasStartedByClock(event.commence_time, nowMs)) return unavailableProjection(MATCH_WORDS.projectionUnavailable);
    const pair = eventPageProjectedPair({
      odds: liveOdds(event),
      sportKey: event.sport,
      commenceTime: event.commence_time,
      isLive: false,
      ladderPair: history?.pm_spread_data?.projected_final,
    });
    const vocab = sportVocab(event.sport || undefined);
    if (!pair || !vocab.hasDerivedSpread || !(pair.home_score > 0) || !(pair.away_score > 0)) {
      return unavailableProjection(MATCH_WORDS.projectionUnavailable);
    }
    const home = Math.round(pair.home_score);
    const away = Math.round(pair.away_score);
    if (!vocab.canEndInATie && home === away) return unavailableProjection(MATCH_WORDS.projectionUnavailable);
    return { title, reading: { kind: "value", text: `Proj. ${away}-${home}` } };
  }
  if (phase === "live") {
    const start = parseMs(event.commence_time);
    const pageIsLive = event.status === "live" && start !== null && start <= nowMs;
    const odds = liveOdds(event);
    if (!pageIsLive || odds?.live_projection == null) return unavailableProjection(MATCH_WORDS.projectionUnavailable);
    if (!admittedLiveProjection(odds, event.sport, event.commence_time)) {
      return unavailableProjection(MATCH_WORDS.projectionWithheld);
    }
    const printed = liveCardProjectedFinal(odds, event.sport, event.commence_time, {
      home: event.home_score,
      away: event.away_score,
    });
    if (!printed) return unavailableProjection(MATCH_WORDS.projectionWithheld);
    return { title, reading: { kind: "value", text: pairText(names, printed) } };
  }
  const comparison = finalForecastComparison({
    sportKey: event.sport,
    status: event.status,
    homeScore: event.home_score,
    awayScore: event.away_score,
    actualPeriod: finalScorePeriod(event.sport, event.final_score_period),
    projection: event.pregame_projection,
  });
  if (!comparison) return unavailableProjection(MATCH_WORDS.projectionUnavailable);
  return { title: comparison.label, reading: { kind: "value", text: pairText(names, comparison.forecast) } };
}

export function soccerMatchHeader(
  event: EventDetailResponse,
  phase: SoccerMatchPhase,
  history: EventHistoryResponse | null,
  nowMs: number,
): SoccerMatchHeader {
  const names = soccerNames(event);
  return {
    state: stateWords(event, phase, names, nowMs),
    date: dateWords(event, phase),
    home: names.home,
    away: names.away,
    score: phase === "before" ? null : scoreOf(event, phase, names),
    clock: phase === "live" ? clockOf(event) : null,
    projection: projectionOf(event, phase, names, history, nowMs),
  };
}

// ─── Headline ──────────────────────────────────────────────────────────────

/** The served display name for a probability source, only when it says more than its key (native `sourceName`). */
function sourceName(source: string | null | undefined, event: EventDetailResponse): string | null {
  if (!source) return null;
  const served = event.win_probability_sources?.[source]?.display_name;
  return served && served !== source ? served : null;
}

/** A chance as native's `formatProbability` prints it: the value alone, through web's one percent rule. */
function chance(value: number | null | undefined): string | null {
  const v = admissible(value);
  return v === null ? null : formatProbabilityPercent(v);
}

interface Reading {
  heading: SoccerReadingHeading;
  home: string | null;
  away: string | null;
}

/** Native `current` (L309-326): the hero's home value, home only. */
function currentReading(event: EventDetailResponse, host: SoccerMatchHost): Reading {
  const hero = host.hero;
  if (!hero) return { heading: { title: MATCH_WORDS.lastRecordedWinChance, context: null }, home: null, away: null };
  const opening = hero.probSourceLabel === MATCH_WORDS.openingLine;
  const title = opening
    ? MATCH_WORDS.openingLine
    : heroReadingIsCurrent(event, host)
      ? MATCH_WORDS.currentWinChance
      : MATCH_WORDS.lastRecordedWinChance;
  const clock = clockWords(host.probabilityObservedAt);
  return {
    heading: { title, context: joined([clock ? `${MATCH_WORDS.recorded} ${clock}` : null, sourceName(event.hero_probability_source, event)]) },
    home: chance(hero.homeProb),
    away: null,
  };
}

const usable = (v: number | null | undefined): v is number => typeof v === "number" && Number.isFinite(v) && v > 0 && v < 1;

/** Native `preMatch` (L330-352): the served ladder, else the opening line, named as such. */
function preMatchReading(event: EventDetailResponse): Reading {
  const reading = prematchReading({ prematch_odds: event.prematch_odds, opening_odds: event.opening_odds });
  if (!reading) return { heading: { title: MATCH_WORDS.preMatchChance, context: null }, home: null, away: null };
  // `prematchReading` reads the served ladder when its home value is usable, else `opening_odds`.
  const isServed = usable(event.prematch_odds?.home_probability);
  const heading = {
    title: isServed ? MATCH_WORDS.preMatchChance : MATCH_WORDS.openingChance,
    context: isServed ? sourceLabel(reading.source) : null,
  };
  // The away win chance only from the opening object's OWN usable away — never a complement.
  const openingAway = !isServed && usable(event.opening_odds?.away_probability) ? chance(event.opening_odds?.away_probability) : null;
  return { heading, home: chance(reading.homeProbability), away: openingAway };
}

function slot(value: string | null, words: string): SoccerSlot {
  return value === null ? { kind: "unavailable", text: words } : { kind: "value", text: value };
}

export function soccerMatchHeadline(event: EventDetailResponse, phase: SoccerMatchPhase, host: SoccerMatchHost): SoccerMatchHeadline {
  const names = soccerNames(event);
  const pregame = preMatchReading(event);
  let primary: Reading;
  let comparison: Reading | null;
  if (phase === "before") {
    primary = currentReading(event, host);
    comparison = null;
  } else if (phase === "live") {
    primary = currentReading(event, host);
    comparison = pregame;
  } else {
    // Settled means settled: after the final the pre-match chance leads, never the settled 1 / 0.5 / 0.
    primary = pregame;
    comparison = null;
  }
  const primaryMissing = phase === "final" ? MATCH_WORDS.preMatchUnavailable : MATCH_WORDS.winChanceUnavailable;
  const home: SoccerOutcomeSlot = {
    key: "home",
    label: MATCH_WORDS.outcome(names.home),
    tint: teamTextColor(event.home_team_data?.primary_color) ?? null,
    primary: slot(primary.home, primaryMissing),
    comparison: comparison ? slot(comparison.home, MATCH_WORDS.preMatchUnavailable) : null,
  };
  const draw: SoccerOutcomeSlot = {
    key: "draw",
    label: MATCH_WORDS.draw,
    tint: null,
    primary: slot(null, MATCH_WORDS.drawChanceUnavailable),
    comparison: comparison ? slot(null, MATCH_WORDS.drawChanceUnavailable) : null,
  };
  const away: SoccerOutcomeSlot = {
    key: "away",
    label: MATCH_WORDS.outcome(names.away),
    tint: teamTextColor(event.away_team_data?.primary_color) ?? null,
    primary: slot(primary.away, MATCH_WORDS.awayChanceUnavailable),
    comparison: comparison ? slot(comparison.away, MATCH_WORDS.awayChanceUnavailable) : null,
  };
  return {
    outcomes: [home, draw, away],
    primaryHeading: primary.heading,
    comparisonHeading: comparison?.heading ?? null,
  };
}

// ─── History ───────────────────────────────────────────────────────────────

/** The body with every away value removed: the history reader then draws, frames and words the home line alone. */
function homeOnly(history: EventHistoryResponse): EventHistoryResponse {
  return {
    ...history,
    history: history.history?.map((point) => ({ ...point, away_probability: null })),
    aggregate_line: history.aggregate_line?.map((point) => {
      const { away_probability: _dropped, ...rest } = point as typeof point & { away_probability?: unknown };
      void _dropped;
      return rest;
    }),
  } as unknown as EventHistoryResponse;
}

function absentEntry(id: string, key: "draw" | "away", name: string, words: string): SoccerHistoryAbsentEntry {
  return { id, key, name, words };
}

function soccerUnavailableHistory(event: EventDetailResponse, phase: SoccerMatchPhase, names: { home: string; away: string }): SoccerMatchHistory {
  const W = SOCCER_HISTORY_WORDS.historyUnavailable;
  return {
    title: SOCCER_HISTORY_WORDS.title,
    caption: phase === "before" ? SOCCER_HISTORY_WORDS.beforeCaption : SOCCER_HISTORY_WORDS.gameCaption,
    line: null,
    // As web's hockey slot: no line is claimed when no body is held.
    home: {
      id: `history:${event.id}:home`,
      side: "home",
      name: MATCH_WORDS.outcome(names.home),
      runs: [],
      before: { kind: "absent", words: W },
      recorded: { kind: "absent", words: W },
    },
    draw: absentEntry(`history:${event.id}:draw`, "draw", SOCCER_HISTORY_WORDS.draw, W),
    away: absentEntry(`history:${event.id}:away`, "away", MATCH_WORDS.outcome(names.away), W),
    domain: null,
    guides: [],
    xTicks: [],
    yTicks: [],
    readout: "single",
    beforeLabel: W,
    recordedLabel: SOCCER_HISTORY_WORDS.recorded,
    markKey: null,
    notes: [],
    summary: W,
    absence: { title: W, words: null },
    detailsLabel: HISTORY_WORDS.details,
  };
}

/** Native `SoccerHistoryAdapter10868.history` / `unavailable` (L93-203). */
export function soccerMatchHistory(
  held: EventHistoryResponse | null | undefined,
  event: EventDetailResponse,
  phase: SoccerMatchPhase,
  nowMs: number,
): SoccerMatchHistory {
  const names = soccerNames(event);
  const own = ownHockeyHistory(held, event);
  if (!own) return soccerUnavailableHistory(event, phase, names);
  const read = hockeyJourneyHistory(homeOnly(own), event, phase, nowMs);
  const line = read.line ?? "blend";
  const kickoff = historyKickoff(own, event);
  const homeName = MATCH_WORDS.outcome(names.home);
  const draw = absentEntry(
    `${line}:${own.event_id}:draw`,
    "draw",
    SOCCER_HISTORY_WORDS.draw,
    SOCCER_HISTORY_WORDS.drawHistoryUnavailable,
  );
  const away = absentEntry(
    `${line}:${own.event_id}:away`,
    "away",
    MATCH_WORDS.outcome(names.away),
    SOCCER_HISTORY_WORDS.awayHistoryUnavailable,
  );
  const sourceNote = line === "blend" ? HISTORY_WORDS.blendSource : HISTORY_WORDS.consensusSource;
  const caption = phase === "before" ? SOCCER_HISTORY_WORDS.beforeCaption : SOCCER_HISTORY_WORDS.gameCaption;
  const served = read.series[0];
  if (read.absence || served.runs.length === 0) {
    const words = SOCCER_HISTORY_WORDS.noHistory;
    return {
      title: SOCCER_HISTORY_WORDS.title,
      caption,
      line,
      home: { ...served, name: homeName, runs: [], before: { kind: "absent", words }, recorded: { kind: "absent", words } },
      draw,
      away,
      domain: null,
      guides: [],
      xTicks: [],
      yTicks: [],
      readout: "single",
      beforeLabel: SOCCER_HISTORY_WORDS.preMatch,
      recordedLabel: SOCCER_HISTORY_WORDS.recorded,
      markKey: null,
      notes: [sourceNote],
      summary: words,
      absence: { title: words, words: null },
      detailsLabel: HISTORY_WORDS.details,
    };
  }
  // The home series in the match's own words: "Last pre-match", and why a slot is empty.
  const before =
    served.before.kind === "reading"
      ? { ...served.before, provenance: served.before.provenance.replace(`${HISTORY_WORDS.lastPregame} · `, `${SOCCER_HISTORY_WORDS.lastPreMatch} · `) }
      : { kind: "absent" as const, words: kickoff === null ? SOCCER_HISTORY_WORDS.unconfirmedKickoffWords : SOCCER_HISTORY_WORDS.notRecorded };
  const drawAndAway = SOCCER_HISTORY_WORDS.drawAndAwayNote(names.away);
  return {
    title: SOCCER_HISTORY_WORDS.title,
    caption,
    line,
    home: { ...served, name: homeName, before },
    draw,
    away,
    domain: read.domain,
    guides: read.guides,
    xTicks: read.xTicks,
    yTicks: read.yTicks,
    readout: read.readout,
    beforeLabel: kickoff === null ? SOCCER_HISTORY_WORDS.unconfirmedKickoff : SOCCER_HISTORY_WORDS.preMatch,
    recordedLabel: SOCCER_HISTORY_WORDS.recorded,
    markKey: kickoff === null ? null : SOCCER_HISTORY_WORDS.hollowKey,
    notes: [sourceNote, drawAndAway, HISTORY_WORDS.gapsNote],
    summary: `${homeName} chance, recorded observations only. ${drawAndAway}`,
    absence: null,
    detailsLabel: HISTORY_WORDS.details,
  };
}

// ─── All props ─────────────────────────────────────────────────────────────

function finite(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function idsText(values: number[] | null | undefined, separator: string): string | null {
  return values && values.length > 0 ? values.map(String).join(separator) : null;
}

/** Web hockey's `identityOf` (H4 `identity(of:)`), restated: it is private there. */
function identityOf(match: HockeyJourneyCatalogueMatch): HockeyJourneyOriginalIdentity {
  const row = match.source.row;
  const source = row.source ? row.source : ORIGINALS_WORDS.unattributed;
  const market =
    (typeof row._market_id === "number" ? String(row._market_id) : null) ?? idsText(row._market_ids, "+") ?? (row.market_name ?? "");
  const side = idsText(row.contributor_outcome_ids, "+") ?? `${row.market_name ?? ""}-${row.outcome_name ?? ""}`;
  return { source, market, side };
}

/** Web hockey's `absenceWords` (H4 `absenceWords`), restated. */
function absenceWords(match: HockeyJourneyCatalogueMatch, status: string | null | undefined, nowMs: number): string {
  if (match.source.closed) return ORIGINALS_WORDS.periodFinished;
  if (!isPregameStatus(status) && sourceIsStale(match.source.row.observed_at ?? null, nowMs)) return ORIGINALS_WORDS.noRecentPrice;
  return ORIGINALS_WORDS.unavailablePrice;
}

/** Web hockey's `historicalQuote` (native `OriginalMarketDetails9483.HistoricalQuote`), restated. */
function historicalQuote(price: number, at: number | null, venue: string | null): HockeyJourneyHistoricalQuote {
  const text = formatProbabilityPercent(price);
  const recorded = at === null ? null : joined([clockWords(at), venue]);
  return {
    text,
    recorded,
    label: ORIGINALS_WORDS.historicalLabel,
    value: recorded ? `${text}, ${ORIGINALS_WORDS.historicalRecorded} ${recorded}` : `${text}, ${ORIGINALS_WORDS.historicalTimeUnknown}`,
  };
}

/**
 * Native H4 `contractGrade` AS IT STANDS AT 274369bc
 * (HockeyJourneyOriginalsAdapter10868.swift:405-430), which native soccer reuses:
 * a player prop by its contract result; an Under leg of a line row whose
 * served grade is its Over's (`gradeIsTheOvers`, L438-443) is not confirmed;
 * otherwise the served settlement. Provenance "Settled by <venue>". Web's hockey
 * twin (`originalGrade`, hockeyJourneyProps.ts) predates both the Under rule and
 * those words ("Settlement · <venue>"); see the handback. The verdict itself is
 * web's one settled vocabulary (`propVerdictLabel`).
 */
function originalGrade(match: HockeyJourneyCatalogueMatch, pricesOutcome: boolean): { hit: boolean | null; words: string; provenance: string } {
  const row = match.source.row;
  const served = servedSettlement(row.is_winner, row.resolution_source);
  let won: boolean | null;
  if (match.source.isPlayerProp) {
    const verdict = propContractResult(row, null, row.threshold ?? 0);
    won = verdict === "reached" ? true : verdict === "missed" ? false : null;
  } else if (!pricesOutcome && finite(row.probability) === null && lineSide(row) === "under") {
    return { hit: null, words: ORIGINALS_WORDS.notYetConfirmed, provenance: ORIGINALS_WORDS.noSettlement };
  } else {
    won = served;
  }
  if (won === null) {
    return {
      hit: null,
      words: ORIGINALS_WORDS.notYetConfirmed,
      provenance: served === null ? ORIGINALS_WORDS.noSettlement : ORIGINALS_WORDS.disputed,
    };
  }
  const venue = sourceLabel(row.source);
  return { hit: won, words: propVerdictLabel(won), provenance: venue ? `Settled by ${venue}` : "Venue settlement" };
}

/** Web hockey's `originalLabel` (H4 `label`), restated. */
function originalLabel(match: HockeyJourneyCatalogueMatch, event: EventDetailResponse): string {
  const source = match.source;
  const row = source.row;
  if (!source.isPlayerProp) return source.label;
  const subject = propSubject(row.outcome_name);
  const threshold = finite(row.threshold);
  if (!subject || threshold === null) return source.label;
  const target = targetLabel(threshold);
  const o = row.outcome_name ?? "";
  const colon = o.indexOf(":");
  if (colon < 0 || o.slice(colon + 1).trim() !== target) return source.label;
  const stat = statFamily(statLabel(row.market_name ?? "", event.home_team, event.away_team, subject));
  return `${subject} ${target} ${stat.toLowerCase()}`;
}

/**
 * Native `clockIsOwn` (SoccerOriginalsAdapter10868.swift:155-160): player props,
 * matchups and `other` rows carry their own clock; game lines, team scoring and
 * periods (served `GameMarketOutcome` arrays) can carry a sibling's. Web's
 * catalogue files `other` moneylines under "Game lines", so an `other` row is
 * recognised by the served array it came from, not by the family label.
 */
function clockIsOwn(match: HockeyJourneyCatalogueMatch, otherRows: ReadonlySet<unknown>): boolean {
  return match.source.family === "Player props" || match.source.family === "Matchups" || otherRows.has(match.source.row);
}

function isPeriod(match: HockeyJourneyCatalogueMatch, admitted: ReadonlySet<number>): boolean {
  const row = match.source.row;
  if (typeof row._market_id === "number" && admitted.has(row._market_id)) return true;
  return (row._market_ids ?? []).some((id) => admitted.has(id));
}

/** Native `pregameReading` (SoccerOriginalsAdapter10868.swift:164-185). */
function originalPregame(
  match: HockeyJourneyCatalogueMatch,
  event: EventDetailResponse,
  markets: GameMarketsResponse,
  started: boolean,
  own: boolean,
  nowMs: number,
): HockeyJourneyOriginalReading {
  const row = match.source.row;
  const venue = sourceLabel(row.source);
  if (started) {
    const market = typeof row._market_id === "number" ? row._market_id : row._market_ids?.[0];
    const option = typeof market === "number" ? matrixOption(market, row.contributor_outcome_ids ?? [], markets) : null;
    const pin = soccerPin(option, event.commence_time);
    if (!pin) return { kind: "missing", words: preMatchAbsence(option) };
    return {
      kind: "value",
      text: formatProbabilityPercent(pin.probability),
      placement: pin.probability,
      provenance: joined([`${SOCCER_ORIGINALS_WORDS.savedBeforeStart} ${clockWords(pin.atMs) ?? ""}`, venue]),
    };
  }
  const price = admissible(match.outcome.probability);
  if (price === null) return { kind: "missing", words: absenceWords(match, event.status, nowMs) };
  const at = parseMs(match.outcome.observedAt);
  if (!own || !isRecentQuote(match.outcome.observedAt, nowMs) || at === null) {
    return { kind: "missing", words: ORIGINALS_WORDS.noRecentPrice };
  }
  return {
    kind: "value",
    text: formatProbabilityPercent(price),
    placement: price,
    provenance: joined([`${SOCCER_ORIGINALS_WORDS.recorded} ${clockWords(at) ?? ""}`, venue]),
  };
}

/** Native `laterReading` (SoccerOriginalsAdapter10868.swift:193-229): an admitted half is never the current chance. */
function originalLater(
  match: HockeyJourneyCatalogueMatch,
  event: EventDetailResponse,
  own: boolean,
  period: boolean,
  nowMs: number,
): { later: HockeyJourneyOriginalReading; quote: HockeyJourneyHistoricalQuote | null } {
  const row = match.source.row;
  const venue = sourceLabel(row.source);
  const observed = match.outcome.observedAt;
  const at = parseMs(observed);
  const stale = !isPregameStatus(event.status) && sourceIsStale(observed, nowMs);
  const missing = (words: string): HockeyJourneyOriginalReading => ({ kind: "missing", words });
  let price = admissible(match.outcome.probability);
  if (price === null && stale && at !== null && !match.source.closed) {
    price = admissible(catalogQuote(row, event.status, at));
  }
  if (price === null) return { later: missing(absenceWords(match, event.status, nowMs)), quote: null };
  if (servedSettlement(row.is_winner, row.resolution_source) !== null) {
    return { later: missing(READING_WORDS.settledNoChance), quote: null };
  }
  const quote = historicalQuote(price, at, venue);
  if (!own || at === null) return { later: missing(ORIGINALS_WORDS.noRecentPrice), quote: period ? null : quote };
  const start = parseMs(event.commence_time);
  if (start !== null && at < start) return { later: missing(READING_WORDS.inPlayUnavailable), quote };
  if (period) return { later: missing(READING_WORDS.inPlayUnavailable), quote };
  if (stale || !isRecentQuote(observed, nowMs)) return { later: missing(ORIGINALS_WORDS.noRecentPrice), quote };
  return {
    later: {
      kind: "value",
      text: formatProbabilityPercent(price),
      placement: price,
      provenance: joined([`${SOCCER_ORIGINALS_WORDS.recorded} ${clockWords(at) ?? ""}`, venue]),
    },
    quote: null,
  };
}

/**
 * "All props": every original the page's catalogue lists, with the soccer
 * readings, only from this match's own body (`ownHockeyMarkets`). Another
 * match's body lists nothing.
 */
export function soccerMatchOriginals(
  event: EventDetailResponse,
  markets: GameMarketsResponse | null | undefined,
  nowMs: number,
  periodMarkets: ReadonlySet<number> = new Set(),
): HockeyJourneyOriginals {
  const phase = soccerMatchPhase(event, nowMs);
  const started = propsHaveStarted(event, nowMs);
  const own = ownHockeyMarkets(markets, event);
  const matches = own ? catalogueMatches(own, event.status, nowMs) : [];
  const otherRows = new Set<unknown>(own?.other ?? []);
  const originals = matches.map((match): HockeyJourneyOriginal => {
    const identity = identityOf(match);
    const ownClock = clockIsOwn(match, otherRows);
    let mode: HockeyJourneyOriginal["mode"] = "pregame";
    let later: HockeyJourneyOriginalReading | null = null;
    let grade: HockeyJourneyOriginal["grade"] = null;
    let historical: HockeyJourneyHistoricalQuote | null = null;
    if (phase === "live") {
      const reading = originalLater(match, event, ownClock, isPeriod(match, periodMarkets), nowMs);
      mode = "current";
      later = reading.later;
      historical = reading.quote;
    } else if (phase === "final") {
      mode = "result";
      // Native `Row.pricesOutcome`: an `other` row or a matchup prices its own outcome.
      grade = originalGrade(match, otherRows.has(match.source.row) || match.source.family === "Matchups");
    }
    const rows: Array<{ label: string; value: string }> = [];
    const marketIds =
      (typeof match.source.row._market_id === "number" ? String(match.source.row._market_id) : null) ??
      idsText(match.source.row._market_ids, ", ");
    if (marketIds) rows.push({ label: ORIGINALS_WORDS.marketId, value: marketIds });
    const outcomeIds = idsText(match.source.row.contributor_outcome_ids, ", ");
    if (outcomeIds) rows.push({ label: ORIGINALS_WORDS.outcomeId, value: outcomeIds });
    return {
      key: `${identity.source}|${identity.market}|${identity.side}`,
      identity,
      title: match.group.question,
      outcome: match.outcome.label,
      label: originalLabel(match, event),
      family: match.group.family,
      mode,
      pregame: originalPregame(match, event, own as GameMarketsResponse, started, ownClock, nowMs),
      later,
      grade,
      about: { source: sourceLabel(match.source.row.source), rules: ORIGINALS_WORDS.rulesUnavailable, rows, historical },
    };
  });
  return {
    scope: `soccer:${event.id}:${phase}:originals`,
    heading: SOCCER_ORIGINALS_WORDS.heading,
    context: originals.length === 0 ? null : SOCCER_ORIGINALS_WORDS.context(originals.length),
    emptyWords: SOCCER_ORIGINALS_WORDS.emptyWords,
    originals,
  };
}

// ─── The stream and the page ───────────────────────────────────────────────

/** The screen's fixed order (native `offeredCards`, SoccerPageInputAdapter10868 L169-180). */
const STORY_ORDER: SoccerStoryId[] = ["goals", "exact", "both", "first", "halves"];

/** "All props · 98", or nothing when no original is listed (native `copy`, L215-221). */
export function soccerAllPropsLabel(count: number): string | null {
  return count > 0 ? `${SOCCER_ORIGINALS_WORDS.heading} · ${count}` : null;
}

export function buildSoccerMatch(inputs: SoccerMatchInputs): SoccerMatchViewModel {
  const { event, host } = inputs;
  const nowMs = host.nowMs;
  const admission = inputs.admitted ?? NO_SOCCER_ADMISSION;
  const phase = soccerMatchPhase(event, nowMs);
  const names = soccerNames(event);
  // Ownership decided once, by exact event id; each reader checks it again.
  const history = ownHockeyHistory(inputs.history, event);
  const markets = ownHockeyMarkets(inputs.gameMarkets, event);

  const built: Record<SoccerStoryId, SoccerStoryCard | null> = {
    goals: soccerGoalsCard(event, markets, admission, phase, names, nowMs),
    exact: soccerExactCard(event, markets, admission, phase, names, nowMs),
    both: soccerBothCard(event, markets, admission, phase, names, nowMs),
    first: soccerFirstCard(event, markets, history, admission, phase, names, nowMs),
    halves: soccerHalvesCard(event, markets, admission, phase, names, nowMs),
  };
  const halvesAdmission = inputs.halvesAdmission ?? "routeDefault";
  const admittedCards = inputs.admittedCards ?? [];
  const cards = STORY_ORDER.filter((id) => offersStory(id, phase, admittedCards, halvesAdmission))
    .map((id) => built[id])
    .filter((card): card is SoccerStoryCard => card !== null);
  const stories: SoccerStoryStream = {
    heading: STORY_WORDS.streamHeading,
    cards,
    manualStatus: cards.length > 1 ? STORY_WORDS.manualStatus : null,
    storiesLabel: STORY_WORDS.storiesLabel,
    emptyWords: STORY_WORDS.emptyWords,
  };
  const originals = soccerMatchOriginals(event, markets, nowMs, periodMarketIds(admission, event));
  return {
    eventId: event.id,
    phase,
    header: soccerMatchHeader(event, phase, history, nowMs),
    headline: soccerMatchHeadline(event, phase, host),
    history: soccerMatchHistory(history, event, phase, nowMs),
    stories,
    copy: { storiesLabel: STORY_WORDS.storiesLabel, allPropsLabel: soccerAllPropsLabel(originals.originals.length) },
    colors: {
      home: event.home_team_data?.primary_color ?? null,
      away: event.away_team_data?.primary_color ?? null,
    },
    originals,
  };
}
