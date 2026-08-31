/**
 * Market *shape* — the frontend mirror of `backend/app/utils/market_shape.py`.
 *
 * Queue L2-118 Phase 1. The backend classifier (Queue #194) assigns one of six
 * shapes to every futures market and stores it on `FuturesMarket.market_type`.
 * Every surface — Discover cards, detail pages, concept pages — keys off that
 * ONE field so the card system and the page system stay in lockstep
 * (strategy_event_page_primitives.md: "kernel × state × angle").
 *
 * A shape maps to a render KERNEL (the compact primitive the surface draws):
 *   claim            → number+delta      (big number + movement)
 *   quantity         → ladder-strip      (QuantityGroup — one question, many lines)
 *   duel             → split             (two-sided)
 *   field            → top-3             (ranked leaderboard)
 *   container_member → headliner+count   (rolls up into a container)
 *   unshaped         → (no native kernel)
 *
 * Keep this vocabulary byte-identical to market_shape.py's ALL_SHAPES /
 * SHAPE_TO_KERNEL so the two never drift.
 */

export const SHAPE_CLAIM = "claim";
export const SHAPE_QUANTITY = "quantity";
export const SHAPE_DUEL = "duel";
export const SHAPE_FIELD = "field";
export const SHAPE_CONTAINER_MEMBER = "container_member";
export const SHAPE_UNSHAPED = "unshaped";

export type MarketShape =
  | typeof SHAPE_CLAIM
  | typeof SHAPE_QUANTITY
  | typeof SHAPE_DUEL
  | typeof SHAPE_FIELD
  | typeof SHAPE_CONTAINER_MEMBER
  | typeof SHAPE_UNSHAPED;

export type MarketKernel =
  | "number+delta"
  | "ladder-strip"
  | "split"
  | "top-3"
  | "headliner+count"
  | null;

const ALL_SHAPES: ReadonlySet<string> = new Set([
  SHAPE_CLAIM,
  SHAPE_QUANTITY,
  SHAPE_DUEL,
  SHAPE_FIELD,
  SHAPE_CONTAINER_MEMBER,
  SHAPE_UNSHAPED,
]);

/** shape → Discover render kernel (mirror of market_shape.py SHAPE_TO_KERNEL). */
export const SHAPE_TO_KERNEL: Record<MarketShape, MarketKernel> = {
  [SHAPE_CLAIM]: "number+delta",
  [SHAPE_QUANTITY]: "ladder-strip",
  [SHAPE_DUEL]: "split",
  [SHAPE_FIELD]: "top-3",
  [SHAPE_CONTAINER_MEMBER]: "headliner+count",
  [SHAPE_UNSHAPED]: null,
};

export function isMarketShape(value: unknown): value is MarketShape {
  return typeof value === "string" && ALL_SHAPES.has(value);
}

/**
 * The STORED shape (`FuturesMarket.market_type`) alone — null when the payload
 * carries no valid one.
 *
 * Deliberately NOT `resolveShape`. The fallback heuristic guesses a shape from
 * outcome-name regexes, which is the same kind of text-derived guess as the
 * Discover archetype's `suggested_format` hint. Letting one guess overrule
 * another adds no truth and can only launder a regex miss into a confident
 * render. Only the field the backend classifier actually wrote gets a vote.
 */
export function storedShape(marketType: unknown): MarketShape | null {
  return isMarketShape(marketType) ? marketType : null;
}

/**
 * Kernels a stored shape positively CONTRADICTS.
 *
 * Discover picks its card from `discover_card.suggested_format`, which
 * `discover_card_archetypes.py` derives from outcome-label regexes and a raw
 * outcome count — it never reads `market_type`. So two channels describe the
 * same market and they disagree. Measured against the live feed (95 items, 61
 * futures cards, 2026-08-31): 12 cards drew a kernel that contradicts the
 * stored shape.
 *
 * This table is the tie-break, and it is deliberately NARROW — only the two
 * contradictions that were observed AND whose correct kernel already exists as
 * a live render:
 *
 *   field    ✗ ladder-strip  A field is a ranked competition between entrants.
 *                            Drawing it as a threshold ladder invents an
 *                            ordering between rivals and prints a cumulative
 *                            "Above 50% through <entrant>" footer over it.
 *   quantity ✗ top-3         A quantity is ONE continuous question. The
 *                            leaderboard numbers its rungs "Rank N by
 *                            probability" and crops to 4, so a 7-rung date
 *                            ladder loses its three nearest buckets and reads
 *                            as if the dates were racing each other.
 *
 * NOT listed, on purpose:
 *   duel / container_member — their kernels (split, headliner+count) have no
 *     live Discover render at all, so a veto could only downgrade a working
 *     card to the generic hero. 7 live cards are in this state; wiring those
 *     two kernels is a separate ship, not a tie-break.
 *   unshaped — by definition has no kernel to defend (SHAPE_TO_KERNEL is null).
 *
 * A veto only ever REMOVES a kernel from consideration. It never forces one:
 * whether the surviving kernel can actually be drawn is still gated on having
 * the data for it, so a mistyped shape degrades to the generic hero rather
 * than rendering an empty ladder.
 */
const SHAPE_FORBIDS_KERNEL: Partial<Record<MarketShape, ReadonlySet<MarketKernel>>> = {
  [SHAPE_FIELD]: new Set<MarketKernel>(["ladder-strip"]),
  [SHAPE_QUANTITY]: new Set<MarketKernel>(["top-3"]),
};

/** True when the stored shape rules out drawing `kernel` for this market. */
export function shapeForbidsKernel(marketType: unknown, kernel: MarketKernel): boolean {
  const shape = storedShape(marketType);
  if (shape == null) return false;
  return SHAPE_FORBIDS_KERNEL[shape]?.has(kernel) ?? false;
}

/** The render kernel for a shape (null when the shape has no native kernel). */
export function kernelForShape(shape: MarketShape | null | undefined): MarketKernel {
  return shape ? SHAPE_TO_KERNEL[shape] ?? null : null;
}

/** Minimal structural signal a caller can supply for the fallback heuristic. */
export interface ShapeSignal {
  /** The stored shape field (`FuturesMarket.market_type`) — the source of truth. */
  market_type?: string | null;
  /** Outcome name strings, for the fallback only. */
  outcomeNames?: (string | null | undefined)[] | null;
  /** Set when the market is linked to a game (→ duel). */
  eventId?: number | null;
  /** >1 when the market is a member of a decomposed field/container. */
  groupSize?: number | null;
  /** cross-source grouping key (fallback container-member detection). */
  groupId?: string | null;
}

const YES_NO = new Set(["yes", "no"]);

// A single outcome name that reads as a numeric threshold / range / bin. This is
// a deliberately loose mirror of market_shape.py's _NUMERIC_OUTCOME_RE — the
// fallback only needs a first-draft signal, never resolution parity.
const NUMERIC_OUTCOME_RE =
  /^\s*(?:(?:≥|≤|>=|<=|>|<)\s*[$€£]?\d|(?:at\s+least|at\s+most|above|over|under|below|less\s+than|more\s+than|greater\s+than|up\s+to|or\s+more|or\s+higher|or\s+less)\b|[$€£]?\d[\d,.]*\s*(?:k|m|b|bn|mn)?\s*(?:[-–—]|to)\s*[$€£]?\d|[$€£]?\d[\d,.]*\s*(?:k|m|b|bn|mn)?\s*(?:\+|or\s+more|or\s+higher)\s*$|[$€£]?\d[\d,.]*\s*(?:%|percent|points?|pts?|goals?|°f?|°c?)?\s*$)/i;

function norm(s: string | null | undefined): string {
  return (s ?? "").trim().toLowerCase();
}

/**
 * Resolve a market's shape.
 *
 * Preference order:
 *   1. The stored `market_type` field (Queue #194 backfill) — authoritative.
 *   2. A fallback structural heuristic — a first-draft mirror of the backend
 *      classifier, used only until the backfill reaches 100% coverage and the
 *      API exposes `market_type` on every surface.
 *
 * TODO(L2-118 Phase 2 / remove): delete `resolveShapeFallback` and require a
 * non-null `market_type` once the #194 backfill is confirmed 100% and the
 * futures/feed payloads carry the field. The fallback exists ONLY to bridge the
 * window where a surface hasn't been re-plumbed to read the stored shape.
 */
export function resolveShape(signal: ShapeSignal): MarketShape | null {
  if (isMarketShape(signal.market_type)) {
    return signal.market_type;
  }
  return resolveShapeFallback(signal);
}

/** TODO(L2-118 Phase 2): remove once `market_type` ships on every payload. */
export function resolveShapeFallback(signal: ShapeSignal): MarketShape | null {
  const names = (signal.outcomeNames ?? [])
    .map(norm)
    .filter((n) => n.length > 0);
  const n = names.length;

  if (n < 2) return SHAPE_UNSHAPED;

  const named = names.filter((nm) => !YES_NO.has(nm));
  const numeric = named.filter((nm) => NUMERIC_OUTCOME_RE.test(nm)).length;
  if (numeric >= 2 && numeric * 2 >= named.length) return SHAPE_QUANTITY;

  const isYesNo = names.every((nm) => YES_NO.has(nm));
  const groupSize = signal.groupSize ?? 1;
  if (signal.groupId && groupSize > 1 && n === 2 && isYesNo) {
    return SHAPE_CONTAINER_MEMBER;
  }

  if (n === 2) {
    if (signal.eventId != null) return SHAPE_DUEL;
    if (isYesNo) return SHAPE_CLAIM;
    return SHAPE_DUEL; // 2 named sides = duel (census mis-bucket fix)
  }

  return SHAPE_FIELD;
}
