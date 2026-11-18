import {
  numericalScaleOrderIndices,
  orderByNumericalScale,
  parseNumericalScaleKey,
} from "@/lib/numericalScaleOrder";
import { futuresDistributionBoard } from "@/lib/discover/futuresBoard";
import { buildOutcomeLadderRungs } from "@/lib/futuresLadder";
import { orderNumericBuckets } from "@/components/economics/atoms";
import type { FeedFuturesData } from "@/lib/types";

describe("Direction 228 (#12885) — numerical-scale ordering across website surfaces", () => {
  it("orders 'What will the Fed rate be at the end of 2026' in ascending rate order, never by probability", () => {
    const fedRate2026 = [
      { id: 1, name: "4.25%", probability: 0.88 },
      { id: 2, name: "≥ 4.5%", probability: 0.06 },
      { id: 3, name: "4.0%", probability: 0.04 },
      { id: 4, name: "3.75%", probability: 0.01 },
    ];
    expect(orderByNumericalScale(fedRate2026).map((r) => r.name)).toEqual([
      "3.75%",
      "4.0%",
      "4.25%",
      "≥ 4.5%",
    ]);
    // Detail page QuantityGroup ladder (mutually_exclusive === true -> "served")
    expect(buildOutcomeLadderRungs(fedRate2026, "served").map((r) => r.label)).toEqual([
      "3.75%",
      "4.0%",
      "4.25%",
      "≥ 4.5%",
    ]);
  });

  it("orders 'How many Fed rate hikes in 2026' (1, 2, 3, 4 with parenthetical bps) in count order", () => {
    const fedHikes2026 = [
      { id: 10, name: "2 (50 bps)", probability: 0.92 },
      { id: 11, name: "3 (75 bps)", probability: 0.04 },
      { id: 12, name: "1 (25 bps)", probability: 0.03 },
      { id: 13, name: "4 (100 bps)", probability: 0.01 },
    ];
    expect(orderByNumericalScale(fedHikes2026).map((r) => r.name)).toEqual([
      "1 (25 bps)",
      "2 (50 bps)",
      "3 (75 bps)",
      "4 (100 bps)",
    ]);
    // /economics RateCutsChart / Histogram buckets
    const econBuckets: [number, string][] = fedHikes2026.map((o) => [
      Math.round(o.probability * 100),
      o.name,
    ]);
    expect(orderNumericBuckets(econBuckets).map(([, label]) => label)).toEqual([
      "1 (25 bps)",
      "2 (50 bps)",
      "3 (75 bps)",
      "4 (100 bps)",
    ]);
  });

  it("orders signed policy rate decisions from deepest cut through hold to largest hike", () => {
    const fomcJan = [
      { id: 1, name: "Hike 25bps", probability: 0.6 },
      { id: 2, name: "Fed maintains rate", probability: 0.37 },
      { id: 3, name: "Hike >25bps", probability: 0.02 },
      { id: 4, name: "Cut 25bps", probability: 0.02 },
      { id: 5, name: "Cut >25bps", probability: 0.01 },
    ];
    expect(orderByNumericalScale(fomcJan).map((r) => r.name)).toEqual([
      "Cut >25bps",
      "Cut 25bps",
      "Fed maintains rate",
      "Hike 25bps",
      "Hike >25bps",
    ]);
  });

  it("orders Discover / category board cards numerically while keeping the #1526 leader and suppressing podium digits", () => {
    const data = {
      id: 9001,
      name: "How many Fed rate hikes in 2026?",
      status: "open",
      outcome_count: 5,
      top_outcomes: [],
      discover_card: {
        suggested_format: "outcome_distribution",
        field_is_a_race: true,
        remaining_outcome_count: 0,
        distribution_outcomes: [
          { id: 1, name: "2 (50 bps)", label: "2 (50 bps)", probability: 0.72 },
          { id: 2, name: "3 (75 bps)", label: "3 (75 bps)", probability: 0.12 },
          { id: 3, name: "1 (25 bps)", label: "1 (25 bps)", probability: 0.09 },
          { id: 4, name: "4 (100 bps)", label: "4 (100 bps)", probability: 0.05 },
          { id: 5, name: "0 (0 bps)", label: "0 (0 bps)", probability: 0.02 },
        ],
      },
    } as unknown as FeedFuturesData;

    const board = futuresDistributionBoard(data);
    expect(board).not.toBeNull();
    expect(board!.scaleOrdered).toBe(true);
    // Leader ("2 (50 bps)") is retained by leaderFirstSlice(4), and the 4 kept rows run 1 -> 2 -> 3 -> 4
    expect(board!.rows.map((r) => r.label)).toEqual([
      "1 (25 bps)",
      "2 (50 bps)",
      "3 (75 bps)",
      "4 (100 bps)",
    ]);
  });

  it("refuses competitor fields (teams, nominees, candidates) and date ladders so they keep their own rules", () => {
    expect(
      numericalScaleOrderIndices([
        { name: "Philadelphia 76ers" },
        { name: "San Francisco 49ers" },
        { name: "Detroit Lions" },
      ]),
    ).toBeNull();
    expect(
      numericalScaleOrderIndices([
        { name: "Philadelphia 76ers" },
        { name: "San Francisco 49ers" },
      ]),
    ).toBeNull();
    expect(
      numericalScaleOrderIndices([
        { name: "Before April" },
        { name: "Before July" },
        { name: "Before 2027" },
      ]),
    ).toBeNull();
    expect(parseNumericalScaleKey("Yes")).toBeNull();
    expect(parseNumericalScaleKey("No")).toBeNull();
  });
});
