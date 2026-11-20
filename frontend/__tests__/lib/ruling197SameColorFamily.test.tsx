/**
 * Ruling 197 (Alex, #12538) — Two teams in the same colour family on the website:
 *
 * When both teams' main colours share a chromatic hue family (in addition to
 * near-identical collisions), the home team keeps its main colour and the away
 * team switches to its own `secondary_color` if we hold one that passes the
 * card contrast floor (3:1), is distinct from home, and is outside home's hue
 * family — otherwise away switches to slate grey (`#64748B`).
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  SLATE_TEAM_FALLBACK,
  colorHueFamily,
  resolveMatchupTeamColors,
  sameColorFamily,
  teamColorStyle,
} from "@/lib/teamColors";
import { probabilityBarPair } from "@/lib/probabilityBarPair";
import { projectedTeamStrokes } from "@/lib/teamLineStrokes";
import EventHeroProbabilityPair from "@/components/EventHeroProbabilityPair";
import GamePlayCard from "@/components/GamePlayCard";
import SeriesProbability from "@/components/SeriesProbability";

const DUKE = { primary: "#00539b", secondary: "#ffffff" };
const KANSAS = { primary: "#0051ba", secondary: "#e8000d" };
const GONZAGA = { primary: "#041e42", secondary: "#c8102e" };
const KENTUCKY = { primary: "#0033a0", secondary: "#ffffff" };
const UNC = { primary: "#7bafd4", secondary: "#13294b" };
const ALABAMA = { primary: "#9e1b32", secondary: "#ffffff" };

describe("Ruling 197 — same colour family switches away to secondary_color or slate grey", () => {
  test("Kansas at Duke: two blues -> Duke keeps #00539b, Kansas switches to crimson #e8000d", () => {
    expect(sameColorFamily(KANSAS.primary, DUKE.primary)).toBe(true);
    expect(
      resolveMatchupTeamColors({
        homePrimary: DUKE.primary,
        awayPrimary: KANSAS.primary,
        homeSecondary: DUKE.secondary,
        awaySecondary: KANSAS.secondary,
      }),
    ).toEqual({
      home: DUKE.primary,
      away: KANSAS.secondary,
      awaySwitched: true,
    });

    expect(
      probabilityBarPair(KANSAS.primary, DUKE.primary, 1, KANSAS.secondary),
    ).toEqual({
      away: KANSAS.secondary,
      home: DUKE.primary,
    });

    expect(
      projectedTeamStrokes(DUKE.primary, KANSAS.primary, KANSAS.secondary),
    ).toEqual({
      home: DUKE.primary,
      away: KANSAS.secondary,
    });
  });

  test("Gonzaga at Duke: dark navy (#041e42) vs Duke blue (#00539b) -> Gonzaga switches to crimson #c8102e", () => {
    expect(colorHueFamily(GONZAGA.primary)).toBe("blue");
    expect(colorHueFamily(DUKE.primary)).toBe("blue");
    expect(sameColorFamily(GONZAGA.primary, DUKE.primary)).toBe(true);

    expect(
      resolveMatchupTeamColors({
        homePrimary: DUKE.primary,
        awayPrimary: GONZAGA.primary,
        homeSecondary: DUKE.secondary,
        awaySecondary: GONZAGA.secondary,
      }),
    ).toEqual({
      home: DUKE.primary,
      away: GONZAGA.secondary,
      awaySwitched: true,
    });

    expect(
      probabilityBarPair(GONZAGA.primary, DUKE.primary, 1, GONZAGA.secondary),
    ).toEqual({
      away: GONZAGA.secondary,
      home: DUKE.primary,
    });
  });

  test("Kentucky at Duke: away secondary is #ffffff (fails 3:1 floor) -> away switches to slate grey #64748B", () => {
    expect(
      resolveMatchupTeamColors({
        homePrimary: DUKE.primary,
        awayPrimary: KENTUCKY.primary,
        awaySecondary: KENTUCKY.secondary,
      }),
    ).toEqual({
      home: DUKE.primary,
      away: SLATE_TEAM_FALLBACK,
      awaySwitched: true,
    });

    expect(
      probabilityBarPair(KENTUCKY.primary, DUKE.primary, 1, KENTUCKY.secondary),
    ).toEqual({
      away: SLATE_TEAM_FALLBACK,
      home: DUKE.primary,
    });
  });

  test("missing secondary_color or same-hue secondary_color falls back to slate grey #64748B", () => {
    expect(
      resolveMatchupTeamColors({
        homePrimary: DUKE.primary,
        awayPrimary: KENTUCKY.primary,
        awaySecondary: null,
      }),
    ).toEqual({
      home: DUKE.primary,
      away: SLATE_TEAM_FALLBACK,
      awaySwitched: true,
    });

    // UNC's secondary is navy (#13294b), still in the blue family -> falls to slate grey
    expect(
      resolveMatchupTeamColors({
        homePrimary: DUKE.primary,
        awayPrimary: "#1d4ed8",
        awaySecondary: UNC.secondary,
      }),
    ).toEqual({
      home: DUKE.primary,
      away: SLATE_TEAM_FALLBACK,
      awaySwitched: true,
    });
  });

  test("CONTROL: Alabama at Duke (red vs blue) does not change either team's colour", () => {
    expect(sameColorFamily(ALABAMA.primary, DUKE.primary)).toBe(false);
    expect(
      resolveMatchupTeamColors({
        homePrimary: DUKE.primary,
        awayPrimary: ALABAMA.primary,
        homeSecondary: DUKE.secondary,
        awaySecondary: ALABAMA.secondary,
      }),
    ).toEqual({
      home: DUKE.primary,
      away: ALABAMA.primary,
      awaySwitched: false,
    });

    expect(
      probabilityBarPair(ALABAMA.primary, DUKE.primary, 1, ALABAMA.secondary),
    ).toEqual({
      away: ALABAMA.primary,
      home: DUKE.primary,
    });
  });

  test("teamColorStyle CSS variables carry Ruling 197's switched away colour for card badges", () => {
    const vars = teamColorStyle(
      DUKE.primary,
      KANSAS.primary,
      DUKE.secondary,
      KANSAS.secondary,
    ) as Record<string, string>;
    expect(vars["--team-home-primary"]).toBe("0 83 155");
    expect(vars["--team-away-primary"]).toBe("232 0 13");
  });

  test("event detail surfaces (hero pair, play readout, series bar) paint away in secondary_color or slate grey", () => {
    const heroKansas = renderToStaticMarkup(
      <EventHeroProbabilityPair
        homeProb={0.58}
        awayProb={0.42}
        homePct={58}
        awayPct={42}
        homeColor={DUKE.primary}
        awayColor={KANSAS.primary}
        awaySecondaryColor={KANSAS.secondary}
      />,
    );
    expect(heroKansas).toContain(`color:${DUKE.primary}`);
    expect(heroKansas).toContain(`color:${KANSAS.secondary}`);
    expect(heroKansas).not.toContain(`color:${KANSAS.primary}`);

    const heroKentucky = renderToStaticMarkup(
      <EventHeroProbabilityPair
        homeProb={0.58}
        awayProb={0.42}
        homePct={58}
        awayPct={42}
        homeColor={DUKE.primary}
        awayColor={KENTUCKY.primary}
        awaySecondaryColor={KENTUCKY.secondary}
      />,
    );
    expect(heroKentucky).toContain(`color:${DUKE.primary}`);
    expect(heroKentucky).toContain(`color:${SLATE_TEAM_FALLBACK}`);

    const playHtml = renderToStaticMarkup(
      <GamePlayCard
        activePoint={{
          timestamp: "2026-11-15T01:00:00Z",
          homeProb: 0.58,
          awayProb: 0.42,
          homeScore: 71,
          awayScore: 68,
        }}
        homeTeam="Duke Blue Devils"
        awayTeam="Kansas Jayhawks"
        homeTeamColor={DUKE.primary}
        awayTeamColor={KANSAS.primary}
        awayTeamSecondaryColor={KANSAS.secondary}
      />,
    );
    expect(playHtml).toContain(`color:${DUKE.primary}`);
    expect(playHtml).toContain(`color:${KANSAS.secondary}`);

    const seriesHtml = renderToStaticMarkup(
      <SeriesProbability
        homeWinProb={0.58}
        homeSeriesWins={2}
        awaySeriesWins={1}
        homeTeam="Duke Blue Devils"
        awayTeam="Gonzaga Bulldogs"
        homeTeamColor={DUKE.primary}
        awayTeamColor={GONZAGA.primary}
        awayTeamSecondaryColor={GONZAGA.secondary}
      />,
    );
    expect(seriesHtml).toContain(`color:${DUKE.primary}`);
    expect(seriesHtml).toContain(`color:${GONZAGA.secondary}`);
  });
});
