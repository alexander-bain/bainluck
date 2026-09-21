// #7837 — the win-probability axis stops cutting the moments that decided the game.
//
// MEASURED ON PRODUCTION, 2026-09-21, from the LAYOUT ENGINE rather than from an API replay
// (`tools/winprob-axis-vs-line-7837.mjs`, 390px):
//
//   /events/14780544  KC 33–30 IND (OT)   ticks 40..90%   6 of 6 drawn lines above the frame,
//                                                         4 below            -> clipped
//   /events/14782150  TB–CLE              ticks 0..100%   0 above, 0 below   -> clean (control)
//
// On the first, Kansas City's blend fell to 24.2% twice and finished at 100%, so the line ran off
// the bottom on the two drives the Colts nearly won it and off the top at the whistle — while the
// trailing callout printed `100%` against an axis whose highest tick said 90%.
//
// THE REPLAY IS NOT THE INSTRUMENT AND THAT COST A WRONG NUMBER. Recomputing the domain from
// `/api/events/{id}/history` rows predicted [25,100] for 14782150, which renders [0,100]: the axis
// is fed the pooled, minute-bucketed, forward-filled series `OddsChart` builds from every plotted
// key, not the raw blend rows. The domains above are read off the rendered `.recharts-yAxis`.
//
// These cases pin the SEPARATOR, which is the part that can silently rot: not "how many samples
// are outside" (3.2% here vs 0.63% on #3973's tennis page — the wrong way round) but "how much of
// the plot would the core band give up". #3973's own guards live in `winProbYAxis3973.test.ts` and
// are the other half of this; a change that widens for the tennis spike passes everything here.

import { computeWinProbYAxis } from "@/lib/eventKeyStats";

/** A series of `n` samples spread evenly across [lo, hi], plus any extras. */
function series(n: number, lo: number, hi: number, ...extras: number[]): number[] {
  const body = Array.from({ length: n }, (_, i) => lo + ((hi - lo) * i) / (n - 1));
  return [...body, ...extras];
}

describe("#7837 — extremes that ARE the story are inside the frame", () => {
  test("14780544's shape: a 24%→100% game is not drawn on a 40–90% axis", () => {
    // 209 samples through the band the game spent its life in, plus the two near-losses and the
    // finish. The production series is 216 blend points with min 24.2 / max 100.0 and p2/p98 of
    // 40.5/88.3 — the percentile window that produced the filed [40, 90].
    const values = series(209, 40.5, 88.3, 24.2, 27.0, 33.0, 38.0, 94.0, 97.0, 100.0);
    const axis = computeWinProbYAxis(values);

    // The reader's property, and the only one worth asserting: nothing the chart draws is outside
    // the axis it draws it against.
    expect(axis.domain[0]).toBeLessThanOrEqual(24.2);
    expect(axis.domain[1]).toBeGreaterThanOrEqual(100);
  });

  test("…and the callout's number is a value the axis can hold", () => {
    // #5581 places the trailing label at the last point and assumed the domain would reach it
    // ("a game that finishes at 100% puts the last data point EXACTLY on the plot's top edge").
    // On 14780544 it did not, so the label said 100% while the top tick said 90%. The axis owes
    // the callout a domain that contains the value it is about to print.
    const values = series(209, 40.5, 88.3, 24.2, 27.0, 33.0, 38.0, 94.0, 97.0, 100.0);
    const axis = computeWinProbYAxis(values);
    const last = values[values.length - 1];

    expect(last).toBeLessThanOrEqual(axis.domain[1]);
  });

  test("the separator is the core's SHARE of the plot, not the outliers' count", () => {
    // Same 3.2%-outside proportion as the repaired case, but the outliers are 60 points away
    // instead of 16 — #3973's "one wild sample in a dead market" shape. Widening here would flatten
    // the band back into a horizontal line, which is the defect #3973 exists to fix.
    const narrow = computeWinProbYAxis(series(209, 40.5, 46.8, 0, 0, 0, 0, 100, 100, 100));
    const bandShare = (46.8 - 40.5) / (narrow.domain[1] - narrow.domain[0]);

    expect(bandShare).toBeGreaterThan(0.15);
    expect(narrow.domain[0]).toBeGreaterThan(0);
    expect(narrow.domain[1]).toBeLessThan(100);
  });

  test("a series whose core is exactly half the full range is widened; well under half is not", () => {
    // The rule's own boundary, stated as two neighbours so a moved threshold has to break one of
    // them. Core 40 points inside a 60-point range is 67% and takes the extremes; core 6 inside 60
    // is 10% and keeps its window.
    const wide = computeWinProbYAxis(series(400, 30, 70, 20, 80));
    expect(wide.domain[0]).toBeLessThanOrEqual(20);
    expect(wide.domain[1]).toBeGreaterThanOrEqual(80);

    const tight = computeWinProbYAxis(series(400, 47, 53, 20, 80));
    expect(tight.domain[0]).toBeGreaterThan(20);
    expect(tight.domain[1]).toBeLessThan(80);
  });

  test("where rule 4's snap already absorbed the extremes, widening is a no-op", () => {
    // Most charts are this shape, which is why only one page of a 14-game slate was clipping: the
    // outward snap to the 5/10/25 grid had already swallowed the extremes, so taking them changes
    // nothing. Asserted as an identity against the pre-#7837 pipeline rather than a literal, so it
    // stays a control if the grid ever moves.
    //
    // NOT NAMED FOR A PRODUCTION PAGE, DELIBERATELY. The clean control page /events/14782150
    // renders [0, 100], but its pooled forward-filled series is not something this file can
    // reconstruct — a replay of its raw rows yields [25, 100], which is the wrong answer (see the
    // header). A synthetic named for that page would be pinning the replay's mistake under its
    // name.
    const axis = computeWinProbYAxis(series(400, 62.5, 97, 60, 100));

    // The percentile window here is ~[63, 96.3]; the snap takes it to [60, 100] either way.
    expect(axis.domain).toEqual([60, 100]);
    expect(axis.domain[0]).toBeLessThanOrEqual(60);
    expect(axis.domain[1]).toBeGreaterThanOrEqual(100);
  });
});
