/**
 * #7134 — THE CALLOUT CLEARS THE PERIOD STRIP THE CHART ACTUALLY DREW, NOT A
 * ONE-ROW STRIP IT ASSUMED.
 *
 * Found by ux/1349's notice-42 marquee walk on `/events/15314181` (Giants @
 * Dodgers, Final 8–2) at 390px, re-measured on production by ux/1368 on
 * 2026-09-19 after #6964 landed:
 *
 *   label   x     w    y        (viewport px, 390 wide)
 *   B8      314   15   -251     period chip, row 0
 *   100%    314   26   -236     the end-value callout
 *   T9      336   15   -238     period chip, ROW 1
 *
 * The callout's box and `T9`'s overlap by 4×11px — eleven of the callout's
 * thirteen rows of pixels. It is the end of a settled game, which is the part of
 * the chart a reader came for, and the `100%` is the glyph that is hardest to
 * read.
 *
 * ═══ THE REMEDY ALREADY EXISTED AND WAS A FRACTION OF ITSELF ═══
 *
 * #5581 built `calloutLabelCenterY` for exactly this collision and it is aimed
 * correctly: `PERIOD_CHIP_BAND_PX` pushes the callout clear of the chip strip.
 * But that constant was measured on `/events/15308045`, where every chip sat on
 * ONE row, and it is applied through a BOOLEAN — chips or no chips. #6882 then
 * taught the chips to stagger onto a second row (`PERIOD_LABEL_ROW_HEIGHT_PX`),
 * and nothing told the callout. So the callout is pushed to exactly the bottom
 * of row 0 and lands squarely on row 1: measured on the specimen above, the
 * callout's centre is `plotTop + PLATE_HALF + 15` to the pixel.
 *
 * A strip that is two rows deep is cleared by a band that is two rows deep. The
 * band stops being a constant and becomes the depth the chart drew.
 *
 * ═══ WHY THIS FILE EXISTS RATHER THAN A NEW ARM IN #5581's ═══
 *
 * `chartCalloutClearsTheTopStrip5581.test.tsx` asserts the clearance for every
 * chip it renders — and it PASSES on the defect, because its fixture's
 * boundaries are spaced so that `assignPeriodLabelRows` puts all of them on row
 * 0. It is a correct guard whose specimen has no second row. This file is the
 * second row: same renderer, same parsing, a fixture chosen so the stagger
 * fires, and `test 1` fails if it ever stops firing.
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
// pass on both arms. Same mock, same reason, as #5581's file.
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
import { PERIOD_LABEL_ROW_HEIGHT_PX } from "@/lib/periodMarkers";
import type { PeriodBoundary } from "@/lib/periodMarkers";

/** Fixed anchor — never `Date.now()` (gotcha #44: offset first, no clock branch). */
const START = Date.UTC(2026, 8, 11, 17, 5, 0);
const N = 120;

/** The specimen's shape: a real curve that finishes pinned to the ceiling. */
function blowout(n: number): number[] {
  const out: number[] = [];
  for (let i = 0; i < n; i++) {
    const t = i / (n - 1);
    out.push(52 + 48 * t * t + 3 * Math.sin(i * 0.9) * (1 - t));
  }
  out[out.length - 1] = 100;
  return out;
}

function points(probs: number[]) {
  return probs.map((p, i) => ({
    timestamp: new Date(START + i * 60_000).toISOString(),
    home_probability: p / 100,
    away_probability: 1 - p / 100,
  }));
}

/**
 * Four innings whose LAST label staggers onto row 1 — the production shape.
 *
 * Chosen against `assignPeriodLabelRows`' own two thresholds on a 119-minute
 * span, not by eye: collapse below 7% (8.3 min), stagger below 12.6% (15.0 min).
 *
 *   T6→B7  30 min = 25.2%  → both row 0
 *   B7→B8  18 min = 15.1%  → clears the stagger band, B8 stays on row 0
 *   B8→T9  13 min = 10.9%  → inside the band, survives the collapse, T9 DROPS
 *
 * That is `B8` on row 0 and `T9` on row 1 against the right-hand rule, which is
 * the pair the production frame photographed.
 */
const STAGGERED_MINUTES: Array<[number, string]> = [
  [55, "T6"],
  [85, "B7"],
  [103, "B8"],
  [116, "T9"],
];

function staggeredBoundaries(): PeriodBoundary[] {
  return STAGGERED_MINUTES.map(([min, label]) => ({
    timestamp: new Date(START + min * 60_000).toISOString(),
    label,
  }));
}

function render(probs: number[], periodBoundaries?: PeriodBoundary[]) {
  return renderToStaticMarkup(
    <OddsChart
      history={[]}
      homeTeam="Dodgers"
      awayTeam="Giants"
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
}

function plotRect(html: string): { top: number; bottom: number } {
  const m = /<clipPath id="recharts\d+-clip"><rect x="[\d.-]+" y="([\d.-]+)" height="([\d.-]+)"/.exec(html);
  if (!m) throw new Error("no plot clip rect — the chart did not lay out");
  const top = Number(m[1]);
  return { top, bottom: top + Number(m[2]) };
}

/**
 * The callout's painted box: the white plate, which is what a chip is covered
 * by. THROWS unless exactly one is found, so a restyle fails this file rather
 * than quietly making every assertion vacuous.
 */
function calloutPlate(html: string): Box {
  const rects = html.match(/<rect[^>]*rx="3"[^>]*fill="#FFFFFF"[^>]*>/g) ?? [];
  if (rects.length !== 1) throw new Error(`expected one callout plate, found ${rects.length}`);
  const num = (attr: string) => {
    const m = new RegExp(`\\s${attr}="([\\d.-]+)"`).exec(rects[0]);
    if (!m) throw new Error(`callout plate has no ${attr}`);
    return Number(m[1]);
  };
  const y = num("y");
  return { top: y, bottom: y + num("height") };
}

/** The larger of the two circles — the dot the callout labels. */
function calloutDot(html: string): number {
  const circles = [...html.matchAll(/<circle[^>]*cy="([\d.-]+)"[^>]*\sr="(\d+)"[^>]*>/g)].map((m) => ({
    cy: Number(m[1]),
    r: Number(m[2]),
  }));
  const glow = circles.find((c) => c.r === 8);
  if (!glow) throw new Error("no callout glow circle — the dot is not being drawn");
  return glow.cy;
}

/**
 * The bottom of a period chip's INK — the number the callout has to clear.
 *
 * Carried verbatim from #5581's file. `0.71em` is recharts' own baseline shift
 * and `CHIP_DESCENT_PX` is ink below that baseline, measured on
 * `/events/15308045` (`y=20` at 11px → bbox `16.81..29.81`).
 *
 * MEASURED, not assumed: recharts FOLDS the label's `dy` into the emitted `y`
 * rather than passing it through as an attribute, so row 1's `y` is already
 * `row 0 + PERIOD_LABEL_ROW_HEIGHT_PX`. Reading a `dy` attribute here would
 * find nothing on either arm — which is what the first draft of this file did,
 * and what `test 1`'s row-separation assertion now catches.
 */
const CHIP_DESCENT_PX = 2.0;

function chips(html: string): Array<{ label: string; inkTop: number; inkBottom: number }> {
  const out: Array<{ label: string; inkTop: number; inkBottom: number }> = [];
  for (const m of html.matchAll(/<text([^>]*)>\s*<tspan[^>]*>(T6|B7|B8|T9)<\/tspan>/g)) {
    const attrs = m[1];
    const y = Number(/\sy="([\d.-]+)"/.exec(attrs)?.[1]);
    const fs = Number(/font-size:\s*([\d.]+)px/.exec(attrs)?.[1]);
    if (!Number.isFinite(y) || !Number.isFinite(fs)) {
      throw new Error(`a period chip rendered without a y or a font-size: ${attrs}`);
    }
    const baseline = y + 0.71 * fs;
    out.push({ label: m[2], inkTop: baseline - fs, inkBottom: baseline + CHIP_DESCENT_PX });
  }
  return out;
}

const SERIES = blowout(N);

describe("#7134 — the end-value callout clears a TWO-row period strip", () => {
  test("the specimen really does stagger, and really does pin the callout to the ceiling", () => {
    // Without all three of these the rest of the file is testing nothing: no
    // second row means #5581's one-row band is already correct here, and a
    // callout off the ceiling is never pushed at all.
    const html = render(SERIES, staggeredBoundaries());

    const rows = /data-period-label-rows="([^"]*)"/.exec(html)?.[1];
    expect(rows).toBe("0,0,0,1");

    const drawn = chips(html);
    expect(drawn.map((c) => c.label)).toEqual(["T6", "B7", "B8", "T9"]);
    // The drop is real ink one row down, not a row index in an attribute: the
    // first three share a row and `T9` sits exactly one row below them.
    expect(drawn[1].inkTop).toBeCloseTo(drawn[0].inkTop, 5);
    expect(drawn[2].inkTop).toBeCloseTo(drawn[0].inkTop, 5);
    expect(drawn[3].inkTop - drawn[2].inkTop).toBeCloseTo(PERIOD_LABEL_ROW_HEIGHT_PX, 5);

    expect(calloutDot(html)).toBeCloseTo(plotRect(html).top, 5);
  });

  test("the callout does not land on the staggered chip", () => {
    // THE DEFECT. Production: callout box −236..−223, `T9` −238..−225, 11px of
    // the callout's 13 covered.
    const html = render(SERIES, staggeredBoundaries());
    const plate = calloutPlate(html);
    for (const chip of chips(html)) {
      expect(plate.top).toBeGreaterThanOrEqual(chip.inkBottom);
    }
  });

  test("it is still inside the plot — clearing row 1 must not push it out the bottom", () => {
    const html = render(SERIES, staggeredBoundaries());
    const plot = plotRect(html);
    const plate = calloutPlate(html);
    expect(plate.top).toBeGreaterThanOrEqual(plot.top);
    expect(plate.bottom).toBeLessThanOrEqual(plot.bottom);
  });

  test("the DOT does not move — the datum is the ceiling, only the label drops", () => {
    const html = render(SERIES, staggeredBoundaries());
    expect(calloutDot(html)).toBeCloseTo(plotRect(html).top, 5);
  });

  test("a one-row strip is cleared by LESS than a two-row strip", () => {
    // The band must be the depth the chart DREW. Asserting the two arms differ
    // by exactly one row is what stops the fix being "always drop two rows",
    // which would be a restyle of every single-row chart wearing a bug fix's
    // name. `oneRow` reuses #5581's spacing: 0.55/0.78/0.93 are >12.6% apart.
    const oneRow: PeriodBoundary[] = [
      [55, "T6"],
      [85, "B7"],
      [110, "B8"],
    ].map(([min, label]) => ({
      timestamp: new Date(START + (min as number) * 60_000).toISOString(),
      label: label as string,
    }));

    const oneRowHtml = render(SERIES, oneRow);
    expect(/data-period-label-rows="([^"]*)"/.exec(oneRowHtml)?.[1]).toBe("0,0,0");

    const shallow = calloutPlate(oneRowHtml).top;
    const deep = calloutPlate(render(SERIES, staggeredBoundaries())).top;
    expect(deep - shallow).toBeCloseTo(PERIOD_LABEL_ROW_HEIGHT_PX, 5);
  });

  test("an ordinary chart is untouched — the label still sits on its dot's row", () => {
    // The deeper band must be invisible everywhere except against the frame.
    const mid = blowout(N).map((v) => 30 + (v - 52) * 0.2);
    const html = render(mid, staggeredBoundaries());
    const plate = calloutPlate(html);
    expect((plate.top + plate.bottom) / 2).toBeCloseTo(calloutDot(html), 5);
  });
});

describe("#7134 — the band is the depth drawn (hand-built, as labelled)", () => {
  // These pin the function's own arithmetic. Everything above measures the real
  // renderer; this block does not pretend to.
  const PLOT = { plotTop: 15, plotHeight: 270 };

  test("row count 0 owes the strip nothing", () => {
    const none = calloutLabelCenterY({ cy: 15, ...PLOT, periodChipRows: 0 });
    const one = calloutLabelCenterY({ cy: 15, ...PLOT, periodChipRows: 1 });
    expect(none).toBeLessThan(one);
  });

  test("each extra row drops the label by exactly one row height", () => {
    const one = calloutLabelCenterY({ cy: 15, ...PLOT, periodChipRows: 1 });
    const two = calloutLabelCenterY({ cy: 15, ...PLOT, periodChipRows: 2 });
    expect(two - one).toBeCloseTo(PERIOD_LABEL_ROW_HEIGHT_PX, 5);
  });

  test("a value mid-plot is returned unchanged whatever the strip's depth", () => {
    expect(calloutLabelCenterY({ cy: 140, ...PLOT, periodChipRows: 2 })).toBe(140);
  });

  test("a plot too short for the deeper band still gets inside the frame", () => {
    // 22px of plot: the label's own box fits, the box plus a two-row strip
    // cannot. Staying inside the frame is the half that must not be given up —
    // outside it the label is not drawn at all.
    const y = calloutLabelCenterY({ cy: 15, plotTop: 15, plotHeight: 22, periodChipRows: 2 });
    expect(y).toBeGreaterThanOrEqual(15);
    expect(y).toBeLessThanOrEqual(37);
  });

  test("a nonsense row count cannot emit NaN or drag the label off the datum", () => {
    expect(calloutLabelCenterY({ cy: 15, ...PLOT, periodChipRows: NaN })).toBe(
      calloutLabelCenterY({ cy: 15, ...PLOT, periodChipRows: 0 }),
    );
    expect(calloutLabelCenterY({ cy: 15, ...PLOT, periodChipRows: -3 })).toBe(
      calloutLabelCenterY({ cy: 15, ...PLOT, periodChipRows: 0 }),
    );
  });
});
