// L2-162: season-journey line picker — tier priority + eligibility.
import { isPlayerDestinationMarket, pickJourneyFuture } from "../../lib/teamSeasonJourney";
import { teamHeadline } from "../../lib/teamHeadline";
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

// #9113: LAFC's page read `CHAMPIONSHIP 1%` — the 1% was Kalshi's "Neymar: Next
// Club" (market 11372050, tier 5, outcome "LAFC"), the only future LAFC carried.
describe("player-destination markets never stand in for a team's season (#9113)", () => {
  const neymar = item({
    market_id: 11372050,
    outcome_id: 64410243,
    outcome_name: "LAFC",
    market_name: "Neymar: Next Club",
    market_tier: 5,
    category: "soccer",
    probability: 0.01,
  });

  test("the LAFC payload has no journey and no hero number", () => {
    expect(pickJourneyFuture([neymar])).toBeNull();
    expect(teamHeadline([], [neymar])).toBeNull();
  });

  test("a real season market still wins when a destination market sits beside it", () => {
    const cup = item({ market_id: 7, outcome_id: 70, market_name: "MLS Cup Winner", market_tier: 5, probability: 0.004 });
    const pick = pickJourneyFuture([{ ...neymar, probability: 0.3 }, cup]);
    expect(pick?.marketId).toBe(7);
    expect(teamHeadline([], [{ ...neymar, probability: 0.3 }, cup])?.probability).toBe(0.004);
  });

  test.each([
    "Neymar: Next Club",
    "David Alaba: Next Club (League)",
    "Kevin Durant's Next Team",
    "Baker Mayfield Next Team",
    "Kenneth Walker III's next team?",
    "NBA: Steph Curry Next Team",
    "Where will Cristiano Ronaldo go next?",
  ])("%s is a player-destination market", (name) => {
    expect(isPlayerDestinationMarket(name)).toBe(true);
  });

  test.each([
    "MLB World Series Winner",
    "Pro Football Champion",
    "MLS Cup Winner",
    "Next Team to Score",
    "Premier League Winner",
    "Who will be the next Pope?",
  ])("%s is not", (name) => {
    expect(isPlayerDestinationMarket(name)).toBe(false);
  });
});
