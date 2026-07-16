// L2-135 Item 3: the "Scoring & Records" classifier — which concept-envelope
// children become QuantityGroup ladders, and the market_ids the page must drop
// from props_script so nothing double-renders.

import {
  scoringRecordChildren,
  scoringRecordMarketIds,
} from "../../components/event/ScoringRecordsLadders";
import type { EventConceptChild } from "../../lib/types";

function child(
  market_id: number,
  market_name: string,
  outcomes: { name: string; probability: number | null }[],
): EventConceptChild {
  return { market_id, market_name, outcomes, kind: "prop" };
}

describe("scoringRecordChildren", () => {
  test("keeps scoring/records families with ≥2 priced outcomes", () => {
    const children = [
      child(1, "Winning score", [
        { name: "Under 270", probability: 0.4 },
        { name: "270 or worse", probability: 0.6 },
      ]),
      child(2, "Margin of victory", [
        { name: "1 stroke", probability: 0.3 },
        { name: "2+ strokes", probability: 0.7 },
      ]),
    ];
    expect(scoringRecordChildren(children).map((c) => c.market_id)).toEqual([1, 2]);
  });

  test("excludes non-scoring markets (e.g. round leader, make cut)", () => {
    const children = [
      child(10, "Round 1 Leader", [
        { name: "Scottie Scheffler", probability: 0.2 },
        { name: "Rory McIlroy", probability: 0.15 },
      ]),
      child(11, "Make the cut: Tiger Woods", [
        { name: "Yes", probability: 0.5 },
        { name: "No", probability: 0.5 },
      ]),
    ];
    expect(scoringRecordChildren(children)).toEqual([]);
  });

  test("a single-outcome scoring market is not a ladder", () => {
    const children = [
      child(20, "Lowest round", [{ name: "Under 64", probability: 0.5 }]),
    ];
    expect(scoringRecordChildren(children)).toEqual([]);
  });

  test("marketIds set powers the props-script exclusion", () => {
    const children = [
      child(1, "Winning score under par", [
        { name: "Under 270", probability: 0.4 },
        { name: "Over 270", probability: 0.6 },
      ]),
      child(2, "Playoff", [
        { name: "Yes", probability: 0.2 },
        { name: "No", probability: 0.8 },
      ]),
    ];
    const ids = scoringRecordMarketIds(children);
    expect(ids.has(1)).toBe(true);
    expect(ids.has(2)).toBe(false);
  });

  test("empty / undefined children are safe", () => {
    expect(scoringRecordChildren(undefined)).toEqual([]);
    expect(scoringRecordMarketIds(undefined).size).toBe(0);
  });
});
