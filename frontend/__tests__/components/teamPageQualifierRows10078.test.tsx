/**
 * #10078 — Miami's "College Football Playoff Qualifiers" 83.5% was served by
 * `/api/teams/15264` and never shown (390px, 2026-10-01 16:50Z).
 *
 * The Season Futures list drops tier 1/2/4 rows whenever a championship path
 * exists, and the qualifier board is STORED at tier 4 (#7189) although the path
 * refuses it. The team route now serves `display_tier` (5 for a qualifier, seed
 * or "advance to" board, 3 for an award); the list and the row label read it.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { TeamFutureRow } from "../../components/TeamFutureRow";
import { seasonFuturesRows } from "../../lib/teamSeasonFutures";
import type { ChampionshipPathEntry, TeamFutureItem } from "../../lib/api";

function row(
  market_id: number,
  market_name: string,
  market_tier: number,
  probability: number,
  display_tier?: number
): TeamFutureItem {
  return {
    outcome_id: market_id * 10,
    outcome_name: "Miami (FL)",
    market_id,
    market_name,
    market_tier,
    category: "championship",
    source: "kalshi",
    probability,
    probability_change_24h: null,
    rank: 1,
    total_outcomes: 50,
    resolution_date: null,
    ...(display_tier !== undefined ? { display_tier } : {}),
  };
}

// Miami 15264 as served on 2026-10-01 (display_tier as the route now stamps it).
const MIAMI = [
  row(52756023, "College Football ACC Championship Game Qualifiers", 1, 0.9, 5),
  row(227, "College Football Playoff Qualifiers", 4, 0.835, 5),
  row(57787014, "NCAA Football 2026 ACC Conference: Winner", 2, 0.71, 2),
  row(52755851, "College Football Playoff Quarterfinals Qualifiers", 5, 0.685, 5),
  row(181, "College Football National Championship Winner", 1, 0.095, 1),
];
const PATH: ChampionshipPathEntry[] = [
  { tier: 1, label: "Championship", market_name: "College Football National Championship Winner", market_id: 181, probability: 0.0948, rank: 5, movement: null },
  { tier: 2, label: "Conference", market_name: "NCAA Football 2026 ACC Conference: Winner", market_id: 57787014, probability: 0.71, rank: 1, movement: null },
];

describe("#10078 Season Futures keeps the qualifier boards the path refuses", () => {
  it("lists Playoff Qualifiers and ACC title-game Qualifiers, drops the two path steps", () => {
    const ids = seasonFuturesRows(MIAMI, PATH).map((f) => f.market_id);
    expect(ids).toEqual([52756023, 227, 52755851]);
  });

  it("falls back to the stored tier when the route serves no display_tier", () => {
    const legacy = MIAMI.map(({ display_tier: _drop, ...rest }) => rest);
    expect(seasonFuturesRows(legacy, PATH).map((f) => f.market_id)).toEqual([52755851]);
  });

  it("lists every row when there is no championship path", () => {
    expect(seasonFuturesRows(MIAMI, [])).toHaveLength(MIAMI.length);
  });

  it("labels the tier-4 qualifier row 'Prop', never 'Division'", () => {
    const html = renderToStaticMarkup(<TeamFutureRow item={MIAMI[1]} />);
    expect(html).toContain(">Prop<");
    expect(html).not.toContain("Division");
  });

  it("labels an award stored at tier 1 'Award', never 'Championship'", () => {
    const html = renderToStaticMarkup(
      <TeamFutureRow item={row(15203992, "Protector of the Year Winner?", 1, 0.185, 3)} />
    );
    expect(html).toContain(">Award<");
    expect(html).not.toContain("Championship");
  });
});
