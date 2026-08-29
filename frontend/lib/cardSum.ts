// What a card says when its two numbers do not add up to 100 (#2088).
//
// ── WHY THERE IS COPY HERE AT ALL ────────────────────────────────────────────
//
// #2060 fixed the two-outcome card that SHOULD total 100: a complement pair is
// normalized, rounded once and derived, so `93 / 8` became `93 / 7`. It
// deliberately left alone the pair that should not total 100, and it was right
// to — normalizing a pair summing to 0.97 would invent three points of
// probability rather than round one.
//
// But that left a card reading `57 / 40` on screen with nothing saying why, and
// INT-104 filed #2088 for exactly that: the reader cannot tell "these are two
// real numbers that genuinely do not add up" from "our renderer is buggy
// again". The two look identical, and one of them is a bug we had just fixed.
// An UNEXPLAINED non-100 is the defect; a labelled one is a fact.
//
// The reason itself is decided once, on the server (`graded_card.card_sum_reason`)
// and driven through `contracts/rendered_percent.json`. This file is only the
// sentence — the same split as `lib/liquidity.ts`, where the grade is a rule and
// the words are a surface concern.
//
// ── THE WORDS, AND WHAT THEY ARE NOT ALLOWED TO BE ───────────────────────────
//
// Ruling 138 bans the whole `price` stem from reader copy — the word is
// PROBABILITY — so nothing here may say "priced", "unpriced" or "prices". The
// machine-readable reasons DO carry that stem (`independent_prices`,
// `unpriced_outcome`) and that is fine: they are payload enums, never rendered,
// and the bundle scanner's own pattern requires a word boundary that
// `independent_prices` and `unpriced_outcome` do not have (the neighbouring
// character is `_`, which is a word character). Asserted in the test beside this
// file rather than left as an argument.
//
// Ruling 141 is not in play — no venue is named. The register is deliberately
// the plain one Alex already has in front of him from the illiquidity mark
// ("nobody has traded it in the last day"), not a second vocabulary.

import { SUM_INDEPENDENT_PRICES, SUM_UNPRICED_OUTCOME } from "./renderedPercent";

export type CardSumReason =
  | typeof SUM_INDEPENDENT_PRICES
  | typeof SUM_UNPRICED_OUTCOME;

/**
 * The sentence a card carries when its numbers do not total 100.
 *
 * One per reason and no default: a reason with no sentence must fail to compile
 * rather than render an empty explanation, which would be worse than the
 * unexplained card this exists to replace.
 */
export const CARD_SUM_EXPLANATION: Record<CardSumReason, string> = {
  [SUM_INDEPENDENT_PRICES]:
    "These two sides are quoted separately, so they do not add up to 100.",
  [SUM_UNPRICED_OUTCOME]: "One side has no number, so there is nothing to add up.",
};

/**
 * A served `card_sum_reason` → the sentence, or null.
 *
 * Null for an absent, unknown or malformed reason, and that is the deliberate
 * direction: a value this build does not recognise must draw NOTHING rather
 * than a guess. The card is already readable without the line; inventing an
 * explanation for a reason we cannot name would be the same class of error the
 * line exists to remove.
 */
export function cardSumExplanation(reason: unknown): string | null {
  if (typeof reason !== "string") return null;
  if (reason === SUM_INDEPENDENT_PRICES || reason === SUM_UNPRICED_OUTCOME) {
    return CARD_SUM_EXPLANATION[reason];
  }
  return null;
}
