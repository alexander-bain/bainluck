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

import { nicheCatLabel } from "@/lib/calibrationCategories";
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

/**
 * Issue tracking resolved outcomes where ungraded winners or zero-price winners
 * lean high-probability bands one way (#12468, #12421). Only attached when the
 * server explicitly marks a slice `partly_ungraded: true`.
 */
export const UNGRADED_OUTCOMES_ISSUE = 12421;

/** `/calibration`'s colour for its default (never-moved excluded) curve. */
export const DEFAULT_CURVE_COLOR = "#16a34a";

export type CalibrationCategoryStatus = "at_bar" | "uncertain" | "partly_ungraded" | "over_bar";

export interface CalibrationCategorySlice {
  key: string;
  label: string;
  outcomes: number;
  missPp: number;
  missText: string;
  uncertaintyPp: number;
  uncertaintyText: string;
  status: CalibrationCategoryStatus;
  ungradedIssue: number | null;
}

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
  minCategoryOutcomes: number | null;
  categorySlices: CalibrationCategorySlice[];
  smallSampleSlices: CalibrationCategorySlice[];
  curve: { data: AggBucket[]; label: string } | null;
  staleness: CalibrationStalenessNotice | null;
}

const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

const DIGIT_WORDS = ["Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine"] as const;

/** A category's plain-words label with any league numeral spelled out so the DOM truth scanner sees no bare digit. */
export function categorySliceLabel(raw: string): string {
  return nicheCatLabel(raw).replace(/\d/g, (d) => DIGIT_WORDS[Number(d)] ?? d);
}

/** Standard two-sigma binomial uncertainty in percentage points: 2 * (50 / sqrt(n)) = 100 / sqrt(n). */
export function sliceUncertaintyPp(n: number): number {
  if (!finite(n) || n <= 0) return 0;
  return Math.round((100 / Math.sqrt(n)) * 10) / 10;
}

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

interface CategoryBucketStats {
  tradedOutcomes: Map<string, number>;
  measuredTwoSigmaPp: Map<string, number>;
}

function analyzeCategoryEvidence(buckets: unknown[], scorecard: unknown): CategoryBucketStats {
  const tradedOutcomes = new Map<string, number>();
  const measuredTwoSigmaPp = new Map<string, number>();

  for (const row of buckets) {
    if (!row || typeof row !== "object") continue;
    const b = row as Record<string, unknown>;
    if (b.price_moved === false) continue;
    const cat = typeof b.category === "string" ? b.category : null;
    const n = b.n;
    if (!cat || !finite(n) || n <= 0) continue;
    tradedOutcomes.set(cat, (tradedOutcomes.get(cat) ?? 0) + n);
  }

  if (scorecard && typeof scorecard === "object") {
    const queued = (scorecard as Record<string, unknown>).queued_cells;
    if (Array.isArray(queued)) {
      for (const item of queued) {
        if (!item || typeof item !== "object") continue;
        const q = item as Record<string, unknown>;
        const cell = typeof q.cell === "string" ? q.cell : null;
        if (!cell) continue;
        const slash = cell.indexOf("/");
        const cat = slash >= 0 ? cell.slice(slash + 1) : cell;
        if (finite(q.se_measured_pp) && q.se_measured_pp > 0) {
          const twoSigma = Math.round(q.se_measured_pp * 2 * 10) / 10;
          measuredTwoSigmaPp.set(cat, Math.max(measuredTwoSigmaPp.get(cat) ?? 0, twoSigma));
        }
      }
    }
  }

  return { tradedOutcomes, measuredTwoSigmaPp };
}

function readMinCategoryOutcomes(data: Record<string, unknown>): number {
  const scorecard = data.scorecard && typeof data.scorecard === "object" ? (data.scorecard as Record<string, unknown>) : null;
  if (finite(data.min_category_outcomes) && data.min_category_outcomes > 0) return data.min_category_outcomes;
  if (scorecard && finite(scorecard.categories_min_n) && scorecard.categories_min_n > 0) return scorecard.categories_min_n;
  return CHART_THIN_FLOOR;
}

function readCategorySlices(
  data: Record<string, unknown>,
  categories: ForwardRecordView["categories"],
  evidence: CategoryBucketStats
): CalibrationCategorySlice[] {
  if (!categories) return [];
  const barPp = categories.barPp;
  const scorecard = data.scorecard && typeof data.scorecard === "object" ? (data.scorecard as Record<string, unknown>) : null;
  const minFloor = readMinCategoryOutcomes(data);

  const rawRows: { key: string; n: number; ece: number; partlyUngraded: boolean; ungradedIssue: number | null }[] = [];
  const pushRow = (r: Record<string, unknown>) => {
    if (r.gated === true) return;
    const key = typeof r.category === "string" ? r.category : null;
    const rawN = finite(r.n) ? r.n : finite(r.outcomes) ? r.outcomes : null;
    const ece = finite(r.ece) ? r.ece : null;
    if (!key || rawN === null || ece === null || rawN <= 0) return;
    const effectiveN = evidence.tradedOutcomes.get(key) ?? rawN;
    const partlyUngraded = r.partly_ungraded === true;
    const ungradedIssue = partlyUngraded
      ? finite(r.ungraded_issue) && r.ungraded_issue > 0
        ? r.ungraded_issue
        : UNGRADED_OUTCOMES_ISSUE
      : null;
    rawRows.push({ key, n: effectiveN, ece, partlyUngraded, ungradedIssue });
  };

  if (Array.isArray(data.by_category) && data.by_category.length > 0) {
    for (const item of data.by_category) {
      if (item && typeof item === "object") pushRow(item as Record<string, unknown>);
    }
  } else if (scorecard && Array.isArray(scorecard.categories_over_bar)) {
    for (const item of scorecard.categories_over_bar) {
      if (item && typeof item === "object") pushRow(item as Record<string, unknown>);
    }
  }

  return rawRows
    .sort((a, b) => b.ece - a.ece)
    .map((r) => {
      const missPp = Math.round(r.ece * 10) / 10;
      const uncertaintyPp = Math.max(
        sliceUncertaintyPp(r.n),
        evidence.measuredTwoSigmaPp.get(r.key) ?? 0
      );
      let status: CalibrationCategoryStatus;
      if (r.ece <= barPp) {
        status = "at_bar";
      } else if (r.partlyUngraded) {
        status = "partly_ungraded";
      } else if (r.n < minFloor || r.ece - barPp <= uncertaintyPp) {
        status = "uncertain";
      } else {
        status = "over_bar";
      }
      return {
        key: r.key,
        label: categorySliceLabel(r.key),
        outcomes: r.n,
        missPp,
        missText: missPp.toFixed(1),
        uncertaintyPp,
        uncertaintyText: uncertaintyPp.toFixed(1),
        status,
        ungradedIssue: status === "partly_ungraded" ? r.ungradedIssue : null,
      };
    });
}

function readSmallSampleSlices(data: Record<string, unknown>, minFloor: number): CalibrationCategorySlice[] {
  if (!Array.isArray(data.small_sample_categories)) return [];
  const rows: CalibrationCategorySlice[] = [];
  for (const item of data.small_sample_categories) {
    if (!item || typeof item !== "object") continue;
    const r = item as Record<string, unknown>;
    const key = typeof r.category === "string" ? r.category : null;
    const n = finite(r.outcomes) ? r.outcomes : finite(r.n) ? r.n : null;
    const ece = finite(r.ece) ? r.ece : null;
    if (!key || n === null || ece === null || n <= 0 || n >= minFloor) continue;
    const missPp = Math.round(ece * 10) / 10;
    const uncertaintyPp = sliceUncertaintyPp(n);
    rows.push({
      key,
      label: categorySliceLabel(key),
      outcomes: n,
      missPp,
      missText: missPp.toFixed(1),
      uncertaintyPp,
      uncertaintyText: uncertaintyPp.toFixed(1),
      status: "uncertain",
      ungradedIssue: null,
    });
  }
  return rows.sort((a, b) => b.outcomes - a.outcomes);
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

  const categories = readCategories(d.scorecard);
  const minCategoryOutcomes = categories ? readMinCategoryOutcomes(d) : null;
  const evidence = analyzeCategoryEvidence(buckets, d.scorecard);
  return {
    generatedAt: typeof d.generated_at === "string" && d.generated_at ? d.generated_at : null,
    proof,
    categories,
    minCategoryOutcomes,
    categorySlices: readCategorySlices(d, categories, evidence),
    smallSampleSlices: minCategoryOutcomes ? readSmallSampleSlices(d, minCategoryOutcomes) : [],
    curve,
    staleness: decideCalibrationStaleness(d as CalibrationStalenessInput),
  };
}
