// #3035 — WHICH END OF A TIME SERIES A PHONE RESTS ON.
//
// The non-mini FuturesChart plot is `min-w-[600px]` inside an `overflow-x-auto`
// card. At a 390px phone width roughly a third of the plot sits outside the
// scroll window, and a scroll container's resting position is its LEFT edge —
// which, for a time series, is the OLDEST data. A reader opening the US Open
// title race saw last week; on the "All" range the entire tournament was
// off-screen while the visible ticks read Jan 2 · Mar 4 · May 4.
//
// Compressing instead (dropping the 600px minimum and letting the plot shrink
// to the viewport) is not an option: the axis labels are 9px inside an 800-unit
// viewBox, so a 390px render would draw them at ~4px.
//
// So the plot still scrolls — it just rests on `now`, and says that it scrolls.
// Both halves live here as pure arithmetic because the repo's jest environment
// is `node` with no DOM (see `lib/chartZoom.ts` for the same split), so the
// component reads element metrics and these functions decide what they mean.

export interface ScrollMetrics {
  scrollLeft: number;
  scrollWidth: number;
  clientWidth: number;
}

/**
 * A fade is suppressed within this many px of a true edge. Fractional layout
 * widths leave sub-pixel slack at the end of a scroll, which without a
 * tolerance strands a fade that is scrolled hard against its edge and never
 * fully fades out.
 */
export const EDGE_TOLERANCE_PX = 1;

/**
 * The resting scroll offset for a time-series plot: the right edge, i.e. the
 * most recent data. Clamped at 0 so a plot that does not overflow (desktop, or
 * a short domain) stays put rather than being handed a negative offset.
 */
export function anchorScrollLeft(
  metrics: Pick<ScrollMetrics, "scrollWidth" | "clientWidth">,
): number {
  return Math.max(0, metrics.scrollWidth - metrics.clientWidth);
}

/**
 * Which edges still have plot hidden behind them, and therefore which fades to
 * draw. Both false when nothing overflows, so a desktop chart gets no chrome.
 */
export function edgeOverflowFor(metrics: ScrollMetrics): {
  left: boolean;
  right: boolean;
} {
  const maxScroll = anchorScrollLeft(metrics);
  return {
    left: metrics.scrollLeft > EDGE_TOLERANCE_PX,
    right: metrics.scrollLeft < maxScroll - EDGE_TOLERANCE_PX,
  };
}
