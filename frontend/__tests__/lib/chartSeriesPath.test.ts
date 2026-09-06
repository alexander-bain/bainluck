/**
 * #3659 — THE RULE: a line is drawn between observations, never across a hole.
 *
 * `chartDoesNotDrawThroughAHole.test.tsx` proves the WIRING. This proves the
 * geometry, and one arm of it matters more than all the others put together.
 *
 * ═══ THE ARM THAT MATTERS ═══
 *
 * `FuturesChart` renders on seven surfaces and nearly all of them plot healthy
 * series nearly all of the time, so the direction that breaks everything at
 * once is not "the hole didn't break" — it is "a chart with no hole changed".
 *
 * So `oldInlinePathD` below is a verbatim copy of the expression this module
 * replaced, and the healthy arm diffs against it as a STRING. Not "renders a
 * path", not "has the same number of points" — the same characters. A shape
 * assertion would go green on a rounding change or a re-ordered command that
 * moved every one of those seven charts by a pixel.
 *
 * ═══ THE THRESHOLD IS NOT RE-DERIVED HERE ═══
 *
 * Cases are built from the two production cadences `seriesFreshness` was
 * measured against (1.00h futures, 8h politics) and assert against
 * `seriesGapThresholdMs`, not against a hard-coded 6h. Pinning the number here
 * would let the caption under a plot and the break in the line above it drift
 * apart, which is the exact failure this module was split out to prevent.
 */

import { chartSeriesPath, type PlottedPoint } from "@/lib/chartSeriesPath";
import { seriesGapThresholdMs, GAP_FLOOR_MS } from "@/lib/seriesFreshness";

const HOUR = 60 * 60 * 1000;
const START = Date.UTC(2026, 7, 22, 15, 15, 0); // fixed anchor — never Date.now()

/**
 * The expression `FuturesChart` used before #3659, character for character.
 * The healthy arm's whole job is that this still describes what ships.
 */
function oldInlinePathD(points: readonly PlottedPoint[], step: boolean): string {
  return step
    ? points.map((p, i) => (i === 0 ? `M ${p.x} ${p.y}` : `H ${p.x} V ${p.y}`)).join(" ")
    : points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ");
}

/** Points at the given hour offsets, on a line that rises 1px an hour. */
function at(hours: readonly number[]): PlottedPoint[] {
  return hours.map((h) => ({ t: START + h * HOUR, x: 50 + h, y: 100 - h }));
}

describe("#3659 chartSeriesPath — a healthy series does not move", () => {
  test("hourly series: one run, zero bridges, byte-identical to the old inline path", () => {
    const points = at(Array.from({ length: 40 }, (_, i) => i));
    const { runs, bridges } = chartSeriesPath(points);

    expect(bridges).toEqual([]);
    expect(runs).toHaveLength(1);
    expect(runs[0]).toBe(oldInlinePathD(points, false));
  });

  test("step interpolation is byte-identical too", () => {
    const points = at(Array.from({ length: 40 }, (_, i) => i));
    const { runs, bridges } = chartSeriesPath(points, { step: true });

    expect(bridges).toEqual([]);
    expect(runs[0]).toBe(oldInlinePathD(points, true));
  });

  test("a SLOW but regular series is healthy — cadence is the reference, not a clock", () => {
    // The /api/politics shape: 8h between readings, forever. Every one of those
    // gaps is four times the 2h floor, and none of them is a hole, because the
    // series is behaving exactly as it always behaves.
    const points = at(Array.from({ length: 30 }, (_, i) => i * 8));
    const { runs, bridges } = chartSeriesPath(points);

    expect(bridges).toEqual([]);
    expect(runs[0]).toBe(oldInlinePathD(points, false));
  });

  test("a single skipped beat is not a hole", () => {
    // 6× the median is the threshold; one missed hourly read is 2×.
    const points = at([0, 1, 2, 4, 5, 6, 7, 8]);
    expect(chartSeriesPath(points).bridges).toEqual([]);
  });

  test("too few points to grade: drawn exactly as before, never split on a guess", () => {
    const points = at([0, 400, 800]); // 3 points, two enormous gaps, no cadence
    const { runs, bridges } = chartSeriesPath(points);

    expect(seriesGapThresholdMs(points.map((p) => p.t))).toBeNull();
    expect(bridges).toEqual([]);
    expect(runs[0]).toBe(oldInlinePathD(points, false));
  });
});

describe("#3659 chartSeriesPath — a hole is not drawn through", () => {
  // The production series, in shape: one observation, a 345.6h hole, then a
  // day of hourly readings. Measured on /api/futures/16630403/history.
  const HOLED = at([0, 345.6, ...Array.from({ length: 19 }, (_, i) => 346.6 + i)]);

  test("the hole becomes a bridge, and the runs either side stay whole", () => {
    const { runs, bridges } = chartSeriesPath(HOLED);

    expect(bridges).toHaveLength(1);
    expect(runs).toHaveLength(2);
  });

  test("no run's own span covers the hole — the solid stroke touches observations only", () => {
    const { runs } = chartSeriesPath(HOLED);
    const threshold = seriesGapThresholdMs(HOLED.map((p) => p.t))!;

    // Reconstruct which points each run drew, by x, and assert no consecutive
    // pair inside a run is further apart in TIME than the threshold.
    const byX = new Map(HOLED.map((p) => [p.x, p.t]));
    for (const d of runs) {
      const times = [...d.matchAll(/[ML] (-?[\d.]+) /g)].map((m) => byX.get(Number(m[1]))!);
      for (let i = 1; i < times.length; i += 1) {
        expect(times[i] - times[i - 1]).toBeLessThanOrEqual(threshold);
      }
    }
  });

  test("the bridge spans exactly the two observations that bracket the hole", () => {
    const { bridges } = chartSeriesPath(HOLED);
    const before = HOLED[0];
    const after = HOLED[1];

    expect(bridges[0]).toBe(`M ${before.x} ${before.y} L ${after.x} ${after.y}`);
  });

  test("an isolated observation survives as a dot, not as nothing", () => {
    // A bare `M` paints nothing, so the Aug 22 point — alone on its side of the
    // hole — would vanish from a chart it is currently visible on.
    const { runs } = chartSeriesPath(HOLED);
    const lonely = HOLED[0];

    expect(runs[0]).toBe(`M ${lonely.x} ${lonely.y} L ${lonely.x} ${lonely.y}`);
  });

  test("every point still appears somewhere — a break drops no data", () => {
    const { runs, bridges } = chartSeriesPath(HOLED);
    const drawn = [...runs, ...bridges].join(" ");
    for (const p of HOLED) expect(drawn).toContain(`${p.x} ${p.y}`);
  });

  test("three holes give three bridges and four runs", () => {
    // The measured series had gaps of 345.6h, 6.9h and 6.1h over threshold.
    const points = at([
      0, 1, 2, 3, 4, 5,
      350.6, 351.6, 352.6, 353.6,
      360.5, 361.5, 362.5, 363.5,
      369.6, 370.6, 371.6, 372.6,
    ]);
    const { runs, bridges } = chartSeriesPath(points);

    expect(bridges).toHaveLength(3);
    expect(runs).toHaveLength(4);
  });

  test("a fast series is not split by a lapse smaller than the 2h floor", () => {
    // 2-minute cadence: 6× the median is 12 minutes, and a 30-minute lapse
    // would break the line five times an hour without the floor.
    const minute = 60 * 1000;
    const points = Array.from({ length: 30 }, (_, i) => ({
      t: START + (i < 15 ? i * 2 * minute : i * 2 * minute + 30 * minute),
      x: i,
      y: i,
    }));
    const threshold = seriesGapThresholdMs(points.map((p) => p.t))!;

    expect(threshold).toBe(GAP_FLOOR_MS);
    expect(chartSeriesPath(points).bridges).toEqual([]);
  });
});

describe("#3659 chartSeriesPath — every input produces an answer", () => {
  test("no points", () => {
    expect(chartSeriesPath([])).toEqual({ runs: [], bridges: [] });
  });

  test("one point is a dot", () => {
    expect(chartSeriesPath(at([0]))).toEqual({
      runs: [`M 50 100 L 50 100`],
      bridges: [],
    });
  });

  test("unparseable stamps never split — a NaN gap is not a hole", () => {
    const points = at([0, 1, 2, 3, 4, 5]).map((p, i) =>
      i === 3 ? { ...p, t: NaN } : p,
    );
    expect(chartSeriesPath(points).bridges).toEqual([]);
  });

  test("points out of order draw the same zigzag they draw today, with no bridge", () => {
    // Handing over unsorted points is somebody else's bug; silently sorting
    // here would change healthy charts, which is the one thing this must not do.
    const points = at([0, 5, 1, 6, 2, 7, 3, 8]);
    const { runs, bridges } = chartSeriesPath(points);

    expect(bridges).toEqual([]);
    expect(runs[0]).toBe(oldInlinePathD(points, false));
  });
});
