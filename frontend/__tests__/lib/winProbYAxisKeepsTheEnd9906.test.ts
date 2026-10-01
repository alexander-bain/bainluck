// #9906 — where a line ENDS is always on the plot.
//
// MEASURED ON PRODUCTION, 2026-09-30 19:05Z, `/api/events/15320754/history`
// (Bublik / Shang v Cerundolo / Rinderknech, venue-settled, Bublik / Shang won).
// One plotted series, Kalshi: 272 samples between 34.5% and 46.0%, then the
// settle point at 100.0 (`evidence: final`). p2/p98 = 37.5/44.5.
//
// The page drew the axis [30, 55] while the line ended with a stroke to 100%
// and the callout printed `100%` at the top edge — the settle stroke off the
// plot, the result outside the chart. Rule 1b (#7837) takes the true extremes
// only when the core keeps half the height; here the core is 7 points of 65.5,
// so the percentile window stood and the END was treated as an outlier.

import { readFileSync } from "fs";
import { join } from "path";

import { computeWinProbYAxis } from "@/lib/eventKeyStats";

/** The served Kalshi series, as value → count (order does not move the axis). */
const SPECIMEN_COUNTS: Array<[number, number]> = [
  [34.5, 1], [35.5, 1], [36.0, 1], [36.5, 1], [37.5, 3], [38.0, 9], [38.5, 1],
  [39.5, 41], [40.0, 2], [40.5, 122], [41.0, 11], [42.0, 17], [42.5, 6], [43.0, 4],
  [43.5, 18], [44.0, 19], [44.5, 12], [45.0, 2], [46.0, 1],
];
const SPECIMEN: number[] = [
  ...SPECIMEN_COUNTS.flatMap(([v, n]) => Array.from({ length: n }, () => v)),
  100.0, // the settle point — the last sample
];
const LAST = SPECIMEN[SPECIMEN.length - 1];

/** A series of `n` samples spread evenly across [lo, hi], plus any extras. */
function series(n: number, lo: number, hi: number, ...extras: number[]): number[] {
  const body = Array.from({ length: n }, (_, i) => lo + ((hi - lo) * i) / (n - 1));
  return [...body, ...extras];
}

describe("#9906 — the settled result is inside the chart", () => {
  test("the specimen without its end reproduces production's [30, 55]", () => {
    expect(SPECIMEN).toHaveLength(273);
    expect(computeWinProbYAxis(SPECIMEN).domain).toEqual([30, 55]);
  });

  test("with its last value as mustShow the axis reaches 100", () => {
    const axis = computeWinProbYAxis(SPECIMEN, [LAST]);
    expect(axis.domain).toEqual([25, 100]);
    expect(axis.ticks).toEqual([25, 50, 75, 100]);
  });

  test("a settle at 0 is reached from below the same way", () => {
    const mirrored = SPECIMEN.map((v) => 100 - v);
    const axis = computeWinProbYAxis(mirrored, [mirrored[mirrored.length - 1]]);
    expect(axis.domain[0]).toBe(0);
    expect(axis.domain[1]).toBeGreaterThanOrEqual(66);
  });
});

describe("#9906 — an end inside the core moves nothing", () => {
  test("the #3973 tennis spike is early, so passing its end leaves the zoom", () => {
    // 15306813's shape: 1,580 samples in 21–28 and an early spike at 92. Its end is in the band.
    const values = series(1580, 21.0, 27.8, 46.5, 76, 76, 77, 77, 92, 92, 92);
    expect(computeWinProbYAxis(values, [24.5])).toEqual(computeWinProbYAxis(values));
  });

  test("a live narrow market whose current price is in its band is unchanged", () => {
    const values = series(600, 56.5, 61.0);
    expect(computeWinProbYAxis(values, [60])).toEqual(computeWinProbYAxis(values));
  });

  test("non-finite ends are ignored", () => {
    const values = series(600, 56.5, 61.0);
    expect(computeWinProbYAxis(values, [NaN, Infinity])).toEqual(computeWinProbYAxis(values));
  });
});

describe("#9906 — OddsChart hands the axis every series' last value", () => {
  const src = readFileSync(join(__dirname, "..", "..", "components", "OddsChart.tsx"), "utf8");
  const memo = src.slice(src.indexOf("const { domain: yDomain, ticks: yTicks } = useMemo("));
  const body = memo.slice(0, memo.indexOf("}, [chartData, plottedProbKeys, drawnMinuteRanges]);"));

  test("the axis call passes the per-key last values", () => {
    expect(body).toContain("lastByKey.set(key, v);");
    // #10093 appends a live minute's inked high/low after the per-key ends.
    expect(body).toContain("return computeWinProbYAxis(values, [...lastByKey.values(), ...rangeEnds]);");
  });

  test("the last value is taken from the same plotted keys that size the axis", () => {
    expect(body).toMatch(/for \(const key of plottedProbKeys\)/);
  });
});
