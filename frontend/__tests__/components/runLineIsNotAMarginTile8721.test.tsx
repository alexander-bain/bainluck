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

/**
 * #8721, one card lower — the FIRST 5 INNINGS margin card.
 *
 * Found by native on the iPhone twin (PR #8775): before first pitch the half
 * card names the rung nearest 50% whatever its price. Specimen, production
 * 2026-09-26 03:25Z, `/events/15318868` (Dodgers @ Giants, scheduled, LAD
 * 74.5%): Kalshi's First 5 ladder is `San Francisco -1.5 first 5 innings` 24%
 * and `-2.5` 18%, so the nearest-to-even rung is a 24% long shot and the
 * iPhone read `PRE-GAME SF by 1.5+`.
 *
 * ⚠️ LATENT ON WEB, NOT VISIBLE. Read on production the same minute, the web
 * page draws no First 5 margin card for any MLB game, for two reasons outside
 * this card: Kalshi's "First 5 Spread" is classified as a full-game `spread`
 * (and `isFullGameSpread` drops it; re-filed as `half_spread` its outcome
 * parses as a 5-run line, because the parser takes the LAST number and that is
 * the "5" in "first 5 innings"), and Polymarket's `1st 5 Innings Spread: X (-1.5)`
 * reaches `half_spread` but the #8739 reader is anchored at `^Spread:`. The
 * floor is here so the card is right the day either path opens.
 *
 * So the rows below are the banked First 5 prices (24% / 18%) in the outcome
 * spelling this parser reads today — Kalshi's full-game "wins by over N runs" —
 * filed as `half_spread`. The rule is the full-game rail's: for baseball a rung
 * stands in only before first pitch and only at even money or better.
 */
import sched15318868 from "../fixtures/ux8721_game_markets_15318868.20260926T0325Z.json";

type Row = Record<string, unknown> & { market_name: string; outcome_name: string; probability: number };

const f5Rung = (outcome: string, probability: number): Row => ({
  market_name: "Los Angeles Dodgers vs San Francisco: First 5 Spread",
  outcome_name: outcome,
  threshold: null,
  probability,
  source: "kalshi",
  is_winner: null,
  resolution_source: null,
});

function withFirstFiveHalfCard(extra: Row[] = [], status = "scheduled") {
  // The banked prices the rows below carry.
  const banked = (sched15318868.spreads as Row[])
    .filter((r) => /First 5 Spread/.test(r.market_name))
    .map((r) => [r.outcome_name, r.probability]);
  expect(banked).toEqual([
    ["San Francisco -1.5 first 5 innings", 0.24],
    ["San Francisco -2.5 first 5 innings", 0.18],
  ]);
  const f5 = [
    f5Rung("San Francisco wins by over 1.5 runs", 0.24),
    f5Rung("San Francisco wins by over 2.5 runs", 0.18),
    ...extra,
  ];
  return {
    gameMarkets: {
      ...sched15318868,
      status,
      home_score: status === "live" ? 0 : null,
      away_score: status === "live" ? 2 : null,
      period_markets: [
        ...sched15318868.period_markets,
        ...f5.map((r) => ({ ...r, market_type: "half_spread", period: "1H" })),
      ],
    },
    eventStatus: status,
    homeTeam: "San Francisco Giants",
    awayTeam: "Los Angeles Dodgers",
    homeAbbr: "SF",
    awayAbbr: "LAD",
    homeWinProb: 0.255,
    awayWinProb: 0.745,
    homeSpread: 1.9,
    openingHomeSpread: null,
    sportKey: "baseball_mlb",
  };
}

const ladEvenMoney = f5Rung("Los Angeles Dodgers wins by over 1.5 runs", 0.55);

describe("#8721 — the First 5 innings margin card never names a long shot", () => {
  it("scheduled 15318868: no `Projection SF by 1.5+` off a 24% rung; the card still draws", () => {
    const text = render(withFirstFiveHalfCard());
    expect(text).toContain("First 5 innings margin");
    expect(text).toMatch(/SF by 1\.5\+\s+24%/); // the ladder row is untouched
    expect(text).not.toMatch(/(Projection|Pre-game)\s+SF by/);
  });

  it("scheduled, a rung at even money or better still reads as the Projection", () => {
    const text = render(withFirstFiveHalfCard([ladEvenMoney]));
    expect(text).toMatch(/Projection\s+LAD by 1\.5\+/);
  });

  it("live: a baseball First 5 rung is never a Projection, even at even money", () => {
    const text = render(withFirstFiveHalfCard([ladEvenMoney], "live"));
    expect(text).toContain("First 5 innings margin");
    expect(text).toMatch(/LAD by 1\.5\+\s+55%/);
    expect(text).not.toMatch(/(Projection|Pre-game)\s+\w+ by 1\.5/);
  });
});

describe("#8721 half-card control — a points sport keeps its nearest-to-even rung", () => {
  it("NBA 1st half, scheduled: `Projection` from a 40% rung is unchanged", () => {
    const m = "Celtics vs Knicks: 1st Half Spread";
    const rung = (outcome: string, probability: number) => ({
      market_name: m,
      outcome_name: outcome,
      threshold: null,
      probability,
      source: "kalshi",
      market_type: "half_spread",
      period: "1H",
      is_winner: null,
      resolution_source: null,
    });
    const text = render({
      gameMarkets: {
        event_id: 2,
        home_team: "Boston Celtics",
        away_team: "New York Knicks",
        home_score: null,
        away_score: null,
        status: "scheduled",
        player_props: [],
        team_totals: [],
        period_markets: [rung("Boston Celtics -2.5", 0.4), rung("Boston Celtics -5.5", 0.25)],
        matchups: [],
        other: [],
        pace: null,
        props_script: [],
        spreads: [],
        totals: [],
      },
      eventStatus: "scheduled",
      homeTeam: "Boston Celtics",
      awayTeam: "New York Knicks",
      homeAbbr: "BOS",
      awayAbbr: "NYK",
      homeWinProb: 0.6,
      awayWinProb: 0.4,
      sportKey: "basketball_nba",
    });
    expect(text).toContain("1st half margin");
    expect(text).toMatch(/Projection\s+BOS by 2\.5\+/);
  });
});
