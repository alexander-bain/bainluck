/**
 * WHERE MAY A LINE BE DRAWN, AND WHERE IS IT ONLY GUESSING?
 *
 * #3659 (charts epic #2911), the second half of #2961. #2961 made a chart *say*
 * it had a hole. This stops it *drawing through* one.
 *
 * ═══ THE MEASUREMENT THIS EXISTS FOR ═══
 *
 * `GET /api/futures/16630403/history` ("Hantavirus pandemic in 2026?"), outcome
 * "Yes", re-read from production 2026-09-06 ~23:0xZ — the third reading of this
 * series in a day, and it had moved twice before, which is why it was re-read:
 *
 *   n = 359      span = 713.9h      median gap = 1.00h      newest = 6.13h old
 *   gaps over threshold: 345.6h, 6.9h, 6.1h
 *
 * On the rendered window that 345.6h hole is not an incident inside the chart —
 * it is very nearly the whole chart, ~93% of the horizontal space, drawn as one
 * confident flat stroke at 3% in the same colour and the same weight as the 345
 * real observations either side of it.
 *
 * ═══ WHY THIS IS THE EXISTING RULING, NOT A NEW ONE ═══
 *
 * The `Sparkline` kernel header records chart ruling 1: *NO smoothing — raw
 * `M/L` segments between real observations. No bezier.* The reason given for
 * banning the bezier is that a curve invents values between observations. A
 * straight segment across 14.4 days invents 14.4 days of them. The letter of
 * the ruling was satisfied; its purpose was not.
 *
 * ═══ WHY A BRIDGE AND NOT A GAP ═══
 *
 * The obvious fix is to stop the path and start a new one, and on this series it
 * would be actively misleading: nineteen points in a sliver at the right edge,
 * one lonely point at the left, and nothing in between reads as a chart that
 * failed to render, not as a chart being careful. `lib/contenderChart.ts`
 * (UX-P207) hit the same wall from the axis side and its answer was to make the
 * hole *legible as a hole* rather than to leave a void.
 *
 * So the hole is spanned by a separate faint dotted path. The eye stays
 * connected; the claim does not survive. The two are different SVG elements
 * with different dash patterns and different opacities, so no restyle can
 * quietly collapse one into the other — and the solid stroke, the thing a
 * reader reads as data, touches nothing but real observations.
 *
 * ═══ THE DIRECTION THAT BREAKS SEVEN SURFACES AT ONCE ═══
 *
 * `FuturesChart` renders on `/futures/[id]`, `/categories/golf`,
 * `/sport/[sport]/[league]`, `TeamSeasonJourney`, `WinnerEvolutionChart`,
 * `SettledPathChart` and `RaceToTitleChart`. The dangerous arm is not the holed
 * series — it is the healthy one, because a healthy series is what nearly every
 * one of those surfaces plots nearly all of the time.
 *
 * So the contract is exact and it is guarded as a string, not as a shape: a
 * series with no hole yields ONE run whose `d` is byte-for-byte the string the
 * old inline `.map().join(" ")` produced, and ZERO bridges. Not "equivalent" —
 * identical. `chartSeriesPath.test.ts` re-implements the old expression and
 * diffs against it.
 *
 * ═══ WHAT DECIDES A HOLE ═══
 *
 * Not a number of hours — `seriesFreshness`'s header sets out at length why no
 * N works — but the series' own cadence, via `seriesGapThresholdMs`. The same
 * threshold that writes the caption under the plot breaks the line above it, so
 * the two can never disagree about which interval they are describing.
 *
 * Pure and total, like the module it borrows its rule from. Every input — no
 * points, one point, unparseable stamps, points out of order — produces an
 * answer, because the caller is a render path and a throw there is a blank page.
 */

import { seriesGapThresholdMs } from "@/lib/seriesFreshness";

/** A point already through both scales: `t` is its real instant, `x`/`y` its pixels. */
export interface PlottedPoint {
  t: number;
  x: number;
  y: number;
}

export interface ChartSeriesPath {
  /**
   * One `d` string per run of observations with no hole in it. Drawn solid —
   * this is the data. A run of a single point is emitted as a zero-length
   * subpath (`M x y L x y`), which SVG paints as a round dot under
   * `stroke-linecap="round"`: an isolated observation stays visible instead of
   * disappearing, which is what a bare `M` would do to it.
   */
  runs: string[];
  /**
   * One `d` string per hole, each spanning exactly the two observations that
   * bracket it. Drawn faint and dotted — this is not data.
   */
  bridges: string[];
}

/** `L x y`, or the two-stroke step idiom the caller may have asked for. */
function segmentTo(p: PlottedPoint, step: boolean): string {
  return step ? `H ${p.x} V ${p.y}` : `L ${p.x} ${p.y}`;
}

function runFrom(points: readonly PlottedPoint[], step: boolean): string {
  const head = `M ${points[0].x} ${points[0].y}`;
  if (points.length === 1) {
    // Zero-length subpath: a dot, not nothing. Deliberately NOT the step idiom —
    // `H` then `V` to the point we are already on is the same zero length said
    // twice, and the plain form is what every renderer agrees to paint.
    return `${head} L ${points[0].x} ${points[0].y}`;
  }
  return [head, ...points.slice(1).map((p) => segmentTo(p, step))].join(" ");
}

/**
 * Split a plotted series into the runs that may be drawn and the holes that may
 * not.
 *
 * `points` are used in the order given — the order the caller is plotting them
 * in — and are never re-sorted here. A renderer that hands over unsorted points
 * already draws a zigzag today, and silently fixing that would change healthy
 * charts, which is the one thing this must not do. Only a POSITIVE gap wider
 * than the threshold splits, so a backwards step (the symptom of unsorted
 * input) can never manufacture a bridge.
 */
export function chartSeriesPath(
  points: readonly PlottedPoint[],
  { step = false }: { step?: boolean } = {},
): ChartSeriesPath {
  if (points.length === 0) return { runs: [], bridges: [] };
  if (points.length === 1) return { runs: [runFrom(points, step)], bridges: [] };

  const threshold = seriesGapThresholdMs(points.map((p) => p.t));

  // No cadence to grade against — too few points, or none of them datable. The
  // honest move is to draw exactly what we drew yesterday rather than to invent
  // a threshold, so this returns the old single run unchanged.
  if (threshold === null) return { runs: [runFrom(points, step)], bridges: [] };

  const runs: string[] = [];
  const bridges: string[] = [];
  let current: PlottedPoint[] = [points[0]];

  for (let i = 1; i < points.length; i += 1) {
    const gap = points[i].t - points[i - 1].t;
    if (Number.isFinite(gap) && gap > threshold) {
      runs.push(runFrom(current, step));
      bridges.push(
        `M ${points[i - 1].x} ${points[i - 1].y} ${segmentTo(points[i], step)}`,
      );
      current = [points[i]];
    } else {
      current.push(points[i]);
    }
  }
  runs.push(runFrom(current, step));

  return { runs, bridges };
}
