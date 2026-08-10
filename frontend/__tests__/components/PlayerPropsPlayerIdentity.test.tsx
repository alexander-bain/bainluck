// #1639 — 17 players must not render as one card wearing one player's face.
//
// `parsePlayerName` read the player and stat from `market_name`. MLB puts the
// MATCHUP there ("Tampa Bay Rays vs. Seattle Mariners - Player Props") and the
// player in `outcome_name` ("Victor Mesa Jr.: Home Runs O/U 0.5"), so on
// production event 15191121 all 25 rows hashed to one key: ONE card, titled with
// the matchup, wearing Cole Young's headshot for all 17 players, under a stat
// labelled "Prop".
//
// Third instance of the same class on this endpoint after #1626 and #1627 — the
// bytes were already on the wire and the client threw them away.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import PlayerPropsDashboard from "../../components/PlayerPropsDashboard";
import type { GameMarketsResponse } from "../../lib/api";

const MATCHUP = "Tampa Bay Rays vs. Seattle Mariners - Player Props";

/** Production shape, event 15191121. */
function mlbRow(outcome: string, threshold: number, headshot?: string, team?: "home" | "away") {
  return {
    market_name: MATCHUP,
    outcome_name: outcome,
    threshold,
    over_probability: 0.5,
    source: "polymarket",
    movement: null,
    actual: null,
    hit: null,
    is_winner: false,
    resolution_source: null,
    ...(headshot ? { player_headshot: headshot } : {}),
    ...(team ? { player_team: team } : {}),
  };
}

const ROWS = [
  mlbRow("Victor Mesa Jr.: Home Runs O/U 0.5", 0.5, "https://img.mlbstatic.com/people/1/headshot.png", "home"),
  mlbRow("Cole Young: Home Runs O/U 0.5", 0.5, "https://img.mlbstatic.com/people/2/headshot.png", "home"),
  mlbRow("Cedric Mullins: Home Runs O/U 0.5", 0.5, "https://img.mlbstatic.com/people/3/headshot.png", "away"),
  mlbRow("George Kirby: Strikeouts O/U 5.5", 5.5, "https://img.mlbstatic.com/people/4/headshot.png", "away"),
];

function render(rows: Array<Record<string, unknown>>, status = "live") {
  return renderToStaticMarkup(
    <PlayerPropsDashboard
      data={{ player_props: rows, other: [] } as unknown as GameMarketsResponse}
      eventStatus={status}
      homeTeam="Tampa Bay Rays"
      awayTeam="Seattle Mariners"
      boxScore={null}
    />,
  );
}

function cardTitles(html: string): string[] {
  return (html.match(/font-semibold truncate">([^<]*)</g) ?? []).map((t) =>
    t.replace(/.*">/, "").replace(/<$/, ""),
  );
}

describe("every player gets their own card", () => {
  const html = render(ROWS);

  it("renders one card per player, not one card for the matchup", () => {
    expect(cardTitles(html).sort()).toEqual(
      ["Cedric Mullins", "Cole Young", "George Kirby", "Victor Mesa Jr."],
    );
  });

  it("never titles a card with the matchup", () => {
    expect(html).not.toContain(MATCHUP);
  });

  it("gives each player their OWN headshot", () => {
    const shots = html.match(/people\/(\d+)\/headshot/g) ?? [];
    expect(new Set(shots).size).toBe(4);
  });

  it("names the statistic instead of labelling everything 'Prop'", () => {
    expect(html).toContain("Home Runs");
    expect(html).toContain("Strikeouts");
    expect(html).not.toMatch(/tracking-wide text-text-secondary">Prop</);
  });
});

// The other direction (gotcha #43): the outcome parser is consulted ONLY when the
// existing market-name parse finds no statistic, so rows that parse today must be
// untouched.
describe("market-name-shaped rows keep their existing parse", () => {
  it("still reads the player from the outcome when market_name names the stat", () => {
    const rows = [
      {
        market_name: "Lakers vs Celtics: Points",
        outcome_name: "LeBron James: Over 25.5",
        threshold: 25.5,
        over_probability: 0.5,
        source: "kalshi",
        movement: null,
      },
    ];
    const html = render(rows);
    expect(cardTitles(html)).toEqual(["LeBron James"]);
    expect(html).toContain("Points");
  });

  /**
   * KNOWN RESIDUAL of #1639, asserted so it is recorded rather than assumed
   * fixed. An outcome that is a bare name carries no `O/U` statistic, so
   * `parsePropLabel` returns null and the row keeps the old market-name parse —
   * still collapsing under a matchup title.
   *
   * This fix covers the `Player: Statistic O/U Threshold` shape, which is what
   * every measured Polymarket MLB row uses. Bare-name labels need a different
   * signal (the row's own `player_headshot`/`player_team`, or a backend-typed
   * player field) and are deliberately out of scope here. Locking the current
   * behaviour in a test means the day it changes, it changes on purpose.
   */
  it("does NOT yet rescue a bare-name label — recorded, not fixed", () => {
    const rows = [
      {
        market_name: "Braves vs Yankees - Player Props",
        outcome_name: "Aaron Judge",
        threshold: 0.5,
        over_probability: 0.5,
        source: "kalshi",
        movement: null,
      },
    ];
    expect(cardTitles(render(rows))).toEqual(["Braves vs Yankees - Player Props"]);
  });
});
