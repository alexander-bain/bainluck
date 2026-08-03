/**
 * L2-243 Item 1 — the DISPLAY title for a client-synthesized Discover group.
 *
 * `groupRelatedMarkets` (app/discover/page.tsx) groups futures by a key derived
 * from the market name: the text before a ":" (a real shared subject, e.g.
 * "Valero Texas Open"), or — when there is no colon — the first three words.
 * The first-three-words fallback is fine as a grouping KEY but is a broken
 * DISPLAY label: it renders a truncated question fragment ("Will the U.S.") in a
 * category-styled pill, which reads like a clipped category chip.
 *
 * This helper decides only what the pill SHOWS. A meaningful colon-derived
 * subject is kept verbatim; a question fragment is replaced by the group's
 * category (e.g. "culture"), which is what the colored/emoji pill already
 * represents. It never invents a claim and never changes grouping.
 */

/**
 * @param name the market name the group was keyed on
 * @param category the group primary's `llm_sport_category` (may be null)
 * @returns the pill display title: a real colon subject, else the category, else a neutral label
 */
export function deriveGroupDisplayTitle(
  name: string,
  category: string | null | undefined
): string {
  const trimmed = (name || "").trim();
  const colonIdx = trimmed.indexOf(":");
  // A colon-derived prefix is a genuine shared subject ("Valero Texas Open",
  // "DDR5 16GB (2GX8)") — keep it.
  if (colonIdx > 0 && colonIdx < 30) {
    const prefix = trimmed.slice(0, colonIdx).trim();
    if (prefix) return prefix;
  }
  // No colon: the grouping key was a first-3-words question fragment. Show the
  // category the pill already color-codes instead of a meaningless fragment.
  const cat = (category || "").trim();
  if (cat) return cat;
  // Category unknown too — a neutral, honest label (never a fabricated subject).
  return "Related markets";
}
