/**
 * THE 95% RANGE ON A COUNT (#12102 S2).
 *
 * The exam's scorer prints a Wilson score interval beside every k/n, at
 * z = 1.959963984540054 (the 97.5th percentile of the normal), rounded to six
 * places. The page draws the scorer's own intervals from the committed record;
 * this function exists so a test can hold every one of them to the arithmetic,
 * and the published ones (24/25 → 80.5–99.3%) to the rounding a reader sees.
 * It reuses `/calibration`'s `wilsonCI`, which is the same formula.
 */

import { wilsonCI } from "@/lib/calibrationParity";

export const WILSON_Z = 1.959963984540054;

/** [low, high] as fractions, or null when there is nothing to estimate (n = 0). */
export function wilson95(k: number, n: number): [number, number] | null {
  if (!Number.isInteger(k) || !Number.isInteger(n) || n <= 0 || k < 0 || k > n) return null;
  return wilsonCI(k, n, WILSON_Z);
}

/** "80.5–99.3%": a range the way the receipts print it, to one decimal. */
export function rangeText(range: readonly [number, number]): string {
  return `${(100 * range[0]).toFixed(1)}–${(100 * range[1]).toFixed(1)}%`;
}
