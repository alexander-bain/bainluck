// #7374 — one confidence interval was printed beside every cohort.
//
// THE FIXTURE IS THE LIVE PAYLOAD, AND THE SECOND INTERVAL IS MEASURED
//
// Every number below was read from `https://api.bainluck.com/api/calibration`
// on 2026-09-20 ~05:10Z, or computed from its buckets by reproducing the
// producer's own `_bootstrap_mce_ci` (deterministic: `random.Random(42)`, 1,000
// bucket resamples, n-weighted):
//
//     resampling all 747,028 outcomes  ->  0.33 - 1.19pp   (== the published pair)
//     resampling the 449,027 traded    ->  0.62 - 1.29pp
//
// That second pair is why this module withholds rather than relabels. The
// interval the page was printing on the view a reader lands on was not a loose
// version of the right one — its lower bound was out by about a factor of two,
// and it belonged to the 298,001 outcomes the banner above it had just said
// were excluded.
//
// HOW THIS SUITE AVOIDS PROVING NOTHING
//
// The fix's visible effect is an ABSENCE, and an absence-guard passes for two
// bad reasons: the predicate never fired, or the fixture could not have
// contained the defect. So every `toBeNull()` arm below is paired with a
// positive control that runs the SAME function over the SAME bounds and must
// produce an interval. If `mceIntervalForCohort` were stubbed to `() => null`,
// the controls go red.

import {
  mceIntervalForCohort,
  formatMceInterval,
} from "@/lib/calibrationIntervalScope";

/** The pair `/api/calibration` served, to the digit. */
const PUBLISHED = { lower: 0.33, upper: 1.19 };

/** Every resolved outcome in that payload. */
const FULL_N = 747_028;
/** The default cohort: full population minus the 298,001 that never moved. */
const TRADED_N = 449_027;

describe("#7374 the interval is published only over the population it was bootstrapped on", () => {
  it("publishes it when the reader has layered every outcome back in", () => {
    expect(mceIntervalForCohort({ ...PUBLISHED, cohortN: FULL_N, fullN: FULL_N }))
      .toEqual({ lower: 0.33, upper: 1.19 });
  });

  it("withholds it on the default traded cohort — the defect", () => {
    expect(mceIntervalForCohort({ ...PUBLISHED, cohortN: TRADED_N, fullN: FULL_N }))
      .toBeNull();
  });

  it("withholds it on any other partial cohort, not just the measured one", () => {
    // The 298,001 untraded rows read alone. Same payload, same bounds, and the
    // producer never bootstrapped this population either.
    expect(mceIntervalForCohort({ ...PUBLISHED, cohortN: 298_001, fullN: FULL_N }))
      .toBeNull();
    expect(mceIntervalForCohort({ ...PUBLISHED, cohortN: FULL_N - 1, fullN: FULL_N }))
      .toBeNull();
  });

  it("is keyed on the population, not on the toggle: a payload with nothing untraded publishes", () => {
    // The reason the predicate is `cohortN === fullN` and not
    // `includeNeverMoved`. On a build where no outcome carries
    // `price_moved: false`, the default view IS the full population and the
    // interval describes it exactly. Keying on the boolean would withhold it
    // there forever, for a reason that had stopped being true.
    expect(mceIntervalForCohort({ ...PUBLISHED, cohortN: 512_000, fullN: 512_000 }))
      .toEqual({ lower: 0.33, upper: 1.19 });
  });
});

describe("#7374 a half-served interval is not an interval", () => {
  // Control: the same three shapes with sound bounds must publish, so a `null`
  // below is the bound check firing rather than the cohort gate.
  const soundControl = { ...PUBLISHED, cohortN: FULL_N, fullN: FULL_N };

  it("control — the sound payload publishes", () => {
    expect(mceIntervalForCohort(soundControl)).not.toBeNull();
  });

  it.each([
    ["lower absent", { lower: undefined, upper: 1.19 }],
    ["upper absent", { lower: 0.33, upper: undefined }],
    ["lower null", { lower: null, upper: 1.19 }],
    ["upper null", { lower: 0.33, upper: null }],
    ["NaN", { lower: Number.NaN, upper: 1.19 }],
    ["infinite", { lower: 0.33, upper: Number.POSITIVE_INFINITY }],
    ["negative", { lower: -0.1, upper: 1.19 }],
    ["inverted", { lower: 1.19, upper: 0.33 }],
  ])("withholds on %s", (_label, bounds) => {
    expect(mceIntervalForCohort({ ...soundControl, ...bounds })).toBeNull();
  });

  it("withholds while the payload is still loading and both counts are zero", () => {
    // `cohortN === fullN` is trivially true at 0/0. An interval over no
    // outcomes is not one, and this is the state the page renders on first
    // paint.
    expect(mceIntervalForCohort({ ...PUBLISHED, cohortN: 0, fullN: 0 })).toBeNull();
  });

  it("an interval whose ends are equal is still an interval", () => {
    // Not a degenerate case worth suppressing: a bootstrap can land both
    // percentiles on one value, and that is a measurement, not a missing field.
    expect(mceIntervalForCohort({ lower: 0.9, upper: 0.9, cohortN: 10, fullN: 10 }))
      .toEqual({ lower: 0.9, upper: 0.9 });
  });
});

describe("#7374 formatting", () => {
  it("prints the pair the way production printed it", () => {
    expect(formatMceInterval({ lower: 0.33, upper: 1.19 })).toBe("0.3-1.2pp");
  });

  it("keeps one decimal on a whole number, so the two ends read as one figure", () => {
    expect(formatMceInterval({ lower: 1, upper: 2 })).toBe("1.0-2.0pp");
  });

  it("would print the traded cohort's own interval if one were ever published", () => {
    // The measured pair from the header. Kept here so the number this fix is
    // about is in the suite, not only in the prose above it.
    expect(formatMceInterval({ lower: 0.62, upper: 1.29 })).toBe("0.6-1.3pp");
  });
});
