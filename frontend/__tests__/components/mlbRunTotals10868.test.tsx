/** @jest-environment jsdom */
/**
 * #10868 — the MLB run-total card, FINAL leaf (`MlbRunTotalsCard`): native
 * `MLBTotalTargetsCardView11284` over `MLBTotalTargetsPresentation11284`.
 *
 * SHIP: a baseball fan sees the final run total against the offered lines,
 * with the pregame chance and source result kept distinct from performance.
 *
 * INPUTS, labelled per test:
 *   - REAL FINAL CAPTURE — `../lib/mlbRunTotals10868.fixtures.json`, the
 *     ENTIRE `game_question_matrix` of the retained 15321836 game-markets body
 *     (final only; never a before or live input), through the real
 *     `mlbRunLines` / `mlbFinalTotals`. The displayed pair is a CONSTRUCTED
 *     host value equal to the retained final row (Astros 3, White Sox 7).
 *   - CONSTRUCTED — reorders, a withdrawn line, a duplicated key, other
 *     scores and other scopes, named where made.
 *
 * jsdom draws no layout: these tests prove what the card states and holds and
 * where each mark is placed on the runs axis (as data), not how it looks at
 * 375 / 393 px or 200% text; only a browser check proves that (owed).
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import fixture from "../lib/mlbRunTotals10868.fixtures.json";
import mlbFixtures from "../lib/mlbGame10868.fixtures.json";
import { propVerdictLabel } from "@/lib/propGrade";
import { MLB_RUN_TOTAL_WORDS, mlbFinalTotals, mlbRunLines, type MlbFinalTotals } from "@/lib/eventPage10868/mlbRunTotals";
import MlbRunTotalsCard from "@/components/event/eventpage10868/MlbRunTotalsCard";

type Json = Record<string, unknown>;
const matrix = (): Json => JSON.parse(JSON.stringify(fixture.game_question_matrix)) as Json;
const questionsOf = (m: Json): Json[] => m.questions as Json[];
const keyOf = (q: Json, field: string): unknown => (q[field] as Json | null | undefined)?.key;
const isFullGameRuns = (q: Json) => q.kind === "count_threshold" && keyOf(q, "quantity") === "runs" && keyOf(q, "period") === "full_game";
function fullGameAt(m: Json, line: number): Json {
  const found = questionsOf(m).filter((q) => isFullGameRuns(q) && (q.predicate as Json).line === line);
  if (found.length !== 1) throw new Error(`expected one full-game question at ${line}`);
  return found[0];
}

const DETAIL = mlbFixtures.finalDetail;
/** CONSTRUCTED host: the displayed pair equal to the retained final row. */
const SCORE = { home: DETAIL.home_score, away: DETAIL.away_score };
const NAMES = { home: DETAIL.home_team, away: DETAIL.away_team };
const SCOPE = "mlb:15321836:final";
const KEY_2_5 = "o:244311416";
const KEY_9_5 = "o:244311417";
const KEY_10_5 = "o:244311422";
const KEY_14_5 = "o:244311418";

function totalsFrom(m: unknown, score: { home: number | null; away: number | null } | null = SCORE): MlbFinalTotals {
  const totals = mlbFinalTotals(mlbRunLines(m), score, NAMES);
  if (!totals) throw new Error("no run-total card");
  return totals;
}
const REAL = () => totalsFrom(fixture.game_question_matrix);

// ─── Harness ───────────────────────────────────────────────────────────────

let host: HTMLDivElement;
let root: Root;

beforeEach(() => {
  (globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

const show = (totals: MlbFinalTotals, scope = SCOPE) => act(() => root.render(<MlbRunTotalsCard totals={totals} scope={scope} />));
function click(el: Element) {
  act(() => {
    el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
}
const text = (selector: string) => host.querySelector(selector)?.textContent ?? null;
const attr = (selector: string, name: string) => host.querySelector(selector)?.getAttribute(name) ?? null;
const choice = (key: string) => {
  const found = host.querySelector<HTMLButtonElement>(`[data-run-choice="${key}"]`);
  if (!found) throw new Error(`no choice ${key}`);
  return found;
};
const choices = () => Array.from(host.querySelectorAll<HTMLButtonElement>("[data-run-choice]"));
const pressed = () => choices().filter((b) => b.getAttribute("aria-pressed") === "true").map((b) => b.getAttribute("data-run-choice"));
const ticks = () => Array.from(host.querySelectorAll("[data-run-tick]")).map((el) => el.getAttribute("data-run-tick"));
const axisLabels = () => Array.from(host.querySelectorAll("[data-run-axis-label]")).map((el) => el.textContent);
const segments = () =>
  Array.from(host.querySelectorAll("[data-run-segment]")).map((el) => [el.getAttribute("data-run-segment"), el.getAttribute("data-run-from"), el.getAttribute("data-run-to")]);
/** What never moves with the selection: the axis, every tick and the bar. */
const scale = () => ({ axis: axisLabels(), ticks: ticks(), segments: segments() });
const sourceWord = () => host.querySelector("[data-run-source] .font-semibold")?.textContent ?? null;

// ─── REAL final capture ────────────────────────────────────────────────────

describe("REAL final capture: the card a fan sees after 15321836", () => {
  it("states the total 10, an unavailable pregame chance, the 9.5 default above the line with its source HIT, and ticks every line", () => {
    show(REAL());
    expect(text("h3")).toBe(MLB_RUN_TOTAL_WORDS.title);
    expect(host.textContent).toContain("RUNS · 13 FULL-GAME LINES");
    expect(text("[data-run-total]")).toBe("10");
    expect(text("[data-run-pregame]")).toBe(MLB_RUN_TOTAL_WORDS.unavailable);
    expect(host.textContent).toContain("Pregame chance · Over 9.5 runs");
    expect(text("[data-run-heading]")).toBe("Over 9.5 runs");
    expect(text("[data-run-comparison]")).toBe("Final 10 runs · above this line");
    expect(sourceWord()).toBe(propVerdictLabel(true));
    expect(pressed()).toEqual([KEY_9_5]);
    expect(attr("[data-run-marker]", "data-run-marker")).toBe("9.5");
    expect(ticks()).toEqual(["2.5", "3.5", "4.5", "5.5", "6.5", "7.5", "8.5", "9.5", "10.5", "11.5", "12.5", "13.5", "14.5"]);
    expect(axisLabels()).toEqual(["0", "5", "10", "15"]);
    expect(segments()).toEqual([
      ["home", "0", "3"],
      ["away", "3", "10"],
    ]);
    expect(text('[data-run-key="home"]')).toBe("Houston Astros 3");
    expect(text('[data-run-key="away"]')).toBe("Chicago White Sox 7");
    expect(text('[data-run-key="marker"]')).toBe("Selected line · 9.5");
  });

  it("every line stays reachable in the strip, each named with its own source result in the one settled vocabulary", () => {
    show(REAL());
    const labels = choices().map((b) => b.getAttribute("aria-label"));
    expect(labels).toHaveLength(13);
    expect(labels[7]).toBe(`Over 9.5 runs. ${MLB_RUN_TOTAL_WORDS.sourceResult} ${propVerdictLabel(true)}.`);
    expect(labels[8]).toBe(`Over 10.5 runs. ${MLB_RUN_TOTAL_WORDS.sourceResult} ${propVerdictLabel(false)}.`);
    expect(labels.filter((l) => l?.endsWith(`${propVerdictLabel(true)}.`))).toHaveLength(8);
    expect(labels.filter((l) => l?.endsWith(`${propVerdictLabel(false)}.`))).toHaveLength(5);
    expect(choices().map((b) => b.textContent)).toEqual(["2.5", "3.5", "4.5", "5.5", "6.5", "7.5", "8.5", "9.5", "10.5", "11.5", "12.5", "13.5", "14.5"]);
    const spoken = `${host.textContent} ${labels.join(" ")}`;
    expect(spoken).not.toMatch(/\bWon\b|\bLost\b/);
  });

  it("choosing 10.5 shows its MISS and the below-line comparison, and the axis, ticks and bar do not move", () => {
    show(REAL());
    const before = scale();
    click(choice(KEY_10_5));
    expect(text("[data-run-heading]")).toBe("Over 10.5 runs");
    expect(text("[data-run-comparison]")).toBe("Final 10 runs · below this line");
    expect(sourceWord()).toBe(propVerdictLabel(false));
    expect(attr("[data-run-marker]", "data-run-marker")).toBe("10.5");
    expect(pressed()).toEqual([KEY_10_5]);
    expect(scale()).toEqual(before);
  });
});

// ─── CONSTRUCTED: the held line ────────────────────────────────────────────

describe("CONSTRUCTED: the held line in one scope", () => {
  it("survives a same-scope refresh and a reorder, by its key alone", () => {
    show(REAL());
    click(choice(KEY_10_5));
    show(REAL()); // a fresh build: new objects, same capture
    expect(pressed()).toEqual([KEY_10_5]);
    const reordered = matrix();
    reordered.questions = [...questionsOf(reordered)].reverse();
    show(totalsFrom(reordered));
    expect(pressed()).toEqual([KEY_10_5]);
    expect(text("[data-run-heading]")).toBe("Over 10.5 runs");
  });

  it("a withdrawn or duplicated key says Selected line unavailable, with no chance, diamond, comparison or result, and returns exactly once", () => {
    show(REAL());
    click(choice(KEY_10_5));
    const withdrawn = matrix();
    withdrawn.questions = questionsOf(withdrawn).filter((q) => q !== fullGameAt(withdrawn, 10.5));
    const duplicated = matrix();
    ((fullGameAt(duplicated, 12.5).options as Json[])[0] as Json).option_key = KEY_10_5;
    for (const changed of [withdrawn, duplicated]) {
      show(totalsFrom(changed));
      expect(text("[data-run-heading]")).toBe(MLB_RUN_TOTAL_WORDS.selectedUnavailable);
      expect(attr("[data-run-selected]", "data-run-selected")).toBe("unavailable");
      expect(host.querySelector("[data-run-comparison]")).toBeNull();
      expect(host.querySelector("[data-run-source]")).toBeNull();
      expect(host.querySelector("[data-run-marker]")).toBeNull();
      expect(host.querySelector("[data-run-stem]")).toBeNull();
      expect(text("[data-run-pregame]")).toBe(MLB_RUN_TOTAL_WORDS.unavailable);
      expect(pressed()).toEqual([]); // never the default 9.5
      expect(ticks()).not.toContain("10.5");
      show(REAL());
      expect(pressed()).toEqual([KEY_10_5]);
      expect(text("[data-run-heading]")).toBe("Over 10.5 runs");
    }
  });

  it("a new event or phase scope resets the held line inside the card, with no parent key", () => {
    show(REAL());
    click(choice(KEY_10_5));
    show(REAL(), "mlb:99000001:final"); // CONSTRUCTED: another event's scope
    expect(pressed()).toEqual([KEY_9_5]);
    click(choice(KEY_14_5));
    show(REAL(), SCOPE); // back: a new reading again, not a memory
    expect(pressed()).toEqual([KEY_9_5]);
  });
});

// ─── CONSTRUCTED: scores and the axis ──────────────────────────────────────

describe("CONSTRUCTED: the displayed pair and the axis", () => {
  it("a partial pair draws no total and no bar, never a zero; the card opens on the lowest line with no comparison", () => {
    show(totalsFrom(fixture.game_question_matrix, { home: 3, away: null }));
    expect(text("[data-run-total]")).toBe(MLB_RUN_TOTAL_WORDS.unavailable);
    expect(attr("[data-run-total]", "data-run-total")).toBe("unavailable");
    expect(segments()).toEqual([]);
    expect(host.querySelector('[data-run-key="home"]')).toBeNull();
    expect(pressed()).toEqual([KEY_2_5]);
    expect(host.querySelector("[data-run-comparison]")).toBeNull();
    expect(sourceWord()).toBe(propVerdictLabel(true));
    expect(axisLabels()).toEqual(["0", "5", "10", "15"]);
  });

  it("a total above 25 takes the 10-run step, and choosing another line never rescales it", () => {
    show(totalsFrom(fixture.game_question_matrix, { home: 20, away: 9 }));
    expect(text("[data-run-total]")).toBe("29");
    expect(axisLabels()).toEqual(["0", "10", "20", "30"]);
    expect(pressed()).toEqual([KEY_14_5]);
    expect(sourceWord()).toBe(propVerdictLabel(false));
    const before = scale();
    expect(before.segments).toEqual([
      ["home", "0", "20"],
      ["away", "20", "29"],
    ]);
    click(choice(KEY_2_5));
    expect(text("[data-run-heading]")).toBe("Over 2.5 runs");
    expect(scale()).toEqual(before);
  });
});
