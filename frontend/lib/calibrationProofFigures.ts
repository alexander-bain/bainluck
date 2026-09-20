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


// #7564 — the proof card's error figure and the population it is measured on.
//
// The card read "across 0.7M resolved outcomes, our numbers land within 1.5
// points of what actually happened", sourcing the 1.5 from `mce_closing_line`
// and falling back to `Math.max(by_source[].ece)`. Measured on the served
// payload (generated_at 2026-09-15T11:16:10Z), three things were wrong:
//
//  1. POPULATION. `mce_closing_line` is `_cohort_mce(buckets, True)`
//     (`precompute_calibration.py:7224`), scoped to `price_moved=true` —
//     293,900 rows. The sentence named 747,028. The other 453,128 were outside
//     it. #7472 removed that same pair from /calibration for this reason.
//  2. STATISTIC. `_cohort_mce` returns a MEAN of ten per-bucket errors, not a
//     maximum, despite the name — so "land WITHIN 1.5 points" asserted a bound
//     the number cannot carry. The worst bucket in that cohort is 3.49pp off.
//  3. METRIC. It is the equal-weight bucket average, which /calibration tells
//     the reader reads BELOW its n-weighted ECE headline (`page.tsx:1417`).
//
// The fallback was a landmine too: `Math.max(by_source.ece)` is 36.49 today —
// #6211's censored 36-outcome DataGolf row — one null scalar away from the
// card reading "within 36.5 points".
//
// WHY THE COHORT, AND NOT THE WHOLE PAYLOAD. The first cut of this fix used an
// n-weighted ECE over all 747,028 rows, on the reasoning that it matched the
// count printed beside it. Measured, that reads 0.675pp — LOWER than every
// cohort it is built from (traded 0.911, untraded 0.863, moved 1.228), because
// pooling lets oppositely-signed cohort biases cancel before the absolute value
// is taken. It would have traded one flattering population for another.
//
// #7486 already settled this for the page next door, in those words:
// "Do not reintroduce an unfiltered aggregate here: if a figure is for the
// reader, it is for the cohort on screen." So this reads the SAME cohort
// /calibration defaults to — `cohortFilterFor(false)`, traded markets,
// `price_moved !== false` — and reports its `n` as well as its error, so the
// count and the figure can never again describe different populations.
//
// It composes `aggregateBuckets` + `ece` rather than reimplementing them. That
// is load-bearing, not tidiness: `aggregateBuckets` rounds each bucket's error
// to 0.1pp BEFORE weighting (`calibrationParity.ts:100`), so an independent
// implementation reads 0.911 where the page reads 0.917 — the same "0.9" today
// and a visible disagreement at the next rounding boundary. Sharing the
// pipeline makes the two surfaces agree by construction.
//
// No producer change is involved: `buckets` is already in the payload, so the
// #6868 freeze on `precompute_calibration.py` is untouched.

import { aggregateBuckets, cohortFilterFor, type ParityBucket } from "./calibrationParity";
import { ece } from "./calibrationMath";

export interface ProofCohortFigures {
  /** Outcomes in the cohort — the number the sentence must name. */
  outcomes: number;
  /** That cohort's n-weighted ECE, in percentage points. */
  errorPp: number;
}

const num = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

/**
 * The fields an ECE actually needs, re-shaped into a `ParityBucket`.
 *
 * `sum_sq_err` is deliberately NOT required: `aggregateBuckets` carries it for
 * the Brier score and drops it from its own output, so demanding it here would
 * make a payload that omitted one unused field fall back to editorial copy with
 * nothing on the page to say why. It is defaulted instead.
 */
function asParityBucket(b: unknown): ParityBucket | null {
  if (!b || typeof b !== "object") return null;
  const r = b as Record<string, unknown>;
  if (!num(r.bucket_idx) || !num(r.n) || r.n <= 0) return null;
  if (!num(r.winners) || !num(r.sum_prob)) return null;
  return {
    bucket_idx: r.bucket_idx,
    n: r.n,
    winners: r.winners,
    sum_prob: r.sum_prob,
    sum_sq_err: num(r.sum_sq_err) ? r.sum_sq_err : 0,
    price_moved: typeof r.price_moved === "boolean" ? r.price_moved : null,
  };
}

/**
 * The traded-market cohort's size and calibration error, or `null` when the
 * payload carried nothing measurable.
 *
 * `null` is the caller's signal to keep the editorial fallback copy. There is
 * deliberately no second-choice statistic: a fallback that silently swaps the
 * metric is what put a 36-outcome sample one null away from the card.
 */
export function proofCohortFigures(buckets: unknown): ProofCohortFigures | null {
  if (!Array.isArray(buckets)) return null;
  const usable = buckets
    .map(asParityBucket)
    .filter((b): b is ParityBucket => b !== null);
  if (usable.length === 0) return null;

  const agg = aggregateBuckets(usable, cohortFilterFor(false));
  const outcomes = agg.reduce((s, b) => s + b.n, 0);
  if (outcomes <= 0) return null;

  return { outcomes, errorPp: ece(agg) };
}

/** That error as the card's display text (one decimal), or `null`. */
export function proofCalibrationErrorText(buckets: unknown): string | null {
  const f = proofCohortFigures(buckets);
  return f === null ? null : f.errorPp.toFixed(1);
}
