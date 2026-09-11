/**
 * #5013 — THE HALF POINTS MAPS STOP PRINTING A LINE OFF A BOOK THAT HAS STOPPED.
 *
 * Seen on production at 390px on 2026-09-10, pre-kickoff 5:32pm PT,
 * `/events/14632820` (49ers @ Rams). Three cards one screen apart:
 *
 *   Points map            Projected 48
 *   1st half points map   O/U 25   PRE-GAME 25
 *   2nd half points map   O/U 11   PRE-GAME 11
 *
 * 25 + 11 = 36. The halves were twelve points short of their own game, and the
 * 2nd half marker sat against the left edge of a 2 → 48+ axis with the darkest
 * bucket leftmost.
 *
 * The venue is not what was wrong. `futures_odds_snapshots` for market 60075113
 * at 00:33:31Z — one minute AFTER the shot — holds thirteen monotone rungs
 * crossing 50% between 21.5 (0.58) and 24.5 (0.43): the honest headline was 25.
 * The line is picked by the rung CLOSEST to 50%, and on a ladder priced by an
 * empty book — ~0.99 under the step, ~0.01 over it — every rung is 49 points
 * from a coin flip, so that reduce returns whichever rung the step sits on.
 *
 * ## What makes this suite non-vacuous
 *
 * The 2nd half card not being in the markup proves nothing on its own; it is
 * also what a payload with no 2nd half rows at all looks like. So every case
 * renders the REAL `MarketMapSection`, the two arms differ ONLY in the twelve
 * probabilities on the 2nd half ladder, and the control arm requires BOTH
 * cards — with the 25 the venue was quoting. A guard that suppressed the card
 * unconditionally would fail the control.
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

const THRESHOLDS = [7.5, 10.5, 14.5, 17.5, 20.5, 21.5, 24.5, 28.5, 31.5, 35.5, 38.5, 42.5];

/** SF@LAR "1st Half Total", as the snapshot holds it at 00:33:31Z. */
const LIVE_1H = [0.975, 0.925, 0.865, 0.745, 0.635, 0.59, 0.43, 0.285, 0.175, 0.105, 0.045, 0.025];
/** SF@LAR "2nd Half Total", same snapshot. Crosses 50% between 21.5 and 24.5. */
const LIVE_2H = [0.93, 0.91, 0.83, 0.72, 0.62, 0.58, 0.43, 0.3, 0.23, 0.15, 0.14, 0.12];
/** The same twelve rungs once the book has emptied and pricing is last-trade. */
const DEAD_2H = [0.99, 0.98, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01];

function half(period: "1H" | "2H", probs: number[]) {
  const label = period === "1H" ? "1st" : "2nd";
  return THRESHOLDS.map((threshold, i) => ({
    market_name: `SF 49ers vs LA Rams: ${label} Half Total`,
    outcome_name: `Over ${threshold} ${period} points scored`,
    threshold,
    probability: null,
    market_type: "half_total",
    over_probability: probs[i],
    period,
    source: "kalshi",
    is_winner: null,
    resolution_source: null,
    movement: 0,
  }));
}

const GAME_TOTALS = [
  { threshold: 45.5, over_probability: 0.595, source: "kalshi", market_type: "game_total", market_name: "San Francisco vs Los Angeles: Total Points", outcome_name: "Over 45.5 points scored", is_winner: null, resolution_source: null, movement: 0, period: null },
  { threshold: 47.5, over_probability: 0.53, source: "kalshi", market_type: "game_total", market_name: "San Francisco vs Los Angeles: Total Points", outcome_name: "Over 47.5 points scored", is_winner: null, resolution_source: null, movement: 0, period: null },
  { threshold: 49.5, over_probability: 0.46, source: "kalshi", market_type: "game_total", market_name: "San Francisco vs Los Angeles: Total Points", outcome_name: "Over 49.5 points scored", is_winner: null, resolution_source: null, movement: 0, period: null },
];

function markets(secondHalf: number[]) {
  return {
    event_id: 14632820,
    home_team: "Los Angeles Rams",
    away_team: "San Francisco 49ers",
    home_score: 0,
    away_score: 0,
    status: "scheduled",
    player_props: [],
    team_totals: [],
    period_markets: [...half("1H", LIVE_1H), ...half("2H", secondHalf)],
    matchups: [],
    other: [],
    pace: null,
    props_script: [],
    spreads: [],
    totals: GAME_TOTALS,
  };
}

function renderMaps(secondHalf: number[]): string {
  return visibleText(
    renderToStaticMarkup(
      <MarketMapSection
        gameMarkets={markets(secondHalf) as never}
        eventStatus="scheduled"
        homeTeam="Los Angeles Rams"
        awayTeam="San Francisco 49ers"
        homeAbbr="LAR"
        awayAbbr="SF"
        overUnder={48}
        sportKey="americanfootball_nfl"
      />
    )
  );
}

describe("#5013 a half card whose book has stopped", () => {
  it("control: with both books quoting, both halves render and add up", () => {
    const text = renderMaps(LIVE_2H);

    expect(text).toContain("1st half points map");
    expect(text).toContain("2nd half points map");
    // 24.5 is the crossing on both ladders, so both cards say 25 — and
    // 25 + 25 is the game's own projected 48 to within a rounding step.
    expect(text).toContain("O/U 25");
    expect(text).toContain("Projected 48");
  });

  it("does not print the 11 the reader saw when the 2nd half book is dead", () => {
    const text = renderMaps(DEAD_2H);

    expect(text).not.toContain("O/U 11");
    expect(text).not.toContain("2nd half points map");
  });

  it("keeps the half that IS quoting, and the game total beside it", () => {
    const text = renderMaps(DEAD_2H);

    expect(text).toContain("1st half points map");
    expect(text).toContain("O/U 25");
    expect(text).toContain("Projected 48");
  });
});
