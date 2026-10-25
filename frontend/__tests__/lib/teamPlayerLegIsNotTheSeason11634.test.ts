import type { TeamFutureItem } from "@/lib/api";
import { teamHeadline } from "@/lib/teamHeadline";
import { pickJourneyFuture } from "@/lib/teamSeasonJourney";

// #11634: the eliminated Dodgers' page led with "CHAMPIONSHIP 27%" — Max
// Muncy's "Silver Slugger: NL Third Baseman" leg (market 52755974, tier 5). The
// served `championship_path` was empty, and the futures fallback had nothing
// but player legs and next-team boards left. Rows are the production payload's
// own (GET /api/teams/los-angeles-dodgers, 2026-10-25 16:05Z), trimmed.
function row(extra: Partial<TeamFutureItem>): TeamFutureItem {
  return {
    outcome_id: 1, outcome_name: "Los Angeles Dodgers", market_id: 1,
    market_name: "Market", market_tier: 5, category: "baseball", source: "kalshi",
    probability: 0.01, probability_change_24h: null, rank: null,
    total_outcomes: null, resolution_date: null, is_winner: false,
    display_tier: 5, ...extra,
  };
}

const dodgers: TeamFutureItem[] = [
  row({ market_id: 59164885, outcome_id: 219750315, market_name: "Tarik Skubal Next Team", probability: 0.495 }),
  row({ market_id: 52755974, outcome_id: 198634611, outcome_name: "Max Muncy", market_name: "Silver Slugger: NL Third Baseman", probability: 0.27, outcome_is_player: true }),
  row({ market_id: 52755970, outcome_id: 2, outcome_name: "Andy Pages", market_name: "Gold Glove: NL Center Field", probability: 0.05, outcome_is_player: true }),
  row({ market_id: 132777, outcome_id: 3, outcome_name: "Roki Sasaki", market_name: "MLB Postseason: Strikeout Leader", probability: 0.01, outcome_is_player: true }),
  row({ market_id: 212, outcome_id: 4, outcome_name: "Tanner Scott", market_name: "NL Reliever of the Year Winner", market_tier: 1, display_tier: 3, probability: 0.03, outcome_is_player: true }),
];

describe("a player's leg is not the team's season (#11634)", () => {
  test("the Dodgers payload has no hero number and no journey", () => {
    expect(teamHeadline([], dodgers)).toBeNull();
    expect(pickJourneyFuture(dodgers)).toBeNull();
  });

  test("STRAWMAN: without the server's flag the page prints CHAMPIONSHIP 27% again", () => {
    const unflagged = dodgers.map(({ outcome_is_player: _flag, ...rest }) => rest);
    expect(teamHeadline([], unflagged)).toMatchObject({ label: "Championship", probability: 0.27 });
  });

  test("the club's own season leg still leads beside its players' legs", () => {
    const title = row({ market_id: 7, outcome_id: 70, market_name: "World Series Champion", market_tier: 1, display_tier: 1, probability: 0.004, outcome_is_player: false });
    expect(pickJourneyFuture([...dodgers, title])?.marketId).toBe(7);
    expect(teamHeadline([], [...dodgers, title])).toMatchObject({ label: "Championship", probability: 0.004 });
  });

  test("a row with no flag (no roster, or an older cached payload) keeps today's behaviour", () => {
    const cup = row({ market_id: 8, outcome_id: 80, outcome_name: "LAFC", market_name: "MLS Cup Winner", probability: 0.004 });
    expect(pickJourneyFuture([cup])?.marketId).toBe(8);
  });
});
