// #2662: 375 open Polymarket markets name every one of their outcomes with the
// parent market's own full title plus a suffix, so a card that truncates from the
// right prints the same string on every row and cuts away the only text that tells
// the rows apart:
//
//   market   "US Open WTA: Zeynep Sonmez vs Coco Gauff"
//   outcomes "US Open WTA: Zeynep Sonmez vs Coco Gauff Set 1 O/U 8.5"   -> "US Open WTA: Zeynep Sonmez vs Coco Ga…"
//            "US Open WTA: Zeynep Sonmez vs Coco Gauff Set 1 Winner"    -> "US Open WTA: Zeynep Sonmez vs Coco Gau…"
//            "US Open WTA: Zeynep Sonmez vs Coco Gauff Set 2 Winner"    -> "US Open WTA: Zeynep Sonmez vs Coco Gau…"
//            "US Open WTA: Zeynep Sonmez vs Coco Gauff"                 -> "US Open WTA: Zeynep Sonmez vs Coco Gauff"
//
// Four unrelated questions — the match, a games over/under, set 1, set 2 — ranked
// against each other under four labels that read identically.
//
// The data half (four distinct Polymarket condition_ids should be four markets, not
// one market's outcomes) is NOT this file's job and is not fixed here. This is the
// display half: give the reader back the distinguishing text.

/**
 * The measured population, and why the rule is shaped the way it is.
 *
 * `POST /api/admin/db-query`, 2026-09-02, over every open market:
 *
 *   HAVING count(fo.id) >= 2
 *      AND count(fo.id) = sum(CASE WHEN fo.name LIKE fm.name || '%' THEN 1 ELSE 0 END)
 *
 * → 375 markets / 2,325 outcomes, all `source = polymarket`, all `market_tier = 5`.
 *
 * Replaying this function over all 2,325 of those real names decided three things
 * that reading the issue would not have:
 *
 *  1. 354 outcomes — across 353 of the 375 markets — are named *exactly* the market
 *     name, so they strip to the empty string. That is 94% of the population, not an
 *     edge case: without the `|| name` fallback below, nearly every card in scope
 *     would render a blank row, which is worse than the bug.
 *  2. The separator between the parent name and the suffix is a single space (1,971
 *     occurrences) or nothing at all (the 354 above). No colons, no dashes. So the
 *     trim is plain leading whitespace — inventing a separator character class would
 *     be guessing at data that does not exist.
 *  3. The strip introduces **zero** new ambiguity. 64 markets contain outcomes whose
 *     *full* names are already byte-identical duplicates upstream; the count of
 *     duplicate labels per market is unchanged by stripping, on all 375.
 *
 * Effect on the population: 335 of 375 markets go from "every row's visible prefix is
 * identical" to rows a reader can tell apart.
 */

/** Leading whitespace only — measured, not guessed. See the note above. */
const LEADING_SPACE = /^\s+/;

/**
 * Display labels for one market's outcomes, with the shared parent-name prefix
 * removed.
 *
 * Fires only when the whole shipped outcome set is prefixed by the market name —
 * deliberately the same predicate as the population's `HAVING` clause — so every
 * market outside that population is returned byte-identically and the two controls
 * named on #2662 (`Set 1 Winner: Sonmez vs Gauff` with No/Yes outcomes, and
 * `Will Coco Gauff advance to the Round of 16…` with Yes/No) cannot move. A market
 * where only *some* outcomes are prefixed is left alone: a partial strip would make
 * the rows less comparable, not more.
 *
 * An outcome named exactly the market name keeps its full name rather than becoming
 * empty. It is then the only long row on the card, which is enough to tell it from
 * its stripped siblings, and it stays truthful — we do not invent a label like
 * "Match Winner" for a question nobody wrote that way.
 *
 * Both parameters are required. `marketName` has no default on purpose (ux/1010's
 * lesson #3): the absent case is exactly the one a caller must think about, and a
 * silent default would let the next call site re-acquire the bug with every test
 * still green.
 *
 * @param marketName the parent market's name
 * @param names      the outcome names, in render order
 * @returns          one label per input, same length and order
 */
export function outcomeDisplayNames(
  marketName: string | null | undefined,
  names: readonly string[],
): string[] {
  const parent = (marketName ?? "").trim();
  // A one-outcome market has nothing to disambiguate, and an empty parent name
  // would make `startsWith` vacuously true for every string.
  if (!parent || names.length < 2) return [...names];
  if (!names.every((n) => typeof n === "string" && n.startsWith(parent))) {
    return [...names];
  }
  return names.map((n) => n.slice(parent.length).replace(LEADING_SPACE, "").trim() || n);
}

/**
 * The same rule for a single outcome, when the caller already knows the whole set
 * qualifies. Kept separate so the all-or-nothing predicate above stays in one place
 * and cannot be applied per-row by accident.
 */
export function stripParentPrefix(marketName: string, name: string): string {
  if (!marketName || !name.startsWith(marketName)) return name;
  return name.slice(marketName.length).replace(LEADING_SPACE, "").trim() || name;
}
