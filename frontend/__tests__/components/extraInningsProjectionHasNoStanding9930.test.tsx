/**
 * #9930 — A RUN-FORWARD OF NO REMAINING TIME IS NOT A FORECAST.
 *
 * ═══ THE SPECIMEN ═══
 *
 * Production, 2026-09-30 21:00Z, `/events/15321782` — Phillies @ Braves, NL
 * Wild Card G2, live, Top 10th, 3 – 3. Read at 390px during the notice-42
 * live-marquee mystery shop:
 *
 *     Runs map — Where it's heading vs what was expected — Projected 6
 *     ACTUAL 6 runs  ·  PROJECTION 6.0  ·  PRE-GAME 7
 *
 * A tied baseball game cannot finish on 6 runs; somebody has to score. The
 * served pace at 21:02Z:
 *
 *     pace = { total_scored: 6, projected_total: 6, fraction_elapsed: 1.0 }
 *
 * `_estimate_game_pace` caps elapsed time at the whole game, so from the end of
 * regulation every overtime projects exactly the tally. #6831 withheld a
 * projection of NOTHING; this withholds one of NO TIME LEFT.
 *
 * ═══ WHAT EACH TEST IS FOR ═══
 *
 *   - the first test is the ship clause and goes red on master.
 *   - `still draws a projection with time left` kills the delete-it-all mutant
 *     (the same game in the 7th, before the cap bites).
 *   - `keeps the rest of the card` proves ACTUAL, PRE-GAME and the ladder
 *     survive — suppressing the card would pass the ship clause.
 *   - `the hero's projected final still wins` pins that #8922's sum, which is
 *     not a run-forward, is not caught by a gate aimed at the pace.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";

function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&#x27;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&[a-z]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

const totalRung = (threshold: number, over: number) => ({
  threshold,
  over_probability: over,
  source: "kalshi",
  market_type: "game_total",
  market_name: "Philadelphia vs Atlanta: Total Runs",
  outcome_name: `Over ${threshold} runs`,
  is_winner: null,
  resolution_source: null,
  movement: 0,
  period: null,
  bookmaker_count: 6,
});

/** Event 15321782 — Philadelphia (away) at Atlanta (home), Top 10th, 3 – 3. */
function phillies_at_braves(overrides: Record<string, unknown> = {}) {
  return {
    event_id: 15321782,
    home_team: "Atlanta Braves",
    away_team: "Philadelphia Phillies",
    home_score: 3,
    away_score: 3,
    status: "live",
    player_props: [],
    team_totals: [],
    period_markets: [],
    matchups: [],
    other: [],
    props_script: [],
    spreads: [],
    pace: {
      total_scored: 6,
      projected_total: 6,
      fraction_elapsed: 1.0,
      time_remaining_display: "0:00 left",
    },
    totals: [totalRung(5.5, 0.78), totalRung(7.5, 0.47), totalRung(9.5, 0.2)],
    ...overrides,
  };
}

function renderCard(
  overrides: Record<string, unknown> = {},
  props: Record<string, unknown> = {}
) {
  return visibleText(
    renderToStaticMarkup(
      <MarketMapSection
        gameMarkets={phillies_at_braves(overrides) as never}
        eventStatus="live"
        homeTeam="Atlanta Braves"
        awayTeam="Philadelphia Phillies"
        homeAbbr="ATL"
        awayAbbr="PHI"
        homeWinProb={0.5}
        awayWinProb={0.5}
        overUnder={7}
        openingOverUnder={7}
        sportKey="baseball_mlb"
        {...props}
      />
    )
  );
}

describe("#9930 — extra innings have no pace projection to print", () => {
  it("prints no projected total on the photographed Top 10th card", () => {
    const text = renderCard();

    expect(text).not.toMatch(/Projected\s+6\b/);
    expect(text).not.toMatch(/Projection\s+6\.0/);
    expect(text).not.toMatch(/Projection/);
  });

  it("CONTROL: still draws a projection with time left", () => {
    // The same game at 3 – 3 with the top of the 7th under way (36 of 54
    // model minutes). If the fix were `projected = null` this goes red.
    const text = renderCard({
      pace: {
        total_scored: 6,
        projected_total: 9,
        fraction_elapsed: 0.667,
        time_remaining_display: "18:00 left",
      },
    });

    // #9944: anchored to the 7 opening total, 6 + (1 − 0.667) × 7 = 8.3.
    expect(text).toMatch(/Projected\s+8\b/);
    expect(text).toMatch(/Projection/);
  });

  it("CONTROL: the extra-innings card keeps every number it can honestly show", () => {
    const text = renderCard();

    expect(text).toMatch(/6 runs/); // ACTUAL
    expect(text).toMatch(/Pre-game/);
    expect(text).toMatch(/Over 7\.5/); // the ladder still draws
  });

  it("CONTROL: the hero's projected final still wins in extras", () => {
    // #8922's sum is a market reading, not a run-forward, so the time-left gate
    // must not reach it.
    const text = renderCard({}, { projectedFinal: { home: 4, away: 3.6 } });

    expect(text).toMatch(/Projected\s+8\b/);
  });
});
