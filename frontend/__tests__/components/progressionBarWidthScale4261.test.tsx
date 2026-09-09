// #4261: the Tournament Progression card says "Bar width = probability". It has
// to draw one.
//
// The bar scale was hardcoded to a column max of 40% (`sqrt(p)/sqrt(0.4)`), so
// every probability at or above 0.4 clamped to a full-width bar. Golf's "Make
// Cut" column lives entirely above 0.4: on production (2026-09-09, Amgen Irish
// Open, 390px) all forty rows — 87%, 84%, 80% … 66% — drew the identical block,
// and an 87% row was pixel-identical to a 66% row apart from the numeral.
//
// This suite is the guard for that class, and it asserts on the RENDERED bar,
// not on the helper: a scaling function that returns different numbers proves
// nothing about the widths the reader sees.
//
// It also pins the near-miss. Keeping the square root and merely re-basing it
// on the table's own max draws that same band at 100 / 98 / 96 / 93 / 87 — a
// different formula and the same screen. "Different numbers" is not the bar;
// "visibly different bars in the band the reader is looking at" is.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

jest.mock("@/hooks/useAnalytics", () => ({
  useAnalytics: () => ({ track: () => {} }),
}));

import TournamentProgressionTable, {
  barWidth,
  BAR_SCALE_FLOOR,
} from "../../components/TournamentProgressionTable";
import type { ProgressionResponse } from "../../lib/types";

/** The band the old scale saturated: everything here clamped to one width. */
const SATURATING_BAND = [0.87, 0.8, 0.73, 0.66, 0.55, 0.4];

/** The old formula, kept verbatim so the guard can prove it fails on it. */
function legacyBarWidth(p: number): number {
  return Math.min(100, (Math.sqrt(p) / Math.sqrt(0.4)) * 100);
}

function golfTable(makeCut: number[], win?: number[]): ProgressionResponse {
  return {
    sport: "golf",
    tournament_name: "Amgen Irish Open",
    stages: [
      { key: "make_cut", label: "Make Cut", order: 0, market_id: null, market_name: null, resolved: false },
      { key: "win", label: "Win", order: 1, market_id: null, market_name: null, resolved: false },
    ],
    participants: makeCut.map((p, i) => ({
      name: `Golfer ${i + 1}`,
      team_id: null,
      logo_url: null,
      primary_color: null,
      conference: null,
      region: null,
      seed: null,
      record: null,
      probabilities: { make_cut: p, win: win?.[i] ?? 0.02 },
      changes_24h: {},
      status: {},
      sources_data: {},
    })),
  };
}

/** Every inline bar width in render order, as numbers. */
function renderedBarWidths(data: ProgressionResponse): number[] {
  const html = renderToStaticMarkup(<TournamentProgressionTable data={data} pageType="golf" />);
  return Array.from(html.matchAll(/width:\s*([0-9.]+)%/g)).map((m) => parseFloat(m[1]));
}

describe("#4261 — the progression bar encodes probability at the width the reader sees", () => {
  it("draws different widths for the golf numbers that used to collapse into one", () => {
    const widths = renderedBarWidths(golfTable([0.87, 0.66], [0.05, 0.03]));
    // Two rows × two stage columns.
    expect(widths).toHaveLength(4);
    const [makeCutTop, , makeCutLower] = widths;
    expect(makeCutTop).toBeGreaterThan(makeCutLower);
    // Not merely different by a rounding hair: visibly different on a phone.
    expect(makeCutTop - makeCutLower).toBeGreaterThan(5);
  });

  it("positive control: the old scale collapsed that whole band to one width", () => {
    const legacy = SATURATING_BAND.map(legacyBarWidth);
    expect(new Set(legacy).size).toBe(1);
    expect(legacy[0]).toBe(100);
    // …and the shipped scale does not.
    const scaled = SATURATING_BAND.map((p) => barWidth(p, Math.max(...SATURATING_BAND)));
    expect(new Set(scaled).size).toBe(SATURATING_BAND.length);
  });

  it("keeps the caption honest: the caption is present AND the widths vary", () => {
    const data = golfTable(SATURATING_BAND);
    const html = renderToStaticMarkup(<TournamentProgressionTable data={data} pageType="golf" />);
    expect(html).toContain("Bar width = probability");
    const widths = Array.from(html.matchAll(/width:\s*([0-9.]+)%/g)).map((m) => parseFloat(m[1]));
    const makeCutWidths = widths.filter((_, i) => i % 2 === 0);
    expect(makeCutWidths).toHaveLength(SATURATING_BAND.length);
    expect(new Set(makeCutWidths).size).toBe(SATURATING_BAND.length);
  });

  it("is monotone in probability, across columns as well as within one", () => {
    // A 12% Win bar must never be drawn as wide as an 87% Make Cut bar: one
    // scale for the whole table, so bigger number ⇒ wider bar everywhere.
    const widths = renderedBarWidths(golfTable([0.87, 0.5], [0.12, 0.027]));
    const [topCut, topWin, lowerCut, lowerWin] = widths;
    expect(topCut).toBeGreaterThan(lowerCut);
    expect(lowerCut).toBeGreaterThan(topWin);
    expect(topWin).toBeGreaterThan(lowerWin);
  });

  it("draws no bar for a zero or absent probability", () => {
    expect(barWidth(0, 0.87)).toBe(0);
    expect(barWidth(null, 0.87)).toBe(0);
    // A row of zeroes renders no inline bar at all.
    const html = renderToStaticMarkup(
      <TournamentProgressionTable data={golfTable([0], [0])} pageType="golf" />,
    );
    expect(html).not.toMatch(/width:\s*[0-9.]+%/);
  });

  it("a table of noise-level numbers does not draw full-width bars", () => {
    // Without the floor, scaling to the table's own max would make a 0.4%
    // favourite look like a lock.
    const widths = renderedBarWidths(golfTable([0.004, 0.002], [0.001, 0.0005]));
    expect(Math.max(...widths)).toBeLessThan(50);
    expect(barWidth(BAR_SCALE_FLOOR, 0.0001)).toBe(100);
  });

  it("steps visibly across the production band, not by a hair", () => {
    // The real Amgen Irish Open "Make Cut" numbers, read off the production
    // progression payload on 2026-09-09: these are the rows a phone shows.
    const band = [0.873, 0.84, 0.796, 0.757, 0.66];
    const widths = renderedBarWidths(golfTable(band)).filter((_, i) => i % 2 === 0);
    expect(widths).toHaveLength(band.length);
    expect(widths[0] - widths[band.length - 1]).toBeGreaterThan(20);
    // Control for the near-miss: square root re-based on the same table max
    // spans under 15 points across that band, which is the complaint again.
    const sqrtScaled = band.map((p) => Math.sqrt(p / band[0]) * 100);
    expect(sqrtScaled[0] - sqrtScaled[band.length - 1]).toBeLessThan(15);
  });

  it("scales to the table it is given, not to a constant", () => {
    // The same probability is drawn wider in a table whose leader is smaller —
    // that is what "scaled to this table" means, and it is why the helper takes
    // the max as an argument instead of closing over one.
    expect(barWidth(0.3, 0.9)).toBeLessThan(barWidth(0.3, 0.4));
  });
});
