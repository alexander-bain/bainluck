/**
 * L2-164: pure helpers for the FuturesChart low-probability zoom chip.
 *
 * The fixed 0–100% axis stays the default so movement is never silently
 * exaggerated — P4 of `docs/chart-design-spec.md`, "Fixed 0–100 axis, no drama-zoom",
 * which forbids an AUTOMATIC rescale as a D1 enticement pattern but not a labelled
 * zoom the reader asks for. (Corrected #4259: this was cited as the "#883 blend-line
 * principle"; #883 is the futures page redesign and does not contain the rule.)
 *
 * For long-horizon low-prob series (season journeys) and for FIELD charts — a
 * 60-outcome golf tournament cannot put a line above ~30%, so the fixed axis strands
 * the whole field at the floor (#4259) — the user can opt into a rounded zoom; these
 * helpers keep the bound math and eligibility rule out of the render body so both
 * directions are unit-testable.
 */

import { ceilingForMax } from "./chartCeiling";

/** Round the zoom cap UP to a clean 5% step with a little headroom, so the chip
 *  label reads as a tidy bound ("Zoom 0–20%") rather than a ragged data max. */
export function computeZoomBound(dataMax: number): number {
  return Math.min(1, Math.max(0.05, Math.ceil((dataMax * 1.1) / 0.05) * 0.05));
}

/** The chip is only offered when the fixed axis genuinely wastes vertical space
 *  (a low-prob line) and we're not rendering a sparkline. */
export function canZoomSeries(dataMax: number, allowZoom: boolean, mini: boolean): boolean {
  return allowZoom && !mini && dataMax > 0 && dataMax < 0.5;
}

/** The effective y-axis max given the fixed/zoom state. When zoomed (and eligible)
 *  it snaps to the rounded bound; otherwise it honors the fixed 0–100% default (or
 *  the rare auto-scale opt-out). */
export function resolveYAxisMax(opts: {
  dataMax: number;
  fixedYAxis: boolean;
  zoomed: boolean;
  allowZoom: boolean;
  mini: boolean;
  /** #4259: this surface is a FIELD chart (many outcomes, nobody near 100%), so its
   *  axis top steps down the #2451 ladder instead of sitting at a flat 100%. Opt-in
   *  per call site so no two-sided chart moves. A user-driven zoom still wins over
   *  it — the reader's explicit choice outranks the automatic rung. */
  fieldCeiling?: boolean;
}): number {
  const { dataMax, fixedYAxis, zoomed, allowZoom, mini, fieldCeiling = false } = opts;
  if (canZoomSeries(dataMax, allowZoom, mini) && zoomed) {
    return computeZoomBound(dataMax);
  }
  // Sparklines keep the flat axis: at 80px tall there is no plot to reclaim, and a
  // mini chart carries no labels to declare a moved top with.
  if (fieldCeiling && !mini && dataMax > 0) {
    return ceilingForMax(dataMax);
  }
  return fixedYAxis ? 1 : Math.min(1, dataMax * 1.1);
}
