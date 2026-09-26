/**
 * #8934 — THE HALF MARGIN TOKEN DRAWS THE TEAM'S LOGO, AND A TEXT FALLBACK
 * STAYS INSIDE ITS CIRCLE.
 *
 * Seen on production at 390px on 2026-09-26 2:21 PM PDT, `/events/15313790`
 * — Ole Miss @ Florida, LIVE 17-3 with 1:18 left in the 2nd quarter. The
 * "2nd half margin" card's projection token printed the word `Rebels` in its
 * 26px round marker at 8px, and the letters ran out through the white ring
 * on both sides. The full-game margin map on the same page drew the Gators
 * logo in the same token: the half card never passed a logo at all, so it
 * always fell back to text, and since #8585 Ole Miss's text is its short name
 * (the ESPN code `MISS` reads as a word).
 *
 * Every case renders the REAL `MarketMapSection` over a live game whose only
 * margin card is the 2nd half, so the one projection token on the page is the
 * one the reader saw. The arms differ only in whether logos are served.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";
import { markerFallbackFontSize } from "@/components/MarketMap";

const HOME = "Florida Gators";
const AWAY = "Ole Miss Rebels";
const HOME_LOGO = "https://a.espncdn.com/i/teamlogos/ncaa/500/57.png";
const AWAY_LOGO = "https://a.espncdn.com/i/teamlogos/ncaa/500/145.png";

function spread(outcome_name: string, probability: number, threshold: number) {
  return {
    market_name: "Ole Miss at Florida: 2nd Half Spread",
    outcome_name,
    probability,
    threshold,
    point: null,
    market_type: "half_spread",
    period: "2H",
    source: "kalshi",
    over_probability: null,
    is_winner: null,
    resolution_source: null,
    movement: 0,
  };
}

/** A quoting 2H ladder whose rung nearest a coin flip favours the AWAY side. */
const SECOND_HALF = [
  spread("Ole Miss wins the 2H by more than 2.5 points", 0.5, 2.5),
  spread("Ole Miss wins the 2H by more than 6.5 points", 0.36, 6.5),
  spread("Florida wins the 2H by more than 2.5 points", 0.3, 2.5),
];

function render(logos: boolean): string {
  return renderToStaticMarkup(
    <MarketMapSection
      gameMarkets={
        {
          event_id: 15313790,
          home_team: HOME,
          away_team: AWAY,
          home_score: 17,
          away_score: 3,
          status: "live",
          player_props: [],
          team_totals: [],
          period_markets: SECOND_HALF,
          matchups: [],
          other: [],
          pace: null,
          props_script: [],
          spreads: [],
          totals: [],
        } as never
      }
      eventStatus="live"
      homeTeam={HOME}
      awayTeam={AWAY}
      homeAbbr="FLA"
      awayAbbr="MISS"
      homeLogo={logos ? HOME_LOGO : undefined}
      awayLogo={logos ? AWAY_LOGO : undefined}
      sportKey="americanfootball_ncaaf"
    />
  );
}

/** The markup of the one projection token, asserted to BE the only one. */
function projToken(html: string): string {
  const opens = html.split('data-dot="proj"').length - 1;
  expect(opens).toBe(1);
  const at = html.indexOf('data-dot="proj"');
  expect(html.lastIndexOf("2nd half margin", at)).toBeGreaterThan(-1);
  return html.slice(at, html.indexOf("</div>", at));
}

describe("#8934 the 2nd half margin token on Ole Miss @ Florida", () => {
  it("is the Rebels' projection — the card the reader saw", () => {
    const html = render(true);
    expect(html).toContain("Rebels by 2.5+");
  });

  it("draws the favoured side's logo, as the full-game token does", () => {
    const token = projToken(render(true));
    expect(token).toContain(`src="${AWAY_LOGO}"`);
    expect(token).not.toContain(HOME_LOGO);
    expect(token).not.toContain("Rebels");
  });

  it("with no logo served, the word steps down so it fits inside the ring", () => {
    const token = projToken(render(false));
    expect(token).toContain(">Rebels<");
    const size = Number(/font-size:(\d+)px/.exec(token)?.[1]);
    expect(size).toBe(markerFallbackFontSize("Rebels"));
    expect(size).toBeLessThan(8);
  });
});

describe("#8934 markerFallbackFontSize", () => {
  it("keeps 8px for the four-capital codes that already fit (MICH, FLA)", () => {
    expect(markerFallbackFontSize("MICH")).toBe(8);
    expect(markerFallbackFontSize("FLA")).toBe(8);
    expect(markerFallbackFontSize("")).toBe(8);
    expect(markerFallbackFontSize(undefined)).toBe(8);
  });

  it("steps down as the label grows, never below 5px", () => {
    expect(markerFallbackFontSize("Rebels")).toBe(5);
    expect(markerFallbackFontSize("Aggie")).toBe(6);
    expect(markerFallbackFontSize("Commodores")).toBe(5);
  });
});
