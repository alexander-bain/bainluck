import { getEmojiForCategory, getNameForCategory } from "./sportCategories";

export interface CategoryTile {
  key: string;
  name: string;
  emoji: string;
  events: number;
  futures: number;
  total: number;
}

/**
 * Build the `/categories` tile list from the COUNTS PAYLOAD, not from a
 * hardcoded array.
 *
 * The page used to render `SPORT_CATEGORIES` filtered by a second hardcoded
 * allowlist, so a category was browsable only if someone had remembered to add
 * it to that file. Measured against production on 2026-08-30, 21 of the 48
 * categories carrying open markets had no tile at all — 14,873 items, 31.6% of
 * everything on the site, including `table_tennis`, which at 13,503 open
 * markets is the LARGEST category we have. Meanwhile `poker` rendered a tile
 * with nothing behind it.
 *
 * Driving off the payload inverts that: a category is browsable because it has
 * markets, not because it is on a list. Unknown keys still render — the name
 * and emoji helpers fall back to a title-cased key and 🏆 — so a new
 * `llm_sport_category` from the classifier is reachable the day it appears
 * instead of the day someone edits a frontend file.
 *
 * Lives in `lib/` rather than beside the page because a Next.js page module may
 * only export a route's own contract (default, metadata, …); an extra export
 * there is a typecheck error.
 */
export function buildTiles(
  counts: Record<string, { events: number; futures: number }> | undefined,
): CategoryTile[] {
  if (!counts) return [];
  return Object.entries(counts)
    .map(([key, c]) => ({
      key,
      name: getNameForCategory(key),
      emoji: getEmojiForCategory(key),
      events: c.events,
      futures: c.futures,
      total: c.events + c.futures,
    }))
    .filter((t) => t.total > 0)
    // Ordered by size. Ties break on name so the order is stable between
    // renders rather than inheriting object-key order.
    .sort((a, b) => b.total - a.total || a.name.localeCompare(b.name));
}
