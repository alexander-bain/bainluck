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
  axisLabelSlots,
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

describe("axis labels never collide (native labelSlots: lanes, nothing dropped, ticks unmoved)", () => {
  const collide = (slots: { start: number; lane: number }[], lengths: number[], gap: number) =>
    slots.some((a, i) =>
      slots.some((b, j) => j > i && a.lane === b.lane && a.start < b.start + lengths[j] + gap && b.start < a.start + lengths[i] + gap),
    );

  it("keeps separate labels in one lane, centred, and slides edge labels inward", () => {
    expect(axisLabelSlots([50, 150, 250], [40, 40, 40], 300, 6)).toEqual([
      { start: 30, lane: 0 },
      { start: 130, lane: 0 },
      { start: 230, lane: 0 },
    ]);
    expect(axisLabelSlots([0, 300], [40, 40], 300, 6)).toEqual([
      { start: 0, lane: 0 },
      { start: 260, lane: 0 },
    ]);
  });

  it("moves a label that would overlap its neighbour to the next lane, dropping none", () => {
    // CONSTRUCTED: three date-and-time labels 100 px apart in a 261 px plot at a 24 px axis font (200% text).
    const lengths = ["Oct 3, 5:00 PM", "Oct 3, 6:00 PM", "Oct 3, 7:00 PM"].map((t) => estimateLabelWidth(t, 24));
    const slots = axisLabelSlots([20, 120, 220], lengths, 261, 6);
    expect(slots).toHaveLength(3);
    expect(collide(slots, lengths, 6)).toBe(false);
    slots.forEach((slot, i) => {
      expect(slot.start).toBeGreaterThanOrEqual(0);
      expect(slot.start + Math.min(lengths[i], 261)).toBeLessThanOrEqual(261 + 1e-9);
    });
    expect(new Set(slots.map((s) => s.lane)).size).toBeGreaterThan(1);
  });

  it("the rendered chart at 200% keeps every x label clear of its lane neighbours and of the y labels", () => {
    withRootFont(32);
    const { history } = finalJourney(finalMarkets);
    act(() => root.render(<HockeyJourneyHistoryChart history={history} colors={{ home: "var(--series-1)", away: "var(--series-2)" }} />));
    const svg = host.querySelector('svg[role="img"]')!;
    const xLabels = Array.from(svg.querySelectorAll("text[data-axis-lane]"));
    // Nothing dropped: one label per tick, in tick order.
    expect(xLabels.map((el) => el.textContent)).toEqual(history.xTicks.map((tick) => tick.label));
    expect(xLabels.length).toBeGreaterThan(1);
    const fontPx = 24; // text-xs (12 px) at a 32 px root
    const placed = xLabels.map((el) => ({
      start: Number(el.getAttribute("x")),
      lane: Number(el.getAttribute("data-axis-lane")),
      length: estimateLabelWidth(el.textContent ?? "", fontPx),
    }));
    expect(collide(placed, placed.map((p) => p.length), 6)).toBe(false);
    // The y labels end at their anchor (text-anchor end); every x label starts to its right …
    const yLabels = Array.from(svg.querySelectorAll('text[text-anchor="end"]'));
    expect(yLabels.length).toBeGreaterThan(0);
    const yAnchor = Math.max(...yLabels.map((el) => Number(el.getAttribute("x"))));
    for (const p of placed) expect(p.start).toBeGreaterThan(yAnchor);
    // … and below the lowest y label (centred on its line), so "0%" and the first x label cannot touch.
    const lowestYLabelBottom = Math.max(...yLabels.map((el) => Number(el.getAttribute("y")))) + fontPx / 2;
    for (const el of xLabels) expect(Number(el.getAttribute("y"))).toBeGreaterThan(lowestYLabelBottom);
  });
});
