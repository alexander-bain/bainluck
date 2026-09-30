/**
 * #9785 — EACH TEAM'S CHAMPIONSHIP PATH NAMES ITS OWN PENNANT.
 *
 * Production 2026-09-30, `/events/15319563` (Red Sox @ Yankees, Wild Card
 * Game 1) at 390px: both team cards read `AL / NL Champ` — the league grid's
 * header for BOTH pennants — over one team's chance at ONE of them. The served
 * `league_context` below is that page's, verbatim in the fields that matter:
 * the `pennant` column label and each team's `conference`.
 *
 * Both directions (gotcha #43): the AL club narrows to `AL Champ`, an NL club
 * to `NL Champ`, and a team whose conference names neither half — or is absent
 * — keeps the column label verbatim rather than being guessed at. The rung's
 * number is asserted beside its label so a repair that dropped the row passes
 * nothing.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import RelatedFutures from "@/components/RelatedFutures";
import { teamScopedColumnLabel } from "@/lib/teamScopedColumnLabel";
import type { RelatedFuturesResponse } from "@/lib/types";

let swrPayload: RelatedFuturesResponse;

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({
    data: swrPayload,
    error: undefined,
    isLoading: false,
    mutate: () => undefined,
  }),
}));

const COLUMNS = [
  { key: "make_playoffs", label: "Make Playoffs" },
  { key: "division", label: "Division" },
  { key: "pennant", label: "AL / NL Champ" },
  { key: "championship", label: "World Series" },
];

function render(
  homeConference: string | null,
  awayConference: string | null,
): string {
  swrPayload = {
    event_id: 15319563,
    home_team: "New York Yankees",
    away_team: "Boston Red Sox",
    home_team_futures: [],
    away_team_futures: [],
    series_markets: [],
    total_count: 0,
    summary: null,
    event_status: "completed",
    box_score: null,
    league_context: {
      league_slug: "mlb",
      league_name: "MLB Playoffs 2026",
      columns: COLUMNS,
      league_page_url: "/baseball/mlb",
      home_team: {
        cells: { pennant: 0.3125, championship: 0.1204 },
        changes_24h: { pennant: 0.0875, championship: 0.0257 },
        record: "93-68",
        conference: homeConference,
        sources_available: ["kalshi", "odds_api", "polymarket"],
      },
      away_team: {
        cells: { pennant: 0.0493, championship: 0.019 },
        changes_24h: { pennant: -0.0592, championship: -0.0335 },
        record: "87-75",
        conference: awayConference,
        sources_available: ["kalshi", "odds_api", "polymarket"],
      },
    },
  } as unknown as RelatedFuturesResponse;

  return renderToStaticMarkup(
    React.createElement(RelatedFutures, {
      eventId: 15319563,
      homeTeam: "New York Yankees",
      awayTeam: "Boston Red Sox",
      homeTeamColor: "#0C2340",
      awayTeamColor: "#BD3039",
    }),
  );
}

/** Every `data-stage` label with its probability, in render order. */
function stages(html: string): [string, number][] {
  return [
    ...html.matchAll(/data-stage="([^"]*)" data-probability="([^"]*)"/g),
  ].map((m) => [m[1], Number(m[2])]);
}

describe("#9785 — the pennant rung names the team's own league", () => {
  it("THE REPORTED PAGE: both American League cards read 'AL Champ'", () => {
    const html = render("American League", "American League");
    expect(stages(html)).toEqual([
      ["AL Champ", 0.3125],
      ["World Series", 0.1204],
      ["AL Champ", 0.0493],
      ["World Series", 0.019],
    ]);
    expect(html).not.toContain("AL / NL");
  });

  it("a National League club reads 'NL Champ' — the rule is not hard-wired to AL", () => {
    const html = render("National League", "American League");
    expect(stages(html).map(([l]) => l)).toEqual([
      "NL Champ",
      "World Series",
      "AL Champ",
      "World Series",
    ]);
  });

  it("CONTROL: no conference, or one naming neither half, keeps the column label verbatim", () => {
    const html = render(null, "Eastern Conference");
    expect(stages(html)).toEqual([
      ["AL / NL Champ", 0.3125],
      ["World Series", 0.1204],
      ["AL / NL Champ", 0.0493],
      ["World Series", 0.019],
    ]);
  });
});

describe("teamScopedColumnLabel", () => {
  it.each([
    ["AL / NL Champ", "American League", "AL Champ"],
    ["AL / NL Champ", "National League", "NL Champ"],
    ["AL / NL Champ", "american league", "AL Champ"],
    ["AL / NL Champ", "Eastern Conference", "AL / NL Champ"],
    ["AL / NL Champ", undefined, "AL / NL Champ"],
    ["Conference", "American League", "Conference"],
    ["World Series", "American League", "World Series"],
  ])("%s under %s → %s", (label, conference, expected) => {
    expect(teamScopedColumnLabel(label, conference)).toBe(expected);
  });
});
