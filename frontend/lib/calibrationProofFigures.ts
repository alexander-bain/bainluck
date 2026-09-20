// #7555 — the /about proof card's outcome count.
//
// It used to gate on 1e3 and divide by 1e6:
//
//   total_outcomes >= 1000 ? `${(total_outcomes / 1_000_000).toFixed(1)}M` : `${total_outcomes}`
//
// so the raw-integer branch was unreachable for any calibration population and
// every value below a million rendered as a sub-1 "M" figure — 747,028 published
// as "0.7M", and anything under ~50k as "0.0M", a number a reader cannot tell
// from zero. Every other compact formatter in the frontend gates on 1e6
// (`app/admin/page.tsx:241`, `app/admin/analytics/page.tsx:175`,
// `components/QuantityGroup.tsx:470`, `components/ThresholdSparkline.tsx:51`);
// `app/admin/page.tsx:995` is the three-tier M/K/raw form this card wanted.
//
// It lives in `lib/` rather than in the page because a Next.js page module may
// not carry a second named export — exporting it from `app/about/page.tsx` to
// reach a unit test fails the typecheck gate.

/**
 * A resolved-outcome count as compact display text, or `null` when the payload
 * carried no readable number.
 *
 * `null` is the caller's signal to keep the editorial fallback copy: a count the
 * server omitted is unknown, and printing `0` for it is a number the reader
 * cannot tell from a measured one.
 */
export function compactOutcomeCount(value: unknown): string | null {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) return null;
  if (value < 1_000) return `${Math.round(value)}`;

  const thousands = Math.round(value / 1_000);
  // 999,750 rounds to 1000K — a million wearing the wrong suffix. Promote it
  // rather than publish a four-digit K.
  if (thousands >= 1_000) return `${(value / 1_000_000).toFixed(1)}M`;
  return `${thousands}K`;
}

/** The bucket fields this module needs; a structural subset of `CalibrationBucket`. */
interface ProofBucket {
  bucket_idx: number;
  n: number;
  winners: number;
  sum_prob: number;
}

// #7564 — the proof card's error figure.
//
// It used to print `mce_closing_line`, falling back to `Math.max(by_source.ece)`.
// Three things were wrong with that, all measured on the served payload:
//
//  1. POPULATION. `mce_closing_line` is `_cohort_mce(buckets, True)`
//     (`precompute_calibration.py:7224`), which filters on `price_moved is True`
//     — 293,900 of the 747,028 outcomes the sentence names. The other 453,128
//     (298,001 `false` + 155,127 `null`, every sportsbook row) are outside it.
//     #7472 removed that same pair from /calibration for this reason.
//  2. STATISTIC. `_cohort_mce` returns `total_abs_err / len(cohort_agg)` — the
//     MEAN of ten per-bucket errors, not a maximum, despite the name. The card
//     said "land WITHIN 1.5 points", a bound; the worst bucket in that very
//     cohort is 3.49pp off (n=34,019). An average cannot carry a bound's verb.
//  3. METRIC. /calibration tells the reader ECE (n-weighted) is the headline
//     "because it reflects the outcomes users actually see", and that the
//     equal-weight bucket average "can read below ECE" (`page.tsx:1417`).
//     `mce_closing_line` is that equal-weight average, so /about published the
//     flattering non-headline number.
//
// And the fallback was a landmine: `Math.max(by_source.ece)` is 36.49 today —
// the censored 36-outcome DataGolf row of #6211 — one null scalar away from
// "our numbers land within 36.5 points" on the public proof card.
//
// So the figure is derived here instead, as the n-weighted ECE over the WHOLE
// published population: the metric /calibration calls the headline, measured on
// the population the sentence actually names. This needs no new payload field,
// which matters — the #6868 freeze bars any change to the producer.

/**
 * Population ECE in percentage points, n-weighted over every bucket, or `null`
 * when the payload carried nothing measurable.
 *
 * Buckets arrive split by source × category × `price_moved`, so they are pooled
 * on `bucket_idx` first: ECE is a property of the reliability curve, and
 * averaging pre-split rows would weight a 36-row cohort like a 300,000-row one.
 *
 * `null` is the caller's signal to keep the editorial fallback copy. There is
 * deliberately no second-choice statistic — a fallback that silently swaps the
 * metric is what put a 36-outcome sample one null away from the card.
 */
export function populationCalibrationErrorPp(buckets: unknown): number | null {
  if (!Array.isArray(buckets) || buckets.length === 0) return null;

  const pooled = new Map<number, { n: number; winners: number; sumProb: number }>();
  for (const raw of buckets) {
    const b = raw as Partial<ProofBucket> | null;
    if (!b || typeof b.bucket_idx !== "number" || !Number.isFinite(b.bucket_idx)) continue;
    if (typeof b.n !== "number" || !Number.isFinite(b.n) || b.n <= 0) continue;
    if (typeof b.winners !== "number" || !Number.isFinite(b.winners)) continue;
    if (typeof b.sum_prob !== "number" || !Number.isFinite(b.sum_prob)) continue;

    const acc = pooled.get(b.bucket_idx) ?? { n: 0, winners: 0, sumProb: 0 };
    acc.n += b.n;
    acc.winners += b.winners;
    acc.sumProb += b.sum_prob;
    pooled.set(b.bucket_idx, acc);
  }

  let total = 0;
  for (const v of pooled.values()) total += v.n;
  if (total <= 0) return null;

  let ece = 0;
  for (const v of pooled.values()) {
    // Both are rates in [0,1]; × 100 once at the end keeps this in pp.
    ece += (v.n / total) * Math.abs(v.winners / v.n - v.sumProb / v.n);
  }
  return ece * 100;
}

/**
 * That figure as the card's display text (one decimal), or `null`.
 *
 * Separate from the arithmetic so a test can assert the measured value exactly
 * without reading it back out of a rounded string.
 */
export function proofCalibrationErrorText(buckets: unknown): string | null {
  const pp = populationCalibrationErrorPp(buckets);
  return pp === null ? null : pp.toFixed(1);
}
