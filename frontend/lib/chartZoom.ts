/**
 * L2-164: pure helpers for the FuturesChart low-probability zoom chip.
 *
 * The fixed 0–100% axis stays the default so movement is never silently
 * exaggerated (#883 blend-line principle). For long-horizon low-prob series
 * (season journeys), the user can opt into a rounded zoom; these helpers keep the
 * bound math and eligibility rule out of the render body so both directions are
 * unit-testable.
 */

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
}): number {
  const { dataMax, fixedYAxis, zoomed, allowZoom, mini } = opts;
  if (canZoomSeries(dataMax, allowZoom, mini) && zoomed) {
    return computeZoomBound(dataMax);
  }
  return fixedYAxis ? 1 : Math.min(1, dataMax * 1.1);
}
