/**
 * #5581 — THE WIN-PROBABILITY CHART STOPS EATING ITS OWN TRAILING VALUE.
 *
 * Found by ux/1212's D48 mystery-shop of production at 390px, on two MLB event
 * pages independently: the green `100%` callout rendered at HALF HEIGHT, cut by
 * the plot's top edge, and what survived landed on the period strip so `T8` read
 * `T o` and `B10` read `⊳10`. Crops in `artifacts/ux-1212/`, reproduced by
 * ux/1214 in `artifacts/ux-1214/crop-5581-topright-3x.png`.
 *
 * THE DEFECT IS STRUCTURAL, WHICH IS WHY IT IS WORTH A GUARD. `computeWinProbYAxis`
 * snaps the domain with `Math.min(100, …)` — a probability has nowhere above 100
 * to go — so a series that finishes at 100% puts its last point EXACTLY on the
 * plot's top edge, and the YAxis's `allowDataOverflow` makes recharts clip the
 * Scatter layer to the plot rect. Every blowout, not one specimen. Measured on
 * `/events/15308045` with `getBBox()` on 2026-09-12: plot top `y=15`, callout
 * `cy=15`, label box `y=8.5..21.5`, chips `y=16.81..29.81`.
 *
 * ═══ WHY THIS GUARD RENDERS THE CHART ═══
 *
 * The rule under test is a collision between three boxes that RECHARTS lays out
 * (the plot rect, the chip labels) and one this repo draws (the callout plate).
 * A test that fed `calloutLabelCenterY` a hand-built plot rect would agree with
 * the component about numbers neither of them had checked against the renderer —
 * `chartTextStaysInsideThePlot`'s header is the standing lesson here ("two
 * artifacts agreeing about a wrong input agree perfectly and prove nothing").
 * So every number below is parsed out of emitted markup, and the fixture's
 * geometry is asserted first: `test 1` fails if the specimen stops putting the
 * callout on the frame, which is the only condition under which the rest of the
 * file is testing anything at all.
 *
 * The one hand-built test is at the bottom and is labelled as such: it pins the
 * degenerate plots the renderer will not produce on demand.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("@/components/Analytics/AnalyticsProvider", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
  AnalyticsProvider: ({ children }: { children: React.ReactNode }) => children,
}));

// recharts draws NOTHING inside a ResponsiveContainer without a viewport, so a
// test that rendered the component as-is would assert over an empty string and
// pass on both arms (same reason as `chartUsesItsHeight3973`).
jest.mock("recharts", () => {
  const actual = jest.requireActual("recharts");
  return {
    __esModule: true,
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactElement }) =>
      React.cloneElement(children, { width: 390, height: 300 }),
  };
});

import OddsChart, { calloutLabelCenterY } from "@/components/OddsChart";
import type { PeriodBoundary } from "@/lib/periodMarkers";

/** Fixed anchor — never `Date.now()` (gotcha #44: offset first, no clock branch). */
const START = Date.UTC(2026, 8, 11, 17, 5, 0);

/**
 * A blowout that ENDS at 100 but does not start there, so the series is a real
 * curve and not a flat line pinned to the ceiling — a fixture that sat at 100
 * throughout would make the clip trivially total and prove less.
 */
function blowout(n: number): number[] {
  const out: number[] = [];
  for (let i = 0; i < n; i++) {
    const t = i / (n - 1);
    out.push(52 + 48 * t * t + 3 * Math.sin(i * 0.9) * (1 - t));
  }
  out[out.length - 1] = 100;
  return out;
}

/** The mirror: the home side collapses to 0, so the callout lands on the FLOOR. */
function collapse(n: number): number[] {
  return blowout(n)
    .map((v) => 100 - v)
    .map((v) => Math.max(0, v));
}

function points(probs: number[]) {
  return probs.map((p, i) => ({
    timestamp: new Date(START + i * 60_000).toISOString(),
    home_probability: p / 100,
    away_probability: 1 - p / 100,
  }));
}

/**
 * Period chips at the END of the series, which is where they collide: the
 * callout is at the last data point, and since the right-hand buffer was removed
 * (#3525) that point IS the plot's right rule.
 */
function lateBoundaries(probs: number[]): PeriodBoundary[] {
  const n = probs.length;
  return [0.55, 0.78, 0.93, 0.99].map((f, i) => ({
    timestamp: new Date(START + Math.floor(f * (n - 1)) * 60_000).toISOString(),
    label: ["T6", "B7", "T8", "T9"][i],
  }));
}

function render(probs: number[], periodBoundaries?: PeriodBoundary[]) {
  return renderToStaticMarkup(
    <OddsChart
      history={[]}
      homeTeam="Orioles"
      awayTeam="Guardians"
      commenceTime={new Date(START).toISOString()}
      isLive={false}
      eventStatus="completed"
      externalTimeRange="all"
      periodBoundaries={periodBoundaries}
      winProbHistory={{ kalshi: points(probs) }}
      winProbSources={{
        kalshi: {
          display_name: "Kalshi",
          color: "#22c55e",
          type: "market",
          snapshot_count: probs.length,
        },
      }}
    />,
  );
}

interface Box {
  top: number;
  bottom: number;
  left: number;
  right: number;
}

/** The plot rectangle recharts laid out, read off the clip rect it emitted. */
function plotRect(html: string): { top: number; bottom: number } {
  const m = /<clipPath id="recharts\d+-clip"><rect x="[\d.-]+" y="([\d.-]+)" height="([\d.-]+)"/.exec(html);
  if (!m) throw new Error("no plot clip rect — the chart did not lay out");
  const top = Number(m[1]);
  return { top, bottom: top + Number(m[2]) };
}

/**
 * The callout's painted box: the white plate, which is what an edge cuts. Found
 * by its own shape rather than by index — it is the only `<rect>` the chart
 * draws with `rx="3"` and a flat white fill.
 *
 * THROWS when it cannot find exactly one, so a restyle that renames or drops the
 * plate fails this file instead of quietly making every assertion vacuous.
 */
function calloutPlate(html: string): Box {
  const rects = html.match(/<rect[^>]*rx="3"[^>]*fill="#FFFFFF"[^>]*>/g) ?? [];
  if (rects.length !== 1) throw new Error(`expected one callout plate, found ${rects.length}`);
  const num = (attr: string) => {
    const m = new RegExp(`\\s${attr}="([\\d.-]+)"`).exec(rects[0]);
    if (!m) throw new Error(`callout plate has no ${attr}`);
    return Number(m[1]);
  };
  const x = num("x");
  const y = num("y");
  return { top: y, bottom: y + num("height"), left: x, right: x + num("width") };
}

/** The dot the callout labels — the larger of the two circles (its glow). */
function calloutDot(html: string): { cy: number; r: number } {
  const circles = [...html.matchAll(/<circle[^>]*cy="([\d.-]+)"[^>]*\sr="(\d+)"[^>]*>/g)].map((m) => ({
    cy: Number(m[1]),
    r: Number(m[2]),
  }));
  const glow = circles.find((c) => c.r === 8);
  if (!glow) throw new Error("no callout glow circle — the dot is not being drawn");
  return glow;
}

/**
 * The bottom of each period chip's INK — the number the callout has to clear.
 *
 * recharts anchors a `ReferenceLine` label with `y` on the `<text>` and pushes
 * the glyphs down by `dy="0.71em"` on a `<tspan>`, so the `y` attribute is NOT
 * the top of the box and asserting against it would pass a label sitting right
 * on the chips. jsdom lays nothing out, so the descent below the baseline comes
 * from the RENDERED page: on `/events/15308045`, `y=20` at `font-size: 11px`
 * measured `getBBox() = 16.81..29.81` — baseline at `y + 0.71em`, ink to 2.0px
 * below it (and 11px, one full em, above it). Only that 2.0 is carried here; the
 * anchor and the size are read from the markup.
 */
const CHIP_DESCENT_PX = 2.0;

function chipInkBottoms(html: string): number[] {
  const out: number[] = [];
  for (const m of html.matchAll(/<text([^>]*)>\s*<tspan[^>]*>(?:T6|B7|T8|T9)<\/tspan>/g)) {
    const attrs = m[1];
    const y = Number(/\sy="([\d.-]+)"/.exec(attrs)?.[1]);
    const fs = Number(/font-size:\s*([\d.]+)px/.exec(attrs)?.[1]);
    if (!Number.isFinite(y) || !Number.isFinite(fs)) {
      throw new Error(`a period chip rendered without a y or a font-size: ${attrs}`);
    }
    out.push(y + 0.71 * fs + CHIP_DESCENT_PX);
  }
  return out;
}

const SERIES = blowout(120);

describe("#5581 — the trailing value label is never cut by the plot's own frame", () => {
  test("the specimen really does put the callout ON the frame (without this the rest is vacuous)", () => {
    const html = render(SERIES, lateBoundaries(SERIES));
    const plot = plotRect(html);
    const dot = calloutDot(html);
    // The dot is the datum, and the datum is the ceiling: this is the condition
    // the whole defect needs, asserted rather than assumed.
    expect(dot.cy).toBeCloseTo(plot.top, 5);
    // ... and the chips really are drawn, in the band the label has to clear.
    // Both halves matter: with no chips in the markup, the strip assertion below
    // would iterate an empty list and pass on a label sitting on top of them.
    const chips = chipInkBottoms(html);
    expect(chips.length).toBeGreaterThan(0);
    for (const inkBottom of chips) {
      expect(inkBottom).toBeGreaterThan(plot.top);
      expect(inkBottom).toBeLessThan(plot.top + 20);
    }
  });

  test("a game that finishes at 100% keeps its whole label inside the plot", () => {
    const html = render(SERIES, lateBoundaries(SERIES));
    const plot = plotRect(html);
    const plate = calloutPlate(html);
    expect(plate.top).toBeGreaterThanOrEqual(plot.top);
    expect(plate.bottom).toBeLessThanOrEqual(plot.bottom);
  });

  test("and clears the period strip rather than relocating the collision into it", () => {
    // native/024's finding on #3237, the iOS twin: the clamp ALONE was wrong,
    // because pulling "Final" inside the frame drove it into "9th" and drew
    // "9Final". A label that is inside the plot and on top of a chip is not fixed.
    const html = render(SERIES, lateBoundaries(SERIES));
    const plate = calloutPlate(html);
    const chips = chipInkBottoms(html);
    expect(chips.length).toBeGreaterThan(0);
    for (const inkBottom of chips) {
      // Below the chips' INK, not below their anchor — see `chipInkBottoms`.
      expect(plate.top).toBeGreaterThanOrEqual(inkBottom);
    }
  });

  test("the DOT does not move — it is the datum, and the datum is on the ceiling", () => {
    const html = render(SERIES, lateBoundaries(SERIES));
    const plot = plotRect(html);
    expect(calloutDot(html).cy).toBeCloseTo(plot.top, 5);
  });

  test("the mirror case: a collapse to 0% is not cut by the plot's FLOOR", () => {
    const series = collapse(120);
    const html = render(series, lateBoundaries(series));
    const plot = plotRect(html);
    const plate = calloutPlate(html);
    expect(calloutDot(html).cy).toBeCloseTo(plot.bottom, 5);
    expect(plate.bottom).toBeLessThanOrEqual(plot.bottom);
    expect(plate.top).toBeGreaterThanOrEqual(plot.top);
  });

  test("a chipless chart drops the label by LESS — the strip is only cleared when drawn", () => {
    // The `Start` marker is anchored at the plot's LEFT edge and the callout is
    // at the right by construction, so a chipless chart owes the strip nothing.
    // Asserting the two arms DIFFER is what stops the band being applied blindly.
    const withChips = calloutPlate(render(SERIES, lateBoundaries(SERIES))).top;
    const without = calloutPlate(render(SERIES)).top;
    expect(without).toBeLessThan(withChips);
    expect(without).toBeGreaterThanOrEqual(plotRect(render(SERIES)).top);
  });

  test("an ordinary chart is untouched — the label still sits on its dot's row", () => {
    // The clamp must be invisible everywhere except at the frame, or it is a
    // restyle of every event page wearing a bug fix's name.
    const mid = blowout(120).map((v) => 30 + (v - 52) * 0.2);
    const html = render(mid, lateBoundaries(mid));
    const plate = calloutPlate(html);
    const dot = calloutDot(html);
    expect((plate.top + plate.bottom) / 2).toBeCloseTo(dot.cy, 5);
  });
});

describe("#5581 — the degenerate plots a renderer will not produce on demand", () => {
  // HAND-BUILT INPUTS, deliberately: these are the branches that exist so the
  // function cannot emit a position worse than the one it replaced. Everything
  // above measures the real renderer; this block does not pretend to.
  const PLOT = { plotTop: 15, plotHeight: 270 };

  test("a value mid-plot is returned unchanged", () => {
    expect(calloutLabelCenterY({ cy: 140, ...PLOT, hasPeriodChips: true })).toBe(140);
  });

  test("a plot with room for the label but not the strip still gets inside the frame", () => {
    // 22px of plot: the label's own box fits, the box plus the 15px strip cannot.
    const y = calloutLabelCenterY({ cy: 15, plotTop: 15, plotHeight: 22, hasPeriodChips: true });
    expect(y).toBeGreaterThanOrEqual(15);
    expect(y).toBeLessThanOrEqual(37);
  });

  test("a plot too short for the label at all leaves the label on its datum", () => {
    expect(calloutLabelCenterY({ cy: 15, plotTop: 15, plotHeight: 4, hasPeriodChips: true })).toBe(15);
  });

  test("a missing or zero plot rect no-ops rather than emitting NaN", () => {
    expect(calloutLabelCenterY({ cy: 15, plotTop: 15, plotHeight: 0, hasPeriodChips: true })).toBe(15);
    expect(
      calloutLabelCenterY({ cy: 15, plotTop: NaN, plotHeight: 270, hasPeriodChips: true }),
    ).toBe(15);
  });
});
