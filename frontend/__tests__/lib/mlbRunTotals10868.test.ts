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
 */

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fixture from "./mlbRunTotals10868.fixtures.json";
import mlbFixtures from "./mlbGame10868.fixtures.json";
import { formatProbabilityPercent } from "@/lib/probabilityDisplay";
import { propVerdictLabel } from "@/lib/propGrade";
import {
  MLB_RUN_TOTAL_WORDS,
  mlbFinalTotals,
  mlbRunAxis,
  mlbRunComparison,
  mlbRunLines,
  mlbRunSelected,
  type MlbFinalTotals,
  type MlbRunLine,
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
