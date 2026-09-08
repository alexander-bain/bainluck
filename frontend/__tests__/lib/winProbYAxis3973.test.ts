// #3973 — the win-probability axis is the window the line lives in.
//
// MEASURED ON PRODUCTION, 2026-09-08, `/api/events/{id}/history?hours=48`, every
// plotted series pooled the way `OddsChart` pools `plottedProbKeys`:
//
//   15306813  Shelton v Alcaraz   1,588 samples   min/max 21.0/92.0   p2/p98 21.5/27.8
//   15306225  Tiafoe v Michelsen  2,000 samples   min/max 46.5/79.0   p2/p98 56.5/61.0
//
// On the old fixed [0, 100] axis the first market — 98% of it inside 6.3 points
// — drew as a horizontal line, and so did the second inside 4.5. The filing
// blamed "a single early outlier stretching the axis"; it did not, `yDomain`
// was a hardcoded literal. The outlier's only role is that it defeats the
// obvious repair: plain min/max on 15306813 is [21, 92], as flat as today.
//
// These cases are the two production shapes plus the ways the rule can be got
// wrong in the other direction — magnifying a market that never moved, losing
// the 50% line while a lead-change diamond is still stamped on it, or welding
// that line to the plot frame.

import {
  computeWinProbYAxis,
  FULL_WIN_PROB_Y_AXIS,
} from "@/lib/eventKeyStats";

/** A series of `n` samples spread evenly across [lo, hi], plus any extras. */
function series(n: number, lo: number, hi: number, ...extras: number[]): number[] {
  const body = Array.from({ length: n }, (_, i) => lo + ((hi - lo) * i) / (n - 1));
  return [...body, ...extras];
}

const span = (a: ReturnType<typeof computeWinProbYAxis>) => a.domain[1] - a.domain[0];

describe("#3973 — a narrow market gets a narrow axis", () => {
  test("15306813's shape: the 21–28 band no longer shares an axis with a 92 spike", () => {
    // 1,580 in the band, 8 up at the early spike — the production ratio.
    const axis = computeWinProbYAxis(series(1580, 21.0, 27.8, 46.5, 76, 76, 77, 77, 92, 92, 92));

    // The reader's property: the band is a real share of the plot, not 6% of it.
    const bandShare = (27.8 - 21.0) / span(axis);
    expect(bandShare).toBeGreaterThan(0.15);

    // …and the spike is OUT of the domain, which is the whole point of using
    // percentiles. It is still drawn — `allowDataOverflow` fits a clip path
    // that confines it to the plot — not deleted.
    expect(axis.domain[1]).toBeLessThan(92);
  });

  test("15306225's shape: a 4.5-point band around 58 is legible", () => {
    const axis = computeWinProbYAxis(series(1988, 56.5, 61.0, 46.5, 46.5, 73.5, 79, 79, 79));

    const bandShare = (61.0 - 56.5) / span(axis);
    expect(bandShare).toBeGreaterThan(0.15);
  });
});

describe("#3973 — the 50% mark, which the chart draws things on", () => {
  test("a series that crosses 50 keeps 50 in the domain AND on the ticks", () => {
    // 15306225 crosses: it starts at 46.5 and settles at 58. The chart stamps a
    // lead-change diamond at y=50 for that crossing, so an axis that zoomed to
    // [55, 62] would be counting a marker it had clipped off the plot.
    const axis = computeWinProbYAxis(series(1988, 56.5, 61.0, 46.5, 46.5, 79));

    expect(axis.domain[0]).toBeLessThanOrEqual(50);
    expect(axis.domain[1]).toBeGreaterThanOrEqual(50);
    expect(axis.ticks).toContain(50);
  });

  test("50 is never the domain's own edge — a reference line on the frame is furniture", () => {
    // The failure this catches is specific: 15306813's p98 is 27.8 and forcing
    // 50 in gives [20, 50] exactly, which would draw the dashed 50% rule and its
    // two lead-change diamonds along the top axis line.
    const axis = computeWinProbYAxis(series(1580, 21.0, 27.8, 46.5, 92));

    expect(axis.domain[0]).toBeLessThan(50);
    expect(axis.domain[1]).toBeGreaterThan(50);
  });

  test("a market that never approaches 50 spends no axis on it", () => {
    // No crossing ⇒ no lead change ⇒ nothing is drawn at 50, and a dashed rule
    // there would label nothing. recharts' `ifOverflow="discard"` drops it.
    const axis = computeWinProbYAxis(series(400, 78, 86));

    expect(axis.domain[0]).toBeGreaterThan(50);
    expect(axis.ticks.every((t) => t > 50)).toBe(true);
  });

  test("ONE crossing print is enough — the test is the extremes, not the percentiles", () => {
    // p2 of this series is inside the band; only the single 49.0 sample reaches
    // 50's side, and that single sample is exactly what mints the diamond.
    const axis = computeWinProbYAxis(series(999, 55, 60, 49.0));

    expect(axis.domain[0]).toBeLessThanOrEqual(50);
    expect(axis.ticks).toContain(50);
  });
});

describe("#3973 — the ways zooming could itself become the lie", () => {
  test("a market that genuinely used the range is left EXACTLY as it was", () => {
    // The control. A rule written as "always zoom to the data" passes every
    // test above and fails this one.
    const axis = computeWinProbYAxis(series(500, 10, 90));

    expect(axis.domain).toEqual(FULL_WIN_PROB_Y_AXIS.domain);
    expect(axis.ticks).toEqual(FULL_WIN_PROB_Y_AXIS.ticks);
  });

  test("a market that never moved is not magnified into a thriller", () => {
    // Pinned at 49.8 all week. Zooming to its own extent would render sampling
    // noise as full-height drama — the same misrepresentation as the flat line,
    // pointing the other way.
    const axis = computeWinProbYAxis(Array.from({ length: 800 }, () => 49.8));

    expect(span(axis)).toBeGreaterThanOrEqual(20);
    // …and the flat line sits INSIDE the window rather than along its frame.
    // Widening after the snap instead of before satisfies the span check above
    // while leaving 49.8 on the top axis line, which reads as a chart whose
    // data ran out rather than as a market that held.
    const [lo, hi] = axis.domain;
    expect(49.8).toBeGreaterThan(lo + span(axis) * 0.25);
    expect(49.8).toBeLessThan(hi - span(axis) * 0.25);
  });

  test("too few samples to have a percentile keeps the full axis", () => {
    // 22/23/24/25 and not, say, 22/23/24/91: with four samples spanning the
    // range the derived axis snaps back to [0, 100] anyway, and the case would
    // pass with no sample floor at all.
    const axis = computeWinProbYAxis([22, 23, 24, 25]);

    expect(axis).toEqual(FULL_WIN_PROB_Y_AXIS);
  });

  test("no samples at all keeps the full axis", () => {
    expect(computeWinProbYAxis([])).toEqual(FULL_WIN_PROB_Y_AXIS);
  });

  test("NaN and Infinity are dropped, and dropping them can cost the percentile", () => {
    // 12 finite samples survive here, so the axis is derived; with the two bad
    // values counted as samples a `length` check would derive it off 14 and a
    // `sort` would put NaN wherever it liked in the percentile.
    const axis = computeWinProbYAxis([...series(12, 30, 34), NaN, Infinity]);

    expect(Number.isFinite(axis.domain[0])).toBe(true);
    expect(Number.isFinite(axis.domain[1])).toBe(true);
    expect(axis.domain[0]).toBeLessThanOrEqual(30);
    expect(axis.domain[1]).toBeGreaterThanOrEqual(34);
  });
});

describe("#3973 — the axis is always drawable", () => {
  const shapes: Array<[string, number[]]> = [
    ["a hopeless underdog", series(600, 1, 4)],
    ["a near-certainty", series(600, 96, 99.5)],
    ["pinned at exactly 0", Array.from({ length: 600 }, () => 0)],
    ["pinned at exactly 100", Array.from({ length: 600 }, () => 100)],
    ["pinned at exactly 50", Array.from({ length: 600 }, () => 50)],
    ["one wild sample in a dead market", [...series(600, 40, 42), 100]],
    ["the full sweep", series(600, 0, 100)],
  ];

  test.each(shapes)("%s yields a sane, in-range, tick-consistent axis", (_name, values) => {
    const axis = computeWinProbYAxis(values);
    const [lo, hi] = axis.domain;

    expect(lo).toBeGreaterThanOrEqual(0);
    expect(hi).toBeLessThanOrEqual(100);
    expect(hi - lo).toBeGreaterThanOrEqual(20);
    expect(axis.ticks.length).toBeGreaterThanOrEqual(3);
    expect(axis.ticks[0]).toBe(lo);
    expect(axis.ticks[axis.ticks.length - 1]).toBe(hi);
    // Every tick is a whole number — `formatYTick` prints the value raw, so a
    // 52.5 tick would put "52.5%" on the axis.
    for (const t of axis.ticks) expect(Number.isInteger(t)).toBe(true);
    // 50 is a multiple of every grid step, so whenever it is in range it is on
    // the tick set — which is what #3525 leaned on when it deleted the 50%
    // line's own label ("the left axis already prints 50% on this exact line").
    if (lo <= 50 && hi >= 50) expect(axis.ticks).toContain(50);
  });
});
