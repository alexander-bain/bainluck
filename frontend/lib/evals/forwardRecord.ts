/**
 * "DO MARKET PROBABILITIES COME TRUE?" — the forward record on /evals (#12102, S3).
 *
 * LIVE: everything here is read from `GET /api/calibration` when the page
 * opens, stamped with the payload's own `generated_at`. Nothing is computed
 * that `/about` or `/calibration` does not already compute, and it is computed
 * by their code, so the three surfaces cannot disagree:
 *
 *   • the figure is `/about`'s proof figure — `proofCohortFigures` over the
 *     served buckets, the traded-market cohort, with `compactOutcomeCount` for
 *     the count. The count is the cohort's, never `total_outcomes`: printing the
 *     whole payload's count beside the cohort's error is the #7202 / #7564
 *     defect;
 *   • the curve is `/calibration`'s default series —
 *     `aggregateBuckets(buckets, cohortFilterFor(false))`, labelled by
 *     `describeCohort`, drawn with the same thin-bucket floor;
 *   • the staleness notice is `decideCalibrationStaleness`, the one the
 *     accuracy page banners with.
 *
 * The categories meter reads the scorecard block: categories at the bar, out of
 * the categories scored, and the bar itself in points — all three from the
 * payload. A field the payload does not carry is `null`, and its line is not
 * shown; nothing is defaulted to a number the server did not write.
 */

import { compactOutcomeCount, proofCohortFigures } from "@/lib/calibrationProofFigures";
import { describeCohort, partitionByActivity } from "@/lib/calibrationCohort";
import { aggregateBuckets, cohortFilterFor, type AggBucket } from "@/lib/calibrationParity";
import {
  decideCalibrationStaleness,
  type CalibrationStalenessInput,
  type CalibrationStalenessNotice,
} from "@/lib/calibrationStaleness";

/**
 * `/calibration`'s `MIN_CHART_BUCKET_N`: a bucket with fewer outcomes is drawn
 * as a faint dashed stretch. The page keeps its constant private, so
 * `__tests__/forwardRecord.test.ts` reads it from the page source and fails if
 * the two drift apart.
 */
export const CHART_THIN_FLOOR = 1000;

/** `/calibration`'s colour for its default (never-moved excluded) curve. */
export const DEFAULT_CURVE_COLOR = "#16a34a";

export interface ForwardRecordView {
  /** The payload's own build time — the LIVE chip's "as of". */
  generatedAt: string | null;
  proof: {
    outcomes: number;
    outcomesText: string;
    errorPp: number;
    errorText: string;
  } | null;
  categories: { atBar: number; total: number; barPp: number } | null;
  curve: { data: AggBucket[]; label: string } | null;
  staleness: CalibrationStalenessNotice | null;
}

const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

function readCategories(scorecard: unknown): ForwardRecordView["categories"] {
  if (!scorecard || typeof scorecard !== "object") return null;
  const s = scorecard as Record<string, unknown>;
  const atBar = s.categories_at_bar;
  const total = s.categories_total;
  const barPp = s.categories_bar_pp;
  if (!finite(atBar) || !finite(total) || !finite(barPp) || total <= 0 || atBar < 0 || atBar > total) {
    return null;
  }
  return { atBar, total, barPp };
}

/** The bar in points as the page prints it: 3.0 → "3", 2.5 → "2.5". */
export function barPointsText(barPp: number): string {
  return Number.isInteger(barPp) ? String(barPp) : barPp.toFixed(1);
}

export function forwardRecordView(data: unknown): ForwardRecordView {
  const d = (data && typeof data === "object" ? data : {}) as Record<string, unknown>;
  const buckets = Array.isArray(d.buckets) ? d.buckets : [];

  const figures = proofCohortFigures(buckets);
  const outcomesText = figures ? compactOutcomeCount(figures.outcomes) : null;
  const proof =
    figures && outcomesText
      ? {
          outcomes: figures.outcomes,
          outcomesText,
          errorPp: figures.errorPp,
          errorText: figures.errorPp.toFixed(1),
        }
      : null;

  // `/calibration` aggregates `normalized` (categories renamed for display);
  // the cohort filter never reads the category, so the raw rows give the same
  // series. The test holds the two equal on a fixture.
  const usable = buckets.filter(
    (b): b is { bucket_idx: number; n: number; winners: number; sum_prob: number; sum_sq_err: number; price_moved?: boolean | null } =>
      !!b &&
      typeof b === "object" &&
      finite((b as Record<string, unknown>).bucket_idx) &&
      finite((b as Record<string, unknown>).n) &&
      finite((b as Record<string, unknown>).winners) &&
      finite((b as Record<string, unknown>).sum_prob) &&
      finite((b as Record<string, unknown>).sum_sq_err)
  );
  const curveData = aggregateBuckets(usable, cohortFilterFor(false));
  const fullN = usable.reduce((s, b) => s + b.n, 0);
  const cohortN = curveData.reduce((s, b) => s + b.n, 0);
  const curve =
    curveData.length > 0
      ? {
          data: curveData,
          label: `${describeCohort(partitionByActivity(usable), fullN, false).shortLabel} (${cohortN.toLocaleString()})`,
        }
      : null;

  return {
    generatedAt: typeof d.generated_at === "string" && d.generated_at ? d.generated_at : null,
    proof,
    categories: readCategories(d.scorecard),
    curve,
    staleness: decideCalibrationStaleness(d as CalibrationStalenessInput),
  };
}
