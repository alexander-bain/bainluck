// L2-162: season-journey line picker — tier priority + eligibility.
import { pickJourneyFuture } from "../../lib/teamSeasonJourney";
import type { TeamFutureItem } from "../../lib/api";

function item(overrides: Partial<TeamFutureItem>): TeamFutureItem {
  return {
    outcome_id: 1,
    outcome_name: "Team",
    market_id: 10,
    market_name: "Market",
    market_tier: 1,
    category: null,
    source: "kalshi",
    probability: 0.2,
    probability_change_24h: null,
    rank: null,
    total_outcomes: null,
    resolution_date: null,
    ...overrides,
  };
}

describe("pickJourneyFuture", () => {
  test("prefers Championship (tier 1) over Conference/Division", () => {
    const pick = pickJourneyFuture([
      item({ market_tier: 4, market_id: 40, outcome_id: 4, market_name: "Division" }),
      item({ market_tier: 1, market_id: 10, outcome_id: 1, market_name: "World Series" }),
      item({ market_tier: 2, market_id: 20, outcome_id: 2, market_name: "Pennant" }),
    ]);
    expect(pick?.marketName).toBe("World Series");
    expect(pick?.marketId).toBe(10);
    expect(pick?.outcomeId).toBe(1);
  });

  test("falls back to Division when no Championship/Conference market exists", () => {
    const pick = pickJourneyFuture([
      item({ market_tier: 5, market_id: 50, outcome_id: 5, market_name: "Prop" }),
      item({ market_tier: 4, market_id: 40, outcome_id: 4, market_name: "Division" }),
    ]);
    expect(pick?.marketName).toBe("Division");
  });

  test("skips outcomes with no probability", () => {
    const pick = pickJourneyFuture([
      item({ market_tier: 1, probability: null, market_id: 10 }),
      item({ market_tier: 4, probability: 0.3, market_id: 40, outcome_id: 4, market_name: "Division" }),
    ]);
    expect(pick?.marketId).toBe(40);
  });

  test("returns null for empty/all-ineligible input", () => {
    expect(pickJourneyFuture([])).toBeNull();
    expect(pickJourneyFuture(null)).toBeNull();
    expect(pickJourneyFuture([item({ probability: null })])).toBeNull();
  });
});
