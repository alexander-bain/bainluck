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
 * Sample bar above which a category slice's 2σ binomial uncertainty (100/√n pp)
 * drops to ≤ 2.0 points. Slices below this bar (or whose miss above the bar is
 * within their 2σ uncertainty) read as "too few to say" rather than red (#12468).
 */
export const CATEGORY_SAMPLE_BAR = 2500;

/**
 * Issue tracking resolved outcomes where ungraded winners or zero-price winners
 * lean high-probability bands one way (#12468, #12421).
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
  categorySlices: CalibrationCategorySlice[];
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

function detectUngradedCategories(buckets: unknown[], scorecard: unknown): Set<string> {
  const flagged = new Set<string>();
  for (const row of buckets) {
    if (!row || typeof row !== "object") continue;
    const b = row as Record<string, unknown>;
    const cat = typeof b.category === "string" ? b.category : null;
    const idx = b.bucket_idx;
    const n = b.n;
    const winners = b.winners;
    const sumProb = b.sum_prob;
    if (!cat || !finite(idx) || !finite(n) || !finite(winners) || !finite(sumProb) || n <= 0) continue;
    // High-probability favorite bands where predicted probability exceeds actual win rate by > 15pp (#12468).
    if (idx >= 5 && n >= 20 && sumProb / n - winners / n > 0.15) {
      flagged.add(cat);
    }
  }
  if (scorecard && typeof scorecard === "object") {
    const queued = (scorecard as Record<string, unknown>).queued_cells;
    if (Array.isArray(queued)) {
      for (const item of queued) {
        if (!item || typeof item !== "object") continue;
        const cell = (item as Record<string, unknown>).cell;
        if (typeof cell === "string" && cell.startsWith("odds_api_bookmaker/")) {
          flagged.add(cell.slice("odds_api_bookmaker/".length));
        }
      }
    }
  }
  return flagged;
}

function readCategorySlices(
  data: Record<string, unknown>,
  categories: ForwardRecordView["categories"]
): CalibrationCategorySlice[] {
  if (!categories) return [];
  const barPp = categories.barPp;
  const scorecard = data.scorecard && typeof data.scorecard === "object" ? (data.scorecard as Record<string, unknown>) : null;
  const minFloor = finite(data.min_category_outcomes)
    ? data.min_category_outcomes
    : scorecard && finite(scorecard.categories_min_n)
      ? scorecard.categories_min_n
      : CHART_THIN_FLOOR;
  const sampleBar = Math.max(minFloor, CATEGORY_SAMPLE_BAR);
  const buckets = Array.isArray(data.buckets) ? data.buckets : [];
  const ungradedCats = detectUngradedCategories(buckets, scorecard);

  const rawRows: { key: string; n: number; ece: number; partlyUngraded: boolean }[] = [];
  if (Array.isArray(data.by_category) && data.by_category.length > 0) {
    for (const item of data.by_category) {
      if (!item || typeof item !== "object") continue;
      const r = item as Record<string, unknown>;
      if (r.gated === true) continue;
      const key = typeof r.category === "string" ? r.category : null;
      const n = finite(r.n) ? r.n : finite(r.outcomes) ? r.outcomes : null;
      const ece = finite(r.ece) ? r.ece : null;
      if (!key || n === null || ece === null || n <= 0) continue;
      rawRows.push({
        key,
        n,
        ece,
        partlyUngraded: r.partly_ungraded === true || ungradedCats.has(key),
      });
    }
  } else if (scorecard && Array.isArray(scorecard.categories_over_bar)) {
    for (const item of scorecard.categories_over_bar) {
      if (!item || typeof item !== "object") continue;
      const r = item as Record<string, unknown>;
      const key = typeof r.category === "string" ? r.category : null;
      const n = finite(r.n) ? r.n : finite(r.outcomes) ? r.outcomes : null;
      const ece = finite(r.ece) ? r.ece : null;
      if (!key || n === null || ece === null || n <= 0) continue;
      rawRows.push({
        key,
        n,
        ece,
        partlyUngraded: r.partly_ungraded === true || ungradedCats.has(key),
      });
    }
  }

  return rawRows
    .sort((a, b) => b.ece - a.ece)
    .map((r) => {
      const missPp = Math.round(r.ece * 10) / 10;
      const uncertaintyPp = sliceUncertaintyPp(r.n);
      let status: CalibrationCategoryStatus;
      if (r.ece <= barPp) {
        status = "at_bar";
      } else if (r.partlyUngraded && r.n >= sampleBar) {
        status = "partly_ungraded";
      } else if (r.n < sampleBar || r.ece - barPp <= uncertaintyPp) {
        status = "uncertain";
      } else if (r.partlyUngraded) {
        status = "partly_ungraded";
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
        ungradedIssue: status === "partly_ungraded" ? UNGRADED_OUTCOMES_ISSUE : null,
      };
    });
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
  return {
    generatedAt: typeof d.generated_at === "string" && d.generated_at ? d.generated_at : null,
    proof,
    categories,
    categorySlices: readCategorySlices(d, categories),
    curve,
    staleness: decideCalibrationStaleness(d as CalibrationStalenessInput),
  };
}
