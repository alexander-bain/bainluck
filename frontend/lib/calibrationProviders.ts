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

// ---------------------------------------------------------------------------
// NAMING A SOURCE — CAL-P1024 (#1865, the SOURCE half of its raw-payload-key item)
//
// Measured on production 2026-09-05: `datagolf` reached the reader RAW in two
// places in the default view — the last Source Comparison row, where every
// sibling is a proper name, and the By Source sentence, which opened on a
// lowercase database identifier ("datagolf has no outcomes in this cohort...").
//
// It is a SCHEDULED defect, not a typo. `/api/calibration` publishes seven
// source keys today; the frozen fixture `fixtures/calibration/prod-2026-08-02
// .json` carries five. The vocabulary is data-driven — there is no source-key
// constant in the backend to hold this file against — so the map falls behind
// upstream growth and nothing notices until a reader does.
//
// The remedy is not a judgement call: #1865 already settled it for CATEGORIES,
// where `table_tennis` reached the reader for the identical reason, and
// `calibrationCategories.ts:14-27` records the ruling. Both halves, always —
// the curated entry because a brand is an opinion and a generated name is a
// fabrication ("DataGolf", never "Datagolf"), and the prettified fallback
// because one label is not a class.
// ---------------------------------------------------------------------------

/**
 * Tokens inside a SOURCE key that are shouted rather than spelled.
 *
 * Deliberately its own set rather than `calibrationCategories`' — that one is
 * derived from `LEAGUE_DISPLAY`, so a source key colliding with a league key
 * would come back named after the league. Two key spaces, two sets.
 */
const SOURCE_ACRONYMS: ReadonlySet<string> = new Set([
  "ai", "api", "espn", "mlb", "nba", "nfl", "nhl", "pga", "ufc", "wta",
]);

/**
 * A source or provider key we hold no curated name for, made readable.
 *
 * **Never returns a raw payload key**: the result carries no underscore and
 * never leads lowercase, so the raw-key state this function exists to close is
 * unreachable for any input, not just the one that exposed it. An imperfect
 * generated name ("Datagolf") is only ever the state of a source nobody has
 * named yet — every source we have an opinion about is in the map above it.
 */
export function prettifySourceKey(raw: string): string {
  const tokens = raw.split(/[_\s]+/).filter(Boolean);
  if (!tokens.length) return raw;
  return tokens
    .map((t) => {
      const lower = t.toLowerCase();
      return SOURCE_ACRONYMS.has(lower)
        ? lower.toUpperCase()
        : lower.charAt(0).toUpperCase() + lower.slice(1);
    })
    .join(" ");
}

/** Reader-facing provider names. */
const PROVIDER_DISPLAY_NAMES: Record<string, string> = {
  kalshi: "Kalshi",
  polymarket: "Polymarket",
  odds_api_family: "Sportsbooks (Odds API)",
  datagolf: "DataGolf",
};

export function providerLabel(provider: string): string {
  return PROVIDER_DISPLAY_NAMES[provider] || prettifySourceKey(provider);
}

/**
 * Reader-facing names for individual SOURCE keys.
 *
 * Kept separate from `PROVIDER_DISPLAY_NAMES` rather than folded into it,
 * because the two genuinely disagree and the disagreement is deliberate:
 * `odds_api` is "Odds API" as a source, while the family it belongs to is
 * "Sportsbooks (Odds API)" as a provider. Only the FALLBACK is shared.
 *
 * Moved here from `app/calibration/page.tsx` by CAL-P1024 under ruling 005
 * (extract-on-touch), for the reason `calibrationCategories.ts` records for its
 * own extraction: the page is a `"use client"` component behind SWR, so no
 * guard could call this function — which is why nothing had ever asserted
 * anything about it, and why `datagolf` sat unnamed since UX-P128.
 */
const SOURCE_DISPLAY_NAMES: Record<string, string> = {
  kalshi: "Kalshi",
  polymarket: "Polymarket",
  odds_api: "Odds API",
  odds_api_spreads: "Spreads (Odds API)",
  odds_api_totals: "Totals (Odds API)",
  odds_api_bookmaker: "Per-Bookmaker (Odds API)",
  datagolf: "DataGolf",
};

/** A source key's human label. **Never returns a raw payload key.** */
export function sourceLabel(src: string): string {
  return SOURCE_DISPLAY_NAMES[src] || prettifySourceKey(src);
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
