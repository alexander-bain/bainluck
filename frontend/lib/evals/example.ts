/**
 * The worked example in "Where the numbers come from" (#12102): one view,
 * written the way a betting site writes it and the way a prediction market
 * writes it (a share's cost in cents), and the single probability Bain Luck shows for both.
 *
 * Illustrative, not measured: no market's reading. So it renders inside an
 * `Example`, labelled "For example", where no `Figure` may render and the
 * truth scan skips the digits. The arithmetic is real, and
 * `__tests__/example.test.ts` holds both sources to the same probability.
 */

/** American odds as a betting site writes them: −150 means stake 150 to win 100. */
export const EXAMPLE_AMERICAN_ODDS = -150;

/** A prediction-market share that pays a dollar if it happens, at this many cents. */
export const EXAMPLE_CONTRACT_CENTS = 60;

/** American odds to the chance they imply, in percent: −150 → 60, +150 → 40. */
export function americanToPercent(odds: number): number {
  if (!Number.isFinite(odds) || Math.abs(odds) < 100) throw new Error(`not American odds: ${odds}`);
  return odds < 0 ? (100 * -odds) / (-odds + 100) : (100 * 100) / (odds + 100);
}

/** American odds the way a reader sees them, with a true minus sign: "−150", "+150". */
export function americanOddsText(odds: number): string {
  return `${odds < 0 ? "−" : "+"}${Math.abs(odds)}`;
}
