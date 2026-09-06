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

/**
 * ── #3538 (ux/1097): THE ALL-OR-NOTHING GATE IS GONE, AND THAT REVERSES A
 *    DELIBERATE #2662 DECISION. Read this before restoring it. ──
 *
 * 🔴 #2662 shipped `outcomeDisplayNames` gated on `names.every(prefixed)`, with the
 * stated reason: *"A market where only some outcomes are prefixed is left alone: a
 * partial strip would make the rows less comparable, not more."* That sentence was
 * reasoned, not measured — #2662's 375-market population was defined by a `HAVING`
 * clause that only admits all-prefixed markets, so the partial case was never in the
 * data it looked at.
 *
 * It is now, and it is the larger half. `/hub/tennis`, production 2026-09-06:
 *
 *     US Open ATP: Karen Khachanov vs Learner Tien
 *       US Open ATP: Karen Khacha…   66%     <- Total Sets: O/U 3.5
 *       US Open ATP: Karen Khacha…   56%     <- Set 1 O/U 9.5
 *       US Open ATP: Karen Khacha…   53%     <- Game Spread +/-2.5
 *       US Open ATP: Karen Khacha…   51%     <- Match O/U 38.5
 *
 * Four prices, four labels a reader cannot tell apart — and the gate is precisely
 * what withheld the fix, because a tenth outcome on that card is named
 * `Karen Khachanov` (the real match-winner leg) and is not prefixed. 31 of 62 outcome
 * rows on that rail restate their own card's headline, and **0 of the affected hub
 * cards are all-prefixed; 4 of 4 are partial.**
 *
 * So the gate is now per-row: strip the rows that carry the parent prefix, leave the
 * rest exactly as served. Measured before changing it, `POST /api/admin/db-query`,
 * 2026-09-06, over every open market resolving in the next 7 days — the markets a
 * reader can currently reach:
 *
 *     all-prefixed  (the #2662 population)   238 markets /  1,348 outcomes
 *     PARTLY prefixed (refused until now)    446 markets /  2,216 outcomes
 *     none prefixed (never touched)        9,265 markets / 27,652 outcomes
 *
 * And over those 446 partial markets, applying the per-row rule:
 *
 *     markets that lose label distinctness    0 of 446
 *     markets with a row that strips to ""   15 of 446   (already covered by `|| name`)
 *
 * Zero. The comparability worry does not appear in the data, and the one hazard that
 * does — a row stripping to nothing — is the hazard #2662 had already built the
 * `|| name` fallback for. That fallback is untouched and is what makes this safe.
 *
 * What #2662 MEASURED is all preserved and still guarded: all-prefixed markets behave
 * exactly as before (every row is prefixed, so a per-row rule strips every row), its
 * two named controls carry zero prefixed outcomes and cannot move, the separator is
 * still leading whitespace only, matching is still case-sensitive, order and length
 * are still one-label-per-input, and no duplicate label is created that the raw names
 * did not already have.
 */

/** Leading whitespace only — measured, not guessed. See the note above. */
const LEADING_SPACE = /^\s+/;

/**
 * Display labels for one market's outcomes, with the parent-name prefix removed
 * from each row that carries it.
 *
 * Applied PER ROW (#3538 — see the block above for the measurement that reversed
 * #2662's all-or-nothing gate). A row that does not begin with the market name is
 * returned byte-identically, so the two controls named on #2662
 * (`Set 1 Winner: Sonmez vs Gauff` with No/Yes outcomes, and `Will Coco Gauff advance
 * to the Round of 16…` with Yes/No) carry no prefixed rows and cannot move — and
 * neither can the real match-winner leg (`Karen Khachanov`) sitting beside nine
 * prefixed siblings on one hub card.
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
  return names.map((n) =>
    typeof n === "string" ? stripParentPrefix(parent, n) : n,
  );
}

/**
 * The rule for a single outcome, and since #3538 the only rule there is —
 * `outcomeDisplayNames` is now this function mapped over a market's rows.
 *
 * It stays exported and separate because the list form still owns two things this
 * one cannot see: the `names.length < 2` no-op (a single-outcome market has nothing
 * to disambiguate) and the empty-parent guard. Call the list form unless you are
 * genuinely labelling one row in isolation.
 */
export function stripParentPrefix(marketName: string, name: string): string {
  if (!marketName || !name.startsWith(marketName)) return name;
  return name.slice(marketName.length).replace(LEADING_SPACE, "").trim() || name;
}
