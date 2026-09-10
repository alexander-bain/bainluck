/**
 * Probability heat scale — design-system tokens ONLY.
 *
 * The site is light-mode only and CLAUDE.md forbids raw Tailwind palette classes
 * (`text-green-400`, `bg-amber-500/15`, …). ThresholdGrid (deleted UX-P075,
 * gotcha #133) and ProgressionLadder
 * historically hand-rolled 4-band heat gradients in raw palette (a dark-mode
 * artifact that renders nearly invisible in light mode). This is the single
 * source of truth that replaces them, expressed purely on the accent tokens
 * (`accent-brand`/`accent-warning`/`accent-danger`) exposed in tailwind.config.
 *
 * Three semantic bands (favored → contested → unlikely) map cleanly onto the
 * three available accent tokens — there is no `orange` token, so the old
 * green/amber/orange/red four-band split collapses to a fully-tokenized three.
 * The #194 Quantity kernel for Discover cards reuses these helpers so the whole
 * card system inherits one clean, light-mode-correct heat scale.
 */

export interface ProbabilityHeat {
  /** Text color class for the probability number. */
  text: string;
  /** Tinted background class (12–15% opacity) for a card/pill. */
  bg: string;
  /** Solid fill class for a mini progress bar. */
  bar: string;
  /**
   * False when there is no probability to be hot or cold about.
   *
   * #4660. A caller that draws a FILL reads this and draws none — a heat class
   * on a zero-width element is harmless, but a heat class on a floored one is
   * the bug. Callers that only tint text can ignore it and take `text`.
   */
  known: boolean;
}

/**
 * Favored (>= 0.6), contested (>= 0.3), else unlikely — token-only.
 *
 * ═══ WHY `null` IS A FOURTH BAND AND NOT A ZERO (#4660) ═══
 *
 * This function used to open with `const p = prob ?? 0`, which sorted an ABSENT
 * probability into the same band as a probability we had measured at zero. The
 * two are different facts — "nobody has priced this" versus "this will almost
 * certainly not happen" — and the danger band asserts the second one.
 *
 * Measured on production 2026-09-09: the Discover card "Netflix App Downloads
 * in September" drew rungs "Above 76" and "Above 82" with `—` in the number
 * cell and a short RED bar beside it, because `QuantityGroup` floored the width
 * at 2% so the danger fill was actually painted. The number said *we don't
 * know* and the bar said *almost impossible*, and the bar is what the eye reads
 * down a ladder.
 *
 * So the scale has four states, and `probabilityHeat(null)` and
 * `probabilityHeat(0)` must never again be the same object. The unknown band is
 * deliberately built from `text-muted`/`surface` tokens rather than a fourth
 * accent: it is the absence of a claim, and an accent of any colour is a claim.
 */
export function probabilityHeat(prob: number | null | undefined): ProbabilityHeat {
  // Not `?? 0`. `NaN` is caught here too: it is not a probability, and every
  // comparison below would be false, so it would otherwise fall through to the
  // danger band exactly the way `null` did.
  if (prob == null || !Number.isFinite(prob)) {
    return {
      text: "text-text-muted",
      bg: "bg-surface-elevated",
      bar: "bg-surface-border",
      known: false,
    };
  }
  if (prob >= 0.6) {
    return { text: "text-accent-brand", bg: "bg-accent-brand/15", bar: "bg-accent-brand", known: true };
  }
  if (prob >= 0.3) {
    return { text: "text-accent-warning", bg: "bg-accent-warning/15", bar: "bg-accent-warning", known: true };
  }
  return { text: "text-accent-danger", bg: "bg-accent-danger/15", bar: "bg-accent-danger", known: true };
}

/** Convenience: just the text color class. */
export function probabilityTextClass(prob: number | null | undefined): string {
  return probabilityHeat(prob).text;
}
