// CAL-P043 (#1643, codex C236) — web's half of the cross-surface parity record.
//
// ## Why this module exists
//
// Native has published a `Parity` descriptor since CAL-P026: one struct carrying
// every figure the calibration surface leads with, rendered from and published
// as the same value. Web published the same FACTS, but scattered across a dozen
// `data-*` attributes computed inline inside `app/calibration/page.tsx` — a
// "use client" component behind SWR. Two consequences, and the second is the
// one that mattered:
//
//   1. No single value described web's surface, so there was nothing to compare
//      against native's `Parity`.
//   2. `aggregateBuckets` and `brierScore` lived INSIDE the page component file
//      and were not exported. A gate could not call the code the page renders
//      from, so the only thing left to assert against was a constant — which is
//      exactly what `calibrationSurfaceParity.contract.test.js` did, and why it
//      proved nothing (#1643).
//
// So the math moves here, the record is built here, and the page renders from
// the same record it publishes. Ruling 003 — clients format, never adjudicate:
// one derivation, formatted at the edge, never two derivations that can drift.
//
// ## What this is NOT
//
// It is not a re-implementation of anything. `aggregateBuckets`, `wilsonCI` and
// `brierScore` are moved verbatim from `page.tsx`; `ece`/`mce` still come from
// `calibrationMath.ts`. A "parity module" that recomputed the figures its own
// way would publish numbers the page does not render, which is a worse failure
// than the one it replaces.

import { ece, mce } from "@/lib/calibrationMath";

/**
 * The only fields the parity math reads.
 *
 * Deliberately narrower than `CalibrationBucket`: the frozen fixture rows carry
 * exactly these, the live API type carries them plus `avg_prob`/`ci_lower`/
 * `ci_upper`, and requiring the wider type here would mean the gate could not be
 * run against the fixture the two surfaces are graded on — which is how the
 * previous gate ended up asserting against constants instead.
 */
export interface ParityBucket {
  bucket_idx: number;
  n: number;
  winners: number;
  sum_prob: number;
  sum_sq_err: number;
  price_moved?: boolean | null;
}

/** One probability bin, aggregated across every dimension but `bucket_idx`. */
export interface AggBucket {
  midpoint: number;
  n: number;
  winners: number;
  avgProb: number;
  actual: number;
  error: number;
  bucket: string;
  ciLower: number;
  ciUpper: number;
}

export function wilsonCI(wins: number, total: number, z = 1.96): [number, number] {
  if (total === 0) return [0, 0];
  const p = wins / total;
  const denom = 1 + (z * z) / total;
  const center = (p + (z * z) / (2 * total)) / denom;
  const spread = (z * Math.sqrt((p * (1 - p) + (z * z) / (4 * total)) / total)) / denom;
  return [Math.max(0, center - spread), Math.min(1, center + spread)];
}

export function aggregateBuckets<T extends ParityBucket>(
  buckets: T[],
  filter?: (b: T) => boolean
): AggBucket[] {
  const agg: Record<number, { n: number; winners: number; sumProb: number; sumSqErr: number }> = {};
  for (const b of buckets) {
    if (filter && !filter(b)) continue;
    const idx = b.bucket_idx;
    if (!agg[idx]) agg[idx] = { n: 0, winners: 0, sumProb: 0, sumSqErr: 0 };
    agg[idx].n += b.n;
    agg[idx].winners += b.winners;
    agg[idx].sumProb += b.sum_prob;
    agg[idx].sumSqErr += b.sum_sq_err;
  }
  return Object.entries(agg)
    .map(([idx, a]) => {
      const i = parseInt(idx);
      const avgProb = a.sumProb / a.n;
      const actual = a.winners / a.n;
      const [ciLo, ciHi] = wilsonCI(a.winners, a.n);
      return {
        midpoint: i * 10 + 5,
        n: a.n,
        winners: a.winners,
        avgProb: Math.round(avgProb * 1000) / 10,
        actual: Math.round(actual * 1000) / 10,
        error: Math.round((actual - avgProb) * 1000) / 10,
        bucket: `${i * 10}-${i * 10 + 10}%`,
        ciLower: Math.round(ciLo * 1000) / 10,
        ciUpper: Math.round(ciHi * 1000) / 10,
      };
    })
    .sort((a, b) => a.midpoint - b.midpoint);
}

export function brierScore<T extends ParityBucket>(
  buckets: T[],
  filter?: (b: T) => boolean
): number {
  let n = 0, sq = 0;
  for (const b of buckets) {
    if (filter && !filter(b)) continue;
    n += b.n;
    sq += b.sum_sq_err;
  }
  return n > 0 ? sq / n : 0;
}

/**
 * The default cohort's predicate.
 *
 * `price_moved` is a TRI-state. The default cohort keeps real trades (`true`)
 * AND sportsbook consensus (`null`, always a live line, where "did trading move
 * the price" is not a question the source can answer), and excludes only the
 * outcomes whose price never moved off its opening line (`false`). The toggle
 * layers the excluded side back in; it never hides.
 *
 * Exported because native carries the identical predicate
 * (`thin || $0.priceMoved != false`) and a parity record is worthless if the two
 * surfaces are describing different populations. See `lib/calibrationCohort.ts`.
 */
export function cohortFilterFor(
  includeNeverMoved: boolean
): ((b: ParityBucket) => boolean) | undefined {
  if (includeNeverMoved) return undefined;
  return (b: ParityBucket) => b.price_moved !== false;
}

/**
 * Everything the calibration surface leads with, as machine-readable data.
 *
 * The native analogue is `CalibrationViewModel.Parity`, field for field. The
 * names differ in case only (Swift camelCase, the shared JSON record
 * snake_case) and `fixtures/calibration/parity-record-2026-08-02.json` is the
 * artifact both are held against.
 */
export interface CalibrationParity {
  populationVersion: string;
  contractState: string;
  cacheStatus: string;
  generatedAt: string;
  markets: number;
  /** The population the surface LEADS with — cohort-dependent. */
  cohortN: number;
  /** Every resolved outcome in the payload, toggle-independent. */
  fullN: number;
  movedN: number;
  unchangedN: number;
  notApplicableN: number;
  ece: number;
  mce: number;
  brier: number;
}

/** The activity partition invariant, published as `data-partition-reconciles`. */
export function parityReconciles(p: CalibrationParity): boolean {
  return p.movedN + p.unchangedN + p.notApplicableN === p.fullN;
}

export interface CalibrationParityInput {
  population_version?: string | null;
  cache?: { status?: string; generated_at?: string } | null;
  generated_at?: string | null;
  total_markets?: number | null;
  buckets: ParityBucket[];
}

/**
 * Build the complete parity record for one cohort-toggle state.
 *
 * `contractState` is passed IN rather than decided here: what this build thinks
 * of the served population is `decideCalibrationContract`'s call, and one place
 * deciding is the whole point of that module. Threading it through keeps the
 * record complete without giving a second module a vote.
 */
export function buildCalibrationParity(
  data: CalibrationParityInput,
  includeNeverMoved: boolean,
  contractState: string,
): CalibrationParity {
  const buckets = data.buckets ?? [];
  const filter = cohortFilterFor(includeNeverMoved);
  const cohortBuckets = aggregateBuckets(buckets, filter);

  const sumN = (pred?: (b: ParityBucket) => boolean) =>
    buckets.reduce((s, b) => (!pred || pred(b) ? s + b.n : s), 0);

  return {
    populationVersion: data.population_version ?? "",
    contractState,
    cacheStatus: data.cache?.status ?? "fresh",
    // The served snapshot's build time when there is one, else the payload's.
    // Native resolves it the same way and in the same order.
    generatedAt: data.cache?.generated_at ?? data.generated_at ?? "",
    markets: data.total_markets ?? 0,
    cohortN: sumN(filter),
    fullN: sumN(),
    movedN: sumN(b => b.price_moved === true),
    unchangedN: sumN(b => b.price_moved === false),
    notApplicableN: sumN(b => b.price_moved === null || b.price_moved === undefined),
    ece: ece(cohortBuckets),
    mce: mce(cohortBuckets),
    brier: brierScore(buckets, filter),
  };
}

/**
 * The parity record as ONE string, in the grammar native publishes as the
 * surface's `accessibilityValue`.
 *
 * `key=value` pairs, space-separated, stable order — parseable without a grammar
 * and readable in Accessibility Inspector without one either. Web publishes it
 * as `data-parity` so the two surfaces can be compared by string equality rather
 * than by a translation table nobody maintains.
 *
 * Raw values only. A formatted figure ("1.5pp", "652,407") is a presentation
 * decision; comparing those across surfaces fails on a thousands separator and
 * passes on a wrong number, which is the exact hazard C236 named.
 */
export function parityValue(p: CalibrationParity): string {
  return [
    `population=${p.populationVersion || "none"}`,
    `contract=${p.contractState}`,
    `cache=${p.cacheStatus}`,
    `generated=${p.generatedAt || "none"}`,
    `cohort_n=${p.cohortN}`,
    `full_n=${p.fullN}`,
    `moved_n=${p.movedN}`,
    `unchanged_n=${p.unchangedN}`,
    `not_applicable_n=${p.notApplicableN}`,
    `markets=${p.markets}`,
    `ece=${p.ece.toFixed(4)}`,
    `mce=${p.mce.toFixed(4)}`,
    `brier=${p.brier.toFixed(4)}`,
    `reconciles=${parityReconciles(p)}`,
  ].join(" ");
}
