/**
 * Single probability chart scale & three-way soccer rule across the website
 * (#12750, Rulings 201, 202-A, and 211-A — web twin of `ChartScaleRule201.swift`).
 *
 * One scale rule everywhere:
 *   1. Two-team games (`NFL`, `NBA`, `CFB`, `CBB`, `MLB`, `NHL`, `Tennis`, `MMA`, etc.):
 *      fitted vertical window from the very first reading (`minSpan = 20` pts).
 *   2. Soccer / draw-priced three-way games (`sportPricesADraw`):
 *      full `0` to `100` scale, drawing all three lines — Home (home team colour),
 *      Draw (`#94A3B8`, the lighter grey the headline uses), and Away (away team
 *      colour, disambiguated via Ruling 197).
 *   3. Golf, futures, and many-way markets:
 *      `0` to the stepped top value shown (`ceilingForMax` / `chartYTicks`).
 */

import { ceilingForMax, chartYTicks } from "@/lib/chartCeiling";
import { awayIsTheComplement, sportPricesADraw } from "@/lib/drawPricedWinner";
import {
  computeWinProbYAxis,
  FULL_WIN_PROB_Y_AXIS,
  type WinProbYAxis,
} from "@/lib/eventKeyStats";
import { HEADLINE_STYLE_199 } from "@/lib/headlineModel199";

/** Ruling 211-A: Draw is the quiet line, using the exact lighter grey from the headline (`#94A3B8`). */
export const SOCCER_DRAW_LINE_HEX = HEADLINE_STYLE_199.drawTextInk;

export interface ThreeWayProbabilitySample {
  home: number;
  draw: number;
  away: number;
}

/**
 * Resolves the Y-axis window and ticks for a single-game win-probability chart
 * (`OddsChart`). Three-way / draw-priced matches always keep `[0, 100]`;
 * two-team matches fit movement from the first reading (`minSpan = 20`).
 */
export function gameChartYAxis(
  values: number[],
  mustShow: number[] = [],
  options?: { threeWay?: boolean },
): WinProbYAxis {
  if (options?.threeWay) {
    return FULL_WIN_PROB_Y_AXIS;
  }
  return computeWinProbYAxis(values, mustShow);
}

/**
 * Ruling 202-A: `0` to a stepped ceiling (`[0.10, 0.15, 0.25, 0.50, 0.75, 1.00]`)
 * above the highest probability shown (`maxProb` in `0..1`).
 */
export function manyWayChartCeiling(maxProb: number): number {
  return ceilingForMax(maxProb);
}

/**
 * Clean integer Y-axis ticks (`0..100` percentages) for a `0..ceiling` (`0..1`)
 * many-way / golf / futures chart.
 */
export function manyWayChartYTicks(ceiling: number): number[] {
  return chartYTicks(ceiling).map((t) => Math.round(t.pct * ceiling * 100));
}

/**
 * Extracts a genuine 3-way `{ home, draw, away }` sample (`0..1`) from a history
 * point on a draw-priced sport (`sportPricesADraw(sportKey)`), or `null` when
 * the point carries only a 2-way complement (`home + away ≈ 1` with no `draw`)
 * or lacks an independent away reading.
 */
export function extractThreeWaySample(
  point: {
    home_probability?: number | null;
    away_probability?: number | null;
    draw_probability?: number | null;
  },
  sportKey: string | null | undefined,
): ThreeWayProbabilitySample | null {
  if (!sportPricesADraw(sportKey)) return null;
  const home = point.home_probability;
  const away = point.away_probability;
  const explicitDraw = point.draw_probability;

  if (
    typeof home !== "number" ||
    !Number.isFinite(home) ||
    typeof away !== "number" ||
    !Number.isFinite(away)
  ) {
    return null;
  }

  if (typeof explicitDraw === "number" && Number.isFinite(explicitDraw)) {
    return {
      home: Math.min(1, Math.max(0, home)),
      draw: Math.min(1, Math.max(0, explicitDraw)),
      away: Math.min(1, Math.max(0, away)),
    };
  }

  // Sportsbook 3-way consensus de-vigs across all three outcomes so `home + away < 0.99`
  // and `1 - home - away` is the genuine draw probability (#1011 / #6238).
  if (awayIsTheComplement(away, home, sportKey)) {
    return null;
  }
  const derivedDraw = 1 - home - away;
  if (!Number.isFinite(derivedDraw) || derivedDraw < 0 || derivedDraw > 1) {
    return null;
  }
  return {
    home: Math.min(1, Math.max(0, home)),
    draw: Math.min(1, Math.max(0, derivedDraw)),
    away: Math.min(1, Math.max(0, away)),
  };
}
