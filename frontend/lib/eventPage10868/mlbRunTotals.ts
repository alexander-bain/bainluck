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
 */

import { formatProbabilityPercent } from "@/lib/probabilityDisplay";
import { decodeQuestionMatrix, MIN_LADDER_LINES, type MatrixOption, type MatrixQuestion } from "@/lib/nbaEventCards";

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

const lineText = (line: number): string => (Number.isInteger(line) ? String(line) : line.toFixed(1));

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
  const home = score?.home ?? null;
  const away = score?.away ?? null;
  // Two whole, non-negative counts, or nothing: a missing side is never 0.
  const sides = count(home) && count(away) ? { home, away } : null;
  // RT1: the sum itself must be exact. Both sides are >= 0, so a safe sum also means each side is safe.
  const sum = sides ? sides.home + sides.away : null;
  const pair = sides && sum !== null && Number.isSafeInteger(sum) ? sides : null;
  const total = pair && sum !== null ? sum : null;
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
