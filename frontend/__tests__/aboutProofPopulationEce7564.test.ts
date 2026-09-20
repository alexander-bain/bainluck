// #7564 — the /about proof card's population and error figure.
//
// The card read:
//
//   "across 0.7M resolved outcomes, our numbers land within 1.5 points of what
//    actually happened."
//
// sourcing 1.5 from `mce_closing_line` with a `Math.max(by_source[].ece)`
// fallback. Three defects, all measured on the served payload and all
// reproduced below from a 30-row distillation of it:
//
//   1. POPULATION — `mce_closing_line` is `_cohort_mce(buckets, True)`, scoped
//      to `price_moved=true`: 293,900 of the 747,028 outcomes it named.
//   2. STATISTIC — a MEAN of ten per-bucket errors, not a max, so "within"
//      asserted a bound. Worst bucket in that cohort: 3.49pp.
//   3. METRIC — the equal-weight bucket average, which /calibration tells
//      readers reads BELOW its n-weighted ECE headline.
//
// The fix reads the cohort /calibration defaults to (traded markets,
// `price_moved !== false`) and reports its size alongside its error, so the two
// halves of the sentence cannot describe different populations again.
//
// The load-bearing assertions are the CLASS ones: the count and the figure come
// from one cohort, that cohort is the page's own, and no per-source maximum or
// unfiltered aggregate can reach the card. Each is paired with a CONTROL that
// the rejected alternative DOES violate it — including the whole-payload
// aggregate this fix's own first cut used, which is why that control is here.

import {
  proofCohortFigures,
  proofCalibrationErrorText,
  compactOutcomeCount,
} from "@/lib/calibrationProofFigures";
import { aggregateBuckets, cohortFilterFor } from "@/lib/calibrationParity";
import { ece } from "@/lib/calibrationMath";
import { SERVED_BUCKETS_20260915 } from "./fixtures/calibrationServedBuckets7564";

type Bucket = (typeof SERVED_BUCKETS_20260915)[number];

/** `_cohort_mce(buckets, pred)` — the producer's function, ported verbatim. */
function legacyCohortMce(buckets: Bucket[], pred: boolean): number | null {
  const agg = new Map<number, { n: number; winners: number; sumProb: number }>();
  for (const b of buckets) {
    if (b.price_moved !== pred) continue;
    const a = agg.get(b.bucket_idx) ?? { n: 0, winners: 0, sumProb: 0 };
    a.n += b.n;
    a.winners += b.winners;
    a.sumProb += b.sum_prob;
    agg.set(b.bucket_idx, a);
  }
  if (agg.size === 0) return null;
  let total = 0;
  for (const v of agg.values()) total += Math.abs(v.winners / v.n - v.sumProb / v.n);
  return Math.round((total / agg.size) * 100 * 100) / 100;
}

/** The per-source ECEs the served payload published. */
const SERVED_SOURCE_ECES = [0.89, 1.57, 1.33, 1.49, 2.5, 0.35, 36.49];

const withSumSqErr = (rows: readonly Bucket[]) => rows.map((b) => ({ ...b, sum_sq_err: 0 }));
const ALL = withSumSqErr(SERVED_BUCKETS_20260915);
const nOf = (pred: boolean | null) =>
  SERVED_BUCKETS_20260915.filter((b) => b.price_moved === pred).reduce((s, b) => s + b.n, 0);

describe("#7564 the /about proof card's population and error figure", () => {
  it("publishes the traded cohort the served payload measures", () => {
    const f = proofCohortFigures(ALL);
    expect(f).not.toBeNull();
    // 449,027 = 293,900 moved + 155,127 sportsbook. The 298,001 untraded are out.
    expect(f!.outcomes).toBe(449_027);
    expect(f!.errorPp).toBeCloseTo(0.917, 2);
    expect(proofCalibrationErrorText(ALL)).toBe("0.9");
    expect(compactOutcomeCount(f!.outcomes)).toBe("449K");
  });

  it("is the same cohort and the same arithmetic /calibration's headline uses", () => {
    // Not "a number that happens to agree" — the identical pipeline. If either
    // page's definition moves, this fails rather than the two silently drifting.
    const pageAgg = aggregateBuckets(ALL, cohortFilterFor(false));
    const f = proofCohortFigures(ALL)!;
    expect(f.errorPp).toBe(ece(pageAgg));
    expect(f.outcomes).toBe(pageAgg.reduce((s, b) => s + b.n, 0));

    // And it is the value the live page published in its `data-plain-ece`
    // attribute the day this was measured: 0.9171802586481436 over n=449,027.
    expect(f.errorPp).toBeCloseTo(0.9171802586481436, 6);
  });

  it("the count and the figure describe the same population", () => {
    // The defect in one assertion: both halves must move together. Drop the
    // sportsbook rows and BOTH the size and the error must change.
    const f = proofCohortFigures(ALL)!;
    const noBooks = proofCohortFigures(ALL.filter((b) => b.price_moved !== null))!;
    expect(noBooks.outcomes).toBe(293_900);
    expect(noBooks.outcomes).not.toBe(f.outcomes);
    expect(noBooks.errorPp).not.toBeCloseTo(f.errorPp, 3);
  });

  it("CONTROL: the legacy figure was scoped to 39% of the count beside it", () => {
    // Non-vacuity for the population claim. `mce_closing_line` is this number,
    // and the card printed it as "1.5" next to a count of 747,028.
    expect(legacyCohortMce(SERVED_BUCKETS_20260915, true)).toBe(1.49);
    expect(nOf(true)).toBe(293_900);
    expect(nOf(false)).toBe(298_001);
    expect(nOf(null)).toBe(155_127);
    expect(SERVED_BUCKETS_20260915.reduce((s, b) => s + b.n, 0)).toBe(747_028);

    // It is blind to every sportsbook row: deleting all 155,127 does not move it.
    expect(legacyCohortMce(SERVED_BUCKETS_20260915.filter((b) => b.price_moved !== null), true))
      .toBe(1.49);

    // The published figure is far enough from it that the swap is visible.
    expect(Math.abs(proofCohortFigures(ALL)!.errorPp - 1.49)).toBeGreaterThan(0.1);
  });

  it("CONTROL: 'within' was a bound the legacy statistic could not carry", () => {
    // `_cohort_mce` averages its buckets, so buckets sit on both sides of it.
    const agg = new Map<number, { n: number; winners: number; sumProb: number }>();
    for (const b of SERVED_BUCKETS_20260915.filter((x) => x.price_moved === true)) {
      const a = agg.get(b.bucket_idx) ?? { n: 0, winners: 0, sumProb: 0 };
      a.n += b.n;
      a.winners += b.winners;
      a.sumProb += b.sum_prob;
      agg.set(b.bucket_idx, a);
    }
    const errs = [...agg.values()].map((v) => Math.abs(v.winners / v.n - v.sumProb / v.n) * 100);
    expect(Math.max(...errs)).toBeCloseTo(3.49, 2);
    expect(Math.max(...errs)).toBeGreaterThan(1.49);
  });

  it("CONTROL: the unfiltered whole-payload aggregate is the flattering one", () => {
    // This fix's own first cut. Pooling all three cohorts lets oppositely
    // signed biases cancel before the absolute value, so the 747,028-row figure
    // reads BELOW every cohort it is built from. #7486 ruled that out for the
    // page next door in those words; this control keeps it out of this one.
    const unfiltered = ece(aggregateBuckets(ALL));
    const traded = ece(aggregateBuckets(ALL, cohortFilterFor(false)));
    const untraded = ece(aggregateBuckets(ALL, (b) => b.price_moved === false));
    const moved = ece(aggregateBuckets(ALL, (b) => b.price_moved === true));

    expect(unfiltered).toBeLessThan(traded);
    expect(unfiltered).toBeLessThan(untraded);
    expect(unfiltered).toBeLessThan(moved);

    // And it is NOT what the card publishes.
    expect(proofCohortFigures(ALL)!.errorPp).not.toBeCloseTo(unfiltered, 3);
    expect(proofCohortFigures(ALL)!.errorPp).toBeCloseTo(traded, 10);
  });

  it("no per-source maximum can reach the card", () => {
    // The removed fallback: #6211's 36-outcome DataGolf row.
    expect(Math.max(...SERVED_SOURCE_ECES)).toBe(36.49);
    const published = proofCohortFigures(ALL)!.errorPp;
    expect(published).toBeLessThan(1);
    expect(Math.max(...SERVED_SOURCE_ECES) / published).toBeGreaterThan(30);
    for (const e of SERVED_SOURCE_ECES) expect(Math.abs(published - e)).toBeGreaterThan(0.01);
  });

  it("withholds rather than guessing when the payload carries nothing readable", () => {
    // `null` keeps the editorial copy. Printing 0 for an unmeasured population
    // would be a perfect score the reader cannot tell from a measured one.
    expect(proofCohortFigures([])).toBeNull();
    expect(proofCohortFigures(undefined)).toBeNull();
    expect(proofCohortFigures(null)).toBeNull();
    expect(proofCalibrationErrorText([])).toBeNull();

    // Malformed or zero-n rows are dropped, not counted.
    expect(proofCohortFigures([{ bucket_idx: 0, n: 0, winners: 0, sum_prob: 0, sum_sq_err: 0 }]))
      .toBeNull();
    expect(proofCohortFigures([{ bucket_idx: 0, n: "5", winners: 1, sum_prob: 0.5, sum_sq_err: 0 }]))
      .toBeNull();
    expect(proofCohortFigures([{ n: 5, winners: 1, sum_prob: 0.5, sum_sq_err: 0 }])).toBeNull();

    // A payload of untraded rows ONLY has an empty cohort — withheld, not 0.
    expect(proofCohortFigures(ALL.filter((b) => b.price_moved === false))).toBeNull();
  });
});

describe("#7564 the proof figures tolerate a payload that omits an unused field", () => {
  it("still measures when `sum_sq_err` is absent — ECE never reads it", () => {
    const withoutSumSqErr = SERVED_BUCKETS_20260915.map((b) => ({
      bucket_idx: b.bucket_idx,
      price_moved: b.price_moved,
      n: b.n,
      winners: b.winners,
      sum_prob: b.sum_prob,
    }));
    const f = proofCohortFigures(withoutSumSqErr);
    expect(f).not.toBeNull();
    expect(f!.outcomes).toBe(449_027);
    expect(f!.errorPp).toBeCloseTo(0.917, 2);
  });
});
