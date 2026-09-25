/**
 * #8721 — A BASEBALL MARGIN MAP DOES NOT PRINT THE RUN LINE AS A MARGIN.
 *
 * The margin map's PRE-GAME tile read `opening_odds.spread` and its live
 * PROJECTION tile read `current_odds.spread`. For baseball both are the
 * sportsbooks' run line, a ±1.5 handicap whatever the matchup — the same
 * number #8617 stopped the Score Differential chart and the Sportsbooks table
 * from reading as a margin (`sportsbookSpreadIsAMargin: false`). This card was
 * the path #8617 did not cover.
 *
 * ═══ THE SPECIMENS (production, 2026-09-25 21:42Z, banked bytes) ═══
 *
 *   | event    | state          | win prob     | opening | current | card printed                         |
 *   |----------|----------------|--------------|---------|---------|--------------------------------------|
 *   | 15318545 | live 0–0       | BOS 51 / 49  | 1.5     | 1.1     | PRE-GAME CHC by 1.5+ · PROJECTION CHC by 1.5+ |
 *   | 15318549 | final BOS 4–3  | 49% pregame  | 1.5     | 0.8     | PRE-GAME CHC by 1.5+ beside FINAL BOS by 1 |
 *   | 15318410 | scheduled      | LAD 73%      | —       | 1.9     | PROJECTION LAD by 1.9+               |
 *
 * The ladder on 15318545's own card priced "Cubs by 2+" at 35%. The served
 * Kalshi reading is Cubs by 0.3.
 *
 * On an unplayed game the Kalshi-rung stand-in is kept only when the rung it
 * picks is at least even money: 15318410's "Dodgers by 3+" is priced at 50%,
 * so that card reads `Projection LAD by 2.5+`, a real median. The same rule on
 * 15318545's ladder ("Cubs by 2+" at 35%) draws no tile.
 *
 * CONTROLS: an NFL card keeps both sportsbook tiles (its spread is a margin),
 * and the baseball ACTUAL / FINAL scoreboard tiles are untouched.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";

import live15318545 from "../fixtures/ux8721_game_markets_15318545.20260925.json";
import done15318549 from "../fixtures/ux8721_game_markets_15318549.20260925.json";
import pre15318410 from "../fixtures/ux8721_game_markets_15318410.20260925.json";

function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&#x27;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&[a-z]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function render(props: Record<string, unknown>): string {
  const p = props as unknown as React.ComponentProps<typeof MarketMapSection>;
  return visibleText(renderToStaticMarkup(<MarketMapSection {...p} />));
}

// Props as `app/events/[id]/page.tsx` builds them, from the served event rows
// read in the same minute as the banked game-markets payloads.
const cubsAtRedSoxLive = {
  gameMarkets: live15318545,
  eventStatus: "live",
  homeTeam: "Boston Red Sox",
  awayTeam: "Chicago Cubs",
  homeAbbr: "BOS",
  awayAbbr: "CHC",
  homeWinProb: 0.508,
  awayWinProb: 0.492,
  homeSpread: 1.1,
  openingHomeSpread: 1.5,
  sportKey: "baseball_mlb",
};

const cubsAtRedSoxFinal = {
  gameMarkets: done15318549,
  eventStatus: "completed",
  homeTeam: "Boston Red Sox",
  awayTeam: "Chicago Cubs",
  homeAbbr: "BOS",
  awayAbbr: "CHC",
  homeWinProb: 0.9379,
  awayWinProb: 0.0621,
  homeSpread: 0.8,
  openingHomeSpread: 1.5,
  sportKey: "baseball_mlb",
};

const dodgersAtGiantsPre = {
  gameMarkets: pre15318410,
  eventStatus: "scheduled",
  homeTeam: "San Francisco Giants",
  awayTeam: "Los Angeles Dodgers",
  homeAbbr: "SF",
  awayAbbr: "LAD",
  homeWinProb: 0.2661,
  awayWinProb: 0.7339,
  homeSpread: 1.9,
  openingHomeSpread: null,
  sportKey: "baseball_mlb",
};

describe("#8721 — the run line never fills a baseball margin tile", () => {
  it("live 15318545: no PRE-GAME or PROJECTION tile from the run line; ACTUAL stays", () => {
    const text = render(cubsAtRedSoxLive);
    // The card drew. Without this every `not` below passes on an empty render.
    expect(text).toContain("Run margin map");
    expect(text).toMatch(/Actual\s+Tied/);
    expect(text).not.toMatch(/Pre-game\s+\w+ by/);
    expect(text).not.toMatch(/Projection\s+\w+ by/);
  });

  it("final 15318549: no PRE-GAME run line beside the FINAL", () => {
    const text = render(cubsAtRedSoxFinal);
    expect(text).toContain("Margin: expected vs final");
    expect(text).toMatch(/Final\s+BOS by 1\b/);
    expect(text).not.toMatch(/Pre-game\s+\w+ by/);
  });

  it("scheduled 15318410: the Projection is the even-money Kalshi rung, not the run-line average", () => {
    const text = render(dodgersAtGiantsPre);
    expect(text).toContain("Run margin map");
    expect(text).not.toMatch(/by 1\.9\+/);
    expect(text).toMatch(/Projection\s+LAD by 2\.5\+/);
  });

  it("scheduled, close game: a long-shot rung is not promoted to a Projection", () => {
    // 15318545's own ladder before first pitch: the rung nearest a coin flip
    // is "Cubs by 2+" at 35%. It is 65% to be false, so it is not a projection.
    const text = render({
      ...cubsAtRedSoxLive,
      eventStatus: "scheduled",
      gameMarkets: { ...live15318545, status: "scheduled", home_score: null, away_score: null },
      openingHomeSpread: null,
    });
    expect(text).toContain("Run margin map");
    expect(text).not.toMatch(/Projection\s+\w+ by/);
  });
});

describe("#8721 controls — a sport whose spread IS a margin keeps both tiles", () => {
  const m = "Buffalo vs Miami";
  const rung = (outcome: string, probability: number) => ({
    market_name: `${m}: Game Spread`,
    outcome_name: outcome,
    threshold: null,
    probability,
    source: "kalshi",
    is_winner: null,
    resolution_source: null,
  });
  const nfl = (status: string) => ({
    gameMarkets: {
      event_id: 1,
      home_team: "Buffalo Bills",
      away_team: "Miami Dolphins",
      home_score: status === "live" ? 7 : null,
      away_score: status === "live" ? 3 : null,
      status,
      player_props: [],
      team_totals: [],
      period_markets: [],
      matchups: [],
      other: [],
      pace: null,
      props_script: [],
      spreads: [rung("Buffalo Bills -3.5", 0.55), rung("Buffalo Bills -6.5", 0.4), rung("Buffalo Bills -9.5", 0.25)],
      totals: [],
    },
    eventStatus: status,
    homeTeam: "Buffalo Bills",
    awayTeam: "Miami Dolphins",
    homeAbbr: "BUF",
    awayAbbr: "MIA",
    homeWinProb: 0.7,
    awayWinProb: 0.3,
    sportKey: "americanfootball_nfl",
  });

  it("NFL live: PRE-GAME from the opening line and PROJECTION from the current one", () => {
    const text = render({ ...nfl("live"), openingHomeSpread: -3.5, homeSpread: -6.5 });
    expect(text).toMatch(/Pre-game\s+BUF by 3\.5\+/);
    expect(text).toMatch(/Projection\s+BUF by 6\.5\+/);
  });

  it("NFL scheduled with no sportsbook line: the rung stand-in is unchanged below even money", () => {
    // The nearest-to-even rung here is 40%; the #8721 even-money floor is
    // scoped to baseball and must not strip a points sport's reading.
    const g = nfl("scheduled");
    g.gameMarkets.spreads = [rung("Buffalo Bills -3.5", 0.4), rung("Buffalo Bills -6.5", 0.25)];
    const text = render({ ...g, openingHomeSpread: null, homeSpread: null });
    expect(text).toMatch(/Projection\s+BUF by 3\.5\+/);
  });
});
