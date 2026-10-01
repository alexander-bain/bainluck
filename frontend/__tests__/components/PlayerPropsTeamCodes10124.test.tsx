// #10124 — the Player Props team filter on /events/14780550 (Steelers at
// Browns, 390px, 2026-10-01) read "All · BRO · STE" while the same page's
// market map read the served codes CLE / PIT. The chips were lettered by the
// crest badge, which reads a team's nickname, and the event page gave the
// dashboard neither the served codes nor the sport.
//
// The issue's suggested repair — pass the sport to the badge — is pinned below
// as INERT: the badge is BRO with or without it. The chips now take the served
// codes as a pair, and fall back to the hero's own call (badge + sport).

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import PlayerPropsDashboard from "../../components/PlayerPropsDashboard";
import type { GameMarketsResponse } from "../../lib/api";
import { shippableCrestBadge } from "../../lib/teamShortName";

const NFL = "americanfootball_nfl";

function row(outcome: string, team: "home" | "away") {
  return {
    market_name: "Player Props",
    outcome_name: outcome,
    threshold: 49.5,
    over_probability: 0.5,
    source: "polymarket",
    movement: null,
    actual: null,
    hit: null,
    is_winner: false,
    resolution_source: null,
    player_team: team,
  };
}

interface ChipProps {
  homeTeam: string;
  awayTeam: string;
  homeTeamAbbrev?: string | null;
  awayTeamAbbrev?: string | null;
  sport?: string | null;
}

function chipLabels(props: ChipProps): string[] {
  const html = renderToStaticMarkup(
    <PlayerPropsDashboard
      data={
        {
          player_props: [
            row("Deshaun Watson: Passing Yards O/U 199.5", "home"),
            row("Aaron Rodgers: Passing Yards O/U 199.5", "away"),
          ],
          other: [],
        } as unknown as GameMarketsResponse
      }
      eventStatus="scheduled"
      boxScore={null}
      {...props}
    />,
  );
  // The filter chips are the only buttons whose whole text is "All" or a code.
  const labels = (html.match(/<button[^>]*>([^<]*)<\/button>/g) ?? []).map((b) =>
    b.replace(/<button[^>]*>/, "").replace(/<\/button>$/, ""),
  );
  const all = labels.indexOf("All");
  expect(all).toBeGreaterThanOrEqual(0);
  return labels.slice(all, all + 3);
}

const BROWNS_STEELERS = { homeTeam: "Cleveland Browns", awayTeam: "Pittsburgh Steelers" };

describe("#10124 premise — the badge alone cannot letter these teams", () => {
  test("the badge is BRO / STE with OR without the sport (the suggested repair is inert)", () => {
    expect(shippableCrestBadge("Cleveland Browns")).toBe("BRO");
    expect(shippableCrestBadge("Pittsburgh Steelers")).toBe("STE");
    expect(shippableCrestBadge("Cleveland Browns", NFL)).toBe("BRO");
    expect(shippableCrestBadge("Pittsburgh Steelers", NFL)).toBe("STE");
  });
});

describe("#10124 the Player Props filter reads the served team codes", () => {
  test("Steelers at Browns, as the event page mounts it: All · CLE · PIT", () => {
    expect(
      chipLabels({ ...BROWNS_STEELERS, homeTeamAbbrev: "CLE", awayTeamAbbrev: "PIT", sport: NFL }),
    ).toEqual(["All", "CLE", "PIT"]);
  });

  test("the codes win without the sport too — the sport is not what fixes it", () => {
    expect(chipLabels({ ...BROWNS_STEELERS, homeTeamAbbrev: "CLE", awayTeamAbbrev: "PIT" })).toEqual([
      "All",
      "CLE",
      "PIT",
    ]);
  });

  test("control: a caller that passes no codes keeps exactly the old chips", () => {
    expect(chipLabels(BROWNS_STEELERS)).toEqual(["All", "BRO", "STE"]);
    expect(chipLabels({ ...BROWNS_STEELERS, sport: NFL })).toEqual(["All", "BRO", "STE"]);
  });
});

describe("#10124 a served code is used only as a clean pair", () => {
  test("one side without a code: both sides take the badge, never 'CLE / STE'", () => {
    expect(chipLabels({ ...BROWNS_STEELERS, homeTeamAbbrev: "CLE", awayTeamAbbrev: null, sport: NFL })).toEqual([
      "All",
      "BRO",
      "STE",
    ]);
  });

  test("a stored long name is not a chip code (rows carry e.g. 'BOSTON UNIVERSITY')", () => {
    expect(
      chipLabels({
        homeTeam: "Boston University Terriers",
        awayTeam: "Holy Cross Crusaders",
        homeTeamAbbrev: "BOSTON UNIVERSITY",
        awayTeamAbbrev: "HC",
        sport: "basketball_ncaab",
      }),
    ).toEqual([
      "All",
      shippableCrestBadge("Boston University Terriers", "basketball_ncaab"),
      shippableCrestBadge("Holy Cross Crusaders", "basketball_ncaab"),
    ]);
  });

  test("the same code on both sides names neither: badges", () => {
    expect(chipLabels({ ...BROWNS_STEELERS, homeTeamAbbrev: "CLE", awayTeamAbbrev: "CLE", sport: NFL })).toEqual([
      "All",
      "BRO",
      "STE",
    ]);
  });

  test("blank codes fall back, and an unnameable side still reads HOME / AWAY", () => {
    expect(chipLabels({ ...BROWNS_STEELERS, homeTeamAbbrev: " ", awayTeamAbbrev: "" })).toEqual([
      "All",
      "BRO",
      "STE",
    ]);
    expect(chipLabels({ homeTeam: "", awayTeam: "", homeTeamAbbrev: null, awayTeamAbbrev: null })).toEqual([
      "All",
      "HOME",
      "AWAY",
    ]);
  });
});

describe("#10124 the fallback is the hero's call — the badge WITH the sport", () => {
  test("another league with no codes: the sport reaches the badge (G2, not ESP)", () => {
    const esports = { homeTeam: "G2 Esports", awayTeam: "Team Liquid" };
    expect(shippableCrestBadge("G2 Esports")).toBe("ESP");
    const [, home, away] = chipLabels({ ...esports, sport: "esports_lol" });
    expect(home).toBe("G2");
    expect(away).toBe(shippableCrestBadge("Team Liquid", "esports_lol"));
    // Without the sport, the old chip stands.
    expect(chipLabels(esports)[1]).toBe("ESP");
  });
});
