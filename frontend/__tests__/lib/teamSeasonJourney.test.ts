// L2-162: season-journey line picker — tier priority + eligibility.
import { isPlayerDestinationMarket, pickJourneyFuture } from "../../lib/teamSeasonJourney";
import { teamHeadline } from "../../lib/teamHeadline";
import type { ChampionshipPathEntry, TeamFutureItem } from "../../lib/api";

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

// #9569: the Warriors' hero read CHAMPIONSHIP 1% off `championship_path` (market
// 2 "NBA Championship Winner", the tier-1 average 0.0069) while the journey under
// it charted "NBA: 2026 NBA Cup Winner" at 2% — tier 1 as well, and it won the
// probability tie-break. Values from production `/api/teams/golden-state-warriors`,
// 2026-09-29 07:33Z.
describe("pickJourneyFuture follows the page's headline market (#9569)", () => {
  const WARRIORS: TeamFutureItem[] = [
    item({ market_id: 57777176, outcome_id: 1, market_tier: 5, market_name: "NBA: Steph Curry Next Team", probability: 0.9865 }),
    item({ market_id: 60087207, outcome_id: 2, market_tier: 2, market_name: "NBA Playoffs: Team to advance to Western Conference Semifinals", probability: 0.22 }),
    item({ market_id: 59249431, outcome_id: 220348459, market_tier: 1, market_name: "NBA: 2026 NBA Cup Winner", probability: 0.02 }),
    item({ market_id: 2, outcome_id: 44, market_tier: 1, market_name: "NBA Championship Winner", probability: 0.013193 }),
    item({ market_id: 20569230, outcome_id: 3, market_tier: 1, market_name: "NBA: 2027 Champion", probability: 0.0105 }),
  ];
  const PATH: ChampionshipPathEntry[] = [
    { tier: 1, label: "Championship", market_name: "NBA Championship Winner", market_id: 2, probability: 0.0069, rank: 17, movement: null, season: "2026-27" },
  ];

  test("strawman: without the path the tier rule picks the Cup (the defect)", () => {
    expect(pickJourneyFuture(WARRIORS)?.marketName).toBe("NBA: 2026 NBA Cup Winner");
  });

  test("with the path, the journey charts the hero's market and prints the hero's number", () => {
    const pick = pickJourneyFuture(WARRIORS, PATH);
    expect(pick).toEqual({
      marketId: 2,
      outcomeId: 44,
      marketName: "NBA Championship Winner",
      probability: 0.0069,
    });
    expect(pick?.probability).toBe(teamHeadline(PATH, WARRIORS)?.probability);
  });

  test("a non-tier-1 headline step is followed too (path[0] when no tier 1)", () => {
    const path: ChampionshipPathEntry[] = [
      { ...PATH[0], tier: 2, label: "Conference", market_id: 60087207, probability: 0.21 },
    ];
    expect(pickJourneyFuture(WARRIORS, path)).toMatchObject({ marketId: 60087207, outcomeId: 2, probability: 0.21 });
  });

  test("falls back to the tier rule when the headline market is not in the futures list", () => {
    const path: ChampionshipPathEntry[] = [{ ...PATH[0], market_id: 999 }];
    expect(pickJourneyFuture(WARRIORS, path)?.marketId).toBe(59249431);
  });

  test("falls back to the tier rule when the headline step has no number", () => {
    const path: ChampionshipPathEntry[] = [{ ...PATH[0], probability: null }];
    expect(pickJourneyFuture(WARRIORS, path)?.marketId).toBe(59249431);
    expect(pickJourneyFuture(WARRIORS, [])?.marketId).toBe(59249431);
  });

  test("never charts an ineligible row even when it is the headline market", () => {
    const settled = WARRIORS.map((f) => (f.market_id === 2 ? { ...f, is_winner: true } : f));
    expect(pickJourneyFuture(settled, PATH)?.marketId).toBe(59249431);
  });
});
