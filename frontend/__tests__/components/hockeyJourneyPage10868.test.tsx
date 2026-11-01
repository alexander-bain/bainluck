/** @jest-environment jsdom */
/**
 * #10868 — the web hockey journey screen renders its view model and its
 * controls work: About is a real disclosure, the story stream moves only on
 * Previous / Next (no timer), All props opens, and the history draws each run
 * as its own path. PREPARED, NOT RUN (quiet-CPU hold; the lead runs it under a
 * grant). Bodies: the verbatim subsets documented in
 * `__tests__/lib/hockeyJourney10868.test.ts` (15169793, Wild 4–1 Bruins, final;
 * 15338496, Devils at Golden Knights). CONSTRUCTED, and named where used: a
 * missing history response; a live read of 15338496 with one row's
 * `observed_at` changed; the final markets without one player's points rows;
 * a before-phase card carrying a later count, result and in-game reading as a
 * negative control; one All props original edited so its label repeats its
 * title and it names no venue; and forced element widths for the matrix's fit steps
 * (jsdom lays nothing out, so these prove the stepping logic, never real fit —
 * real fit is proved only by browser views at 375 / 393 px, normal and 200%
 * text, under grant I).
 */
import React from "react";
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import fixtures from "../lib/hockeyJourney10868.fixtures.json";
import type { EventDetailResponse, EventHistoryResponse } from "@/lib/types";
import type { GameMarketsResponse } from "@/lib/api";
import {
  buildHockeyJourney,
  hockeyJourneyContribution,
  hockeyJourneyHeadline,
  hockeyJourneyOriginals,
  NO_HELD_CHOICE,
  type HockeyJourneyContribution,
} from "@/lib/eventPage10868/hockeyJourney";
import HockeyJourneyPage from "@/components/event/eventpage10868/HockeyJourneyPage";
import HockeyJourneyAllProps from "@/components/event/eventpage10868/HockeyJourneyAllProps";
import HockeyJourneyContributionCard from "@/components/event/eventpage10868/HockeyJourneyContributionCard";
import HockeyJourneyMatrix, {
  BOTH_TEAMS_LABEL,
  matrixArrangements,
  matrixSharedAbsences,
} from "@/components/event/eventpage10868/HockeyJourneyMatrix";
import HockeyJourneyHistoryChart, {
  axisLabelSubset,
  estimateLabelWidth,
  guideLabelPlacement,
} from "@/components/event/eventpage10868/HockeyJourneyHistoryChart";
// FQ2: the shared chart's football caller, through its own history builder (read-only).
import footballFixtures from "../lib/footballJourney10868.fixtures.json";
// M1: the shared All props rows on the REAL MLB final subset (provenance in `__tests__/lib/mlbGame10868.test.ts`).
import mlbFixtures from "../lib/mlbGame10868.fixtures.json";
import { footballJourneyHistory } from "@/lib/eventPage10868/footballJourney";
import type { HockeyJourneyHistory } from "@/lib/eventPage10868/hockeyJourneyTypes";

const journey = buildHockeyJourney({
  event: fixtures.finalDetail as unknown as EventDetailResponse,
  history: fixtures.finalHistory as unknown as EventHistoryResponse,
  gameMarkets: fixtures.finalMarkets as unknown as GameMarketsResponse,
  host: { nowMs: Date.parse("2026-10-11T04:56:41Z"), hero: null, probabilityObservedAt: null },
});

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

function button(label: string): HTMLButtonElement {
  const found = Array.from(host.querySelectorAll("button")).find((b) => (b.textContent ?? "").startsWith(label));
  if (!found) throw new Error(`no button "${label}"`);
  return found;
}

function click(el: Element) {
  act(() => {
    el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
}

it("prints the final matrix's values and verdicts as text", () => {
  act(() => root.render(<HockeyJourneyPage journey={journey} />));
  const table = host.querySelector("table");
  expect(table?.textContent).toContain("66%");
  expect(table?.textContent).toContain("34%");
  expect(table?.textContent).toContain("Won");
  expect(table?.textContent).toContain("Lost");
  // Neither team has a pregame forecast: said once for both, not in each row.
  expect(table?.textContent).not.toContain("No pregame forecast");
  expect(host.querySelector("[data-matrix-shared-absences]")?.textContent).toBe(
    `${BOTH_TEAMS_LABEL}Pregame forecast:No pregame forecast`,
  );
  expect(host.querySelector("h2")?.textContent).toBe("Final: Minnesota Wild 4–1 Boston Bruins");
});

it("opens and closes About with a real button", () => {
  act(() => root.render(<HockeyJourneyPage journey={journey} />));
  const about = button("About these sources");
  const region = document.getElementById(about.getAttribute("aria-controls") ?? "");
  expect(about.getAttribute("aria-expanded")).toBe("false");
  expect(region?.hidden).toBe(true);
  click(about);
  expect(about.getAttribute("aria-expanded")).toBe("true");
  expect(region?.hidden).toBe(false);
  expect(region?.textContent).toContain("Pregame chance: Pre-match");
  click(about);
  expect(region?.hidden).toBe(true);
});

it("moves between stories only when the reader asks, and runs no interval", () => {
  const interval = jest.spyOn(window, "setInterval");
  act(() => root.render(<HockeyJourneyPage journey={journey} />));
  const storyTitle = () => host.querySelector("article h4")?.textContent;
  expect(storyTitle()).toBe("Points in context");
  click(button("Next"));
  expect(storyTitle()).toBe("Who creates the goals?");
  click(button("Previous"));
  expect(storyTitle()).toBe("Points in context");
  expect(interval).not.toHaveBeenCalled();
});

it("draws each multi-row run of each team as its own path, and opens All props", () => {
  act(() => root.render(<HockeyJourneyPage journey={journey} />));
  // Six home runs, one of them a single row (a mark, not a path); the away side mirrors them.
  expect(host.querySelectorAll('svg[role="img"] path')).toHaveLength(10);
  const entry = button("All 23 original outcomes");
  const list = document.getElementById(entry.getAttribute("aria-controls") ?? "");
  expect(list?.hidden).toBe(true);
  click(entry);
  expect(list?.hidden).toBe(false);
  expect(list?.textContent).toContain("Kirill Kaprizov 2+ points");
});

it("with no history response shows only the chart as unavailable, with no history control", () => {
  const missing = buildHockeyJourney({
    event: fixtures.finalDetail as unknown as EventDetailResponse,
    history: null, // CONSTRUCTED: no history response
    gameMarkets: fixtures.finalMarkets as unknown as GameMarketsResponse,
    host: { nowMs: Date.parse("2026-10-11T04:56:41Z"), hero: null, probabilityObservedAt: null },
  });
  act(() => root.render(<HockeyJourneyPage journey={missing} />));
  expect(host.textContent).toContain("History unavailable");
  expect(host.textContent).not.toContain("No recorded history");
  expect(host.querySelector('svg[role="img"]')).toBeNull();
  const labels = Array.from(host.querySelectorAll("button")).map((b) => b.textContent ?? "");
  expect(labels.some((l) => l.startsWith("History & source details"))).toBe(false);
  expect(labels.some((l) => /retry|try again/i.test(l))).toBe(false);
  // The rest of the page is still there.
  expect(host.querySelector("table")?.textContent).toContain("66%");
  expect(host.querySelector("article h4")?.textContent).toBe("Points in context");
  expect(labels.some((l) => l.startsWith("All 23 original outcomes"))).toBe(true);
});

it("during play a stale original shows no figure on its row; Details show the historical quote", () => {
  const live = { ...(fixtures.pregameDetail as unknown as EventDetailResponse), status: "live" } as EventDetailResponse; // CONSTRUCTED: status only
  const base = fixtures.pregameMarkets as unknown as GameMarketsResponse;
  const markets = {
    ...base,
    player_props: base.player_props.map((row) =>
      row.contributor_outcome_ids?.[0] === 256284771 ? { ...row, observed_at: "2026-10-30T22:05:00Z" } : row,
    ),
  } as GameMarketsResponse; // CONSTRUCTED: one row's observed_at
  const originals = hockeyJourneyOriginals(live, markets, Date.parse("2026-10-30T22:45:00Z"));
  act(() => root.render(<HockeyJourneyAllProps originals={originals} entryLabel="All 18 original outcomes" />));
  const row = Array.from(host.querySelectorAll("li")).find((li) => li.textContent?.includes("Jack Eichel 1+ points"))!;
  const face = row.querySelector("div")!;
  expect(face.textContent).toContain("No recent probability update");
  expect(face.textContent).not.toContain("%");
  const details = Array.from(row.querySelectorAll("button")).find((b) => (b.textContent ?? "").startsWith("Details"))!;
  const region = document.getElementById(details.getAttribute("aria-controls") ?? "");
  expect(region?.hidden).toBe(true);
  click(details);
  expect(region?.hidden).toBe(false);
  expect(region?.textContent).toContain("Last recorded probability (historical)");
  expect(region?.textContent).toContain("69%, recorded ");
  expect(region?.textContent).toContain(" · Kalshi");
});

const FINAL_NOW = Date.parse("2026-10-11T04:56:41Z");
const finalEvent = fixtures.finalDetail as unknown as EventDetailResponse;
const finalHistory = fixtures.finalHistory as unknown as EventHistoryResponse;
const finalMarkets = fixtures.finalMarkets as unknown as GameMarketsResponse;
const finalJourney = (markets: GameMarketsResponse, nowMs = FINAL_NOW) =>
  buildHockeyJourney({
    event: finalEvent,
    history: finalHistory,
    gameMarkets: markets,
    host: { nowMs, hero: null, probabilityObservedAt: null },
  });

function choose(select: HTMLSelectElement, value: string) {
  act(() => {
    select.value = value;
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });
}

it("keeps the reader's held player through a refresh, and says so when that player is no longer served", () => {
  act(() => root.render(<HockeyJourneyPage journey={finalJourney(finalMarkets)} />));
  const card = () => host.querySelector("article")!;
  const select = () => card().querySelector("select") as HTMLSelectElement;
  const group = (name: string) => card().querySelector(`[role="group"][aria-label="${name} milestones"]`);
  // Before any choice: the first player.
  expect(group("Kirill Kaprizov")).not.toBeNull();
  choose(select(), "player:quinn hughes");
  const twoPlus = Array.from(group("Quinn Hughes")!.querySelectorAll("button")).find((b) => b.textContent?.includes("2+"))!;
  click(twoPlus);
  expect(twoPlus.getAttribute("aria-pressed")).toBe("true");

  // An unrelated refresh (same data, a minute later) rewrites nothing.
  act(() => root.render(<HockeyJourneyPage journey={finalJourney(finalMarkets, FINAL_NOW + 60_000)} />));
  const pressed = Array.from(group("Quinn Hughes")!.querySelectorAll('button[aria-pressed="true"]'));
  expect(pressed.map((b) => b.textContent?.includes("2+"))).toEqual([true]);

  // CONSTRUCTED: the same markets without Quinn Hughes's points rows; nothing else changes.
  const withoutHughes = {
    ...finalMarkets,
    player_props: finalMarkets.player_props.filter(
      (row) => !(row.market_name.endsWith(": Points") && row.outcome_name.startsWith("Quinn Hughes:")),
    ),
  } as GameMarketsResponse;
  act(() => root.render(<HockeyJourneyPage journey={finalJourney(withoutHughes)} />));
  expect(card().textContent).toContain("Selected player unavailable.");
  expect(group("Kirill Kaprizov")).toBeNull();
  expect(group("Max Shabanov")).toBeNull();
  // The chooser is still reachable, and shows no one else as chosen.
  expect(select()).not.toBeNull();
  expect(select().value).toBe("");

  // Only a new explicit choice substitutes.
  choose(select(), "player:kirill kaprizov");
  expect(card().textContent).not.toContain("Selected player unavailable.");
  expect(group("Kirill Kaprizov")).not.toBeNull();
});

it("before play shows no count, progress, in-game or result block — even when the input carries them", () => {
  const pregameDetail = fixtures.pregameDetail as unknown as EventDetailResponse;
  const pregameMarkets = fixtures.pregameMarkets as unknown as GameMarketsResponse;
  const built = hockeyJourneyContribution("points", pregameDetail, pregameMarkets, Date.parse("2026-10-30T20:13:55Z"))!;
  expect(built.phase).toBe("before");
  // CONSTRUCTED negative control: a later count, progress, in-game reading and result on a before-phase card.
  const card: HockeyJourneyContribution = {
    ...built,
    players: built.players.map((p, i) =>
      i !== 0
        ? p
        : {
            ...p,
            actual: { kind: "count", count: "7", unit: "points so far", breakdown: "3 goals + 4 assists", detail: "box" } as const,
            milestones: p.milestones.map((m) => ({
              ...m,
              current: { kind: "withheld", words: "No update since goal" } as const,
              progress: { status: "1 more for 2+", fraction: 0.5 },
              result: { kind: "missed", words: "Missed" } as const,
            })),
          },
    ),
  };
  act(() => root.render(<HockeyJourneyContributionCard card={card} held={NO_HELD_CHOICE} onHold={() => {}} />));
  const text = host.textContent ?? "";
  expect(text).toContain("69%");
  for (const banned of ["Count unavailable", "Count so far", "Final count", "points so far", "3 goals + 4 assists",
    "No update since goal", "1 more for 2+", "Missed", "MISS"]) {
    expect(text).not.toContain(banned);
  }
});

it("prints the matrix as aligned columns by default and leaves column sources to About", () => {
  act(() => root.render(<HockeyJourneyPage journey={journey} />));
  const matrix = host.querySelector("[data-hockey-matrix]")!;
  expect(matrix.querySelector("[data-arrangement]")?.getAttribute("data-arrangement")).toBe("grid");
  expect(matrix.querySelector("table")).not.toBeNull();
  expect(matrix.textContent).not.toContain("score observed");
  expect(matrix.textContent).not.toContain("Pre-match");
  const about = button("About these sources");
  click(about);
  const region = document.getElementById(about.getAttribute("aria-controls") ?? "");
  expect(region?.textContent).toContain("Final goals: ESPN · score observed");
  expect(region?.textContent).toContain("Pregame chance: Pre-match");
  // The game state and the result words stay in the headline.
  expect(host.querySelector("header")?.textContent).toContain("Final");
  expect(matrix.textContent).toContain("Won");
});

it("steps to short names, then to labelled pairs, only when the wider arrangement does not fit", () => {
  expect(matrixArrangements(true)).toEqual(["pairs"]);
  expect(matrixArrangements(false)).toEqual(["grid", "shortGrid", "pairs"]);
  const proto = HTMLElement.prototype as unknown as Record<string, unknown>;
  const overflowing = new Set<string>();
  Object.defineProperty(proto, "clientWidth", { configurable: true, get: () => 300 });
  Object.defineProperty(proto, "scrollWidth", {
    configurable: true,
    get(this: HTMLElement) {
      return overflowing.has(this.dataset?.arrangement ?? "") ? 1000 : 300;
    },
  });
  try {
    const { headline } = journey;
    // Only the full-name grid overflows: short names if the owner has any, else pairs.
    overflowing.add("grid");
    act(() => root.render(<HockeyJourneyMatrix key="a" headline={headline} inlineProvenance={false} />));
    const expected = headline.home.short || headline.away.short ? "shortGrid" : "pairs";
    expect(host.querySelector("[data-arrangement]")?.getAttribute("data-arrangement")).toBe(expected);
    if (expected === "shortGrid") {
      const rowHeads = Array.from(host.querySelectorAll('th[scope="row"]')).map((th) => th.textContent ?? "");
      // The short name shows; the full name is still there for a screen reader.
      expect(rowHeads[0]).toContain(headline.home.name);
    }
    // Neither grid fits: one labelled block per team, pairs kept together.
    overflowing.add("shortGrid");
    act(() => root.render(<HockeyJourneyMatrix key="b" headline={headline} inlineProvenance={false} />));
    expect(host.querySelector("[data-arrangement]")?.getAttribute("data-arrangement")).toBe("pairs");
    expect(host.querySelector("table")).toBeNull();
    const blocks = Array.from(host.querySelectorAll('[data-arrangement] [role="group"]'));
    expect(blocks.map((b) => b.getAttribute("aria-label"))).toEqual([headline.home.name, headline.away.name]);
    // The pregame forecast both teams lack is stated once, below the blocks, not in each.
    expect(blocks[0].querySelectorAll("dl")).toHaveLength(2);
    expect(Array.from(blocks[0].querySelectorAll("dt")).map((dt) => dt.textContent)).toEqual([
      "Pregame chance",
      "Final goals",
    ]);
    expect(blocks[0].textContent).toContain("66%");
    expect(host.querySelectorAll("[data-matrix-shared-absences]")).toHaveLength(1);
  } finally {
    delete proto.clientWidth;
    delete proto.scrollWidth;
  }
});

/**
 * Forced layout for the same-component reflow cases: the matrix frame is 300 px
 * wide, and a GRID with `overflowAt` or more header cells (the team cell plus
 * its metric columns) is 1000 px wide — it overflows — while a narrower grid
 * fits. Every other element reports 0. jsdom lays nothing out, so this proves
 * the re-measure, not real fit.
 */
function withForcedMatrixLayout(overflowAt: number, run: () => void) {
  const proto = HTMLElement.prototype as unknown as Record<string, unknown>;
  Object.defineProperty(proto, "clientWidth", { configurable: true, get: () => 300 });
  Object.defineProperty(proto, "scrollWidth", {
    configurable: true,
    get(this: HTMLElement) {
      if (this.dataset?.arrangement === undefined) return 0;
      return this.querySelectorAll("thead th").length >= overflowAt ? 1000 : 300;
    },
  });
  try {
    run();
  } finally {
    delete proto.clientWidth;
    delete proto.scrollWidth;
  }
}

const arrangementNow = () => host.querySelector("[data-arrangement]")?.getAttribute("data-arrangement");

/**
 * CONSTRUCTED host: the hero pair the lab's production resolver printed for the
 * retained 15338496 bodies (51% / 49%), with a price clock. jsdom has no
 * resolver; the null-host cases above show every chance absent instead.
 */
const LAB_HERO = { homeProb: 0.51, awayProb: 0.49, homePct: 51, awayPct: 49, probSourceLabel: null };
const heroHost = (nowMs: number, probabilityObservedAt: string) => ({ nowMs, hero: LAB_HERO, probabilityObservedAt });

it("re-fits the SAME matrix when its content changes: before fits, live overflows to pairs, a narrower final climbs back", () => {
  const history = fixtures.finalHistory as unknown as EventHistoryResponse;
  // CONSTRUCTED lifecycle of 15169793 (status, scores, score clock and ESPN period/clock edited), with
  // the constructed hero pair before and during play so each phase has a chance to draw:
  const before = hockeyJourneyHeadline(
    { ...finalEvent, status: "scheduled", home_score: null, away_score: null } as unknown as EventDetailResponse,
    history,
    heroHost(Date.parse("2026-10-03T23:00:00Z"), "2026-10-03T22:59:00Z"),
  );
  const live = hockeyJourneyHeadline(
    {
      ...finalEvent,
      status: "live",
      home_score: 2,
      away_score: 1,
      score_observed_at: "2026-10-04T01:45:25Z",
      espn: { ...finalEvent.espn, period: "2nd Period", game_clock: "4:09" },
    } as EventDetailResponse,
    history,
    heroHost(Date.parse("2026-10-04T01:46:00Z"), "2026-10-04T01:45:50Z"),
  );
  const final = hockeyJourneyHeadline(finalEvent, history, { nowMs: FINAL_NOW, hero: null, probabilityObservedAt: null });
  // Grid columns once the forecasts neither team has are stated below it: 1, 3, 2.
  const drawn = (h: typeof before) => h.matrix.columns.length - matrixSharedAbsences(h.matrix).length;
  expect([drawn(before), drawn(live), drawn(final)]).toEqual([1, 3, 2]);

  withForcedMatrixLayout(4, () => {
    // One element type, no key, no resize event: only the headline prop changes.
    act(() => root.render(<HockeyJourneyMatrix headline={before} inlineProvenance={false} />));
    expect(arrangementNow()).toBe("grid");
    const frame = host.querySelector("[data-arrangement]");

    act(() => root.render(<HockeyJourneyMatrix headline={live} inlineProvenance={false} />));
    expect(host.querySelector("[data-arrangement]")).toBe(frame); // same element: not remounted
    expect(arrangementNow()).toBe("pairs");
    expect(host.querySelector("table")).toBeNull();
    // The current chance still leads in the fallback.
    expect(live.matrix.lead).toBe(1);

    act(() => root.render(<HockeyJourneyMatrix headline={final} inlineProvenance={false} />));
    expect(host.querySelector("[data-arrangement]")).toBe(frame);
    expect(arrangementNow()).toBe("grid");
    expect(host.querySelector("table")?.textContent).toContain("Won");
  });
});

it("reflows the page's matrix from before to live without remounting or losing the held player", () => {
  const pregameDetail = fixtures.pregameDetail as unknown as EventDetailResponse;
  const build = (event: EventDetailResponse, nowMs: number, observedAt: string) =>
    buildHockeyJourney({
      event,
      history: fixtures.pregameHistory as unknown as EventHistoryResponse,
      gameMarkets: fixtures.pregameMarkets as unknown as GameMarketsResponse,
      host: heroHost(nowMs, observedAt),
    });
  // Before: one chance column (two header cells). Live with a score: chance + goals (three) — overflows.
  withForcedMatrixLayout(3, () => {
    act(() => root.render(<HockeyJourneyPage journey={build(pregameDetail, Date.parse("2026-10-30T20:13:55Z"), "2026-10-30T20:13:00Z")} />));
    expect(arrangementNow()).toBe("grid");
    const select = () => host.querySelector("article select") as HTMLSelectElement;
    choose(select(), "player:jack hughes");
    expect(host.querySelector('[aria-label="Jack Hughes milestones"]')).not.toBeNull();

    // CONSTRUCTED: the same game read live at 1–0 (status, scores, score clock); same page element, no key change.
    const live = {
      ...pregameDetail,
      status: "live",
      home_score: 1,
      away_score: 0,
      score_observed_at: "2026-10-30T22:29:30Z",
    } as EventDetailResponse;
    act(() => root.render(<HockeyJourneyPage journey={build(live, Date.parse("2026-10-30T22:30:00Z"), "2026-10-30T20:13:55Z")} />));
    expect(arrangementNow()).toBe("pairs");
    expect(select().value).toBe("player:jack hughes");
    expect(host.querySelector('[aria-label="Jack Hughes milestones"]')).not.toBeNull();
    expect(host.textContent).not.toContain("Selected player unavailable.");
  });
});

// ─── Channels neither team has, stated once (Design P1, 2026-10-31) ──────────

describe("a column absent for both teams in the same words is stated once, not in every team's row", () => {
  const pregameDetail = fixtures.pregameDetail as unknown as EventDetailResponse;
  const pregameHistory = fixtures.pregameHistory as unknown as EventHistoryResponse;
  const LIVE_NOW = Date.parse("2026-10-30T22:30:00Z");
  // CONSTRUCTED: the lab's live-constructed case — retained 15338496 bodies, status 'live' only, at 22:30Z.
  const liveStatusOnly = { ...pregameDetail, status: "live" } as EventDetailResponse;
  const sharedLines = () =>
    Array.from(host.querySelectorAll("[data-matrix-shared-absences] dl > div")).map((d) => d.textContent);
  const headerCells = () => Array.from(host.querySelectorAll("thead th")).map((th) => th.textContent);

  it("degraded live read (the lab's 375 px case): one chance column in the grid, the other three said once", () => {
    const headline = hockeyJourneyHeadline(liveStatusOnly, pregameHistory, heroHost(LIVE_NOW, "2026-10-30T20:13:55Z"));
    act(() => root.render(<HockeyJourneyMatrix headline={headline} inlineProvenance={false} />));
    expect(arrangementNow()).toBe("grid");
    expect(headerCells()).toEqual(["Team", "Last recorded chance"]);
    const rows = Array.from(host.querySelectorAll("tbody tr"));
    expect(rows.map((r) => r.querySelector("td span[aria-hidden]")?.textContent)).toEqual(["51%", "49%"]);
    // The lead stays the largest figure.
    expect(rows[0].querySelector("td span[aria-hidden]")?.className).toContain("text-3xl");
    // Each missing channel keeps its own title and words, once, in column order.
    expect(sharedLines()).toEqual([
      "Pregame chance:No recorded chance",
      "Goals:Score unavailable",
      "Projected final:No in-game forecast",
    ]);
    const group = host.querySelector("[data-matrix-shared-absences]")!;
    expect(group.getAttribute("role")).toBe("group");
    expect(document.getElementById(group.getAttribute("aria-labelledby") ?? "")?.textContent).toBe(BOTH_TEAMS_LABEL);
    const text = host.querySelector("[data-hockey-matrix]")?.textContent ?? "";
    for (const words of ["No recorded chance", "Score unavailable", "No in-game forecast"]) {
      expect(text.split(words)).toHaveLength(2);
    }
  });

  it("the same read at an accessibility size: team blocks hold only the chance; the shared lines follow once", () => {
    withRootFont(32);
    const headline = hockeyJourneyHeadline(liveStatusOnly, pregameHistory, heroHost(LIVE_NOW, "2026-10-30T20:13:55Z"));
    act(() => root.render(<HockeyJourneyMatrix headline={headline} inlineProvenance={false} />));
    expect(arrangementNow()).toBe("pairs");
    const blocks = Array.from(host.querySelectorAll('[data-arrangement] [role="group"]'));
    expect(blocks.map((b) => b.getAttribute("aria-label"))).toEqual([headline.home.name, headline.away.name]);
    for (const block of blocks) {
      expect(Array.from(block.querySelectorAll("dt")).map((dt) => dt.textContent)).toEqual(["Last recorded chance"]);
      expect(block.textContent).not.toContain("No recorded chance");
    }
    expect(host.querySelectorAll("[data-matrix-shared-absences]")).toHaveLength(1);
    expect(sharedLines()).toHaveLength(3);
  });

  it("unavailable (no chance, no score, no forecast for either team): no grid, every column said once", () => {
    const headline = hockeyJourneyHeadline(liveStatusOnly, pregameHistory, { nowMs: LIVE_NOW, hero: null, probabilityObservedAt: null });
    act(() => root.render(<HockeyJourneyMatrix headline={headline} inlineProvenance={false} />));
    expect(host.querySelector("table")).toBeNull();
    expect((host.querySelector("[data-arrangement]") as HTMLElement).hidden).toBe(true);
    expect(sharedLines()).toEqual([
      "Pregame chance:No recorded chance",
      "Last recorded chance:No recorded chance",
      "Goals:Score unavailable",
      "Projected final:No in-game forecast",
    ]);
  });

  it("complete live read: every column with a value stays in the grid; only the forecast neither team has moves", () => {
    const live = hockeyJourneyHeadline(
      {
        ...finalEvent,
        status: "live",
        home_score: 2,
        away_score: 1,
        score_observed_at: "2026-10-04T01:45:25Z",
        espn: { ...finalEvent.espn, period: "2nd Period", game_clock: "4:09" },
      } as EventDetailResponse, // CONSTRUCTED: the refit test's live edit of 15169793
      finalHistory,
      heroHost(Date.parse("2026-10-04T01:46:00Z"), "2026-10-04T01:45:50Z"),
    );
    act(() => root.render(<HockeyJourneyMatrix headline={live} inlineProvenance={false} />));
    expect(headerCells()).toEqual(["Team", "Pregame chance", "Current chance", "Goals"]);
    expect(sharedLines()).toEqual(["Projected final:No in-game forecast"]);
  });

  it("a column one team has (mixed), or absent in different words, stays in the grid with both slots", () => {
    const base = hockeyJourneyHeadline(liveStatusOnly, pregameHistory, heroHost(LIVE_NOW, "2026-10-30T20:13:55Z"));
    // CONSTRUCTED slots on the real live headline: home has a goals count, away does not; the
    // pregame-chance absences are worded differently per team.
    const [home, away] = base.matrix.rows;
    const mixed = {
      ...base,
      matrix: {
        ...base.matrix,
        rows: [
          { ...home, values: home.values.map((v, i) => (i === 2 ? { kind: "value", text: "1", spoken: "1 goal" } : v)) },
          { ...away, values: away.values.map((v, i) => (i === 0 ? { kind: "absent", text: "Not offered" } : v)) },
        ],
      },
    } as typeof base;
    expect(matrixSharedAbsences(mixed.matrix)).toEqual([3]);
    act(() => root.render(<HockeyJourneyMatrix headline={mixed} inlineProvenance={false} />));
    expect(headerCells()).toEqual(["Team", "Pregame chance", "Last recorded chance", "Goals"]);
    const rows = Array.from(host.querySelectorAll("tbody tr")).map((r) => Array.from(r.querySelectorAll("td")).map((td) => td.textContent));
    expect(rows[0][0]).toBe("No recorded chance");
    expect(rows[1][0]).toBe("Not offered");
    expect(rows[0][2]).toContain("1");
    expect(rows[1][2]).toBe("Score unavailable");
    expect(sharedLines()).toEqual(["Projected final:No in-game forecast"]);
  });
});

// ─── Browser-lab regressions (2026-10-30, 200% root font on phones) ──────────

/** CONSTRUCTED reader setting: the root font at `px` (the lab's 200% is 32 px); every other element 16 px. */
function withRootFont(px: number) {
  jest.spyOn(window, "getComputedStyle").mockImplementation(((el: Element) =>
    ({ fontSize: el === document.documentElement ? `${px}px` : "16px" }) as unknown as CSSStyleDeclaration) as typeof window.getComputedStyle);
}

const pregamePointsCard = () =>
  hockeyJourneyContribution(
    "points",
    fixtures.pregameDetail as unknown as EventDetailResponse,
    fixtures.pregameMarkets as unknown as GameMarketsResponse,
    Date.parse("2026-10-30T20:13:55Z"),
  )!;

it("the player chooser can never be wider than its container", () => {
  act(() => root.render(<HockeyJourneyContributionCard card={pregamePointsCard()} held={NO_HELD_CHOICE} onHold={() => {}} />));
  const select = host.querySelector("select")!;
  for (const cls of ["w-full", "min-w-0", "max-w-full", "min-h-11"]) expect(select.classList.contains(cls)).toBe(true);
  // Label above, not a shrink-proof flex item beside it.
  expect(select.parentElement?.classList.contains("flex-col")).toBe(true);
  expect(select.parentElement?.classList.contains("flex-wrap")).toBe(false);
  // Every option keeps its whole "name · team" text for the open list.
  expect(Array.from(select.options).map((o) => o.textContent)).toEqual(
    pregamePointsCard().players.map((p) => (p.team ? `${p.name} · ${p.team}` : p.name)),
  );
});

it("points columns give way to stacked rows at an accessibility text size — every milestone kept, nothing sideways", () => {
  const card = pregamePointsCard();
  act(() => root.render(<HockeyJourneyContributionCard card={card} held={NO_HELD_CHOICE} onHold={() => {}} />));
  expect(host.querySelector("[data-milestone-form]")?.getAttribute("data-milestone-form")).toBe("columns");
  act(() => root.unmount());

  withRootFont(32);
  root = createRoot(host);
  const onHold = jest.fn();
  act(() => root.render(<HockeyJourneyContributionCard card={card} held={NO_HELD_CHOICE} onHold={onHold} />));
  const rail = host.querySelector("[data-milestone-form]")!;
  expect(rail.getAttribute("data-milestone-form")).toBe("bars");
  expect(rail.querySelector(".overflow-x-auto")).toBeNull();
  // Every milestone keeps its button, its line and its pregame chance (or the words for none) …
  const shown = card.players[0];
  const buttons = Array.from(rail.querySelectorAll("button"));
  expect(buttons).toHaveLength(shown.milestones.length);
  expect(shown.milestones.length).toBeGreaterThan(1);
  shown.milestones.forEach((m, i) => {
    expect(buttons[i].textContent).toContain(m.target);
    expect(buttons[i].textContent).toContain(m.before ? m.before.text : m.beforeMissing);
  });
  // … the default milestone is still the pressed one …
  expect(buttons.map((b) => b.getAttribute("aria-pressed"))).toEqual(
    shown.milestones.map((m) => String(m.id === shown.defaultMilestoneId)),
  );
  // … and every other milestone can still be chosen.
  const last = shown.milestones.length - 1;
  click(buttons[last]);
  expect(onHold).toHaveBeenCalledWith({ playerId: shown.id, milestoneId: shown.milestones[last].id });
});

it("points columns that do not fit their frame give way to stacked rows at standard text too", () => {
  const proto = HTMLElement.prototype as unknown as Record<string, unknown>;
  Object.defineProperty(proto, "clientWidth", { configurable: true, get: () => 261 });
  Object.defineProperty(proto, "scrollWidth", {
    configurable: true,
    get(this: HTMLElement) {
      // CONSTRUCTED layout: the lab's 464 px columns rail in a 261 px card.
      return this.tagName === "UL" && this.closest('[data-milestone-form="columns"]') ? 464 : 0;
    },
  });
  try {
    act(() => root.render(<HockeyJourneyContributionCard card={pregamePointsCard()} held={NO_HELD_CHOICE} onHold={() => {}} />));
    expect(host.querySelector("[data-milestone-form]")?.getAttribute("data-milestone-form")).toBe("bars");
  } finally {
    delete proto.clientWidth;
    delete proto.scrollWidth;
  }
});

const COLORS = { home: "var(--series-1)", away: "var(--series-2)" };

describe("the time axis draws a measured subset of the owner's tick labels (Design decision 2026-10-30)", () => {
  type Placed = { index: number; start: number; lane: number };
  /** Two labels in one row closer than `gap` (or overlapping). */
  const collide = (placed: Placed[], lengths: number[], gap: number) =>
    placed.some((a, i) =>
      placed.some(
        (b, j) =>
          j > i &&
          a.lane === b.lane &&
          a.start < b.start + lengths[b.index] + gap &&
          b.start < a.start + lengths[a.index] + gap,
      ),
    );

  it("draws every tick, centred on it, when all fit with clear space", () => {
    expect(axisLabelSubset([50, 150, 250, 350], [40, 40, 40, 40], 400, 6, 12)).toEqual([
      { index: 0, start: 30, lane: 0 },
      { index: 1, start: 130, lane: 0 },
      { index: 2, start: 230, lane: 0 },
      { index: 3, start: 330, lane: 0 },
    ]);
  });

  it("slides an edge label inward only as far as the plot needs", () => {
    expect(axisLabelSubset([0, 300], [40, 40], 300, 6)).toEqual([
      { index: 0, start: 0, lane: 0 },
      { index: 1, start: 260, lane: 0 },
    ]);
  });

  it("draws an intermediate only when it clears its neighbours by the clear gap, not merely the gap", () => {
    // first [0,80], last [180,260], middle [90,170]: 10 px either side.
    expect(axisLabelSubset([0, 130, 260], [80, 80, 80], 260, 6, 6).map((l) => l.index)).toEqual([0, 1, 2]);
    expect(axisLabelSubset([0, 130, 260], [80, 80, 80], 260, 6, 24).map((l) => l.index)).toEqual([0, 2]);
  });

  it("prefers two clear endpoints when the labels are large for the width", () => {
    // CONSTRUCTED: four 120 px labels (enlarged text) across a 261 px plot.
    expect(axisLabelSubset([0, 87, 174, 261], [120, 120, 120, 120], 261, 6, 24)).toEqual([
      { index: 0, start: 0, lane: 0 },
      { index: 3, start: 141, lane: 0 },
    ]);
  });

  it("gives the endpoints a second row only when they cannot share one, and then draws nothing between", () => {
    expect(axisLabelSubset([0, 87, 174, 261], [140, 140, 140, 140], 261, 6, 24)).toEqual([
      { index: 0, start: 0, lane: 0 },
      { index: 3, start: 121, lane: 1 },
    ]);
  });

  it("keeps a lone tick and draws nothing for none", () => {
    expect(axisLabelSubset([100], [40], 300, 6)).toEqual([{ index: 0, start: 80, lane: 0 }]);
    expect(axisLabelSubset([], [], 300, 6)).toEqual([]);
  });

  it("across widths and text sizes: endpoints always, no collision, inside the plot, on its tick unless slid", () => {
    const families = [
      ["5 PM", "6 PM", "7 PM", "8 PM"],
      ["Oct 10, 5 PM", "Oct 10, 6 PM", "Oct 10, 7 PM", "Oct 10, 8 PM"], // CONSTRUCTED label shapes
    ];
    for (const words of families) {
      for (const extent of [180, 261, 340, 600]) {
        for (const fontPx of [12, 18, 24]) {
          const lengths = words.map((w) => estimateLabelWidth(w, fontPx));
          const centers = words.map((_, i) => (extent * i) / (words.length - 1));
          const placed = axisLabelSubset(centers, lengths, extent, 6, Math.max(6, fontPx));
          expect(placed[0].index).toBe(0);
          expect(placed[placed.length - 1].index).toBe(words.length - 1);
          expect(collide(placed, lengths, 6)).toBe(false);
          for (const label of placed) {
            const length = Math.min(lengths[label.index], extent);
            expect(label.start).toBeGreaterThanOrEqual(0);
            expect(label.start + length).toBeLessThanOrEqual(extent + 1e-9);
            expect(label.start).toBeCloseTo(Math.min(Math.max(0, centers[label.index] - length / 2), extent - length), 9);
            expect(label.lane === 0 || (label.lane === 1 && placed.length === 2)).toBe(true);
          }
        }
      }
    }
  });

  it("the rendered chart at 200%: endpoints drawn, a subset of the ticks in order, clear of each other, the y labels and 0%", () => {
    withRootFont(32);
    const { history } = finalJourney(finalMarkets);
    act(() => root.render(<HockeyJourneyHistoryChart history={history} colors={COLORS} />));
    const svg = host.querySelector('svg[role="img"]')!;
    const xLabels = Array.from(svg.querySelectorAll("text[data-axis-lane]"));
    const ticks = xLabels.map((el) => Number(el.getAttribute("data-axis-tick")));
    expect(history.xTicks.length).toBeGreaterThan(1);
    expect(ticks[0]).toBe(0);
    expect(ticks[ticks.length - 1]).toBe(history.xTicks.length - 1);
    expect([...ticks].sort((a, b) => a - b)).toEqual(ticks);
    // Each drawn label is the owner's own words for its tick, unchanged.
    expect(xLabels.map((el) => el.textContent)).toEqual(ticks.map((i) => history.xTicks[i].label));
    const fontPx = 24; // text-xs (12 px) at a 32 px root
    const lengths = history.xTicks.map((tick) => estimateLabelWidth(tick.label, fontPx));
    const placed = xLabels.map((el) => ({
      index: Number(el.getAttribute("data-axis-tick")),
      start: Number(el.getAttribute("x")),
      lane: Number(el.getAttribute("data-axis-lane")),
    }));
    expect(collide(placed, lengths, 6)).toBe(false);
    // The y labels end at their anchor (text-anchor end); every x label starts to its right …
    const yLabels = Array.from(svg.querySelectorAll('text[text-anchor="end"]'));
    expect(yLabels.length).toBeGreaterThan(0);
    const yAnchor = Math.max(...yLabels.map((el) => Number(el.getAttribute("x"))));
    for (const p of placed) expect(p.start).toBeGreaterThan(yAnchor);
    // … and below the lowest y label (centred on its line), so "0%" and the first x label cannot touch.
    const lowestYLabelBottom = Math.max(...yLabels.map((el) => Number(el.getAttribute("y")))) + fontPx / 2;
    for (const el of xLabels) expect(Number(el.getAttribute("y"))).toBeGreaterThan(lowestYLabelBottom);
  });

  it("enlarged text never draws more time labels than standard text, and both keep the endpoints", () => {
    const { history } = finalJourney(finalMarkets);
    const drawn = () =>
      Array.from(host.querySelectorAll('svg[role="img"] text[data-axis-tick]')).map((el) => Number(el.getAttribute("data-axis-tick")));
    act(() => root.render(<HockeyJourneyHistoryChart history={history} colors={COLORS} />));
    const standard = drawn();
    act(() => root.unmount());
    withRootFont(32);
    root = createRoot(host);
    act(() => root.render(<HockeyJourneyHistoryChart history={history} colors={COLORS} />));
    const enlarged = drawn();
    expect(enlarged.length).toBeLessThanOrEqual(standard.length);
    for (const set of [standard, enlarged]) {
      expect(set[0]).toBe(0);
      expect(set[set.length - 1]).toBe(history.xTicks.length - 1);
    }
  });
});

// ─── Fidelity pass (Design 2026-10-30: compact About, line key, missing baselines, shown player) ─

it("About is a compact info control beside the header, its words the accessible name", () => {
  act(() => root.render(<HockeyJourneyPage journey={journey} />));
  const about = button("About these sources");
  expect(about.querySelector("svg")).not.toBeNull();
  expect(about.querySelector(".sr-only")?.textContent).toBe("About these sources");
  // Nothing printed beside the icon: the words are its accessible name only.
  const printed = Array.from(about.childNodes).filter((n) => n.nodeType === Node.TEXT_NODE && (n.textContent ?? "").trim() !== "");
  expect(printed).toHaveLength(0);
  for (const cls of ["min-h-11", "min-w-11", "shrink-0"]) expect(about.classList.contains(cls)).toBe(true);
  // Beside the state lines, in a row that does not wrap the control onto a line of its own…
  const row = about.parentElement!;
  expect(row.hasAttribute("data-hockey-journey-header-row")).toBe(true);
  expect(row.textContent).toContain(journey.headline.state);
  expect(row.classList.contains("flex-wrap")).toBe(false);
  // …while the title sits below that row at the card's full width, so the target's column never narrows it
  // (at 200% text on a 375px phone that column left the event's name one word per line).
  const heading = host.querySelector("h2")!;
  expect(row.contains(heading)).toBe(false);
  expect(heading.parentElement?.tagName).toBe("HEADER");
  expect(row.compareDocumentPosition(heading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  // Still a real disclosure with the same content.
  click(about);
  expect(about.getAttribute("aria-expanded")).toBe("true");
  expect(document.getElementById(about.getAttribute("aria-controls") ?? "")?.textContent).toContain("Pregame chance: Pre-match");
});

it("prints the history's readings as one compact key under the plot; exact timing moves into Details", () => {
  const { history } = finalJourney(finalMarkets);
  act(() => root.render(<HockeyJourneyHistoryChart history={history} colors={COLORS} />));
  const key = host.querySelector("[data-line-key]")!;
  const [home, away] = Array.from(key.children);
  expect(key.children).toHaveLength(2);
  expect(home.querySelector("p")?.textContent).toBe("Minnesota Wild");
  expect(away.querySelector("p")?.textContent).toBe("Boston Bruins");
  expect(home.querySelector("dl")?.textContent).toBe("Pregame66%");
  expect(away.querySelector("dl")?.textContent).toBe("Pregame34%");
  // The key follows the plot; no per-team boxes; no clock words on the face.
  const plot = host.querySelector('svg[role="img"]')!;
  expect(plot.compareDocumentPosition(key) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(host.querySelector(".bg-surface-deep")).toBeNull();
  expect(key.textContent).not.toContain("Last pregame");
  const basis = host.querySelector("[data-history-basis]")?.textContent ?? "";
  expect(basis).toContain("Game history");
  expect(basis).toContain("Hollow · last pregame");
  const details = button("History & source details");
  const region = document.getElementById(details.getAttribute("aria-controls") ?? "")!;
  expect(region.hidden).toBe(true);
  click(details);
  expect(region.hidden).toBe(false);
  expect(region.textContent).toContain("Minnesota Wild · Pregame 66% · Last pregame · ");
  expect(region.textContent).toContain("Boston Bruins · Pregame 34% · Last pregame · ");
  expect(region.textContent).toContain("Source: Bain Luck");
  expect(region.textContent).toContain("Gaps remain blank.");
});

it("when the readout asks, each team keeps its own labelled pregame and recorded slots; an absent slot keeps its words", () => {
  const { history: base } = finalJourney(finalMarkets);
  // CONSTRUCTED presentation input: the final history given a live readout; one side has no recorded row.
  const history = {
    ...base,
    readout: "beforeAndRecorded" as const,
    series: [
      { ...base.series[0], recorded: { kind: "reading" as const, figure: "71%", provenance: "Recorded 9:30 PM", pointId: null } },
      { ...base.series[1], recorded: { kind: "absent" as const, words: "Not recorded" } },
    ] as typeof base.series,
  };
  act(() => root.render(<HockeyJourneyHistoryChart history={history} colors={COLORS} />));
  const [home, away] = Array.from(host.querySelector("[data-line-key]")!.children);
  expect(Array.from(home.querySelectorAll("dt")).map((d) => d.textContent)).toEqual(["Pregame", "Recorded"]);
  expect(Array.from(home.querySelectorAll("dd")).map((d) => d.textContent)).toEqual(["66%", "71%"]);
  expect(Array.from(away.querySelectorAll("dt")).map((d) => d.textContent)).toEqual(["Pregame", "Recorded"]);
  expect(Array.from(away.querySelectorAll("dd")).map((d) => d.textContent)).toEqual(["34%", "Not recorded"]);
  expect(home.textContent).not.toContain("9:30 PM");
  const details = button("History & source details");
  click(details);
  const region = document.getElementById(details.getAttribute("aria-controls") ?? "")!;
  expect(region.textContent).toContain("Minnesota Wild · Recorded 71% · Recorded 9:30 PM");
  expect(region.textContent).not.toContain("Boston Bruins · Recorded");
});

it("with no history response both teams are still named in the key, each slot's words printed once", () => {
  const missing = buildHockeyJourney({
    event: finalEvent,
    history: null, // CONSTRUCTED: no history response
    gameMarkets: finalMarkets,
    host: { nowMs: FINAL_NOW, hero: null, probabilityObservedAt: null },
  });
  act(() => root.render(<HockeyJourneyHistoryChart history={missing.history} colors={COLORS} />));
  const entries = Array.from(host.querySelector("[data-line-key]")!.children);
  expect(entries.map((li) => li.querySelector("p")?.textContent)).toEqual(["Minnesota Wild", "Boston Bruins"]);
  for (const li of entries) {
    expect(li.querySelector("dd")?.textContent).toBe("History unavailable");
    expect(li.querySelector("dt")?.classList.contains("sr-only")).toBe(true);
  }
});

const finalPointsCard = () => hockeyJourneyContribution("points", finalEvent, finalMarkets, FINAL_NOW)!;

it("a player with no pregame chance on any milestone takes a compact row of targets — absence, result and count kept, no empty bars", () => {
  const card = finalPointsCard();
  const hughes = card.players.find((p) => p.name === "Quinn Hughes")!;
  expect(hughes.milestones.length).toBeGreaterThan(1);
  expect(hughes.milestones.every((m) => m.before === null)).toBe(true);
  const onHold = jest.fn();
  act(() => root.render(<HockeyJourneyContributionCard card={card} held={{ playerId: hughes.id, milestoneId: null }} onHold={onHold} />));
  const rail = host.querySelector("[data-milestone-form]")!;
  expect(rail.getAttribute("data-milestone-form")).toBe("targets");
  const buttons = Array.from(rail.querySelectorAll("button"));
  // Each target, its own absence words and its settled result — in milestone order.
  expect(buttons.map((b) => b.textContent)).toEqual(hughes.milestones.map((m) => `${m.target}${m.beforeMissing}${m.result?.words ?? ""}`));
  // No bar is drawn, no chance printed.
  expect(rail.querySelectorAll('[aria-hidden="true"]')).toHaveLength(0);
  expect(rail.textContent).not.toContain("%");
  // The count stays its own block, untouched.
  const text = host.textContent ?? "";
  expect(text).toContain("Final count");
  expect(text).toContain("1 goal + 1 assist");
  // No default milestone (none has a chance); every target can still be chosen.
  expect(buttons.map((b) => b.getAttribute("aria-pressed"))).toEqual(hughes.milestones.map(() => "false"));
  click(buttons[1]);
  expect(onHold).toHaveBeenCalledWith({ playerId: hughes.id, milestoneId: hughes.milestones[1].id });
  // Even at an accessibility text size the targets keep this form.
  act(() => root.unmount());
  withRootFont(32);
  root = createRoot(host);
  act(() => root.render(<HockeyJourneyContributionCard card={card} held={{ playerId: hughes.id, milestoneId: null }} onHold={onHold} />));
  expect(host.querySelector("[data-milestone-form]")?.getAttribute("data-milestone-form")).toBe("targets");
});

it("a player with some chances keeps the full columns, the missing milestone honest in its own place", () => {
  const base = pregamePointsCard();
  const eichel = base.players[0];
  // CONSTRUCTED: the first milestone without its pregame chance; the rest unchanged.
  const mixed = {
    ...base,
    players: [
      { ...eichel, milestones: eichel.milestones.map((m, i) => (i === 0 ? { ...m, before: null, beforeMissing: "Unavailable" } : m)) },
      ...base.players.slice(1),
    ],
  };
  act(() => root.render(<HockeyJourneyContributionCard card={mixed} held={NO_HELD_CHOICE} onHold={() => {}} />));
  const rail = host.querySelector("[data-milestone-form]")!;
  expect(rail.getAttribute("data-milestone-form")).toBe("columns");
  const buttons = Array.from(rail.querySelectorAll("button"));
  expect(buttons[0].textContent).toContain("Unavailable");
  expect(buttons[0].querySelector(".absolute")).toBeNull(); // its column stays empty — never a neighbour's height
  const populated = mixed.players[0].milestones.findIndex((m) => m.before !== null);
  expect(populated).toBeGreaterThan(0);
  expect(buttons[populated].querySelector(".absolute")).not.toBeNull();
  expect(buttons[populated].textContent).toContain(mixed.players[0].milestones[populated].before!.text);
});

it("prints the shown player's whole name and team on the card, outside the closed picker", () => {
  const card = finalPointsCard();
  const [kaprizov, shabanov] = card.players;
  act(() => root.render(<HockeyJourneyContributionCard card={card} held={NO_HELD_CHOICE} onHold={() => {}} />));
  const shown = () => host.querySelector("[data-shown-player]")!;
  expect(shown().textContent).toBe(`${kaprizov.name}${kaprizov.team ?? ""}`);
  expect(shown().contains(host.querySelector("select"))).toBe(false);
  expect(shown().querySelector(".truncate")).toBeNull();
  expect(shown().querySelector("p")?.classList.contains("break-words")).toBe(true);
  // The picker keeps its constrained footprint.
  expect(host.querySelector("select")?.classList.contains("max-w-full")).toBe(true);
  // A held choice of another player (team not served) moves the identity with it.
  act(() => root.render(<HockeyJourneyContributionCard card={card} held={{ playerId: shabanov.id, milestoneId: null }} onHold={() => {}} />));
  expect(shown().textContent).toBe(shabanov.name);
  // A held player no longer served shows no one else's identity.
  act(() => root.render(<HockeyJourneyContributionCard card={card} held={{ playerId: "player:nobody", milestoneId: null }} onHold={() => {}} />));
  expect(host.querySelector("[data-shown-player]")).toBeNull();
});

// ─── FQ2 (Design admission 2026-10-31): period guide labels stay inside the chart ─────────────
//
// Browser lab c9bcdad25b (RESULTS sha256 f3c763c1…): Jaguars–Eagles 14639175 live at 200% text drew
// "Q3" from 3 px right of its guide line straight past the SVG's right edge (375 px: 299.6–331.9
// against an SVG ending at 318; 393 px: 316.9–349.1 against 336). The chart frame widths below are
// the lab's measured SVG widths for those two phones (CONSTRUCTED layout: jsdom lays nothing out,
// so the frame's clientWidth is set to the measured value; label widths are the chart's own
// estimate, which is what it draws with before the browser can measure).

describe("period guide labels stay inside the SVG, at their own line when they have room (FQ2)", () => {
  /** CONSTRUCTED layout: the chart frame's width in px, as the browser lab measured it. */
  function withFrameWidth(px: number) {
    Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, get: () => px });
  }
  afterEach(() => {
    delete (HTMLElement.prototype as unknown as Record<string, unknown>).clientWidth;
  });

  const jagLive = footballFixtures.jaguarsLiveDetail as unknown as EventDetailResponse;
  const jagLiveHistory = footballFixtures.jaguarsLiveHistory as unknown as EventHistoryResponse;
  const JAG_LIVE_NOW = Date.parse("2026-10-11T15:37:30Z");
  /** The history the football section draws for the retained live read (footballJourney10868 tests' JAG_LIVE_NOW). */
  const jaguarsLive = () => footballJourneyHistory(jagLiveHistory, jagLive, "live", JAG_LIVE_NOW).history;
  const hockeyFinal = () => finalJourney(finalMarkets).history;

  /** Every period label the chart drew, found by its own words, with its own guide line. */
  function periodLabels(history: HockeyJourneyHistory, fontPx: number) {
    const svg = host.querySelector('svg[role="img"]')!;
    const texts = Array.from(svg.querySelectorAll("text"));
    const labels = history.guides
      .filter((guide) => guide.kind === "period")
      .map((guide) => {
        const text = texts.find((t) => t.textContent === guide.label)!;
        const line = text.parentElement!.querySelector("line")!;
        const start = Number(text.getAttribute("x"));
        return {
          label: guide.label,
          className: text.getAttribute("class") ?? "",
          start,
          end: start + estimateLabelWidth(guide.label, fontPx),
          y: Number(text.getAttribute("y")),
          lineX: Number(line.getAttribute("x1")),
          lineTop: Number(line.getAttribute("y1")),
        };
      });
    const yLabels = Array.from(svg.querySelectorAll('text[text-anchor="end"]')).map((t) => Number(t.getAttribute("y")));
    return {
      width: Number(svg.getAttribute("width")),
      height: Number(svg.getAttribute("height")),
      plotHeight: Math.max(...yLabels) - Math.min(...yLabels),
      labels,
    };
  }

  it.each([
    [375, 261],
    [393, 279],
  ])(
    "Jaguars live, 200 percent text, %i px phone (chart %i px): Q3 stays inside the SVG, still at its own line, at full size",
    (_phone, frameWidth) => {
      withRootFont(32);
      withFrameWidth(frameWidth);
      const history = jaguarsLive();
      expect(history.guides.filter((guide) => guide.kind === "period").map((guide) => guide.label)).toEqual(["Q1", "Q2", "Q3"]);
      act(() => root.render(<HockeyJourneyHistoryChart history={history} colors={COLORS} />));
      const drawn = periodLabels(history, 24); // text-xs (12 px) at a 32 px root
      expect(drawn.width).toBe(frameWidth);
      const q3 = drawn.labels.find((label) => label.label === "Q3")!;
      // Where Q3 always started (3 px right of its line) it would end past the SVG: the lab's escape.
      expect(q3.lineX + 3 + estimateLabelWidth("Q3", 24)).toBeGreaterThan(drawn.width);
      for (const label of drawn.labels) {
        expect(label.start).toBeGreaterThanOrEqual(0);
        expect(label.end).toBeLessThanOrEqual(drawn.width); // inside the SVG
        expect(label.start).toBeLessThanOrEqual(label.lineX + 3); // never further right than it always was
        expect(label.end).toBeGreaterThanOrEqual(label.lineX); // still reaches its own line
        expect(label.className.split(/\s+/)).toContain("text-xs"); // type never shrinks
        expect(label.y).toBeLessThan(label.lineTop); // above the plot, never over the lines
      }
      // Q1 and Q2 already fit: exactly where they always were.
      for (const label of drawn.labels.filter((l) => l.label !== "Q3")) {
        expect(label.start).toBe(label.lineX + 3);
        expect(label.y).toBe(label.lineTop - 8);
      }
    },
  );

  it("at 100% text every caller's period labels are exactly where they always were (hockey final, Jaguars live)", () => {
    const cases: Array<[string, () => HockeyJourneyHistory, number]> = [
      ["hockey final 15169793", hockeyFinal, 317],
      ["hockey final 15169793", hockeyFinal, 1190],
      ["Jaguars live 14639175", jaguarsLive, 317],
      ["Jaguars live 14639175", jaguarsLive, 335],
      ["Jaguars live 14639175", jaguarsLive, 1190],
    ];
    for (const [name, make, frameWidth] of cases) {
      withFrameWidth(frameWidth);
      const history = make();
      act(() => root.render(<HockeyJourneyHistoryChart key={`${name}|${frameWidth}`} history={history} colors={COLORS} />));
      const drawn = periodLabels(history, 12);
      expect(drawn.labels.length).toBeGreaterThan(0);
      for (const label of drawn.labels) {
        expect([name, frameWidth, label.label, label.start]).toEqual([name, frameWidth, label.label, label.lineX + 3]);
        expect([name, frameWidth, label.label, label.y]).toEqual([name, frameWidth, label.label, label.lineTop - 8]);
      }
    }
  });

  it("guideLabelPlacement: fitting labels keep their start; an edge label slides only as far as the edge; never past the plot's left; a collision lifts a row", () => {
    expect(guideLabelPlacement([100, 200], [17, 17], 44, 317, 6)).toEqual([
      { index: 0, start: 103, lane: 0 },
      { index: 1, start: 203, lane: 0 },
    ]);
    // The lab's 375 px / 200% Q3: line at 239.6, a 32.3 px label, a 261 px SVG — it ends at the edge.
    expect(guideLabelPlacement([239.6], [32.3], 56, 261, 6)).toEqual([{ index: 0, start: 261 - 32.3, lane: 0 }]);
    // Longer than the room: it starts at the plot's left edge, never over the y labels.
    expect(guideLabelPlacement([60], [300], 56, 261, 6)).toEqual([{ index: 0, start: 56, lane: 0 }]);
    // Two lines 5 px apart: the second keeps its own start and takes the row above.
    expect(guideLabelPlacement([100, 105], [30, 30], 44, 317, 6)).toEqual([
      { index: 0, start: 103, lane: 0 },
      { index: 1, start: 108, lane: 1 },
    ]);
    // An edge slide that lands on a neighbour lifts the slid label.
    expect(guideLabelPlacement([210, 250], [30, 30], 44, 270, 6)).toEqual([
      { index: 0, start: 213, lane: 0 },
      { index: 1, start: 240, lane: 1 },
    ]);
    expect(guideLabelPlacement([], [], 44, 317, 6)).toEqual([]);
  });

  it("a lifted row adds height above the plot: the plot keeps its height and every guide line keeps its time (TEST MUTATION: a constructed Q4 one minute after Q3)", () => {
    withRootFont(32);
    withFrameWidth(261);
    const history = jaguarsLive();
    act(() => root.render(<HockeyJourneyHistoryChart history={history} colors={COLORS} />));
    const base = periodLabels(history, 24);
    const q3 = history.guides.find((guide) => guide.label === "Q3")!;
    const crowded: HockeyJourneyHistory = {
      ...history,
      guides: [...history.guides, { id: "period:Q4", t: q3.t + 60_000, label: "Q4", kind: "period" }], // CONSTRUCTED
    };
    act(() => root.render(<HockeyJourneyHistoryChart history={crowded} colors={COLORS} />));
    const lifted = periodLabels(crowded, 24);
    const laneHeight = Math.ceil(24 * 1.25);
    expect(lifted.plotHeight).toBe(base.plotHeight);
    expect(lifted.height).toBe(base.height + laneHeight);
    const at = (d: typeof base, label: string) => d.labels.find((l) => l.label === label)!;
    expect(at(lifted, "Q4").y).toBe(at(lifted, "Q3").y - laneHeight);
    for (const label of ["Q1", "Q2", "Q3"]) {
      expect(at(lifted, label).lineX).toBe(at(base, label).lineX);
      expect(at(lifted, label).start).toBe(at(base, label).start);
    }
    for (const label of lifted.labels) {
      expect(label.start).toBeGreaterThanOrEqual(0);
      expect(label.end).toBeLessThanOrEqual(lifted.width);
      expect(label.y).toBeGreaterThan(0);
    }
  });
});

// ─── All props rows say which prop they are before Details opens (M1) ──────
//
// The e9b6 browser review counted "Over" 191 times on the REAL 15321836 final:
// team totals, first-five totals and player props all list that side, so a row
// and its Details button said only "Over". The shared row now leads with the
// served market text the view model already built (`title`: subject and
// threshold), then the side (`label`) and the venue (`about.source`); Details'
// accessible name uses the same fields. The view model is the shared builder's
// (`hockeyJourneyOriginals`), unchanged. Two genuinely identical venue offers may
// still read alike, so names are compared against the distinct props they name.

describe("All props rows name their prop, side and venue, and Details has a specific accessible name", () => {
  const mlbFinal = hockeyJourneyOriginals(
    mlbFixtures.finalDetail as unknown as EventDetailResponse,
    mlbFixtures.finalMarkets as unknown as GameMarketsResponse,
    Date.parse("2026-10-11T04:57:23.592725Z"),
  );
  const hockeyFinal = hockeyJourneyOriginals(
    fixtures.finalDetail as unknown as EventDetailResponse,
    fixtures.finalMarkets as unknown as GameMarketsResponse,
    Date.parse("2026-10-11T04:56:41Z"),
  );
  /** Each rendered row beside the original it draws (rows are drawn in the model's order). */
  function rendered(originals: typeof mlbFinal) {
    act(() => root.render(<HockeyJourneyAllProps originals={originals} entryLabel="All props" />));
    const rows = Array.from(host.querySelectorAll("li"));
    expect(rows).toHaveLength(originals.originals.length);
    return originals.originals.map((original, i) => ({
      original,
      row: rows[i],
      /** The row's face before Details opens: the prop block, beside its reading. */
      prop: rows[i].querySelector("div > span")?.textContent ?? "",
      name: rows[i].querySelector("button")?.textContent ?? "",
    }));
  }
  const propOf = (o: (typeof mlbFinal)["originals"][number]) => `${o.title}|${o.label}|${o.about.source ?? ""}`;

  it("REAL MLB final: rows that share the side Over read as their own subject and threshold", () => {
    const over = rendered(mlbFinal).filter(({ original }) => original.label === "Over");
    // Several different props list the same side (REAL: team totals, first-five totals, player props).
    expect(over.length).toBeGreaterThan(1);
    expect(new Set(over.map(({ original }) => original.title)).size).toBeGreaterThan(1);
    for (const { original, prop } of over) {
      expect(prop).toContain(original.title);
      expect(prop).toContain("Over");
      if (original.about.source) expect(prop).toContain(original.about.source);
    }
    // One distinct face per distinct prop: no longer a column of identical "Over" rows.
    expect(new Set(over.map(({ prop }) => prop)).size).toBe(new Set(over.map(({ original }) => propOf(original))).size);
  });

  it("REAL MLB final: each Details button's accessible name says which prop it opens", () => {
    const over = rendered(mlbFinal).filter(({ original }) => original.label === "Over");
    for (const { original, name } of over) {
      expect(name.startsWith("Details")).toBe(true);
      expect(name).toContain(original.title);
      expect(name).toContain("Over");
      if (original.about.source) expect(name).toContain(original.about.source);
    }
    expect(over.map(({ name }) => name)).not.toContain("Details: Over");
    expect(new Set(over.map(({ name }) => name)).size).toBe(new Set(over.map(({ original }) => propOf(original))).size);
  });

  it("opening a row's Details shows the same payload as before: the original's title, outcome, venue and ids", () => {
    const [first] = rendered(mlbFinal).filter(({ original }) => original.label === "Over");
    const details = first.row.querySelector("button")!;
    const region = document.getElementById(details.getAttribute("aria-controls") ?? "")!;
    expect(region.hidden).toBe(true);
    click(details);
    expect(region.hidden).toBe(false);
    const paragraphs = Array.from(region.children)
      .filter((el) => el.tagName === "P")
      .map((p) => p.textContent);
    expect(paragraphs).toEqual([first.original.title, first.original.outcome]);
    for (const row of first.original.about.rows) expect(region.textContent).toContain(`${row.label}${row.value}`);
  });

  it("hockey keeps its readable rows: the rung's own words, under its market, with its venue", () => {
    const rows = rendered(hockeyFinal);
    const kaprizov = rows.find(({ original }) => original.label === "Kirill Kaprizov 2+ points");
    expect(kaprizov).toBeDefined();
    for (const { original, prop, name } of rows) {
      expect(prop).toContain(original.title);
      expect(prop).toContain(original.label);
      expect(name).toContain(original.label);
      if (original.about.source) expect(prop).toContain(original.about.source);
    }
    // The existing hockey reading is unchanged: after the final the row's figure is still its own grade.
    expect(kaprizov!.original.grade).not.toBeNull();
    expect(kaprizov!.row.querySelector("div")?.textContent).toContain(kaprizov!.original.grade!.words);
  });

  it("CONSTRUCTED: a label that only repeats the title is said once, and no venue leaves no stray separator", () => {
    const base = hockeyFinal.originals[0];
    const lone = { ...hockeyFinal, originals: [{ ...base, title: base.label, about: { ...base.about, source: null } }] };
    const [only] = rendered(lone);
    expect(only.prop).toBe(base.label);
    expect(only.name.split(base.label).length - 1).toBe(1);
    expect(only.name).not.toContain(" · ");
    expect(only.name.trim().endsWith(",")).toBe(false);
  });
});
