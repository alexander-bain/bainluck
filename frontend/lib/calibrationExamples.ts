// #994 — the drill-in's footer says which rows the reader is looking at.
//
// `/calibration/examples` samples futures sources (Kalshi, Polymarket and now
// DataGolf) from the canonical population evaluated NOW. The curve on the page
// can be an older published update, and nothing in the response proves a sampled
// row was in THAT update — the backend says so as
// `sampling.published_generation_membership: "unverified"`. A field no screen
// reads tells the reader nothing, so this is where it becomes one short caption.
//
// Kept out of the `"use client"` page so a test can call it (CAL-P1024 / #1865).

import type { CalibrationExample, CalibrationExamplesSampling } from "./api";

export const EXAMPLES_FOOTER_DEFAULT = "A representative sample — not the full bucket.";

export const EXAMPLES_FOOTER_CURRENT_ROWS =
  "A sample of current outcomes in this range — not the full bucket. " +
  "The chart may come from an earlier update, so the two can differ.";

// #994: the DataGolf drill-in can now sample the exact rows the published
// chart counted. When the backend proves that (`basis: "published_generation"`,
// membership `"verified"`), the footer says so instead of hedging.
export const EXAMPLES_FOOTER_PUBLISHED =
  "A random sample of the outcomes this chart counted — not the full bucket.";

export function examplesFooterCopy(
  sampling: CalibrationExamplesSampling | null | undefined,
): string {
  if (
    sampling?.basis === "live_canonical_population" &&
    sampling.published_generation_membership !== "verified"
  ) {
    return EXAMPLES_FOOTER_CURRENT_ROWS;
  }
  if (
    sampling?.basis === "published_generation" &&
    sampling.published_generation_membership === "verified"
  ) {
    return EXAMPLES_FOOTER_PUBLISHED;
  }
  return EXAMPLES_FOOTER_DEFAULT;
}

// #994: a published example shows the grade the chart counted. If that grade
// has been corrected since, the row must not present the old one as current,
// so it carries a short note with today's grade. `null` when nothing changed
// (or when the row is not a published-membership example at all).
export function correctedGradeNote(example: CalibrationExample): string | null {
  if (example.result_basis !== "published" || !example.grade_changed_since_publish) {
    return null;
  }
  return example.current_result ? `now ${example.current_result}` : "now ungraded";
}
