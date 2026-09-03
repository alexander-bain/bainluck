// UX-P276 / #2710 — "a card with no number is not shown" (Alex).
//
// The props strip rendered one card per grouped-feed row with no admission of
// any kind, so a market arriving with `outcomes: []` became a full card whose
// body was the words "No outcomes available". Measured on the served payload at
// the page's own `limit: 20` on 2026-09-03: 2 of 20 rows.
//
// FAIL CLOSED IS THE POINT. The defect is a card rendered bare, so a row shape
// this build does not recognise must be dropped, not shown. The `unknown type`
// test below is the one that pins that.

import {
  groupedFeedRowHasNumber,
  admittedPropStripRows,
} from "@/lib/sports/propStripAdmission";
import type { GroupedFeedItem } from "@/lib/types";

function marketRow(
  probabilities: Array<number | null>,
  id = 1,
): GroupedFeedItem {
  return {
    type: "market",
    market: {
      id,
      name: `Market ${id}`,
      source: "polymarket",
      category: "game_prop",
      sport: "tennis",
      outcomes: probabilities.map((probability, i) => ({
        id: id * 100 + i,
        name: i === 0 ? "Yes" : "No",
        probability,
      })),
    },
  } as GroupedFeedItem;
}

describe("groupedFeedRowHasNumber — market rows", () => {
  it("admits a market carrying a printable probability", () => {
    expect(groupedFeedRowHasNumber(marketRow([0.92, 0.08]))).toBe(true);
  });

  it("REFUSES a market with no outcomes at all — the measured defect", () => {
    // This is the row that rendered "No outcomes available".
    expect(groupedFeedRowHasNumber(marketRow([]))).toBe(false);
  });

  it("REFUSES a market whose every outcome is unpriced — Alex's 'Yes —, No —'", () => {
    expect(groupedFeedRowHasNumber(marketRow([null, null]))).toBe(false);
  });

  it("admits a partially-priced market: one real number is something to show", () => {
    expect(groupedFeedRowHasNumber(marketRow([null, 0.31]))).toBe(true);
  });

  it("admits a genuine 0 — a truthiness test would have dropped a printable 0%", () => {
    expect(groupedFeedRowHasNumber(marketRow([0, null]))).toBe(true);
  });

  it("REFUSES a STRINGIFIED probability — #2554's shape must not readmit a row", () => {
    // `json.dumps(default=str)` put `"0.682560"` on this very endpoint. A string
    // is truthy and is not something the card can render.
    const row = marketRow([null]);
    (row as { market: { outcomes: Array<{ probability: unknown }> } }).market.outcomes[0].probability =
      "0.682560";
    expect(groupedFeedRowHasNumber(row)).toBe(false);
  });

  it("REFUSES NaN, which is a number but not a printable one", () => {
    expect(groupedFeedRowHasNumber(marketRow([NaN]))).toBe(false);
  });
});

describe("groupedFeedRowHasNumber — the other three arms", () => {
  it("threshold: admitted on a priced point, refused when every point is bare", () => {
    const withPoints = (probability: number | null): GroupedFeedItem =>
      ({
        type: "threshold",
        group_key: "threshold:x",
        title: "Total games",
        points: [
          {
            id: 1,
            name: "Over 21.5",
            probability,
            threshold_value: 21.5,
            threshold_unit: "",
            threshold_direction: "above",
          },
        ],
        outcome_count: 1,
      }) as GroupedFeedItem;
    expect(groupedFeedRowHasNumber(withPoints(0.55))).toBe(true);
    expect(groupedFeedRowHasNumber(withPoints(null))).toBe(false);
  });

  it("stat_prop: admitted on a priced line, refused when every line is bare", () => {
    const withLine = (probability: number | null): GroupedFeedItem =>
      ({
        type: "stat_prop",
        group_key: "stat:x",
        player_name: "A Player",
        stat_category: "points",
        lines: [
          {
            id: 1,
            name: "25+ points",
            probability,
            threshold_value: 25,
            threshold_direction: "above",
            source: "kalshi",
          },
        ],
        market_count: 1,
      }) as GroupedFeedItem;
    expect(groupedFeedRowHasNumber(withLine(0.4))).toBe(true);
    expect(groupedFeedRowHasNumber(withLine(null))).toBe(false);
  });

  it("playoff_progression: admitted on a priced stage, refused when every stage is bare", () => {
    const withStage = (probability: number | null): GroupedFeedItem =>
      ({
        type: "playoff_progression",
        group_key: "playoff:x",
        entity_name: "A Team",
        stages: [
          {
            id: 1,
            name: "Reach the final",
            stage_name: "Final",
            stage_order: 1,
            probability,
            source: "kalshi",
          },
        ],
        market_count: 1,
      }) as GroupedFeedItem;
    expect(groupedFeedRowHasNumber(withStage(0.2))).toBe(true);
    expect(groupedFeedRowHasNumber(withStage(null))).toBe(false);
  });
});

describe("groupedFeedRowHasNumber — fail closed", () => {
  it("an UNRECOGNISED row type is dropped, never shown bare", () => {
    expect(
      groupedFeedRowHasNumber({ type: "brand_new_kernel" } as unknown as GroupedFeedItem),
    ).toBe(false);
  });

  it.each([null, undefined, "market", 7])("a malformed row (%p) is dropped", (row) => {
    expect(groupedFeedRowHasNumber(row as unknown as GroupedFeedItem)).toBe(false);
  });
});

describe("admittedPropStripRows — one list for the grid and the count", () => {
  it("keeps order and drops only the numberless rows", () => {
    const rows = [
      marketRow([0.9, 0.1], 1),
      marketRow([], 2),
      marketRow([null, null], 3),
      marketRow([0.4, 0.6], 4),
    ];
    const admitted = admittedPropStripRows(rows);
    expect(admitted).toHaveLength(2);
    expect(admitted.map((r) => (r as { market: { id: number } }).market.id)).toEqual([1, 4]);
  });

  it("CONTROL: a fully-priced list is returned untouched", () => {
    // Green on the parent too — this is what proves the filter narrows rather
    // than shrinks. If this ever goes red the strip is dropping real cards.
    const rows = [marketRow([0.9, 0.1], 1), marketRow([0.4, 0.6], 2)];
    expect(admittedPropStripRows(rows)).toHaveLength(2);
  });

  it.each([null, undefined, []])("%p yields an empty list rather than throwing", (rows) => {
    expect(admittedPropStripRows(rows as GroupedFeedItem[] | null)).toEqual([]);
  });
});
