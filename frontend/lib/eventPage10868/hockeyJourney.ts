/**
 * #10868 — THE HOCKEY JOURNEY SCREEN (web), PART ONE AND THE WHOLE PAGE:
 * PHASE, HEADER, THE PAIRED COMPARISON MATRIX, AND THE COMPOSED VIEW MODEL.
 *
 * PILLARS: FORMATTING / TRUTH / DISCOVER. SHIP: on `nhl-journey` the before,
 * during and final matrix prints exactly the chances, goals and forecasts the
 * rest of the event page already decides, the history draws only what was
 * recorded, and a reader moves between the points and assists stories with
 * Previous and Next.
 *
 * The web port of native `HockeyJourneyPageAdapter10868` +
 * `HockeyJourneyPageInputAdapter10868`. Each slot is the output of the web
 * authority that owns it, or that slot's own absence words:
 *
 *   - phase           `hockeyJourneyPhase` — status only (core).
 *   - current pair    THE HERO'S OWN PAIR, passed in by the host exactly as
 *                     page.tsx resolves it (`resolveProbability`,
 *                     eventKeyStats.ts:962 — `homeProb`, `awayProb`, `homePct`,
 *                     `awayPct`, `probSourceLabel`), with page.tsx:2169's
 *                     `printableAway` applied here, and printed through
 *                     `formatProbabilityPercent` with the hero's integers — so
 *                     the matrix and the hero cannot round one price twice.
 *                     "Current" versus "last recorded" is the quote's own clock
 *                     (page.tsx `acceptedPriceClock`) against the page's stale
 *                     window (`SOURCE_STALE_AFTER_MS`, sourceAge.ts:52), as
 *                     native `EventHeadlinePhase9483.resolve`: an undated,
 *                     stale, interrupted, or started-but-not-live pair is "last
 *                     recorded", never "current".
 *   - pregame pair    `prematchReading` (prematchReading.ts:135) with its served
 *                     integers. It carries no clock of its own, so none is printed.
 *   - goals           the event's `home_score`/`away_score`, dated only by the
 *                     producer's `score_observed_at` and named by `score_source`.
 *   - state words     `formatLiveClockLabel` (gameTimeLabel.ts:811), as page.tsx
 *                     :1487 calls it. ESPN's period and clock carry no time of
 *                     their own, so the state line is NEVER dated by the score's
 *                     clock: it says "Game state from ESPN".
 *   - forecasts       before the start `eventPageProjectedPair` (projectedFinalPair
 *                     .ts:311) under the hero line's own gates (page.tsx:1805-1866);
 *                     during play only the producer's admitted in-play pair
 *                     (`admittedLiveProjection` → `liveCardProjectedFinal`) and
 *                     `livePregameComparison`; after the final
 *                     `finalForecastComparison`. Today all of them refuse hockey,
 *                     so every hockey forecast slot prints its absence words —
 *                     never a reference value. An admitted pair prints at its own
 *                     precision (`formatPoints`, a whole number whole, otherwise
 *                     one decimal). During play, when no in-play object is
 *                     served, web's page line falls back to the ladders
 *                     (`pm_spread_data.projected_final`); this screen follows
 *                     native and says "No in-game forecast" (see report).
 *                     The before-the-start ladder pair is read ONLY from this
 *                     game's own `/history` body (`ownHockeyHistory`: exact
 *                     `event_id`); another game's body supplies no forecast.
 *   - history         `hockeyJourneyHistory` over the held `/history` body, only
 *                     when it is this game's own (#10868 hockey F1). OWNERSHIP IS
 *                     DECIDED ONCE in `buildHockeyJourney`, and the chart and the
 *                     before-the-start forecast each check it again. A foreign
 *                     body reads exactly as a missing one: "History unavailable",
 *                     no borrowed point, series id, note or control. No name or
 *                     time matching.
 *   - props           the held `/game-markets` body (stories and All props), only
 *                     when its `event_id` is exactly this game's id
 *                     (`ownHockeyMarkets`, #10868 F1b), decided once in
 *                     `buildHockeyJourney`; the points/assists ladders and the
 *                     originals each check it again. Another game's body reads
 *                     as a missing one: no card, story, original, id, grade or
 *                     count.
 *   - result          `servedOutcome` — the served verdict, else the scores.
 *   - names / tints   `teamShortNames` (teamShortName.ts:1220), `teamTextColor`
 *                     (teamColors.ts:140).
 *   - source names    the served `win_probability_sources[...].display_name`
 *                     only; an unnamed source is left unnamed rather than guessed.
 *
 * Nothing here fetches, subscribes, schedules or holds state; the host passes
 * what it already holds and `nowMs`.
 */

import type { GameMarketsResponse } from "@/lib/api";
import type { EventDetailResponse, EventHistoryResponse } from "@/lib/types";
import { printableAway } from "@/lib/drawPricedWinner";
import { prematchReading } from "@/lib/prematchReading";
import {
  admittedLiveProjection,
  eventPageProjectedPair,
  liveCardProjectedFinal,
  projectedFinalLabel,
  sportsbookProjectedPair,
  type ProjectedScorePair,
  type SportsbookProjectionFields,
} from "@/lib/projectedFinalPair";
import { finalForecastComparison, finalScorePeriod } from "@/lib/finalForecastComparison";
import { livePregameComparison } from "@/lib/livePregameComparison";
import { sportVocab } from "@/lib/marketMapUtils";
import { SOURCE_STALE_AFTER_MS, sourceIsStale } from "@/lib/sourceAge";
import { formatLiveClockLabel } from "@/lib/gameTimeLabel";
import { isFinishedStatus, isSuspendedStatus } from "@/lib/eventState";
import { teamShortNames } from "@/lib/teamShortName";
import { teamTextColor } from "@/lib/teamColors";
import {
  absentSlot,
  clockWords,
  dayWords,
  forecastSlot,
  goalsSlot,
  hasStartedByClock,
  hockeyJourneyPhase,
  joined,
  parseMs,
  probabilitySlot,
  servedOutcome,
  sourceWord,
  timeWords,
  type HockeyJourneyPhase,
  type HockeyJourneySlot,
} from "./hockeyJourneyCore";
import { hockeyJourneyHistory, ownHockeyHistory, type HockeyJourneyHistory } from "./hockeyJourneyHistory";
import {
  hockeyJourneyContribution,
  hockeyJourneyOriginals,
  ownHockeyMarkets,
  type HockeyJourneyContribution,
  type HockeyJourneyOriginals,
} from "./hockeyJourneyProps";

import type {
  HockeyJourneyColumn,
  HockeyJourneyHeadline,
  HockeyJourneyMatrix,
  HockeyJourneyMatrixRow,
  HockeyJourneyTeam,
} from "./hockeyJourneyTypes";

export * from "./hockeyJourneyCore";
export * from "./hockeyJourneyHistory";
export * from "./hockeyJourneyProps";
export type {
  HockeyJourneyColumn,
  HockeyJourneyHeadline,
  HockeyJourneyMatrix,
  HockeyJourneyMatrixRow,
  HockeyJourneyTeam,
} from "./hockeyJourneyTypes";

export const MATRIX_WORDS = {
  winChance: "Win chance",
  currentChance: "Current chance",
  lastRecordedChance: "Last recorded chance",
  openingLine: "Opening line",
  pregameChance: "Pregame chance",
  projectedGoals: "Projected goals",
  goals: "Goals",
  finalGoals: "Final goals",
  projectedFinal: "Projected final",
  pregameForecast: "Pregame forecast",
  noChance: "No recorded chance",
  noScore: "Score unavailable",
  noPregameForecast: "No pregame forecast",
  noInGameForecast: "No in-game forecast",
  // The live projection exists but fails admission (stale or unbacked): availability words, not machinery.
  forecastWithheld: "Forecast unavailable",
  // The TEAM's result after the final — not a prop verdict, so not lib/propGrade's
  // vocabulary. Web has no exported team-result word: the settled event hero
  // spells "Won" inline (SettledOutcomeHero.tsx) and prints no loser word, and
  // `resolveEventOutcome` names a winner, not a word. Kept here; native prints
  // the same "Won" / "Lost".
  won: "Won",
  lost: "Lost",
  spokenLabel: "Hockey win chances, score and forecast",
  aboutLabel: "About these sources",
  stateSource: "Game state from ESPN",
  result: "Result",
} as const;

export const PAGE_WORDS = {
  streamHeading: "Expectations and performance",
  manualStatus: "Use Previous or Next to see each story",
  storiesLabel: "Game stories",
  storyUnavailable: "This story isn’t available for this game state. Every original is still in All props.",
  matrixUnavailable: "Comparison unavailable for this game state",
  previous: "Previous",
  next: "Next",
} as const;

/**
 * The hero's resolved pair, exactly as page.tsx destructures
 * `resolveProbability`'s result BEFORE its `printableAway` step.
 */
export interface HockeyJourneyHeroPair {
  homeProb: number | null;
  awayProb: number | null;
  homePct: number | null;
  awayPct: number | null;
  probSourceLabel?: string | null;
}

/** What the host already holds, passed in unchanged. */
export interface HockeyJourneyHost {
  nowMs: number;
  /** page.tsx `resolvedProbability` (the hero's own pair), or null before it resolves. */
  hero: HockeyJourneyHeroPair | null;
  /** page.tsx `acceptedPriceClock`. Null is undated: "last recorded", never "current". */
  probabilityObservedAt: string | null;
  /** True while the page says live delivery is interrupted. */
  deliveryInterrupted?: boolean;
}

export interface HockeyJourneyStory {
  id: "points" | "assists";
  name: string;
  exploreLabel: string;
}

export interface HockeyJourneyViewModel {
  eventId: number;
  phase: HockeyJourneyPhase;
  header: { title: string; aboutLabel: string };
  headline: HockeyJourneyHeadline;
  history: HockeyJourneyHistory;
  points: HockeyJourneyContribution | null;
  assists: HockeyJourneyContribution | null;
  /** The stories this phase has content for, in the screen's fixed order. No ranking, no timer. */
  stories: HockeyJourneyStory[];
  originals: HockeyJourneyOriginals;
  /** Every provenance line the screen prints, for the About disclosure. */
  about: string[];
  /**
   * True only when `about` carries every column's own source/clock line
   * ("<title>: <provenance>") — checked, not assumed. Then the matrix leaves
   * them to About, as native does when a readable About entry exists
   * (`HockeyJourneyHeadlineModel10868.inlineProvenance`); otherwise it keeps
   * them inline.
   */
  provenanceInAbout: boolean;
  copy: {
    streamHeading: string;
    manualStatus: string | null;
    storiesLabel: string;
    storyUnavailable: string;
    matrixUnavailable: string;
    allPropsLabel: string | null;
  };
  /** Served team colours for the chart's CSS variables (page.tsx's `teamColorStyle` input). */
  colors: { home: string | null; away: string | null };
}

// ─── Header and state ──────────────────────────────────────────────────────

function score(event: EventDetailResponse): { home: number; away: number } | null {
  const { home_score: home, away_score: away } = event;
  return typeof home === "number" && typeof away === "number" && home >= 0 && away >= 0 ? { home, away } : null;
}

export function hockeyJourneyHeader(event: EventDetailResponse, phase: HockeyJourneyPhase): { title: string; aboutLabel: string } {
  const s = score(event);
  let title: string;
  if (phase === "before") title = `${event.home_team} vs ${event.away_team}`;
  else if (phase === "live") title = s ? `${event.home_team} ${s.home}–${s.away} ${event.away_team}` : `${event.home_team} vs ${event.away_team}`;
  else title = s ? `Final: ${event.home_team} ${s.home}–${s.away} ${event.away_team}` : `Final: ${event.home_team} vs ${event.away_team}`;
  return { title, aboutLabel: MATRIX_WORDS.aboutLabel };
}

export function hockeyJourneyState(
  event: EventDetailResponse,
  phase: HockeyJourneyPhase,
): { state: string; context: string | null } {
  const start = parseMs(event.commence_time);
  if (phase === "before") {
    if (start === null) return { state: "Before game", context: null };
    if (event.start_is_tbd === true) return { state: "Before game · start time to be announced", context: dayWords(start) };
    return { state: `Before game · ${timeWords(start)} start`, context: dayWords(start) };
  }
  if (phase === "live") {
    const period = event.espn?.period;
    const clock = event.espn?.game_clock;
    const label = formatLiveClockLabel(period, clock, " · ");
    const state = label || (isSuspendedStatus(event.status) ? "Play suspended" : "Live");
    const hasState = !!(period && period.trim()) || !!(clock && clock.trim());
    return { state, context: hasState ? MATRIX_WORDS.stateSource : null };
  }
  return { state: "Final", context: start === null ? null : dayWords(start) };
}

// ─── Slots ─────────────────────────────────────────────────────────────────

interface PairSlots {
  title: string;
  home: HockeyJourneySlot;
  away: HockeyJourneySlot;
  provenance: string | null;
}

/** The served display name for a probability source, or null. */
function sourceName(source: string | null | undefined, event: EventDetailResponse): string | null {
  if (!source) return null;
  const served = event.win_probability_sources?.[source]?.display_name;
  return served && served !== source ? served : null;
}

/** "Current" only for a dated, fresh, delivered quote on a game that is live or not yet started. */
export function heroReadingIsCurrent(event: EventDetailResponse, host: HockeyJourneyHost): boolean {
  if (host.deliveryInterrupted) return false;
  if (parseMs(host.probabilityObservedAt) === null) return false;
  if (sourceIsStale(host.probabilityObservedAt, host.nowMs, SOURCE_STALE_AFTER_MS)) return false;
  if (event.status === "live") return true;
  return !hasStartedByClock(event.commence_time, host.nowMs);
}

/** The pair the hero prints, through the hero's own integers. Null when it prints none. */
export function heroPair(event: EventDetailResponse, host: HockeyJourneyHost): PairSlots | null {
  const hero = host.hero;
  if (!hero || typeof hero.homeProb !== "number" || !Number.isFinite(hero.homeProb)) return null;
  const away = printableAway(hero.awayProb, event.sport);
  if (typeof away !== "number" || !Number.isFinite(away)) return null;
  const awayPct = printableAway(hero.awayPct, event.sport);
  const opening = hero.probSourceLabel === MATRIX_WORDS.openingLine;
  const title = opening
    ? MATRIX_WORDS.openingLine
    : heroReadingIsCurrent(event, host)
      ? MATRIX_WORDS.currentChance
      : MATRIX_WORDS.lastRecordedChance;
  const clock = clockWords(host.probabilityObservedAt);
  return {
    title,
    home: probabilitySlot(hero.homeProb, hero.homePct),
    away: probabilitySlot(away, awayPct),
    provenance: joined([clock ? `Recorded ${clock}` : null, sourceName(event.hero_probability_source, event)]),
  };
}

/** The last reading before the start, through `prematchReading`. */
export function pregamePair(event: EventDetailResponse): PairSlots | null {
  const reading = prematchReading({ prematch_odds: event.prematch_odds, opening_odds: event.opening_odds });
  if (!reading) return null;
  // `prematchReading` reads the served ladder when its home value is usable
  // (strictly inside 0…1), else `opening_odds` — the same test, said here so
  // the caption can say which: "Pre-match" for the ladder, "Opened" otherwise.
  const servedHome = event.prematch_odds?.home_probability;
  const isServed = typeof servedHome === "number" && Number.isFinite(servedHome) && servedHome > 0 && servedHome < 1;
  return {
    title: MATRIX_WORDS.pregameChance,
    home: probabilitySlot(reading.homeProbability, reading.homePercent),
    away: probabilitySlot(reading.awayProbability, reading.awayPercent),
    provenance: joined([isServed ? "Pre-match" : "Opened", isServed ? sourceName(reading.source, event) : null]),
  };
}

function liveOdds(event: EventDetailResponse): SportsbookProjectionFields | undefined {
  return event.current_odds as SportsbookProjectionFields | undefined;
}

/**
 * Before the start: the pair `eventPageProjectedPair` hands the hero line,
 * under that line's own gates (page.tsx:1805-1866: a derived spread, a possible
 * result, both halves above zero), printed at its own precision. The ladder
 * pair comes only from this game's own body (`ownHockeyHistory`); a foreign or
 * missing body supplies none, and the game's own sportsbook pair still prints.
 */
export function beforeForecast(
  event: EventDetailResponse,
  history: EventHistoryResponse | null | undefined,
): PairSlots | null {
  const pair = eventPageProjectedPair({
    odds: liveOdds(event),
    sportKey: event.sport,
    commenceTime: event.commence_time,
    isLive: false,
    ladderPair: ownHockeyHistory(history, event)?.pm_spread_data?.projected_final,
  });
  if (!pair) return null;
  const vocab = sportVocab(event.sport || undefined);
  const possible = vocab.canEndInATie || Math.round(pair.home_score) !== Math.round(pair.away_score);
  if (!vocab.hasDerivedSpread || !possible || !(pair.home_score > 0) || !(pair.away_score > 0)) return null;
  const fromSportsbooks = sportsbookProjectedPair(liveOdds(event), event.sport) !== null;
  const books = event.current_odds?.bookmaker_count;
  const provenance = fromSportsbooks
    ? typeof books === "number"
      ? `Before the start · ${books} ${books === 1 ? "sportsbook" : "sportsbooks"}`
      : "Sportsbooks before the start"
    : "Prediction-market lines before the start";
  return {
    title: MATRIX_WORDS.projectedGoals,
    home: forecastSlot(pair.home_score),
    away: forecastSlot(pair.away_score),
    provenance,
  };
}

/** page.tsx's live predicate: `status === "live"` and the listed start passed. */
function pageIsLive(event: EventDetailResponse, nowMs: number): boolean {
  const start = parseMs(event.commence_time);
  return event.status === "live" && start !== null && start <= nowMs;
}

/**
 * During play: the producer's admitted in-play pair, rounded and gated as the
 * live card prints it (`liveCardProjectedFinal`), or the slot's absence words.
 */
export function liveForecast(
  event: EventDetailResponse,
  nowMs: number,
): { home: HockeyJourneySlot; away: HockeyJourneySlot; provenance: string | null; admitted: ProjectedScorePair | null } {
  const none = (words: string) => ({ home: absentSlot(words), away: absentSlot(words), provenance: null, admitted: null });
  if (!pageIsLive(event, nowMs)) return none(MATRIX_WORDS.noInGameForecast);
  const odds = liveOdds(event);
  if (odds?.live_projection == null) return none(MATRIX_WORDS.noInGameForecast);
  if (!admittedLiveProjection(odds, event.sport, event.commence_time)) return none(MATRIX_WORDS.forecastWithheld);
  const printed = liveCardProjectedFinal(odds, event.sport, event.commence_time, {
    home: event.home_score,
    away: event.away_score,
  });
  if (!printed) return none(MATRIX_WORDS.forecastWithheld);
  return {
    home: goalsSlot(printed.home),
    away: goalsSlot(printed.away),
    provenance: projectedFinalLabel(event.sport),
    admitted: printed,
  };
}

/** After the final: the comparison `finalForecastComparison` admits, its served halves at their own precision. */
export function finalForecast(event: EventDetailResponse): PairSlots | null {
  const comparison = finalForecastComparison({
    sportKey: event.sport,
    status: event.status,
    homeScore: event.home_score,
    awayScore: event.away_score,
    actualPeriod: finalScorePeriod(event.sport, event.final_score_period),
    projection: event.pregame_projection,
  });
  const projection = event.pregame_projection;
  if (!comparison || !projection) return null;
  const n = comparison.details.bookmakerCount;
  return {
    title: MATRIX_WORDS.pregameForecast,
    home: forecastSlot(projection.projected_home_score),
    away: forecastSlot(projection.projected_away_score),
    provenance: `${comparison.label} · ${n} ${n === 1 ? "sportsbook" : "sportsbooks"}`,
  };
}

/** The score, dated by the producer's own observation clock. */
export function goalSlots(event: EventDetailResponse): { home: HockeyJourneySlot; away: HockeyJourneySlot; provenance: string | null } {
  const s = score(event);
  if (!s) return { home: absentSlot(MATRIX_WORDS.noScore), away: absentSlot(MATRIX_WORDS.noScore), provenance: null };
  const observed = clockWords(event.score_observed_at);
  return {
    home: goalsSlot(s.home),
    away: goalsSlot(s.away),
    provenance: joined([event.score_source ? sourceWord(event.score_source) : null, observed ? `score observed ${observed}` : null]),
  };
}

// ─── The matrix ────────────────────────────────────────────────────────────

export function hockeyJourneyMatrix(
  event: EventDetailResponse,
  phase: HockeyJourneyPhase,
  history: EventHistoryResponse | null | undefined,
  host: HockeyJourneyHost,
): HockeyJourneyMatrix {
  const W = MATRIX_WORDS;
  if (phase === "before") {
    const chance = heroPair(event, host);
    const forecast = beforeForecast(event, history);
    return {
      phase,
      columns: [
        { title: chance?.title ?? W.winChance, provenance: chance?.provenance ?? null },
        { title: W.projectedGoals, provenance: forecast?.provenance ?? null },
      ],
      rows: [
        { side: "home", values: [chance?.home ?? absentSlot(W.noChance), forecast?.home ?? absentSlot(W.noPregameForecast)], result: null },
        { side: "away", values: [chance?.away ?? absentSlot(W.noChance), forecast?.away ?? absentSlot(W.noPregameForecast)], result: null },
      ],
      lead: 0,
      groups: [[0, 1]],
    };
  }
  if (phase === "live") {
    const pregame = pregamePair(event);
    const current = heroPair(event, host);
    const goals = goalSlots(event);
    const projected = liveForecast(event, host.nowMs);
    return {
      phase,
      columns: [
        { title: W.pregameChance, provenance: pregame?.provenance ?? null },
        { title: current?.title ?? W.lastRecordedChance, provenance: current?.provenance ?? null },
        { title: W.goals, provenance: goals.provenance },
        { title: W.projectedFinal, provenance: projected.provenance },
      ],
      rows: [
        {
          side: "home",
          values: [pregame?.home ?? absentSlot(W.noChance), current?.home ?? absentSlot(W.noChance), goals.home, projected.home],
          result: null,
        },
        {
          side: "away",
          values: [pregame?.away ?? absentSlot(W.noChance), current?.away ?? absentSlot(W.noChance), goals.away, projected.away],
          result: null,
        },
      ],
      lead: 1,
      groups: [
        [0, 1],
        [2, 3],
      ],
    };
  }
  const pregame = pregamePair(event);
  const goals = goalSlots(event);
  const forecast = finalForecast(event);
  const outcome = servedOutcome(event.status, event.home_score, event.away_score, event.hero_settled_result);
  const homeResult = outcome === "home" ? W.won : outcome === "away" ? W.lost : null;
  const awayResult = outcome === "away" ? W.won : outcome === "home" ? W.lost : null;
  return {
    phase,
    columns: [
      { title: W.pregameChance, provenance: pregame?.provenance ?? null },
      { title: W.finalGoals, provenance: goals.provenance },
      { title: W.pregameForecast, provenance: forecast?.provenance ?? null },
    ],
    rows: [
      {
        side: "home",
        values: [pregame?.home ?? absentSlot(W.noChance), goals.home, forecast?.home ?? absentSlot(W.noPregameForecast)],
        result: homeResult,
      },
      {
        side: "away",
        values: [pregame?.away ?? absentSlot(W.noChance), goals.away, forecast?.away ?? absentSlot(W.noPregameForecast)],
        result: awayResult,
      },
    ],
    lead: 0,
    groups: [[0], [1, 2]],
  };
}

/** During play: the retained pregame forecast beneath an admitted current one. */
function historicalForecast(
  event: EventDetailResponse,
  names: { home: string; away: string },
  nowMs: number,
): { title: string; reading: string } | null {
  const admitted = liveForecast(event, nowMs).admitted;
  if (!admitted) return null;
  const comparison = livePregameComparison({
    sportKey: event.sport,
    status: event.status,
    isLive: pageIsLive(event, nowMs),
    commenceTime: event.commence_time,
    odds: liveOdds(event),
    heroProjected: admitted,
    projection: event.pregame_projection,
  });
  if (!comparison) return null;
  return {
    title: MATRIX_WORDS.pregameForecast,
    reading: `${names.away} ${comparison.baseline.away} · ${names.home} ${comparison.baseline.home}`,
  };
}

export function hockeyJourneyHeadline(
  event: EventDetailResponse,
  history: EventHistoryResponse | null | undefined,
  host: HockeyJourneyHost,
): HockeyJourneyHeadline {
  const phase = hockeyJourneyPhase(event, host.nowMs);
  const names = teamShortNames(
    { name: event.home_team, abbreviation: event.home_team_data?.abbreviation },
    { name: event.away_team, abbreviation: event.away_team_data?.abbreviation },
    event.sport,
  );
  const state = hockeyJourneyState(event, phase);
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
    matrix: hockeyJourneyMatrix(event, phase, history, host),
    historicalForecast: phase === "live" ? historicalForecast(event, names, host.nowMs) : null,
    spokenLabel: MATRIX_WORDS.spokenLabel,
  };
}

// ─── The whole page ────────────────────────────────────────────────────────

/** A column's source/clock line as About prints it: "Final goals: ESPN · score observed …". */
export function matrixProvenanceLine(column: HockeyJourneyColumn): string {
  return `${column.title}: ${column.provenance ?? ""}`;
}

export function allPropsLabel(count: number | null): string | null {
  if (count === null || count <= 0) return null;
  return count === 1 ? "1 original outcome" : `All ${count} original outcomes`;
}

export interface HockeyJourneyInput {
  /** The event the page already holds (`["event", id]`). */
  event: EventDetailResponse;
  /**
   * The `/history` body the page already holds (`["history", id, full]`). Used
   * only when its `event_id` is exactly `event.id`; any other body reads as missing.
   */
  history: EventHistoryResponse | null | undefined;
  /**
   * The `/game-markets` body the page already holds (its `gameMarkets` memo).
   * Used only when its `event_id` is exactly `event.id`; any other body reads as missing.
   */
  gameMarkets: GameMarketsResponse | null | undefined;
  host: HockeyJourneyHost;
}

/**
 * The whole screen's view model. Pure: same inputs, same answer. A missing
 * history response (not arrived, or failed) leaves ONLY the chart slot
 * unavailable: the matrix, stories and All props compose from their own inputs
 * (native `HockeyJourneyEventPageHostAdapter10868.build`). A body for another
 * game is decided here, once, to be no body at all: the chart reads "History
 * unavailable" and no forecast is read from it. The same holds for another
 * game's `/game-markets` body: no points or assists story, no original, no
 * All props count.
 */
export function buildHockeyJourney({ event, history, gameMarkets, host }: HockeyJourneyInput): HockeyJourneyViewModel {
  const phase = hockeyJourneyPhase(event, host.nowMs);
  const own = ownHockeyHistory(history, event);
  const ownMarkets = ownHockeyMarkets(gameMarkets, event);
  const headline = hockeyJourneyHeadline(event, own, host);
  const historyModel = hockeyJourneyHistory(own, event, phase, host.nowMs);
  const points = hockeyJourneyContribution("points", event, ownMarkets, host.nowMs);
  const assists = hockeyJourneyContribution("assists", event, ownMarkets, host.nowMs);
  const originals = hockeyJourneyOriginals(event, ownMarkets, host.nowMs);
  const stories: HockeyJourneyStory[] = [];
  if (points) stories.push({ id: "points", name: points.title, exploreLabel: "Explore points" });
  if (assists) stories.push({ id: "assists", name: assists.title, exploreLabel: "Explore assists" });
  const about = [
    ...headline.matrix.columns.flatMap((c) => (c.provenance ? [matrixProvenanceLine(c)] : [])),
    ...(headline.stateContext && phase === "live" ? [headline.stateContext] : []),
    ...historyModel.notes,
  ];
  const provenanceInAbout = headline.matrix.columns.every(
    (c) => !c.provenance || about.includes(matrixProvenanceLine(c)),
  );
  return {
    eventId: event.id,
    phase,
    header: hockeyJourneyHeader(event, phase),
    headline,
    history: historyModel,
    points,
    assists,
    stories,
    originals,
    about,
    provenanceInAbout,
    copy: {
      streamHeading: PAGE_WORDS.streamHeading,
      manualStatus: stories.length > 1 ? PAGE_WORDS.manualStatus : null,
      storiesLabel: PAGE_WORDS.storiesLabel,
      storyUnavailable: PAGE_WORDS.storyUnavailable,
      matrixUnavailable: PAGE_WORDS.matrixUnavailable,
      allPropsLabel: allPropsLabel(originals.originals.length),
    },
    colors: {
      home: event.home_team_data?.primary_color ?? null,
      away: event.away_team_data?.primary_color ?? null,
    },
  };
}

/** Whether the page should mount this screen: hockey only (`sportVocab`'s hockey row). */
export function hockeyJourneyApplies(sportKey: string | null | undefined): boolean {
  const key = (sportKey ?? "").toLowerCase();
  return key.startsWith("icehockey_");
}

/** Re-exported so a host can test "finished" exactly as this screen does. */
export const hockeyJourneyIsFinished = isFinishedStatus;
