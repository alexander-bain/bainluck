/** @jest-environment jsdom */
/**
 * #10868 R-H1 — the shared paired-history chart's optional `layout`
 * (`HockeyJourneyHistoryChart`): "inline" (the default, every page caller)
 * draws the 230 px plot exactly as before; "expanded" draws a 360 px plot for
 * a full-size reader (the web soccer chart's convention). Only the vertical
 * extent of the plot changes; everything else is the inline chart's.
 *
 * SHIP: a baseball fan's Full chart can give the probability journey real
 * vertical room while the on-page win-probability anchor keeps its existing
 * size and behavior. No caller passes "expanded" yet (the Full chart reader is
 * a later increment); these tests drive the ACTUAL component directly.
 *
 * INPUTS, labelled per test:
 *   - RETAINED — `../lib/hockeyJourney10868.fixtures.json` (Wild–Bruins
 *     15169793 final, through the accepted `buildHockeyJourney`) and
 *     `../lib/mlbGame10868.fixtures.json` (White Sox at Astros 15321836 final,
 *     through the accepted `buildMlbGame`): real positive plots with real runs,
 *     gaps and (hockey) period guides. Neither fixture is edited.
 *   - CONSTRUCTED — the frame width (jsdom lays nothing out, so `clientWidth`
 *     is set), the reader's text size (the root font), one extra period guide
 *     placed to collide (to lift a label row), and a missing history response.
 *
 * jsdom draws nothing: these read the SVG's own attributes (the geometry the
 * chart computed), not pixels. Browser fit, modality, accessibility, native,
 * device and TestFlight are NOT verified here; 360 px is not native pixel
 * parity (native baseball keeps its owner's 230 px plot).
 */
import React from "react";
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import hockeyFixtures from "../lib/hockeyJourney10868.fixtures.json";
import mlbFixtures from "../lib/mlbGame10868.fixtures.json";
import type { EventDetailResponse, EventHistoryResponse } from "@/lib/types";
import type { GameMarketsResponse } from "@/lib/api";
import type { HockeyJourneyHistory } from "@/lib/eventPage10868/hockeyJourneyTypes";
import { buildHockeyJourney } from "@/lib/eventPage10868/hockeyJourney";
import { buildMlbGame } from "@/lib/eventPage10868/mlbGame";
import HockeyJourneyHistoryChart, { type HockeyJourneyHistoryLayout } from "@/components/event/eventpage10868/HockeyJourneyHistoryChart";

// ─── Inputs ────────────────────────────────────────────────────────────────

/** The two layouts' plot heights, as the admission (R-H1) fixes them. */
const INLINE_PX = 230;
const EXPANDED_PX = 360;
const EXTRA = EXPANDED_PX - INLINE_PX;
const COLORS = { home: "var(--series-1)", away: "var(--series-2)" };

/** RETAINED hockey final 15169793 through the accepted builder (the hockey suite's own clock). */
function hockeyFinal(history: EventHistoryResponse | null = hockeyFixtures.finalHistory as unknown as EventHistoryResponse): HockeyJourneyHistory {
  return buildHockeyJourney({
    event: hockeyFixtures.finalDetail as unknown as EventDetailResponse,
    history,
    gameMarkets: hockeyFixtures.finalMarkets as unknown as GameMarketsResponse,
    host: { nowMs: Date.parse("2026-10-11T04:56:41Z"), hero: null, probabilityObservedAt: null },
  }).history;
}
/** RETAINED MLB final 15321836 through the accepted builder (the MLB page suite's CONSTRUCTED final host). */
function mlbFinal(): HockeyJourneyHistory {
  const m = buildMlbGame({
    event: mlbFixtures.finalDetail as unknown as EventDetailResponse,
    history: mlbFixtures.finalHistory as unknown as EventHistoryResponse,
    gameMarkets: mlbFixtures.finalMarkets as unknown as GameMarketsResponse,
    host: {
      nowMs: Date.parse("2026-10-11T04:57:23.592725Z"),
      hero: null,
      probabilityObservedAt: null,
      deliveryInterrupted: false,
      liveClaimUnbacked: false,
      score: { home: 3, away: 7, observedAt: null },
      projectedFinal: null,
    },
  });
  if (m.kind !== "game") throw new Error("refused");
  return m.history;
}

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
  delete (HTMLElement.prototype as unknown as Record<string, unknown>).clientWidth;
  jest.restoreAllMocks();
});

/** CONSTRUCTED layout: the chart frame's width in px (jsdom lays nothing out). */
function withFrameWidth(px: number) {
  Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, get: () => px });
}
/** CONSTRUCTED reader setting: the root font at `px` (200% is 32 px); every other element 16 px. */
function withRootFont(px: number) {
  jest.spyOn(window, "getComputedStyle").mockImplementation(((el: Element) =>
    ({ fontSize: el === document.documentElement ? `${px}px` : "16px" }) as unknown as CSSStyleDeclaration) as typeof window.getComputedStyle);
}

function show(history: HockeyJourneyHistory, layout?: HockeyJourneyHistoryLayout) {
  act(() =>
    root.render(
      layout === undefined ? (
        <HockeyJourneyHistoryChart history={history} colors={COLORS} />
      ) : (
        <HockeyJourneyHistoryChart history={history} colors={COLORS} layout={layout} />
      ),
    ),
  );
}
/** A fresh mount per layout (no state carried between the two drawings). */
function fresh(history: HockeyJourneyHistory, layout?: HockeyJourneyHistoryLayout) {
  act(() => root.unmount());
  root = createRoot(host);
  show(history, layout);
}
function click(el: Element) {
  act(() => {
    el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
}

const num = (el: Element, name: string) => Number(el.getAttribute(name));
/** "M x y L x y …" → its points; the command letters kept so a bridged gap (a second M or a missing break) shows. */
function pathPoints(d: string) {
  const tokens = d.trim().split(/\s+/);
  const out: Array<{ cmd: string; x: number; y: number }> = [];
  for (let i = 0; i + 2 < tokens.length; i += 3) out.push({ cmd: tokens[i], x: Number(tokens[i + 1]), y: Number(tokens[i + 2]) });
  return out;
}

/** Everything the plot drew, read from the SVG's own attributes. */
function drawn(history: HockeyJourneyHistory) {
  const svg = host.querySelector('svg[role="img"]');
  if (!svg) throw new Error("no plot");
  const yTickTexts = Array.from(svg.querySelectorAll('text[text-anchor="end"]'));
  const yTicks = yTickTexts.map((t) => {
    const p = history.yTicks.find((tick) => tick.label === t.textContent)!.p;
    const grid = t.parentElement!.querySelector("line")!;
    return { p, label: t.textContent, x: num(t, "x"), y: num(t, "y"), gridX1: num(grid, "x1"), gridX2: num(grid, "x2"), gridY: num(grid, "y1") };
  });
  // The plot's own vertical frame, from two y ticks: y(p) = top + (1 − p) · height.
  const [a, b] = [yTicks[0], yTicks[yTicks.length - 1]];
  const plotHeight = (a.y - b.y) / (b.p - a.p);
  const plotTop = a.y - (1 - a.p) * plotHeight;
  return {
    svg,
    width: num(svg, "width"),
    height: num(svg, "height"),
    viewBox: svg.getAttribute("viewBox"),
    plotTop,
    plotHeight,
    yTicks,
    guides: Array.from(svg.querySelectorAll("line[stroke-dasharray]")).map((l) => ({ x: num(l, "x1"), x2: num(l, "x2"), y1: num(l, "y1"), y2: num(l, "y2") })),
    guideLabels: Array.from(svg.querySelectorAll("text[data-guide-label]")).map((t) => ({
      id: t.getAttribute("data-guide-label"),
      text: t.textContent,
      lane: t.getAttribute("data-guide-lane"),
      x: num(t, "x"),
      y: num(t, "y"),
      className: t.getAttribute("class"),
    })),
    paths: Array.from(svg.querySelectorAll("path")).map((p) => pathPoints(p.getAttribute("d") ?? "")),
    marks: Array.from(svg.querySelectorAll("circle, rect")).map((m) =>
      m.tagName.toLowerCase() === "circle"
        ? { kind: "circle", x: num(m, "cx"), y: num(m, "cy"), size: num(m, "r") }
        : { kind: "rect", x: num(m, "x") + 3.5, y: num(m, "y") + 3.5, size: num(m, "width") },
    ),
    xLabels: Array.from(svg.querySelectorAll("text[data-axis-tick]")).map((t) => ({
      tick: t.getAttribute("data-axis-tick"),
      lane: t.getAttribute("data-axis-lane"),
      text: t.textContent,
      x: num(t, "x"),
      y: num(t, "y"),
      className: t.getAttribute("class"),
    })),
    texts: Array.from(svg.querySelectorAll("text")).map((t) => t.getAttribute("class")),
  };
}
type Drawn = ReturnType<typeof drawn>;
/** What sits outside the plot, as text: the key, the caption line and the Details list. */
function around() {
  const details = Array.from(host.querySelectorAll("button")).find((b) => b.hasAttribute("aria-controls")) ?? null;
  return {
    title: host.querySelector("h3")?.textContent ?? null,
    key: host.querySelector("[data-line-key]")?.textContent ?? null,
    basis: host.querySelector("[data-history-basis]")?.textContent ?? null,
    detailsLabel: details?.textContent ?? null,
    detailsText: details ? (document.getElementById(details.getAttribute("aria-controls") ?? "")?.textContent ?? null) : null,
  };
}

/** The multi-row runs in drawing order, and the marked rows (hollow, single-row or run end), as the chart draws them. */
const runsOf = (history: HockeyJourneyHistory) => history.series.flatMap((s) => s.runs.filter((run) => run.length > 1));
const markedOf = (history: HockeyJourneyHistory) =>
  history.series.flatMap((s) => s.runs.flatMap((run) => run.filter((pt, i) => pt.hollow || run.length === 1 || i === run.length - 1)));

/** Inline vs expanded of ONE history: every horizontal fact equal; every vertical fact mapped onto the taller plot. */
function expectSameJourneyTaller(history: HockeyJourneyHistory, inline: Drawn, expanded: Drawn) {
  // The SVG grows by exactly the extra plot height; its width never moves.
  expect([expanded.width, expanded.height - inline.height]).toEqual([inline.width, EXTRA]);
  expect(expanded.viewBox).toBe(`0 0 ${expanded.width} ${expanded.height}`);
  // The plot keeps its top and gains the extra height.
  expect(expanded.plotTop).toBeCloseTo(inline.plotTop, 6);
  expect(expanded.plotHeight - inline.plotHeight).toBeCloseTo(EXTRA, 6);
  // Y scale: the same ticks, at the same x, each at its percentage of the taller plot.
  expect(expanded.yTicks.map((t) => [t.label, t.x, t.gridX1, t.gridX2])).toEqual(inline.yTicks.map((t) => [t.label, t.x, t.gridX1, t.gridX2]));
  for (const t of expanded.yTicks) {
    expect(t.y).toBeCloseTo(expanded.plotTop + (1 - t.p) * expanded.plotHeight, 6);
    expect(t.gridY).toBeCloseTo(t.y, 6);
  }
  // Every run is its own path, never bridged; the same points at the same x, each at its own p on the taller plot.
  const runs = runsOf(history);
  expect(expanded.paths).toHaveLength(runs.length);
  expect(inline.paths).toHaveLength(runs.length);
  expanded.paths.forEach((points, i) => {
    expect(points.map((pt) => pt.cmd)).toEqual(["M", ...Array(runs[i].length - 1).fill("L")]);
    expect(points.map((pt) => pt.x)).toEqual(inline.paths[i].map((pt) => pt.x));
    points.forEach((pt, j) => {
      expect(Math.abs(pt.y - (expanded.plotTop + (1 - runs[i][j].p) * expanded.plotHeight))).toBeLessThanOrEqual(0.051);
      expect(Math.abs(inline.paths[i][j].y - (inline.plotTop + (1 - runs[i][j].p) * inline.plotHeight))).toBeLessThanOrEqual(0.051);
    });
  });
  // Every mark (hollow pregame, single row, run end): same kind, size and x; y at its own p.
  const marked = markedOf(history);
  expect(expanded.marks).toHaveLength(marked.length);
  expect(expanded.marks.map((m) => [m.kind, m.size, m.x])).toEqual(inline.marks.map((m) => [m.kind, m.size, m.x]));
  expanded.marks.forEach((m, i) => expect(m.y).toBeCloseTo(expanded.plotTop + (1 - marked[i].p) * expanded.plotHeight, 6));
  // Guides: the same lines at the same x, spanning the taller plot; their labels exactly where they were (above it).
  expect(expanded.guides.map((g) => [g.x, g.x2, g.y1])).toEqual(inline.guides.map((g) => [g.x, g.x2, g.y1]));
  for (const g of expanded.guides) {
    expect(g.y1).toBeCloseTo(expanded.plotTop, 6);
    expect(g.y2 - g.y1).toBeCloseTo(expanded.plotHeight, 6);
  }
  expect(expanded.guideLabels).toEqual(inline.guideLabels);
  // Time labels: the same drawn subset, lanes, words, type and x; the band moves down by the extra height.
  expect(expanded.xLabels.map((l) => [l.tick, l.lane, l.text, l.x, l.className])).toEqual(
    inline.xLabels.map((l) => [l.tick, l.lane, l.text, l.x, l.className]),
  );
  expanded.xLabels.forEach((l, i) => expect(l.y - inline.xLabels[i].y).toBe(EXTRA));
  // Type never shrinks: every SVG text keeps its class.
  expect(expanded.texts).toEqual(inline.texts);
}

// ─── Default = inline ──────────────────────────────────────────────────────

describe("the default is the inline chart, unchanged", () => {
  it("RETAINED hockey and MLB finals: no layout and layout=\"inline\" draw identical markup; the inline plot is 230 px", () => {
    for (const history of [hockeyFinal(), mlbFinal()]) {
      fresh(history);
      const byDefault = host.innerHTML;
      show(history, "inline");
      expect(host.innerHTML).toBe(byDefault);
      const inline = drawn(history);
      // The inline plot block: its top margin + plot + bottom margin is the 230 px height (no lifted row here).
      expect(inline.guideLabels.every((l) => l.lane === "0")).toBe(true);
      const bottomMargin = 6;
      expect(inline.plotTop + inline.plotHeight + bottomMargin).toBeCloseTo(INLINE_PX, 6);
    }
  });
});

// ─── Expanded: the same journey, taller ────────────────────────────────────

describe("expanded: the same journey on a taller plot", () => {
  it("RETAINED hockey final 15169793: every run, gap, mark, guide, label and tick keeps its x and maps its p onto the 360 px plot", () => {
    const history = hockeyFinal();
    // Non-vacuity: a real journey with several runs (gaps), single-row marks and period guides.
    expect(runsOf(history).length).toBeGreaterThan(2);
    expect(history.series.some((s) => s.runs.some((run) => run.length === 1))).toBe(true);
    expect(history.guides.filter((g) => g.kind === "period").length).toBeGreaterThan(0);
    fresh(history, "inline");
    const inline = drawn(history);
    const aroundInline = around();
    fresh(history, "expanded");
    const expanded = drawn(history);
    expectSameJourneyTaller(history, inline, expanded);
    expect(expanded.plotTop + expanded.plotHeight + 6).toBeCloseTo(EXPANDED_PX, 6);
    expect(expanded.guides.length).toBeGreaterThan(0);
    expect(expanded.guideLabels.length).toBeGreaterThan(0);
    // The title, key, caption and notes are the inline chart's.
    expect(around()).toEqual(aroundInline);
    expect(aroundInline.key).toContain("Minnesota Wild");
  });

  it("RETAINED MLB final 15321836: the same mapping on the baseball page's own history", () => {
    const history = mlbFinal();
    expect(history.domain).not.toBeNull();
    expect(runsOf(history).length).toBeGreaterThan(0);
    fresh(history, "inline");
    const inline = drawn(history);
    const aroundInline = around();
    fresh(history, "expanded");
    expectSameJourneyTaller(history, inline, drawn(history));
    expect(around()).toEqual(aroundInline);
  });

  it("the Details disclosure stays a working disclosure in the expanded chart, with the same lines", () => {
    const history = hockeyFinal();
    fresh(history, "expanded");
    const details = Array.from(host.querySelectorAll("button")).find((b) => b.textContent === history.detailsLabel)!;
    const region = document.getElementById(details.getAttribute("aria-controls") ?? "")!;
    expect([details.getAttribute("aria-expanded"), region.hidden]).toEqual(["false", true]);
    click(details);
    expect([details.getAttribute("aria-expanded"), region.hidden]).toEqual(["true", false]);
    expect(region.textContent).toContain("Gaps remain blank.");
    click(details);
    expect(region.hidden).toBe(true);
  });
});

// ─── Width, text size, lifted guide rows ───────────────────────────────────

describe("CONSTRUCTED width, text size and a lifted guide-label row", () => {
  it.each([
    [300, 16],
    [300, 32],
    [1190, 16],
  ])("frame %i px, root font %i px: the expanded chart keeps every horizontal placement and lane, only taller", (frameWidth, rootFont) => {
    withFrameWidth(frameWidth);
    if (rootFont !== 16) withRootFont(rootFont);
    const history = hockeyFinal();
    fresh(history, "inline");
    const inline = drawn(history);
    fresh(history, "expanded");
    const expanded = drawn(history);
    expect(inline.width).toBe(frameWidth);
    expectSameJourneyTaller(history, inline, expanded);
  });

  it("a lifted period-label row adds height ABOVE the plot and never takes it from the plot, in both layouts", () => {
    const base = hockeyFinal();
    const first = base.guides.find((g) => g.kind === "period")!;
    // CONSTRUCTED: one more period guide a moment after the first, so the two labels collide and one lifts a row.
    const lifted: HockeyJourneyHistory = {
      ...base,
      guides: [...base.guides, { id: "constructed-collision", t: first.t + 1, label: "CONSTRUCTED", kind: "period" }],
    };
    for (const layout of ["inline", "expanded"] as const) {
      fresh(base, layout);
      const flat = drawn(base);
      fresh(lifted, layout);
      const raised = drawn(lifted);
      const lanes = raised.guideLabels.map((l) => Number(l.lane));
      expect(Math.max(...lanes)).toBeGreaterThan(0); // non-vacuity: a row really lifted
      const band = raised.plotTop - flat.plotTop;
      expect(band).toBeGreaterThan(0);
      // The plot keeps its full height; the drawing grows by the band.
      expect(raised.plotHeight).toBeCloseTo(flat.plotHeight, 6);
      expect(raised.plotHeight).toBeCloseTo((layout === "inline" ? INLINE_PX : EXPANDED_PX) - 6 - flat.plotTop, 6);
      expect(raised.height - flat.height).toBeCloseTo(band, 6);
      for (const g of raised.guides) expect(g.y2 - g.y1).toBeCloseTo(raised.plotHeight, 6);
      // Every label still sits above the plot, never over the lines.
      for (const l of raised.guideLabels) expect(l.y).toBeLessThan(raised.plotTop);
    }
    // And across layouts the lifted drawing differs only by the extra plot height.
    fresh(lifted, "inline");
    const inline = drawn(lifted);
    fresh(lifted, "expanded");
    expectSameJourneyTaller(lifted, inline, drawn(lifted));
  });
});

// ─── Absence ───────────────────────────────────────────────────────────────

describe("a missing history keeps its truthful absence in both layouts", () => {
  it("CONSTRUCTED no history response: no plot, mark or line is drawn, the absence panel keeps the inline height, the key and caption are unchanged", () => {
    const missing = hockeyFinal(null);
    expect(missing.domain).toBeNull();
    // The frame is the section's second child (after the header); the absence panel is its only child.
    const panelOf = () => host.querySelector<HTMLElement>("section > header + div > div");
    fresh(missing, "inline");
    const inlineHtml = host.innerHTML;
    const aroundInline = around();
    const panelInline = panelOf();
    const inlineMinHeight = panelInline?.style.minHeight;
    const inlineText = panelInline?.textContent;
    show(missing, "expanded"); // the same mount, so the markup can be compared byte for byte
    expect(host.querySelector('svg[role="img"]')).toBeNull();
    expect(host.querySelector("path")).toBeNull();
    // The only SVG left is each key entry's glyph; nothing is plotted.
    expect(Array.from(host.querySelectorAll("svg")).every((svg) => svg.closest("[data-line-key]"))).toBe(true);
    const panel = panelOf();
    expect(panel?.textContent).toBe(inlineText);
    expect(panel?.textContent).toContain(missing.absence!.title);
    expect([inlineMinHeight, panel?.style.minHeight]).toEqual([`${INLINE_PX}px`, `${INLINE_PX}px`]);
    expect(around()).toEqual(aroundInline);
    // With nothing to draw, the two layouts are the same markup.
    expect(host.innerHTML).toBe(inlineHtml);
  });
});
