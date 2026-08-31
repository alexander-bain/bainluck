// lane1-Q478 — TOP-PRODUCT-DEFECTS item 10: the detail page renders a `quantity`
// market as a LADDER, off the shape field, instead of a ranked leaderboard.
//
// THE MEASURED DEFECT (production, 2026-08-31 ~11:0x PT, before the fix):
//   futures_markets.market_type for 109349 ("When will Apple release the iPhone
//     18?")                                                    = 'quantity'
//   GET /api/futures/109349 top-level keys                     = 26, and
//     `market_type` is NOT one of them.
//   GET /api/futures/groups/kalshi:KXIPHONERELEASE-IPHONE18
//     .threshold_groups                                        = {}
//
// So the classifier was right, and the page could not have keyed off it if it had
// tried: the field was never served. The only route to `QuantityGroup` was the
// backend's `threshold_groups`, whose `extract_threshold()` is numeric-only —
// replayed against the real rungs it returns None for all four:
//     'Before 2027' -> None   'Before October' -> None
//     'Before April' -> None  'Before July'    -> None
// Hence the empty group, the fallthrough, and the rank badges + "BA"/"BJ"/"BO"/"B2"
// initial avatars Alex saw.
//
// These tests pin the ORDERING CONTRACT and the shape VOCABULARY. The page-level
// proof (the ladder actually replaces the ranked table on the real payload) is in
// __tests__/components/futuresDetailShapeLadderQ478.test.tsx.

import {
  SHAPE_FIELD,
  SHAPE_PARTICIPATION,
  SHAPE_QUANTITY,
  SHAPE_UNSHAPED,
  isMarketShape,
  kernelForShape,
  resolveShape,
} from "@/lib/marketShape";

// The four real rungs of 109349, in the order and at the prices production served
// them (captured verbatim into __tests__/fixtures/futuresDetail109349Production.json).
const REAL_RUNGS = [
  { id: 1596638, name: "Before 2027", probability: 0.15 },
  { id: 1596639, name: "Before October", probability: 0.065 },
  { id: 1596641, name: "Before April", probability: 0.01 },
  { id: 1596640, name: "Before July", probability: 0.01 },
];

describe("the shape vocabulary mirrors the backend (lib/marketShape.ts)", () => {
  // market_shape.py's ALL_SHAPES has SEVEN members; the mirror had six. The
  // docstring claims they are kept "byte-identical … so the two never drift", and
  // `participation` had drifted. This is not cosmetic: `resolveShape` prefers the
  // stored field ONLY when `isMarketShape()` accepts it, so an unrecognised value
  // silently fell through to the structural name-guessing fallback — the exact
  // behaviour this queue exists to stop relying on.
  test("participation is a recognised shape and renders like a field", () => {
    expect(isMarketShape("participation")).toBe(true);
    expect(kernelForShape(SHAPE_PARTICIPATION)).toBe("top-3");
    // ...but it keeps its own identity: it is NOT collapsed into `field`, because
    // calibration cohorts on this same value.
    expect(SHAPE_PARTICIPATION).not.toBe(SHAPE_FIELD);
  });

  test("a stored participation value survives resolveShape instead of being re-guessed", () => {
    // Structurally these outcomes look like a field (3+ named entities). If the
    // stored value were rejected, the fallback would answer `field` and the drift
    // would be invisible.
    const shape = resolveShape({
      market_type: "participation",
      outcomeNames: ["Scottie Scheffler", "Rory McIlroy", "Jon Rahm"],
    });
    expect(shape).toBe(SHAPE_PARTICIPATION);
  });

  test("the stored field beats the structural fallback for the real specimen", () => {
    // The fallback CANNOT see this market's shape: its rungs carry no numeral that
    // NUMERIC_OUTCOME_RE matches, so it answers `field` — a leaderboard — which is
    // precisely the wrong render.
    const names = REAL_RUNGS.map((r) => r.name);
    expect(resolveShape({ outcomeNames: names })).toBe(SHAPE_FIELD);
    // With the field served, the same market resolves correctly.
    expect(resolveShape({ market_type: "quantity", outcomeNames: names })).toBe(
      SHAPE_QUANTITY,
    );
  });

  test("an unknown/absent stored value still falls back rather than throwing", () => {
    expect(resolveShape({ market_type: "not_a_shape", outcomeNames: ["a"] })).toBe(
      SHAPE_UNSHAPED,
    );
  });
});

describe("ladder ordering (lib/futuresLadder.ts)", () => {
  test("mutually_exclusive === false is the cumulative case; everything else keeps serve order", () => {
    const { ladderOrderFor } = require("@/lib/futuresLadder");
    // 109349 is mutually_exclusive=false in production — "Before April" ⊂ "Before
    // July", the rungs nest, so probabilities are monotone along the ladder.
    expect(ladderOrderFor(false)).toBe("cumulative");
    // Disjoint bins carry no ordering information in their prices.
    expect(ladderOrderFor(true)).toBe("served");
    // Unknown is conservative: never reorder on a guess.
    expect(ladderOrderFor(null)).toBe("served");
    expect(ladderOrderFor(undefined)).toBe("served");
  });

  test("the real specimen orders April -> July -> October -> 2027", () => {
    const { buildOutcomeLadderRungs } = require("@/lib/futuresLadder");
    const rungs = buildOutcomeLadderRungs(REAL_RUNGS, "cumulative");
    expect(rungs.map((r: { label: string }) => r.label)).toEqual([
      "Before April",
      "Before July",
      "Before October",
      "Before 2027",
    ]);
  });

  test("🔴 a PRICE TIE keeps serve order — it must NOT be broken on outcome id", () => {
    // This is the assertion that caught a real bug in this queue's own first cut.
    // "Before April" and "Before July" are BOTH 1%, and their ids run
    //     1596640 = July, 1596641 = April
    // so tiebreaking on id (insertion order) renders JULY ABOVE APRIL — a
    // backwards timeline, on the exact market the defect is about. Insertion order
    // is not a fact about the ladder. Serve order at least claims to be one.
    const { buildOutcomeLadderRungs } = require("@/lib/futuresLadder");
    const tied = REAL_RUNGS.filter((r) => r.probability === 0.01);
    expect(tied.map((r) => r.id)).toEqual([1596641, 1596640]); // April, July — id DESC
    const rungs = buildOutcomeLadderRungs(REAL_RUNGS, "cumulative");
    const labels = rungs.map((r: { label: string }) => r.label);
    expect(labels.indexOf("Before April")).toBeLessThan(labels.indexOf("Before July"));
  });

  test("the served order is preserved exactly when the market is mutually exclusive", () => {
    // Disjoint bins: sorting by probability would scramble a timeline.
    const { buildOutcomeLadderRungs } = require("@/lib/futuresLadder");
    const bins = [
      { id: 1, name: "0-10", probability: 0.1 },
      { id: 2, name: "10-20", probability: 0.6 },
      { id: 3, name: "20-30", probability: 0.3 },
    ];
    const rungs = buildOutcomeLadderRungs(bins, "served");
    expect(rungs.map((r: { label: string }) => r.label)).toEqual(["0-10", "10-20", "20-30"]);
  });

  test("rungs carry their final position in `value`, so QuantityGroup's sort is a no-op", () => {
    // QuantityGroup sorts ascending by `value` unless told not to. If the builder
    // left `value` unset the component would sort every rung as -Infinity and the
    // order decided here would be silently replaced by sort stability.
    const { buildOutcomeLadderRungs } = require("@/lib/futuresLadder");
    const rungs = buildOutcomeLadderRungs(REAL_RUNGS, "cumulative");
    expect(rungs.map((r: { value?: number }) => r.value)).toEqual([0, 1, 2, 3]);
  });

  test("labels are the outcome names verbatim — no invented '>= N' text", () => {
    const { buildOutcomeLadderRungs } = require("@/lib/futuresLadder");
    const rungs = buildOutcomeLadderRungs(REAL_RUNGS, "cumulative");
    for (const r of rungs) {
      expect(REAL_RUNGS.map((x) => x.name)).toContain(r.label);
      expect(r.label).not.toMatch(/[≥≤]/);
    }
  });

  test("a null price sorts to the end rather than to the front", () => {
    const { buildOutcomeLadderRungs } = require("@/lib/futuresLadder");
    const rungs = buildOutcomeLadderRungs(
      [
        { id: 1, name: "unknown", probability: null },
        { id: 2, name: "cheap", probability: 0.02 },
      ],
      "cumulative",
    );
    expect(rungs.map((r: { label: string }) => r.label)).toEqual(["cheap", "unknown"]);
  });

  test("wide labels are requested for date rungs and not for short numeric ones", () => {
    const { buildOutcomeLadderRungs, ladderNeedsWideLabels } = require("@/lib/futuresLadder");
    expect(ladderNeedsWideLabels(buildOutcomeLadderRungs(REAL_RUNGS, "cumulative"))).toBe(true);
    const numeric = buildOutcomeLadderRungs(
      [
        { id: 1, name: "≥ 60", probability: 0.8 },
        { id: 2, name: "≥ 80", probability: 0.3 },
      ],
      "cumulative",
    );
    expect(ladderNeedsWideLabels(numeric)).toBe(false);
  });
});
