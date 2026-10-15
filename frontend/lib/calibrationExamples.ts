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

import type { CalibrationExamplesSampling } from "./api";

export const EXAMPLES_FOOTER_DEFAULT = "A representative sample — not the full bucket.";

export const EXAMPLES_FOOTER_CURRENT_ROWS =
  "A sample of current outcomes in this range — not the full bucket. " +
  "The chart may come from an earlier update, so the two can differ.";

export function examplesFooterCopy(
  sampling: CalibrationExamplesSampling | null | undefined,
): string {
  if (
    sampling?.basis === "live_canonical_population" &&
    sampling.published_generation_membership !== "verified"
  ) {
    return EXAMPLES_FOOTER_CURRENT_ROWS;
  }
  return EXAMPLES_FOOTER_DEFAULT;
}
