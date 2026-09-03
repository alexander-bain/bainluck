/**
 * The win-probability sources an event page's chart footer names (ux/1034 B7).
 *
 * ═══ WHY THIS IS A MODULE ═══
 *
 * Alex asked for B7 to be VERIFIED, not built: *"the legend must pick
 * [Polymarket] up without a deploy."* It could not. What the footer had was
 *
 *     Object.keys(win_prob_sources).some(k => k contains 'kalshi')
 *       -> a hard-coded <span>Kalshi</span>, in violet
 *
 * — one venue, present or absent, with no branch for a second source at all.
 * No attachment could ever reach that strip. Measured on `/events/15293830` at
 * 2026-09-03T02:00Z: Polymarket had been attached since 20:26Z the previous
 * evening (145 points in `win_prob_history`, a full `win_prob_sources` entry),
 * the chart above was drawing its line, and the strip still read
 * `BainLuck · Sportsbooks · Kalshi`.
 *
 * It lives here rather than in the route file for the ordinary reason — a
 * Next.js page may not carry named exports, and a rule with no seam is a rule
 * that gets asserted through a screenshot.
 *
 * ═══ THE TWO RULES ═══
 *
 * 1. **A source is listed because the payload has it**, never because somebody
 *    wrote its name in a component. `win_prob_sources` is the server's list;
 *    `win_prob_history` is what it drew from. A key with an empty series is
 *    dropped — a legend entry for a line that is not on the chart is the same
 *    lie as a missing one, facing the other way.
 *
 * 2. **Colour and name come from `SOURCE_COLORS`**, the registry the chart's
 *    own legend reads. "Same source, same colour, everywhere" is L2-155's
 *    whole point, and two components resolving one supplier independently is
 *    exactly how Kalshi came to be `#22c55e` on the plot and violet six pixels
 *    underneath it.
 */

import { canonicalSourceKey, getSourceColor, sourceLabel } from "./sourceColors";

export interface ChartSourceChip {
  /** The payload's own key, e.g. `kalshi`. Also the React key. */
  key: string;
  label: string;
  /** Canonical hex from `SOURCE_COLORS`. */
  color: string;
}

/**
 * The sportsbook aggregate, which the footer already draws its own chip for.
 *
 * Excluded through `canonicalSourceKey` rather than by string, so the alias
 * `betting` — which is what the win-prob payload actually calls it — is caught
 * as well as the spelling somebody happened to remember.
 */
const SPORTSBOOK_KEY = "odds_api";

export function chartSourceChips(
  sources: Record<string, { display_name?: string | null } | null | undefined> | null | undefined,
  series: Record<string, unknown[] | null | undefined> | null | undefined
): ChartSourceChip[] {
  const drawn = series ?? {};
  return Object.keys(sources ?? {})
    .filter((key) => (drawn[key]?.length ?? 0) > 0)
    .filter((key) => canonicalSourceKey(key) !== SPORTSBOOK_KEY)
    .map((key) => ({
      key,
      label: sourceLabel(key, sources?.[key]?.display_name),
      color: getSourceColor(key).hex,
    }));
}
