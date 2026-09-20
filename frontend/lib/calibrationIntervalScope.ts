// #7374 — the accuracy page printed one confidence interval beside every cohort.
//
// WHAT WAS WRONG
//
// `mce_ci_lower` / `mce_ci_upper` are a single pair of top-level payload
// scalars. The producer bootstraps them ONCE, over every bucket with no
// `price_moved` filter (`precompute_calibration.py:7221`), so they describe the
// whole published population and nothing else. The page rendered them beside
// figures that ARE cohort-scoped, and the value could not move when the reader
// moved the toggle:
//
//     default (traded)     1.0pp per-bucket (95% CI: 0.3-1.2pp) | 449,027 outcomes
//     include untraded     0.9pp per-bucket (95% CI: 0.3-1.2pp) | 747,028 outcomes
//
// `_bootstrap_mce_ci` is deterministic (`random.Random(42)`, 1,000 bucket
// resamples), so both intervals reproduce off the live 2026-09-15 payload:
// all outcomes 0.33-1.19pp — the published pair, to the digit — and traded-only
// 0.62-1.29pp. On the view a reader lands on, the lower bound was out by
// roughly a factor of two, and the interval shown was the one belonging to the
// 298,001 outcomes the same screen had just said were excluded.
//
// THE KEY IS THE POPULATION, NOT THE TOGGLE
//
// This gates on `cohortN === fullN` rather than on `includeNeverMoved`, because
// what makes the interval publishable is that the figure beside it was measured
// over the rows the interval was bootstrapped over. A payload with no untraded
// outcomes in it has one population in both toggle states, and that case should
// publish the interval on the default view — keying on the boolean would
// withhold it there forever, for a reason that had stopped being true.
//
// WHAT THIS DOES NOT DO
//
// It does not compute a cohort's interval. That is a second bootstrap and it
// belongs in the producer beside the first one, so the two cannot drift into
// two records of one capability. It cannot ship today: `/api/calibration` has
// served `availability: "stale"` since 2026-09-15 while #6868's staged bank
// converges, so a new payload key would reach no reader, and an edit inside the
// hashed population functions zeroes that bank (#6211). #7374 carries it.

/** The published bootstrap interval, in percentage points. */
export interface MceInterval {
  lower: number;
  upper: number;
}

export interface MceIntervalScopeInput {
  /** `mce_ci_lower` as served. */
  lower: number | null | undefined;
  /** `mce_ci_upper` as served. */
  upper: number | null | undefined;
  /** Outcomes behind the figure the page is about to print. */
  cohortN: number;
  /** Every resolved outcome in the payload — the interval's own population. */
  fullN: number;
}

function isBound(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

/**
 * The interval to print beside the ACTIVE cohort's n-weighted figure, or `null`.
 *
 * `null` means "this cohort has no published interval" — the page then prints
 * no interval at all rather than the wrong one, and says nothing about the
 * absence (notice 34).
 *
 * Also `null` for a payload that omits either bound or serves them inverted:
 * the type says `number`, the wire does not have to agree, and half an interval
 * is not one.
 */
export function mceIntervalForCohort(
  input: MceIntervalScopeInput
): MceInterval | null {
  const { lower, upper, cohortN, fullN } = input;
  if (!isBound(lower) || !isBound(upper) || lower > upper) return null;
  if (!Number.isFinite(cohortN) || !Number.isFinite(fullN)) return null;
  if (fullN <= 0 || cohortN !== fullN) return null;
  return { lower, upper };
}

/**
 * The interval as the page prints it, at one decimal: `"0.3-1.2pp"`.
 *
 * Here rather than at the call site so the two render sites cannot format the
 * same pair two ways.
 */
export function formatMceInterval(interval: MceInterval): string {
  return `${interval.lower.toFixed(1)}-${interval.upper.toFixed(1)}pp`;
}
