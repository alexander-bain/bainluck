// #7848 — THE WIN-PROBABILITY TOOLTIP RAN OFF THE BOTTOM OF THE PHONE SCREEN.
//
// Sibling of #1833, on the other axis, and NOT the same defect: #1833 was the card
// being too WIDE for the space left of the plot's y-axis inset, and narrowing the
// card fixed it. This one survives any width: the card is simply TALLER than the
// chart it annotates, and recharts pins it to the chart.
//
// `recharts/util/tooltip/translate.js`, with the default `allowEscapeViewBox.y =
// false` and `reverseDirection.y = false`:
//
//     positive        = coordinate.y + offset
//     tooltipBoundary = positive + tooltipHeight
//     viewBoxBoundary = viewBox.y + viewBox.height
//     if (tooltipBoundary > viewBoxBoundary) return Math.max(negative, viewBox.y)
//
// For a 444px card in a ~300px plot the first branch is ALWAYS taken, and
// `negative` (coordinate.y − height − offset) is always negative, so the card is
// pinned at `viewBox.y` — the top of the plot — at every cursor position. That is
// why the measured card top is a CONSTANT (~447px on /events/14780544 at 390px)
// while the card's own height varies 303 → 477px, and why the bottom edge lands at
// 891 and 923 on an 844px screen.
//
// So the clamp is doing its job — it is just clamping to the wrong box. The chart's
// viewBox is not what the reader can see. This computes the correction against the
// VIEWPORT instead, and the card carries it as its own `translateY`.
//
// ── WHY THE APPLIED SHIFT IS AN INPUT ────────────────────────────────────────
//
// The only geometry available at runtime is `getBoundingClientRect()`, which
// reports the card WHERE IT CURRENTLY IS — i.e. with any shift already folded in.
// Computing a correction from that without adding the shift back would re-correct
// an already-corrected card on every measurement and walk it off the top of the
// screen. Adding it back recovers the natural (unshifted) box, which makes this
// function IDEMPOTENT: feeding it the rect produced by its own answer returns that
// same answer, so the layout effect that drives it settles after one pass instead
// of oscillating. `idempotence` in the guard is that property, asserted on the
// real production specimens.
//
// ── WHAT IT DELIBERATELY DOES NOT DO ─────────────────────────────────────────
//
// It never shifts a card so far up that the card's TOP leaves the screen: the
// answer is capped at the available headroom. A card taller than the viewport
// therefore still overflows at the bottom — by as little as possible, with its top
// edge on the margin. That is the honest degradation, because the top of this card
// is the score, the period and the blend, and the tail is the per-source rows: if
// something has to be off-screen it should be the tail. No `max-height` and no
// internal scrolling — the card is `pointer-events: none` and follows the cursor,
// so a scrollbar would turn rows that are visibly cut off into rows that are
// silently unreachable.
//
// It returns 0 whenever the card already fits, so every surface that was not
// broken is byte-identical: the fullscreen modal (measured 0 of 5 positions
// clipped at both 390px and 375px, same card and same content) and every desktop
// width go through this function and come out unmoved.
//
// ── THE VIEWPORT IS NOT THE READABLE AREA ────────────────────────────────────
//
// The first cut of this bounded the card at `window.innerHeight` and the probe
// agreed it was clean — and the screenshot showed the ESPN row still missing. The
// mobile `BottomNav` is `fixed bottom-0 z-50`, 57px tall, painted OVER the page:
// a card ending at y=836 on an 844px screen has its last 49px behind it. Both the
// rule and the probe were measuring against a boundary the reader does not have.
// So the bound is the top of that bar when it is on screen, and the viewport
// bottom when it is not. It is passed in rather than queried here so this stays a
// pure function — the DOM read lives at the one call site.



/** Gap left between the tooltip card and the edge of the readable area, in px. */
export const CHART_TOOLTIP_VIEWPORT_MARGIN_PX = 8;

/**
 * Marks an element that is painted OVER the page against the bottom of the
 * screen, so the bottom of the viewport is not the bottom of what a reader can
 * see. Carried by the mobile `BottomNav`; see `bottomObstructionTop`.
 */
export const VIEWPORT_BOTTOM_OBSTRUCTION_ATTR = "data-viewport-bottom-obstruction";

export interface ChartTooltipViewportFitInput {
  /** `getBoundingClientRect().top` of the card AS CURRENTLY PAINTED. */
  rectTop: number;
  /** `getBoundingClientRect().bottom` of the card AS CURRENTLY PAINTED. */
  rectBottom: number;
  /** The upward shift already applied to the card, in px (0 when unshifted). */
  appliedShift: number;
  /** `window.innerHeight`. */
  viewportHeight: number;
  /**
   * Viewport y of the top of whatever is painted over the bottom of the screen —
   * the mobile nav bar. `null` when nothing is (desktop, where it is
   * `display:none`). THE VIEWPORT IS NOT THE READABLE AREA: on a phone the last
   * 57px of it are behind a `z-50` nav, and a card that stops at the viewport's
   * bottom edge still has its final rows hidden.
   */
  bottomObstructionTop?: number | null;
  margin?: number;
}

/**
 * How far UP the tooltip card must move (px, always >= 0) to sit inside the
 * readable area. 0 means "already fits — do not move it".
 */
export function chartTooltipViewportShift({
  rectTop,
  rectBottom,
  appliedShift,
  viewportHeight,
  bottomObstructionTop = null,
  margin = CHART_TOOLTIP_VIEWPORT_MARGIN_PX,
}: ChartTooltipViewportFitInput): number {
  // Recover the box recharts actually placed, before our own correction.
  const naturalTop = rectTop + appliedShift;
  const naturalBottom = rectBottom + appliedShift;

  // A hidden obstruction reports a zero-height rect at the origin, so only a
  // positive top counts — otherwise desktop would clamp everything to y=0.
  const readableBottom =
    bottomObstructionTop != null && bottomObstructionTop > 0
      ? Math.min(viewportHeight, bottomObstructionTop)
      : viewportHeight;

  const overflowBelow = naturalBottom - (readableBottom - margin);
  if (!(overflowBelow > 0)) return 0; // fits (and NaN-safe)

  // Never trade a clipped bottom for a clipped top.
  const headroomAbove = naturalTop - margin;
  if (!(headroomAbove > 0)) return 0;

  return Math.min(overflowBelow, headroomAbove);
}
