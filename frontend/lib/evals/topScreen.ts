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

/**
 * The probability picture's drawing box, in SVG units. 84 tall, not 96 (Nov 6):
 * under #12227's "Get the app" bar the first phone screen must still hold the
 * accuracy note's longest form, "We can't confirm the curve is current. …",
 * which takes two lines at 390 px.
 */
export const TRUTH_PLOT = { width: 320, height: 84, left: 28, right: 4, top: 4, bottom: 13 } as const;

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

/**
 * The worked example under the probability picture: the group whose stated
 * probability is nearest to the typical "likely" call, among groups big enough
 * to draw solid. Its two numbers are the live payload's, so "when we said X, it
 * happened Y of the time" is read, never written. Null when no group qualifies.
 */
export const EXAMPLE_TARGET_PCT = 70;

export function truthExample(dots: TruthDot[]): TruthDot | null {
  const solid = dots.filter((d) => !d.thin);
  if (solid.length === 0) return null;
  return solid.reduce((best, d) =>
    Math.abs(d.said - EXAMPLE_TARGET_PCT) < Math.abs(best.said - EXAMPLE_TARGET_PCT) ? d : best
  );
}

/** A whole percent for a reader: 72.4 → "72%". */
export function wholePercent(pct: number): string {
  return `${Math.round(pct)}%`;
}

/**
 * One mark per case of one kind for the reviewer picture: right when every try
 * recorded so far was the right call, wrong when any was not, not yet when no
 * try is in.
 */
export type CaseMark = "right" | "wrong" | "not_yet";

export function caseMarks(results: ReviewerResults, study: ReviewerStudy, kind: "defect" | "control"): CaseMark[] {
  const right: ReviewOutcome = kind === "defect" ? "caught" : "passed";
  return study.cases
    .filter((c) => c.kind === kind)
    .map((c) => {
      const tries = results.results.filter((r) => r.case === c.id);
      if (tries.length === 0) return "not_yet";
      return tries.every((r) => r.outcome === right) ? "right" : "wrong";
    });
}
