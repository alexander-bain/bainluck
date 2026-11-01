/** @jest-environment jsdom */
/**
 * #10868 — the MLB web core checkpoint renders its model and its controls work:
 * the team-paired headline away first, the history, and All props with each
 * original's exact Details held by its own identity through a refresh and reset
 * on a new event or phase.
 *
 * Bodies: the REAL retained subsets in `__tests__/lib/mlbGame10868.fixtures.json`
 * (White Sox at Astros 15321836, final 3–7; provenance in its `_header` and in
 * `__tests__/lib/mlbGame10868.test.ts`). CONSTRUCTED, and named where used: every
 * clock and host value; the live event (native `liveEdits`); a refreshed
 * markets body with one earlier row removed, and one with the opened row
 * removed; another event's ids; a before-first-pitch event (native
 * `beforeEdits`) with no hero pair, and a final with no pregame odds and no
 * displayed score, so every headline slot is absent; and forced element widths and a forced root font
 * (jsdom lays nothing out, so these prove the arrangement steps and the
 * enlarged-text branch, never real fit — that is the later 375 / 393 / 1280 px,
 * 100% / 200% browser check on the exact committed export).
 *
 * THE FINAL RUN-TOTAL CARD (binding): its matrix is the REAL whole
 * `game_question_matrix` of the same retained game-markets body, kept in
 * `__tests__/lib/mlbRunTotals10868.fixtures.json` (final only) and joined onto
 * the reduced markets body here — a CONSTRUCTED admission, since the reduced
 * fixture omits the member; neither fixture is edited. CONSTRUCTED, and named
 * where used: other displayed pairs, a withdrawn line, a duplicated key, a
 * wrong scope, a two-line matrix, another event's id, and models handed an
 * input of the wrong kind or another phase (PHASE AGREEMENT, S2c). The
 * row's side-by-side or stacked fit is not provable in jsdom (owed to the
 * browser check); these prove its order, its contents and what it holds.
 * B1 (CONSTRUCTED same-scope passes with no matrix, and a host-held selection
 * given to the card directly): the chosen line is held above the card, so a
 * same-scope absence keeps it; the standalone card's own S1 tests stay as they
 * are and prove its default, uncontrolled behaviour.
 * S2c (every phase): before first pitch and during play the same row draws the
 * run milestones of the page's OWN phase. The joined matrix is still the REAL
 * FINAL capture (every option graded, no pins); every before/live quote, pin,
 * clock, status, displayed pair, raw row score and noReportedResult put around
 * it is CONSTRUCTED and named where made (the listed start is the capture's).
 * No genuine before/live capture exists yet; these prove the binding, not a
 * specimen.
 */
import React, { act } from "react";
import fs from "node:fs";
import path from "node:path";
import { createRoot, type Root } from "react-dom/client";
import fixtures from "../lib/mlbGame10868.fixtures.json";
import runTotalsFixture from "../lib/mlbRunTotals10868.fixtures.json";
import type { EventDetailResponse, EventHistoryResponse } from "@/lib/types";
import type { GameMarketsResponse } from "@/lib/api";
import { PROP_HIT_LABEL, PROP_MISS_LABEL } from "@/lib/propGrade";
import { formatProbabilityPercent } from "@/lib/probabilityDisplay";
import { HISTORY_WORDS } from "@/lib/eventPage10868/hockeyJourneyHistory";
import { MLB_RUN_TOTAL_WORDS } from "@/lib/eventPage10868/mlbRunTotals";
import {
  MLB_ORIGINALS_WORDS,
  MLB_WORDS,
  buildMlbGame,
  type MlbGameHost,
  type MlbGameModel,
  type MlbGameView,
} from "@/lib/eventPage10868/mlbGame";
import MlbGamePage from "@/components/event/eventpage10868/MlbGamePage";
import MlbRunTotalsCard from "@/components/event/eventpage10868/MlbRunTotalsCard";
import { BOTH_TEAMS_LABEL } from "@/components/event/eventpage10868/HockeyJourneyMatrix";

const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x)) as T;
/** A deep copy with keys replaced — a TEST MUTATION (CONSTRUCTED). */
const mutate = <T,>(x: T, patch: Record<string, unknown>): T => ({ ...clone(x), ...patch });

const finalDetail = fixtures.finalDetail as unknown as EventDetailResponse;
const finalHistory = fixtures.finalHistory as unknown as EventHistoryResponse;
const finalMarkets = fixtures.finalMarkets as unknown as GameMarketsResponse;

/** REAL: the capture's retrieval instant. CONSTRUCTED: the live clock and its host clock (native). */
const FINAL_NOW = Date.parse("2026-10-11T04:57:23.592725Z");
const LIVE_NOW = Date.parse("2026-10-01T00:16:30Z");
const LIVE_OBSERVED = "2026-10-01T00:15:57.061753Z";

/** CONSTRUCTED: native `liveEdits` over the real final. */
const liveDetail = mutate(finalDetail, {
  status: "live",
  completed_at: null,
  hero_settled_result: null,
  hero_probability: null,
  hero_probability_away: null,
  hero_probability_source: null,
});

/** CONSTRUCTED host answers; every key explicit. */
const finalHost: MlbGameHost = {
  nowMs: FINAL_NOW,
  hero: null,
  probabilityObservedAt: null,
  deliveryInterrupted: false,
  liveClaimUnbacked: false,
  score: { home: 3, away: 7, observedAt: null },
  projectedFinal: null,
};
/** CONSTRUCTED: the served live quote as the hero's pair, a displayed 3–6 and an admitted 4–7. */
const liveHost: MlbGameHost = {
  nowMs: LIVE_NOW,
  hero: { homeProb: 0.001, awayProb: 0.999, homePct: 0, awayPct: 100, probSourceLabel: null },
  probabilityObservedAt: LIVE_OBSERVED,
  deliveryInterrupted: false,
  liveClaimUnbacked: false,
  score: { home: 3, away: 6, observedAt: LIVE_OBSERVED },
  projectedFinal: { home: 4, away: 7 },
};

/** CONSTRUCTED: one minute before the retained game's listed first pitch (21:00 UTC). */
const BEFORE_NOW = Date.parse("2026-09-30T20:59:00Z");
/** CONSTRUCTED: native `beforeEdits` over the real final, one minute before first pitch, with no hero pair. */
const beforeDetail = mutate(finalDetail, {
  status: "scheduled",
  completed_at: null,
  home_score: null,
  away_score: null,
  hero_settled_result: null,
  hero_probability: null,
  hero_probability_away: null,
  hero_probability_source: null,
});
const beforeHost: MlbGameHost = { ...finalHost, nowMs: BEFORE_NOW, score: null };

function model(
  event: EventDetailResponse,
  host: MlbGameHost,
  bodies: { history?: EventHistoryResponse | null; gameMarkets?: GameMarketsResponse | null } = {},
): MlbGameModel {
  return buildMlbGame({
    event,
    history: bodies.history === undefined ? finalHistory : bodies.history,
    gameMarkets: bodies.gameMarkets === undefined ? finalMarkets : bodies.gameMarkets,
    host,
  });
}
const view = (m: MlbGameModel): MlbGameView => {
  if (m.kind !== "game") throw new Error("refused");
  return m;
};

/** CONSTRUCTED refresh: the same body without the player prop at `index` (served order otherwise kept). */
function marketsWithout(index: number): GameMarketsResponse {
  const body = clone(finalMarkets) as unknown as { player_props: unknown[] };
  body.player_props.splice(index, 1);
  return body as unknown as GameMarketsResponse;
}

/** The Kalshi home-run rung (served row 33): Jeremy Peña 1+, market 64514605, outcome 242692574. */
const PENA_KEY = "kalshi|64514605|242692574";
const PENA_ROW = 33;

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
  jest.restoreAllMocks();
});

function render(m: MlbGameModel) {
  act(() => root.render(<MlbGamePage model={m} />));
}

function click(el: Element) {
  act(() => {
    el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
}

function entryButton(): HTMLButtonElement {
  const found = Array.from(host.querySelectorAll("button")).find((b) => /original outcome/.test(b.textContent ?? ""));
  if (!found) throw new Error("no All props entry");
  return found;
}

const detailsButtons = () => Array.from(host.querySelectorAll("button")).filter((b) => (b.textContent ?? "").startsWith("Details"));
const openDetails = () => detailsButtons().filter((b) => b.getAttribute("aria-expanded") === "true");

function penaOriginal(m: MlbGameModel) {
  const found = view(m).originals.originals.find((o) => o.key === PENA_KEY);
  if (!found) throw new Error("no Peña original");
  return found;
}

/** The Peña row's Details button, found by what its accessible name says (its prop, side and venue), not by an exact template. */
function penaDetails(m: MlbGameModel): HTMLButtonElement | null {
  const o = penaOriginal(m);
  return (
    detailsButtons().find((b) => {
      const name = b.textContent ?? "";
      return name.includes(o.title) && name.includes(o.label) && (!o.about.source || name.includes(o.about.source));
    }) ?? null
  );
}

// ─── The headline ──────────────────────────────────────────────────────────

describe("the headline", () => {
  it("FINAL (REAL): away first, pregame chance beside the final runs with Won / Lost, the projection said once", () => {
    const m = model(finalDetail, finalHost);
    render(m);
    const section = host.querySelector("section[data-mlb-game='final']");
    expect(section?.getAttribute("aria-label")).toBe(MLB_WORDS.spokenLabel);
    expect(host.querySelector("header")?.textContent).toContain("Final");
    const rows = Array.from(host.querySelectorAll("table tbody tr"));
    expect(rows.map((r) => r.querySelector("th")?.textContent ?? "")).toEqual([
      expect.stringContaining("Chicago White Sox"),
      expect.stringContaining("Houston Astros"),
    ]);
    expect(rows[0].textContent).toContain("Won");
    expect(rows[1].textContent).toContain("Lost");
    const cells = rows.map((r) => Array.from(r.querySelectorAll("td")).map((td) => td.textContent ?? ""));
    expect(cells[0]).toEqual([expect.stringContaining("41%"), expect.stringContaining("7")]);
    expect(cells[1]).toEqual([expect.stringContaining("59%"), expect.stringContaining("3")]);
    expect(host.querySelector("[data-matrix-shared-absences]")?.textContent).toBe(
      `${BOTH_TEAMS_LABEL}${MLB_WORDS.pregameProjectedFinal}:${MLB_WORDS.unavailable}`,
    );
    // The grid names the teams; no second names line is added.
    expect(host.querySelector("[data-mlb-team-names]")).toBeNull();
    const table = host.querySelector("table")?.textContent ?? "";
    expect(table).not.toContain("100%");
    expect(table).not.toContain(">99%");
    // Each column's source and clock is said once, under the matrix.
    expect(host.textContent).toContain("Pregame chance:Pre-match");
    expect(host.textContent).toContain("Final runs:Final score");
  });

  it("LIVE (CONSTRUCTED): pregame, current (the largest figure), runs and projected final in one aligned grid", () => {
    render(model(liveDetail, liveHost));
    const titles = Array.from(host.querySelectorAll("table thead th"))
      .map((th) => th.textContent ?? "")
      .filter((t) => t !== "Team");
    expect(titles).toEqual(["Pregame chance", "Current chance", "Runs", "Projected final"]);
    expect(host.querySelector("[data-mlb-team-names]")).toBeNull();
    const rows = Array.from(host.querySelectorAll("table tbody tr"));
    const cells = rows.map((r) => Array.from(r.querySelectorAll("td")).map((td) => td.textContent ?? ""));
    // Away first: White Sox 41% · >99% · 6 runs · 7 runs projected; Astros 59% · <1% · 3 · 4.
    expect(cells[0]).toEqual(["41%41 percent", ">99%over 99 percent", "66 runs", "77 runs"]);
    expect(cells[1]).toEqual(["59%59 percent", "<1%under 1 percent", "33 runs", "44 runs"]);
    const lead = rows[0].querySelectorAll("td")[1].querySelector("[aria-hidden='true']");
    expect(lead?.className).toContain("text-3xl");
    const runs = rows[0].querySelectorAll("td")[2].querySelector("[aria-hidden='true']");
    expect(runs?.className).toContain("text-xl");
    expect(runs?.className).not.toContain("text-text-secondary");
  });

  it("a narrow frame keeps the four live columns aligned (names above) before falling back to labelled pairs", () => {
    const proto = HTMLElement.prototype as unknown as Record<string, unknown>;
    Object.defineProperty(proto, "clientWidth", { configurable: true, get: () => 300 });
    Object.defineProperty(proto, "scrollWidth", {
      configurable: true,
      get(this: HTMLElement) {
        if (this.dataset?.arrangement === undefined) return 0;
        // CONSTRUCTED: any grid with a team column beside four metrics overflows the 300 px frame.
        return this.querySelectorAll("thead th").length >= 5 ? 1000 : 300;
      },
    });
    try {
      render(model(liveDetail, liveHost));
      expect(host.querySelector("[data-arrangement]")?.getAttribute("data-arrangement")).toBe("compactNamesAbove");
      const names = Array.from(host.querySelectorAll('th[scope="rowgroup"]')).map((th) => th.textContent ?? "");
      expect(names).toEqual([expect.stringContaining("Chicago White Sox"), expect.stringContaining("Houston Astros")]);
    } finally {
      delete proto.clientWidth;
      delete proto.scrollWidth;
    }
  });

  it("at enlarged text (200%, CONSTRUCTED root font) each team is one labelled block holding every figure", () => {
    jest.spyOn(window, "getComputedStyle").mockImplementation(((el: Element) =>
      ({ fontSize: el === document.documentElement ? "32px" : "16px" }) as unknown as CSSStyleDeclaration) as typeof window.getComputedStyle);
    render(model(liveDetail, liveHost));
    expect(host.querySelector("[data-arrangement]")?.getAttribute("data-arrangement")).toBe("pairs");
    expect(host.querySelector("table")).toBeNull();
    const blocks = Array.from(host.querySelectorAll('[data-arrangement] [role="group"]'));
    expect(blocks.map((b) => b.getAttribute("aria-label"))).toEqual(["Chicago White Sox", "Houston Astros"]);
    expect(Array.from(blocks[0].querySelectorAll("dt")).map((dt) => dt.textContent)).toEqual([
      "Pregame chance",
      "Current chance",
      "Runs",
      "Projected final",
    ]);
    // Words wrap as words: nothing in the state lines or the matrix splits inside a word.
    expect(host.querySelector("header")?.innerHTML).not.toContain("break-all");
    expect(host.querySelector("[data-hockey-matrix]")?.innerHTML).not.toContain("break-all");
  });
});

// ─── Team names when nothing in the headline is readable (M2) ──────────────

describe("team names when no headline slot holds a readable value", () => {
  /** CONSTRUCTED host: no hero pair, no score, no projection — every slot is its absence words. */
  const emptyHost: MlbGameHost = {
    nowMs: Date.parse("2026-09-30T20:59:00Z"),
    hero: null,
    probabilityObservedAt: null,
    deliveryInterrupted: false,
    liveClaimUnbacked: false,
    score: null,
    projectedFinal: null,
  };
  const namesLine = () => host.querySelector("[data-mlb-team-names]");

  it("every slot absent: the away and home names stay visible once, beside the unchanged Both teams lines", () => {
    const m = model(beforeDetail, emptyHost);
    const v = view(m);
    expect(v.phase).toBe("before");
    expect(v.headline.matrix.rows.every((r) => r.values.every((slot) => slot.kind === "absent") && !r.result)).toBe(true);
    render(m);
    // The shared matrix draws no team row: every column is said once under Both teams, as before.
    expect(host.querySelector("table")).toBeNull();
    const shared = host.querySelector("[data-matrix-shared-absences]")?.textContent ?? "";
    expect(shared.startsWith(BOTH_TEAMS_LABEL)).toBe(true);
    for (const column of v.headline.matrix.columns) expect(shared).toContain(column.title);
    // The model's own names, away first, each once in the headline, with no figure beside them.
    const names = Array.from(namesLine()?.querySelectorAll("li") ?? []).map((li) => li.textContent);
    expect(names).toEqual([v.headline.away.name, v.headline.home.name]);
    const headlineText = namesLine()?.parentElement?.textContent ?? "";
    for (const name of names) expect(headlineText.split(name ?? "").length - 1).toBe(1);
    expect(namesLine()?.textContent).not.toMatch(/[0-9%]/);
  });

  it("every slot absent but a result to show: the grid names the teams, so no names line is added", () => {
    // TEST MUTATION (CONSTRUCTED): no pregame odds and no displayed score; the served verdict still says who won.
    const m = model(mutate(finalDetail, { prematch_odds: null, opening_odds: null }), { ...finalHost, score: null });
    const v = view(m);
    expect(v.headline.matrix.rows.every((r) => r.values.every((slot) => slot.kind === "absent"))).toBe(true);
    expect(v.headline.matrix.rows.every((r) => !!r.result)).toBe(true);
    render(m);
    expect(namesLine()).toBeNull();
    const rows = Array.from(host.querySelectorAll("table tbody tr"));
    expect(rows.map((r) => r.querySelector("th")?.textContent ?? "")).toEqual([
      expect.stringContaining(v.headline.away.name),
      expect.stringContaining(v.headline.home.name),
    ]);
  });
});

// ─── All props: exact Details, held identity, reset ────────────────────────

describe("All props", () => {
  it("opens one original's exact Details: its own market id, outcome id and graded result", () => {
    const m = model(finalDetail, finalHost);
    render(m);
    const entry = entryButton();
    expect(entry.textContent).toBe(view(m).allPropsLabel);
    click(entry);
    const details = penaDetails(m);
    expect(details).not.toBeNull();
    click(details!);
    const region = document.getElementById(details!.getAttribute("aria-controls") ?? "");
    expect(region?.hidden).toBe(false);
    const text = region?.textContent ?? "";
    expect(text).toContain("Market ID64514605");
    expect(text).toContain("Outcome ID242692574");
    expect(text).toContain(PROP_HIT_LABEL);
    expect(openDetails()).toHaveLength(1);
  });

  it("a refresh in the same scope keeps the list and THAT original's Details open, by its exact key", () => {
    const first = model(finalDetail, finalHost);
    render(first);
    click(entryButton());
    click(penaDetails(first)!);
    // CONSTRUCTED refresh: an earlier served row (row 0) is gone, so every later original moves up one place.
    const refreshed = model(finalDetail, { ...finalHost, nowMs: FINAL_NOW + 60_000 }, { gameMarkets: marketsWithout(0) });
    expect(view(refreshed).originals.scope).toBe(view(first).originals.scope);
    render(refreshed);
    expect(entryButton().getAttribute("aria-expanded")).toBe("true");
    const open = openDetails();
    expect(open).toHaveLength(1);
    expect(open[0]).toBe(penaDetails(refreshed));
    const region = document.getElementById(open[0].getAttribute("aria-controls") ?? "");
    expect(region?.textContent).toContain("Outcome ID242692574");
  });

  it("a withdrawn original takes its Details with it and nothing else opens in its place", () => {
    const first = model(finalDetail, finalHost);
    render(first);
    click(entryButton());
    click(penaDetails(first)!);
    const withdrawn = model(finalDetail, finalHost, { gameMarkets: marketsWithout(PENA_ROW) });
    expect(view(withdrawn).originals.originals.some((o) => o.key === PENA_KEY)).toBe(false);
    render(withdrawn);
    expect(penaDetails(first)).toBeNull();
    expect(openDetails()).toHaveLength(0);
    expect(host.textContent).not.toContain("Outcome ID242692574");
  });

  it("a new phase resets the reading: no list, Details or choice survives live → final", () => {
    const live = model(liveDetail, liveHost);
    render(live);
    click(entryButton());
    click(detailsButtons()[0]);
    expect(openDetails()).toHaveLength(1);
    render(model(finalDetail, finalHost));
    expect(entryButton().getAttribute("aria-expanded")).toBe("false");
    expect(openDetails()).toHaveLength(0);
  });

  it("a new event resets the reading too (CONSTRUCTED: the same bodies under another id)", () => {
    render(model(finalDetail, finalHost));
    click(entryButton());
    click(detailsButtons()[0]);
    const other = model(mutate(finalDetail, { id: 15321837 }), finalHost, {
      history: mutate(finalHistory, { event_id: 15321837 }),
      gameMarkets: mutate(finalMarkets, { event_id: 15321837 }),
    });
    render(other);
    expect(entryButton().getAttribute("aria-expanded")).toBe("false");
    expect(openDetails()).toHaveLength(0);
  });

  it("another event's bodies are never drawn: History unavailable, and All props says so in its own words", () => {
    render(
      model(finalDetail, finalHost, {
        history: mutate(finalHistory, { event_id: 1 }),
        gameMarkets: mutate(finalMarkets, { event_id: 1 }),
      }),
    );
    expect(host.querySelector("section")?.getAttribute("data-history-foreign")).toBe("true");
    expect(host.textContent).toContain("History unavailable");
    expect(host.textContent).toContain(MLB_ORIGINALS_WORDS.emptyWords);
    expect(detailsButtons()).toHaveLength(0);
  });
});

// ─── The final run-total card beside the history (binding) ─────────────────

type Json = Record<string, unknown>;
/** REAL: the whole retained matrix of this game's own game-markets body, a fresh copy each call. */
const ownMatrix = (): Json => clone(runTotalsFixture.game_question_matrix) as unknown as Json;
/** CONSTRUCTED admission: the reduced markets body with a matrix joined on (anything but `ownMatrix()` is a TEST MUTATION). */
const withMatrix = (matrix: unknown, body: GameMarketsResponse = finalMarkets): GameMarketsResponse =>
  mutate(body, { game_question_matrix: matrix });
const isFullGameRuns = (q: Json) =>
  q.kind === "count_threshold" && (q.quantity as Json | null)?.key === "runs" && (q.period as Json | null)?.key === "full_game";
const lineOf = (q: Json) => (q.predicate as Json).line;
/** TEST MUTATION: the own matrix with only the full-game lines `keep` (every other question kept). */
function matrixKeeping(keep: number[]): Json {
  const m = ownMatrix();
  m.questions = (m.questions as Json[]).filter((q) => !isFullGameRuns(q) || keep.includes(lineOf(q) as number));
  return m;
}
const LINE_TEXTS = ["2.5", "3.5", "4.5", "5.5", "6.5", "7.5", "8.5", "9.5", "10.5", "11.5", "12.5", "13.5", "14.5"];
const KEY_2_5 = "o:244311416";
const KEY_9_5 = "o:244311417";
const KEY_10_5 = "o:244311422";
const KEY_11_5 = "o:244311421";

const historyRow = () => host.querySelector("[data-mlb-history-row]");
const rowItems = () => Array.from(historyRow()?.children ?? []).map((el) => el.getAttribute("data-mlb-row-item"));
const historyChart = () => historyRow()?.children[0]?.querySelector("section") ?? null;
const historyDisclosure = () => Array.from(host.querySelectorAll("button")).find((b) => b.textContent === HISTORY_WORDS.details) ?? null;
const runCard = () => host.querySelector("[data-mlb-run-totals]");
const runText = (selector: string) => runCard()?.querySelector(selector)?.textContent ?? null;
const runChoices = () => Array.from(host.querySelectorAll<HTMLButtonElement>("[data-run-choice]"));
function runChoice(key: string): HTMLButtonElement {
  const found = host.querySelector<HTMLButtonElement>(`[data-run-choice="${key}"]`);
  if (!found) throw new Error(`no run line ${key}`);
  return found;
}
const pressedRuns = () =>
  runChoices()
    .filter((b) => b.getAttribute("aria-pressed") === "true")
    .map((b) => b.getAttribute("data-run-choice"));
const runSegments = () =>
  Array.from(host.querySelectorAll("[data-run-segment]")).map((el) => [
    el.getAttribute("data-run-segment"),
    el.getAttribute("data-run-from"),
    el.getAttribute("data-run-to"),
  ]);
const sourceSays = (verdict: string) => `${MLB_RUN_TOTAL_WORDS.sourceResult} ${verdict}`;

describe("the final run-total card beside the history", () => {
  it("REAL final 3–7: history then card in one row; total 10, 13 lines, 9.5 by default with its HIT, 10.5 with its MISS", () => {
    const m = model(finalDetail, finalHost, { gameMarkets: withMatrix(ownMatrix()) });
    render(m);
    expect(rowItems()).toEqual(["history", "runTotals"]);
    expect(historyChart()?.querySelector("h3")?.textContent).toBe(view(m).history.title);
    expect(historyRow()?.children[1]?.querySelector("[data-mlb-run-totals]")).toBe(runCard());
    expect(runCard()?.getAttribute("data-mlb-run-totals")).toBe("mlb:15321836:final");
    expect(runCard()?.querySelector("h3")?.textContent).toBe(MLB_RUN_TOTAL_WORDS.title);
    expect(runCard()?.textContent).toContain(MLB_RUN_TOTAL_WORDS.eyebrow(13));
    expect(runText("[data-run-total]")).toBe("10");
    expect(runText("[data-run-pregame]")).toBe(MLB_RUN_TOTAL_WORDS.unavailable);
    expect(runText('[data-run-key="home"]')).toBe("Houston Astros 3");
    expect(runText('[data-run-key="away"]')).toBe("Chicago White Sox 7");
    expect(runChoices().map((b) => b.textContent)).toEqual(LINE_TEXTS);
    expect(pressedRuns()).toEqual([KEY_9_5]);
    expect(runText("[data-run-heading]")).toBe("Over 9.5 runs");
    expect(runText("[data-run-comparison]")).toBe("Final 10 runs · above this line");
    expect(runText("[data-run-source]")).toBe(sourceSays(PROP_HIT_LABEL));
    // Each line carries the venue's own result, independent of the comparison: 8 HIT, then 5 MISS.
    const labels = runChoices().map((b) => b.getAttribute("aria-label") ?? "");
    expect(labels.filter((l) => l.endsWith(`${PROP_HIT_LABEL}.`))).toHaveLength(8);
    expect(labels.filter((l) => l.endsWith(`${PROP_MISS_LABEL}.`))).toHaveLength(5);
    click(runChoice(KEY_10_5));
    expect(pressedRuns()).toEqual([KEY_10_5]);
    expect(runText("[data-run-heading]")).toBe("Over 10.5 runs");
    expect(runText("[data-run-comparison]")).toBe("Final 10 runs · below this line");
    expect(runText("[data-run-source]")).toBe(sourceSays(PROP_MISS_LABEL));
    // No reader and no Details on the new card in this increment.
    expect(runCard()?.querySelector("[aria-expanded]")).toBeNull();
    expect(Array.from(runCard()?.querySelectorAll("button") ?? []).some((b) => /Details/.test(b.textContent ?? ""))).toBe(false);
  });

  it("the card changes nothing around it: the headline (D1 = B), the away-first rows and All props read the same with and without it", () => {
    render(model(finalDetail, finalHost));
    expect(runCard()).toBeNull();
    const headlineBefore = host.querySelector("[data-hockey-matrix]")?.outerHTML;
    const stateBefore = host.querySelector("header")?.outerHTML;
    const entryBefore = entryButton().textContent;
    render(model(finalDetail, finalHost, { gameMarkets: withMatrix(ownMatrix()) }));
    expect(runCard()).not.toBeNull();
    expect(host.querySelector("[data-hockey-matrix]")?.outerHTML).toBe(headlineBefore);
    expect(host.querySelector("header")?.outerHTML).toBe(stateBefore);
    expect(host.querySelector("[data-matrix-shared-absences]")?.textContent).toBe(
      `${BOTH_TEAMS_LABEL}${MLB_WORDS.pregameProjectedFinal}:${MLB_WORDS.unavailable}`,
    );
    const rows = Array.from(host.querySelectorAll("table tbody tr"));
    expect(rows.map((r) => r.querySelector("th")?.textContent ?? "")).toEqual([
      expect.stringContaining("Chicago White Sox"),
      expect.stringContaining("Houston Astros"),
    ]);
    expect(entryButton().textContent).toBe(entryBefore);
    // All props comes after the row, and its exact Details still open.
    const following = historyRow()?.compareDocumentPosition(entryButton()) ?? 0;
    expect(following & Node.DOCUMENT_POSITION_FOLLOWING).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    click(entryButton());
    click(penaDetails(model(finalDetail, finalHost))!);
    expect(openDetails()).toHaveLength(1);
  });

  it("the card says the headline's DISPLAYED pair, not the raw event final (CONSTRUCTED host pair 4–8 over the row's 3–7)", () => {
    render(model(finalDetail, { ...finalHost, score: { home: 4, away: 8, observedAt: null } }, { gameMarkets: withMatrix(ownMatrix()) }));
    const rows = Array.from(host.querySelectorAll("table tbody tr"));
    const cells = rows.map((r) => Array.from(r.querySelectorAll("td")).map((td) => td.textContent ?? ""));
    expect(cells[0][1]).toContain("8 runs"); // away first
    expect(cells[1][1]).toContain("4 runs");
    expect(runText("[data-run-total]")).toBe("12");
    expect(runText('[data-run-key="home"]')).toBe("Houston Astros 4");
    expect(runText('[data-run-key="away"]')).toBe("Chicago White Sox 8");
    expect(runSegments()).toEqual([
      ["home", "0", "4"],
      ["away", "4", "12"],
    ]);
    expect(pressedRuns()).toEqual([KEY_11_5]);
    expect(runText("[data-run-comparison]")).toBe("Final 12 runs · above this line");
    // The venue graded 11.5 on the real game (lost); the card never regrades it from the pair.
    expect(runText("[data-run-source]")).toBe(sourceSays(PROP_MISS_LABEL));
  });

  it("a partial or missing displayed pair: Unavailable total and no bar, never a zero, every line still offered (CONSTRUCTED host)", () => {
    for (const score of [{ home: 3, away: null, observedAt: null }, null]) {
      render(model(finalDetail, { ...finalHost, score }, { gameMarkets: withMatrix(ownMatrix()) }));
      expect(runText("[data-run-total]")).toBe(MLB_RUN_TOTAL_WORDS.unavailable);
      expect(runCard()?.querySelector("[data-run-total]")?.getAttribute("data-run-total")).toBe("unavailable");
      expect(runSegments()).toEqual([]);
      expect(host.querySelector('[data-run-key="home"]')).toBeNull();
      expect(host.querySelector('[data-run-key="away"]')).toBeNull();
      expect(host.querySelector("[data-run-comparison]")).toBeNull();
      expect(runChoices().map((b) => b.textContent)).toEqual(LINE_TEXTS);
      expect(pressedRuns()).toEqual([KEY_2_5]);
      expect(runCard()?.textContent).not.toMatch(/Final 0|Final 3 runs|Final 10 runs/);
    }
  });

  it("no card for another event's body, a wrong scope, two full-game lines or no matrix: the history stays alone; the own matrix restores it", () => {
    const refusals: Array<[string, GameMarketsResponse]> = [
      ["another event's body (TEST MUTATION: event_id 1)", mutate(withMatrix(ownMatrix()), { event_id: 1 })],
      ["a series-scoped matrix (TEST MUTATION)", withMatrix({ ...ownMatrix(), display_scope: "series" })],
      ["two full-game lines (TEST MUTATION)", withMatrix(matrixKeeping([2.5, 3.5]))],
      ["the reduced body, with no matrix member", finalMarkets],
    ];
    for (const [name, gameMarkets] of refusals) {
      render(model(finalDetail, finalHost, { gameMarkets }));
      expect({ name, card: runCard(), items: rowItems() }).toEqual({ name, card: null, items: ["history"] });
      expect(runChoices()).toHaveLength(0);
    }
    render(model(finalDetail, finalHost, { gameMarkets: withMatrix(ownMatrix()) }));
    expect(rowItems()).toEqual(["history", "runTotals"]);
    expect(runChoices()).toHaveLength(13);
  });

  it("before and live draw the milestone card of the page's OWN phase; a wrong-kind or wrong-phase input draws none (CONSTRUCTED)", () => {
    const markets = withMatrix(ownMatrix());
    const beforeM = model(beforeDetail, beforeHost, { gameMarkets: markets });
    const liveM = model(liveDetail, liveHost, { gameMarkets: markets });
    const finalM = model(finalDetail, finalHost, { gameMarkets: markets });
    render(beforeM);
    expect(host.querySelector("section[data-mlb-game='before']")).not.toBeNull();
    expect(rowItems()).toEqual(["history", "runTotals"]);
    expect([runCard()?.getAttribute("data-mlb-run-totals"), runCard()?.getAttribute("data-mlb-run-milestones")]).toEqual(["mlb:15321836:before", "before"]);
    expect(host.querySelector("[data-run-total]")).toBeNull();
    render(liveM);
    expect(host.querySelector("section[data-mlb-game='live']")).not.toBeNull();
    expect([runCard()?.getAttribute("data-mlb-run-totals"), runCard()?.getAttribute("data-mlb-run-milestones")]).toEqual(["mlb:15321836:live", "live"]);
    expect(runCard()?.querySelectorAll('[data-soccer-card="goals"]')).toHaveLength(1);
    expect(host.querySelector("[data-run-total]")).toBeNull();
    // CONSTRUCTED mismatches: the wrong kind and the wrong phase each draw no card — never a final card during play.
    const mismatches: Array<[string, MlbGameModel]> = [
      ["a final card on the live page", { ...view(liveM), runTotals: view(finalM).runTotals }],
      ["live milestones on the final page", { ...view(finalM), runTotals: view(liveM).runTotals }],
      ["before milestones on the live page", { ...view(liveM), runTotals: view(beforeM).runTotals }],
      ["live milestones on the before page", { ...view(beforeM), runTotals: view(liveM).runTotals }],
    ];
    for (const [name, misfit] of mismatches) {
      render(misfit);
      expect({ name, card: runCard(), items: rowItems() }).toEqual({ name, card: null, items: ["history"] });
    }
    // Non-vacuity: every borrowed input is a real card on its own page.
    for (const own of [beforeM, liveM, finalM]) {
      render(own);
      expect(rowItems()).toEqual(["history", "runTotals"]);
    }
  });

  it("a same-scope refresh keeps the chosen line; a withdrawn or duplicated key never substitutes, and the line returns by its key", () => {
    render(model(finalDetail, finalHost, { gameMarkets: withMatrix(ownMatrix()) }));
    click(runChoice(KEY_10_5));
    // CONSTRUCTED refresh: a minute later, every object rebuilt, the same scope.
    render(model(finalDetail, { ...finalHost, nowMs: FINAL_NOW + 60_000 }, { gameMarkets: withMatrix(ownMatrix()) }));
    expect(pressedRuns()).toEqual([KEY_10_5]);
    // TEST MUTATIONS: 10.5 withdrawn; 12.5's option carrying 10.5's key.
    const withdrawn = matrixKeeping([2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5, 11.5, 12.5, 13.5, 14.5]);
    const duplicated = ownMatrix();
    const at12 = (duplicated.questions as Json[]).find((q) => isFullGameRuns(q) && lineOf(q) === 12.5) as Json;
    ((at12.options as Json[])[0] as Json).option_key = KEY_10_5;
    for (const changed of [withdrawn, duplicated]) {
      render(model(finalDetail, finalHost, { gameMarkets: withMatrix(changed) }));
      expect(runText("[data-run-heading]")).toBe(MLB_RUN_TOTAL_WORDS.selectedUnavailable);
      expect(pressedRuns()).toEqual([]); // never the default 9.5 or a neighbour
      expect(host.querySelector("[data-run-source]")).toBeNull();
      expect(host.querySelector("[data-run-comparison]")).toBeNull();
      expect(host.querySelector("[data-run-marker]")).toBeNull();
      expect(runChoices().map((b) => b.textContent)).not.toContain("10.5");
      render(model(finalDetail, finalHost, { gameMarkets: withMatrix(ownMatrix()) }));
      expect(pressedRuns()).toEqual([KEY_10_5]);
      expect(runText("[data-run-heading]")).toBe("Over 10.5 runs");
    }
  });

  it("a new event or phase resets the chosen line (CONSTRUCTED: the same bodies under another id; final → live → final)", () => {
    render(model(finalDetail, finalHost, { gameMarkets: withMatrix(ownMatrix()) }));
    click(runChoice(KEY_10_5));
    const otherId = 15321837;
    render(
      model(mutate(finalDetail, { id: otherId }), finalHost, {
        history: mutate(finalHistory, { event_id: otherId }),
        gameMarkets: withMatrix(ownMatrix(), mutate(finalMarkets, { event_id: otherId })),
      }),
    );
    expect(runCard()?.getAttribute("data-mlb-run-totals")).toBe("mlb:15321837:final");
    expect(pressedRuns()).toEqual([KEY_9_5]);
    render(model(finalDetail, finalHost, { gameMarkets: withMatrix(ownMatrix()) }));
    click(runChoice(KEY_10_5));
    render(model(liveDetail, liveHost, { gameMarkets: withMatrix(ownMatrix()) }));
    // Live is a new reading: its milestones (the same option keys) open with nothing chosen, never the final's 10.5.
    expect(runCard()?.getAttribute("data-mlb-run-milestones")).toBe("live");
    expect(host.querySelector("[data-soccer-chosen]")).toBeNull();
    render(model(finalDetail, finalHost, { gameMarkets: withMatrix(ownMatrix()) }));
    expect(pressedRuns()).toEqual([KEY_9_5]);
  });

  // ─── B1: the chosen line is held above the card, through a same-scope absence ───

  /** Every full-game line except 10.5 (TEST MUTATION). */
  const WITHOUT_10_5 = [2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5, 11.5, 12.5, 13.5, 14.5];

  it("B1: 10.5 survives the WHOLE matrix going away in the same scope — no card meanwhile — and returns pressed with its readout, not 9.5", () => {
    render(model(finalDetail, finalHost, { gameMarkets: withMatrix(ownMatrix()) }));
    click(runChoice(KEY_10_5));
    expect(pressedRuns()).toEqual([KEY_10_5]);
    // CONSTRUCTED same-scope passes with NO matrix: the member removed (the reduced body), then a null member.
    for (const gameMarkets of [finalMarkets, withMatrix(null)]) {
      const absent = model(finalDetail, { ...finalHost, nowMs: FINAL_NOW + 60_000 }, { gameMarkets });
      expect(view(absent).scope).toBe("mlb:15321836:final");
      expect(view(absent).runTotals).toBeNull();
      render(absent);
      // No card, placeholder or stale card: the row holds the history alone (DOM order only; no geometry claim).
      expect({ card: runCard(), items: rowItems() }).toEqual({ card: null, items: ["history"] });
      expect(runChoices()).toHaveLength(0);
      expect(host.textContent).not.toContain(MLB_RUN_TOTAL_WORDS.title);
      expect(host.textContent).not.toContain(MLB_RUN_TOTAL_WORDS.selectedUnavailable);
    }
    render(model(finalDetail, finalHost, { gameMarkets: withMatrix(ownMatrix()) }));
    expect(rowItems()).toEqual(["history", "runTotals"]);
    expect(pressedRuns()).toEqual([KEY_10_5]);
    expect(runText("[data-run-heading]")).toBe("Over 10.5 runs");
    expect(runText("[data-run-comparison]")).toBe("Final 10 runs · below this line");
    expect(runText("[data-run-source]")).toBe(sourceSays(PROP_MISS_LABEL));
    expect(runCard()?.querySelector("[data-run-marker]")?.getAttribute("data-run-marker")).toBe("10.5");
  });

  it("B1: after an absence, a matrix without the held key says Selected line unavailable (never the 9.5 default); the key's return restores 10.5", () => {
    render(model(finalDetail, finalHost, { gameMarkets: withMatrix(ownMatrix()) }));
    click(runChoice(KEY_10_5));
    render(model(finalDetail, finalHost, { gameMarkets: finalMarkets })); // CONSTRUCTED: the matrix gone, same scope
    expect(runCard()).toBeNull();
    render(model(finalDetail, finalHost, { gameMarkets: withMatrix(matrixKeeping(WITHOUT_10_5)) }));
    expect(runText("[data-run-heading]")).toBe(MLB_RUN_TOTAL_WORDS.selectedUnavailable);
    expect(runCard()?.querySelector("[data-run-selected]")?.getAttribute("data-run-selected")).toBe("unavailable");
    expect(pressedRuns()).toEqual([]);
    expect(host.querySelector("[data-run-source]")).toBeNull();
    expect(host.querySelector("[data-run-comparison]")).toBeNull();
    expect(host.querySelector("[data-run-marker]")).toBeNull();
    expect(runChoices().map((b) => b.textContent)).toEqual(LINE_TEXTS.filter((t) => t !== "10.5"));
    render(model(finalDetail, finalHost, { gameMarkets: withMatrix(ownMatrix()) }));
    expect(pressedRuns()).toEqual([KEY_10_5]);
    expect(runText("[data-run-heading]")).toBe("Over 10.5 runs");
    expect(runText("[data-run-comparison]")).toBe("Final 10 runs · below this line");
  });

  it("B1: a scope change while the card is absent opens the new scope on its default (CONSTRUCTED: another event id; then a phase change)", () => {
    render(model(finalDetail, finalHost, { gameMarkets: withMatrix(ownMatrix()) }));
    click(runChoice(KEY_10_5));
    render(model(finalDetail, finalHost, { gameMarkets: finalMarkets })); // absent, same scope
    const otherId = 15321837;
    const other = (gameMarkets: GameMarketsResponse) =>
      model(mutate(finalDetail, { id: otherId }), finalHost, { history: mutate(finalHistory, { event_id: otherId }), gameMarkets });
    render(other(mutate(finalMarkets, { event_id: otherId }))); // the new event, still without a matrix
    expect(runCard()).toBeNull();
    render(other(withMatrix(ownMatrix(), mutate(finalMarkets, { event_id: otherId }))));
    expect(runCard()?.getAttribute("data-mlb-run-totals")).toBe("mlb:15321837:final");
    expect(pressedRuns()).toEqual([KEY_9_5]);
    // Back on 15321836's final: choose 10.5, lose the matrix, pass through live (a new scope), return.
    render(model(finalDetail, finalHost, { gameMarkets: withMatrix(ownMatrix()) }));
    click(runChoice(KEY_10_5));
    render(model(finalDetail, finalHost, { gameMarkets: finalMarkets }));
    render(model(liveDetail, liveHost));
    expect(runCard()).toBeNull();
    render(model(finalDetail, finalHost, { gameMarkets: withMatrix(ownMatrix()) }));
    expect(pressedRuns()).toEqual([KEY_9_5]);
  });

  it("B1 seam (CONSTRUCTED host-held selection): one onSelect per tap, no automatic selection, and the card shows only the key it is given", () => {
    const own = view(model(finalDetail, finalHost, { gameMarkets: withMatrix(ownMatrix()) })).runTotals;
    const withdrawn = view(model(finalDetail, finalHost, { gameMarkets: withMatrix(matrixKeeping(WITHOUT_10_5)) })).runTotals;
    if (!own || !withdrawn) throw new Error("no run-total card");
    const totals = own;
    const withdrawnTotals = withdrawn;
    const onSelect = jest.fn();
    const show = (held: string | null, t = totals) =>
      act(() => root.render(<MlbRunTotalsCard totals={t} scope="mlb:15321836:final" selection={{ held, onSelect }} />));
    show(null);
    expect(pressedRuns()).toEqual([KEY_9_5]); // no choice yet: native's default
    expect(onSelect).not.toHaveBeenCalled();
    click(runChoice(KEY_10_5));
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenLastCalledWith(KEY_10_5);
    // The host has not changed its key yet, so the card does not move on its own.
    expect(pressedRuns()).toEqual([KEY_9_5]);
    show(KEY_10_5);
    expect(pressedRuns()).toEqual([KEY_10_5]);
    // A held key the lines do not carry: unavailable, and nothing is selected on the host's behalf.
    show(KEY_10_5, withdrawnTotals);
    expect(runText("[data-run-heading]")).toBe(MLB_RUN_TOTAL_WORDS.selectedUnavailable);
    expect(pressedRuns()).toEqual([]);
    show(KEY_10_5);
    expect(pressedRuns()).toEqual([KEY_10_5]);
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it("the history chart and its open disclosure survive the card arriving and leaving in the same scope; a new event resets them", () => {
    render(model(finalDetail, finalHost)); // the reduced body: no card
    expect(rowItems()).toEqual(["history"]);
    const chart = historyChart();
    const disclosure = historyDisclosure();
    expect(chart).not.toBeNull();
    expect(disclosure).not.toBeNull();
    click(disclosure!);
    expect(disclosure!.getAttribute("aria-expanded")).toBe("true");
    render(model(finalDetail, finalHost, { gameMarkets: withMatrix(ownMatrix()) })); // the card arrives
    expect(rowItems()).toEqual(["history", "runTotals"]);
    expect(historyChart()).toBe(chart);
    expect(historyDisclosure()).toBe(disclosure);
    expect(disclosure!.getAttribute("aria-expanded")).toBe("true");
    render(model(finalDetail, finalHost, { gameMarkets: finalMarkets })); // the card leaves
    expect(rowItems()).toEqual(["history"]);
    expect(historyChart()).toBe(chart);
    expect(historyDisclosure()?.getAttribute("aria-expanded")).toBe("true");
    // CONSTRUCTED: the same bodies under another id — a new scope, a new reading.
    const otherId = 15321837;
    render(
      model(mutate(finalDetail, { id: otherId }), finalHost, {
        history: mutate(finalHistory, { event_id: otherId }),
        gameMarkets: withMatrix(ownMatrix(), mutate(finalMarkets, { event_id: otherId })),
      }),
    );
    expect(historyChart()).not.toBe(chart);
    expect(historyDisclosure()?.getAttribute("aria-expanded")).toBe("false");
  });
});

// ─── S2c: this phase's run milestones in the same row ──────────────────────
//
// The joined matrix is the REAL final capture (every option graded, no pins).
// Every quote, pin and clock put on it below is CONSTRUCTED, as are the phase
// edits (`liveDetail`, `beforeDetail`), the hosts' displayed pairs and the
// state owner's noReportedResult (`liveClaimUnbacked`).

/** REAL: the retained game's own listed start. */
const START_MS = Date.parse(finalDetail.commence_time);
const MIN = 60_000;
const iso = (ms: number) => new Date(ms).toISOString();
/** The strip's thirteen milestones, 2.5 → "3+ runs" … 14.5 → "15+ runs". */
const MILESTONE_LABELS = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15].map((n) => `${n}+ runs`);
function overOfLine(m: Json, line: number): Json {
  const found = (m.questions as Json[]).filter((q) => isFullGameRuns(q) && lineOf(q) === line);
  if (found.length !== 1) throw new Error(`expected one full-game question at ${line}`);
  return (found[0].options as Json[])[0];
}
/** CONSTRUCTED: the line's Over option published as a quoted value on its own clock. */
function quoteLine(m: Json, line: number, value: number, observedAt: string): void {
  const o = overOfLine(m, line);
  o.published = { ...(o.published as Json), value, value_state: "quoted", observed_at: observedAt };
}
/** CONSTRUCTED: an admitted pregame pin (comparable baseline) on the line's Over option. */
function pinLine(m: Json, line: number, probability: number, observedAt: string): void {
  overOfLine(m, line).comparison = {
    state: "comparable",
    reason: null,
    baseline: { basis: "pregame_pin", probability, observed_at: observedAt },
    latest: null,
    delta_points: null,
  };
}
/** CONSTRUCTED live readings over the REAL matrix: pins on 9.5 (40%) and 11.5 (30%); a recorded 20% on 11.5 two minutes before the live clock. */
function liveMilestoneMatrix(): Json {
  const m = ownMatrix();
  pinLine(m, 9.5, 0.4, iso(START_MS - 30 * MIN));
  pinLine(m, 11.5, 0.3, iso(START_MS - 30 * MIN));
  quoteLine(m, 11.5, 0.2, iso(LIVE_NOW - 2 * MIN));
  return m;
}
/** TEST MUTATION: one full-game line withdrawn (every other question kept). */
function withoutLine(m: Json, line: number): Json {
  m.questions = (m.questions as Json[]).filter((q) => !(isFullGameRuns(q) && lineOf(q) === line));
  return m;
}
const msChips = () => Array.from(runCard()?.querySelectorAll<HTMLButtonElement>('[data-soccer-card="goals"] li > button[aria-pressed]') ?? []);
const msLabel = (b: HTMLButtonElement) => b.querySelector("span")?.textContent ?? null;
const msPressed = () => msChips().filter((b) => b.getAttribute("aria-pressed") === "true").map(msLabel);
const msChosen = () => runCard()?.querySelector("[data-soccer-chosen]")?.getAttribute("data-soccer-chosen") ?? null;
const msUnavailable = () => runCard()?.querySelector("[data-soccer-selection-unavailable]") ?? null;
function msChip(label: string): HTMLButtonElement {
  const found = msChips().filter((b) => msLabel(b) === label);
  if (found.length !== 1) throw new Error(`expected one milestone ${label}`);
  return found[0];
}
const readoutTitles = () => Array.from(runCard()?.querySelectorAll("[data-soccer-chosen] dt") ?? []).map((dt) => dt.textContent);
const readoutValues = () => Array.from(runCard()?.querySelectorAll("[data-soccer-chosen] dd") ?? []).map((dd) => dd.textContent);
/** Any Details the run-total card itself offers (the milestone leaf's Details are off). */
const cardDetails = () =>
  (runCard()?.querySelectorAll("[data-soccer-details-entry]").length ?? 0) +
  Array.from(runCard()?.querySelectorAll("button") ?? []).filter((b) => (b.textContent ?? "").startsWith("Details")).length;
const liveWith = (matrix: unknown, h: MlbGameHost = liveHost) => model(liveDetail, h, { gameMarkets: withMatrix(matrix) });

describe("S2c: before first pitch and during play the row draws this phase's run milestones (CONSTRUCTED phases over the REAL matrix)", () => {
  it("LIVE: the count is the DISPLAYED pair, never the raw row; the pin, the recorded in-game quote and the runs so far stay apart; no final grade leaks", () => {
    // CONSTRUCTED (#8278's shape): the event row lags at 1–0 while the page displays 3–6.
    const lagging = mutate(liveDetail, { home_score: 1, away_score: 0 });
    render(model(lagging, liveHost, { gameMarkets: withMatrix(liveMilestoneMatrix()) }));
    expect(rowItems()).toEqual(["history", "runTotals"]);
    // The headline's Runs column (away first) and the card's count read the same displayed pair.
    const cells = Array.from(host.querySelectorAll("table tbody tr")).map((r) =>
      Array.from(r.querySelectorAll("td")).map((td) => td.textContent ?? ""),
    );
    expect([cells[0][2], cells[1][2]]).toEqual(["66 runs", "33 runs"]);
    const card = runCard();
    expect([card?.getAttribute("data-mlb-run-totals"), card?.getAttribute("data-mlb-run-milestones")]).toEqual(["mlb:15321836:live", "live"]);
    expect(card?.querySelector("h4")?.textContent).toBe(MLB_RUN_TOTAL_WORDS.liveTitle);
    expect(card?.textContent).toContain(MLB_RUN_TOTAL_WORDS.milestonesEyebrow);
    expect(card?.querySelector('[data-axis-labels="actual"] [data-axis-label="actual"]')?.textContent).toBe("9 so far");
    expect(card?.querySelector('[data-mark="actual-rule"]')).not.toBeNull();
    expect(msChips().map(msLabel)).toEqual(MILESTONE_LABELS);
    // Reached lines are performance; the rest say how many more, from 9 (never the row's 1).
    expect(msChip("3+ runs").textContent).toContain("Reached so far");
    expect(msChip("9+ runs").textContent).toContain("Reached so far");
    expect(msChip("10+ runs").textContent).toContain(MLB_RUN_TOTAL_WORDS.more(1, "10+"));
    expect(msChip("12+ runs").textContent).toContain(MLB_RUN_TOTAL_WORDS.more(3, "12+"));
    // Two pins drawn as pregame marks; the one recorded in-game quote as the only current mark.
    expect(card?.querySelectorAll('[data-mark="pregame"]')).toHaveLength(2);
    expect(card?.querySelectorAll('[data-mark="current"]')).toHaveLength(1);
    expect(card?.querySelector(`[data-milestone="${KEY_11_5}"] [data-mark="current"]`)).not.toBeNull();
    // The shown pin nearest even odds opens (40% over 30%): pregame and in-game kept apart.
    expect(msPressed()).toEqual(["10+ runs"]);
    expect(msChosen()).toBe(KEY_9_5);
    expect(readoutTitles()).toEqual(["Pregame chance", "In-game chance"]);
    expect(readoutValues()).toEqual([formatProbabilityPercent(0.4), MLB_RUN_TOTAL_WORDS.inGameUnavailable]);
    click(msChip("12+ runs"));
    expect(msChosen()).toBe(KEY_11_5);
    expect(readoutTitles()).toEqual(["Pregame chance", "Recorded in-game"]);
    expect(readoutValues()).toEqual([formatProbabilityPercent(0.3), formatProbabilityPercent(0.2)]);
    click(msChip("3+ runs"));
    expect(readoutValues()).toEqual([MLB_RUN_TOTAL_WORDS.pregameUnavailable, "Reached so far"]);
    // The capture grades every line; during play none of it shows, and the final leaf is not drawn.
    expect(card?.textContent).not.toContain(PROP_HIT_LABEL);
    expect(card?.textContent).not.toContain(PROP_MISS_LABEL);
    expect(card?.querySelector("[data-run-total]")).toBeNull();
    expect(card?.querySelector("[data-run-source]")).toBeNull();
    expect(cardDetails()).toBe(0);
    // Whatever the row says, the card is the same: it never reads the row's score.
    const otherRow = model(mutate(liveDetail, { home_score: 8, away_score: 8 }), liveHost, { gameMarkets: withMatrix(liveMilestoneMatrix()) });
    expect(view(otherRow).runTotals).toEqual(view(model(lagging, liveHost, { gameMarkets: withMatrix(liveMilestoneMatrix()) })).runTotals);
  });

  it("noReportedResult is the page's own state owner's answer: an unbacked live claim withholds the recorded in-game quote; the pin, the count and the held key stay (CONSTRUCTED)", () => {
    render(liveWith(liveMilestoneMatrix(), { ...liveHost, liveClaimUnbacked: true }));
    expect(runCard()?.getAttribute("data-mlb-run-milestones")).toBe("live");
    expect(runCard()?.querySelectorAll('[data-mark="current"]')).toHaveLength(0);
    click(msChip("12+ runs"));
    expect(readoutTitles()).toEqual(["Pregame chance", "In-game chance"]);
    expect(readoutValues()).toEqual([formatProbabilityPercent(0.3), MLB_RUN_TOTAL_WORDS.inGameUnavailable]);
    expect(msChip("3+ runs").textContent).toContain("Reached so far");
    expect(runCard()?.querySelector('[data-axis-labels="actual"] [data-axis-label="actual"]')?.textContent).toBe("9 so far");
    // Non-vacuity: the same scope, backed, records the quote on the same held line.
    render(liveWith(liveMilestoneMatrix()));
    expect(runCard()?.querySelectorAll('[data-mark="current"]')).toHaveLength(1);
    expect(msChosen()).toBe(KEY_11_5);
    expect(readoutValues()).toEqual([formatProbabilityPercent(0.3), formatProbabilityPercent(0.2)]);
  });

  it("BEFORE: no count before first pitch even with a displayed 0–0; a recent quote is the pregame chance and the shown default, a pin is not; no shown chance opens nothing", () => {
    const m = ownMatrix();
    quoteLine(m, 9.5, 0.45, iso(BEFORE_NOW - 5 * MIN)); // CONSTRUCTED recent quote
    pinLine(m, 10.5, 0.5, iso(START_MS - 60 * MIN)); // CONSTRUCTED pin
    const paired: MlbGameHost = { ...beforeHost, score: { home: 0, away: 0, observedAt: null } }; // CONSTRUCTED pair
    render(model(beforeDetail, paired, { gameMarkets: withMatrix(m) }));
    const card = runCard();
    expect([card?.getAttribute("data-mlb-run-totals"), card?.getAttribute("data-mlb-run-milestones")]).toEqual(["mlb:15321836:before", "before"]);
    expect(card?.querySelector("h4")?.textContent).toBe(MLB_RUN_TOTAL_WORDS.beforeTitle);
    expect(card?.querySelector('[data-axis-labels="actual"]')).toBeNull();
    expect(card?.querySelector('[data-mark="actual-rule"]')).toBeNull();
    expect(card?.querySelectorAll('[data-mark="current"]')).toHaveLength(0);
    expect(card?.textContent).not.toMatch(/more for|Reached so far/);
    expect(card?.querySelectorAll('[data-mark="pregame"]')).toHaveLength(1);
    expect(msChip("10+ runs").textContent).toContain(formatProbabilityPercent(0.45));
    expect(msChip("11+ runs").textContent).toContain(MLB_RUN_TOTAL_WORDS.pregameUnavailable);
    expect(msPressed()).toEqual(["10+ runs"]);
    expect(msChosen()).toBe(KEY_9_5);
    expect(readoutTitles()).toEqual(["Pregame chance"]);
    expect(readoutValues()).toEqual([formatProbabilityPercent(0.45)]);
    expect(card?.textContent).not.toContain(PROP_HIT_LABEL);
    expect(card?.textContent).not.toContain(PROP_MISS_LABEL);
    expect(cardDetails()).toBe(0);
    // No shown chance (the REAL matrix alone): nothing is chosen, and nothing says unavailable.
    render(model(beforeDetail, beforeHost, { gameMarkets: withMatrix(ownMatrix()) }));
    expect(msChips().map(msLabel)).toEqual(MILESTONE_LABELS);
    expect(msPressed()).toEqual([]);
    expect(msChosen()).toBeNull();
    expect(msUnavailable()).toBeNull();
  });

  it("before and live: no card for another event's body, a wrong scope, two full-game lines or no matrix — the history stays alone; the own matrix restores it", () => {
    const refusals: Array<[string, GameMarketsResponse]> = [
      ["another event's body (TEST MUTATION: event_id 1)", mutate(withMatrix(liveMilestoneMatrix()), { event_id: 1 })],
      ["a series-scoped matrix (TEST MUTATION)", withMatrix({ ...liveMilestoneMatrix(), display_scope: "series" })],
      ["two full-game lines (TEST MUTATION)", withMatrix(matrixKeeping([9.5, 11.5]))],
      ["the reduced body, with no matrix member", finalMarkets],
    ];
    const phases = [
      ["before", beforeDetail, beforeHost],
      ["live", liveDetail, liveHost],
    ] as const;
    for (const [phase, detail, h] of phases) {
      for (const [name, gameMarkets] of refusals) {
        render(model(detail, h, { gameMarkets }));
        expect(host.querySelector(`section[data-mlb-game='${phase}']`)).not.toBeNull();
        expect({ phase, name, card: runCard(), items: rowItems() }).toEqual({ phase, name, card: null, items: ["history"] });
      }
      render(model(detail, h, { gameMarkets: withMatrix(liveMilestoneMatrix()) }));
      expect(runCard()?.getAttribute("data-mlb-run-milestones")).toBe(phase);
      expect(msChips()).toHaveLength(13);
    }
  });

  it("B1 in the live scope: the chosen milestone survives the WHOLE matrix going away and returns by its key; withdrawn or duplicated it is unavailable, never a substitute", () => {
    render(liveWith(liveMilestoneMatrix()));
    expect(msChosen()).toBe(KEY_9_5); // the shown default
    click(msChip("12+ runs"));
    expect(msChosen()).toBe(KEY_11_5);
    // CONSTRUCTED same-scope passes with NO matrix: the member removed (the reduced body), then a null member.
    for (const gameMarkets of [finalMarkets, withMatrix(null)]) {
      const absent = model(liveDetail, { ...liveHost, nowMs: LIVE_NOW + 30_000 }, { gameMarkets });
      expect(view(absent).scope).toBe("mlb:15321836:live");
      expect(view(absent).runTotals).toBeNull();
      render(absent);
      expect({ card: runCard(), items: rowItems() }).toEqual({ card: null, items: ["history"] });
      expect(host.textContent).not.toContain(MLB_RUN_TOTAL_WORDS.liveTitle);
    }
    render(liveWith(liveMilestoneMatrix()));
    expect(msChosen()).toBe(KEY_11_5); // never the 9.5 default
    expect(msPressed()).toEqual(["12+ runs"]);
    expect(readoutValues()).toEqual([formatProbabilityPercent(0.3), formatProbabilityPercent(0.2)]);
    // TEST MUTATIONS: 11.5 withdrawn; 12.5's option carrying 11.5's key (the admission drops both).
    const duplicated = liveMilestoneMatrix();
    overOfLine(duplicated, 12.5).option_key = KEY_11_5;
    for (const changed of [withoutLine(liveMilestoneMatrix(), 11.5), duplicated]) {
      render(liveWith(changed));
      expect(msUnavailable()?.textContent).toBe("Selected milestone unavailable.");
      expect(msPressed()).toEqual([]); // never the 9.5 default or a neighbour
      expect(msChosen()).toBeNull();
      expect(msChips().map(msLabel)).not.toContain("12+ runs");
      render(liveWith(liveMilestoneMatrix()));
      expect(msChosen()).toBe(KEY_11_5);
      expect(msPressed()).toEqual(["12+ runs"]);
      expect(msUnavailable()).toBeNull();
    }
  });

  it("B1: an event or phase change while the card is absent opens the new scope on its own shown default, never the held 12+ (CONSTRUCTED: another event id; then before first pitch)", () => {
    const otherId = 15321837;
    const otherLive = (gameMarkets: GameMarketsResponse) =>
      model(mutate(liveDetail, { id: otherId }), liveHost, { history: mutate(finalHistory, { event_id: otherId }), gameMarkets });
    render(liveWith(liveMilestoneMatrix()));
    click(msChip("12+ runs"));
    expect(msChosen()).toBe(KEY_11_5);
    render(model(liveDetail, liveHost, { gameMarkets: finalMarkets })); // absent, same scope
    render(otherLive(mutate(finalMarkets, { event_id: otherId }))); // the new event, still absent
    expect(runCard()).toBeNull();
    render(otherLive(withMatrix(liveMilestoneMatrix(), mutate(finalMarkets, { event_id: otherId }))));
    expect(runCard()?.getAttribute("data-mlb-run-totals")).toBe("mlb:15321837:live");
    expect(msChosen()).toBe(KEY_9_5);
    // Back on 15321836 live (a new scope again): choose 12+, lose the matrix, pass through before first pitch, return.
    render(liveWith(liveMilestoneMatrix()));
    expect(msChosen()).toBe(KEY_9_5);
    click(msChip("12+ runs"));
    render(model(liveDetail, liveHost, { gameMarkets: finalMarkets }));
    render(model(beforeDetail, beforeHost)); // a new phase, still no matrix
    expect(host.querySelector("section[data-mlb-game='before']")).not.toBeNull();
    expect(runCard()).toBeNull();
    render(liveWith(liveMilestoneMatrix()));
    expect(msChosen()).toBe(KEY_9_5);
    expect(msPressed()).toEqual(["10+ runs"]);
  });

  it("the history chart, its open disclosure and an open original's Details survive the live milestones arriving and leaving in the same scope", () => {
    render(model(liveDetail, liveHost)); // the reduced body: no card
    expect(rowItems()).toEqual(["history"]);
    const chart = historyChart();
    const disclosure = historyDisclosure();
    expect(chart).not.toBeNull();
    expect(disclosure).not.toBeNull();
    click(disclosure!);
    expect(disclosure!.getAttribute("aria-expanded")).toBe("true");
    click(entryButton());
    const original = detailsButtons()[0];
    click(original);
    expect(openDetails()).toHaveLength(1);
    expect(openDetails()[0]).toBe(original);
    render(liveWith(liveMilestoneMatrix())); // the milestones arrive
    expect(rowItems()).toEqual(["history", "runTotals"]);
    expect(runCard()?.getAttribute("data-mlb-run-milestones")).toBe("live");
    expect(historyChart()).toBe(chart);
    expect(historyDisclosure()).toBe(disclosure);
    expect(disclosure!.getAttribute("aria-expanded")).toBe("true");
    expect(openDetails()).toHaveLength(1);
    expect(openDetails()[0]).toBe(original);
    expect(cardDetails()).toBe(0); // the card adds no Details; the original's stay the only ones
    render(model(liveDetail, liveHost, { gameMarkets: finalMarkets })); // they leave
    expect(rowItems()).toEqual(["history"]);
    expect(historyChart()).toBe(chart);
    expect(historyDisclosure()).toBe(disclosure);
    expect(disclosure!.getAttribute("aria-expanded")).toBe("true");
    expect(openDetails()).toHaveLength(1);
    expect(openDetails()[0]).toBe(original);
    expect(document.getElementById(original.getAttribute("aria-controls") ?? "")?.hidden).toBe(false);
  });
});

// ─── Refusals, quiet behaviour and design tokens ───────────────────────────

describe("refusals, no timers, design tokens", () => {
  it("a refused row prints its authority's word and the absence words; a non-MLB row renders nothing", () => {
    render(model(mutate(finalDetail, { venue_closed_no_winner: true }), finalHost)); // TEST MUTATION
    const refused = host.querySelector("section[data-mlb-game='refused']");
    expect(refused?.getAttribute("aria-label")).toBe(MLB_WORDS.refusedLabel);
    expect(refused?.textContent).toContain("Ended · no winner");
    render(model(mutate(finalDetail, { sport: "icehockey_nhl" }), finalHost)); // TEST MUTATION
    expect(host.innerHTML).toBe("");
  });

  it("schedules nothing: no interval runs while the section is shown", () => {
    const interval = jest.spyOn(window, "setInterval");
    render(model(liveDetail, liveHost));
    render(model(liveDetail, { ...liveHost, nowMs: LIVE_NOW + 30_000 }));
    expect(interval).not.toHaveBeenCalled();
  });

  it("the new source uses design tokens only: no hex colour, no dark: class, no `|| 0` fallback", () => {
    const root = path.resolve(__dirname, "../..");
    for (const file of ["components/event/eventpage10868/MlbGamePage.tsx", "lib/eventPage10868/mlbGame.ts"]) {
      // Code only: comments cite issue numbers ("#8278"), which are not colours.
      const src = fs
        .readFileSync(path.join(root, file), "utf8")
        .replace(/\/\*[\s\S]*?\*\//g, "")
        .replace(/^\s*\/\/.*$/gm, "");
      expect({ file, hex: src.match(/#[0-9a-fA-F]{3,8}\b/g) }).toEqual({ file, hex: null });
      expect({ file, dark: /\bdark:/.test(src) }).toEqual({ file, dark: false });
      expect({ file, orZero: /\|\|\s*0\b/.test(src) }).toEqual({ file, orZero: false });
    }
  });
});
