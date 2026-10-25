/**
 * #10955 / #11158 Step 2 — the split itself. The host wiring is proven in
 * `components/settlementPointIsAResultMark10955.test.tsx`; a helper test alone
 * cannot show the chart obeys it.
 */

import {
  isSettlementPoint,
  settlementResultWord,
  splitSettlementPoints,
} from "@/lib/chartSettlementPoints";
import type { FuturesHistoryPoint, FuturesOutcomeHistory } from "@/lib/types";

type ServedPoint = FuturesHistoryPoint & { settlement_basis?: string };

const point = (ts: string, p: number | null, bookmaker = "consensus"): ServedPoint => ({
  timestamp: ts,
  probability: p,
  american_odds: null,
  bookmaker,
});

const settle = (ts: string, p: number | null, basis?: string): ServedPoint => ({
  ...point(ts, p, "settlement"),
  ...(basis === undefined ? {} : { settlement_basis: basis }),
});

const leg = (id: number, history: ServedPoint[]): FuturesOutcomeHistory => ({
  outcome_id: id,
  name: `Leg ${id}`,
  history,
});

const REAL = [point("2026-10-01T10:00:00Z", 0.4), point("2026-10-01T11:00:00Z", 0.41)];

describe("point kind decides, never the basis", () => {
  test.each(["resolution_date", "settled_at", "last_observation", "clock", undefined, "venue_close_v2"])(
    "basis %p: the settlement point leaves the series",
    (basis) => {
      const { real, results } = splitSettlementPoints([
        leg(1, [...REAL, settle("2026-10-01T12:00:00Z", 0, basis)]),
      ]);
      expect(real[0].history).toEqual(REAL);
      expect(results.get(1)).toBe("lost");
    },
  );

  test("only the exact word 'settlement' is a settlement point", () => {
    expect(isSettlementPoint({ bookmaker: "settlement" })).toBe(true);
    for (const b of ["consensus", "Settlement", "settlement_sync", "kalshi_archive", ""]) {
      expect(isSettlementPoint({ bookmaker: b })).toBe(false);
    }
  });
});

describe("the grade is read as served, never repaired", () => {
  test("1 is won, 0 is lost", () => {
    const { results } = splitSettlementPoints([
      leg(1, [...REAL, settle("2026-10-01T12:00:00Z", 1)]),
      leg(2, [...REAL, settle("2026-10-01T12:00:00Z", 0)]),
    ]);
    expect(results.get(1)).toBe("won");
    expect(results.get(2)).toBe("lost");
  });

  test.each([0.5, 0.999, 0.001, null])("%p is recorded, never lost", (p) => {
    const { results } = splitSettlementPoints([leg(1, [...REAL, settle("2026-10-01T12:00:00Z", p)])]);
    expect(results.get(1)).toBe("recorded");
    expect(settlementResultWord("recorded")).toBeNull();
  });

  test("a leg with no settlement point has no result at all", () => {
    expect(splitSettlementPoints([leg(1, REAL)]).results.size).toBe(0);
  });

  test("the words are the product's settled vocabulary", () => {
    expect(settlementResultWord("won")).toBe("Won");
    expect(settlementResultWord("lost")).toBe("Lost");
  });
});

describe("healthy legs are untouched by construction", () => {
  test("a field with no settlement point returns the very same array", () => {
    const field = [leg(1, REAL), leg(2, REAL)];
    expect(splitSettlementPoints(field).real).toBe(field);
  });

  test("a healthy leg beside a settled one is the same object", () => {
    const healthy = leg(2, REAL);
    const { real } = splitSettlementPoints([leg(1, [...REAL, settle("2026-10-01T12:00:00Z", 0)]), healthy]);
    expect(real[1]).toBe(healthy);
  });

  test("a synthesized-only winner keeps its place with an empty series", () => {
    const { real, results } = splitSettlementPoints([
      leg(1, REAL),
      leg(99, [settle("2026-10-27T12:00:00Z", 1, "resolution_date")]),
    ]);
    expect(real.map((o) => o.outcome_id)).toEqual([1, 99]);
    expect(real[1].history).toEqual([]);
    expect(results.get(99)).toBe("won");
  });

  test("the input is never mutated; raw stamps, values and sources survive", () => {
    const field = [leg(1, [...REAL, settle("2026-10-01T12:00:00Z", 0, "resolution_date")])];
    const before = JSON.stringify(field);
    const { real } = splitSettlementPoints(field);
    expect(JSON.stringify(field)).toBe(before);
    expect(real[0].history[0]).toBe(field[0].history[0]);
  });
});
