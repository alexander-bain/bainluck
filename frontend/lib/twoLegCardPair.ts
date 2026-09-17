import { isComplementPair } from "@/lib/renderedPercent";

/**
 * THE TWO NUMBERS A DASHBOARD CARD MAY PRINT FOR A TWO-LEG MARKET — #6766.
 *
 * ═══ WHAT A READER SAW, production 2026-09-17 at 390px ═══
 *
 * `/politics`, "John Thune announces departure as Senate Majority Leader?":
 *
 *     3%  Before Nov 3, 2026            vs  98%  Before Oct 1, 2026
 *
 * The payload prices `Before Oct 1, 2026` at **1.0%**. The card drew a nearly
 * full grey bar under it, so the one thing a reader took from that card — Thune
 * is almost certainly gone by October — was the opposite of what the market says.
 *
 * Three more on the same pass (probe: `tools/dashboard-two-leg-cards-6766.mjs`,
 * 19 two-leg cards measured across the two dashboards, **4 disagreeing**):
 *
 * | surface | card | printed | served |
 * |---|---|---|---|
 * | /politics | Thune departure | 98% Before Oct 1 | **1.0%** |
 * | /politics | South Dakota AG | 6% Democratic party | **4.2%** |
 * | /politics | New York AG | 7% Saritha Komatireddy (R) | **4.8%** |
 * | /entertainment | MrBeast week-1 views | NO 94% | `100M+` **5.1%** |
 *
 * ═══ THE DEFECT: A DERIVED NUMBER UNDER A SERVED NAME ═══
 *
 * `BinaryCard` computed the second number as `100 - prob` and then labelled it
 * with `top_outcomes[1].name`. For a Yes/No contract that is exactly right — the
 * No side IS one minus the Yes side, and no venue quotes it separately. For a
 * market with two real legs it is a fabrication wearing a real leg's name, and
 * the two legs of a RUNG market are not complements: `Before Nov 3` (2.5%) and
 * `Before Oct 1` (1.0%) are nested, not opposite, and they sum to 3.5.
 *
 * ═══ THE RULE ═══
 *
 * 1. **A served second leg is READ, never derived.** The payload already carries
 *    the price the venue quotes for the name the card is about to print.
 * 2. **The complement is licensed by ARITY, not by arithmetic.** It survives
 *    exactly where it is true by construction — `outcome_count === 1`, the Kalshi
 *    binary whose No side is implicit (33 of 68 politics rows, 19 of 107
 *    entertainment rows, measured 2026-09-17). A market with two or more outcomes
 *    that served us only ONE price is the #6255 population — an unpriced rung —
 *    and there the honest second number is NO second number, so `second` is null.
 *    That arm draws 0 cards today and is asserted anyway, because the arm that
 *    invents a price is the one this file exists to close.
 * 3. **`oneQuestion` governs PRESENTATION only.** `isComplementPair`'s [0.99,
 *    1.01] band is this repo's existing measured definition of "these two are two
 *    halves of one question" (`renderedPercent.ts`, and `drawPricedWinner`'s
 *    `awayIsTheComplement` reuses it for the same judgement on a match surface).
 *    Only a pair inside it may be drawn as two ends of one full bar or labelled
 *    YES/NO. Outside it the card falls back to the list render both pages already
 *    have for independent rungs — no new markup, and no layout inventing a
 *    partition that the prices deny.
 *
 * ═══ WHY THIS IS A LIB AND NOT THREE EDITS ═══
 *
 * The three call sites — `app/politics/page.tsx`'s `MarketCard`/`BinaryCard` and
 * `app/entertainment/page.tsx`'s two `YesNoBar` sites — each spelled the
 * derivation out longhand, which is how one of them can be repaired and its
 * neighbours left printing the same lie (the exact split `renderedDuelPercents`
 * documents, and #6082's "it was a second copy, and this is where it had
 * diverged"). The rule lives once, beside the argument for it.
 *
 * `/economics` and `/weather` were scanned for the same expression and have none:
 * the class is these three sites.
 */

/** One served leg of a market: the name a card prints and the price beside it, on the 0–100 axis. */
export interface CardLeg {
  name: string;
  prob: number;
}

export interface TwoLegCardPair {
  /** The headline leg. Its price is the SERVED one, never re-derived. */
  first: CardLeg;
  /** The second leg, or null where this surface may not state a second number. */
  second: CardLeg | null;
  /** May these two be drawn as two halves of one question — one full bar, YES/NO labels? */
  oneQuestion: boolean;
}

/** The shape both dashboard serializers give a card. */
export interface TwoLegCardRow {
  prob: number;
  outcome_count: number;
  top_outcomes?: readonly CardLeg[] | null;
}

export function twoLegCardPair(
  row: TwoLegCardRow,
  names: { first: string; second: string } = { first: "Yes", second: "No" },
): TwoLegCardPair {
  const legs = row.top_outcomes ?? [];
  // `politics._market_row` sets `prob` to `top_outcomes[0]["prob"]` and the
  // entertainment serializer does the same — measured equal on all 175 served
  // rows — so the fallback is a shape guarantee, not a second source of truth.
  const first: CardLeg = legs[0] ?? { name: names.first, prob: row.prob };

  const served = legs[1];
  if (served) {
    return {
      first,
      second: served,
      oneQuestion: isComplementPair([first.prob / 100, served.prob / 100]),
    };
  }

  if (row.outcome_count <= 1) {
    return {
      first,
      second: { name: names.second, prob: 100 - first.prob },
      oneQuestion: true,
    };
  }

  return { first, second: null, oneQuestion: false };
}
