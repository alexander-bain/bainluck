// #999 L2-75: pure calibration math extracted from the /calibration page so it's
// unit-testable without SWR/data mocking. ECE is the n-weighted headline metric
// (reflects the outcomes users actually see); MCE is the equal-weighted
// worst-bucket-sensitivity number (a tiny bucket counts as much as a huge one).

export interface CalibrationErrorBucket {
  n: number;
  /** actual - predicted, in percentage points. */
  error: number;
}

/** Equal-weighted mean |error| (pp). Worst-bucket sensitive. */
export function mce(cal: CalibrationErrorBucket[]): number {
  if (!cal.length) return 0;
  return cal.reduce((s, b) => s + Math.abs(b.error), 0) / cal.length;
}

/** n-weighted mean |error| (pp). The headline calibration metric. */
export function ece(cal: CalibrationErrorBucket[]): number {
  const totalN = cal.reduce((s, b) => s + b.n, 0);
  if (!totalN) return 0;
  return cal.reduce((s, b) => s + (b.n / totalN) * Math.abs(b.error), 0);
}

// ---------------------------------------------------------------------------
// L2-230 / C111 [P1]: the trading-activity comparison.
//
// The page used to render an UNCONDITIONAL claim — "outcomes where the price
// moved are dramatically better calibrated" — plus `(unchangedECE / movedECE)`
// followed by the words "more accurately calibrated". Both are wrong whenever
// the observed ordering reverses, and on 2026-08-02 it had: price moved 1.7pp,
// price unchanged 1.0pp, rendering the literal sentence "Markets with active
// trading are 0.6x more accurately calibrated". A ratio below 1 printed as
// "more accurately" is not a wording nit — it inverts the number beside it.
//
// So the comparison is derived here, from the SAME values the page prints, and
// it states only the observed ordering. Two rules make that safe:
//
//   1. Compare at DISPLAY precision. If the page shows two cohorts as "1.0pp"
//      and "1.0pp", prose that ranks one above the other contradicts the pixels
//      next to it. Rounding first makes the tie state fall out for free, and
//      makes 0.05pp the tolerance rather than an invented threshold.
//   2. Never infer cause. C111 [P2] showed this aggregate is composition
//      sensitive: a synthetic mix where moved was better within BOTH strata
//      still inverted in aggregate. An ordering is an ordering. When it can't
//      be computed honestly, we say nothing — nothing > unhelpful.
// ---------------------------------------------------------------------------

/** Decimal places every ECE on the calibration page is rendered with. */
const ECE_DISPLAY_DP = 1;

/** One side of the activity split, as the page has it. */
export interface ActivityCohort {
  /** n-weighted ECE in percentage points. */
  ece: number | null | undefined;
  /** Outcomes behind it. Absent or <= 0 means there is nothing to compare. */
  n: number | null | undefined;
}

export interface ActivityComparison {
  /** Which cohort carries the HIGHER error, judged at display precision. */
  direction: "moved_higher" | "unchanged_higher" | "tied" | "unknown";
  /** Moved cohort ECE exactly as printed, e.g. "1.7". null when unusable. */
  movedText: string | null;
  /** Unchanged cohort ECE exactly as printed. null when unusable. */
  unchangedText: string | null;
  /** higher ÷ lower at display precision, e.g. "1.7". null when unstateable. */
  ratioText: string | null;
  /** The sentence to render. null means render no comparison at all. */
  sentence: string | null;
}

const UNRENDERABLE: ActivityComparison = {
  direction: "unknown",
  movedText: null,
  unchangedText: null,
  ratioText: null,
  sentence: null,
};

/** A cohort is usable only if it has outcomes AND a finite, non-negative ECE. */
function cohortValue(c: ActivityCohort | null | undefined): number | null {
  if (!c) return null;
  const { ece: e, n } = c;
  if (typeof n !== "number" || !Number.isFinite(n) || n <= 0) return null;
  if (typeof e !== "number" || !Number.isFinite(e) || e < 0) return null;
  // Round to what the reader actually sees before anything is compared.
  return Number(e.toFixed(ECE_DISPLAY_DP));
}

/**
 * Direction-aware, causation-free description of the trading-activity split.
 *
 * Returns `sentence: null` for every state where a comparison cannot be made
 * honestly — a missing cohort, an empty cohort, NaN/Infinity, a negative ECE.
 * The caller renders nothing in that case rather than guessing.
 */
export function describeActivityComparison(
  moved: ActivityCohort | null | undefined,
  unchanged: ActivityCohort | null | undefined
): ActivityComparison {
  const m = cohortValue(moved);
  const u = cohortValue(unchanged);
  if (m === null || u === null) return UNRENDERABLE;

  const movedText = m.toFixed(ECE_DISPLAY_DP);
  const unchangedText = u.toFixed(ECE_DISPLAY_DP);
  const lead = `Price moved sits at ${movedText}pp and price unchanged at ${unchangedText}pp`;

  if (m === u) {
    return {
      direction: "tied",
      movedText,
      unchangedText,
      ratioText: null,
      sentence: `${lead} — effectively the same calibration error in this sample.`,
    };
  }

  const movedHigher = m > u;
  const higher = movedHigher ? m : u;
  const lower = movedHigher ? u : m;
  const higherLabel = movedHigher ? "price-moved" : "price-unchanged";
  const lowerLabel = movedHigher ? "price-unchanged" : "price-moved";

  // The ratio is suppressed when the smaller side rounds to 0.0pp (division by
  // zero) and when it would print as "1.0x", which reads as "the same" beside
  // prose that just said one is higher.
  let ratioText: string | null = null;
  if (lower > 0) {
    const r = (higher / lower).toFixed(ECE_DISPLAY_DP);
    if (r !== "1.0") ratioText = r;
  }

  const tail = ratioText
    ? `, ${ratioText}x the ${lowerLabel} cohort's`
    : "";
  return {
    direction: movedHigher ? "moved_higher" : "unchanged_higher",
    movedText,
    unchangedText,
    ratioText,
    sentence:
      `${lead} — in this sample the ${higherLabel} cohort carries the ` +
      `higher calibration error${tail}.`,
  };
}

/** "Jul 2026" from an ISO date; echoes the raw string if unparseable. */
export function monthYear(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString("en-US", { month: "short", year: "numeric" });
}
