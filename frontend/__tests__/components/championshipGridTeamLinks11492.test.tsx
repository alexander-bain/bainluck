import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("@/hooks/useAnalytics", () => ({
  useAnalytics: () => ({ track: () => {} }),
}));

import TournamentProgressionTable from "@/components/TournamentProgressionTable";
import { gridSlugToSportKey } from "@/lib/gridSlug";
import type { ProgressionResponse } from "@/lib/types";

const THIRTEEN_TEAM_GRIDS: ReadonlyArray<{
  slug: string;
  team: string;
  expectedHref: string;
}> = [
  { slug: "mlb", team: "Atlanta Braves", expectedHref: "/sport/baseball/mlb/team/atlanta-braves" },
  { slug: "nba", team: "Boston Celtics", expectedHref: "/sport/basketball/nba/team/boston-celtics" },
  { slug: "nfl", team: "Kansas City Chiefs", expectedHref: "/sport/football/nfl/team/kansas-city-chiefs" },
  { slug: "nhl", team: "Edmonton Oilers", expectedHref: "/sport/hockey/nhl/team/edmonton-oilers" },
  { slug: "wnba", team: "New York Liberty", expectedHref: "/sport/basketball/wnba/team/new-york-liberty" },
  { slug: "ncaa-basketball", team: "Duke Blue Devils", expectedHref: "/sport/basketball/ncaab/team/duke-blue-devils" },
  { slug: "ncaa-women-basketball", team: "South Carolina Gamecocks", expectedHref: "/sport/basketball/wncaab/team/south-carolina-gamecocks" },
  { slug: "ncaa-football", team: "Ohio State Buckeyes", expectedHref: "/sport/football/ncaaf/team/ohio-state-buckeyes" },
  { slug: "epl", team: "Arsenal", expectedHref: "/sport/soccer/epl/team/arsenal" },
  { slug: "la-liga", team: "Real Madrid", expectedHref: "/sport/soccer/laliga/team/real-madrid" },
  { slug: "champions-league", team: "Bayern Munich", expectedHref: "/sport/soccer/ucl/team/bayern-munich" },
  { slug: "bundesliga", team: "Bayer Leverkusen", expectedHref: "/sport/soccer/bundesliga/team/bayer-leverkusen" },
  { slug: "mls", team: "Inter Miami CF", expectedHref: "/sport/soccer/mls/team/inter-miami-cf" },
];

function buildProgression(slug: string, participantName: string): ProgressionResponse {
  return {
    sport: gridSlugToSportKey(slug) ?? slug,
    tournament_name: "",
    stages: [
      {
        key: "champion",
        label: "Champion",
        order: 0,
        market_id: null,
        market_name: null,
        resolved: false,
      },
    ],
    participants: [
      {
        name: participantName,
        team_id: 1,
        logo_url: null,
        primary_color: null,
        conference: null,
        region: null,
        seed: null,
        record: "10-2",
        probabilities: { champion: 0.25 },
        changes_24h: {},
        status: {},
        sources_data: {},
      },
    ],
  };
}

describe("#11492 Championship grid team names link to their team page across all 13 team leagues", () => {
  test.each(THIRTEEN_TEAM_GRIDS)(
    "/playoffs/$slug renders <a href=\"$expectedHref\"> for $team",
    ({ slug, team, expectedHref }) => {
      const html = renderToStaticMarkup(
        <TournamentProgressionTable data={buildProgression(slug, team)} />,
      );
      expect(html).toContain(`href="${expectedHref}"`);
      expect(html).toContain(`>${team}</a>`);
    },
  );

  test("/playoffs/golf keeps golfers as unlinked spans without hover:underline", () => {
    const html = renderToStaticMarkup(
      <TournamentProgressionTable data={buildProgression("golf", "Scottie Scheffler")} />,
    );
    expect(html).not.toContain("<a ");
    expect(html).not.toContain("hover:underline");
    expect(html).toContain("Scottie Scheffler");
  });
});
