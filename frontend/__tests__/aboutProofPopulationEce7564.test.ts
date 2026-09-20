// #7564 — the /about proof card's error figure.
//
// The card read:
//
//   "across 0.7M resolved outcomes, our numbers land within 1.5 points of what
//    actually happened."
//
// and sourced that 1.5 from `mce_closing_line`, falling back to
// `Math.max(by_source[].ece)`. Three defects, all measured on the served payload
// and all reproduced below from the same 30-row distillation of it:
//
//   1. POPULATION — `mce_closing_line` is `_cohort_mce(buckets, True)`, scoped to
//      `price_moved=true`: 293,900 of the 747,028 outcomes the sentence names.
//   2. STATISTIC — it is a MEAN of ten per-bucket errors, not a max, so "within"
//      asserted a bound the number cannot support.
//   3. METRIC — it is the equal-weight bucket average, which /calibration tells
//      readers reads BELOW its headline ECE.
//
// plus a dormant fourth: the `Math.max` fallback is 36.49 today (#6211's
// 36-outcome DataGolf row).
//
// The load-bearing assertions are the CLASS ones — the figure is measured over
// the whole population, and no per-source maximum can reach the card. Each is
// paired with a CONTROL asserting the legacy selector DOES violate it, so if a
// refactor ever makes an invariant unfalsifiable the control stops failing and
// this file goes red.

import {
  populationCalibrationErrorPp,
  proofCalibrationErrorText,
} from "@/lib/calibrationProofFigures";
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
  for (const v of agg.values()) {
    if (v.n === 0) continue;
    total += Math.abs(v.winners / v.n - v.sumProb / v.n);
  }
  return Math.round((total / agg.size) * 100 * 100) / 100;
}

/** The per-source ECEs the served payload published, worst last. */
const SERVED_SOURCE_ECES = [0.89, 1.57, 1.33, 1.49, 2.5, 0.35, 36.49];

const cohortRows = (pred: boolean | null) =>
  SERVED_BUCKETS_20260915.filter((b) => b.price_moved === pred);

describe("#7564 the /about proof card's calibration-error figure", () => {
  it("publishes the live population ECE the served payload measures", () => {
    // 0.675pp, n-weighted over all ten pooled buckets.
    expect(populationCalibrationErrorPp(SERVED_BUCKETS_20260915)).toBeCloseTo(0.675, 3);
    expect(proofCalibrationErrorText(SERVED_BUCKETS_20260915)).toBe("0.7");
  });

  it("measures the figure over every outcome the card counts, not one cohort", () => {
    // The sentence names `total_outcomes`. The figure must move when rows the
    // card counts change — so dropping a cohort must change the answer.
    const whole = populationCalibrationErrorPp(SERVED_BUCKETS_20260915);
    const withoutSportsbooks = populationCalibrationErrorPp(
      SERVED_BUCKETS_20260915.filter((b) => b.price_moved !== null)
    );
    expect(whole).not.toBeCloseTo(withoutSportsbooks as number, 3);

    // And the population it weighs really is all 747,028 rows.
    const n = SERVED_BUCKETS_20260915.reduce((s, b) => s + b.n, 0);
    expect(n).toBe(747_028);
    expect(cohortRows(true).reduce((s, b) => s + b.n, 0)).toBe(293_900);
    expect(cohortRows(false).reduce((s, b) => s + b.n, 0)).toBe(298_001);
    expect(cohortRows(null).reduce((s, b) => s + b.n, 0)).toBe(155_127);
  });

  it("CONTROL: the legacy figure was scoped to 39% of that population", () => {
    // Non-vacuity for the population claim, stated exactly. `mce_closing_line`
    // is this number, and the card printed it as "1.5".
    expect(legacyCohortMce(SERVED_BUCKETS_20260915, true)).toBe(1.49);
    expect(legacyCohortMce(SERVED_BUCKETS_20260915, false)).toBe(1.32);

    // It is blind to every sportsbook row: deleting all 155,127 of them does not
    // move it by a hundredth, which is precisely why it could not describe the
    // population the sentence named.
    const withoutSportsbooks = SERVED_BUCKETS_20260915.filter((b) => b.price_moved !== null);
    expect(legacyCohortMce(withoutSportsbooks, true)).toBe(1.49);

    // The new figure IS sensitive to them — the two differ by more than a
    // rounding step, so the swap is observable on the card.
    expect(Math.abs((populationCalibrationErrorPp(SERVED_BUCKETS_20260915) as number) - 1.49))
      .toBeGreaterThan(0.05);
  });

  it("CONTROL: 'within' was a bound the legacy statistic could not carry", () => {
    // `_cohort_mce` averages its buckets, so buckets sit on both sides of it.
    // In the very cohort the card quoted, the worst is 3.49pp — more than twice
    // the 1.5 the reader was told their numbers land within.
    const agg = new Map<number, { n: number; winners: number; sumProb: number }>();
    for (const b of cohortRows(true)) {
      const a = agg.get(b.bucket_idx) ?? { n: 0, winners: 0, sumProb: 0 };
      a.n += b.n;
      a.winners += b.winners;
      a.sumProb += b.sum_prob;
      agg.set(b.bucket_idx, a);
    }
    const errs = [...agg.values()].map((v) => Math.abs(v.winners / v.n - v.sumProb / v.n) * 100);
    const worst = Math.max(...errs);
    expect(worst).toBeCloseTo(3.49, 2);
    expect(worst).toBeGreaterThan(1.49);
    expect(errs.filter((e) => e > 1.49).length).toBeGreaterThan(0);
  });

  it("no per-source maximum can reach the card", () => {
    // The removed fallback. A 36-outcome DataGolf sample (#6211) is the worst
    // per-source ECE in the served payload; the figure the card now prints is
    // two orders of magnitude away from it and is not a max of anything.
    expect(Math.max(...SERVED_SOURCE_ECES)).toBe(36.49);
    const published = populationCalibrationErrorPp(SERVED_BUCKETS_20260915) as number;

    // Two orders of magnitude from what the fallback would have printed.
    expect(published).toBeLessThan(1);
    expect(Math.max(...SERVED_SOURCE_ECES) / published).toBeGreaterThan(50);

    // A pooled population figure is its own quantity, not one of the per-source
    // rows relabelled — it need not be the smallest of them (odds_api_spreads
    // reads 0.35 on 15,120 rows), but it must not BE any of them.
    for (const e of SERVED_SOURCE_ECES) expect(Math.abs(published - e)).toBeGreaterThan(0.01);
  });

  it("withholds rather than guessing when the payload carries no buckets", () => {
    // `null` keeps the editorial copy. Printing 0 for an unmeasured population
    // would be a perfect score the reader cannot tell from a measured one.
    expect(populationCalibrationErrorPp([])).toBeNull();
    expect(populationCalibrationErrorPp(undefined)).toBeNull();
    expect(populationCalibrationErrorPp(null)).toBeNull();
    expect(proofCalibrationErrorText([])).toBeNull();

    // All-zero / malformed rows are withheld too, not published as 0.0.
    expect(populationCalibrationErrorPp([{ bucket_idx: 0, n: 0, winners: 0, sum_prob: 0 }])).toBeNull();
    expect(populationCalibrationErrorPp([{ bucket_idx: 0, n: "5", winners: 1, sum_prob: 0.5 }])).toBeNull();
    expect(populationCalibrationErrorPp([{ n: 5, winners: 1, sum_prob: 0.5 }])).toBeNull();
  });

  it("pools split rows before weighing them", () => {
    // Buckets arrive split by source x category x price_moved. A perfectly
    // calibrated curve split into a huge and a tiny row must read 0, and must
    // not let the tiny row vote like the huge one.
    const split = [
      { bucket_idx: 0, price_moved: true, n: 100_000, winners: 10_000, sum_prob: 10_000 },
      { bucket_idx: 0, price_moved: null, n: 10, winners: 1, sum_prob: 1 },
    ];
    expect(populationCalibrationErrorPp(split)).toBeCloseTo(0, 6);

    // And a 10-row cohort that is 100% wrong cannot drag a 1,000,000-row
    // population more than its weight allows (~0.001%).
    const lopsided = [
      { bucket_idx: 0, price_moved: false, n: 1_000_000, winners: 500_000, sum_prob: 500_000 },
      { bucket_idx: 1, price_moved: null, n: 10, winners: 10, sum_prob: 0 },
    ];
    expect(populationCalibrationErrorPp(lopsided) as number).toBeLessThan(0.002);
  });
});
