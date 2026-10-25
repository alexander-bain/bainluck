import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { TeamFutureItem, TeamPageTeam } from "@/lib/api";
import { teamHeadline } from "@/lib/teamHeadline";
import { pickJourneyFuture } from "@/lib/teamSeasonJourney";
import { buildTeamShareCopy, teamCardCopy } from "@/lib/teamShareMeta";
import { TeamFutureRow } from "@/components/TeamFutureRow";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

// Browser regression from #9858: with only the finalist/joint award in the
// synthetic team response, the hero said CHAMPIONSHIP 80% / 1%. Keep those
// markets reachable, but never turn their odds into the team's season odds.
function award(extra: Partial<TeamFutureItem> = {}): TeamFutureItem {
  return {
    market_id: 404, outcome_id: 4040, outcome_name: "Shai Gilgeous-Alexander",
    market_name: "NBA MVP Finalists", market_tier: 3, category: "awards",
    source: "kalshi", probability: 0.8, probability_change_24h: null,
    rank: null, total_outcomes: 75, resolution_date: null,
    ...extra,
  };
}

const team: TeamPageTeam = {
  id: 9859, slug: "thunder", name: "Oklahoma City Thunder", abbreviation: "OKC",
  sport_key: "basketball_nba", sport_name: "NBA", location: null,
  primary_color: null, secondary_color: null, logo_small: null, logo_large: null,
  record: null, standings: null, season_stats: null, roster: null,
};

describe("declared awards do not become a team's championship (#9858)", () => {
  test.each([
    "NBA MVP Finalists",
    "MVP Winner",
    "Western Conference Finals MVP Winner",
    "Shohei Ohtani: Cy Young and MVP Winner",
  ])("%s has no team hero or season-journey pick", (market_name) => {
    const rows = [award({ market_name })];
    expect(teamHeadline([], rows)).toBeNull();
    expect(pickJourneyFuture(rows)).toBeNull();
  });

  test.each<Partial<TeamFutureItem>>([
    { market_tier: 3, category: null },
    { market_tier: 1, display_tier: 3, category: null },
    { market_tier: 1, category: "awards" },
    { market_tier: null, category: "award" },
  ])("honors served award classification %j without a title heuristic", (classification) => {
    const rows = [award({ market_name: "Provider-specific award title", ...classification })];
    expect(teamHeadline([], rows)).toBeNull();
    expect(pickJourneyFuture(rows)).toBeNull();
  });

  test.each([1, 2, 4])("an actual season row at tier %i remains the hero and chart", (tier) => {
    const season = award({
      market_id: 12, outcome_id: 120, outcome_name: "Oklahoma City Thunder",
      market_name: "Team season market", market_tier: tier, category: "championship",
      probability: 0.04,
    });
    const rows = [award(), season];
    expect(teamHeadline([], rows)?.probability).toBe(0.04);
    expect(pickJourneyFuture(rows)?.marketId).toBe(12);
    expect(rows).toEqual([award(), season]);
  });

  test("the standalone award keeps its name, price and destination", () => {
    const html = renderToStaticMarkup(<TeamFutureRow item={award()} />);
    expect(html).toContain('href="/futures/404"');
    expect(html).toContain("NBA MVP Finalists");
    expect(html).toContain("80%");
    expect(html).toContain("Award");
  });

  test("the share description and image cannot relabel the finalist odds", () => {
    const verdict = { kind: "team" as const, payload: { team, championship_path: [], futures: [award()] } };
    expect(buildTeamShareCopy(verdict, "nba").description).not.toContain("80%");
    expect(teamCardCopy(verdict, "basketball", "nba").rows).toEqual([]);
  });
});
