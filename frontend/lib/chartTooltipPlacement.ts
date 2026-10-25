/**
 * #10955 (327) — THE HOVER CALLOUT STAYS INSIDE THE CARD IT DESCRIBES.
 *
 * `FuturesChart` used to flip its tooltip by a fixed rule: right of the
 * crosshair in the left 60% of the plot, `translateX(-105%)` past it. That rule
 * knows nothing about how wide the callout is or how much of the plot is on
 * screen, so on a 390px phone a hover at the right edge pushed a five-team
 * callout past the card's LEFT edge — the names were cut off and only the
 * percentages showed (/futures/199045, 2026-10-22). A value whose identity is
 * off-screen is not a value the reader can use.
 *
 * Pure arithmetic in CSS pixels, all in the scroll container's content
 * coordinates (the same space `left` is resolved in):
 *   - beside the crosshair on the right when the whole callout fits there,
 *   - else beside it on the left when that fits,
 *   - else clamped inside the visible window — the callout may then sit over
 *     the crosshair, which is still better than hiding its rows.
 * The crosshair, the observation it names and the plot never move; only the
 * callout does. Its width is capped by `tooltipMaxWidth` so long names wrap
 * instead of being truncated into ambiguity.
 */

/** Space between the crosshair and the callout's near edge. */
export const TOOLTIP_GAP_PX = 8;
/** Space kept between the callout and the visible edge of the card. */
export const TOOLTIP_EDGE_MARGIN_PX = 4;

export interface TooltipView {
  /** Crosshair x in content pixels. */
  anchorX: number;
  /** Rendered callout width in pixels. */
  tooltipWidth: number;
  /** Left edge of the visible window in content pixels (`scrollLeft`). */
  viewLeft: number;
  /** Width of the visible window (`clientWidth`). */
  viewWidth: number;
}

/** The widest the callout may be and still fit the visible window. */
export function tooltipMaxWidth(viewWidth: number): number {
  return Math.max(0, viewWidth - 2 * TOOLTIP_EDGE_MARGIN_PX);
}

/** The callout's `left` in content pixels. */
export function placeChartTooltip({ anchorX, tooltipWidth, viewLeft, viewWidth }: TooltipView): number {
  const minLeft = viewLeft + TOOLTIP_EDGE_MARGIN_PX;
  const maxLeft = viewLeft + viewWidth - TOOLTIP_EDGE_MARGIN_PX - tooltipWidth;
  const right = anchorX + TOOLTIP_GAP_PX;
  if (right <= maxLeft) return Math.max(right, minLeft);
  const left = anchorX - TOOLTIP_GAP_PX - tooltipWidth;
  if (left >= minLeft) return Math.min(left, maxLeft);
  // Fits on neither side: keep every row on screen. A callout wider than the
  // window (cannot happen once `tooltipMaxWidth` applies) pins to the left edge
  // so the names, which lead each row, are the part that stays visible.
  return Math.max(minLeft, Math.min(maxLeft, anchorX - tooltipWidth / 2));
}
