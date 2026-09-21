/**
 * #7839 — a gridline must be labelled with the value it is actually drawn at.
 *
 * `FuturesChart` drew five rules at `[0, .25, .5, .75, 1]` of the axis top and
 * printed `Math.round(top * pct * 100)%` on each. On a 15% axis that prints
 * `0 / 4 / 8 / 11 / 15` over rules at `0 / 3.75 / 7.5 / 11.25 / 15`: two of the
 * five labels are wrong, in opposite directions, so the grid reads as a
 * non-uniform ladder and a reader interpolating between the bottom two rules on
 * the 10% frame is out by a fifth.
 *
 * The property this file pins is the one the defect broke, and it is the only
 * one worth pinning: FOR EVERY REACHABLE AXIS TOP, EVERY PRINTED LABEL EQUALS
 * ITS OWN POSITION. Not "the labels are integers" (the old ones were), and not
 * a fixed tick count (the count is now allowed to follow the step).
 *
 * The reachable population is closed and small, so it is enumerated rather than
 * sampled — `CEILING_STEPS` under `fieldCeiling`, and `computeZoomBound`'s
 * multiples of 5% under `allowZoom` (`TeamSeasonJourney`).
 */
import {
  CEILING_STEPS,
  Y_TICK_MAX_INTERVALS,
  Y_TICK_MIN_INTERVALS,
  chartYTicks,
} from "@/lib/chartCeiling";
import { computeZoomBound } from "@/lib/chartZoom";

/** Every axis top `resolveYAxisMax` can hand the renderer. */
function reachableTops(): number[] {
  const tops = new Set<number>(CEILING_STEPS);
  tops.add(1); // fixedYAxis
  // canZoomSeries gates the zoom on dataMax < 0.5.
  for (let dataMax = 0.005; dataMax < 0.5; dataMax += 0.005) {
    tops.add(Math.round(computeZoomBound(dataMax) * 1e6) / 1e6);
  }
  return [...tops].sort((a, b) => a - b);
}

/** Tops that the whole-percent ladder covers — everything but the fallback. */
const LADDER_TOPS = [0.1, 0.15, 0.25, 0.5, 0.75, 1];

describe("#7839 chartYTicks: the label names the line it sits on", () => {
  it.each(reachableTops())("top %p: every label equals its own position", (top) => {
    const ticks = chartYTicks(top);
    for (const { pct, label } of ticks) {
      const printed = Number(label.replace("%", ""));
      const drawnAt = top * 100 * pct;
      // The fallback ladder (35/45/55% zoom bounds) is allowed ONE rounded
      // middle label — the `chartYLabels` arrangement it falls back to. Nothing
      // else may round at all.
      const tolerance = LADDER_TOPS.includes(top) ? 1e-9 : 0.5;
      expect(
        `top ${top * 100}% label ${label} drawn at ${drawnAt.toFixed(4)}%`
      ).toBe(
        Math.abs(printed - drawnAt) <= tolerance
          ? `top ${top * 100}% label ${label} drawn at ${drawnAt.toFixed(4)}%`
          : `top ${top * 100}% label ${label} drawn at ${printed.toFixed(4)}%`
      );
    }
  });

  it.each(LADDER_TOPS)("top %p: labels are whole percents, no rounding at all", (top) => {
    for (const { pct, label } of chartYTicks(top)) {
      expect(label).toMatch(/^\d+%$/);
      expect(top * 100 * pct).toBeCloseTo(Number(label.replace("%", "")), 9);
    }
  });

  it("keeps the 0/25/50/75/100 axis every fixedYAxis call site draws today", () => {
    // SettledPathChart, RaceToTitleChart and the futures detail page all land
    // here. #2451 and #3032 tuned this shape; the repair must not move it.
    expect(chartYTicks(1).map((t) => t.label)).toEqual([
      "0%",
      "25%",
      "50%",
      "75%",
      "100%",
    ]);
    expect(chartYTicks(1).map((t) => t.pct)).toEqual([0, 0.25, 0.5, 0.75, 1]);
  });

  it("repairs the two frames the issue photographed", () => {
    // /futures/59165099 at 390px, both ranges.
    expect(chartYTicks(0.15).map((t) => t.label)).toEqual(["0%", "5%", "10%", "15%"]);
    expect(chartYTicks(0.1).map((t) => t.label)).toEqual([
      "0%",
      "2%",
      "4%",
      "6%",
      "8%",
      "10%",
    ]);
  });

  it("always spans the full axis, floor first, ceiling last", () => {
    for (const top of reachableTops()) {
      const ticks = chartYTicks(top);
      expect(ticks[0].pct).toBe(0);
      expect(ticks[ticks.length - 1].pct).toBe(1);
      expect(ticks[0].label).toBe("0%");
      // Strictly ascending, so no two rules share a position.
      for (let i = 1; i < ticks.length; i++) {
        expect(ticks[i].pct).toBeGreaterThan(ticks[i - 1].pct);
      }
    }
  });

  it("stays inside the density the chart already had", () => {
    for (const top of reachableTops()) {
      const n = chartYTicks(top).length - 1; // intervals
      // The fallback is halves (2 intervals) by construction; the ladder is
      // bounded so a large step cannot thin a 600px plot to one middle rule.
      expect(n).toBeGreaterThanOrEqual(2);
      expect(n).toBeLessThanOrEqual(Y_TICK_MAX_INTERVALS);
      if (LADDER_TOPS.includes(top)) {
        expect(n).toBeGreaterThanOrEqual(Y_TICK_MIN_INTERVALS);
      }
    }
  });

  it("POSITIVE CONTROL: the old fixed-quarters ladder fails this file", () => {
    // Guards against the assertions above going vacuous. This is what the
    // renderer did before #7839, reproduced exactly.
    const oldTicks = (top: number) =>
      [0, 0.25, 0.5, 0.75, 1].map((pct) => ({
        pct,
        label: `${Math.round(top * pct * 100)}%`,
      }));
    const offenders = LADDER_TOPS.filter((top) =>
      oldTicks(top).some(
        ({ pct, label }) => Math.abs(Number(label.replace("%", "")) - top * 100 * pct) > 1e-9
      )
    );
    // 10/15/25/50/75 all lied; only the 100% axis was already honest.
    expect(offenders).toEqual([0.1, 0.15, 0.25, 0.5, 0.75]);
  });

  it("degenerate tops do not throw or emit a broken axis", () => {
    for (const bad of [0, -1, NaN, Infinity]) {
      const ticks = chartYTicks(bad);
      expect(ticks.length).toBeGreaterThan(0);
      expect(ticks[0].label).toBe("0%");
    }
  });
});
