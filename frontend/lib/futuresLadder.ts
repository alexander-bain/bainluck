/**
 * futuresLadder — turn a `quantity` market's OWN outcomes into ladder rungs.
 *
 * Queue lane1-Q478 (TOP-PRODUCT-DEFECTS item 10). `QuantityGroup` already existed
 * and the detail page already imported it, but the only thing that could ever feed
 * it was the backend's `threshold_groups` payload — and `extract_threshold()` is
 * purely NUMERIC. A market whose rungs are dates ("Before April", "Before July",
 * "Before October", "Before 2027" — market 109349, "When will Apple release the
 * iPhone 18?") produces `threshold_groups == {}`, so the ladder never rendered and
 * the page fell through to the generic ranked table: rank badges 1-4 and avatar
 * circles reading "BA", "BJ", "BO", "B2".
 *
 * This builder needs no threshold parser at all. It reads the shape field
 * (`market_type`, #194) for WHETHER to draw a ladder, and two facts the payload
 * already carries for HOW to order it. Deliberately no new regex layer: re-deriving
 * shape from outcome names is the very defect this queue closes.
 */

import type { QuantityRung } from "@/components/QuantityGroup";

/** The minimum an outcome must carry to become a rung. */
export interface LadderOutcome {
  id: number;
  name: string;
  probability: number | null;
}

/**
 * Ordering for a quantity ladder, decided from fields the payload already has.
 *
 * A quantity market comes in two sub-kinds and they order differently:
 *
 *   - **Cumulative** ("Before July" ⊂ "Before October"; "≥ 80" ⊂ "≥ 60"). The rungs
 *     nest, so they are NOT mutually exclusive and their probabilities are monotone
 *     non-decreasing along the ladder *by construction*. Ascending probability IS
 *     the ladder order — nothing is inferred from the text.
 *   - **Disjoint bins** ("0-10", "10-20"). These ARE mutually exclusive and their
 *     probabilities carry no ordering information at all, so sorting by probability
 *     would scramble a timeline. Serve order is preserved instead.
 *
 * `mutually_exclusive` is an existing column on `FuturesMarket`, already on the
 * detail payload, and it is exactly the cumulative/disjoint distinction. Using it
 * beats guessing from names.
 */
export type LadderOrder = "cumulative" | "served";

export function ladderOrderFor(mutuallyExclusive: boolean | null | undefined): LadderOrder {
  // Default (null/undefined) is the conservative one: don't reorder what we were given.
  return mutuallyExclusive === false ? "cumulative" : "served";
}

/**
 * Build ladder rungs from a market's own outcomes.
 *
 * Labels are the outcome names verbatim — a date rung has no numeric value to
 * format, and inventing "≥ N" text for it would be a lie. `QuantityGroup`'s
 * `wideLabels` mode exists for exactly this ("the 'by WHEN' variant of the
 * kernel"), so the caller pairs the two.
 *
 * The returned rungs always carry an explicit `value` giving their final position,
 * so the caller can leave `QuantityGroup`'s own `sort` on without it re-deciding
 * the order: rung `value` is the index, ascending.
 */
export function buildOutcomeLadderRungs(
  outcomes: readonly LadderOutcome[],
  order: LadderOrder,
): QuantityRung[] {
  const rows = [...outcomes];

  if (order === "cumulative") {
    // Ascending probability, and TIES KEEP SERVE ORDER. `Array.prototype.sort` is
    // stable (ES2019), so returning 0 is the whole tiebreak: we reorder only where
    // the prices give us a reason to, and otherwise leave the source's own order
    // alone.
    //
    // This is measured, not stylistic. Market 109349 prices "Before April" and
    // "Before July" identically at 1%, and its outcome IDS run 1596640 = July,
    // 1596641 = April — so tiebreaking on id (insertion order) renders **July
    // above April**, a backwards timeline on the exact market this queue is about.
    // Serve order has April first and is right. Insertion order is not a fact
    // about the ladder; the source's ordering at least claims to be.
    rows.sort((a, b) => {
      const ap = a.probability ?? Number.POSITIVE_INFINITY;
      const bp = b.probability ?? Number.POSITIVE_INFINITY;
      return ap === bp ? 0 : ap - bp;
    });
  }

  return rows.map((o, i) => ({
    key: o.id,
    label: o.name,
    probability: o.probability,
    value: i,
  }));
}

/**
 * True when a rung set wants the roomy label track — any label that is not a short
 * numeric threshold. Dates ("Before October", "2029 or later") need it; "≥ 80"
 * does not.
 */
export function ladderNeedsWideLabels(rungs: readonly QuantityRung[]): boolean {
  return rungs.some((r) => r.label.trim().length > 8);
}
