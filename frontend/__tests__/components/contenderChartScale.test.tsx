/**
 * #2451 — THE TITLE-RACE CHART GETS A SCALE A READER CAN USE.
 *
 * Alex, on the TO WIN THE TITLE chart on `/tournaments/us-open`:
 *
 *   > renders three contender lines inside roughly the bottom 15% of the plot
 *   > area, with **no y-axis labels at all**. Alcaraz 34.5%, Zverev 23.5%,
 *   > Shelton 9.3% — all visually flat and indistinguishable.
 *
 * and the instruction, which is the constraint this file exists to hold:
 *
 *   > **Fix the scale, do not smooth the line.**
 *
 * ## The arithmetic, on his three numbers
 *
 * The old y-axis was a hard 0–100. On the 96px phone plot that puts Alcaraz at
 * 33px off the floor, Zverev at 23px and Shelton at 9px — the whole title race
 * inside the bottom third, the ten-point Alcaraz–Zverev gap drawn as 10px, and
 * the top two thirds of the card permanently blank.
 *
 * `chartCeiling` steps the TOP to 0.5 for that field. The same three lines land
 * at 69%, 47% and 19% of the plot height. The gap he could not see is now half
 * the plot, and no line moved relative to any other — the shape of the race is
 * identical, which is what "do not smooth" requires.
 *
 * ## Zero is not negotiable, and that is a tested property
 *
 * The classic chart lie is a cropped baseline. This axis is always anchored at
 * 0, so a line's height stays proportional to the probability; only the top
 * moves. `never crops the baseline` below is the guard on that, and it matters
 * more than the legibility one, because the legibility fix is what creates the
 * temptation.
 *
 * ## And the steps are coarse ON PURPOSE
 *
 * A continuous fit-to-max would rescale the plot every time the leader moved a
 * point, and an axis that changes daily makes movement unreadable — the exact
 * inverse of the standing ruling that movement is the product. Four steps
 * (10/25/50/100) means the axis holds still for weeks and moves when the shape
 * of the race genuinely changes. `holds still across ordinary movement` pins
 * that, because it is the property a well-meaning "just fit the data" rewrite
 * would delete.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import ContenderChart from "@/components/tournament/ContenderChart";
import {
  chartCeiling,
  chartGeometry,
  chartYLabels,
  seriesPoints,
  type ChartSeries,
} from "@/lib/contenderChart";
import type { TournamentRow } from "@/lib/tournament";

const HEIGHT = 96;
const WIDTH = 320;

function series(
  entityKey: string,
  displayName: string,
  probability: number,
  history: number[]
): ChartSeries {
  return {
    entityKey,
    displayName,
    color: "#112233",
    probability,
    isLive: true,
    points: history.map((p, i) => ({
      date: `2026-08-${String(20 + i).padStart(2, "0")}`,
      probability: p,
    })),
  } as ChartSeries;
}

/** Alex's three, verbatim off the live board. */
const LIVE_FIELD = [
  series("alcaraz", "Carlos Alcaraz", 0.345, [0.32, 0.345]),
  series("zverev", "Alexander Zverev", 0.235, [0.24, 0.235]),
  series("shelton", "Ben Shelton", 0.093, [0.09, 0.093]),
];

/** Where a series' last point sits, as a fraction of plot height above the floor. */
function heightFraction(entry: ChartSeries, all: ChartSeries[]): number {
  const geometry = chartGeometry(all, "ALL", WIDTH, HEIGHT);
  const drawn = seriesPoints(entry, geometry, "ALL");
  const last = drawn.split(" ").pop() ?? "";
  const y = Number(last.split(",")[1]);
  return (HEIGHT - y) / HEIGHT;
}

function row(entityKey: string, name: string, probability: number): TournamentRow {
  return {
    entity_key: entityKey,
    display_name: name,
    probability,
    probability_is_live: true,
    // `chartSeriesFor` reads `trend`, not `history`.
    trend: [
      { date: "2026-08-20", probability: probability - 0.02 },
      { date: "2026-08-21", probability },
    ],
  } as unknown as TournamentRow;
}

describe("#2451 — the contender chart's y-axis", () => {
  it("lifts the field off the floor on Alex's own three numbers", () => {
    expect(chartCeiling(LIVE_FIELD, "ALL")).toBe(0.5);

    const alcaraz = heightFraction(LIVE_FIELD[0], LIVE_FIELD);
    const zverev = heightFraction(LIVE_FIELD[1], LIVE_FIELD);
    const shelton = heightFraction(LIVE_FIELD[2], LIVE_FIELD);

    // Before the fix these were 0.345 / 0.235 / 0.093 — the whole race inside
    // the bottom third of the plot.
    expect(alcaraz).toBeCloseTo(0.69, 2);
    expect(zverev).toBeCloseTo(0.47, 2);
    expect(shelton).toBeCloseTo(0.186, 2);

    // The leader is above the middle of the plot, which is the legibility claim
    // in one assertion.
    expect(alcaraz).toBeGreaterThan(0.5);
  });

  /**
   * THE SHAPE IS UNTOUCHED. "Fix the scale, do not smooth the line" — a rescale
   * multiplies every height by the same constant, so every RATIO between two
   * lines survives it exactly. A fix that changed a ratio would have changed
   * the race.
   */
  it("rescales without changing the race", () => {
    const [a, z, s] = LIVE_FIELD.map((entry) => heightFraction(entry, LIVE_FIELD));
    /* RELATIVE error, not absolute. `seriesPoints` emits `toFixed(1)` on a
       96-unit viewBox, so a height carries up to 0.05 units of quantisation —
       which is a tenth of a percent on Alcaraz's line and half a percent on
       Shelton's, because his is the short one. An absolute `toBeCloseTo` on the
       RATIO therefore tightens as the denominator shrinks and would be testing
       the rounding rather than the rescale. 1% is comfortably inside the
       drawing resolution and nowhere near a real change of shape. */
    const off = (got: number, want: number) => Math.abs(got / want - 1);
    expect(off(a / z, 0.345 / 0.235)).toBeLessThan(0.01);
    expect(off(z / s, 0.235 / 0.093)).toBeLessThan(0.01);
  });

  /**
   * ZERO IS NOT NEGOTIABLE. The temptation a legibility fix creates is to crop
   * the bottom as well as move the top, which is the chart lie. A player at 0
   * must draw on the floor at every ceiling.
   */
  it("never crops the baseline", () => {
    for (const ceiling of [0.1, 0.25, 0.5, 1]) {
      const field = [
        series("top", "Top", ceiling * 0.8, [ceiling * 0.8, ceiling * 0.8]),
        series("zero", "Zero", 0, [0, 0]),
      ];
      const floor = heightFraction(field[1], field);
      expect(floor).toBe(0);
      // And the labels always end at 0%, whatever the top is.
      expect(chartYLabels(chartCeiling(field, "ALL")).at(-1)).toEqual({
        probability: 0,
        label: "0%",
      });
    }
  });

  /**
   * COARSE STEPS. The axis must not follow the leader point by point, or
   * movement becomes unreadable — a line that rose would be redrawn at the same
   * height on a taller axis and look flat, which is the failure Alex reported
   * arriving by a different road.
   */
  it("holds still across ordinary movement", () => {
    const at = (p: number) => chartCeiling([series("x", "X", p, [p, p])], "ALL");
    // Everything from 22% to 43% shares one ceiling — weeks of a title race.
    expect(at(0.22)).toBe(0.5);
    expect(at(0.345)).toBe(0.5);
    expect(at(0.43)).toBe(0.5);
    // The whole ladder, so a rewrite to a continuous fit fails here.
    expect(at(0.05)).toBe(0.1);
    expect(at(0.2)).toBe(0.25);
    expect(at(0.9)).toBe(1);
    expect(at(1)).toBe(1);
  });

  /**
   * ═══ #3032: THE LADDER HAD A CLIFF IN IT ═══
   *
   * The 50→100 gap is the one leader range where #2451's fix stopped paying,
   * and it bit precisely when a tournament has a clear favourite. Measured on
   * the live men's board on 2026-09-05, before this: Alcaraz 44.5% wanted
   * 51.2%, landed on 100, and the whole title race drew in the bottom half.
   */
  it("gives a mid-forties favourite an axis instead of the bottom half", () => {
    const field = [
      series("alcaraz", "Carlos Alcaraz", 0.445, [0.122, 0.445]),
      series("zverev", "Alexander Zverev", 0.2, [0.107, 0.2]),
      series("fritz", "Taylor Fritz", 0.103, [0.027, 0.103]),
    ];
    expect(chartCeiling(field, "ALL")).toBe(0.75);

    const alcaraz = heightFraction(field[0], field);
    // 0.445 of a 100 axis was 0.445 of the plot; on 75 it is 0.593.
    expect(alcaraz).toBeCloseTo(0.593, 2);
    expect(alcaraz).toBeGreaterThan(0.5);

    // And the step is only allowed to exist because the axis says what it is.
    expect(chartYLabels(0.75).map((entry) => entry.label)).toEqual(["75%", "38%", "0%"]);
  });

  /** The new step's two edges, so a later re-tune cannot quietly reopen the gap. */
  it("holds the 75 step from 44% to 65%", () => {
    const at = (p: number) => chartCeiling([series("x", "X", p, [p, p])], "ALL");
    expect(at(0.43)).toBe(0.5); // the last value the 50 step holds
    expect(at(0.44)).toBe(0.75);
    expect(at(0.65)).toBe(0.75); // the last value the 75 step holds
    expect(at(0.66)).toBe(1);
  });

  /** A near-certain favourite still gets the full axis, not a 115% one. */
  it("never proposes a ceiling above 100%", () => {
    const field = [series("sure", "Sure Thing", 0.99, [0.97, 0.99])];
    expect(chartCeiling(field, "ALL")).toBe(1);
    expect(heightFraction(field[0], field)).toBeCloseTo(0.99, 3);
  });

  /**
   * THE LABELS ARE THE OTHER HALF, not a decoration on it. A moving ceiling
   * with no labels would be strictly WORSE than the fixed one it replaced,
   * because the reader would have no way to know the top had changed. Asserted
   * against rendered markup, and against the rules as well as the numbers.
   */
  it("prints the axis it is drawing", () => {
    const html = renderToStaticMarkup(
      <ContenderChart
        rows={[
          row("alcaraz", "Carlos Alcaraz", 0.345),
          row("zverev", "Alexander Zverev", 0.235),
          row("shelton", "Ben Shelton", 0.093),
        ]}
        draw="mens-singles"
        selection={["alcaraz", "zverev", "shelton"]}
        onToggle={() => {}}
      />
    );

    expect(html).toContain('data-testid="chart-y-axis"');
    const labels = [...html.matchAll(/data-testid="chart-y-label"[^>]*>([^<]*)</g)].map(
      (m) => m[1].trim()
    );
    expect(labels).toEqual(["50%", "25%", "0%"]);

    // A rule per label, so a height can be carried across to a number.
    const rules = html.match(/data-testid="chart-y-rule"/g) ?? [];
    expect(rules).toHaveLength(3);

    // And the ceiling it used is on the DOM, so a capture can be read back.
    expect(html).toContain('data-ceiling="0.5"');
  });

  /** The 100% case still says 100%, so nothing about a full axis is implicit. */
  it("labels a full axis as a full axis", () => {
    expect(chartYLabels(1).map((entry) => entry.label)).toEqual(["100%", "50%", "0%"]);
    expect(chartYLabels(0.1).map((entry) => entry.label)).toEqual(["10%", "5%", "0%"]);
  });
});
