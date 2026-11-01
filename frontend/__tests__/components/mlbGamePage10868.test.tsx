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
 */
import React, { act } from "react";
import fs from "node:fs";
import path from "node:path";
import { createRoot, type Root } from "react-dom/client";
import fixtures from "../lib/mlbGame10868.fixtures.json";
import type { EventDetailResponse, EventHistoryResponse } from "@/lib/types";
import type { GameMarketsResponse } from "@/lib/api";
import { PROP_HIT_LABEL } from "@/lib/propGrade";
import {
  MLB_ORIGINALS_WORDS,
  MLB_WORDS,
  buildMlbGame,
  type MlbGameHost,
  type MlbGameModel,
  type MlbGameView,
} from "@/lib/eventPage10868/mlbGame";
import MlbGamePage from "@/components/event/eventpage10868/MlbGamePage";
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
  /** CONSTRUCTED: native `beforeEdits` over the real final — one minute before first pitch. */
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
