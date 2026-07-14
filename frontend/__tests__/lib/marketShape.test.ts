// L2-118 Phase 1: the frontend shape resolver mirrors market_shape.py. Every
// surface keys off the stored `market_type` field; the fallback heuristic bridges
// the window before the #194 backfill reaches every payload (TODO-remove).

import {
  SHAPE_CLAIM,
  SHAPE_QUANTITY,
  SHAPE_DUEL,
  SHAPE_FIELD,
  SHAPE_CONTAINER_MEMBER,
  SHAPE_UNSHAPED,
  SHAPE_TO_KERNEL,
  isMarketShape,
  kernelForShape,
  resolveShape,
  resolveShapeFallback,
} from "@/lib/marketShape";

describe("marketShape vocabulary", () => {
  test("kernel map matches market_shape.py SHAPE_TO_KERNEL", () => {
    expect(SHAPE_TO_KERNEL[SHAPE_CLAIM]).toBe("number+delta");
    expect(SHAPE_TO_KERNEL[SHAPE_QUANTITY]).toBe("ladder-strip");
    expect(SHAPE_TO_KERNEL[SHAPE_DUEL]).toBe("split");
    expect(SHAPE_TO_KERNEL[SHAPE_FIELD]).toBe("top-3");
    expect(SHAPE_TO_KERNEL[SHAPE_CONTAINER_MEMBER]).toBe("headliner+count");
    expect(SHAPE_TO_KERNEL[SHAPE_UNSHAPED]).toBeNull();
  });

  test("isMarketShape guards the vocabulary", () => {
    expect(isMarketShape("quantity")).toBe(true);
    expect(isMarketShape("bogus")).toBe(false);
    expect(isMarketShape(null)).toBe(false);
    expect(isMarketShape(42)).toBe(false);
  });

  test("kernelForShape handles null/undefined", () => {
    expect(kernelForShape(SHAPE_QUANTITY)).toBe("ladder-strip");
    expect(kernelForShape(null)).toBeNull();
    expect(kernelForShape(undefined)).toBeNull();
  });
});

describe("resolveShape — stored field is authoritative", () => {
  test("uses market_type when valid", () => {
    expect(resolveShape({ market_type: "quantity", outcomeNames: ["Yes", "No"] })).toBe(
      SHAPE_QUANTITY,
    );
  });

  test("falls back when market_type absent or invalid", () => {
    expect(resolveShape({ market_type: null, outcomeNames: ["Yes", "No"] })).toBe(SHAPE_CLAIM);
    expect(resolveShape({ market_type: "garbage", outcomeNames: ["Yes", "No"] })).toBe(
      SHAPE_CLAIM,
    );
  });
});

describe("resolveShapeFallback — first-draft heuristic (TODO-remove)", () => {
  test("0/1 outcome → unshaped", () => {
    expect(resolveShapeFallback({ outcomeNames: [] })).toBe(SHAPE_UNSHAPED);
    expect(resolveShapeFallback({ outcomeNames: ["Before 2028"] })).toBe(SHAPE_UNSHAPED);
  });

  test("numeric bins → quantity", () => {
    expect(resolveShapeFallback({ outcomeNames: ["≥ 60", "≥ 70", "≥ 80"] })).toBe(SHAPE_QUANTITY);
    expect(
      resolveShapeFallback({ outcomeNames: ["Over 5.5", "Under 5.5"] }),
    ).toBe(SHAPE_QUANTITY);
  });

  test("yes/no pair with no game link → claim", () => {
    expect(resolveShapeFallback({ outcomeNames: ["Yes", "No"] })).toBe(SHAPE_CLAIM);
  });

  test("yes/no pair linked to a game → duel", () => {
    expect(resolveShapeFallback({ outcomeNames: ["Yes", "No"], eventId: 99 })).toBe(SHAPE_DUEL);
  });

  test("two named sides → duel (census mis-bucket fix)", () => {
    expect(resolveShapeFallback({ outcomeNames: ["Lakers", "Celtics"] })).toBe(SHAPE_DUEL);
  });

  test("yes/no member of a decomposed group → container_member", () => {
    expect(
      resolveShapeFallback({ outcomeNames: ["Yes", "No"], groupId: "poly:123", groupSize: 8 }),
    ).toBe(SHAPE_CONTAINER_MEMBER);
  });

  test("many named outcomes → field", () => {
    expect(
      resolveShapeFallback({ outcomeNames: ["Jokic", "Doncic", "Gilgeous-Alexander", "Tatum"] }),
    ).toBe(SHAPE_FIELD);
  });
});
