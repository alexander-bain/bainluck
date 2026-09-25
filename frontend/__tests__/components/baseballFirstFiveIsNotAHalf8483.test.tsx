/**
 * #8483 — A BASEBALL GAME PAGE NAMES ITS FIRST-FIVE-INNINGS CARD FOR WHAT IT IS.
 *
 * Seen on production at 390px on 2026-09-24 ~23:15Z (shopper pass 0044):
 * Reds at Braves `/events/15317976` read "1st half runs map" / "1st half runs
 * distribution" over Polymarket's `1st 5 Innings O/U 2.5 … 6.5` ladder, and
 * Rays at Yankees `/events/15317975` (live, Top 1st) read the same. Baseball
 * has no halves.
 *
 * The backend's `half_total` classification is right and stays (#3951 pins
 * "First 5 Innings Total" there); the defect was the card's fixed label.
 *
 * ## What makes this suite non-vacuous
 *
 * Every case renders the REAL `MarketMapSection`. The baseball arm uses the
 * specimen's own rows as `/api/events/15317976/game-markets` served them, and
 * asserts the new heading is PRESENT — a card that vanished would fail it, not
 * pass it. The football control renders the same component over the same kind
 * of rows and requires "1st half" to survive, so a change that renamed every
 * sport's card would fail there. The F5 arm is the second door: that name
 * carries no "1st"/"first" and fell to the "2H" default, so without the
 * `derivePeriod` rule it would render as a "2nd half" card.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";
import { derivePeriod } from "@/lib/marketMapUtils";

function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&#x27;|&#39;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&[a-z]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** The specimen's `half_total` Over rows, `/api/events/15317976/game-markets`, 23:13Z. */
const BRAVES_F5 = [
  [2.5, 0.755],
  [3.5, 0.635],
  [4.5, 0.505],
  [5.5, 0.385],
  [6.5, 0.285],
] as const;

function rows(marketName: (t: number) => string) {
  return BRAVES_F5.map(([threshold, over]) => ({
    threshold,
    over_probability: over,
    probability: null,
    source: "polymarket",
    market_type: "half_total",
    market_name: marketName(threshold),
    outcome_name: "Over",
    is_winner: null,
    resolution_source: null,
    movement: 0,
    period: null,
  }));
}

/**
 * The margin card's door to the same label. NOT the specimen's own
 * `half_spread` rows: those are Polymarket's `1st 5 Innings Spread: Cincinnati
 * Reds (-1.5)` with a bare team as the outcome, which `parseSpreadRungs` does
 * not read, so on production that card never drew (the shopper's text holds
 * only the runs card). These are the rung shape it does read, under the same
 * five-inning market name.
 */
const F5_SPREADS = [
  ["Atlanta Braves -0.5", 0.56],
  ["Atlanta Braves -1.5", 0.41],
  ["Atlanta Braves -2.5", 0.27],
].map(([outcome_name, probability]) => ({
  market_type: "half_spread",
  market_name: "Cincinnati Reds vs. Atlanta Braves: 1st 5 Innings Spread",
  outcome_name,
  probability,
  threshold: null,
  source: "kalshi",
  period: null,
  is_winner: null,
  resolution_source: null,
}));

function render(periodMarkets: unknown[], sportKey: string, home: string, away: string, hAbbr: string, aAbbr: string): string {
  return visibleText(
    renderToStaticMarkup(
      <MarketMapSection
        gameMarkets={
          {
            event_id: 15317976,
            home_team: home,
            away_team: away,
            home_score: 0,
            away_score: 0,
            status: "scheduled",
            player_props: [],
            team_totals: [],
            period_markets: periodMarkets,
            matchups: [],
            other: [],
            pace: null,
            props_script: [],
            spreads: [],
            totals: [],
          } as never
        }
        eventStatus="scheduled"
        homeTeam={home}
        awayTeam={away}
        homeAbbr={hAbbr}
        awayAbbr={aAbbr}
        sportKey={sportKey}
      />
    )
  );
}

const renderBraves = (periodMarkets: unknown[]) =>
  render(periodMarkets, "baseball_mlb", "Atlanta Braves", "Cincinnati Reds", "ATL", "CIN");

describe("#8483 the first-five-innings card on a baseball page", () => {
  it("names the specimen's totals card for five innings, never a half", () => {
    const text = renderBraves(rows((t) => `Cincinnati Reds vs. Atlanta Braves: 1st 5 Innings O/U ${t}`));

    expect(text).toContain("First 5 innings runs map");
    expect(text).toContain("O/U 5");
    expect(text).not.toMatch(/1st half|2nd half/i);
  });

  it("names a five-inning margin card the same way", () => {
    const text = renderBraves(F5_SPREADS);

    expect(text).toContain("First 5 innings margin");
    expect(text).not.toMatch(/1st half|2nd half/i);
  });

  it("files an `F5 Innings` line as the first period, not the 2nd-half default", () => {
    expect(derivePeriod({ market_name: "CIN vs ATL: F5 Innings Total", outcome_name: "Over" })).toBe("1H");

    const text = renderBraves(rows(() => "Cincinnati Reds vs. Atlanta Braves: F5 Innings Total"));

    expect(text).toContain("First 5 innings runs map");
    expect(text).not.toMatch(/2nd half/i);
  });

  it("control: a football page keeps its 1st half card", () => {
    const text = render(
      rows((t) => `SF 49ers vs LA Rams: 1st Half Total ${t}`),
      "americanfootball_nfl",
      "Los Angeles Rams",
      "San Francisco 49ers",
      "LAR",
      "SF"
    );

    expect(text).toContain("1st half points map");
    expect(text).not.toMatch(/innings/i);
  });
});
