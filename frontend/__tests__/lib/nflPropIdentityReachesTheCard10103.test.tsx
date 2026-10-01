/**
 * #10103 — the props card shows an NFL player in the team and picture of the
 * game he played in, not today's roster.
 *
 * No frontend source changes: the card has always read `player_team` and
 * `player_headshot`. This test proves the backend's new values reach it.
 * The rows below are not hand-written. `backend/tests/fixtures/
 * nfl_prop_identity_payload_10103.json` is the exact `player_props` subset
 * the backend test produces end to end: the source-retained ESPN summary for
 * Bills @ Texans (14780141), then `get_event_context`, then the settled box
 * writer, then `GET /api/events/14780141/game-markets`. The backend test
 * asserts equality with the same file, so neither side can drift alone.
 *
 * In that fixture today's roster (REPRESENTATIVE) lists David Montgomery on
 * Buffalo with another picture, as after a post-game trade. He played this game
 * for Houston, and that is what the card must say.
 */
import fs from "node:fs";
import path from "node:path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import PlayerPropsDashboard from "../../components/PlayerPropsDashboard";
import type { GameMarketsResponse } from "../../lib/api";
import { groupPlayerProps, type PlayerPropRow } from "../../lib/playerPropsGrouping";

const GOLDEN = JSON.parse(
  fs.readFileSync(
    path.join(__dirname, "../../../backend/tests/fixtures/nfl_prop_identity_payload_10103.json"),
    "utf8",
  ),
) as { home_team: string; away_team: string; player_props: PlayerPropRow[] };

const HOME_COLOR = "#03202F"; // any two distinct colours; only which one matters
const AWAY_COLOR = "#00338D";

function grouped() {
  return groupPlayerProps({
    playerProps: GOLDEN.player_props,
    homeTeam: GOLDEN.home_team,
    awayTeam: GOLDEN.away_team,
    homeColor: HOME_COLOR,
    awayColor: AWAY_COLOR,
  });
}

describe("#10103 the game's own athlete identity reaches the props card", () => {
  it("draws Montgomery as a Texan with his own picture, against today's roster", () => {
    const { players, dropped } = grouped();
    expect(dropped).toEqual([]);
    const montgomery = players.find((p) => p.name === "David Montgomery");
    expect(montgomery).toBeDefined();
    expect(montgomery!.team).toBe("home");
    expect(montgomery!.color).toBe(HOME_COLOR);
    expect(montgomery!.headshot).toBe(
      "https://a.espncdn.com/i/headshots/nfl/players/full/4035538.png",
    );
  });

  it("keeps each quarterback on his own side of this game", () => {
    const { players } = grouped();
    const side = Object.fromEntries(players.map((p) => [p.name, p.team]));
    expect(side["C.J. Stroud"]).toBe("home");
    expect(side["Josh Allen"]).toBe("away");
  });

  it("CONTROL: a subject ESPN did not box keeps the roster answer it had", () => {
    const hawes = grouped().players.find((p) => p.name === "Jackson Hawes");
    expect(hawes?.team).toBe("away");
    expect(hawes?.headshot).toBe("https://example.invalid/roster-today/hawes.png");
  });

  it("the rendered card carries the game's picture, never the transferred one", () => {
    const html = renderToStaticMarkup(
      <PlayerPropsDashboard
        data={{ player_props: GOLDEN.player_props, other: [] } as unknown as GameMarketsResponse}
        eventStatus="completed"
        homeTeam={GOLDEN.home_team}
        awayTeam={GOLDEN.away_team}
        homeColor={HOME_COLOR}
        awayColor={AWAY_COLOR}
      />,
    );
    expect(html).toContain("players/full/4035538.png");
    expect(html).not.toContain("roster-today/montgomery.png");
  });
});
