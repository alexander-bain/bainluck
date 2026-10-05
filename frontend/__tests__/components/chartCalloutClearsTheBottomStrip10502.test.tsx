/**
 * #10502 — THE END-VALUE CALLOUT CLEARS THE PERIOD STRIP AT THE BOTTOM TOO.
 *
 * Found by ux's notice-42 walk on `/events/15323826` (NLDS, Dodgers 2–3 Braves)
 * at 390px, one page held open from first pitch to final+10 with no reload. The
 * Dodgers are home and led most of the game, so #7940 moved the inning strip to
 * the bottom, and then the series collapsed onto it: `9%` printed on `T9` live,
 * and `0%` over `B9` at the final, which reads "B9%".
 *
 * #7940's call site passed ZERO chip rows whenever the strip was at the bottom,
 * reasoning that the strip only moves down when the series is pinned UP, so the
 * label and the strip are at opposite ends. The band is chosen from the whole
 * labelled span; the callout sits where the series ENDS. A late collapse breaks
 * the reasoning on every comeback.
 *
 * Same renderer, mock and parsing as the #7134 / #5581 files, with the series
 * mirrored: high across the labels, 0% at the whistle.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("@/components/Analytics/AnalyticsProvider", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
  AnalyticsProvider: ({ children }: { children: React.ReactNode }) => children,
}));

// recharts draws NOTHING inside a ResponsiveContainer without a viewport; same
// mock, same reason, as the #5581 and #7134 files.
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

/** Fixed anchor — never `Date.now()` (gotcha #44). */
const START = Date.UTC(2026, 9, 5, 0, 0, 0);
const N = 120;

/** The specimen's shape: ~62% for four fifths of the game, then down to 0. */
function lateCollapse(n: number): number[] {
  const out: number[] = [];
  for (let i = 0; i < n; i++) {
    const t = i / (n - 1);
    out.push(t < 0.8 ? 62 + 6 * Math.sin(i * 0.7) : 62 * (1 - (t - 0.8) / 0.2));
  }
  out[out.length - 1] = 0;
  return out;
}

/**
 * The control: the identical collapse, stopped at 15%. Probed rather than
 * guessed: the axis zooms (#3973), so most stopping points put the last value
 * back on the drawn floor (20% and 30% both do) and a stop near 50% flips the
 * strip to the top. 15% keeps the bottom strip and ends the dot well above it.
 */
const CONTROL_FLOOR = 15;
function stopsAboveTheStrip(n: number): number[] {
  return lateCollapse(n).map((p, i) => (i >= Math.floor(n * 0.8) ? Math.max(p, CONTROL_FLOOR) : p));
}

/** Innings spaced so the last one staggers onto row 1 beside the right rule. */
const MINUTES: Array<[number, string]> = [
  [10, "T2"],
  [40, "T4"],
  [70, "T6"],
  [100, "B8"],
  [116, "B9"],
];

function boundaries(): PeriodBoundary[] {
  return MINUTES.map(([min, label]) => ({
    timestamp: new Date(START + min * 60_000).toISOString(),
    label,
  }));
}

function points(probs: number[]) {
  return probs.map((p, i) => ({
    timestamp: new Date(START + i * 60_000).toISOString(),
    home_probability: p / 100,
    away_probability: 1 - p / 100,
  }));
}

function render(probs: number[]) {
  return renderToStaticMarkup(
    <OddsChart
      history={[]}
      homeTeam="Dodgers"
      awayTeam="Braves"
      commenceTime={new Date(START).toISOString()}
      isLive={false}
      eventStatus="completed"
      externalTimeRange="all"
      periodBoundaries={boundaries()}
      winProbHistory={{ kalshi: points(probs) }}
      winProbSources={{
        kalshi: { display_name: "Kalshi", color: "#22c55e", type: "market", snapshot_count: probs.length },
      }}
    />,
  );
}

function plotRect(html: string): { top: number; bottom: number } {
  const m = /<clipPath id="recharts\d+-clip"><rect x="[\d.-]+" y="([\d.-]+)" height="([\d.-]+)"/.exec(html);
  if (!m) throw new Error("no plot clip rect — the chart did not lay out");
  const top = Number(m[1]);
  return { top, bottom: top + Number(m[2]) };
}

/** The callout's white plate. THROWS unless exactly one is found. */
function calloutPlate(html: string): { top: number; bottom: number } {
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

function calloutDot(html: string): number {
  const m = /<circle[^>]*cy="([\d.-]+)"[^>]*\sr="8"[^>]*>/.exec(html);
  if (!m) throw new Error("no callout glow circle — the dot is not being drawn");
  return Number(m[1]);
}

function stripBand(html: string): string {
  const m = html.match(/data-period-strip-band="([^"]*)"/);
  if (!m) throw new Error("chart did not report data-period-strip-band");
  return m[1];
}

/**
 * A bottom chip's ink. `insideBottom*` emits the BASELINE as `y` with
 * `dy="0em"` (recharts folds the row's `dy` into `y`); the glyph box is 11px
 * above it and 2px below (#5581's measurement). THROWS on any other `dy`, so a
 * recharts change to the anchor maths fails here instead of moving the ink.
 */
function bottomChips(html: string): Array<{ label: string; inkTop: number; inkBottom: number }> {
  const out: Array<{ label: string; inkTop: number; inkBottom: number }> = [];
  const re = /<text([^>]*)>\s*<tspan([^>]*)>(T2|T4|T6|B8|B9)<\/tspan>/g;
  for (const m of html.matchAll(re)) {
    const y = Number(/\sy="([\d.-]+)"/.exec(m[1])?.[1]);
    const fs = Number(/font-size:\s*([\d.]+)px/.exec(m[1])?.[1]);
    const dy = /\sdy="([^"]*)"/.exec(m[2])?.[1];
    if (!Number.isFinite(y) || !Number.isFinite(fs)) throw new Error(`chip without y/font-size: ${m[1]}`);
    if (dy !== "0em") throw new Error(`bottom chip ${m[3]} carries dy=${dy}; the ink maths assumes 0em`);
    out.push({ label: m[3], inkTop: y - fs, inkBottom: y + 2 });
  }
  return out;
}

describe("#10502 — the specimen carries the defect's shape", () => {
  test("the strip is at the BOTTOM, two rows deep, and the series ends on the floor", () => {
    // Without all three the remaining arms test nothing: a top strip is #7134's
    // case, one row is not the frame's shape, and a mid-plot finish is never lifted.
    const html = render(lateCollapse(N));
    const plot = plotRect(html);
    expect(stripBand(html)).toBe("bottom");
    const chips = bottomChips(html);
    expect(chips.map((c) => c.label).sort()).toEqual(["B8", "B9", "T2", "T4", "T6"]);
    const rows = new Set(chips.map((c) => plot.bottom - c.inkBottom));
    expect(rows.size).toBe(2);
    expect(calloutDot(html)).toBe(plot.bottom);
  });
});

describe("#10502 — the end-value callout clears a bottom strip", () => {
  test("the plate sits above the ink of every chip", () => {
    // Every chip, not just the ones beside the right rule — the band is the
    // whole chart's deepest row, the direction #7134 already chose.
    const html = render(lateCollapse(N));
    const plate = calloutPlate(html);
    for (const chip of bottomChips(html)) {
      expect({ chip: chip.label, clears: plate.bottom <= chip.inkTop + 1e-6 }).toEqual({
        chip: chip.label,
        clears: true,
      });
    }
  });

  test("the dot stays on its datum while the label lifts", () => {
    const html = render(lateCollapse(N));
    expect(calloutDot(html)).toBe(plotRect(html).bottom);
    expect(calloutPlate(html).bottom).toBeLessThan(calloutDot(html));
  });

  test("CONTROL: the same collapse stopping above the strip is not lifted", () => {
    // Same strip, same chips — only the end moved. The label stays on its dot.
    const html = render(stopsAboveTheStrip(N));
    expect(stripBand(html)).toBe("bottom");
    expect(calloutDot(html)).toBeLessThan(plotRect(html).bottom - 30);
    const plate = calloutPlate(html);
    const dot = calloutDot(html);
    expect(Math.abs((plate.top + plate.bottom) / 2 - dot)).toBeLessThan(1);
  });
});

describe("#10502 — calloutLabelCenterY with a bottom strip", () => {
  const plotTop = 15;
  const plotHeight = 250;
  const bottom = plotTop + plotHeight;

  test("lifts a floor-pinned label by one row more for each extra row", () => {
    const one = calloutLabelCenterY({ cy: bottom, plotTop, plotHeight, periodChipRows: 1, periodStripBand: "bottom" });
    const two = calloutLabelCenterY({ cy: bottom, plotTop, plotHeight, periodChipRows: 2, periodStripBand: "bottom" });
    expect(one).toBeLessThan(bottom);
    expect(one - two).toBeCloseTo(PERIOD_LABEL_ROW_HEIGHT_PX, 6);
  });

  test("never pays the bottom band for a ceiling-pinned label", () => {
    // The half of #7940 that was right: a label at the top does not move for a
    // strip at the bottom. It only comes inside the frame.
    const atTop = calloutLabelCenterY({ cy: plotTop, plotTop, plotHeight, periodChipRows: 2, periodStripBand: "bottom" });
    const noStrip = calloutLabelCenterY({ cy: plotTop, plotTop, plotHeight, periodChipRows: 0 });
    expect(atTop).toBe(noStrip);
  });

  test("an omitted side is the top strip, byte-for-byte", () => {
    for (const cy of [plotTop, 100, bottom]) {
      expect(calloutLabelCenterY({ cy, plotTop, plotHeight, periodChipRows: 2 })).toBe(
        calloutLabelCenterY({ cy, plotTop, plotHeight, periodChipRows: 2, periodStripBand: "top" }),
      );
    }
  });

  test("a plot too short to clear the strip keeps the label inside the frame", () => {
    const short = 30;
    const y = calloutLabelCenterY({ cy: plotTop + short, plotTop, plotHeight: short, periodChipRows: 2, periodStripBand: "bottom" });
    expect(y).toBeLessThanOrEqual(plotTop + short);
    expect(y).toBeGreaterThanOrEqual(plotTop);
  });
});
