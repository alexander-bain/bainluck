/**
 * #10159 — the settled hero says "Upset" only when the winner opened beneath
 * the close-matchup line the game's cards already hold (#2753).
 *
 * The specimen, production 2026-10-02 03:47Z, 390px: `/events/14780550`,
 * Steelers 24 @ Browns 27 (TNF). Served `prematch_odds` (Kalshi) Browns 0.405 /
 * Steelers 0.595, printed 40 / 60. The hero read "Browns · WON · Upset · 40%
 * pregame" in amber, while the Sports and Discover cards one tap away called it
 * no upset (`winner_opened_as_a_real_underdog`: winner share < 0.40).
 *
 * #9490's comparison stays: winner priced below the loser on the printed pair.
 * This adds the band on the winner's two-way SHARE of that pair, the server's
 * rule. Every case goes through `settledPregameMark` into the hero — the page's
 * own path — and reads the one pregame span.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import SettledOutcomeHero, { CLOSE_MATCHUP_MIN, pregameUpset } from "@/components/event/SettledOutcomeHero";
import type { SettledOutcome } from "@/lib/eventOutcome";
import { settledPregameMark } from "@/lib/settledPregameMark";
import { readFileSync } from "fs";
import { join } from "path";

type Prematch = Parameters<typeof settledPregameMark>[0]["prematchOdds"];

function line(winnerSide: "home" | "away", prematch: Prematch, sport: string): string {
  const mark = settledPregameMark({
    winnerSide,
    prematchOdds: prematch,
    openingHomeProb: null,
    openingAwayProb: null,
    sport,
  });
  const html = renderToStaticMarkup(
    <SettledOutcomeHero
      outcome={{ winnerName: "W", winnerSide, authority: "score", resultLine: null, resultKind: "score", resultExplanation: null } as unknown as SettledOutcome}
      hasNumericScore
      winnerPregameProb={mark?.probability ?? null}
      winnerPregamePercent={mark?.percent ?? null}
      winnerPregameSource={mark?.source ?? null}
      winnerPregameLabel={mark?.label ?? null}
      loserPregameProb={mark?.loserProbability ?? null}
      loserPregamePercent={mark?.loserPercent ?? null}
    />,
  );
  const at = html.indexOf('data-testid="event-hero-pregame"');
  if (at === -1) return "";
  const open = html.indexOf(">", at) + 1;
  return html.slice(open, html.indexOf("</span>", open)).split("<!-- -->").join("");
}

const pair = (home: number, away: number, homePct: number, awayPct: number): Prematch => ({
  home_probability: home,
  away_probability: away,
  home_rendered_percent: homePct,
  away_rendered_percent: awayPct,
  source: "kalshi",
});

describe("#10159 — a close matchup's underdog winning is not an upset", () => {
  it("THE SPECIMEN 14780550: Browns 0.405 over Steelers 0.595 reads '40% pregame'", () => {
    expect(line("home", pair(0.405, 0.595, 40, 60), "americanfootball_nfl")).toBe("40% pregame");
  });

  it("a 49 / 51 win is not an upset (the Cubs / Red Sox case #2753 removed from the cards)", () => {
    expect(line("away", pair(0.51, 0.49, 51, 49), "baseball_mlb")).toBe("49% pregame");
  });

  it("a draw-priced board is judged on its two-way split: 34 over 43 is 44 / 56, no upset", () => {
    expect(line("away", pair(0.425, 0.335, 43, 34), "soccer_uefa_nations_league")).toBe("34% pregame");
  });
});

describe("#10159 — real upsets and #9490 are unchanged", () => {
  it("a 27% winner still reads Upset", () => {
    expect(line("away", pair(0.73, 0.27, 73, 27), "americanfootball_nfl")).toBe("Upset · 27% pregame");
  });

  it("39 over 61 is beneath the line: Upset", () => {
    expect(line("away", pair(0.61, 0.39, 61, 39), "baseball_mlb")).toBe("Upset · 39% pregame");
  });

  it("#9490's three-way favourite (Italy 0.395 over Turkey 0.325) is still no upset", () => {
    expect(line("away", pair(0.325, 0.395, 33, 40), "soccer_uefa_nations_league")).toBe("40% pregame");
  });

  it("the band is the server's number, at its edge on the printed pair", () => {
    expect(CLOSE_MATCHUP_MIN).toBe(0.4);
    expect(pregameUpset({ winnerProb: 0.4, winnerPercent: 40, loserProb: 0.6, loserPercent: 60 })).toBe(false);
    expect(pregameUpset({ winnerProb: 0.39, winnerPercent: 39, loserProb: 0.61, loserPercent: 61 })).toBe(true);
    const server = readFileSync(join(__dirname, "../../backend/app/utils/highlights.py"), "utf8");
    expect(server).toMatch(/^CLOSE_MATCHUP_MIN = 0\.40$/m);
  });
});
