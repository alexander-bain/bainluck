/**
 * #8627 — a player-award page stops printing one player's price as a team's odds.
 *
 * Production, `/futures/209` (NL MVP), 2026-09-25: the hero read 100% for Pete
 * Crow-Armstrong while "Games This Week — Each team's odds in this market"
 * printed "Chicago Cubs 1%". The route now serves each team's leading player and
 * `outcome_is_team: false` on a player field; the row names that player and the
 * caption stops claiming the numbers are team odds.
 *
 * CONTROL: a team field (no flag, or `true`) renders the team name and the old
 * caption, so a component that printed `outcome_name` everywhere would fail here.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import GamesThisWeek, { oddsCaption, oddsLabel } from "@/components/futures/GamesThisWeek";
import type { RelatedEvent, RelatedEventLinkedTeam } from "@/lib/types";

const player = (
  side: "home" | "away",
  team_name: string,
  outcome_name: string,
  probability: number,
): RelatedEventLinkedTeam => ({
  side,
  team_name,
  outcome_name,
  probability,
  american_odds: null,
  rank: null,
  outcome_is_team: false,
});

const CUBS_AT_RED_SOX: RelatedEvent = {
  event_id: 15320001,
  home_team: "Boston Red Sox",
  away_team: "Chicago Cubs",
  commence_time: "2026-09-25T14:05:00+00:00",
  status: "scheduled",
  sport: "baseball_mlb",
  home_score: null,
  away_score: null,
  linked_teams: [
    player("home", "Boston Red Sox", "Caleb Durbin", 0.01),
    player("away", "Chicago Cubs", "Pete Crow-Armstrong", 0.995),
  ],
};

/** A team field as older payloads serve it: no flag at all. */
const DODGERS_GIANTS: RelatedEvent = {
  event_id: 15400001,
  home_team: "Los Angeles Dodgers",
  away_team: "San Francisco Giants",
  commence_time: "2026-09-25T02:10:00+00:00",
  status: "scheduled",
  sport: "baseball_mlb",
  home_score: null,
  away_score: null,
  linked_teams: [
    {
      side: "home",
      team_name: "Los Angeles Dodgers",
      outcome_name: "Los Angeles Dodgers",
      probability: 0.3,
      american_odds: null,
      rank: 1,
    },
  ],
};

/** The odds block's name spans: the fixture line is not one of them. */
const oddsNames = (html: string): string[] =>
  Array.from(
    html.matchAll(/class="font-medium text-text-primary truncate[^"]*">([^<]*)</g),
    (m) => m[1],
  );

describe("#8627 a player field names the player, never the team", () => {
  it("prints each team's leading player, in fixture order", () => {
    const html = renderToStaticMarkup(<GamesThisWeek events={[CUBS_AT_RED_SOX]} />);

    expect(oddsNames(html)).toEqual(["Pete Crow-Armstrong", "Caleb Durbin"]);
    // The fixture itself still names both teams.
    expect(html).toContain("Chicago Cubs");
    expect(html).toContain("Boston Red Sox");
  });

  it("stops captioning the numbers as team odds", () => {
    const html = renderToStaticMarkup(<GamesThisWeek events={[CUBS_AT_RED_SOX]} />);

    expect(html).toContain("Each team&#x27;s leading player in this market.");
    expect(html).not.toContain("Each team&#x27;s odds in this market.");
  });

  it("CONTROL: a team field keeps the team name and the team-odds caption", () => {
    const html = renderToStaticMarkup(<GamesThisWeek events={[DODGERS_GIANTS]} />);

    expect(oddsNames(html)).toEqual(["Los Angeles Dodgers"]);
    expect(html).toContain("Each team&#x27;s odds in this market.");
    expect(oddsLabel({ ...DODGERS_GIANTS.linked_teams[0], outcome_is_team: true })).toBe(
      "Los Angeles Dodgers",
    );
    expect(oddsCaption([DODGERS_GIANTS])).toBe("Each team's odds in this market.");
  });
});
