/**
 * Provider grouping for the calibration Source Comparison table.
 *
 * WHY THIS EXISTS (queue 316 item 2, and Fable's addendum to it).
 *
 * The table used to render one row per SOURCE KEY. Three of the five live keys
 * — `odds_api`, `odds_api_spreads`, `odds_api_totals` — are the same provider
 * answering three different question shapes, so a reader scanning the table saw
 * "sportsbooks" three times with three different error figures and no way to
 * tell that they were one data source or that the three numbers were not
 * comparable to each other.
 *
 * The fix is a row per PROVIDER, and the rule that makes it honest is Fable's:
 * **the same aggregation rule applied to every provider, with no bespoke
 * treatment for the Odds API family because it happens to have variants.**
 * `providerOf` is total over source keys — Kalshi and Polymarket are providers
 * with exactly one shape, not special cases exempted from the grouping.
 *
 * WHAT THIS MODULE DELIBERATELY DOES NOT DO — it never fuses two source keys of
 * the SAME shape into one child row. That is the forbidden blend: `odds_api`
 * (event-level) and `odds_api_bookmaker` (per-bookmaker) are both moneyline,
 * and averaging them pairwise would invent a number neither source published.
 * The provider row aggregates by pooling BUCKETS and re-running the page's own
 * metric over them — the identical operation the per-source rows already use —
 * so the parent is a measurement, not a blend of summaries. Children stay
 * one-per-source-key.
 */

/** The provider a source key belongs to. Total: an unknown key is its own provider. */
export function providerOf(source: string): string {
  if (source === "odds_api" || source.startsWith("odds_api_")) return "odds_api_family";
  return source;
}

/** Reader-facing provider names. */
const PROVIDER_DISPLAY_NAMES: Record<string, string> = {
  kalshi: "Kalshi",
  polymarket: "Polymarket",
  odds_api_family: "Sportsbooks (Odds API)",
};

export function providerLabel(provider: string): string {
  return PROVIDER_DISPLAY_NAMES[provider] || provider;
}

/**
 * The per-shape sample floor for showing the shape breakdown INLINE.
 *
 * Stated as a constant rather than inlined because the addendum requires the
 * threshold be declared and applied identically to every provider. Matches the
 * page's small-sample bar so one idea of "too thin to show" governs the page.
 */
export const SHAPE_BREAKDOWN_MIN_N = 1000;

export interface ProviderGroup {
  provider: string;
  label: string;
  /** Source keys in this provider, in the order they arrived. */
  sources: string[];
}

/**
 * Group source keys into providers, preserving first-seen order.
 *
 * Order is preserved rather than sorted so the caller keeps whatever ordering
 * it chose (the table sorts by ECE afterwards); a sort in here would silently
 * override that and be invisible at the call site.
 */
export function groupSourcesByProvider(sources: readonly string[]): ProviderGroup[] {
  const out: ProviderGroup[] = [];
  const byProvider = new Map<string, ProviderGroup>();
  for (const src of sources) {
    const provider = providerOf(src);
    let group = byProvider.get(provider);
    if (!group) {
      group = { provider, label: providerLabel(provider), sources: [] };
      byProvider.set(provider, group);
      out.push(group);
    }
    // A duplicated source key must not double-count into the parent's n.
    if (!group.sources.includes(src)) group.sources.push(src);
  }
  return out;
}

/**
 * Can the shape breakdown be shown INLINE, symmetrically, for every provider?
 *
 * Fable's addendum: it appears "for every source with sufficient per-shape `n`,
 * or for none — if it cannot be shown symmetrically, it moves to an annex
 * rather than appearing for one source and not the others."
 *
 * So this returns true only when EVERY provider has at least two shapes that
 * each clear the floor. One provider with a single shape (Kalshi, Polymarket)
 * is enough to make an inline breakdown asymmetric, which sends the whole
 * breakdown to the annex. That is the intended outcome on today's payload and
 * it is a measurement, not a hard-coded verdict — if per-shape data ever lands
 * for the prediction markets, the breakdown comes inline on its own.
 */
export function shapeBreakdownIsSymmetric(
  groups: readonly ProviderGroup[],
  nBySource: Readonly<Record<string, number>>,
  minN: number = SHAPE_BREAKDOWN_MIN_N
): boolean {
  if (groups.length === 0) return false;
  return groups.every(
    g => g.sources.filter(s => (nBySource[s] ?? 0) >= minN).length >= 2
  );
}
