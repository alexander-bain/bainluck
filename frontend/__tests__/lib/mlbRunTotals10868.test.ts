/**
 * #10868 — the MLB run-total story's FINAL leaf (`mlbRunTotals.ts`): native
 * `MLBTotalsCard11284.build` (MLBFinalReader11284.swift L633-702) and
 * `MLBTotalTargetsPresentation11284` (L19-187).
 *
 * SHIP: a baseball fan sees the final run total against the offered lines,
 * with the pregame chance and source result kept distinct from performance.
 *
 * INPUTS, labelled per test:
 *   - REAL FINAL CAPTURE — `mlbRunTotals10868.fixtures.json`: the ENTIRE
 *     `game_question_matrix` of the retained 15321836 game-markets body
 *     (sha256 42dfb489…, see its `_header`), unedited. It proves the FINAL
 *     phase only; it is never a before or live input. The displayed pair is a
 *     CONSTRUCTED host value set equal to the retained final row in
 *     `mlbGame10868.fixtures.json` (Astros 3, White Sox 7) — the pair the
 *     headline draws when the page shows that score.
 *   - CONSTRUCTED — every edit of that matrix (scope, contract, keys, lines,
 *     sides, typing, pins, results) and every other score, named where made.
 *
 * Expected ids are literal option keys read from the capture; nothing here
 * derives an identity, a price, a grade or a clock.
 *
 * BEFORE / LIVE (S2b, `mlbRunMilestones`): the REAL capture is a final, so
 * every before/live case is CONSTRUCTED — published quotes, pins, clocks, the
 * listed start, the displayed pair and the page's `noReportedResult` are set
 * in-test on a copy of the matrix and named where made. No genuine before or
 * live specimen is claimed.
 */

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fixture from "./mlbRunTotals10868.fixtures.json";
import mlbFixtures from "./mlbGame10868.fixtures.json";
import { formatProbabilityPercent } from "@/lib/probabilityDisplay";
import { propVerdictLabel } from "@/lib/propGrade";
import { decodeQuestionMatrix } from "@/lib/nbaEventCards";
import { sourceLabel } from "@/lib/sourceLabels";
import { clockWords, timeWords } from "@/lib/eventPage10868/hockeyJourneyCore";
import { GOALS_WORDS } from "@/lib/eventPage10868/soccerMatchStories";
import type { SoccerGoalsCard, SoccerGoalsMilestone } from "@/lib/eventPage10868/soccerMatchTypes";
import {
  MLB_RUN_TOTAL_WORDS,
  mlbFinalTotals,
  mlbRunAxis,
  mlbRunComparison,
  mlbRunLines,
  mlbRunMilestones,
  mlbRunSelected,
  type MlbFinalTotals,
  type MlbRunLine,
  type MlbRunObservedScore,
} from "@/lib/eventPage10868/mlbRunTotals";
import MlbRunTotalsCard from "@/components/event/eventpage10868/MlbRunTotalsCard";

type Json = Record<string, unknown>;

/** A fresh, independent copy of the REAL matrix, for one CONSTRUCTED edit. */
const matrix = (): Json => JSON.parse(JSON.stringify(fixture.game_question_matrix)) as Json;
const questionsOf = (m: Json): Json[] => m.questions as Json[];
const keyOf = (q: Json, field: string): unknown => (q[field] as Json | null | undefined)?.key;
const isRuns = (q: Json, period: string) => q.kind === "count_threshold" && keyOf(q, "quantity") === "runs" && keyOf(q, "period") === period;
/** The ONE full-game run question whose predicate line is `line`. */
function fullGameAt(m: Json, line: number): Json {
  const found = questionsOf(m).filter((q) => isRuns(q, "full_game") && (q.predicate as Json).line === line);
  if (found.length !== 1) throw new Error(`expected one full-game question at ${line}, found ${found.length}`);
  return found[0];
}
const overOf = (q: Json): Json => (q.options as Json[])[0];

const LINES = [2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5, 10.5, 11.5, 12.5, 13.5, 14.5];
const KEYS = [
  "o:244311416",
  "o:244311415",
  "o:244311414",
  "o:244311413",
  "o:244311412",
  "o:244311411",
  "o:244311410",
  "o:244311417",
  "o:244311422",
  "o:244311421",
  "o:244311420",
  "o:244311419",
  "o:244311418",
];
const KEY_9_5 = "o:244311417";
const KEY_10_5 = "o:244311422";
const KEY_2_5 = "o:244311416";
const KEY_14_5 = "o:244311418";

/** CONSTRUCTED host: the displayed pair equal to the retained final row. */
const DETAIL = mlbFixtures.finalDetail;
const SCORE = { home: DETAIL.home_score, away: DETAIL.away_score };
const NAMES = { home: DETAIL.home_team, away: DETAIL.away_team };

function realLines(): MlbRunLine[] {
  const lines = mlbRunLines(fixture.game_question_matrix);
  if (!lines) throw new Error("the REAL capture offers no run-total card");
  return lines;
}
function totalsOf(lines: MlbRunLine[] | null, score: { home: number | null; away: number | null } | null = SCORE): MlbFinalTotals {
  const totals = mlbFinalTotals(lines, score, NAMES);
  if (!totals) throw new Error("no final totals");
  return totals;
}
const lineAt = (lines: MlbRunLine[], line: number): MlbRunLine => {
  const found = lines.filter((l) => l.line === line);
  if (found.length !== 1) throw new Error(`expected one line ${line}`);
  return found[0];
};

// ─── REAL final capture ────────────────────────────────────────────────────

describe("the REAL final capture (15321836): thirteen full-game lines", () => {
  it("admits the 13 typed full-game run lines, sorted by line, and none of the first-five-innings lines", () => {
    const lines = realLines();
    expect(lines.map((l) => l.line)).toEqual(LINES);
    expect(lines.map((l) => l.optionKey)).toEqual(KEYS);
    expect(lines.map((l) => l.label)).toEqual(LINES.map((line) => `Over ${line} runs`));
    expect(lineAt(lines, 9.5).lineText).toBe("9.5");
    // Non-vacuity: the capture really serves five first-five run lines, and its order is not the line order.
    const firstFive = questionsOf(matrix()).filter((q) => isRuns(q, "first_5_innings"));
    expect(firstFive).toHaveLength(5);
    const firstFiveKeys = firstFive.flatMap((q) => (q.options as Json[]).map((o) => o.option_key));
    expect(lines.some((l) => firstFiveKeys.includes(l.optionKey))).toBe(false);
    expect((questionsOf(matrix()).find((q) => isRuns(q, "full_game"))!.predicate as Json).line).toBe(9.5);
    expect(fixture._header.capture).toBe("REAL final capture");
    expect(fixture.game_question_matrix.questions).toHaveLength(49);
  });

  it("states 8 source HITs and 5 MISSes, and every pregame chance is unavailable (no admitted pin or reading)", () => {
    const lines = realLines();
    const won = lines.filter((l) => l.result === true).map((l) => l.line);
    const lost = lines.filter((l) => l.result === false).map((l) => l.line);
    expect(won).toEqual([2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5]);
    expect(lost).toEqual([10.5, 11.5, 12.5, 13.5, 14.5]);
    expect(lines.filter((l) => l.result === null)).toEqual([]); // non-vacuity: every line has a verdict
    for (const l of lines) {
      expect({ line: l.line, pregame: l.pregame, at: l.pregameObservedAt, text: l.pregameText }).toEqual({
        line: l.line,
        pregame: null,
        at: null,
        text: MLB_RUN_TOTAL_WORDS.unavailable,
      });
    }
    // The capture's settled 1.0 source evidence is never a pregame chance.
    for (const line of LINES) expect(((overOf(fullGameAt(matrix(), line)).comparison as Json).state)).toBe("unavailable");
  });

  it("the displayed 7 + 3 is a total of 10; the default is the highest line cleared, 9.5 (above); 10.5 reads below", () => {
    expect(SCORE).toEqual({ home: 3, away: 7 });
    const totals = totalsOf(realLines());
    expect(totals.total).toBe(10);
    expect(totals.bar).toEqual({ kind: "stacked", home: 3, away: 7 });
    expect(totals.axis).toEqual({ step: 5, upper: 15, labels: [0, 5, 10, 15] });
    expect(totals.defaultKey).toBe(KEY_9_5);
    expect([totals.homeName, totals.awayName]).toEqual(["Houston Astros", "Chicago White Sox"]);
    const opened = mlbRunSelected(totals, null)!;
    expect(opened.line).toBe(9.5);
    expect(mlbRunComparison(totals.total, opened)).toBe("Final 10 runs · above this line");
    const other = mlbRunSelected(totals, KEY_10_5)!;
    expect(other.line).toBe(10.5);
    expect(mlbRunComparison(totals.total, other)).toBe("Final 10 runs · below this line");
  });

  it("renders the canonical HIT on the default line and MISS on a lost one, never Won or Lost", () => {
    const hit = renderToStaticMarkup(createElement(MlbRunTotalsCard, { totals: totalsOf(realLines()), scope: "mlb:15321836:final" }));
    // CONSTRUCTED score 9 + 7 = 16: the highest line cleared is 14.5, which the source graded lost.
    const miss = renderToStaticMarkup(
      createElement(MlbRunTotalsCard, { totals: totalsOf(realLines(), { home: 9, away: 7 }), scope: "mlb:15321836:final" }),
    );
    const source = (html: string) => /data-run-source="">.*?<span class="font-semibold">([^<]*)<\/span>/.exec(html)?.[1] ?? null;
    expect(source(hit)).toBe(propVerdictLabel(true));
    expect(source(miss)).toBe(propVerdictLabel(false));
    expect(propVerdictLabel(true)).not.toBe(propVerdictLabel(false));
    for (const html of [hit, miss]) expect(html).not.toMatch(/\bWon\b|\bLost\b/);
  });
});

// ─── CONSTRUCTED: the envelope ─────────────────────────────────────────────

describe("CONSTRUCTED: the matrix envelope's scope and contract, read before the shared decoder", () => {
  it("an absent, null or game scope passes; any other or malformed scope refuses", () => {
    const absent = matrix();
    delete absent.display_scope;
    expect(mlbRunLines(absent)).toHaveLength(13);
    for (const scope of [null, "game"]) expect(mlbRunLines({ ...matrix(), display_scope: scope })).toHaveLength(13);
    for (const scope of ["series", "", "GAME", 7, {}, ["game"], false]) {
      expect({ scope, lines: mlbRunLines({ ...matrix(), display_scope: scope }) }).toEqual({ scope, lines: null });
    }
  });

  it("the scope is never inferred from the questions: their own scope fields decide nothing", () => {
    const rows = matrix();
    for (const q of questionsOf(rows)) q.display_scope = "series";
    expect(mlbRunLines(rows)).toHaveLength(13);
    const refused = { ...matrix(), display_scope: "series" };
    for (const q of questionsOf(refused)) q.display_scope = "game";
    expect(mlbRunLines(refused)).toBeNull();
  });

  it("another contract, a missing question list or a non-object envelope offers no card", () => {
    expect(mlbRunLines({ ...matrix(), contract: "10238.v2" })).toBeNull();
    expect(mlbRunLines({ ...matrix(), questions: null })).toBeNull();
    for (const envelope of [null, undefined, "matrix", 7, []]) expect(mlbRunLines(envelope)).toBeNull();
  });
});

// ─── CONSTRUCTED: line admission ───────────────────────────────────────────

describe("CONSTRUCTED: native's line admission", () => {
  it("an option key carried by two lines refuses both; a line carried twice refuses both", () => {
    const twoKeys = matrix();
    overOf(fullGameAt(twoKeys, 10.5)).option_key = KEY_9_5;
    const keyed = mlbRunLines(twoKeys)!;
    expect(keyed).toHaveLength(11);
    expect(keyed.map((l) => l.line)).not.toContain(9.5);
    expect(keyed.map((l) => l.line)).not.toContain(10.5);
    expect(keyed.map((l) => l.optionKey)).not.toContain(KEY_9_5);

    const twoLines = matrix();
    (fullGameAt(twoLines, 10.5).predicate as Json).line = 9.5;
    const lined = mlbRunLines(twoLines)!;
    expect(lined).toHaveLength(11);
    expect(lined.map((l) => l.optionKey)).not.toContain(KEY_9_5);
    expect(lined.map((l) => l.optionKey)).not.toContain(KEY_10_5);
  });

  it("exactly one Over: an Under-only line or a line with two Overs is refused", () => {
    const under = matrix();
    overOf(fullGameAt(under, 11.5)).side = "under";
    expect(mlbRunLines(under)!.map((l) => l.line)).toEqual(LINES.filter((l) => l !== 11.5));
    const twoOvers = matrix();
    const q = fullGameAt(twoOvers, 12.5);
    q.options = [...(q.options as Json[]), { ...overOf(q), option_key: "o:99000001" }];
    expect(mlbRunLines(twoOvers)!.map((l) => l.line)).toEqual(LINES.filter((l) => l !== 12.5));
  });

  it("the line is the predicate's finite line, else bound − 0.5; with neither the line is refused", () => {
    const noLine = matrix();
    delete (fullGameAt(noLine, 9.5).predicate as Json).line;
    expect(lineAt(mlbRunLines(noLine)!, 9.5).optionKey).toBe(KEY_9_5);
    const textLine = matrix();
    (fullGameAt(textLine, 9.5).predicate as Json).line = "9.5";
    expect(lineAt(mlbRunLines(textLine)!, 9.5).optionKey).toBe(KEY_9_5);
    const neither = matrix();
    const predicate = fullGameAt(neither, 9.5).predicate as Json;
    predicate.line = null;
    predicate.bound = null;
    expect(mlbRunLines(neither)!.map((l) => l.optionKey)).not.toContain(KEY_9_5);
  });

  it("every other part of native's typing is required: typed, count threshold, runs, game, full game, at least", () => {
    const edits: Array<[string, (q: Json) => void]> = [
      ["untyped", (q) => (q.typing = { state: "untyped", reason: "untyped_unit" })],
      ["another kind", (q) => (q.kind = "named_options")],
      ["another quantity", (q) => (q.quantity = { ...(q.quantity as Json), key: "hits" })],
      ["one team's runs", (q) => (q.subject = { side: "home", label: null })],
      ["another period", (q) => (q.period = { key: "first_5_innings", label: "First 5 innings" })],
      ["another relation", (q) => (q.predicate = { ...(q.predicate as Json), relation: "gt" })],
    ];
    for (const [name, edit] of edits) {
      const m = matrix();
      edit(fullGameAt(m, 13.5));
      expect({ name, lines: mlbRunLines(m)!.map((l) => l.line) }).toEqual({ name, lines: LINES.filter((l) => l !== 13.5) });
    }
  });

  it("fewer than three lines is no card; exactly three is a card", () => {
    const keep = (lines: number[]): Json => {
      const m = matrix();
      m.questions = questionsOf(m).filter((q) => !isRuns(q, "full_game") || lines.includes((q.predicate as Json).line as number));
      return m;
    };
    expect(mlbRunLines(keep([2.5, 3.5]))).toBeNull();
    expect(mlbRunLines(keep([2.5, 3.5, 4.5]))!.map((l) => l.line)).toEqual([2.5, 3.5, 4.5]);
    expect(mlbFinalTotals(null, SCORE, NAMES)).toBeNull();
    expect(mlbFinalTotals(realLines().slice(0, 2), SCORE, NAMES)).toBeNull();
  });
});

// ─── CONSTRUCTED: the pregame chance ───────────────────────────────────────

describe("CONSTRUCTED: native's pin order over the decoder's admitted fields", () => {
  const baseline = (probability: number, basis = "pregame_pin") => ({
    state: "comparable",
    reason: null,
    baseline: { basis, probability, observed_at: "2026-09-30T22:55:00Z" },
    latest: null,
    delta_points: null,
  });
  const reading = (probability: number, outcome: number, reason: string | null = null) => ({
    state: "available",
    reason,
    basis: "pregame_pin",
    probability,
    observed_at: "2026-09-30T23:00:00Z",
    outcome_id: outcome,
  });

  it("the comparable baseline first, else the admitted pregame reading, else unavailable", () => {
    const m = matrix();
    const both = overOf(fullGameAt(m, 9.5));
    both.comparison = baseline(0.41);
    both.pregame_reading = reading(0.38, 244311417);
    const readingOnly = overOf(fullGameAt(m, 10.5));
    readingOnly.pregame_reading = reading(0.27, 244311422);
    const reasoned = overOf(fullGameAt(m, 11.5));
    reasoned.pregame_reading = reading(0.3, 244311421, "late");
    const otherBasis = overOf(fullGameAt(m, 12.5));
    otherBasis.comparison = baseline(0.2, "latest");
    const otherOutcome = overOf(fullGameAt(m, 13.5));
    otherOutcome.pregame_reading = reading(0.22, 244311417);
    const lines = mlbRunLines(m)!;
    expect(lineAt(lines, 9.5)).toMatchObject({ pregame: 0.41, pregameObservedAt: "2026-09-30T22:55:00Z", pregameText: formatProbabilityPercent(0.41) });
    expect(lineAt(lines, 10.5)).toMatchObject({ pregame: 0.27, pregameObservedAt: "2026-09-30T23:00:00Z", pregameText: formatProbabilityPercent(0.27) });
    for (const line of [11.5, 12.5, 13.5, 14.5]) {
      expect(lineAt(lines, line)).toMatchObject({ pregame: null, pregameObservedAt: null, pregameText: MLB_RUN_TOTAL_WORDS.unavailable });
    }
  });
});

// ─── CONSTRUCTED: the displayed pair ───────────────────────────────────────

describe("CONSTRUCTED: the total comes only from the displayed pair", () => {
  it("a missing, negative or fractional side gives no total and no bar, never a zero; the default is then the lowest line", () => {
    const lines = realLines();
    for (const score of [null, { home: 3, away: null }, { home: null, away: 7 }, { home: null, away: null }, { home: -1, away: 7 }, { home: 3.5, away: 7 }]) {
      const totals = totalsOf(lines, score);
      expect({ score, total: totals.total, bar: totals.bar, defaultKey: totals.defaultKey, axis: totals.axis }).toEqual({
        score,
        total: null,
        bar: { kind: "none" },
        defaultKey: KEY_2_5,
        axis: { step: 5, upper: 15, labels: [0, 5, 10, 15] },
      });
      expect(mlbRunComparison(totals.total, lineAt(lines, 9.5))).toBeNull();
    }
    // A real zero is a count, not a gap.
    const zero = totalsOf(lines, { home: 0, away: 0 });
    expect([zero.total, zero.bar, zero.defaultKey]).toEqual([0, { kind: "stacked", home: 0, away: 0 }, KEY_2_5]);
    expect(mlbRunComparison(0, lineAt(lines, 2.5))).toBe("Final 0 runs · below this line");
  });

  it("RT1: an overflowing or unrepresentable sum is no total and no bar, with a finite axis over the offered lines (CONSTRUCTED pairs)", () => {
    const lines = realLines();
    const offered = JSON.parse(JSON.stringify(lines)) as MlbRunLine[];
    // Each side passes the whole, non-negative count rule on its own; only the SUM is wrong.
    for (const score of [
      { home: Number.MAX_VALUE, away: Number.MAX_VALUE }, // adds to Infinity
      { home: Number.MAX_SAFE_INTEGER, away: 1 }, // 2^53: no longer exact
    ]) {
      expect([Number.isInteger(score.home), Number.isInteger(score.away), Number.isSafeInteger(score.home + score.away)]).toEqual([true, true, false]);
      const totals = totalsOf(lines, score);
      expect({ score, total: totals.total, bar: totals.bar, defaultKey: totals.defaultKey }).toEqual({
        score,
        total: null,
        bar: { kind: "none" },
        defaultKey: KEY_2_5,
      });
      expect(totals.axis).toEqual({ step: 5, upper: 15, labels: [0, 5, 10, 15] });
      expect([totals.axis.step, totals.axis.upper, ...totals.axis.labels].every(Number.isFinite)).toBe(true);
      expect(totals.lines.every((l) => l.line <= totals.axis.upper)).toBe(true);
      expect(totals.lines).toEqual(offered);
      for (const l of totals.lines) expect(mlbRunComparison(totals.total, l)).toBeNull();
      const html = renderToStaticMarkup(createElement(MlbRunTotalsCard, { totals, scope: "mlb:15321836:final" }));
      expect(html).toContain('data-run-total="unavailable"');
      expect(html).toContain(`>${MLB_RUN_TOTAL_WORDS.unavailable}</dd>`);
      expect(html).not.toContain("data-run-segment");
      expect(html).not.toContain("data-run-comparison");
      expect(html).not.toMatch(/Infinity|NaN/);
    }
    // No score ceiling: the largest exact sum is still a total, with a finite axis above it.
    const largest = totalsOf(lines, { home: Number.MAX_SAFE_INTEGER - 1, away: 1 });
    expect([largest.total, largest.bar]).toEqual([Number.MAX_SAFE_INTEGER, { kind: "stacked", home: Number.MAX_SAFE_INTEGER - 1, away: 1 }]);
    expect(Number.isFinite(largest.axis.upper) && largest.axis.upper >= Number.MAX_SAFE_INTEGER).toBe(true);
    expect(largest.axis.labels.length).toBeGreaterThanOrEqual(2);
    expect(largest.axis.labels.every(Number.isFinite)).toBe(true);
    // CONTROL: the ordinary pairs are unchanged.
    expect(totalsOf(lines, { home: 0, away: 0 }).total).toBe(0);
    expect(totalsOf(lines).total).toBe(10);
  });

  it("the sporting comparison never reads the source's verdict, and no verdict is read from the count", () => {
    const m = matrix();
    (overOf(fullGameAt(m, 9.5)).result as Json).state = "lost";
    (overOf(fullGameAt(m, 12.5)).result as Json).state = "won";
    (fullGameAt(m, 10.5).predicate as Json).line = 10;
    const lines = mlbRunLines(m)!;
    const totals = totalsOf(lines);
    expect([lineAt(lines, 9.5).result, mlbRunComparison(totals.total, lineAt(lines, 9.5))]).toEqual([false, "Final 10 runs · above this line"]);
    expect([lineAt(lines, 12.5).result, mlbRunComparison(totals.total, lineAt(lines, 12.5))]).toEqual([true, "Final 10 runs · below this line"]);
    const onTheLine = lineAt(lines, 10);
    expect([onTheLine.label, onTheLine.lineText, mlbRunComparison(totals.total, onTheLine)]).toEqual(["Over 10 runs", "10", "Final 10 runs · on the line"]);
  });

  it("open, unknown, void and missing results are all null: the documented Result unavailable partial", () => {
    const m = matrix();
    (overOf(fullGameAt(m, 11.5)).result as Json).state = "open";
    (overOf(fullGameAt(m, 12.5)).result as Json).state = "unknown";
    (overOf(fullGameAt(m, 13.5)).result as Json).state = "void";
    delete overOf(fullGameAt(m, 14.5)).result;
    const lines = mlbRunLines(m)!;
    expect([11.5, 12.5, 13.5, 14.5].map((line) => lineAt(lines, line).result)).toEqual([null, null, null, null]);
    expect(MLB_RUN_TOTAL_WORDS.resultUnavailable).toBe("Result unavailable");
  });
});

// ─── CONSTRUCTED: the axis ─────────────────────────────────────────────────

describe("CONSTRUCTED: the runs axis follows every line and the total, never the selection", () => {
  it("a total above 25 or 50 takes native's step; so does a line above the total", () => {
    const lines = realLines();
    expect(totalsOf(lines, { home: 20, away: 9 }).axis).toEqual({ step: 10, upper: 30, labels: [0, 10, 20, 30] });
    expect(totalsOf(lines, { home: 40, away: 21 }).axis).toEqual({ step: 13, upper: 65, labels: [0, 13, 26, 39, 52, 65] });
    const high = matrix();
    const predicate = fullGameAt(high, 14.5).predicate as Json;
    predicate.line = 30.5;
    predicate.bound = 31;
    expect(totalsOf(mlbRunLines(high)).axis).toEqual({ step: 10, upper: 40, labels: [0, 10, 20, 30, 40] });
  });

  it("native's boundaries: 25 and 50 keep the smaller step; the upper is never below one step", () => {
    expect(mlbRunAxis([2.5], 25)).toEqual({ step: 5, upper: 25, labels: [0, 5, 10, 15, 20, 25] });
    expect(mlbRunAxis([2.5], 26)).toEqual({ step: 10, upper: 30, labels: [0, 10, 20, 30] });
    expect(mlbRunAxis([2.5], 50)).toEqual({ step: 10, upper: 50, labels: [0, 10, 20, 30, 40, 50] });
    expect(mlbRunAxis([2.5], 51)).toEqual({ step: 11, upper: 55, labels: [0, 11, 22, 33, 44, 55] });
    expect(mlbRunAxis([2.5], 0)).toEqual({ step: 5, upper: 5, labels: [0, 5] });
  });

  it("the same lines in another order give the same axis; the axis takes no selection at all", () => {
    const reordered = matrix();
    reordered.questions = [...questionsOf(reordered)].reverse();
    expect(totalsOf(mlbRunLines(reordered)).axis).toEqual(totalsOf(realLines()).axis);
    expect(mlbFinalTotals.length).toBe(3); // lines, score, names: no selection input
  });
});

// ─── CONSTRUCTED: the held line ────────────────────────────────────────────

describe("CONSTRUCTED: a held line resolves exactly once and never falls back", () => {
  it("held keys resolve by key only; a missing or duplicated key is unavailable, never the default", () => {
    const totals = totalsOf(realLines());
    expect(mlbRunSelected(totals, null)?.optionKey).toBe(KEY_9_5);
    expect(mlbRunSelected(totals, KEY_14_5)?.line).toBe(14.5);
    expect(mlbRunSelected(totals, "o:99000001")).toBeNull();
    const duplicated: MlbFinalTotals = { ...totals, lines: [...totals.lines, totals.lines[8]] }; // CONSTRUCTED model
    expect(mlbRunSelected(duplicated, KEY_10_5)).toBeNull();
    const noDefault: MlbFinalTotals = { ...totals, defaultKey: null }; // CONSTRUCTED model
    expect(mlbRunSelected(noDefault, null)).toBeNull();
  });
});

// ─── S2b: before first pitch and during play (CONSTRUCTED phases) ──────────

/** CONSTRUCTED clocks: a listed first pitch, ten minutes before it, and twenty minutes into play. */
const START_ISO = "2026-09-30T23:10:00.000Z";
const START = Date.parse(START_ISO);
const MIN = 60_000;
const BEFORE_NOW = START - 10 * MIN;
const LIVE_NOW = START + 20 * MIN;
const iso = (ms: number) => new Date(ms).toISOString();
/** CONSTRUCTED event fields: only the listed start and the sport, as the page holds them. */
const EVENT = { commence_time: START_ISO, sport: "baseball_mlb" };
/** CONSTRUCTED displayed pair during play: 2 + 3 = 5 runs, dated a minute ago by its own clock. */
const PAIR_AT = iso(LIVE_NOW - MIN);
const LIVE_PAIR: MlbRunObservedScore = { home: 2, away: 3, observedAt: PAIR_AT };
const COUNTS = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15];
const KEY_12_5 = "o:244311420";
const keyAt = (line: number) => KEYS[LINES.indexOf(line)];

/** CONSTRUCTED: the line's Over option published as `state` with `value`, on its own clock. */
function publish(m: Json, line: number, value: unknown, observedAt: string | null, state = "quoted"): void {
  const o = overOf(fullGameAt(m, line));
  o.published = { ...(o.published as Json), value, value_state: state, observed_at: observedAt };
}
/** CONSTRUCTED: an admitted pregame pin (comparable baseline) on the line's Over option. */
function pinLine(m: Json, line: number, probability: number, observedAt: string): void {
  overOf(fullGameAt(m, line)).comparison = {
    state: "comparable",
    reason: null,
    baseline: { basis: "pregame_pin", probability, observed_at: observedAt },
    latest: null,
    delta_points: null,
  };
}
const copyOf = (m: Json): Json => JSON.parse(JSON.stringify(m)) as Json;

type MilestoneOptions = { score?: MlbRunObservedScore | null; noReportedResult?: boolean; now?: number; event?: { commence_time: string; sport: string | null } };
/** The ACTUAL helper over the ACTUAL admission, with the CONSTRUCTED phase inputs above unless overridden. */
function built(m: Json, phase: "before" | "live", o: MilestoneOptions = {}): Omit<SoccerGoalsCard, "id"> {
  const result = mlbRunMilestones(
    mlbRunLines(m),
    phase,
    o.event ?? EVENT,
    o.score === undefined ? LIVE_PAIR : o.score,
    o.noReportedResult ?? false,
    o.now ?? (phase === "before" ? BEFORE_NOW : LIVE_NOW),
  );
  if (!result) throw new Error("no run milestones");
  expect(result.phase).toBe(phase);
  return result.card;
}
function rowOf(card: Omit<SoccerGoalsCard, "id">, line: number): SoccerGoalsMilestone {
  const found = card.milestones.filter((r) => r.id === keyAt(line));
  if (found.length !== 1) throw new Error(`expected one milestone for ${line}`);
  return found[0];
}
/** A shown reading: the figure in web's one percent rule, the short clock, and "<lead> <full clock> · Kalshi". */
const obs = (lead: string, probability: number, atMs: number) => ({
  probability,
  text: formatProbabilityPercent(probability),
  clock: timeWords(atMs),
  detail: `${lead} ${clockWords(atMs)} · Kalshi`,
});
const PREGAME_UNAVAILABLE = { kind: "missing", words: "Pregame chance unavailable" };
const IN_GAME_UNAVAILABLE = { kind: "unavailable", words: "In-game chance unavailable" };
const REACHED = { kind: "reached", words: "Reached so far" };

describe("S2b: the run milestones before first pitch and during play (CONSTRUCTED phases over the REAL admission)", () => {
  it("only before and live, with at least three lines: the same 13 admitted lines as 3+ … 15+ runs, in native's words, with no source result", () => {
    const lines = realLines();
    expect(mlbRunMilestones(lines, "final", EVENT, LIVE_PAIR, false, LIVE_NOW)).toBeNull();
    expect(mlbRunMilestones(null, "live", EVENT, LIVE_PAIR, false, LIVE_NOW)).toBeNull();
    expect(mlbRunMilestones(lines.slice(0, 2), "before", EVENT, null, false, BEFORE_NOW)).toBeNull();
    expect(sourceLabel("kalshi")).toBe("Kalshi");
    for (const phase of ["before", "live"] as const) {
      const card = built(matrix(), phase);
      expect(card.milestones.map((r) => r.id)).toEqual(KEYS);
      expect(card.milestones.map((r) => r.quantity)).toEqual(COUNTS);
      expect(card.milestones.map((r) => r.quantityLabel)).toEqual(COUNTS.map((n) => `${n}+`));
      expect(card.milestones.map((r) => r.label)).toEqual(COUNTS.map((n) => `${n}+ runs`));
      // The capture grades every line; before and during play no grade is shown or inferred.
      expect(card.milestones.every((r) => r.result === null)).toBe(true);
      expect([card.eyebrow, card.name, card.quantityAxisTitle, card.chartTitle]).toEqual([
        "TOTAL RUNS · BOTH TEAMS",
        "Choose milestone",
        "Total runs in the game",
        GOALS_WORDS.chartTitle,
      ]);
      expect(card.titles).toEqual({ pregame: "Pregame chance", current: "In-game chance", result: "Final result" });
      expect(card.currentTitles).toEqual({ recorded: "Recorded in-game", status: "In-game chance", reached: "Actual so far" });
      expect(card.selectionUnavailable).toBe(GOALS_WORDS.selectionUnavailable);
    }
    expect(built(matrix(), "before").title).toBe("How many runs?");
    expect(built(matrix(), "live").title).toBe("Runs so far against the milestones");
  });

  it("each line carries the shared decoder's quoted, observedAt and source verbatim (no re-decode)", () => {
    const m = matrix();
    publish(m, 9.5, 0.42, iso(BEFORE_NOW - 5 * MIN)); // CONSTRUCTED quote
    const options = decodeQuestionMatrix(m).flatMap((q) => q.options);
    const lines = mlbRunLines(m)!;
    for (const l of lines) {
      const o = options.filter((x) => x.optionKey === l.optionKey);
      expect(o).toHaveLength(1);
      expect({ key: l.optionKey, quoted: l.quoted, observedAt: l.observedAt, source: l.source }).toEqual({
        key: l.optionKey,
        quoted: o[0].quoted,
        observedAt: o[0].observedAt,
        source: o[0].source,
      });
    }
    expect(lineAt(lines, 9.5).quoted).toBe(0.42);
    expect(lineAt(realLines(), 9.5)).toMatchObject({ quoted: null, observedAt: "2026-10-09T04:12:27.146416+00:00", source: "kalshi" });
  });

  it("BEFORE: a quoted value on its own readable, recent clock is the pregame chance; stale, undated, unreadable and unquoted are not; 0 and 1 are real quotes; a pin never fills it", () => {
    const m = matrix();
    const recent = BEFORE_NOW - 5 * MIN;
    publish(m, 9.5, 0.45, iso(recent));
    publish(m, 10.5, 0.3, iso(BEFORE_NOW - 30 * MIN)); // exactly 30 minutes old: still recent
    publish(m, 11.5, 0.2, iso(BEFORE_NOW - 30 * MIN - 1)); // one millisecond past: stale
    publish(m, 12.5, 0.1, null); // undated
    publish(m, 13.5, 0.05, iso(recent), "result"); // not quoted
    publish(m, 14.5, 0.02, "not a time"); // unreadable clock
    publish(m, 2.5, 1, iso(recent)); // a real 100% quote
    publish(m, 3.5, 0, iso(recent)); // a real 0% quote
    pinLine(m, 11.5, 0.33, iso(START - 60 * MIN)); // a pin beside the stale quote
    pinLine(m, 4.5, 0.6, iso(START - 60 * MIN)); // a pin with no quote at all
    const card = built(m, "before");
    expect(rowOf(card, 9.5).pregame).toEqual({ kind: "value", observation: obs("Recorded", 0.45, recent) });
    expect(rowOf(card, 10.5).pregame).toEqual({ kind: "value", observation: obs("Recorded", 0.3, BEFORE_NOW - 30 * MIN) });
    expect(rowOf(card, 2.5).pregame).toEqual({ kind: "value", observation: obs("Recorded", 1, recent) });
    expect(rowOf(card, 3.5).pregame).toEqual({ kind: "value", observation: obs("Recorded", 0, recent) });
    for (const line of [11.5, 12.5, 13.5, 14.5, 4.5]) {
      expect({ line, pregame: rowOf(card, line).pregame }).toEqual({ line, pregame: PREGAME_UNAVAILABLE });
    }
    // Before first pitch there is no in-game slot, no count and no performance.
    expect(card.milestones.every((r) => r.current === null && r.performance === null)).toBe(true);
    expect(card.actual).toBeNull();
    expect(built(m, "before", { score: LIVE_PAIR }).actual).toBeNull();
    // Timing: the pregame reading only, in the leaf's own words.
    expect(rowOf(card, 9.5).timing).toEqual({ title: "10+ runs · chance timing", lines: [`Pregame chance: Recorded ${clockWords(recent)} · Kalshi`] });
    expect(rowOf(card, 12.5).timing.lines).toEqual(["Pregame chance: Pregame chance unavailable"]);
  });

  it("LIVE pregame: the pin (baseline, else the admitted reading) on its own clock, never the quote; no start filter of its own", () => {
    const m = matrix();
    const pinAt = START - 45 * MIN;
    pinLine(m, 9.5, 0.41, iso(pinAt));
    pinLine(m, 11.5, 0.22, iso(START + 5 * MIN)); // stamped after the start: native applies no filter here
    overOf(fullGameAt(m, 12.5)).pregame_reading = {
      state: "available",
      reason: null,
      basis: "pregame_pin",
      probability: 0.18,
      observed_at: iso(pinAt),
      outcome_id: 244311420,
    };
    publish(m, 10.5, 0.37, iso(LIVE_NOW - 2 * MIN)); // a live quote but no pin
    const card = built(m, "live");
    expect(rowOf(card, 9.5).pregame).toEqual({ kind: "value", observation: obs("Saved before first pitch", 0.41, pinAt) });
    expect(rowOf(card, 11.5).pregame).toEqual({ kind: "value", observation: obs("Saved before first pitch", 0.22, START + 5 * MIN) });
    expect(rowOf(card, 12.5).pregame).toEqual({ kind: "value", observation: obs("Saved before first pitch", 0.18, pinAt) });
    expect(rowOf(card, 10.5).pregame).toEqual(PREGAME_UNAVAILABLE);
    expect(rowOf(card, 10.5).current).toEqual({ kind: "recorded", observation: obs("Recorded", 0.37, LIVE_NOW - 2 * MIN) });
  });

  it("LIVE current: a recent quote at or after a readable start is Recorded in-game; pre-start, stale, undated, unquoted, a missing start and noReportedResult are not", () => {
    const m = matrix();
    publish(m, 9.5, 0.6, iso(LIVE_NOW - 2 * MIN)); // recent, after the start
    publish(m, 10.5, 0.4, iso(START)); // exactly at the start
    publish(m, 11.5, 0.3, iso(START - 1)); // recent but a millisecond before the start
    publish(m, 12.5, 0.2, null); // undated
    publish(m, 13.5, 0.1, iso(LIVE_NOW - MIN), "result"); // not quoted
    publish(m, 14.5, 0, iso(LIVE_NOW - MIN)); // a real 0% in-game quote
    const card = built(m, "live");
    expect(rowOf(card, 9.5).current).toEqual({ kind: "recorded", observation: obs("Recorded", 0.6, LIVE_NOW - 2 * MIN) });
    expect(rowOf(card, 10.5).current).toEqual({ kind: "recorded", observation: obs("Recorded", 0.4, START) });
    expect(rowOf(card, 14.5).current).toEqual({ kind: "recorded", observation: obs("Recorded", 0, LIVE_NOW - MIN) });
    for (const line of [11.5, 12.5, 13.5]) expect({ line, current: rowOf(card, line).current }).toEqual({ line, current: IN_GAME_UNAVAILABLE });
    // The pin and the quote stay apart: no pin here, so the pregame slot says so beside the recorded quote.
    expect(rowOf(card, 9.5).pregame).toEqual(PREGAME_UNAVAILABLE);
    expect(rowOf(card, 9.5).timing.lines).toEqual([
      "Pregame chance: Pregame chance unavailable",
      `Recorded in-game: Recorded ${clockWords(LIVE_NOW - 2 * MIN)} · Kalshi`,
    ]);
    expect(rowOf(card, 11.5).timing.lines[1]).toBe("In-game chance: In-game chance unavailable");
    // Stale after the start (CONSTRUCTED later clock).
    const later = START + 60 * MIN;
    const stale = matrix();
    publish(stale, 9.5, 0.6, iso(later - 30 * MIN - 1));
    expect(rowOf(built(stale, "live", { now: later }), 9.5).current).toEqual(IN_GAME_UNAVAILABLE);
    // A missing or unreadable start refuses every quote (CONSTRUCTED event fields).
    for (const start of ["", "not a time"]) {
      const noStart = built(m, "live", { event: { ...EVENT, commence_time: start } });
      for (const line of [9.5, 10.5, 14.5]) {
        expect({ start, line, current: rowOf(noStart, line).current }).toEqual({ start, line, current: IN_GAME_UNAVAILABLE });
      }
    }
    // The page's own noReportedResult withholds every quote; a reached line stays performance.
    const withheld = built(m, "live", { noReportedResult: true });
    for (const line of [9.5, 10.5, 14.5]) expect({ line, current: rowOf(withheld, line).current }).toEqual({ line, current: IN_GAME_UNAVAILABLE });
    expect(rowOf(withheld, 2.5).current).toEqual(REACHED);
  });

  it("LIVE runs so far: only the displayed pair, dated by its own clock; reached lines are performance; others say k more for N+", () => {
    const card = built(matrix(), "live");
    const at = Date.parse(PAIR_AT);
    expect(card.actual).toEqual({
      kind: "count",
      title: "Count so far",
      quantity: 5,
      text: "5",
      unit: "runs",
      clock: timeWords(at),
      ruleLabel: "5 so far",
      detail: `Score observed ${clockWords(at)}`,
    });
    for (const line of [2.5, 3.5, 4.5]) {
      expect({ line, current: rowOf(card, line).current, performance: rowOf(card, line).performance }).toEqual({ line, current: REACHED, performance: null });
    }
    expect(rowOf(card, 2.5).timing.lines[1]).toBe("Actual so far: Reached so far");
    expect([5.5, 9.5, 14.5].map((line) => rowOf(card, line).performance)).toEqual(["1 more for 6+", "5 more for 10+", "10 more for 15+"]);
    // An undated pair: no clock, the count in words; one run is singular.
    expect(built(matrix(), "live", { score: { home: 2, away: 3, observedAt: null } }).actual).toMatchObject({ clock: null, detail: "5 runs so far" });
    expect(built(matrix(), "live", { score: { home: 1, away: 0, observedAt: null } }).actual).toMatchObject({ quantity: 1, unit: "run", detail: "1 run so far" });
    // A real zero is a count: nothing reached yet.
    const zero = built(matrix(), "live", { score: { home: 0, away: 0, observedAt: PAIR_AT } });
    expect(zero.actual).toMatchObject({ kind: "count", quantity: 0, text: "0", ruleLabel: "0 so far" });
    expect(rowOf(zero, 2.5).performance).toBe("3 more for 3+");
    expect(zero.milestones.some((r) => r.current?.kind === "reached")).toBe(false);
  });

  it("LIVE: a missing, partial, invalid or unrepresentable pair is no count (never 0); the event row is never read", () => {
    for (const score of [
      null,
      { home: 3, away: null, observedAt: PAIR_AT },
      { home: null, away: 7, observedAt: PAIR_AT },
      { home: -1, away: 7, observedAt: PAIR_AT },
      { home: 3.5, away: 7, observedAt: PAIR_AT },
      { home: Number.MAX_SAFE_INTEGER, away: 1, observedAt: PAIR_AT },
      { home: Number.MAX_VALUE, away: Number.MAX_VALUE, observedAt: PAIR_AT },
    ]) {
      const card = built(matrix(), "live", { score });
      expect({ score, actual: card.actual }).toEqual({ score, actual: { kind: "unavailable", words: "Score unavailable" } });
      expect(card.milestones.every((r) => r.performance === null && r.current?.kind !== "reached")).toBe(true);
      expect(JSON.stringify(card)).not.toMatch(/Infinity|NaN/);
    }
    // CONSTRUCTED event row that disagrees with the displayed pair: the count is the pair's, or none.
    const rowSays = { ...EVENT, home_score: 9, away_score: 9 };
    expect(built(matrix(), "live", { event: rowSays }).actual).toMatchObject({ kind: "count", quantity: 5 });
    expect(built(matrix(), "live", { event: rowSays, score: null }).actual).toEqual({ kind: "unavailable", words: "Score unavailable" });
  });

  it("the final total and the runs so far are ONE rule over the same pair (the shared RT1 guard); the final leaf is unchanged", () => {
    for (const pair of [
      { home: 3, away: 7 },
      { home: 0, away: 0 },
      { home: 3, away: null },
      { home: -1, away: 7 },
      { home: Number.MAX_SAFE_INTEGER, away: 1 },
      { home: Number.MAX_SAFE_INTEGER - 1, away: 1 },
    ]) {
      const final = totalsOf(realLines(), pair).total;
      const live = built(matrix(), "live", { score: { ...pair, observedAt: null } }).actual;
      expect({ pair, final, live: live?.kind === "count" ? live.quantity : null }).toEqual({ pair, final, live: final });
    }
  });

  it("the default is the nearest even odds among SHOWN pregame chances, ties to the lower line; none shown is no default", () => {
    const tie = matrix();
    publish(tie, 9.5, 0.25, iso(BEFORE_NOW - MIN));
    publish(tie, 10.5, 0.75, iso(BEFORE_NOW - MIN));
    publish(tie, 13.5, 0.5, iso(BEFORE_NOW - 31 * MIN)); // even odds, but stale: not shown, cannot win
    expect(built(tie, "before").defaultId).toBe(keyAt(9.5));
    const reversed = matrix();
    publish(reversed, 9.5, 0.75, iso(BEFORE_NOW - MIN));
    publish(reversed, 10.5, 0.25, iso(BEFORE_NOW - MIN));
    expect(built(reversed, "before").defaultId).toBe(keyAt(9.5));
    publish(tie, 12.5, 0.375, iso(BEFORE_NOW - MIN)); // nearer than either
    expect(built(tie, "before").defaultId).toBe(KEY_12_5);
    // During play the pins decide; an even in-game quote does not.
    const live = matrix();
    pinLine(live, 11.5, 0.25, iso(START - 30 * MIN));
    pinLine(live, 13.5, 0.625, iso(START - 30 * MIN));
    publish(live, 9.5, 0.5, iso(LIVE_NOW - MIN));
    expect(built(live, "live").defaultId).toBe(keyAt(13.5));
    // No shown pregame chance: no default, before or live.
    expect(built(matrix(), "before").defaultId).toBeNull();
    expect(built(matrix(), "live").defaultId).toBeNull();
    const notShown = matrix();
    publish(notShown, 9.5, 0.5, iso(BEFORE_NOW - 31 * MIN));
    pinLine(notShown, 10.5, 0.5, iso(START - 60 * MIN));
    expect(built(notShown, "before").defaultId).toBeNull();
    expect(built(notShown, "live").defaultId).toBe(KEY_10_5);
  });

  it("identity is the option key: a reorder builds the same card; a withdrawn line leaves; a key carried twice is dropped by S1's admission", () => {
    const m = matrix();
    publish(m, 9.5, 0.4, iso(BEFORE_NOW - MIN));
    const base = built(m, "before");
    expect(new Set(base.milestones.map((r) => r.id)).size).toBe(13);
    const reordered = copyOf(m);
    reordered.questions = [...questionsOf(reordered)].reverse();
    expect(built(reordered, "before")).toEqual(base);
    const withdrawn = copyOf(m);
    withdrawn.questions = questionsOf(withdrawn).filter((q) => q !== fullGameAt(withdrawn, 10.5));
    expect(built(withdrawn, "before").milestones.map((r) => r.id)).toEqual(KEYS.filter((k) => k !== KEY_10_5));
    const duplicated = copyOf(m);
    overOf(fullGameAt(duplicated, 12.5)).option_key = KEY_10_5;
    const dup = built(duplicated, "before");
    expect(dup.milestones.map((r) => r.id)).not.toContain(KEY_10_5);
    expect(dup.milestones.map((r) => r.id)).not.toContain(KEY_12_5);
    expect(dup.milestones).toHaveLength(11);
  });
});
