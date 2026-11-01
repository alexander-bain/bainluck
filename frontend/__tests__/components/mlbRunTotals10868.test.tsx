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
 *
 * BEFORE / LIVE (S2b): the same card given `mlbRunMilestones`' input draws
 * S2a's `CountMilestoneCard`. Every before/live quote, pin, clock, start,
 * displayed pair and `noReportedResult` is CONSTRUCTED on a copy of the REAL
 * matrix and named where made; no genuine before/live specimen is claimed.
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import fixture from "../lib/mlbRunTotals10868.fixtures.json";
import mlbFixtures from "../lib/mlbGame10868.fixtures.json";
import { propVerdictLabel } from "@/lib/propGrade";
import { formatProbabilityPercent } from "@/lib/probabilityDisplay";
import {
  MLB_RUN_TOTAL_WORDS,
  mlbFinalTotals,
  mlbRunLines,
  mlbRunMilestones,
  type MlbFinalTotals,
  type MlbRunMilestones,
} from "@/lib/eventPage10868/mlbRunTotals";
import MlbRunTotalsCard, { type MlbRunTotalsSelection } from "@/components/event/eventpage10868/MlbRunTotalsCard";

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

// ─── S2b: before first pitch and during play (CONSTRUCTED phases) ──────────

/** CONSTRUCTED clocks: a listed first pitch, ten minutes before it, and twenty minutes into play. */
const START_ISO = "2026-09-30T23:10:00.000Z";
const START = Date.parse(START_ISO);
const MIN = 60_000;
const BEFORE_NOW = START - 10 * MIN;
const LIVE_NOW = START + 20 * MIN;
const iso = (ms: number) => new Date(ms).toISOString();
/** CONSTRUCTED event fields and displayed pair (2 + 3 = 5 runs, on its own clock). */
const EVENT = { commence_time: START_ISO, sport: "baseball_mlb" };
const LIVE_PAIR = { home: 2, away: 3, observedAt: iso(LIVE_NOW - MIN) };
const BEFORE_SCOPE = "mlb:15321836:before";
const LIVE_SCOPE = "mlb:15321836:live";
const KEY_11_5 = "o:244311421";
const KEY_12_5 = "o:244311420";
const MILESTONE_LABELS = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15].map((n) => `${n}+ runs`);

const overAt = (m: Json, line: number): Json => (fullGameAt(m, line).options as Json[])[0];
/** CONSTRUCTED: the line's Over option published as `state` with `value`, on its own clock. */
function publish(m: Json, line: number, value: unknown, observedAt: string | null, state = "quoted"): void {
  const o = overAt(m, line);
  o.published = { ...(o.published as Json), value, value_state: state, observed_at: observedAt };
}
/** CONSTRUCTED: an admitted pregame pin (comparable baseline). */
function pinLine(m: Json, line: number, probability: number, observedAt: string): void {
  overAt(m, line).comparison = {
    state: "comparable",
    reason: null,
    baseline: { basis: "pregame_pin", probability, observed_at: observedAt },
    latest: null,
    delta_points: null,
  };
}
/** CONSTRUCTED live matrix: pins on 9.5 (30%), 10.5 (45%) and 12.5 (20%); a recorded in-game quote on 11.5 (35%). */
function liveMatrix(): Json {
  const m = matrix();
  pinLine(m, 9.5, 0.3, iso(START - 30 * MIN));
  pinLine(m, 10.5, 0.45, iso(START - 30 * MIN));
  pinLine(m, 12.5, 0.2, iso(START - 30 * MIN));
  publish(m, 11.5, 0.35, iso(LIVE_NOW - 2 * MIN));
  return m;
}
/** The ACTUAL helper over the ACTUAL admission, with the CONSTRUCTED phase inputs. */
function milestonesOf(m: Json, phase: "before" | "live", now = phase === "before" ? BEFORE_NOW : LIVE_NOW): MlbRunMilestones {
  const built = mlbRunMilestones(mlbRunLines(m), phase, EVENT, phase === "live" ? LIVE_PAIR : null, false, now);
  if (!built) throw new Error("no run milestones");
  return built;
}
const showMs = (input: MlbRunMilestones, scope: string, selection?: MlbRunTotalsSelection) =>
  act(() => root.render(<MlbRunTotalsCard totals={input} scope={scope} selection={selection} />));
const msChips = () => Array.from(host.querySelectorAll<HTMLButtonElement>('[data-soccer-card="goals"] li > button[aria-pressed]'));
const msLabel = (b: HTMLButtonElement) => b.querySelector("span")?.textContent ?? null;
const msPressed = () => msChips().filter((b) => b.getAttribute("aria-pressed") === "true").map(msLabel);
const msChosen = () => host.querySelector("[data-soccer-chosen]")?.getAttribute("data-soccer-chosen") ?? null;
const msUnavailable = () => host.querySelector("[data-soccer-selection-unavailable]");
function msChip(label: string): HTMLButtonElement {
  const found = msChips().filter((b) => msLabel(b) === label);
  if (found.length !== 1) throw new Error(`expected one milestone ${label}`);
  return found[0];
}
const readoutTitles = () => Array.from(host.querySelectorAll("[data-soccer-chosen] dt")).map((dt) => dt.textContent);
const readoutValues = () => Array.from(host.querySelectorAll("[data-soccer-chosen] dd")).map((dd) => dd.textContent);
const detailsOffered = () =>
  host.querySelectorAll("[data-soccer-details-entry]").length +
  Array.from(host.querySelectorAll("button")).filter((b) => (b.textContent ?? "").startsWith("Details")).length;

describe("S2b: before first pitch and during play, the same card draws S2a's milestone visual (CONSTRUCTED phases)", () => {
  it("BEFORE (CONSTRUCTED quotes): every line as a milestone in the card's own wrapper, phase words, the shown default, no final markup and no Details", () => {
    const m = matrix();
    publish(m, 9.5, 0.4, iso(BEFORE_NOW - 5 * MIN));
    publish(m, 10.5, 0.55, iso(BEFORE_NOW - 5 * MIN));
    showMs(milestonesOf(m, "before"), BEFORE_SCOPE);
    const wrapper = host.querySelector("[data-mlb-run-totals]");
    expect(wrapper?.getAttribute("data-mlb-run-totals")).toBe(BEFORE_SCOPE);
    expect(wrapper?.getAttribute("data-mlb-run-milestones")).toBe("before");
    expect(host.querySelectorAll('[data-soccer-card="goals"]')).toHaveLength(1);
    expect(host.querySelector("h4")?.textContent).toBe("How many runs?");
    expect(wrapper?.textContent).toContain("TOTAL RUNS · BOTH TEAMS");
    expect(host.querySelector("ul[aria-label]")?.getAttribute("aria-label")).toBe("Choose milestone");
    expect(msChips().map(msLabel)).toEqual(MILESTONE_LABELS);
    // Only the two shown quotes are marks; the others keep their own words; nothing in-game and no count before first pitch.
    expect(host.querySelectorAll('[data-mark="pregame"]')).toHaveLength(2);
    expect(host.querySelectorAll('[data-mark="current"]')).toHaveLength(0);
    expect(host.querySelector('[data-mark="actual-rule"]')).toBeNull();
    expect(msChip("11+ runs").textContent).toContain(formatProbabilityPercent(0.55));
    expect(msChip("3+ runs").textContent).toContain("Pregame chance unavailable");
    // The shown quote nearest even odds opens (55% over 40%).
    expect(msPressed()).toEqual(["11+ runs"]);
    expect(msChosen()).toBe(KEY_10_5);
    // None of the final leaf, no source result, no Details.
    expect(host.querySelector("[data-run-total]")).toBeNull();
    expect(host.querySelector("[data-run-source]")).toBeNull();
    expect(host.textContent).not.toContain(propVerdictLabel(true));
    expect(host.textContent).not.toContain(propVerdictLabel(false));
    expect(detailsOffered()).toBe(0);
  });

  it("LIVE: the pin as pregame, the recorded in-game quote, reached performance and the runs so far, each in its own words", () => {
    showMs(milestonesOf(liveMatrix(), "live"), LIVE_SCOPE);
    expect(host.querySelector("[data-mlb-run-totals]")?.getAttribute("data-mlb-run-milestones")).toBe("live");
    expect(host.querySelector("h4")?.textContent).toBe("Runs so far against the milestones");
    expect(msChip("3+ runs").textContent).toContain("Reached so far");
    expect(msChip("6+ runs").textContent).toContain("1 more for 6+");
    expect(host.querySelectorAll('[data-mark="current"]')).toHaveLength(1);
    expect(host.querySelector(`[data-milestone="${KEY_11_5}"] [data-mark="current"]`)).not.toBeNull();
    expect(host.querySelector('[data-axis-labels="actual"] [data-axis-label="actual"]')?.textContent).toBe("5 so far");
    expect(Array.from(host.querySelectorAll("[data-goals-key-item]")).map((el) => el.getAttribute("data-goals-key-item"))).toEqual([
      "pregame",
      "current",
      "actual",
    ]);
    // The pin nearest even odds opens (10.5 at 45%); its readout keeps pregame and in-game apart.
    expect(msChosen()).toBe(KEY_10_5);
    expect(readoutTitles()).toEqual(["Pregame chance", "In-game chance"]);
    expect(readoutValues()).toEqual([formatProbabilityPercent(0.45), "In-game chance unavailable"]);
    click(msChip("12+ runs"));
    expect(msChosen()).toBe(KEY_11_5);
    expect(readoutTitles()).toEqual(["Pregame chance", "Recorded in-game"]);
    expect(readoutValues()).toEqual(["Pregame chance unavailable", formatProbabilityPercent(0.35)]);
    expect(detailsOffered()).toBe(0);
  });

  it("no shown pregame chance: nothing is chosen until the reader chooses, and no unavailable message", () => {
    showMs(milestonesOf(matrix(), "before"), BEFORE_SCOPE);
    expect(msPressed()).toEqual([]);
    expect(msChosen()).toBeNull();
    expect(msUnavailable()).toBeNull();
    expect(host.textContent).not.toContain("Selected milestone unavailable.");
    click(msChip("9+ runs"));
    expect(msPressed()).toEqual(["9+ runs"]);
    expect(detailsOffered()).toBe(0);
  });

  it("uncontrolled: the chosen line holds through a refresh and a reorder; withdrawn or duplicated it is unavailable with no substitute; its return restores it; a new scope resets", () => {
    showMs(milestonesOf(liveMatrix(), "live"), LIVE_SCOPE);
    click(msChip("13+ runs"));
    expect(msChosen()).toBe(KEY_12_5);
    showMs(milestonesOf(liveMatrix(), "live", LIVE_NOW + 30_000), LIVE_SCOPE); // CONSTRUCTED refresh 30 s later
    expect(msChosen()).toBe(KEY_12_5);
    const reordered = liveMatrix();
    reordered.questions = [...questionsOf(reordered)].reverse();
    showMs(milestonesOf(reordered, "live"), LIVE_SCOPE);
    expect(msChosen()).toBe(KEY_12_5);
    // TEST MUTATIONS: 12.5 withdrawn; 13.5's option carrying 12.5's key (S1's admission drops both).
    const withdrawn = liveMatrix();
    withdrawn.questions = questionsOf(withdrawn).filter((q) => q !== fullGameAt(withdrawn, 12.5));
    const duplicated = liveMatrix();
    overAt(duplicated, 13.5).option_key = KEY_12_5;
    for (const changed of [withdrawn, duplicated]) {
      showMs(milestonesOf(changed, "live"), LIVE_SCOPE);
      expect(msUnavailable()?.textContent).toBe("Selected milestone unavailable.");
      expect(msPressed()).toEqual([]); // never the 10.5 default or a neighbour
      expect(msChosen()).toBeNull();
      expect(msChips().map(msLabel)).not.toContain("13+ runs");
      showMs(milestonesOf(liveMatrix(), "live"), LIVE_SCOPE);
      expect(msChosen()).toBe(KEY_12_5);
      expect(msPressed()).toEqual(["13+ runs"]);
      expect(msUnavailable()).toBeNull();
    }
    // A new phase is a new reading: before first pitch nothing is shown, so nothing is chosen.
    showMs(milestonesOf(matrix(), "before"), BEFORE_SCOPE);
    expect(msChosen()).toBeNull();
    expect(msPressed()).toEqual([]);
    // Back to live: a new reading again, on the live default.
    showMs(milestonesOf(liveMatrix(), "live"), LIVE_SCOPE);
    expect(msChosen()).toBe(KEY_10_5);
  });

  it("controlled (the B1 seam): one onSelect per tap, the card shows only the host's key, and nothing is chosen on the host's behalf", () => {
    const onSelect = jest.fn();
    const input = milestonesOf(liveMatrix(), "live");
    showMs(input, LIVE_SCOPE, { held: null, onSelect });
    expect(msChosen()).toBe(KEY_10_5); // no host choice yet: the shown default
    expect(onSelect).not.toHaveBeenCalled();
    click(msChip("13+ runs"));
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenLastCalledWith(KEY_12_5);
    expect(msChosen()).toBe(KEY_10_5); // the host has not moved its key yet
    showMs(input, LIVE_SCOPE, { held: KEY_12_5, onSelect });
    expect(msChosen()).toBe(KEY_12_5);
    const withdrawn = liveMatrix();
    withdrawn.questions = questionsOf(withdrawn).filter((q) => q !== fullGameAt(withdrawn, 12.5));
    showMs(milestonesOf(withdrawn, "live"), LIVE_SCOPE, { held: KEY_12_5, onSelect });
    expect(msUnavailable()).not.toBeNull();
    expect(msPressed()).toEqual([]);
    showMs(input, LIVE_SCOPE, { held: KEY_12_5, onSelect });
    expect(msChosen()).toBe(KEY_12_5);
    showMs(milestonesOf(matrix(), "before"), BEFORE_SCOPE, { held: null, onSelect });
    expect(msChosen()).toBeNull();
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it("the final input still draws the S1 final leaf in the same component; phases switch between the two without crossing", () => {
    show(REAL());
    expect(text("[data-run-total]")).toBe("10");
    expect(host.querySelector("[data-soccer-card]")).toBeNull();
    expect(host.querySelector("[data-mlb-run-milestones]")).toBeNull();
    showMs(milestonesOf(liveMatrix(), "live"), LIVE_SCOPE);
    expect(host.querySelector("[data-run-total]")).toBeNull();
    expect(host.querySelectorAll('[data-soccer-card="goals"]')).toHaveLength(1);
    show(REAL());
    expect(pressed()).toEqual([KEY_9_5]);
    expect(host.querySelector("[data-soccer-card]")).toBeNull();
  });
});
