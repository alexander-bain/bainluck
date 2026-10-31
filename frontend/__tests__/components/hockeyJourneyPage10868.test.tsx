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
 * negative control; and forced element widths for the matrix's fit steps
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
import HockeyJourneyMatrix, { matrixArrangements } from "@/components/event/eventpage10868/HockeyJourneyMatrix";
import HockeyJourneyHistoryChart, {
  axisLabelSubset,
  estimateLabelWidth,
} from "@/components/event/eventpage10868/HockeyJourneyHistoryChart";

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
  expect(table?.textContent).toContain("No pregame forecast");
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
    const blocks = Array.from(host.querySelectorAll('[role="group"]'));
    expect(blocks.map((b) => b.getAttribute("aria-label"))).toEqual([headline.home.name, headline.away.name]);
    expect(blocks[0].querySelectorAll("dl")).toHaveLength(headline.matrix.groups.length);
    expect(Array.from(blocks[0].querySelectorAll("dt")).map((dt) => dt.textContent)).toEqual(
      headline.matrix.columns.map((c) => c.title),
    );
    expect(blocks[0].textContent).toContain("66%");
  } finally {
    delete proto.clientWidth;
    delete proto.scrollWidth;
  }
});

/**
 * Forced layout for the same-component reflow cases: the matrix frame is 300 px
 * wide, and a GRID with four metric columns (five header cells) is 1000 px
 * wide — it overflows — while two or three columns fit. Every other element
 * reports 0. jsdom lays nothing out, so this proves the re-measure, not real fit.
 */
function withForcedMatrixLayout(run: () => void) {
  const proto = HTMLElement.prototype as unknown as Record<string, unknown>;
  Object.defineProperty(proto, "clientWidth", { configurable: true, get: () => 300 });
  Object.defineProperty(proto, "scrollWidth", {
    configurable: true,
    get(this: HTMLElement) {
      if (this.dataset?.arrangement === undefined) return 0;
      return this.querySelectorAll("thead th").length >= 5 ? 1000 : 300;
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

it("re-fits the SAME matrix when its content changes: before fits, live overflows to pairs, a narrower final climbs back", () => {
  const history = fixtures.finalHistory as unknown as EventHistoryResponse;
  const hostAt = (nowMs: number) => ({ nowMs, hero: null, probabilityObservedAt: null });
  // CONSTRUCTED lifecycle of 15169793 (status, scores, score clock and ESPN period/clock edited):
  const before = hockeyJourneyHeadline(
    { ...finalEvent, status: "scheduled", home_score: null, away_score: null } as unknown as EventDetailResponse,
    history,
    hostAt(Date.parse("2026-10-03T23:00:00Z")),
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
    hostAt(Date.parse("2026-10-04T01:46:00Z")),
  );
  const final = hockeyJourneyHeadline(finalEvent, history, hostAt(FINAL_NOW));
  expect([before.matrix.columns.length, live.matrix.columns.length, final.matrix.columns.length]).toEqual([2, 4, 3]);

  withForcedMatrixLayout(() => {
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
  const build = (event: EventDetailResponse, nowMs: number) =>
    buildHockeyJourney({
      event,
      history: fixtures.pregameHistory as unknown as EventHistoryResponse,
      gameMarkets: fixtures.pregameMarkets as unknown as GameMarketsResponse,
      host: { nowMs, hero: null, probabilityObservedAt: null },
    });
  withForcedMatrixLayout(() => {
    act(() => root.render(<HockeyJourneyPage journey={build(pregameDetail, Date.parse("2026-10-30T20:13:55Z"))} />));
    expect(arrangementNow()).toBe("grid");
    const select = () => host.querySelector("article select") as HTMLSelectElement;
    choose(select(), "player:jack hughes");
    expect(host.querySelector('[aria-label="Jack Hughes milestones"]')).not.toBeNull();

    // CONSTRUCTED: the same game read live (status only); same page element, no key change.
    const live = { ...pregameDetail, status: "live" } as EventDetailResponse;
    act(() => root.render(<HockeyJourneyPage journey={build(live, Date.parse("2026-10-30T22:30:00Z"))} />));
    expect(arrangementNow()).toBe("pairs");
    expect(select().value).toBe("player:jack hughes");
    expect(host.querySelector('[aria-label="Jack Hughes milestones"]')).not.toBeNull();
    expect(host.textContent).not.toContain("Selected player unavailable.");
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
