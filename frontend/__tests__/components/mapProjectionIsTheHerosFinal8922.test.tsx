/**
 * #8922 — THE MAPS' LIVE PROJECTION IS THE HERO'S PROJECTED FINAL.
 * #8925 — AND A LONG TILE NEVER LEAVES ITS CARD.
 *
 * Mystery-shopped on production 2026-09-26 20:30Z at 390px: `/events/15315949`,
 * Notre Dame 35 – 3 Purdue (Purdue at home), end of the 3rd quarter. One page,
 * one question — how does this finish? — three answers:
 *
 *     hero        Projected final: 6 – 47      ND by 41 · 53 points
 *     margin map  PROJECTION ND by 36.1+       the sportsbook MEAN (current_odds)
 *     points map  PROJECTION 51.0              the scoring PACE run forward
 *
 * The hero is the market ladders (`pm_spread_data.projected_final`). The margin
 * tile read `current_odds.spread`, which that minute still averaged in four
 * books frozen at kickoff (the backend half, PR #8924); the points tile read
 * `pace.projected_total` (38 points at 75% elapsed). While the hero prints a
 * pair, both tiles now print THAT pair — its margin and its sum — and when the
 * hero prints none, each keeps what it had (the control arms below).
 *
 * Fixture numbers are production's from that minute (payload saved under
 * artifacts/ux-shop-0926b), except the ladder rungs, which are trimmed to the
 * few the rail needs.
 */

import React from "react";
import { readFileSync } from "fs";
import path from "path";
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

const PUR = "Purdue Boilermakers";
const ND = "Notre Dame Fighting Irish";

const spread = (team: string, threshold: number, probability: number) => ({
  market_name: `${ND} vs ${PUR}: Spread`,
  outcome_name: `${team} wins by more than ${threshold} points`,
  threshold: null,
  probability,
  market_type: "spread",
  source: "kalshi",
  is_winner: null,
  resolution_source: null,
});

const total = (threshold: number, over: number) => ({
  threshold,
  over_probability: over,
  source: "kalshi",
  market_type: "game_total",
  market_name: `${ND} vs ${PUR}: Total Points`,
  outcome_name: `Over ${threshold} points`,
  is_winner: null,
  resolution_source: null,
  movement: 0,
  period: null,
});

function renderLiveNDPurdue(projectedFinal?: { home: number; away: number } | null): string {
  return renderToStaticMarkup(
    <MarketMapSection
      gameMarkets={
        {
          event_id: 15315949,
          home_team: PUR,
          away_team: ND,
          home_score: 3,
          away_score: 35,
          status: "live",
          player_props: [],
          team_totals: [],
          period_markets: [],
          matchups: [],
          other: [],
          pace: {
            total_scored: 38,
            projected_total: 51.0,
            fraction_elapsed: 0.75,
            time_remaining_display: "15:00",
          },
          props_script: [],
          spreads: [
            spread(ND, 35.5, 0.81),
            spread(ND, 41.5, 0.455),
            spread(ND, 45.5, 0.24),
          ],
          totals: [total(45.5, 0.87), total(51.5, 0.73), total(54.5, 0.455), total(59.5, 0.24)],
        } as never
      }
      eventStatus="live"
      homeTeam={PUR}
      awayTeam={ND}
      homeAbbr="PUR"
      awayAbbr="ND"
      homeWinProb={0.001}
      awayWinProb={0.999}
      openingHomeSpread={27.5}
      openingOverUnder={57}
      homeSpread={36.5}
      overUnder={54.2}
      projectedFinal={projectedFinal}
      sportKey="americanfootball_ncaaf"
    />
  );
}

describe("#8922: while the hero prints a projected final, the maps print the same one", () => {
  const text = visibleText(renderLiveNDPurdue({ home: 6, away: 47 }));

  it("margin map PROJECTION is the hero's margin, stated as a scoreline", () => {
    expect(text).toContain("Projection ND by 41");
    // not the sportsbook mean, and not hedged with a cover-line `+`
    expect(text).not.toMatch(/Projection ND by 36/);
    expect(text).not.toContain("ND by 41+");
  });

  it("points map PROJECTION and headline are the hero's total", () => {
    expect(text).toContain("Projected 53");
    expect(text).toContain("Projection 53");
    expect(text).not.toContain("51.0");
    expect(text).not.toContain("Projected 51");
  });

  it("the other tiles do not move: PRE-GAME is the opening line, ACTUAL the scoreboard", () => {
    expect(text).toContain("Pre-game ND by 27.5+");
    expect(text).toContain("Actual ND by 32");
    expect(text).toContain("Pre-game 57");
    expect(text).toContain("Actual 38");
  });
});

describe("#8922 control: with no hero pair, each tile keeps the value it had", () => {
  for (const [name, pair] of [["null", null], ["absent", undefined]] as const) {
    it(`projectedFinal ${name}`, () => {
      const text = visibleText(renderLiveNDPurdue(pair));
      expect(text).toContain("Projection ND by 36.5+");
      // #9944: the pace is anchored to the 57 opening total — 38 + 0.25 × 57 =
      // 52.25 — rather than run forward (38 / 0.75 = 51). Still the pace, not
      // the hero's 53, which is what this control is for.
      expect(text).toContain("Projected 52");
      expect(text).toContain("Projection 52.3");
      expect(text).not.toContain("Projected 53");
    });
  }
});

describe("#8922: the page hands the maps the pair its hero prints, decided once", () => {
  const page = readFileSync(
    path.join(__dirname, "..", "..", "app", "events", "[id]", "page.tsx"),
    "utf8"
  );

  it("the hero line renders heroProjectedFinal and nothing else", () => {
    expect(page).toMatch(
      /Projected final: \{heroProjectedFinal\.home\}[^\n]*\{heroProjectedFinal\.away\}/
    );
    // the old inline reads of the raw pair are gone from the render
    expect(page).not.toMatch(/Projected final: \{Math\.round\(historyData/);
  });

  it("MarketMapSection receives the same value", () => {
    expect(page).toMatch(/<MarketMapSection[\s\S]*?projectedFinal=\{heroProjectedFinal\}/);
  });
});

describe("#8925: a long value wraps inside its tile instead of spilling past the card", () => {
  // `/events/14870008` Oklahoma @ Georgia at 390px: `PROJECTION UGA by 26.1+`
  // pushed the third tile past the card's right edge.
  const html = renderToStaticMarkup(
    <MarketMapSection
      gameMarkets={
        {
          event_id: 14870008,
          home_team: "Georgia Bulldogs",
          away_team: "Oklahoma Sooners",
          home_score: 21,
          away_score: 0,
          status: "live",
          player_props: [],
          team_totals: [],
          period_markets: [],
          matchups: [],
          other: [],
          pace: null,
          props_script: [],
          spreads: [
            {
              ...spread("Georgia Bulldogs", 24.5, 0.6),
              market_name: "Oklahoma vs Georgia: Spread",
            },
            {
              ...spread("Georgia Bulldogs", 28.5, 0.45),
              market_name: "Oklahoma vs Georgia: Spread",
            },
          ],
          totals: [],
        } as never
      }
      eventStatus="live"
      homeTeam="Georgia Bulldogs"
      awayTeam="Oklahoma Sooners"
      homeAbbr="UGA"
      awayAbbr="OU"
      openingHomeSpread={-11.5}
      homeSpread={-26.1}
      sportKey="americanfootball_ncaaf"
    />
  );

  it("the tile grid's columns may shrink below their content", () => {
    expect(html).toContain("grid-template-columns:repeat(3, minmax(0, auto))");
    expect(html).not.toMatch(/grid-template-columns:repeat\(\d+, 1fr\)/);
  });

  it("the value is allowed to wrap and is never cut to an ellipsis", () => {
    const values = html.match(/<div data-tile-value="[^"]*" style="[^"]*"/g) ?? [];
    expect(values.length).toBe(3);
    for (const v of values) {
      expect(v).not.toContain("white-space:nowrap");
      expect(v).not.toContain("text-overflow:ellipsis");
    }
    expect(visibleText(html)).toContain("UGA by 26.1+");
  });
});
