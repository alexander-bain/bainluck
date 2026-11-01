/**
 * #10868 — THE MLB RUN-TOTAL STORY, FINAL LEAF (web): every typed full-game
 * run line with the source's result on it, and the final total against them.
 *
 * PILLARS: FORMATTING / DISCOVER / TRUTH. SHIP: a baseball fan sees the final
 * run total against the offered lines, with the pregame chance and source
 * result kept distinct from performance.
 *
 * Native: `MLBTotalsCard11284.build` (MLBFinalReader11284.swift L633-702) and
 * `MLBTotalTargetsPresentation11284` (L19-187). Pure: no React, fetch, timer,
 * cache or clock; no new decoder, formatter, probability or truth policy.
 *
 * LINES (`mlbRunLines`). The matrix envelope arrives as `unknown`. Native
 * refuses a matrix whose `display_scope` is neither absent nor "game"
 * (L678); the shared web decoder does not carry that one envelope field, so it
 * is read here FIRST — absent, null or "game" pass; any other value, a
 * malformed one included, refuses — and only then does the UNCHANGED shared
 * `decodeQuestionMatrix` parse every question and option (contract `10238.v1`).
 * A line is native's: typed, `count_threshold`, quantity `runs`, subject
 * `game`, period `full_game`, relation `ge`; its line is the predicate's finite
 * line, else bound − 0.5; it has exactly ONE `over` option. An option key
 * carried by two lines refuses both, and so does a line value carried twice
 * (two prices for one tick). Fewer than `MIN_LADDER_LINES` lines: no card.
 * No label is ever matched.
 *
 * PREGAME CHANCE: native's `NBALadderCard9483.pin` order over the fields the
 * shared decoder already admits — the comparable pregame baseline, else the
 * admitted `pregame_reading` — else unavailable. Never a settled 0/1, a live
 * quote or a complement.
 *
 * RESULT: the decoder's `result` (won → true, lost → false, anything else →
 * null). Native tells Open, Pending and Not confirmed apart; the shared
 * decoder folds them, so web says "Result unavailable" for all three (the
 * documented partial). The words are the card's (`propVerdictLabel`), never
 * graded from the run count.
 *
 * TOTAL (`mlbFinalTotals`): the SAME displayed pair the headline draws
 * (structurally `MlbDisplayedScore`; each side may be null). Only two whole,
 * non-negative counts give a total and a stacked team split; anything else
 * gives no total and no bar — a missing side is never 0, and no total is read
 * off a line or a result. The COMPUTED sum is checked too (RT1, native's
 * `addingReportingOverflow`): only a sum that is a safe integer
 * (`Number.isSafeInteger`, at most 2^53 − 1, so the addition was exact) is a
 * total. An overflowing or unrepresentable sum (two `Number.MAX_VALUE` sides
 * add to Infinity; `MAX_SAFE_INTEGER + 1` is no longer exact) gives no total
 * and no bar, and the axis then comes from the offered lines alone — never
 * Infinity, NaN or a made-up 0. There is no sport score ceiling.
 *
 * AXIS (native L76-85): the top is the largest of EVERY line and the total,
 * never the selection, so choosing a line never rescales the bar. Step 5 up to
 * 25, 10 up to 50, else ceil(top / 5); upper = max(step, ceil(top / step) ·
 * step); labels every step from 0.
 *
 * BEFORE FIRST PITCH AND DURING PLAY (S2b, `mlbRunMilestones`). Native
 * `BaseballRunMilestonesAdapter10868`: the SAME admitted lines drawn as run
 * milestones ("10+ runs") in the approved milestone visual (S2a's
 * `CountMilestoneCard`). Pure, over lines the CALLER owns: this helper never
 * sees the markets envelope, so it cannot prove which event the lines belong
 * to — the binding passes only lines `mlbRunLines` admitted from this event's
 * own body (`ownHockeyMarkets`). Each reading is an existing owner's,
 * composed as native composes it:
 *
 *   - N+            `milestoneCount(line)` (Over 9.5 is "10+"), titled in the
 *                   sport's unit words (`sportVocab`).
 *   - before        Pregame chance = the decoder's `quoted` value only while
 *                   its own clock is readable and recent (`isRecentQuote`),
 *                   "Recorded <clock> · <venue>". The pin NEVER fills it.
 *   - live pregame  S1's pin (comparable baseline, else the admitted reading)
 *                   on its own readable clock, "Saved before first pitch <clock>
 *                   · <venue>". No start filter of its own (native has none).
 *   - live current  the `quoted` value only while recent, observed at or after
 *                   a READABLE start (a missing start refuses) and not under the
 *                   page's own `noReportedResult`; otherwise "In-game chance
 *                   unavailable". `soccerCurrent` is not used (it lets a missing
 *                   start pass).
 *   - runs so far   during play only, from the host's DISPLAYED pair through
 *                   the same RT1 guard as the final total (one private helper),
 *                   dated only by the pair's own `observedAt`. Never the event
 *                   row; a partial pair is no count, never 0. A reached line
 *                   (count ≥ line, native `rungVerdict`) says "Reached so far" —
 *                   performance, never 100% and never a result; otherwise "k more
 *                   for N+". No source result is shown before or during play.
 *   - default       `defaultRungIndex` over the SHOWN pregame chances only
 *                   (nearest even odds, ties to the lower line); none shown is
 *                   no default, so no row is chosen until the reader chooses.
 *   - words         native baseball's, below; the leaf's statics are S2a's
 *                   `GOALS_WORDS` (`TotalMilestoneInput10868`), never copied.
 */

import type { EventDetailResponse } from "@/lib/types";
import { formatProbabilityPercent } from "@/lib/probabilityDisplay";
import { decodeQuestionMatrix, MIN_LADDER_LINES, type MatrixOption, type MatrixQuestion } from "@/lib/nbaEventCards";
import { defaultRungIndex, isRecentQuote, type MilestoneCard, type MilestoneRung } from "@/lib/nflEventCardDeck";
import { sourceLabel } from "@/lib/sourceLabels";
import { sportVocab } from "@/lib/marketMapUtils";
import { clockWords, parseMs, timeWords } from "./hockeyJourneyCore";
import { GOALS_WORDS, milestoneCount, observation } from "./soccerMatchStories";
import type { HockeyJourneyPhase } from "./hockeyJourneyTypes";
import type {
  SoccerCurrent,
  SoccerGoalsActual,
  SoccerGoalsCard,
  SoccerGoalsMilestone,
  SoccerPregame,
  SoccerTiming,
} from "./soccerMatchTypes";

/** Native's words (MLBTotalTargetsPresentation11284 / CardView11284), verbatim where web has them. */
export const MLB_RUN_TOTAL_WORDS = {
  title: "Where the total finished",
  eyebrow: (count: number) => `RUNS · ${count} FULL-GAME LINES`,
  actualLabel: "Final total runs",
  unavailable: "Unavailable",
  pregameLabel: "Pregame chance",
  selectedUnavailable: "Selected line unavailable",
  sourceResult: "Source result",
  resultUnavailable: "Result unavailable",
  strip: "Offered run lines",
  markerKey: (lineText: string) => `Selected line · ${lineText}`,
  // Before / live: native `BaseballRunMilestonesAdapter10868.Words`, verbatim.
  milestonesEyebrow: "TOTAL RUNS · BOTH TEAMS",
  beforeTitle: "How many runs?",
  liveTitle: "Runs so far against the milestones",
  axisTitle: "Total runs in the game",
  /** `TotalMilestoneInput10868.selectorTitle`: the strip's name. */
  stripName: "Choose milestone",
  pregameUnavailable: "Pregame chance unavailable",
  inGameUnavailable: "In-game chance unavailable",
  scoreUnavailable: "Score unavailable",
  recorded: "Recorded",
  savedBeforeStart: "Saved before first pitch",
  scoreObserved: "Score observed",
  more: (count: number, label: string) => `${count} more for ${label}`,
} as const;

/** One offered full-game run line. */
export interface MlbRunLine {
  /** The producer's identity (`o:` + contributor outcome ids); the held id. */
  optionKey: string;
  questionKey: string;
  line: number;
  /** "9.5" — native `NBALadderCard9483.number`. */
  lineText: string;
  /** "Over 9.5 runs". */
  label: string;
  /** Native pin order: the comparable baseline, else the admitted pregame reading; else null. */
  pregame: number | null;
  pregameObservedAt: string | null;
  /** The pregame chance in web's one percent rule, or "Unavailable". */
  pregameText: string;
  /** The source's verdict: true won, false lost, null open / unknown / void / none. */
  result: boolean | null;
  /** The decoder's published value, only while `quoted` (`MatrixOption.quoted`), verbatim. */
  quoted: number | null;
  /** The published value's own clock (`MatrixOption.observedAt`), verbatim. */
  observedAt: string | null;
  /** The published row's source key (`MatrixOption.source`), verbatim. */
  source: string | null;
}

/** The displayed pair, structurally `MlbDisplayedScore`: each side may be null. */
export interface MlbRunScore {
  home: number | null;
  away: number | null;
}

export type MlbRunBar = { kind: "stacked"; home: number; away: number } | { kind: "none" };

export interface MlbRunAxis {
  step: number;
  upper: number;
  labels: number[];
}

/** The final leaf's built input. */
export interface MlbFinalTotals {
  kind: "final";
  /** Sorted by line, each option key and each line exactly once. */
  lines: MlbRunLine[];
  /** home + away from the displayed pair; null without two whole counts. */
  total: number | null;
  bar: MlbRunBar;
  axis: MlbRunAxis;
  /** Native `defaultIndex`: the highest line the total cleared, else the lowest line. */
  defaultKey: string | null;
  homeName: string;
  awayName: string;
}

/** The displayed pair WITH its own observation clock: structurally the page's `MlbDisplayedScore`. */
export interface MlbRunObservedScore extends MlbRunScore {
  observedAt: string | null;
}

/** The event fields the milestones read, exactly as the page holds them: the listed start and the sport. */
export type MlbRunEvent = Pick<EventDetailResponse, "commence_time" | "sport">;

/** The before / live leaf's built input: S2a's `CountMilestoneCard` card, in this leaf's own wrapper. */
export interface MlbRunMilestones {
  kind: "milestones";
  phase: "before" | "live";
  card: Omit<SoccerGoalsCard, "id">;
}

/** What `MlbRunTotalsCard` draws: the final leaf, or the before / live milestones. */
export type MlbRunTotalsInput = MlbFinalTotals | MlbRunMilestones;

const lineText =(line: number): string => (Number.isInteger(line) ? String(line) : line.toFixed(1));

/** Native L678: absent, null or "game" passes; anything else — a malformed value included — refuses. */
function gameScoped(envelope: unknown): boolean {
  if (envelope === null || typeof envelope !== "object" || Array.isArray(envelope)) return true;
  if (!Object.prototype.hasOwnProperty.call(envelope, "display_scope")) return true;
  const scope = (envelope as Record<string, unknown>).display_scope;
  return scope === undefined || scope === null || scope === "game";
}

function pinOf(option: MatrixOption): { probability: number; observedAt: string | null } | null {
  if (option.baseline !== null) return { probability: option.baseline, observedAt: option.baselineObservedAt };
  if (option.reading !== null) return { probability: option.reading, observedAt: option.readingObservedAt };
  return null;
}

function lineOf(question: MatrixQuestion): MlbRunLine | null {
  if (!question.typed || question.kind !== "count_threshold" || question.quantityKey !== "runs") return null;
  if (question.subjectSide !== "game" || question.periodKey !== "full_game" || question.relation !== "ge") return null;
  const line = question.line ?? (question.bound !== null ? question.bound - 0.5 : null);
  if (line === null || !Number.isFinite(line)) return null;
  const own = question.options.filter((option) => option.side === "over");
  if (own.length !== 1) return null;
  const option = own[0];
  const pin = pinOf(option);
  const text = lineText(line);
  return {
    optionKey: option.optionKey,
    questionKey: question.questionKey,
    line,
    lineText: text,
    label: `Over ${text} runs`,
    pregame: pin?.probability ?? null,
    pregameObservedAt: pin?.observedAt ?? null,
    pregameText: pin ? formatProbabilityPercent(pin.probability) : MLB_RUN_TOTAL_WORDS.unavailable,
    result: option.result,
    // Verbatim from the unchanged shared decoder: no re-decode and no admission of their own.
    quoted: option.quoted,
    observedAt: option.observedAt,
    source: option.source,
  };
}

/** Every offered full-game run line, sorted; null when the matrix offers no card. */
export function mlbRunLines(envelope: unknown): MlbRunLine[] | null {
  if (!gameScoped(envelope)) return null;
  const lines = decodeQuestionMatrix(envelope)
    .map(lineOf)
    .filter((line): line is MlbRunLine => line !== null);
  const keys = new Map<string, number>();
  const values = new Map<number, number>();
  for (const l of lines) {
    keys.set(l.optionKey, (keys.get(l.optionKey) ?? 0) + 1);
    values.set(l.line, (values.get(l.line) ?? 0) + 1);
  }
  const kept = lines.filter((l) => keys.get(l.optionKey) === 1 && values.get(l.line) === 1).sort((a, b) => a.line - b.line);
  return kept.length >= MIN_LADDER_LINES ? kept : null;
}

const count = (value: number | null): value is number => typeof value === "number" && Number.isInteger(value) && value >= 0;

/**
 * The ONE runs rule, shared by the final total and the runs so far: two whole,
 * non-negative counts from the displayed pair whose sum is exact (RT1,
 * `Number.isSafeInteger`), or null. A missing side is never 0, and the event
 * row is never read.
 */
function wholePair(score: MlbRunScore | null): { home: number; away: number; total: number } | null {
  const home = score?.home ?? null;
  const away = score?.away ?? null;
  if (!count(home) || !count(away)) return null;
  // RT1: the sum itself must be exact. Both sides are >= 0, so a safe sum also means each side is safe.
  const total = home + away;
  return Number.isSafeInteger(total) ? { home, away, total } : null;
}

/** The runs axis from every line and the total (native L76-85); never from the selection. */
export function mlbRunAxis(lines: readonly number[], total: number | null): MlbRunAxis {
  const top = Math.max(0, ...lines, ...(total === null ? [] : [total]));
  const step = top <= 25 ? 5 : top <= 50 ? 10 : Math.ceil(top / 5);
  const upper = Math.max(step, Math.ceil(top / step) * step);
  const labels: number[] = [];
  for (let at = 0; at <= upper; at += step) labels.push(at);
  return { step, upper, labels };
}

/**
 * The final leaf's input: the lines, the displayed pair's total and split, the
 * axis and native's default line. Null when there is no card.
 */
export function mlbFinalTotals(
  lines: readonly MlbRunLine[] | null,
  score: MlbRunScore | null,
  names: { home: string; away: string },
): MlbFinalTotals | null {
  if (!lines || lines.length < MIN_LADDER_LINES) return null;
  // Two whole, non-negative counts with an exact sum, or nothing (the shared RT1 rule).
  const pair = wholePair(score);
  const total = pair ? pair.total : null;
  const sorted = [...lines].sort((a, b) => a.line - b.line);
  let defaultIndex = 0;
  if (total !== null) {
    for (let i = 0; i < sorted.length; i += 1) if (sorted[i].line < total) defaultIndex = i;
  }
  return {
    kind: "final",
    lines: sorted,
    total,
    bar: pair ? { kind: "stacked", home: pair.home, away: pair.away } : { kind: "none" },
    axis: mlbRunAxis(
      sorted.map((l) => l.line),
      total,
    ),
    defaultKey: sorted[defaultIndex]?.optionKey ?? null,
    homeName: names.home,
    awayName: names.away,
  };
}

/** The sporting comparison of the total with a line (native `comparison`); never the source's verdict. */
export function mlbRunComparison(total: number | null, line: MlbRunLine): string | null {
  if (total === null) return null;
  if (total === line.line) return `Final ${total} runs · on the line`;
  return `Final ${total} runs · ${total > line.line ? "above" : "below"} this line`;
}

/** The held (else default) key, resolved exactly once against this pass's lines; never the default for a held key. */
export function mlbRunSelected(totals: MlbFinalTotals, held: string | null): MlbRunLine | null {
  const key = held ?? totals.defaultKey;
  if (key === null) return null;
  const found = totals.lines.filter((l) => l.optionKey === key);
  return found.length === 1 ? found[0] : null;
}

// ─── Before first pitch and during play: the run milestones (S2b) ──────────

const MW = MLB_RUN_TOTAL_WORDS;

/** Before first pitch: the `quoted` value while its own clock is readable and recent (native L296-304). Never the pin. */
function beforeChance(line: MlbRunLine, nowMs: number): SoccerPregame {
  const at = parseMs(line.observedAt);
  if (line.quoted === null || at === null || !isRecentQuote(line.observedAt, nowMs)) {
    return { kind: "missing", words: MW.pregameUnavailable };
  }
  return { kind: "value", observation: observation(line.quoted, at, MW.recorded, sourceLabel(line.source)) };
}

/** Once play starts: S1's pin (baseline, else admitted reading) on its own readable clock (native L305-306). */
function pinChance(line: MlbRunLine): SoccerPregame {
  const at = parseMs(line.pregameObservedAt);
  if (line.pregame === null || at === null) return { kind: "missing", words: MW.pregameUnavailable };
  return { kind: "value", observation: observation(line.pregame, at, MW.savedBeforeStart, sourceLabel(line.source)) };
}

/**
 * During play (native L311-321): the `quoted` value only while recent, observed
 * at or after a READABLE start, and not under the page's own `noReportedResult`
 * (its `isSuspended`, which already withholds the projected final).
 */
function inGameChance(line: MlbRunLine, startMs: number | null, noReportedResult: boolean, nowMs: number): SoccerCurrent {
  const at = parseMs(line.observedAt);
  if (
    line.quoted === null ||
    at === null ||
    !isRecentQuote(line.observedAt, nowMs) ||
    startMs === null || // a missing or unreadable start refuses
    at < startMs || // a quote from before the start is never the in-game chance
    noReportedResult
  ) {
    return { kind: "unavailable", words: MW.inGameUnavailable };
  }
  return { kind: "recorded", observation: observation(line.quoted, at, MW.recorded, sourceLabel(line.source)) };
}

/** Native `timing`: each reading under its leaf title, joined from words already built. */
function milestoneTiming(title: string, pregame: SoccerPregame, current: SoccerCurrent | null): SoccerTiming {
  const lines = [`${GOALS_WORDS.pregameTitle}: ${pregame.kind === "value" ? pregame.observation.detail : pregame.words}`];
  if (current) {
    const lead =
      current.kind === "recorded"
        ? GOALS_WORDS.recordedTitle
        : current.kind === "reached"
          ? GOALS_WORDS.actualSoFarTitle
          : GOALS_WORDS.currentStatusTitle;
    lines.push(`${lead}: ${current.kind === "recorded" ? current.observation.detail : current.words}`);
  }
  return { title: `${title} · ${GOALS_WORDS.timingSuffix}`, lines };
}

/** The sport's unit for a count ("run" / "runs"), never a trailing space when the sport declares none. */
function unitFor(n: number, sport: string | null | undefined): string {
  const vocab = sportVocab(sport || undefined);
  return n === 1 ? vocab.unitSingular : vocab.unit;
}

function milestoneRow(
  line: MlbRunLine,
  phase: "before" | "live",
  startMs: number | null,
  runs: number | null,
  sport: string | null | undefined,
  noReportedResult: boolean,
  nowMs: number,
): SoccerGoalsMilestone {
  const n = milestoneCount(line.line);
  const label = `${n}+`;
  const unit = unitFor(n, sport);
  const title = unit ? `${label} ${unit}` : label;
  const pregame = phase === "before" ? beforeChance(line, nowMs) : pinChance(line);
  let current: SoccerCurrent | null = null;
  let performance: string | null = null;
  if (phase === "live") {
    // `PlayerPropsCardView.rungVerdict` on the runs so far: performance, never 100% and never a result.
    const reached = runs !== null && runs >= line.line;
    current = reached ? { kind: "reached", words: GOALS_WORDS.reachedSoFar } : inGameChance(line, startMs, noReportedResult, nowMs);
    performance = reached || runs === null ? null : MW.more(Math.max(1, n - runs), label);
  }
  return {
    id: line.optionKey,
    label: title,
    quantity: n,
    quantityLabel: label,
    pregame,
    current,
    // The source's grade belongs to the final leaf only; it is never inferred from reaching a line.
    result: null,
    performance,
    timing: milestoneTiming(title, pregame, current),
  };
}

/** Native `actual`: during play the displayed pair's total, dated only by the pair's own clock; else its absence. */
function runsSoFar(runs: number | null, observedAt: string | null, sport: string | null | undefined): SoccerGoalsActual {
  if (runs === null) return { kind: "unavailable", words: MW.scoreUnavailable };
  const unit = unitFor(runs, sport);
  const at = parseMs(observedAt);
  return {
    kind: "count",
    title: GOALS_WORDS.countSoFarTitle,
    quantity: runs,
    text: `${runs}`,
    unit,
    clock: at === null ? null : timeWords(at),
    ruleLabel: `${runs} so far`,
    detail: at === null ? `${runs}${unit ? ` ${unit}` : ""} so far` : `${MW.scoreObserved} ${clockWords(at) ?? ""}`,
  };
}

/**
 * The before / live run milestones for S2a's `CountMilestoneCard`, or null
 * after the final, for any other phase, or with fewer than three lines.
 *
 * `lines` must be `mlbRunLines` over THIS event's own body (the caller proves
 * ownership; this helper cannot). `event` gives only the listed start and the
 * sport; `score` is the host's displayed pair with its own `observedAt` (the
 * page's `score`); `noReportedResult` is the page's own answer.
 */
export function mlbRunMilestones(
  lines: readonly MlbRunLine[] | null,
  phase: HockeyJourneyPhase,
  event: MlbRunEvent,
  score: MlbRunObservedScore | null,
  noReportedResult: boolean,
  nowMs: number,
): MlbRunMilestones | null {
  if (phase !== "before" && phase !== "live") return null;
  if (!lines || lines.length < MIN_LADDER_LINES) return null;
  const sorted = [...lines].sort((a, b) => a.line - b.line);
  const startMs = parseMs(event.commence_time);
  // During play only, and only from the displayed pair (the same RT1 rule as the final total).
  const runs = phase === "live" ? (wholePair(score)?.total ?? null) : null;
  const rows = sorted.map((line) => milestoneRow(line, phase, startMs, runs, event.sport, noReportedResult, nowMs));
  // The milestone cards' own default over the SHOWN pregame chances; only `rungs[].chance` is read by it.
  const shown: MilestoneCard = {
    kind: "milestone",
    id: "mlb-run-milestones",
    player: "",
    stat: "",
    side: "unknown",
    basis: phase === "before" ? "pregamePrice" : "pregameMark",
    rungs: rows.map(
      (row, i): MilestoneRung => ({
        threshold: sorted[i].line,
        chance: row.pregame.kind === "value" ? row.pregame.observation.probability : null,
        observedAt: null,
        rowId: row.id,
        hit: null,
      }),
    ),
    actual: null,
  };
  const opening = defaultRungIndex(shown);
  return {
    kind: "milestones",
    phase,
    card: {
      name: MW.stripName,
      eyebrow: MW.milestonesEyebrow,
      chartTitle: GOALS_WORDS.chartTitle,
      quantityAxisTitle: MW.axisTitle,
      titles: { pregame: GOALS_WORDS.pregameTitle, current: GOALS_WORDS.currentStatusTitle, result: GOALS_WORDS.resultTitle },
      currentTitles: { recorded: GOALS_WORDS.recordedTitle, status: GOALS_WORDS.currentStatusTitle, reached: GOALS_WORDS.actualSoFarTitle },
      spoken: { hollow: GOALS_WORDS.spokenHollow, filled: GOALS_WORDS.spokenFilled, rule: GOALS_WORDS.spokenRule, strip: GOALS_WORDS.spokenStrip },
      title: phase === "before" ? MW.beforeTitle : MW.liveTitle,
      milestones: rows,
      defaultId: opening === null ? null : rows[opening].id,
      selectionUnavailable: GOALS_WORDS.selectionUnavailable,
      actual: phase === "live" ? runsSoFar(runs, score?.observedAt ?? null, event.sport) : null,
    },
  };
}
