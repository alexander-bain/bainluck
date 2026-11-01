/** @jest-environment jsdom */
/**
 * #10868 — the web soccer match screen renders its view model and its controls
 * work: the three-outcome headline tries aligned columns first and falls back
 * to labelled blocks only when a measured cell does not fit or the text is an
 * accessibility size; the history draws each run as its own path and keys Draw
 * and the away win by their words; the story stream moves only on Previous /
 * Next (no timer); each story card is its approved native VISUAL (marks drawn
 * only for qualified chances, the count and results kept apart from chance,
 * the reader's choice held and read out); and All props opens with each
 * original's exact Details. Same harness as `hockeyJourneyPage10868.test.tsx`
 * (react-dom `createRoot` + `act`; the repo has no @testing-library/react).
 *
 * Bodies: the verbatim native soccer fixtures documented in
 * `__tests__/lib/soccerMatch10868.test.ts`. CONSTRUCTED, and named where used:
 * the owner's story admissions and exact-score descriptor (no production owner
 * supplies them), a missing history response, forced layout widths and a root
 * font size, and single edited readings on a built card. jsdom lays nothing
 * out: these prove the arrangement choice and the drawn geometry's inputs, not
 * real fit at 375 or 393 px, which only a browser render proves (owed).
 */
import React from "react";
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import fixtures from "../lib/soccerMatch10868.fixtures.json";
import type { EventDetailResponse, EventHistoryResponse } from "@/lib/types";
import type { GameMarketsResponse } from "@/lib/api";
import { formatProbabilityPercent } from "@/lib/probabilityDisplay";
import { PROP_HIT_LABEL, PROP_MISS_LABEL } from "@/lib/propGrade";
import {
  buildSoccerMatch,
  EXACT_WORDS,
  soccerExactCard,
  soccerMatchPhase,
  soccerNames,
  type SoccerMatchAdmission,
  type SoccerMatchViewModel,
} from "@/lib/eventPage10868/soccerMatch";
import type {
  SoccerBothCard,
  SoccerExactCard,
  SoccerFirstCard,
  SoccerGoalsCard,
  SoccerHalvesCard,
  SoccerStoryCard,
  SoccerStoryStream,
} from "@/lib/eventPage10868/soccerMatchTypes";
import SoccerMatchPage from "@/components/event/eventpage10868/SoccerMatchPage";
import SoccerMatchHeadline, {
  soccerHeadlineArrangements,
  soccerHeadlineFitContent,
} from "@/components/event/eventpage10868/SoccerMatchHeadline";
import SoccerMatchStories, { exactCellFill } from "@/components/event/eventpage10868/SoccerMatchStories";

type BodyKey = keyof typeof fixtures.bodies;
type Json = Record<string, unknown>;
const parsed = (key: BodyKey): Json => JSON.parse(fixtures.bodies[key].raw) as Json;
const detail = (key: BodyKey) => parsed(key) as unknown as EventDetailResponse;
const history = (key: BodyKey) => parsed(key) as unknown as EventHistoryResponse;
const markets = (key: BodyKey) => parsed(key) as unknown as GameMarketsResponse;
const pct = formatProbabilityPercent;

const LIVE_NOW = Date.parse(fixtures.provenance.clocks.liveNow);
const FINAL_NOW = Date.parse(fixtures.provenance.clocks.finalNow);
const EXACT_PRE_NOW = Date.parse(fixtures.provenance.clocks.exactPreKickoffNow);
const EXACT_FINAL_NOW = Date.parse(fixtures.provenance.clocks.exactFinalNow);

/** CONSTRUCTED owner metadata (native's ids; no production owner supplies it). */
const C = fixtures.constructed as unknown as {
  liveAdmission: SoccerMatchAdmission;
  hullAdmission: SoccerMatchAdmission;
  fullTotals: number[];
  hullDescriptor: NonNullable<SoccerMatchAdmission["exactScore"]>;
};
/** CONSTRUCTED: Hull before kickoff with the goal totals and the exact-score descriptor admitted. */
const HULL_BEFORE_ADMISSION: SoccerMatchAdmission = { ...C.hullAdmission, goals: C.fullTotals, exactScore: C.hullDescriptor };

function page(
  event: EventDetailResponse,
  held: EventHistoryResponse | null,
  body: GameMarketsResponse | null,
  nowMs: number,
  admitted?: SoccerMatchAdmission,
  extra: { halvesAdmission?: "routeDefault" | "explicit" } = {},
): SoccerMatchViewModel {
  return buildSoccerMatch({
    event,
    history: held,
    gameMarkets: body,
    admitted,
    ...extra,
    // The hero's home value as page.tsx would hold it; only the home value is ever read.
    host: { nowMs, hero: { homeProb: event.hero_probability ?? null, awayProb: null, homePct: null, awayPct: null }, probabilityObservedAt: event.hero_probability_observed_at ?? null },
  });
}

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

function button(label: string, within: ParentNode = host): HTMLButtonElement {
  const found = Array.from(within.querySelectorAll("button")).find((b) => (b.textContent ?? "").startsWith(label));
  if (!found) throw new Error(`no button "${label}"`);
  return found;
}

function click(el: Element) {
  act(() => {
    el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
}

const text = (selector: string, within: ParentNode = host) => within.querySelector(selector)?.textContent ?? "";
/** The numeric value of a percentage style (`bottom`, `left`, `width`) on a mark's positioned box. */
const percentOf = (el: Element | null | undefined, prop: "bottom" | "left" | "width") =>
  parseFloat((el as HTMLElement | null)?.style[prop] ?? "NaN");
/** A one-card stream, for a card built straight from the owner (no page route). */
const oneCard = (card: SoccerStoryCard): SoccerStoryStream => ({ scope: "soccer:one-card", heading: "Stories", cards: [card], manualStatus: null, storiesLabel: "Stories", emptyWords: "" });
const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T;

const live = page(detail("liveDetail"), history("liveHistory"), markets("liveMarkets"), LIVE_NOW);
const hullBefore = page(detail("hullDetail"), history("hullHistory"), markets("hullExactMarkets"), EXACT_PRE_NOW);

// ─── The headline: columns first, labelled blocks only when they do not fit ──

/**
 * CONSTRUCTED layout: every element is 100 px wide; a headline column cell
 * (`data-fit-cell`) whose text includes `wide` reports 240 px of content — it
 * does not fit its third. Every other element's content fits.
 */
function withForcedCells(wide: string, run: () => void) {
  const proto = HTMLElement.prototype as unknown as Record<string, unknown>;
  Object.defineProperty(proto, "clientWidth", { configurable: true, get: () => 100 });
  Object.defineProperty(proto, "scrollWidth", {
    configurable: true,
    get(this: HTMLElement) {
      return this.hasAttribute("data-fit-cell") && (this.textContent ?? "").includes(wide) ? 240 : 100;
    },
  });
  try {
    run();
  } finally {
    delete proto.clientWidth;
    delete proto.scrollWidth;
  }
}

/** CONSTRUCTED reader setting: the root font at `px`; every other element 16 px. */
function withRootFont(px: number) {
  jest.spyOn(window, "getComputedStyle").mockImplementation(((el: Element) =>
    ({ fontSize: el === document.documentElement ? `${px}px` : "16px" }) as unknown as CSSStyleDeclaration) as typeof window.getComputedStyle);
}

const arrangementNow = () => host.querySelector("[data-soccer-headline] [data-arrangement]")?.getAttribute("data-arrangement");

describe("the three-outcome headline's arrangement (native SoccerThreeOutcomeHeadline11449)", () => {
  it("tries columns then blocks, and an accessibility text size goes straight to blocks", () => {
    expect(soccerHeadlineArrangements(false)).toEqual(["columns", "blocks"]);
    expect(soccerHeadlineArrangements(true)).toEqual(["blocks"]);
    // The fit key follows every printed name and reading, so new content re-measures.
    const renamed = { ...hullBefore.headline, outcomes: hullBefore.headline.outcomes.map((o, i) => (i === 0 ? { ...o, label: "Hull" } : o)) } as typeof hullBefore.headline;
    expect(soccerHeadlineFitContent(renamed)).not.toBe(soccerHeadlineFitContent(hullBefore.headline));
  });

  it("Hull City / Draw / Everton get three aligned columns, each reading under its own full-width heading", () => {
    act(() => root.render(<SoccerMatchHeadline headline={hullBefore.headline} />));
    expect(arrangementNow()).toBe("columns");
    const names = Array.from(host.querySelectorAll("thead th[data-soccer-outcome]"));
    expect(names.map((th) => th.textContent)).toEqual(["Hull City win", "Draw", "Everton win"]);
    expect(names.map((th) => th.getAttribute("data-soccer-outcome"))).toEqual(["home", "draw", "away"]);
    // One heading row, said once, spanning all three columns.
    const heading = host.querySelector('th[colspan="3"]')!;
    expect(heading.textContent).toContain("Current win chance");
    expect(heading.textContent).toContain("Recorded 11 Oct, 4:56 AM");
    expect(text('[data-soccer-reading="0:home"]')).toBe(pct(0.27));
    expect(text('[data-soccer-reading="0:draw"]')).toBe("Draw chance unavailable");
    expect(text('[data-soccer-reading="0:away"]')).toBe("Away win chance unavailable");
    // Each reading names its outcome column and its heading row for a screen reader.
    const cell = host.querySelector('[data-soccer-reading="0:away"]')!;
    const [outcomeId, headingId] = (cell.getAttribute("headers") ?? "").split(" ");
    expect(document.getElementById(outcomeId)?.textContent).toBe("Everton win");
    expect(document.getElementById(headingId)?.textContent).toContain("Current win chance");
  });

  it("during play the primary and comparison rows line up across the three outcomes", () => {
    act(() => root.render(<SoccerMatchHeadline headline={live.headline} />));
    expect(arrangementNow()).toBe("columns");
    expect(Array.from(host.querySelectorAll("[data-soccer-heading]")).map((h) => h.textContent)).toEqual([
      expect.stringContaining("Current win chance"),
      "Opening chance",
    ]);
    expect(text('[data-soccer-reading="0:home"]')).toBe(pct(0.995));
    expect(text('[data-soccer-reading="1:home"]')).toBe(pct(0.4929));
    expect(text('[data-soccer-reading="0:draw"]')).toBe("Draw chance unavailable");
    expect(text('[data-soccer-reading="1:draw"]')).toBe("Draw chance unavailable");
    expect(text('[data-soccer-reading="0:away"]')).toBe("Away win chance unavailable");
    expect(text('[data-soccer-reading="1:away"]')).toBe(pct(0.2278));
  });

  it("a cell whose content does not fit its third steps to labelled blocks before anything clips, at the same figure size", () => {
    act(() => root.render(<SoccerMatchHeadline headline={live.headline} />));
    const columnFigure = host.querySelector('[data-soccer-reading="0:home"] span')!.className;
    act(() => root.unmount());
    root = createRoot(host);
    withForcedCells("Away win chance unavailable", () => {
      act(() => root.render(<SoccerMatchHeadline headline={live.headline} />));
      expect(arrangementNow()).toBe("blocks");
    });
    expect(host.querySelector("table")).toBeNull();
    const blocks = Array.from(host.querySelectorAll("li[data-soccer-outcome]"));
    expect(blocks.map((b) => b.getAttribute("data-soccer-outcome"))).toEqual(["home", "draw", "away"]);
    // Every reading keeps its heading title in its own block; nothing is dropped.
    expect(Array.from(blocks[2].querySelectorAll("dt")).map((dt) => dt.textContent)).toEqual(["Current win chance", "Opening chance"]);
    expect(blocks[2].textContent).toContain("Away win chance unavailable");
    expect(blocks[2].textContent).toContain(pct(0.2278));
    // Type never shrinks: the figure is drawn with the same classes in both arrangements.
    expect(blocks[0].querySelector("dd span")!.className).toBe(columnFigure);
    expect(columnFigure).toContain("text-2xl");
  });

  it("content that fits keeps the columns under the same forced layout", () => {
    withForcedCells("no such words", () => {
      act(() => root.render(<SoccerMatchHeadline headline={hullBefore.headline} />));
      expect(arrangementNow()).toBe("columns");
    });
  });

  it("an accessibility text size draws labelled blocks", () => {
    withRootFont(32);
    act(() => root.render(<SoccerMatchHeadline headline={hullBefore.headline} />));
    expect(arrangementNow()).toBe("blocks");
    expect(Array.from(host.querySelectorAll("li[data-soccer-outcome] > p")).map((p) => p.textContent)).toEqual([
      "Hull City win",
      "Draw",
      "Everton win",
    ]);
  });
});

// ─── The page with REAL inputs ─────────────────────────────────────────────

describe("REAL inputs (no owner admission): the page a reader sees today", () => {
  it("opens on the three outcomes, each a figure or its own words, and the score with its own clock", () => {
    act(() => root.render(<SoccerMatchPage match={live} />));
    expect(host.querySelector("[data-soccer-match]")?.getAttribute("data-soccer-match")).toBe("live");
    expect(arrangementNow()).toBe("columns");
    expect(text('[data-soccer-reading="0:home"]')).toBe(pct(0.995));
    expect(text('[data-soccer-reading="1:away"]')).toBe(pct(0.2278));
    expect(host.querySelector("h2")?.getAttribute("aria-label")).toBe(`${live.header.home} 4, ${live.header.away} 0`);
    expect(text("[data-soccer-context]")).toContain("Score observed");
    expect(text("[data-soccer-context]")).toContain("Match clock unavailable");
  });

  it("draws only the home line, each run its own path, and keys Draw and the away win by their words", () => {
    act(() => root.render(<SoccerMatchPage match={live} />));
    expect(host.querySelectorAll('svg[role="img"] path')).toHaveLength(2);
    expect(text('[data-history-absent="draw"]')).toContain("Draw chance history unavailable");
    expect(text('[data-history-absent="away"]')).toContain("Away win chance history unavailable");
    const details = button("History & source details");
    const region = document.getElementById(details.getAttribute("aria-controls") ?? "");
    expect(region?.hidden).toBe(true);
    click(details);
    expect(region?.textContent).toContain("Gaps remain blank.");
  });

  it("says the stories are unavailable in the stream's own words and still opens All props with exact Details", () => {
    act(() => root.render(<SoccerMatchPage match={live} />));
    expect(text("[data-soccer-stories]")).toContain("No stories in this order. Every original prop is still in All props.");
    expect(host.querySelector("article")).toBeNull();
    const entry = button(`All props · ${live.originals.originals.length}`);
    const list = document.getElementById(entry.getAttribute("aria-controls") ?? "");
    expect(list?.hidden).toBe(true);
    click(entry);
    expect(list?.hidden).toBe(false);
    // One original's exact Details: its market and outcome ids.
    const details = Array.from(list?.querySelectorAll("button") ?? []).find((b) => (b.textContent ?? "").startsWith("Details"));
    expect(details).toBeDefined();
    const panel = document.getElementById(details!.getAttribute("aria-controls") ?? "");
    expect(panel?.hidden).toBe(true);
    click(details!);
    expect(details!.getAttribute("aria-expanded")).toBe("true");
    expect(panel?.hidden).toBe(false);
    expect(panel?.textContent).toContain("Market ID");
    expect(panel?.textContent).toContain("Outcome ID");
  });

  it("with no history response only the chart says so, and offers no history control", () => {
    const missing = page(detail("liveDetail"), null, markets("liveMarkets"), LIVE_NOW);
    act(() => root.render(<SoccerMatchPage match={missing} />));
    expect(host.textContent).toContain("History unavailable");
    expect(host.querySelector('svg[role="img"]')).toBeNull();
    expect(Array.from(host.querySelectorAll("button")).some((b) => b.textContent === "History & source details")).toBe(false);
    expect(text('[data-soccer-reading="0:home"]')).toBe(pct(0.995));
  });

  it("Design parity case 2: Hull–Everton's 2–2 final says Draw, and no settled 0.5 reads as a pre-match chance", () => {
    const draw = page(detail("hullFinalDetail"), null, markets("hullFinalMarkets"), EXACT_FINAL_NOW);
    act(() => root.render(<SoccerMatchPage match={draw} />));
    expect(host.textContent).toContain("Final · Draw");
    const headline = text("[data-soccer-headline]");
    expect(headline).toContain("Pre-match chance");
    expect(headline).toContain(pct(0.225));
    expect(headline).not.toContain(pct(0.5));
  });
});

// ─── The story stream and its five visuals (CONSTRUCTED admissions) ────────

describe("CONSTRUCTED admission: the story stream", () => {
  const admitted = page(detail("liveDetail"), history("liveHistory"), markets("liveMarkets"), LIVE_NOW, C.liveAdmission);

  it("moves between stories only when the reader asks, and runs no interval", () => {
    const interval = jest.spyOn(window, "setInterval");
    const timeout = jest.spyOn(window, "setTimeout");
    act(() => root.render(<SoccerMatchPage match={admitted} />));
    const shown = () => host.querySelector("[data-soccer-card]")?.getAttribute("data-soccer-card");
    expect(shown()).toBe("goals");
    expect(host.textContent).toContain("1 of 3 · Goal milestones");
    expect(host.textContent).toContain("Use Previous or Next to see each story");
    click(button("Next"));
    expect(shown()).toBe("both");
    click(button("Next"));
    expect(shown()).toBe("first");
    click(button("Next"));
    expect(shown()).toBe("goals");
    click(button("Previous"));
    expect(shown()).toBe("first");
    expect(interval).not.toHaveBeenCalled();
    expect(timeout).not.toHaveBeenCalled();
  });
});

describe("GOALS — the milestone profile (TotalMilestonePresentation10868)", () => {
  const admitted = page(detail("liveDetail"), history("liveHistory"), markets("liveMarkets"), LIVE_NOW, C.liveAdmission);
  const goals = admitted.stories.cards[0] as SoccerGoalsCard;
  const card = () => host.querySelector('[data-soccer-card="goals"]')!;
  const chips = () => Array.from(card().querySelectorAll("li > button[aria-pressed]"));

  it("draws a hollow pre-match mark on a stem per milestone and the count as its own rule, never a chance", () => {
    act(() => root.render(<SoccerMatchStories stream={admitted.stories} />));
    expect(card().querySelector("[data-goals-plot]")?.getAttribute("data-goals-plot")).toBe("chart");
    expect(goals.milestones.map((m) => m.quantity)).toEqual([3, 5, 6]);
    const pregame = (id: string) => card().querySelector(`[data-milestone="${id}"] [data-mark="pregame"]`)?.parentElement;
    expect(percentOf(pregame("242143183"), "bottom")).toBeCloseTo(50, 6);
    expect(percentOf(pregame("242143187"), "bottom")).toBeCloseTo(13, 6);
    expect(percentOf(pregame("242765587"), "bottom")).toBeCloseTo(6, 6);
    expect(card().querySelectorAll('[data-mark="stem"]')).toHaveLength(3);
    // Reached (3+) and withheld (5+, 6+) draw no in-game mark: a reached milestone is not 100%.
    expect(card().querySelectorAll('[data-mark="current"]')).toHaveLength(0);
    // The count (4) is a solid rule on the quantity axis (domain 0…6+1), labelled in its own words.
    const rule = card().querySelector('[data-mark="actual-rule"]')!;
    expect(percentOf(rule, "left")).toBeCloseTo((4 / 7) * 100, 6);
    expect(rule.textContent).toBe("4 so far");
    expect(rule.querySelector('[data-mark="pregame"], [data-mark="current"]')).toBeNull();
    // The strip lists every milestone with its own phase reading.
    expect(chips().map((b) => b.querySelector("span")?.textContent)).toEqual(["3+ goals", "5+ goals", "6+ goals"]);
    expect(chips()[0].textContent).toContain("Reached so far");
    expect(chips()[1].textContent).toContain("1 more for 5+");
  });

  it("the selected milestone's readout compares its pre-match chance with its current state, and the choice is held", () => {
    act(() => root.render(<SoccerMatchPage match={admitted} />));
    expect(chips()[0].getAttribute("aria-pressed")).toBe("true");
    const readout = () => card().querySelector("[data-soccer-chosen]")!;
    expect(readout().getAttribute("data-soccer-chosen")).toBe("242143183");
    expect(Array.from(readout().querySelectorAll("dt")).map((dt) => dt.textContent)).toEqual(["Pregame chance", "In-game chance"]);
    expect(Array.from(readout().querySelectorAll("dd")).map((dd) => dd.textContent)).toEqual([pct(0.5), "Reached so far"]);
    const timing = button("3+ goals · chance timing", card());
    const region = document.getElementById(timing.getAttribute("aria-controls") ?? "");
    expect(region?.hidden).toBe(true);
    click(timing);
    expect(region?.textContent).toContain("Pregame chance: saved before kickoff");
    expect(region?.textContent).toContain("Actual so far: Reached so far");
    click(chips()[1]);
    expect(chips()[1].getAttribute("aria-pressed")).toBe("true");
    expect(Array.from(readout().querySelectorAll("dd")).map((dd) => dd.textContent)).toEqual([pct(0.13), "No recent probability update"]);
    // The chosen milestone's marks are emphasised; the others are not.
    expect(card().querySelector('[data-milestone="242143187"] [data-mark="pregame"]')?.className).toContain("ring-2");
    expect(card().querySelector('[data-milestone="242143183"] [data-mark="pregame"]')?.className).not.toContain("ring-2");
    click(button("Next"));
    click(button("Previous"));
    expect(chips()[1].getAttribute("aria-pressed")).toBe("true");
  });

  it("CONSTRUCTED recorded in-game chance: a filled mark at that chance, beside the hollow pre-match one", () => {
    const edited = clone(admitted.stories);
    const five = (edited.cards[0] as SoccerGoalsCard).milestones[1];
    five.current = { kind: "recorded", observation: { probability: 0.2, text: pct(0.2), clock: null, detail: "CONSTRUCTED" } };
    act(() => root.render(<SoccerMatchStories stream={edited} />));
    const marks = card().querySelectorAll('[data-milestone="242143187"] [data-mark="current"]');
    expect(marks).toHaveLength(1);
    expect(percentOf(marks[0].parentElement, "bottom")).toBeCloseTo(20, 6);
    expect(marks[0].className).not.toContain("bg-surface-card");
    expect((card().querySelector('[data-milestone="242143187"] [data-mark="pregame"]') as HTMLElement).className).toContain("bg-surface-card");
  });

  it("before kickoff with no usable chance: no mark at all, the strip of quantities, each milestone in its own words", () => {
    const before = page(detail("hullDetail"), history("hullHistory"), markets("hullExactMarkets"), EXACT_PRE_NOW, HULL_BEFORE_ADMISSION);
    act(() => root.render(<SoccerMatchStories stream={before.stories} />));
    expect(card().querySelector("[data-goals-plot]")?.getAttribute("data-goals-plot")).toBe("strip");
    expect(card().querySelectorAll("[data-mark]")).toHaveLength(0);
    expect(card().textContent).not.toContain("0%");
    expect(chips().every((b) => (b.textContent ?? "").includes("No recent probability update"))).toBe(true);
  });
});

describe("BOTH — the ring and the team tiles (BothTeamsScorePresentation10868)", () => {
  const RING_C = 2 * Math.PI * 30;
  const livePage = page(detail("liveDetail"), history("liveHistory"), markets("liveMarkets"), LIVE_NOW, C.liveAdmission);
  const finalPage = page(detail("finalDetail"), history("finalHistory"), markets("finalMarkets"), FINAL_NOW, C.liveAdmission);
  const card = () => host.querySelector('[data-soccer-card="both"]')!;

  it("during play the ring holds the chosen outcome's own pre-match chance; the tiles keep each outcome's own figure", () => {
    act(() => root.render(<SoccerMatchPage match={livePage} />));
    click(button("Next"));
    const arc = () => card().querySelector('[data-mark="ring-arc"]');
    expect(arc()?.getAttribute("stroke-dasharray")).toBe(`${(RING_C * 0.55).toFixed(2)} ${RING_C.toFixed(2)}`);
    expect(card().querySelector("[data-ring]")?.getAttribute("aria-label")).toBe(`Yes · Pregame chance: ${pct(0.55)}`);
    // Each team's goals: observed state, beside the ring.
    expect(card().textContent).toContain("has scored");
    expect(card().textContent).toContain("yet to score");
    // Pregame and current side by side; no result during play.
    const readout = card().querySelector("[data-soccer-chosen]")!;
    expect(Array.from(readout.querySelectorAll("dd")).map((dd) => dd.textContent)).toEqual([pct(0.55), pct(0.49)]);
    expect(card().querySelector("[data-result]")).toBeNull();
    // No's own figure, never 1 − Yes.
    const no = button("No", card());
    expect(no.textContent).toContain(pct(0.455));
    click(no);
    expect(arc()?.getAttribute("stroke-dasharray")).toBe(`${(RING_C * 0.455).toFixed(2)} ${RING_C.toFixed(2)}`);
  });

  it("after the final a missing pre-match chance draws no arc, and each result is its own badge, never a full ring", () => {
    act(() => root.render(<SoccerMatchPage match={finalPage} />));
    expect(host.querySelector("[data-soccer-card]")?.getAttribute("data-soccer-card")).toBe("both");
    expect(card().querySelector("[data-ring]")?.getAttribute("data-ring")).toBe("empty");
    expect(card().querySelector('[data-mark="ring-arc"]')).toBeNull();
    expect(card().textContent).toContain("Pre-match chance unavailable");
    expect(text("[data-soccer-chosen] [data-result]", card())).toBe(PROP_MISS_LABEL);
    expect(card().querySelector("[data-soccer-chosen] [data-result]")?.getAttribute("data-result")).toBe("lost");
    click(button("No", card()));
    expect(text("[data-soccer-chosen] [data-result]", card())).toBe(PROP_HIT_LABEL);
    expect(card().querySelector('[data-mark="ring-arc"]')).toBeNull();
  });
});

describe("FIRST — the lollipop comparison (FirstScorerComparisonPresentation10868)", () => {
  const livePage = page(detail("liveDetail"), history("liveHistory"), markets("liveMarkets"), LIVE_NOW, C.liveAdmission);
  const finalPage = page(detail("finalDetail"), history("finalHistory"), markets("finalMarkets"), FINAL_NOW, C.liveAdmission);
  const card = () => host.querySelector('[data-soccer-card="first"]')!;

  it("draws every outcome's pre-match chance on one shared scale, with each row's phase reading under its track", () => {
    act(() => root.render(<SoccerMatchPage match={livePage} />));
    click(button("Previous"));
    const dot = (id: string) => card().querySelector(`[data-first-row="${id}"] [data-mark="pregame"]`)?.parentElement;
    expect(percentOf(dot("244237963"), "left")).toBeCloseTo(57, 6);
    expect(percentOf(dot("244237965"), "left")).toBeCloseTo(6.5, 6);
    expect(percentOf(dot("244237964"), "left")).toBeCloseTo(33.5, 6);
    expect(percentOf(card().querySelector('[data-first-row="244237963"] [data-mark="stem"]'), "width")).toBeCloseTo(57, 6);
    expect(text('[data-first-row="244237963"]', card())).toContain(`Current chance: ${pct(0.999)}`);
    expect(text('[data-first-row="244237964"]', card())).toContain("Current chance: No recent probability update");
    // The selected comparison sits above the plot; choosing a row changes it.
    expect(card().querySelector("[data-soccer-chosen]")?.getAttribute("data-soccer-chosen")).toBe("244237963");
    click(button("Albacete", card()));
    expect(card().querySelector("[data-soccer-chosen]")?.getAttribute("data-soccer-chosen")).toBe("244237964");
    expect(card().querySelector('[data-first-row="244237964"] [data-mark="pregame"]')?.className).toContain("ring-2");
    // Score checkpoints are their own section, outside the plot.
    const checkpoints = card().querySelector("[data-first-checkpoints]")!;
    expect(checkpoints).not.toBeNull();
    expect(card().querySelector("[data-first-plot] [data-first-checkpoints]")).toBeNull();
  });

  it("after the final a missing pre-match chance draws no mark, and each row's result is its own badge", () => {
    act(() => root.render(<SoccerMatchPage match={finalPage} />));
    click(button("Next"));
    expect(card().querySelectorAll('[data-mark="pregame"]')).toHaveLength(0);
    expect(card().querySelectorAll('[data-mark="stem"]')).toHaveLength(0);
    expect(card().querySelector('[data-first-row="244237963"] [data-result]')?.getAttribute("data-result")).toBe("won");
    expect(text('[data-first-row="244237963"] [data-result]', card())).toBe(PROP_HIT_LABEL);
    expect(text('[data-first-row="244237965"] [data-result]', card())).toBe(PROP_MISS_LABEL);
    expect(card().querySelector("[data-first-checkpoints]")).toBeNull();
  });
});

describe("HALVES — the dot plot (PeriodOutcomeComparisonPresentation10868)", () => {
  const livePage = page(detail("liveDetail"), history("liveHistory"), markets("liveMarkets"), LIVE_NOW, C.liveAdmission, { halvesAdmission: "explicit" });
  const finalPage = page(detail("finalDetail"), history("finalHistory"), markets("finalMarkets"), FINAL_NOW, C.liveAdmission);
  const card = () => host.querySelector('[data-soccer-card="halves"]')!;
  const halvesStream = (p: SoccerMatchViewModel) => oneCard(p.stories.cards.find((c) => c.id === "halves")!);

  it("each outcome's pre-match chance per half on one scale, lines joining its halves, and no table as the display", () => {
    act(() => root.render(<SoccerMatchStories stream={halvesStream(livePage)} />));
    expect(card().querySelector("table")).toBeNull();
    const point = (key: string) => card().querySelector(`[data-half-point="${key}"]`);
    expect(percentOf(point("home:first"), "bottom")).toBeCloseTo(37.5, 6);
    expect(percentOf(point("home:second"), "bottom")).toBeCloseTo(43, 6);
    expect(percentOf(point("draw:first"), "bottom")).toBeCloseTo(42.5, 6);
    expect(percentOf(point("away:second"), "bottom")).toBeCloseTo(23, 6);
    expect(card().querySelectorAll("[data-half-point]")).toHaveLength(6);
    const lines = Array.from(card().querySelectorAll('[data-mark="half-line"]'));
    expect(lines).toHaveLength(3);
    expect([Number(lines[0].getAttribute("y1")), Number(lines[0].getAttribute("y2"))]).toEqual([62.5, 57]);
    expect(card().textContent).toContain("Lines compare halves, not changes over time.");
  });

  it("choosing a series shows its tile per half; the others dim", () => {
    act(() => root.render(<SoccerMatchStories stream={halvesStream(livePage)} />));
    const chosen = () => card().querySelector("[data-soccer-chosen]")!;
    expect(chosen().getAttribute("data-soccer-chosen")).toBe("home");
    click(button("Draw", card()));
    expect(chosen().getAttribute("data-soccer-chosen")).toBe("draw");
    expect(button("Draw", card()).getAttribute("aria-pressed")).toBe("true");
    const tiles = Array.from(chosen().querySelectorAll("li"));
    expect(tiles.map((t) => t.querySelector("p")?.textContent)).toEqual(["First half", "Second half"]);
    expect(tiles[0].textContent).toContain(pct(0.425));
    expect(tiles[0].textContent).toContain("In-play chance unavailable");
    expect(card().querySelector('[data-half-point="home:first"] svg')?.getAttribute("class")).toContain("opacity-40");
    expect(card().querySelector('[data-half-point="draw:first"] svg')?.getAttribute("class")).not.toContain("opacity-40");
  });

  it("CONSTRUCTED missing half chance: no point there and the line breaks; no zero is drawn", () => {
    const edited = clone(halvesStream(livePage));
    (edited.cards[0] as SoccerHalvesCard).series[0].cells[0].pregame = { kind: "missing", words: "Pre-match chance unavailable" };
    act(() => root.render(<SoccerMatchStories stream={edited} />));
    expect(card().querySelector('[data-half-point="home:first"]')).toBeNull();
    expect(card().querySelectorAll("[data-half-point]")).toHaveLength(5);
    expect(card().querySelectorAll('[data-mark="half-line"]')).toHaveLength(2);
  });

  it("after the final no pre-match chance is drawn and each half's result is its own badge", () => {
    act(() => root.render(<SoccerMatchStories stream={halvesStream(finalPage)} />));
    expect(card().querySelectorAll("[data-half-point]")).toHaveLength(0);
    expect(card().querySelectorAll('[data-mark="half-line"]')).toHaveLength(0);
    expect(card().textContent).toContain(`Final results · ${finalPage.header.home}`);
    const results = Array.from(card().querySelectorAll("[data-soccer-chosen] [data-result]"));
    expect(results.map((r) => r.textContent)).toEqual([PROP_HIT_LABEL, PROP_HIT_LABEL]);
    click(button("Draw", card()));
    expect(Array.from(card().querySelectorAll("[data-soccer-chosen] [data-result]")).map((r) => r.textContent)).toEqual([PROP_MISS_LABEL, PROP_MISS_LABEL]);
  });
});

describe("EXACT — the heat map (ExactScoreMapPresentation10868)", () => {
  const before = page(detail("hullDetail"), history("hullHistory"), markets("hullExactMarkets"), EXACT_PRE_NOW, HULL_BEFORE_ADMISSION);
  const exact = before.stories.cards.find((c) => c.id === "exact") as SoccerExactCard;
  const card = () => host.querySelector('[data-soccer-card="exact"]')!;
  const cell = (id: string) => card().querySelector(`td[data-cell="${id}"]`)!;

  it("shades each listed score by its own pre-match chance on the owner's scale, with no figure in the cells", () => {
    act(() => root.render(<SoccerMatchStories stream={oneCard(exact)} />));
    const full = exact.scopes[0];
    expect(full.scale?.upper).toBe(0.1);
    expect(card().querySelectorAll("td button")).toHaveLength(36);
    expect(card().querySelectorAll('[data-fill="intensity"]').length).toBeGreaterThanOrEqual(36);
    const grid = full.originals.filter((o) => o.placement.kind === "grid");
    for (const o of grid) {
      const p = o.pregame.kind === "value" ? o.pregame.observation.probability : NaN;
      const fill = cell(o.id).querySelector('[data-fill="intensity"]') as HTMLElement;
      expect(Number(fill.getAttribute("data-fraction"))).toBeCloseTo(p / 0.1, 4);
      expect(Number(fill.style.opacity)).toBeCloseTo(0.55 * (p / 0.1), 4);
      expect(cell(o.id).querySelector("button")?.textContent).toBe("");
    }
    // Heat follows the chances: 1–1 (9.52%) is darker than 0–0 (5.99%), darker than 4–3 (0.14%).
    const opacity = (id: string) => Number((cell(id).querySelector('[data-fill="intensity"]') as HTMLElement).style.opacity);
    expect(opacity("238846931")).toBeGreaterThan(opacity("238846934"));
    expect(opacity("238846934")).toBeGreaterThan(opacity("242779549"));
    expect(cell("238846934").querySelector("button")?.getAttribute("aria-label")).toBe(`Hull City AFC 0 - 0 Everton FC. Pre-match chance: ${pct(0.0599)}`);
    expect(text("[data-exact-legend]")).toContain(`${pct(0)}`);
    expect(text("[data-exact-legend]")).toContain(pct(0.05));
    expect(text("[data-exact-legend]")).toContain(pct(0.1));
    // The non-grid original is its own named choice.
    expect(button("Any Other Score", card()).textContent).toContain(pct(0.0088));
  });

  it("the selected score gets corner marks and a legible readout; until then the map says to choose", () => {
    act(() => root.render(<SoccerMatchStories stream={oneCard(exact)} />));
    expect(card().textContent).toContain(EXACT_WORDS.noSelection);
    expect(card().querySelectorAll('td [data-mark="selected"]')).toHaveLength(0);
    click(cell("238846934").querySelector("button")!);
    expect(host.querySelector("[data-soccer-exact-chosen]")?.getAttribute("data-soccer-exact-chosen")).toBe("238846934");
    expect(cell("238846934").querySelectorAll('[data-mark="selected"]')).toHaveLength(1);
    expect(card().querySelectorAll('td [data-mark="selected"]')).toHaveLength(1);
    const readout = host.querySelector("[data-soccer-exact-chosen]")!;
    expect(readout.textContent).toContain("Hull City AFC 0 - 0 Everton FC");
    expect(Array.from(readout.querySelectorAll("dd")).map((dd) => dd.textContent)).toEqual([pct(0.0599)]);
    // The first-half scope keeps its own identities and its own scale; 2–2 is not listed there.
    click(button("First half", card()));
    expect(card().querySelectorAll("td button")).toHaveLength(8);
    expect(host.querySelector("[data-soccer-exact-chosen]")).toBeNull();
    const unlisted = card().querySelectorAll('td[data-cell="notListed"]');
    expect(unlisted).toHaveLength(1);
    expect(unlisted[0].className).toContain("border-dashed");
    expect(unlisted[0].querySelector("button, [data-fill]")).toBeNull();
    expect(unlisted[0].textContent).toBe(EXACT_WORDS.notListed);
    expect(text("[data-exact-legend]")).toContain(EXACT_WORDS.legend.notListed);
    expect(text("[data-exact-legend]")).toContain(pct(0.4));
  });

  it("CONSTRUCTED off-scale and missing chances: hatched, never clamped; blank with its own mark, never a zero shade", () => {
    const edited = clone(exact);
    const full = edited.scopes[0];
    const oneOne = full.originals.find((o) => o.id === "238846931")!;
    oneOne.pregame = { kind: "value", observation: { probability: 0.15, text: pct(0.15), clock: null, detail: "CONSTRUCTED" } };
    full.originals.find((o) => o.id === "238846934")!.pregame = { kind: "missing", words: "Pre-match chance unavailable" };
    expect(exactCellFill(oneOne.pregame, full.scale)).toEqual({ kind: "offScale" });
    act(() => root.render(<SoccerMatchStories stream={oneCard(edited)} />));
    expect(cell("238846931").querySelector('[data-fill="offScale"]')).not.toBeNull();
    expect(cell("238846931").querySelector('[data-fill="intensity"]')).toBeNull();
    expect(cell("238846934").querySelector("[data-fill]")).toBeNull();
    expect(cell("238846934").querySelector("button")?.textContent).toBe(EXACT_WORDS.unavailableMark);
    expect(cell("238846934").querySelector("button")?.getAttribute("aria-label")).toContain("Pre-match chance unavailable");
    expect(text("[data-exact-legend]")).toContain(EXACT_WORDS.legend.offScale);
    expect(text("[data-exact-legend]")).toContain(EXACT_WORDS.legend.unavailable);
  });

  it("CONSTRUCTED unusable scale: no cell is shaded and the map says so", () => {
    const edited = clone(exact);
    edited.scopes[0].scale = null;
    act(() => root.render(<SoccerMatchStories stream={oneCard(edited)} />));
    expect(card().querySelectorAll("td [data-fill]")).toHaveLength(0);
    expect(card().textContent).toContain(EXACT_WORDS.scaleUnavailable);
  });

  it("Design parity case 2 — Hull–Everton's 2–2 final: the confirmed result is outlined, never shaded as a chance", () => {
    const event = detail("hullFinalDetail");
    const settled = soccerExactCard(event, markets("hullFinalMarkets"), HULL_BEFORE_ADMISSION, soccerMatchPhase(event, EXACT_FINAL_NOW), soccerNames(event), EXACT_FINAL_NOW)!;
    act(() => root.render(<SoccerMatchStories stream={oneCard(settled)} />));
    const draw = cell("237459055");
    expect(draw.querySelector("button")?.hasAttribute("data-confirmed")).toBe(true);
    expect(draw.querySelector("button")?.className).toContain("border-text-primary");
    expect(card().querySelectorAll("button[data-confirmed]")).toHaveLength(1);
    // No pre-match chance on the final: nothing is shaded, the result included.
    expect(card().querySelectorAll("td [data-fill]")).toHaveLength(0);
    expect(draw.querySelector("button")?.getAttribute("aria-label")).toContain(`Final result: ${PROP_HIT_LABEL}`);
    // The actual score is its own line, never matched onto the grid.
    const names = soccerNames(event);
    expect(text("[data-exact-actual]")).toBe(`${EXACT_WORDS.finalScore}: ${names.home} 2–2 ${names.away}`);
    expect(text("[data-exact-legend]")).toContain(EXACT_WORDS.legend.result);
  });
});

// ─── Held selections across refresh (Design correction on 8c2ab49c) ─────────
//
// Native: a choice resolves by its exact id, exactly once; a withdrawn or
// duplicated id is unavailable with no substitute, and the held id is kept so
// the same identity returns (`TotalMilestoneInput10868.selection`,
// `ExactScoreMapInput10868.scopeSelection` / `originalSelection`,
// ExactScoreMapPresentation10868.swift:384-405). Every refresh below re-renders
// the SAME mounted stream with a new payload — no key, no remount — exactly as
// page.tsx would on a poll. Each payload edit is CONSTRUCTED and says so.

describe("held selections: exact id, exactly once, no substitute, kept across refresh", () => {
  const livePage = page(detail("liveDetail"), history("liveHistory"), markets("liveMarkets"), LIVE_NOW, C.liveAdmission, { halvesAdmission: "explicit" });
  const finalPage = page(detail("finalDetail"), history("finalHistory"), markets("finalMarkets"), FINAL_NOW, C.liveAdmission);
  const hullPage = page(detail("hullDetail"), history("hullHistory"), markets("hullExactMarkets"), EXACT_PRE_NOW, HULL_BEFORE_ADMISSION);

  const show = (stream: SoccerStoryStream) => act(() => root.render(<SoccerMatchStories stream={stream} />));
  /** A refresh: the same stream with one card's payload edited (CONSTRUCTED at each call site). */
  function edited<T extends SoccerStoryCard>(stream: SoccerStoryStream, id: T["id"], edit: (card: T) => void): SoccerStoryStream {
    const next = clone(stream);
    edit(next.cards.find((c) => c.id === id) as T);
    return next;
  }
  const card = (id: string) => host.querySelector(`[data-soccer-card="${id}"]`)!;
  const notice = (id: string) => card(id).querySelector("[data-soccer-selection-unavailable]");
  const readout = (id: string) => card(id).querySelector("[data-soccer-chosen], [data-soccer-exact-chosen]");
  const pressed = (id: string) => Array.from(card(id).querySelectorAll('button[aria-pressed="true"]'));
  const timingButtons = (id: string) => Array.from(card(id).querySelectorAll("button[aria-controls]"));
  const chip = (id: string, label: string) => button(label, card(id));
  const goalChip = (label: string) => Array.from(card("goals").querySelectorAll<HTMLButtonElement>("li > button")).find((b) => b.querySelector("span")?.textContent === label)!;

  describe("GOALS milestones", () => {
    it("a removed held milestone says so, shows no other milestone, and the reader can choose another", () => {
      show(livePage.stories);
      click(goalChip("5+ goals"));
      expect(readout("goals")?.getAttribute("data-soccer-chosen")).toBe("242143187");
      // CONSTRUCTED refresh: the 5+ market is withdrawn.
      show(edited<SoccerGoalsCard>(livePage.stories, "goals", (c) => (c.milestones = c.milestones.filter((m) => m.id !== "242143187"))));
      expect(notice("goals")?.textContent).toBe("Selected milestone unavailable.");
      expect(notice("goals")?.getAttribute("data-soccer-selection-unavailable")).toBe("missing");
      // No substitute: not the default (3+), not a neighbour — no readout, timing, pressed chip or emphasis.
      expect(readout("goals")).toBeNull();
      expect(timingButtons("goals")).toHaveLength(0);
      expect(pressed("goals")).toHaveLength(0);
      expect(card("goals").querySelector(".ring-2")).toBeNull();
      expect(card("goals").textContent).not.toContain("Pregame chance");
      // The other milestones stay choosable; a deliberate choice resolves.
      click(goalChip("6+ goals"));
      expect(readout("goals")?.getAttribute("data-soccer-chosen")).toBe("242765587");
      expect(notice("goals")).toBeNull();
    });

    it("the same identity returns to the held milestone without the reader choosing again", () => {
      show(livePage.stories);
      click(goalChip("5+ goals"));
      // CONSTRUCTED refresh: withdrawn, then served again with the same id.
      show(edited<SoccerGoalsCard>(livePage.stories, "goals", (c) => (c.milestones = c.milestones.filter((m) => m.id !== "242143187"))));
      expect(readout("goals")).toBeNull();
      show(livePage.stories);
      expect(readout("goals")?.getAttribute("data-soccer-chosen")).toBe("242143187");
      expect(goalChip("5+ goals").getAttribute("aria-pressed")).toBe("true");
    });

    it("unchanged values under a changed id are not the held milestone: unavailable, no substitute", () => {
      show(livePage.stories);
      click(goalChip("5+ goals"));
      // CONSTRUCTED refresh: the 5+ row re-served under a new id, every value identical.
      show(edited<SoccerGoalsCard>(livePage.stories, "goals", (c) => (c.milestones[1].id = "242143187-reissued")));
      expect(notice("goals")?.textContent).toBe("Selected milestone unavailable.");
      expect(readout("goals")).toBeNull();
      expect(goalChip("5+ goals").getAttribute("aria-pressed")).toBe("false");
      expect(goalChip("5+ goals").disabled).toBe(false);
    });

    it("a held id now carried by two milestones picks neither; both offer no action", () => {
      show(livePage.stories);
      click(goalChip("5+ goals"));
      // CONSTRUCTED refresh: the 6+ row also carries the 5+ id.
      show(edited<SoccerGoalsCard>(livePage.stories, "goals", (c) => (c.milestones[2].id = "242143187")));
      expect(notice("goals")?.getAttribute("data-soccer-selection-unavailable")).toBe("duplicate");
      expect(readout("goals")).toBeNull();
      expect(goalChip("5+ goals").disabled).toBe(true);
      expect(goalChip("6+ goals").disabled).toBe(true);
      expect(goalChip("3+ goals").disabled).toBe(false);
      expect(pressed("goals")).toHaveLength(0);
    });

    it("a normal refresh keeps the held milestone and shows its new values", () => {
      show(livePage.stories);
      click(goalChip("6+ goals"));
      // CONSTRUCTED refresh: the 6+ pre-match pin re-read at a new value, same id.
      show(
        edited<SoccerGoalsCard>(livePage.stories, "goals", (c) => {
          c.milestones[2].pregame = { kind: "value", observation: { probability: 0.08, text: pct(0.08), clock: null, detail: "CONSTRUCTED" } };
        }),
      );
      expect(readout("goals")?.getAttribute("data-soccer-chosen")).toBe("242765587");
      expect(Array.from(readout("goals")!.querySelectorAll("dd")).map((dd) => dd.textContent)[0]).toBe(pct(0.08));
    });
  });

  describe("BOTH, FIRST and HALVES outcomes", () => {
    it("both teams: a removed held outcome empties the ring with its words; the other outcome is a deliberate choice", () => {
      show(livePage.stories);
      click(button("Next"));
      click(chip("both", "No"));
      expect(readout("both")?.getAttribute("data-soccer-chosen")).toBe("242143190");
      // CONSTRUCTED refresh: the No outcome is withdrawn.
      show(edited<SoccerBothCard>(livePage.stories, "both", (c) => (c.outcomes = c.outcomes.filter((o) => o.id !== "242143190"))));
      expect(card("both").querySelector('[data-mark="ring-arc"]')).toBeNull();
      expect(card("both").querySelector("[data-ring]")?.getAttribute("aria-label")).toBe("Selected outcome unavailable.");
      expect(notice("both")?.textContent).toBe("Selected outcome unavailable.");
      expect(readout("both")).toBeNull();
      expect(card("both").textContent).not.toContain("Pregame chance");
      expect(pressed("both")).toHaveLength(0);
      click(chip("both", "Yes"));
      expect(readout("both")?.getAttribute("data-soccer-chosen")).toBe("242143189");
      expect(card("both").querySelector('[data-mark="ring-arc"]')).not.toBeNull();
    });

    it("first team: a removed held outcome shows no other outcome's readout or timing, and returns when served again", () => {
      show(livePage.stories);
      click(button("Next"));
      click(button("Next"));
      click(chip("first", "Albacete"));
      const without = edited<SoccerFirstCard>(livePage.stories, "first", (c) => (c.rows = c.rows.filter((r) => r.id !== "244237964")));
      // CONSTRUCTED refresh: withdrawn.
      show(without);
      expect(notice("first")?.textContent).toBe("Selected outcome unavailable.");
      expect(readout("first")).toBeNull();
      expect(timingButtons("first")).toHaveLength(0);
      expect(card("first").querySelector(".ring-2")).toBeNull();
      // CONSTRUCTED refresh: served again with the same id.
      show(livePage.stories);
      expect(readout("first")?.getAttribute("data-soccer-chosen")).toBe("244237964");
    });

    it("first team, no explicit choice: a duplicated default picks neither row, never the first", () => {
      // CONSTRUCTED payload: Neither re-served under the default (Valladolid) id.
      show(edited<SoccerFirstCard>(livePage.stories, "first", (c) => (c.rows[1].id = c.rows[0].id)));
      click(button("Next"));
      click(button("Next"));
      expect(notice("first")?.getAttribute("data-soccer-selection-unavailable")).toBe("duplicate");
      expect(readout("first")).toBeNull();
      expect(button("Real Valladolid CF", card("first")).disabled).toBe(true);
      expect(button("Albacete", card("first")).disabled).toBe(false);
    });

    it("half by half: a removed held series dims nothing and shows no tiles; another series is a deliberate choice", () => {
      const halves = oneCard(livePage.stories.cards.find((c) => c.id === "halves")!);
      show(halves);
      click(chip("halves", "Draw"));
      expect(readout("halves")?.getAttribute("data-soccer-chosen")).toBe("draw");
      // CONSTRUCTED refresh: the Draw series is withdrawn.
      show(edited<SoccerHalvesCard>(halves, "halves", (c) => (c.series = c.series.filter((s) => s.id !== "draw"))));
      expect(notice("halves")?.textContent).toBe("Selected outcome unavailable.");
      expect(readout("halves")).toBeNull();
      expect(card("halves").querySelector(".opacity-40")).toBeNull();
      expect(pressed("halves")).toHaveLength(0);
      click(chip("halves", livePage.header.away));
      expect(readout("halves")?.getAttribute("data-soccer-chosen")).toBe("away");
    });
  });

  describe("EXACT scopes and scores", () => {
    const exact = () => oneCard(hullPage.stories.cards.find((c) => c.id === "exact")!);
    const cell = (id: string) => card("exact").querySelector(`td[data-cell="${id}"] button`) as HTMLButtonElement;

    it("a removed held scope says so, draws no map, and keeps the scope choices reachable", () => {
      show(exact());
      click(chip("exact", "First half"));
      expect(card("exact").querySelector("[data-exact-map]")?.getAttribute("data-exact-map")).toBe("first");
      // CONSTRUCTED refresh: the first-half market is withdrawn; one scope is left.
      show(edited<SoccerExactCard>(exact(), "exact", (c) => (c.scopes = c.scopes.filter((s) => s.id !== "first"))));
      expect(notice("exact")?.textContent).toBe("Selected market unavailable.");
      expect(card("exact").querySelector("[data-exact-map]")).toBeNull();
      expect(readout("exact")).toBeNull();
      const full = chip("exact", "Full match");
      expect(full.getAttribute("aria-pressed")).toBe("false");
      click(full);
      expect(card("exact").querySelector("[data-exact-map]")?.getAttribute("data-exact-map")).toBe("full");
    });

    it("duplicated scope ids resolve nobody, with or without an explicit choice", () => {
      // CONSTRUCTED payload: both scopes carry the default id.
      const twice = edited<SoccerExactCard>(exact(), "exact", (c) => (c.scopes[1].id = "full"));
      show(twice);
      expect(notice("exact")?.getAttribute("data-soccer-selection-unavailable")).toBe("duplicate");
      expect(card("exact").querySelector("[data-exact-map]")).toBeNull();
      expect(chip("exact", "Full match").disabled).toBe(true);
      expect(chip("exact", "First half").disabled).toBe(true);
    });

    it("a removed held score says so with no corner marks or readout; another score is a deliberate choice; the same identity returns", () => {
      show(exact());
      click(cell("238846934"));
      expect(readout("exact")?.getAttribute("data-soccer-exact-chosen")).toBe("238846934");
      // CONSTRUCTED refresh: the 0–0 market is withdrawn from the full match.
      const without = edited<SoccerExactCard>(exact(), "exact", (c) => (c.scopes[0].originals = c.scopes[0].originals.filter((o) => o.id !== "238846934")));
      show(without);
      expect(notice("exact")?.textContent).toBe("Selected score unavailable.");
      expect(readout("exact")).toBeNull();
      expect(card("exact").querySelectorAll('td [data-mark="selected"]')).toHaveLength(0);
      expect(card("exact").textContent).not.toContain(EXACT_WORDS.noSelection);
      // CONSTRUCTED refresh: served again — the held score is back without a new choice.
      show(exact());
      expect(readout("exact")?.getAttribute("data-soccer-exact-chosen")).toBe("238846934");
      // Withdrawn again, and this time the reader chooses 1–1 deliberately; the return of 0–0 does not retake it.
      show(without);
      click(cell("238846931"));
      show(exact());
      expect(readout("exact")?.getAttribute("data-soccer-exact-chosen")).toBe("238846931");
    });

    it("a held score id now carried by two listed scores picks neither; both offer no action", () => {
      show(exact());
      click(cell("238846934"));
      // CONSTRUCTED refresh: the 1–1 original also carries the 0–0 id.
      show(edited<SoccerExactCard>(exact(), "exact", (c) => (c.scopes[0].originals.find((o) => o.id === "238846931")!.id = "238846934")));
      expect(notice("exact")?.getAttribute("data-soccer-selection-unavailable")).toBe("duplicate");
      expect(card("exact").querySelectorAll('td [data-mark="selected"]')).toHaveLength(0);
      const shared = Array.from(card("exact").querySelectorAll('td[data-cell="238846934"] button')) as HTMLButtonElement[];
      expect(shared).toHaveLength(2);
      expect(shared.every((b) => b.disabled)).toBe(true);
    });

    it("CONSTRUCTED shared coordinate: the cell is ambiguous, not 'not listed', and each original is a named choice", () => {
      // CONSTRUCTED payload: the 1–1 original placed on 0–0's coordinate.
      show(
        edited<SoccerExactCard>(exact(), "exact", (c) => {
          c.scopes[0].originals.find((o) => o.id === "238846931")!.placement = { kind: "grid", home: 0, away: 0 };
        }),
      );
      const ambiguous = card("exact").querySelector('td[data-cell="ambiguous"]')!;
      expect(ambiguous.textContent).toBe(EXACT_WORDS.unavailableMark);
      expect(ambiguous.className).not.toContain("border-dashed");
      expect(ambiguous.querySelector("button")).toBeNull();
      expect(button("Hull City AFC 0 - 0 Everton FC", card("exact"))).toBeDefined();
      click(button("Hull City AFC 1 - 1 Everton FC", card("exact")));
      expect(readout("exact")?.getAttribute("data-soccer-exact-chosen")).toBe("238846931");
    });
  });

  describe("the reading scope: a refresh keeps choices; a new event or phase is a new reading", () => {
    it("CONSTRUCTED another event's stream with the same cards starts with the owner's defaults, no unavailable notice", () => {
      show(livePage.stories);
      click(goalChip("6+ goals"));
      // The same event's refresh keeps the choice.
      show(clone(livePage.stories));
      expect(readout("goals")?.getAttribute("data-soccer-chosen")).toBe("242765587");
      // CONSTRUCTED: the same cards under another event's scope.
      show({ ...clone(livePage.stories), scope: "soccer:999999:live" });
      expect(readout("goals")?.getAttribute("data-soccer-chosen")).toBe("242143183");
      expect(notice("goals")).toBeNull();
    });

    it("kickoff-to-final is a new reading: the shown story and every choice start again", () => {
      expect(livePage.stories.scope).not.toBe(finalPage.stories.scope);
      show(livePage.stories);
      click(button("Next"));
      click(chip("both", "No"));
      click(button("Next"));
      expect(host.querySelector("[data-soccer-card]")?.getAttribute("data-soccer-card")).toBe("first");
      // The final's own stream (same event, new phase): first story, the owner's default outcome.
      show(finalPage.stories);
      expect(host.querySelector("[data-soccer-card]")?.getAttribute("data-soccer-card")).toBe("both");
      expect(readout("both")?.getAttribute("data-soccer-chosen")).toBe("242143189");
      expect(notice("both")).toBeNull();
    });
  });
});
