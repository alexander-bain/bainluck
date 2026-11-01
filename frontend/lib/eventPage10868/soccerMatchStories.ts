/**
 * #10868 — THE SOCCER MATCH SCREEN (web), THE PROP STORIES: ONE ORIGINAL
 * OUTCOME'S READINGS, AND THE GOAL, BOTH-TEAMS, FIRST-TEAM, HALF-BY-HALF AND
 * EXACT-SCORE CARDS.
 *
 * PILLARS: FORMATTING / TRUTH. SHIP: every soccer prop story prints, for each
 * original outcome, the same pre-match chance, in-play reading and result the
 * iPhone screen prints — or that slot's own words.
 *
 * The web port of native `SoccerPropReadingAdapter10868` (part three) and of
 * `SoccerGoalsAdapter10868`, `SoccerBothTeamsAdapter10868`,
 * `SoccerFirstTeamAdapter10868`, `SoccerHalvesAdapter10868` and
 * `SoccerExactScoreAdapter10868` (parts four to seven and ten), at 274369bc.
 * Read their headers for the full reasoning. Web authorities used, and native
 * rules ported where web has no twin:
 *
 *   - WHICH MARKET   the owner's typed admission (`SoccerMatchAdmission`), by
 *                    exact venue market id — never a title or a position.
 *                    PRODUCTION HAS NO OWNER for it yet (native host header, SoccerEventPageHostAdapter10868.swift:30-36),
 *                    so a real page passes none and every story is absent;
 *                    only tests pass CONSTRUCTED admissions.
 *   - legs           every served row of that market id, in served order:
 *                    `totals`, `spreads`, `team_totals`, `period_markets` (their
 *                    clock can be a sibling's, served `observed_at_basis:
 *                    "capped_to_sibling"`), then `other` (own clock). Native
 *                    `SoccerPropReadingAdapter10868.legs` (L227–244).
 *   - identity       contributor outcome ids joined "+", else
 *                    `market_name-outcome_name` (native L250-260).
 *   - matrix         the option for the SAME market and contributor outcomes,
 *                    only in the known contract at game scope (`MATRIX_CONTRACT`,
 *                    nbaEventCards.ts:34; display scope "game" or absent) —
 *                    native `admittedMatrix` / `option` (L268-289).
 *   - pre-match      before the start (`propsHaveStarted`, hockeyJourneyProps.ts,
 *                    the web twin of `HockeyJourneyContributionAdapter10868
 *                    .hasStarted`): the row's own price (`catalogQuote`,
 *                    questionCatalog.ts:100) while `isRecentQuote` finds its own
 *                    clock recent, own-clock rows only. Once started: the
 *                    producer's pin through web's twin of `NBALadderCard9483.pin`
 *                    — `decodeQuestionMatrix`'s `baseline`, else its admitted
 *                    `pregame_reading` (nbaEventCards.ts:97-176; the web reading
 *                    arm also asks `reason: null` and a quoted/result value
 *                    state, stricter than native) — kept only when observed
 *                    strictly before the listed start. No pin: "not recorded"
 *                    only on the producer's own `no_pregame_pin` reason
 *                    (native `preMatchAbsence`, L439-441).
 *   - in-play        native `current` (L370-381) in its order; a period row
 *                    (an admitted half) is never the current chance
 *                    (`periodCurrent`, L390-399).
 *   - result         `servedSettlement` (the web twin of H4's settlement), left
 *                    unconfirmed when the matrix grade disagrees (L401-405).
 *                    Unknown is not loss. Verdict words are web's one settled
 *                    vocabulary (`propVerdictLabel`, lib/propGrade.ts); native
 *                    says OutcomeVerdict's "Won" / "Lost" (platform difference,
 *                    as hockey's All props).
 *   - words          `formatProbabilityPercent`, `sourceLabel`, and the hockey
 *                    core's `clockWords` / `timeWords` (web's one stamp formatter).
 *
 * PURE: no fetch, no subscription, no timer, no ranking. `nowMs` is a parameter.
 */

import type { GameMarketsResponse } from "@/lib/api";
import type { EventDetailResponse, EventHistoryResponse } from "@/lib/types";
import { decodeQuestionMatrix, MATRIX_CONTRACT } from "@/lib/nbaEventCards";
import { isRecentQuote } from "@/lib/nflEventCardDeck";
import { catalogQuote } from "@/lib/questionCatalog";
import { propOutcomeSide } from "@/lib/propOutcomeSide";
import { formatProbabilityPercent } from "@/lib/probabilityDisplay";
import { propVerdictLabel } from "@/lib/propGrade";
import { sourceLabel } from "@/lib/sourceLabels";
import { admissible, clockWords, joined, parseMs, servedSettlement, timeWords } from "./hockeyJourneyCore";
import { ORIGINALS_WORDS, propsHaveStarted, type HockeyJourneyMarketRow } from "./hockeyJourneyProps";
import type {
  SoccerBothCard,
  SoccerCurrent,
  SoccerExactCard,
  SoccerExactOriginal,
  SoccerExactPlacement,
  SoccerExactScope,
  SoccerFirstCard,
  SoccerGoalsActual,
  SoccerGoalsCard,
  SoccerGoalsMilestone,
  SoccerHalfCell,
  SoccerHalfSeries,
  SoccerHalvesCard,
  SoccerMatchPhase,
  SoccerObservation,
  SoccerPregame,
  SoccerReadingRow,
  SoccerResult,
  SoccerStoryId,
  SoccerTeamGoals,
  SoccerTiming,
} from "./soccerMatchTypes";

// ─── The owner's admission ─────────────────────────────────────────────────

/** One period of the half-by-half story: its market and the owner's period identity and words. */
export interface SoccerHalfAdmission {
  marketId: number;
  periodId: string;
  label: string;
}

/** One listed original of an exact-score scope (native `Descriptor.Original`). */
export interface SoccerExactDescriptorOriginal {
  outcomeIds: number[];
  placement: SoccerExactPlacement;
  label: string;
}

/** One exact-score market (native `Descriptor.Scope`). */
export interface SoccerExactDescriptorScope {
  id: string;
  label: string;
  marketId: number;
  periodId: string | null;
  homeGoals: number[];
  awayGoals: number[];
  scaleUpper: number;
  originals: SoccerExactDescriptorOriginal[];
}

/** The owner's explicit exact-score metadata for one event (native `SoccerExactScoreAdapter10868.Descriptor`). */
export interface SoccerExactDescriptor {
  eventId: number;
  scopes: SoccerExactDescriptorScope[];
}

/**
 * The owner's admission: which exact venue markets each story reads (native
 * `SoccerPropReadingAdapter10868.Markets`). NO PRODUCTION OWNER SUPPLIES THIS
 * YET; the page passes `NO_SOCCER_ADMISSION` and every story is absent.
 */
export interface SoccerMatchAdmission {
  /** Full-match goal totals, in milestone order. */
  goals: number[];
  both: number | null;
  first: number | null;
  /** In period order. */
  halves: SoccerHalfAdmission[];
  /** Goal markets whose row clock the owner has proved is the row's own. None can be supplied today. */
  ownClockGoals: number[];
  exactScore: SoccerExactDescriptor | null;
}

export const NO_SOCCER_ADMISSION: SoccerMatchAdmission = {
  goals: [],
  both: null,
  first: null,
  halves: [],
  ownClockGoals: [],
  exactScore: null,
};

// ─── Words ─────────────────────────────────────────────────────────────────

/** Native `SoccerPropReadingAdapter10868.Words` (L180–205). */
export const READING_WORDS = {
  preMatchNotRecorded: "Pre-match chance not recorded",
  preMatchUnavailable: "Pre-match chance unavailable",
  /** `AllMarketsCatalogView9483.unavailablePrice` — web's `ORIGINALS_WORDS.unavailablePrice`. */
  chanceUnavailable: ORIGINALS_WORDS.unavailablePrice,
  /** `AllMarketsCatalogView9483.noRecentPrice` — web's `ORIGINALS_WORDS.noRecentPrice`. */
  noRecentUpdate: ORIGINALS_WORDS.noRecentPrice,
  inPlayUnavailable: "In-play chance unavailable",
  settledNoChance: "No current chance after settlement",
  resultUnavailable: "Result unavailable",
  notStarted: "Not started",
  savedBeforeStart: "saved before kickoff",
  recorded: "recorded",
  final: "Final",
} as const;

/** The known producer's statement that no pre-match pin was recorded (`TennisOriginalsAdapter10868.noPregamePinReason`). */
export const NO_PREGAME_PIN_REASON = "no_pregame_pin";

// ─── Legs ──────────────────────────────────────────────────────────────────

/** The admitted matrix option for one market and contributor set (native `QuestionMatrixOption`, the fields read). */
export interface SoccerMatrixOption {
  side: string | null;
  comparisonReason: string | null;
  /** The producer's `won` / `lost` grade; anything else is no grade. */
  resultIsWinner: boolean | null;
  /** The producer's pregame pin through web's `decodeQuestionMatrix` (baseline, else admitted reading). */
  pin: { probability: number; observedAt: string } | null;
}

/** One served original outcome of an admitted market (native `Leg`). */
export interface SoccerLeg {
  marketId: number;
  id: string;
  label: string;
  row: HockeyJourneyMarketRow;
  contributors: number[];
  threshold: number | null;
  /** False for a `GameMarketOutcome`-array row, whose clock can be a sibling's. */
  clockIsOwn: boolean;
  option: SoccerMatrixOption | null;
}

type Raw = Record<string, unknown>;
const obj = (v: unknown): Raw | null => (v && typeof v === "object" && !Array.isArray(v) ? (v as Raw) : null);
const finite = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const ints = (v: unknown): number[] =>
  Array.isArray(v) ? v.filter((x): x is number => typeof x === "number" && Number.isInteger(x)) : [];
/** Native `Set(a) == Set(b)`: the same outcome ids, whatever their order or repeats. */
const sameSet = (a: readonly number[], b: readonly number[]): boolean => {
  const left = new Set(a);
  const right = new Set(b);
  return left.size === right.size && [...left].every((id) => right.has(id));
};

/** The game matrix's raw questions, only in the known contract at game scope; else none. */
function admittedQuestions(data: GameMarketsResponse | null | undefined): Raw[] {
  const matrix = obj(data?.game_question_matrix);
  if (!matrix || matrix.contract !== MATRIX_CONTRACT) return [];
  const scope = matrix.display_scope;
  if (scope !== undefined && scope !== null && scope !== "game") return [];
  return (Array.isArray(matrix.questions) ? matrix.questions : []).map(obj).filter((q): q is Raw => q !== null);
}

/**
 * Web's twin of `NBALadderCard9483.pin` (NBALadderCard9483.swift:253-265), run on
 * this one raw option. The decoder keys options by `option_key`, which the pin
 * does not read; a keyless option is given one so it is not dropped.
 */
function pinOf(raw: Raw): SoccerMatrixOption["pin"] {
  const keyed = typeof raw.option_key === "string" && raw.option_key ? raw : { ...raw, option_key: "soccer-option" };
  const decoded = decodeQuestionMatrix({
    contract: MATRIX_CONTRACT,
    questions: [{ question_key: "soccer-option", kind: "named_options", options: [keyed] }],
  })[0]?.options[0];
  if (!decoded) return null;
  if (decoded.baseline !== null && decoded.baselineObservedAt) {
    return { probability: decoded.baseline, observedAt: decoded.baselineObservedAt };
  }
  if (decoded.reading !== null && decoded.readingObservedAt) {
    return { probability: decoded.reading, observedAt: decoded.readingObservedAt };
  }
  return null;
}

/**
 * The one admitted option naming exactly this market and these contributor
 * outcomes, or null when none or more than one does (native `option`, L278-289).
 */
export function matrixOption(
  marketId: number,
  contributors: number[],
  data: GameMarketsResponse | null | undefined,
): SoccerMatrixOption | null {
  if (contributors.length === 0) return null;
  const found: Raw[] = [];
  for (const question of admittedQuestions(data)) {
    for (const candidate of Array.isArray(question.options) ? question.options : []) {
      const option = obj(candidate);
      if (!option) continue;
      if (ints(option.market_ids).includes(marketId) && sameSet(ints(option.contributor_outcome_ids), contributors)) {
        found.push(option);
      }
    }
  }
  if (found.length !== 1) return null;
  const raw = found[0];
  const state = obj(raw.result)?.state;
  const reason = obj(raw.comparison)?.reason;
  return {
    side: typeof raw.side === "string" ? raw.side : null,
    comparisonReason: typeof reason === "string" ? reason : null,
    resultIsWinner: state === "won" ? true : state === "lost" ? false : null,
    pin: pinOf(raw),
  };
}

const ARRAYS_WITH_SIBLING_CLOCKS = ["totals", "spreads", "team_totals", "period_markets"] as const;

/** Every served row of `marketId`, in the catalogue's array order and served order within each array. */
export function soccerLegs(marketId: number, data: GameMarketsResponse | null | undefined): SoccerLeg[] {
  if (!data) return [];
  const out: SoccerLeg[] = [];
  const belongs = (row: HockeyJourneyMarketRow) =>
    row._market_id === marketId || (row._market_ids ?? []).includes(marketId);
  const add = (row: HockeyJourneyMarketRow, clockIsOwn: boolean) => {
    const contributors = ints(row.contributor_outcome_ids);
    const outcome = row.outcome_name ?? "";
    const trimmed = outcome.trim();
    out.push({
      marketId,
      id: contributors.length === 0 ? `${row.market_name ?? ""}-${outcome}` : contributors.map(String).join("+"),
      label: trimmed === "" ? (row.market_name ?? "") : trimmed,
      row,
      contributors,
      threshold: clockIsOwn ? null : finite(row.threshold),
      clockIsOwn,
      option: matrixOption(marketId, contributors, data),
    });
  };
  const source = data as unknown as Record<string, HockeyJourneyMarketRow[] | null | undefined>;
  for (const key of ARRAYS_WITH_SIBLING_CLOCKS) for (const row of source[key] ?? []) if (belongs(row)) add(row, false);
  for (const row of source.other ?? []) if (belongs(row)) add(row, true);
  return out;
}

/** Which side of the line a row names (gotcha #17) — `QuestionCatalog9483.lineSide`, as the hockey props restate it. */
export function lineSide(row: HockeyJourneyMarketRow): "over" | "under" | "unreadable" {
  if (row._inverted === true) return "under";
  const side = propOutcomeSide(row.outcome_name);
  if (side !== "unreadable") return side;
  const o = row.outcome_name ?? "";
  if (/\bunder\b/i.test(o)) return "under";
  if (/\bover\b/i.test(o)) return "over";
  return "unreadable";
}

// ─── Readings ──────────────────────────────────────────────────────────────

/** The catalogue's own price for the row, read at the row's own observation instant (or now when undated). */
function quoted(leg: SoccerLeg, event: EventDetailResponse, nowMs: number): number | null {
  const instant = parseMs(leg.row.observed_at) ?? nowMs;
  return admissible(catalogQuote(leg.row, event.status, instant));
}

/** The stored pre-match pin, kept only when its clock is strictly before the listed start (native `pin`, L425-431). */
export function soccerPin(
  option: SoccerMatrixOption | null,
  commenceTime: string | null | undefined,
): { probability: number; atMs: number } | null {
  if (!option?.pin) return null;
  const at = parseMs(option.pin.observedAt);
  const value = admissible(option.pin.probability);
  if (at === null || value === null) return null;
  const start = parseMs(commenceTime);
  if (start !== null && at >= start) return null;
  return { probability: value, atMs: at };
}

/** Why a started original shows no pre-match chance. */
export function preMatchAbsence(option: SoccerMatrixOption | null): string {
  return option?.comparisonReason === NO_PREGAME_PIN_REASON
    ? READING_WORDS.preMatchNotRecorded
    : READING_WORDS.preMatchUnavailable;
}

export function observation(value: number, atMs: number, lead: string, venue: string | null): SoccerObservation {
  const full = `${lead} ${clockWords(atMs) ?? ""}`;
  return {
    probability: value,
    text: formatProbabilityPercent(value),
    clock: timeWords(atMs),
    detail: joined([full, venue]) ?? full,
  };
}

/** Before the start: the row's own price on its own recent clock. Once started: the stored pin, or its absence. */
export function soccerPregame(leg: SoccerLeg, event: EventDetailResponse, nowMs: number): SoccerPregame {
  const venue = sourceLabel(leg.row.source);
  if (propsHaveStarted(event, nowMs)) {
    const pin = soccerPin(leg.option, event.commence_time);
    if (!pin) return { kind: "missing", words: preMatchAbsence(leg.option) };
    return { kind: "value", observation: observation(pin.probability, pin.atMs, READING_WORDS.savedBeforeStart, venue) };
  }
  if (!leg.clockIsOwn) return { kind: "missing", words: READING_WORDS.noRecentUpdate };
  const price = quoted(leg, event, nowMs);
  if (price === null) return { kind: "missing", words: READING_WORDS.chanceUnavailable };
  const at = parseMs(leg.row.observed_at);
  if (at === null || !isRecentQuote(leg.row.observed_at, nowMs)) return { kind: "missing", words: READING_WORDS.noRecentUpdate };
  return { kind: "value", observation: observation(price, at, READING_WORDS.recorded, venue) };
}

/** The served settlement (`servedSettlement`), the web twin of H4's rule. */
function settlement(leg: SoccerLeg): boolean | null {
  return servedSettlement(leg.row.is_winner, leg.row.resolution_source);
}

/** During play, in H4's order, with the sibling-clock refusal. */
export function soccerCurrent(leg: SoccerLeg, event: EventDetailResponse, nowMs: number): SoccerCurrent {
  if (settlement(leg) !== null) return { kind: "unavailable", words: READING_WORDS.settledNoChance };
  const price = quoted(leg, event, nowMs);
  if (price === null) return { kind: "unavailable", words: READING_WORDS.inPlayUnavailable };
  const at = parseMs(leg.row.observed_at);
  if (!leg.clockIsOwn || at === null) return { kind: "withheld", words: READING_WORDS.noRecentUpdate };
  const start = parseMs(event.commence_time);
  if (start !== null && at < start) return { kind: "unavailable", words: READING_WORDS.inPlayUnavailable };
  if (!isRecentQuote(leg.row.observed_at, nowMs)) return { kind: "withheld", words: READING_WORDS.noRecentUpdate };
  return { kind: "recorded", observation: observation(price, at, READING_WORDS.recorded, sourceLabel(leg.row.source)) };
}

/** A period's dated recorded quote, never its current chance (native `Words.periodQuote`). */
export function periodQuote(figure: string, clock: string, venue: string | null): string {
  return joined([READING_WORDS.inPlayUnavailable, `${figure} ${READING_WORDS.recorded} ${clock}`, venue]) ?? READING_WORDS.inPlayUnavailable;
}

/** During play, for a row about one admitted half: never the current chance. */
export function soccerPeriodCurrent(leg: SoccerLeg, event: EventDetailResponse, nowMs: number): SoccerCurrent {
  if (settlement(leg) !== null) return { kind: "unavailable", words: READING_WORDS.settledNoChance };
  const price = quoted(leg, event, nowMs);
  if (price === null) return { kind: "unavailable", words: READING_WORDS.inPlayUnavailable };
  const at = parseMs(leg.row.observed_at);
  if (!leg.clockIsOwn || at === null) return { kind: "withheld", words: READING_WORDS.noRecentUpdate };
  const start = parseMs(event.commence_time);
  if (start !== null && at < start) return { kind: "unavailable", words: READING_WORDS.inPlayUnavailable };
  return {
    kind: "withheld",
    words: periodQuote(formatProbabilityPercent(price), clockWords(at) ?? "", sourceLabel(leg.row.source)),
  };
}

/** The served settlement, unless the matrix grade disagrees. Unknown is not loss. */
export function soccerResult(leg: SoccerLeg): SoccerResult {
  const won = settlement(leg);
  if (won === null) return { kind: "unconfirmed", words: READING_WORDS.resultUnavailable };
  const graded = leg.option?.resultIsWinner;
  if (typeof graded === "boolean" && graded !== won) return { kind: "unconfirmed", words: READING_WORDS.resultUnavailable };
  return won ? { kind: "won" } : { kind: "lost" };
}

/** A result in words: web's one settled vocabulary for a verdict, else its own words. */
export function resultWords(result: SoccerResult): string {
  return result.kind === "unconfirmed" ? result.words : propVerdictLabel(result.kind === "won");
}

const UNCONFIRMED: SoccerResult = { kind: "unconfirmed", words: READING_WORDS.resultUnavailable };

// ─── The score the stories share ───────────────────────────────────────────

export interface SoccerGoals {
  home: number;
  away: number;
  total: number;
  observedAtMs: number | null;
}

export function soccerGoals(event: EventDetailResponse): SoccerGoals | null {
  const { home_score: home, away_score: away } = event;
  if (typeof home !== "number" || typeof away !== "number" || home < 0 || away < 0) return null;
  return { home, away, total: home + away, observedAtMs: parseMs(event.score_observed_at) };
}

/** "Valladolid 4, Albacete 0 · score observed …", or "Final: …". */
function goalsDetail(goals: SoccerGoals, names: { home: string; away: string }, final: boolean): string {
  const pair = `${names.home} ${goals.home}, ${names.away} ${goals.away}`;
  if (final) return `${READING_WORDS.final}: ${pair}`;
  return goals.observedAtMs === null ? pair : `${pair} · score observed ${clockWords(goals.observedAtMs) ?? ""}`;
}

/** "Observed 5:54 AM", "Final", or null when undated. */
function goalsClock(goals: SoccerGoals, final: boolean): string | null {
  if (final) return READING_WORDS.final;
  return goals.observedAtMs === null ? null : `Observed ${timeWords(goals.observedAtMs)}`;
}

// ─── Shared row parts ──────────────────────────────────────────────────────

function pregameLine(title: string, pregame: SoccerPregame): string {
  return `${title}: ${pregame.kind === "value" ? pregame.observation.detail : pregame.words}`;
}

function currentWords(current: SoccerCurrent): string {
  return current.kind === "recorded" ? current.observation.detail : current.words;
}

/** "Result: HIT · settled by Polymarket", or the result's own words. */
function resultLine(title: string, result: SoccerResult, leg: SoccerLeg): string {
  const venue = result.kind === "unconfirmed" ? null : sourceLabel(leg.row.source);
  return joined([`${title}: ${resultWords(result)}`, venue ? `settled by ${venue}` : null]) ?? resultWords(result);
}

// ─── Part four: goals ──────────────────────────────────────────────────────

export const GOALS_WORDS = {
  eyebrow: "TOTAL GOALS · EXPECTATIONS VS ACTUAL",
  beforeTitle: "How many goals?",
  liveTitle: "Goals so far against the milestones",
  finalTitle: "Final goals against the milestones",
  reachedSoFar: "Reached so far",
  scoreUnavailable: "Score unavailable",
  finalScoreUnavailable: "Final score unavailable",
  timingSuffix: "chance timing",
  chartTitle: "Chance of reaching each total",
  axisTitle: "Total goals in the match",
  /** `TotalMilestoneInput10868`'s leaf titles. */
  pregameTitle: "Pregame chance",
  recordedTitle: "Recorded in-game",
  currentStatusTitle: "In-game chance",
  actualSoFarTitle: "Actual so far",
  resultTitle: "Final result",
  countSoFarTitle: "Count so far",
  finalCountTitle: "Final count",
  /** `TotalMilestoneInput10868.milestoneUnavailable` (TotalMilestonePresentation10868.swift:443). */
  selectionUnavailable: "Selected milestone unavailable.",
  /** `TotalMilestoneInput10868` spoken key (TotalMilestonePresentation10868.swift:454-458). */
  spokenHollow: "Hollow marks are pregame chances.",
  spokenFilled: "Filled marks are recorded in-game chances.",
  spokenRule: "The solid rule is the count, not a chance.",
  spokenStrip: "Offered milestones on the count scale; no chances are shown.",
} as const;

const unit = (count: number) => (count === 1 ? "goal" : "goals");

/**
 * The at-least count a line asks for: a whole line itself, a half line the next
 * whole number. No web twin; ported from `MLBFinalReader11284.milestone`
 * (MLBFinalReader11284.swift:507-509).
 */
export function milestoneCount(threshold: number): number {
  return Number.isInteger(threshold) ? threshold : Math.floor(threshold) + 1;
}

/** Nearest even odds among printed chances, ties to the first (`PlayerPropsFamily.defaultTarget`). */
function defaultTarget(probabilities: Array<number | null>): number | null {
  let bestIndex: number | null = null;
  let bestDistance = Infinity;
  for (let index = 0; index < probabilities.length; index += 1) {
    const p = probabilities[index];
    if (p === null) continue;
    const distance = Math.abs(p - 0.5);
    if (distance < bestDistance) {
      bestIndex = index;
      bestDistance = distance;
    }
  }
  return bestIndex;
}

export function soccerGoalsCard(
  event: EventDetailResponse,
  data: GameMarketsResponse | null | undefined,
  admission: SoccerMatchAdmission,
  phase: SoccerMatchPhase,
  names: { home: string; away: string },
  nowMs: number,
): SoccerGoalsCard | null {
  const goals = soccerGoals(event);
  const milestones: SoccerGoalsMilestone[] = [];
  const legs: SoccerLeg[] = [];
  for (const marketId of admission.goals) {
    const overs = soccerLegs(marketId, data).filter((leg) => lineSide(leg.row) === "over" && leg.threshold !== null);
    // One original line per market; two over rows is not one milestone.
    if (overs.length !== 1) continue;
    const served = overs[0];
    const leg = admission.ownClockGoals.includes(marketId) ? { ...served, clockIsOwn: true } : served;
    milestones.push(goalRow(leg, leg.threshold as number, event, phase, goals, nowMs));
    legs.push(leg);
  }
  if (milestones.length === 0) return null;
  // Timing lines name the result's venue from each row's own leg.
  milestones.forEach((row, i) => {
    row.timing = goalTiming(row, legs[i], phase);
  });
  const opening = defaultTarget(milestones.map((m) => (m.pregame.kind === "value" ? m.pregame.observation.probability : null)));
  let actual: SoccerGoalsActual | null = null;
  if (phase !== "before") {
    const final = phase === "final";
    actual = goals
      ? {
          kind: "count",
          title: final ? GOALS_WORDS.finalCountTitle : GOALS_WORDS.countSoFarTitle,
          quantity: goals.total,
          text: `${goals.total}`,
          unit: unit(goals.total),
          clock: goalsClock(goals, final),
          ruleLabel: final ? `${goals.total} final` : `${goals.total} so far`,
          detail: goalsDetail(goals, names, final),
        }
      : { kind: "unavailable", words: final ? GOALS_WORDS.finalScoreUnavailable : GOALS_WORDS.scoreUnavailable };
  }
  return {
    id: "goals",
    name: storyName("goals", phase),
    eyebrow: GOALS_WORDS.eyebrow,
    chartTitle: GOALS_WORDS.chartTitle,
    quantityAxisTitle: GOALS_WORDS.axisTitle,
    titles: { pregame: GOALS_WORDS.pregameTitle, current: GOALS_WORDS.currentStatusTitle, result: GOALS_WORDS.resultTitle },
    currentTitles: { recorded: GOALS_WORDS.recordedTitle, status: GOALS_WORDS.currentStatusTitle, reached: GOALS_WORDS.actualSoFarTitle },
    spoken: { hollow: GOALS_WORDS.spokenHollow, filled: GOALS_WORDS.spokenFilled, rule: GOALS_WORDS.spokenRule, strip: GOALS_WORDS.spokenStrip },
    title: phase === "before" ? GOALS_WORDS.beforeTitle : phase === "live" ? GOALS_WORDS.liveTitle : GOALS_WORDS.finalTitle,
    milestones,
    defaultId: opening === null ? null : milestones[opening].id,
    selectionUnavailable: GOALS_WORDS.selectionUnavailable,
    actual,
  };
}

function goalRow(
  leg: SoccerLeg,
  threshold: number,
  event: EventDetailResponse,
  phase: SoccerMatchPhase,
  goals: SoccerGoals | null,
  nowMs: number,
): SoccerGoalsMilestone {
  const count = milestoneCount(threshold);
  const label = `${count}+`;
  const pregame = soccerPregame(leg, event, nowMs);
  // `PlayerPropsCardView.rungVerdict` on the goals so far: performance, never a settlement.
  const reached = goals !== null && goals.total >= threshold;
  let current: SoccerCurrent | null = null;
  let performance: string | null = null;
  if (phase === "live") {
    current = reached ? { kind: "reached", words: GOALS_WORDS.reachedSoFar } : soccerCurrent(leg, event, nowMs);
    performance = reached || goals === null ? null : `${Math.max(1, count - goals.total)} more for ${label}`;
  }
  return {
    id: leg.id,
    label: `${label} ${unit(count)}`,
    quantity: count,
    quantityLabel: label,
    pregame,
    current,
    result: phase === "final" ? soccerResult(leg) : null,
    performance,
    timing: { title: "", lines: [] },
  };
}

function goalTiming(row: SoccerGoalsMilestone, leg: SoccerLeg, phase: SoccerMatchPhase): SoccerTiming {
  const lines = [pregameLine(GOALS_WORDS.pregameTitle, row.pregame)];
  if (phase === "live" && row.current) {
    const title =
      row.current.kind === "recorded"
        ? GOALS_WORDS.recordedTitle
        : row.current.kind === "reached"
          ? GOALS_WORDS.actualSoFarTitle
          : GOALS_WORDS.currentStatusTitle;
    lines.push(`${title}: ${currentWords(row.current)}`);
  }
  if (phase === "final" && row.result) lines.push(resultLine(GOALS_WORDS.resultTitle, row.result, leg));
  return { title: `${row.label} · ${GOALS_WORDS.timingSuffix}`, lines };
}

// ─── Part five: both teams to score ────────────────────────────────────────

export const BOTH_WORDS = {
  eyebrow: "BOTH TEAMS TO SCORE",
  beforeContext: "At least one goal each",
  actualGoals: "Actual goals",
  finalGoals: "Final goals",
  scoreUnavailable: "Score unavailable",
  hasScored: "has scored",
  yetToScore: "yet to score",
  timingSuffix: "chance timing",
  /** `BothTeamsScoreInput10868`'s leaf titles. */
  pregameTitle: "Pregame chance",
  currentTitle: "Current chance",
  resultTitle: "Result",
  /** `BothTeamsScoreInput10868.selectionUnavailable` (BothTeamsScorePresentation10868.swift:221). */
  selectionUnavailable: "Selected outcome unavailable.",
  /** Each outcome tile's captions (BothTeamsScorePresentation10868.swift:218-219). */
  pregameShort: "Pregame",
  currentShort: "Current",
} as const;

/** The reading row every card shares: pre-match, in-play (live) and result (after the final). */
function readingRow(
  leg: SoccerLeg,
  event: EventDetailResponse,
  phase: SoccerMatchPhase,
  nowMs: number,
  period = false,
): SoccerReadingRow {
  return {
    id: leg.id,
    label: leg.label,
    pregame: soccerPregame(leg, event, nowMs),
    current: phase === "live" ? (period ? soccerPeriodCurrent(leg, event, nowMs) : soccerCurrent(leg, event, nowMs)) : null,
    result: phase === "before" ? null : soccerResult(leg),
    timing: { title: "", lines: [] },
  };
}

export function soccerBothCard(
  event: EventDetailResponse,
  data: GameMarketsResponse | null | undefined,
  admission: SoccerMatchAdmission,
  phase: SoccerMatchPhase,
  names: { home: string; away: string },
  nowMs: number,
): SoccerBothCard | null {
  if (admission.both === null) return null;
  const legs = soccerLegs(admission.both, data);
  if (legs.length === 0) return null;
  const outcomes = legs.map((leg) => {
    const row = readingRow(leg, event, phase, nowMs);
    const lines = [pregameLine(BOTH_WORDS.pregameTitle, row.pregame)];
    if (phase === "live" && row.current) lines.push(`${BOTH_WORDS.currentTitle}: ${currentWords(row.current)}`);
    if (phase === "final" && row.result) lines.push(resultLine(BOTH_WORDS.resultTitle, row.result, leg));
    row.timing = { title: `${row.label} · ${BOTH_WORDS.timingSuffix}`, lines };
    return row;
  });
  const fallback = legs.find((leg) => propOutcomeSide(leg.label) === "over") ?? legs[0];
  const goals = soccerGoals(event);
  const final = phase === "final";
  const title = final ? BOTH_WORDS.finalGoals : BOTH_WORDS.actualGoals;
  let scoring: SoccerBothCard["scoring"];
  if (phase === "before" || goals === null) {
    const words = phase === "before" ? READING_WORDS.notStarted : BOTH_WORDS.scoreUnavailable;
    const team = (name: string): SoccerTeamGoals => ({ name, value: { kind: "unavailable", text: words }, status: null });
    scoring = { title, home: team(names.home), away: team(names.away), clock: null, detail: null };
  } else {
    const status = (count: number) => (final ? null : count > 0 ? BOTH_WORDS.hasScored : BOTH_WORDS.yetToScore);
    scoring = {
      title,
      home: { name: names.home, value: { kind: "value", text: `${goals.home}` }, status: status(goals.home) },
      away: { name: names.away, value: { kind: "value", text: `${goals.away}` }, status: status(goals.away) },
      clock: goalsClock(goals, final),
      detail: goalsDetail(goals, names, final),
    };
  }
  return {
    id: "both",
    name: storyName("both", phase),
    eyebrow: BOTH_WORDS.eyebrow,
    titles: { pregame: BOTH_WORDS.pregameTitle, current: BOTH_WORDS.currentTitle, result: BOTH_WORDS.resultTitle },
    shortTitles: { pregame: BOTH_WORDS.pregameShort, current: BOTH_WORDS.currentShort },
    beforeContext: phase === "before" ? BOTH_WORDS.beforeContext : null,
    outcomes,
    defaultId: fallback.id,
    selectionUnavailable: BOTH_WORDS.selectionUnavailable,
    scoring,
  };
}

// ─── Part six: first team to score ─────────────────────────────────────────

export const FIRST_WORDS = {
  title: "First team to score",
  plotTitle: "Pre-match chances",
  checkpointsTitle: "Observed scores",
  checkpointsNote: "Observation times, not exact goal times.",
  timingSuffix: "chance timing",
  pregameTitle: "Pre-match chance",
  currentTitle: "Current chance",
  liveResultTitle: "Result",
  finalResultTitle: "Final result",
  /** The soccer adapter's own word (SoccerFirstTeamAdapter10868.swift:46). */
  selectionUnavailable: "Selected outcome unavailable.",
} as const;

export function soccerFirstCard(
  event: EventDetailResponse,
  data: GameMarketsResponse | null | undefined,
  history: EventHistoryResponse | null | undefined,
  admission: SoccerMatchAdmission,
  phase: SoccerMatchPhase,
  names: { home: string; away: string },
  nowMs: number,
): SoccerFirstCard | null {
  if (admission.first === null) return null;
  const legs = soccerLegs(admission.first, data);
  if (legs.length === 0) return null;
  const rows = legs.map((leg) => {
    const row = readingRow(leg, event, phase, nowMs);
    const lines = [pregameLine(FIRST_WORDS.pregameTitle, row.pregame)];
    if (phase === "live") {
      if (row.result && row.result.kind !== "unconfirmed") {
        lines.push(`${FIRST_WORDS.liveResultTitle}: ${resultWords(row.result)}`);
      } else if (row.current) {
        lines.push(`${FIRST_WORDS.currentTitle}: ${currentWords(row.current)}`);
      }
    }
    if (phase === "final" && row.result) lines.push(`${FIRST_WORDS.finalResultTitle}: ${resultWords(row.result)}`);
    row.timing = { title: `${row.label} · ${FIRST_WORDS.timingSuffix}`, lines };
    return row;
  });
  return {
    id: "first",
    name: storyName("first", phase),
    title: FIRST_WORDS.title,
    plotTitle: FIRST_WORDS.plotTitle,
    titles: {
      pregame: FIRST_WORDS.pregameTitle,
      current: FIRST_WORDS.currentTitle,
      result: phase === "final" ? FIRST_WORDS.finalResultTitle : FIRST_WORDS.liveResultTitle,
    },
    context: sourceLabel(legs[0].row.source),
    rows,
    defaultId: rows[0].id,
    selectionUnavailable: FIRST_WORDS.selectionUnavailable,
    scorePath: phase === "live" ? checkpoints(event, history, names, nowMs) : null,
  };
}

/** `score_history` as served, each checkpoint with its own clock, up to now only — and only this event's own body. */
function checkpoints(
  event: EventDetailResponse,
  history: EventHistoryResponse | null | undefined,
  names: { home: string; away: string },
  nowMs: number,
): SoccerFirstCard["scorePath"] {
  const own = history && history.event_id === event.id ? history : null;
  const observations = (own?.score_history ?? []).flatMap((point) => {
    const at = parseMs(point.timestamp);
    if (at === null || at > nowMs) return [];
    if (typeof point.home_score !== "number" || typeof point.away_score !== "number") return [];
    if (point.home_score < 0 || point.away_score < 0) return [];
    return [
      {
        id: point.timestamp,
        score: `${point.home_score}–${point.away_score}`,
        time: timeWords(at),
        spoken: `${names.home} ${point.home_score}, ${names.away} ${point.away_score} · observed ${clockWords(at) ?? ""}`,
      },
    ];
  });
  if (observations.length === 0) return null;
  return { title: FIRST_WORDS.checkpointsTitle, note: FIRST_WORDS.checkpointsNote, observations };
}

// ─── Part seven: half by half ──────────────────────────────────────────────

export const HALVES_WORDS = {
  eyebrow: "Half-by-half expectations",
  title: "Two halves, two sets of expectations",
  plotTitle: "Pre-match chances",
  scaleCaption: "0–100% scale",
  pointExplanation: "Each dot is a pre-match chance for that half.",
  lineExplanation: "Lines compare halves, not changes over time.",
  draw: "Draw",
  liveResults: "Results so far",
  finalResults: "Final results",
  pregameTitle: "Pre-match chance",
  currentTitle: "Current chance",
  liveResultTitle: "Half result",
  finalResultTitle: "Final result",
  cellUnavailable: "Chance unavailable for this half",
  /** The soccer adapter's own word (SoccerHalvesAdapter10868.swift:54). */
  selectionUnavailable: "Selected outcome unavailable.",
} as const;

/** The three sides a series may be, in the card's order. */
export const HALF_SIDES = ["home", "draw", "away"] as const;

/** The cell id the card hands back: `<market>:<leg id>` (native `SoccerHalvesAdapter10868.cell`). */
export function halfCellId(half: SoccerHalfAdmission, leg: SoccerLeg): string {
  return `${half.marketId}:${leg.id}`;
}

export function soccerHalvesCard(
  event: EventDetailResponse,
  data: GameMarketsResponse | null | undefined,
  admission: SoccerMatchAdmission,
  phase: SoccerMatchPhase,
  names: { home: string; away: string },
  nowMs: number,
): SoccerHalvesCard | null {
  if (admission.halves.length === 0) return null;
  const byHalf = admission.halves.map((half) => ({ half, legs: soccerLegs(half.marketId, data) }));
  const series: SoccerHalfSeries[] = [];
  for (const side of HALF_SIDES) {
    const cells: SoccerHalfCell[] = byHalf.flatMap(({ half, legs }) => {
      const matching = legs.filter((leg) => leg.option?.side === side);
      if (matching.length !== 1) return [];
      const leg = matching[0];
      const row = readingRow(leg, event, phase, nowMs, true);
      const cell: SoccerHalfCell = { ...row, id: halfCellId(half, leg), label: half.label, periodId: half.periodId };
      const lines = [pregameLine(HALVES_WORDS.pregameTitle, cell.pregame)];
      if (phase === "live" && cell.current) lines.push(`${HALVES_WORDS.currentTitle}: ${currentWords(cell.current)}`);
      if (phase !== "before" && cell.result) {
        lines.push(`${phase === "final" ? HALVES_WORDS.finalResultTitle : HALVES_WORDS.liveResultTitle}: ${resultWords(cell.result)}`);
      }
      cell.timing = { title: half.label, lines };
      return [cell];
    });
    if (cells.length === 0) continue;
    series.push({
      id: side,
      label: side === "home" ? names.home : side === "away" ? names.away : HALVES_WORDS.draw,
      cells,
    });
  }
  if (series.length === 0) return null;
  const chosenLabel = series[0].label;
  const resultsLead = phase === "live" ? HALVES_WORDS.liveResults : phase === "final" ? HALVES_WORDS.finalResults : null;
  return {
    id: "halves",
    name: storyName("halves", phase),
    eyebrow: HALVES_WORDS.eyebrow,
    titles: {
      pregame: HALVES_WORDS.pregameTitle,
      current: HALVES_WORDS.currentTitle,
      result: phase === "final" ? HALVES_WORDS.finalResultTitle : HALVES_WORDS.liveResultTitle,
    },
    scaleCaption: HALVES_WORDS.scaleCaption,
    lineExplanation: HALVES_WORDS.lineExplanation,
    title: HALVES_WORDS.title,
    periods: admission.halves.map((half) => ({ id: half.periodId, label: half.label })),
    series,
    defaultId: series[0].id,
    selectionUnavailable: HALVES_WORDS.selectionUnavailable,
    resultsTitle: resultsLead === null ? null : `${resultsLead} · ${chosenLabel}`,
    resultsLead,
    resultTitle: phase === "final" ? HALVES_WORDS.finalResultTitle : HALVES_WORDS.liveResultTitle,
    cellUnavailable: HALVES_WORDS.cellUnavailable,
    plotTitle: HALVES_WORDS.plotTitle,
    pointExplanation: HALVES_WORDS.pointExplanation,
  };
}

// ─── Part ten: the exact-score map ─────────────────────────────────────────

export const EXACT_WORDS = {
  title: "How might it finish?",
  beforeIntro:
    "Each listed score’s pre-match chance, recorded at its own time. The chances are not adjusted to add up to 100%.",
  liveIntro: "Each listed score’s pre-match chance beside its own current chance.",
  finalIntro: "Each listed score’s pre-match chance beside its own result.",
  scoreSoFar: "Score so far",
  finalScore: "Final score",
  observed: "observed",
  otherChoicesTitle: "Other listed outcomes",
  notListed: "Not separately listed",
  noSelection: "Choose a score to compare.",
  /** `SoccerExactScoreAdapter10868` words (L149-151): a held scope, then a held score, not named exactly once. */
  scopeUnavailable: "Selected market unavailable.",
  selectionUnavailable: "Selected score unavailable.",
  scaleUnavailable: "Pre-match scale unavailable. Cells are not shaded.",
  unavailableMark: "—",
  /** `ExactScoreMapWords10868.panHint` (SoccerExactScoreAdapter10868.swift:155). */
  panHint: "Swipe the map sideways to see every column.",
  /** `SoccerExactScoreAdapter10868.Words.legend` (L167-173). */
  legend: {
    scaleTitle: "Pre-match chance · darker is higher",
    offScale: "Hatched: outside the pre-match scale",
    notListed: "Dashed: not separately listed",
    unavailable: "—: no pre-match chance",
    result: "Dark outline: confirmed result",
    selection: "Corner marks: selected score",
  },
  pregameTitle: "Pre-match chance",
  currentTitle: "Current chance",
  finalResultTitle: "Final result",
  rows: (team: string) => `Rows: ${team} goals`,
  columns: (team: string) => `Columns: ${team} goals`,
} as const;

/** The descriptor only when it is this event's own. */
export function admittedDescriptor(admission: SoccerMatchAdmission, event: EventDetailResponse): SoccerExactDescriptor | null {
  const descriptor = admission.exactScore;
  return descriptor && descriptor.eventId === event.id ? descriptor : null;
}

/** The descriptor's period markets, for All props to keep their in-play quotes historical. */
export function periodMarketIds(admission: SoccerMatchAdmission, event: EventDetailResponse): Set<number> {
  const ids = new Set(admission.halves.map((half) => half.marketId));
  for (const scope of admittedDescriptor(admission, event)?.scopes ?? []) if (scope.periodId !== null) ids.add(scope.marketId);
  return ids;
}

export function soccerExactCard(
  event: EventDetailResponse,
  data: GameMarketsResponse | null | undefined,
  admission: SoccerMatchAdmission,
  phase: SoccerMatchPhase,
  names: { home: string; away: string },
  nowMs: number,
): SoccerExactCard | null {
  const descriptor = admittedDescriptor(admission, event);
  if (!descriptor || !data || data.event_id !== event.id) return null;
  const goals = soccerGoals(event);
  const built = descriptor.scopes.map((described) => exactScope(described, event, data, phase, goals, names, nowMs));
  if (!built.some((b) => b.served)) return null;
  return {
    id: "exact",
    name: storyName("exact", phase),
    title: EXACT_WORDS.title,
    titles: { pregame: EXACT_WORDS.pregameTitle, current: EXACT_WORDS.currentTitle, result: EXACT_WORDS.finalResultTitle },
    legend: EXACT_WORDS.legend,
    noSelection: EXACT_WORDS.noSelection,
    scopeUnavailable: EXACT_WORDS.scopeUnavailable,
    selectionUnavailable: EXACT_WORDS.selectionUnavailable,
    scaleUnavailable: EXACT_WORDS.scaleUnavailable,
    unavailableMark: EXACT_WORDS.unavailableMark,
    panHint: EXACT_WORDS.panHint,
    intro: phase === "before" ? EXACT_WORDS.beforeIntro : phase === "live" ? EXACT_WORDS.liveIntro : EXACT_WORDS.finalIntro,
    homeLabel: names.home,
    awayLabel: names.away,
    rowsTitle: EXACT_WORDS.rows(names.home),
    columnsTitle: EXACT_WORDS.columns(names.away),
    scopes: built.map((b) => b.scope),
    defaultScopeId: descriptor.scopes[0]?.id ?? null,
    otherChoicesTitle: EXACT_WORDS.otherChoicesTitle,
    notListed: EXACT_WORDS.notListed,
  };
}

function exactScope(
  described: SoccerExactDescriptorScope,
  event: EventDetailResponse,
  data: GameMarketsResponse,
  phase: SoccerMatchPhase,
  goals: SoccerGoals | null,
  names: { home: string; away: string },
  nowMs: number,
): { scope: SoccerExactScope; served: boolean } {
  const legs = soccerLegs(described.marketId, data);
  const period = described.periodId !== null;
  const claimed = new Set<number>();
  const originals: SoccerExactOriginal[] = [];
  const served = (leg: SoccerLeg, placement: SoccerExactPlacement): SoccerExactOriginal => {
    const row = readingRow(leg, event, phase, nowMs, period);
    const lines = [pregameLine(EXACT_WORDS.pregameTitle, row.pregame)];
    if (phase === "live" && row.current) lines.push(`${EXACT_WORDS.currentTitle}: ${currentWords(row.current)}`);
    if (phase === "final" && row.result) lines.push(`${EXACT_WORDS.finalResultTitle}: ${resultWords(row.result)}`);
    return { ...row, result: phase === "before" ? null : row.result, placement, held: false, timing: { title: row.label, lines } };
  };
  for (const listed of described.originals) {
    if (listed.outcomeIds.length === 0) continue;
    const hits = legs
      .map((leg, index) => ({ leg, index }))
      .filter(({ leg }) => leg.contributors.length > 0 && sameSet(leg.contributors, listed.outcomeIds));
    if (hits.length === 0) {
      originals.push(heldOriginal(listed, phase));
      continue;
    }
    for (const { leg, index } of hits) {
      claimed.add(index);
      originals.push(served(leg, listed.placement));
    }
  }
  // A served row the owner did not describe stays reachable, off the grid.
  legs.forEach((leg, index) => {
    if (!claimed.has(index)) originals.push(served(leg, { kind: "nonGrid" }));
  });
  let actual: SoccerExactScope["actual"] = null;
  if (!period && phase !== "before" && goals) {
    const pair = `${names.home} ${goals.home}–${goals.away} ${names.away}`;
    actual =
      phase === "final"
        ? { title: EXACT_WORDS.finalScore, text: pair }
        : {
            title: EXACT_WORDS.scoreSoFar,
            text:
              joined([pair, goals.observedAtMs === null ? null : `${EXACT_WORDS.observed} ${clockWords(goals.observedAtMs) ?? ""}`]) ??
              pair,
          };
  }
  return {
    scope: {
      id: described.id,
      label: described.label,
      rows: described.homeGoals,
      columns: described.awayGoals,
      originals,
      actual,
      scale: exactScale(described.scaleUpper),
    },
    served: legs.length > 0,
  };
}

/**
 * The owner's shading bound and its three ticks (native `scale`,
 * SoccerExactScoreAdapter10868.swift:318-324), each figure through web's one
 * percent rule. An unusable bound (not inside (0, 1]) shades nothing; it is
 * never clamped or normalised.
 */
export function exactScale(upper: number): SoccerExactScope["scale"] {
  if (!Number.isFinite(upper) || upper <= 0 || upper > 1) return null;
  return {
    upper,
    ticks: [0, 0.5, 1].map((fraction) => ({ fraction, text: formatProbabilityPercent(upper * fraction) })),
  };
}

/** A listed original the payload no longer serves: its identity and the owner's held label, no chance, no result. */
function heldOriginal(listed: SoccerExactDescriptorOriginal, phase: SoccerMatchPhase): SoccerExactOriginal {
  return {
    id: listed.outcomeIds.map(String).join("+"),
    label: listed.label,
    placement: listed.placement,
    pregame: { kind: "missing", words: READING_WORDS.preMatchUnavailable },
    current: phase === "live" ? { kind: "unavailable", words: READING_WORDS.inPlayUnavailable } : null,
    result: phase === "before" ? null : UNCONFIRMED,
    held: true,
    timing: { title: listed.label, lines: [`${EXACT_WORDS.pregameTitle}: ${READING_WORDS.preMatchUnavailable}`] },
  };
}

// ─── Part nine: which stories the page offers ──────────────────────────────

export const STORY_WORDS = {
  streamHeading: "Explore the match",
  manualStatus: "Use Previous or Next to see each story",
  storiesLabel: "Match stories",
  /** `StoryStreamPresentation10868.emptyWords`: the stream with no card. */
  emptyWords: "No stories in this order. Every original prop is still in All props.",
  goals: "Goal milestones",
  goalOutlook: "Total goal outlook",
  exact: "Exact final score",
  both: "Both teams to score",
  first: "First team to score",
  halves: "Half-by-half expectations",
} as const;

/**
 * The reading's scope: one per event and phase (native
 * `SoccerPageInputAdapter10868.scope`, SoccerPageInputAdapter10868.swift:163-165).
 * The reader's held story and choices belong to it.
 */
export function soccerStoryScope(eventId: number, phase: SoccerMatchPhase): string {
  return `soccer:${eventId}:${phase}`;
}

/** The card's name in `phase`: before kickoff the goal card is the outlook. */
export function storyName(card: SoccerStoryId, phase: SoccerMatchPhase): string {
  if (card === "goals") return phase === "before" ? STORY_WORDS.goalOutlook : STORY_WORDS.goals;
  return STORY_WORDS[card];
}

/** The approved route-phase membership (native `SoccerPageInputAdapter10868.routeCards`). */
export function routeCards(phase: SoccerMatchPhase): SoccerStoryId[] {
  if (phase === "before") return ["goals", "exact"];
  if (phase === "live") return ["goals", "both", "first"];
  return ["goals", "both", "first", "halves"];
}

export type SoccerHalvesAdmission = "routeDefault" | "explicit";

/** Whether `card` is offered in `phase`: the route's own card, or one the owner admitted explicitly. */
export function offersStory(
  card: SoccerStoryId,
  phase: SoccerMatchPhase,
  admittedCards: readonly SoccerStoryId[],
  halvesAdmission: SoccerHalvesAdmission,
): boolean {
  if (card === "halves" && halvesAdmission === "explicit") return true;
  return routeCards(phase).includes(card) || admittedCards.includes(card);
}
