/**
 * #9064 — BEFORE KICKOFF, THE POINTS MAP'S PROJECTION IS THE HERO'S SUM TOO.
 *
 * Production 2026-09-27 05:20Z at 390px, `/events/14781701` (Dolphins v Chiefs,
 * pre-game), right after #9034 went live: the hero read `Projected final:
 * 18 – 29` (the sportsbook pair, 17.5 / 28.7) and the Points map one scroll
 * below read `Projected 45` (the over/under line, 44.8). Two projected totals
 * for one game. #8922 made the maps print the hero's pair while LIVE; this is
 * the same rule on the pre-game arm. With no hero pair, the line stays.
 *
 * Fixture numbers are production's from that minute; ladder rungs trimmed.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";

function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&#x27;|&#39;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&[a-z]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

const MIA = "Miami Dolphins";
const KC = "Kansas City Chiefs";

const total = (threshold: number, over: number) => ({
  threshold,
  over_probability: over,
  source: "kalshi",
  market_type: "game_total",
  market_name: `${KC} vs ${MIA}: Total Points`,
  outcome_name: `Over ${threshold} points`,
  is_winner: null,
  resolution_source: null,
  movement: 0,
  period: null,
});

function renderPreMiaKc(
  projectedFinal?: { home: number; away: number } | null,
  extra: { noResultReported?: boolean } = {}
): string {
  return renderToStaticMarkup(
    <MarketMapSection
      gameMarkets={
        {
          event_id: 14781701,
          home_team: MIA,
          away_team: KC,
          home_score: null,
          away_score: null,
          status: "scheduled",
          player_props: [],
          team_totals: [],
          period_markets: [],
          matchups: [],
          other: [],
          pace: null,
          props_script: [],
          spreads: [],
          totals: [total(40.5, 0.7), total(44.5, 0.52), total(48.5, 0.34), total(52.5, 0.18)],
        } as never
      }
      eventStatus="scheduled"
      homeTeam={MIA}
      awayTeam={KC}
      homeAbbr="MIA"
      awayAbbr="KC"
      homeWinProb={0.155}
      awayWinProb={0.845}
      homeSpread={11.2}
      overUnder={44.8}
      projectedFinal={projectedFinal}
      sportKey="americanfootball_nfl"
      {...extra}
    />
  );
}

/** The points card's slice of the page: from its title to the end. */
function pointsCard(text: string): string {
  const i = text.indexOf("Points map");
  expect(i).toBeGreaterThanOrEqual(0);
  return text.slice(i);
}

describe("#9064: pre-game, the points projection is the hero's projected final summed", () => {
  const card = pointsCard(visibleText(renderPreMiaKc({ home: 18, away: 29 })));

  it("headline is the hero's total, not the over/under line", () => {
    expect(card).toContain("Projected 47");
    expect(card).not.toContain("Projected 45");
  });

  it("the Projection marker carries the same number", () => {
    // headline, then the ring's own number (hideTile: the dot is the only mark
    // on this arm), then the rail's axis ticks
    expect(card).toMatch(/Projected 47 47 /);
    expect(card).not.toMatch(/ 45 /);
  });
});

describe("#9064 control: with no hero pair, the pre-game projection stays the line", () => {
  for (const [name, pair] of [["null", null], ["absent", undefined]] as const) {
    it(`projectedFinal ${name}`, () => {
      const card = pointsCard(visibleText(renderPreMiaKc(pair)));
      expect(card).toMatch(/Projected 45 45 /);
      expect(card).not.toContain("Projected 47");
    });
  }
});

describe("#9064 control: an unreported match keeps no forecast even with a hero pair", () => {
  it("noForecast still prints no Projected headline", () => {
    const card = pointsCard(
      visibleText(renderPreMiaKc({ home: 18, away: 29 }, { noResultReported: true }))
    );
    // the past-tense mark is the quoted line, never the hero's forecast
    expect(card).not.toContain("Projected");
    // #10171: as drawn — the 44.8 line, not rounded to 45.
    expect(card).toContain("Pre-game 44.8");
  });
});
