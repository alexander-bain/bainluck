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
 * How far this plot CAN be scrolled — pure geometry, no editorial. Clamped at 0
 * so a plot that does not overflow (desktop, or a short domain) is never handed
 * a negative offset.
 *
 * #6548 split this out of `anchorScrollLeft`. The two were one function only
 * because the resting anchor happened to BE the maximum offset; `edgeOverflowFor`
 * was already calling the anchor to mean "max scroll". The moment the anchor
 * became conditional, that shared call would have made a settled chart compute
 * its fades against 0 and report no right-hand overflow on a plot that has a
 * screen and a half of it.
 */
export function maxScrollLeft(
  metrics: Pick<ScrollMetrics, "scrollWidth" | "clientWidth">,
): number {
  return Math.max(0, metrics.scrollWidth - metrics.clientWidth);
}

/**
 * The resting scroll offset for a time-series plot.
 *
 * LIVE (#3035): the RIGHT edge — the news on a running race is the newest point,
 * and a reader who opened the US Open title race landed on January.
 *
 * SETTLED (#6548): the LEFT edge. #3035's premise inverts once a question is
 * decided — the right edge is then a flat run to the resolution and the race
 * itself is behind the left edge. Measured on `/futures/110141` (South Dakota
 * GOP governor, resolved 7/28): at 390px the phone rested on Jun 18 → Sep 16,
 * a single blue line already at 100%, while the whole contest — Dusty Johnson
 * leading ~50-70% from Mar 20 and the June crossover that decided it — sat
 * off-screen left. The legend still drew his red key, pointing at no line.
 */
export function anchorScrollLeft(
  metrics: Pick<ScrollMetrics, "scrollWidth" | "clientWidth">,
  opts?: { settled?: boolean },
): number {
  return opts?.settled ? 0 : maxScrollLeft(metrics);
}

/**
 * Which edges still have plot hidden behind them, and therefore which fades to
 * draw. Both false when nothing overflows, so a desktop chart gets no chrome.
 */
export function edgeOverflowFor(metrics: ScrollMetrics): {
  left: boolean;
  right: boolean;
} {
  // `maxScrollLeft`, NOT `anchorScrollLeft` — see the note on the split above.
  const maxScroll = maxScrollLeft(metrics);
  return {
    left: metrics.scrollLeft > EDGE_TOLERANCE_PX,
    right: metrics.scrollLeft < maxScroll - EDGE_TOLERANCE_PX,
  };
}
