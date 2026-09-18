/**
 * #6831 — A RUN-FORWARD OF NOTHING IS NOT A FORECAST.
 *
 * ═══ THE SPECIMEN ═══
 *
 * Production, 2026-09-18 00:27Z, `/events/14638444` — Lions @ Bills, live,
 * 11:08 into the 1st quarter, score 0 – 0. Read at 390px during the notice-42
 * live-marquee mystery shop:
 *
 *     POINTS MAPS
 *     Points map  — Where it's heading vs what was expected —  Projected 0
 *     ACTUAL 0 points  ·  PROJECTION 0.0  ·  PRE-GAME 55
 *
 * A projected final total of ZERO for an NFL game, printed twice, over the
 * card's own `PRE-GAME 55` tile — and one screen above it the hero read
 * `Projected final: 32 – 24` off `current_odds.projected_home_score 31.5` /
 * `projected_away_score 24.4`. 56 and 0, one page, one game.
 *
 * ═══ WHY IT IS STRUCTURAL AND NOT A BAD MINUTE ═══
 *
 * `pace.projected_total` is the score so far run forward over the whole game.
 * Measured on the same event at 00:29Z, once Buffalo had scored:
 *
 *     pace = { total_scored: 6, projected_total: 62, fraction_elapsed: 0.097 }
 *
 * `6 / 0.097 = 61.8 ≈ 62`, so `projected_total === scored / elapsed`. A
 * scoreless game therefore projects exactly 0 at EVERY elapsed fraction — and
 * `0` is not `null`, so the presence-only guards at both consumers drew it.
 *
 * Population: every live game between kickoff and the first score. That is the
 * opening of essentially every game on the site, which is the window a reader
 * is most likely to have the live page open in.
 *
 * ═══ WHY THIS IS A NEW RULE AND NOT ONE THE FILE ALREADY HAS ═══
 *
 * `MarketMapSection` declines rather than fabricates twice already — #5206's
 * `noForecast` (a match nobody reported has no forecast to offer) and the
 * neighbouring card's `isDone ? "" : …`. Both rule on TENSE. Here the tense is
 * correct — the game really is live — and it is the VALUE that has no standing.
 * Same posture, new axis.
 *
 * ═══ WHAT EACH TEST IS FOR ═══
 *
 * The first test is the ship clause and is the one that goes red on master.
 * Everything after it is a CONTROL, because the ship clause alone is satisfied
 * by deleting the projection outright:
 *
 *   - `still draws a projection that HAS standing` is the control that kills
 *     the delete-it-all mutant. It is the whole reason the predicate is
 *     `> 0` and not `false`.
 *   - `keeps the rest of the card` proves the scoreless card still says
 *     everything it honestly knows (ACTUAL, PRE-GAME, the ladder). Suppressing
 *     the card would "fix" the headline and lose four true numbers.
 *   - `the pre arm is untouched` guards the neighbouring branch, which sources
 *     its headline from `ouVal` and must not have been caught in the change.
 *   - `refuses a negative` pins `> 0` against `!== 0`. Flagged honestly: the
 *     current estimator cannot emit a negative, so this is a predicate
 *     boundary rather than a reader case — it is here so a later widening of
 *     the upstream formula cannot quietly reintroduce a printable absurdity.
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

/** A `game_total` rung in the shape `selectGameTotalRungs` accepts. */
const totalRung = (threshold: number, over: number) => ({
  threshold,
  over_probability: over,
  source: "kalshi",
  market_type: "game_total",
  market_name: "Detroit vs Buffalo: Total Points",
  outcome_name: `Over ${threshold} points`,
  is_winner: null,
  resolution_source: null,
  movement: 0,
  period: null,
  bookmaker_count: 8,
});

/**
 * Event 14638444 — Detroit (away) at Buffalo (home), live at 0 – 0.
 *
 * `pace` defaults to the scoreless reading the shop actually photographed.
 * The ladder brackets the real 54.1 line so the rail is a genuine one and the
 * `Pre-game 55` marker lands inside it rather than pinning to an edge.
 */
function lionsAtBills(overrides: Record<string, unknown> = {}) {
  return {
    event_id: 14638444,
    home_team: "Buffalo Bills",
    away_team: "Detroit Lions",
    home_score: 0,
    away_score: 0,
    status: "live",
    player_props: [],
    team_totals: [],
    period_markets: [],
    matchups: [],
    other: [],
    props_script: [],
    spreads: [],
    pace: {
      total_scored: 0,
      projected_total: 0,
      fraction_elapsed: 0.097,
      time_remaining_display: "54:08 left",
    },
    totals: [totalRung(48.5, 0.82), totalRung(54.5, 0.49), totalRung(60.5, 0.18)],
    ...overrides,
  };
}

function renderCard(overrides: Record<string, unknown> = {}, eventStatus = "live") {
  return visibleText(
    renderToStaticMarkup(
      <MarketMapSection
        gameMarkets={lionsAtBills({ status: eventStatus, ...overrides }) as never}
        eventStatus={eventStatus}
        homeTeam="Buffalo Bills"
        awayTeam="Detroit Lions"
        homeAbbr="BUF"
        awayAbbr="DET"
        homeWinProb={0.73}
        awayWinProb={0.27}
        overUnder={54.1}
        openingOverUnder={55}
        sportKey="americanfootball_nfl"
      />
    )
  );
}

describe("#6831 — a scoreless live game has no projection to print", () => {
  it("prints no projected total on the photographed 0 – 0 card", () => {
    const text = renderCard();

    // The two sites that drew it: the card headline and the PROJECTION tile.
    expect(text).not.toMatch(/Projected\s+0\b/);
    expect(text).not.toMatch(/Projection\s+0\.0/);

    // And no bare `Projection` label left hanging over a deleted number.
    expect(text).not.toMatch(/Projection/);
  });

  it("CONTROL: still draws a projection that HAS standing", () => {
    // The same event 4 minutes later, once Buffalo had scored — the real
    // 00:29Z payload. If the fix were `projected = null` this goes red.
    const text = renderCard({
      home_score: 6,
      away_score: 0,
      pace: {
        total_scored: 6,
        projected_total: 62,
        fraction_elapsed: 0.097,
        time_remaining_display: "54:08 left",
      },
    });

    expect(text).toMatch(/Projected\s+62/);
    expect(text).toMatch(/Projection/);
    expect(text).toMatch(/62\.0/);
  });

  it("CONTROL: the scoreless card keeps every number it can honestly show", () => {
    const text = renderCard();

    // Withholding the forecast must not withhold the card. All three of these
    // are true statements the reader is entitled to, and a suppress-the-card
    // "fix" would pass the ship clause above while losing them.
    expect(text).toMatch(/0 points/); // ACTUAL
    expect(text).toMatch(/Pre-game/); // the 55 marker
    expect(text).toMatch(/55/);
    expect(text).toMatch(/Over 54\.5 points|54\.5/); // the ladder still draws
  });

  it("CONTROL: the pre arm is untouched", () => {
    // Sources its headline from `ouVal`, not from `pace`. A change that reached
    // across into this branch would show up as a missing pre-game headline.
    const text = renderCard({ home_score: null, away_score: null, pace: null }, "scheduled");

    expect(text).toMatch(/Projected\s+55/);
  });

  it("CONTROL: refuses a negative, so the predicate is `> 0` and not `!== 0`", () => {
    const text = renderCard({
      pace: {
        total_scored: 0,
        projected_total: -3,
        fraction_elapsed: 0.5,
        time_remaining_display: "30:00 left",
      },
    });

    expect(text).not.toMatch(/Projected\s+-3/);
    expect(text).not.toMatch(/Projection/);
  });
});
