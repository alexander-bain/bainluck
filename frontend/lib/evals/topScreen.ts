/**
 * The top screen's pictures, as plain geometry and plain readings (#12102).
 *
 * Kept out of the component so the tests can hold each picture to its record
 * without rendering: which dots the probability picture draws and where, and
 * whether its sentence may say "close". Nothing here invents a number; every
 * input is a record's or the live payload's.
 */

import type { AggBucket } from "@/lib/calibrationParity";
import type { ForwardRecordView } from "@/lib/evals/forwardRecord";
import type { ReviewOutcome, ReviewerResults } from "@/lib/evals/reviewerResults";
import type { ReviewerStudy } from "@/lib/evals/reviewerStudy";

/** The probability picture's drawing box, in SVG units. */
export const TRUTH_PLOT = { width: 320, height: 96, left: 28, right: 4, top: 4, bottom: 13 } as const;

export interface TruthDot {
  /** Centre, in SVG units. */
  cx: number;
  cy: number;
  /** What the group was given, and how often it happened, both in percent. */
  said: number;
  happened: number;
  n: number;
  /** Fewer outcomes than the accuracy page's floor: drawn hollow, as that page draws it dashed. */
  thin: boolean;
}

const clampPct = (v: number) => Math.max(0, Math.min(100, v));

/** Percent to SVG units, on each axis. */
export function plotX(pct: number): number {
  const w = TRUTH_PLOT.width - TRUTH_PLOT.left - TRUTH_PLOT.right;
  return TRUTH_PLOT.left + (clampPct(pct) / 100) * w;
}

export function plotY(pct: number): number {
  const h = TRUTH_PLOT.height - TRUTH_PLOT.top - TRUTH_PLOT.bottom;
  return TRUTH_PLOT.top + (1 - clampPct(pct) / 100) * h;
}

/** One dot per group of past markets the live curve has, in the curve's order of probability. */
export function truthDots(curve: AggBucket[], thinFloor: number): TruthDot[] {
  return curve
    .filter((b) => Number.isFinite(b.avgProb) && Number.isFinite(b.actual) && b.n > 0)
    .slice()
    .sort((a, b) => a.avgProb - b.avgProb)
    .map((b) => ({
      cx: plotX(b.avgProb),
      cy: plotY(b.actual),
      said: b.avgProb,
      happened: b.actual,
      n: b.n,
      thin: b.n < thinFloor,
    }));
}

/**
 * What the probability picture's sentence may say. "close" only when the live
 * average miss is inside the payload's own bar for a category; "far" when it is
 * outside; "plain" when the payload lacks either number, so the sentence only
 * explains the picture and claims nothing.
 */
export type TruthReading = "close" | "far" | "plain";

export function truthReading(view: ForwardRecordView): TruthReading {
  if (!view.proof || !view.categories) return "plain";
  return view.proof.errorPp <= view.categories.barPp ? "close" : "far";
}

/** One block per planned review of one kind of case: its outcome when recorded, else not yet. */
export type ReviewBlock = ReviewOutcome | "not_yet";

export function reviewBlocks(results: ReviewerResults, study: ReviewerStudy, kind: "defect" | "control"): ReviewBlock[] {
  const passes = results.planned / study.cases.length;
  const cases = study.cases.filter((c) => c.kind === kind).map((c) => c.id);
  const recorded = results.results.filter((r) => cases.includes(r.case)).map((r) => r.outcome);
  const planned = cases.length * passes;
  return [...recorded, ...Array<ReviewBlock>(Math.max(0, planned - recorded.length)).fill("not_yet")];
}
