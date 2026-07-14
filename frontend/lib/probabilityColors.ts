/**
 * Probability heat scale — design-system tokens ONLY.
 *
 * The site is light-mode only and CLAUDE.md forbids raw Tailwind palette classes
 * (`text-green-400`, `bg-amber-500/15`, …). ThresholdGrid and ProgressionLadder
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
}

/** Favored (>= 0.6), contested (>= 0.3), else unlikely — token-only. */
export function probabilityHeat(prob: number | null | undefined): ProbabilityHeat {
  const p = prob ?? 0;
  if (p >= 0.6) {
    return { text: "text-accent-brand", bg: "bg-accent-brand/15", bar: "bg-accent-brand" };
  }
  if (p >= 0.3) {
    return { text: "text-accent-warning", bg: "bg-accent-warning/15", bar: "bg-accent-warning" };
  }
  return { text: "text-accent-danger", bg: "bg-accent-danger/15", bar: "bg-accent-danger" };
}

/** Convenience: just the text color class. */
export function probabilityTextClass(prob: number | null | undefined): string {
  return probabilityHeat(prob).text;
}
