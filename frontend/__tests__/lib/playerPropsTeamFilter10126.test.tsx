// #10126 — a card whose bucket is keyed to an authoritative side SHOWS under that
// side, whichever of its rows arrived first.
//
// Production specimen: /events/14780550 (Steelers at Browns). Deshaun Watson has 32
// rows tagged `player_team: "home"` and 11 with no tag. The untagged rows already
// joined his home bucket (one known side → join it), but the card's display `team`
// was copied from whichever row CREATED the bucket. An untagged row read either
// "unknown" (a "Deshaun Watson: …" market names no team) or "away" (a "Pittsburgh vs
// Cleveland" matchup string, where the first team named counts as the visitor). The
// dashboard filter keeps an "unknown" card under BOTH teams, so Watson appeared
// under the Steelers.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import { groupPlayerProps, type PlayerPropRow } from "../../lib/playerPropsGrouping";
import PlayerPropsDashboard from "../../components/PlayerPropsDashboard";

const HOME = "Cleveland Browns";
const AWAY = "Pittsburgh Steelers";

function row(over: Partial<PlayerPropRow>): PlayerPropRow {
  return {
    market_name: "Deshaun Watson: Passing Yards O/U 249.5",
    outcome_name: "Over",
    threshold: 249.5,
    over_probability: 0.45,
    movement: null,
    source: "polymarket",
    actual: null,
    hit: null,
    is_winner: null,
    resolution_source: null,
    player_team: null,
    ...over,
  };
}

/** Untagged, and its market names no team → the old card read "unknown". */
const untaggedNoTeam = row({});
/** Untagged, on a matchup market → the old card read "away" (first-named team). */
const untaggedMatchup = row({
  market_name: "Pittsburgh vs Cleveland: Rushing Yards",
  outcome_name: "Deshaun Watson: 15+",
  threshold: 15,
  over_probability: 0.6,
  source: "kalshi",
});
const taggedHome = row({
  market_name: "Pittsburgh vs Cleveland: Passing Yards",
  outcome_name: "Deshaun Watson: 200+",
  threshold: 200,
  over_probability: 0.7,
  source: "kalshi",
  player_team: "home",
});

function group(rows: PlayerPropRow[]) {
  return groupPlayerProps({
    playerProps: rows,
    other: [],
    homeTeam: HOME,
    awayTeam: AWAY,
    homeColor: "#311D00",
    awayColor: "#FFB612",
    boxScorePlayers: null,
  });
}

describe("#10126 — the card's team is its bucket's authoritative side", () => {
  const orders: Array<[string, PlayerPropRow[]]> = [
    ["untagged (no team) row first", [untaggedNoTeam, taggedHome]],
    ["untagged (matchup) row first", [untaggedMatchup, taggedHome]],
    ["tagged row first", [taggedHome, untaggedNoTeam, untaggedMatchup]],
    ["tagged row last", [untaggedMatchup, untaggedNoTeam, taggedHome]],
  ];
  for (const [label, rows] of orders) {
    it(`${label}: ONE Watson card, on the home side`, () => {
      const { players } = group(rows);
      const watson = players.filter((p) => p.name === "Deshaun Watson");
      expect(watson).toHaveLength(1);
      expect(watson[0].team).toBe("home");
      // The dashboard's filter: `p.team === teamFilter || p.team === "unknown"`.
      const underAway = watson.filter((p) => p.team === "away" || p.team === "unknown");
      expect(underAway).toHaveLength(0);
    });
  }

  it("control: a player with NO tagged row keeps its detected side (unchanged)", () => {
    const { players } = group([untaggedMatchup]);
    expect(players).toHaveLength(1);
    expect(players[0].team).toBe("away");
    const { players: noTeam } = group([untaggedNoTeam]);
    expect(noTeam[0].team).toBe("unknown");
  });

  it("control: same name on BOTH tagged sides stays two cards, one per side", () => {
    const { players } = group([
      untaggedNoTeam,
      taggedHome,
      row({ ...taggedHome, threshold: 225, outcome_name: "Deshaun Watson: 225+", player_team: "away" }),
    ]);
    const sides = players.filter((p) => p.name === "Deshaun Watson").map((p) => p.team).sort();
    // The untagged row stands alone ("unknown"), as it did before #10126.
    expect(sides).toEqual(["away", "home", "unknown"]);
  });

  it("SSR: the rendered Watson card is labelled Home, not blank", () => {
    const html = renderToStaticMarkup(
      React.createElement(PlayerPropsDashboard, {
        data: { player_props: [untaggedMatchup, taggedHome], other: [] } as never,
        eventStatus: "scheduled",
        homeTeam: HOME,
        awayTeam: AWAY,
        homeColor: "#311D00",
        awayColor: "#FFB612",
      } as never),
    );
    expect(html).toContain("Deshaun Watson");
    expect(html).toMatch(/>Home</);
  });
});
