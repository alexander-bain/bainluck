/**
 * #9944 — A RUN-FORWARD OF A SLIVER OF THE GAME IS NOT A FORECAST.
 *
 * ═══ THE SPECIMEN ═══
 *
 * Production, 2026-09-30 21:47Z, `/events/15321836` — White Sox @ Astros, live,
 * Bottom 1st, CHW 4 – 1, read at 390px:
 *
 *     Runs map — Where it's heading vs what was expected — Projected 90
 *     ACTUAL 5 runs  ·  PRE-GAME 8  ·  PROJECTION 90.0      rail 0 … 52 … 103+
 *
 * The served pace, same minute:
 *
 *     pace = { total_scored: 5, projected_total: 90, fraction_elapsed: 0.056 }
 *
 * `5 / 0.056 ≈ 90`. The page's own markets said ~12 (sportsbook live total 12.5,
 * Polymarket 8.5 rung at 86.5% over); the game opened at 7.5.
 *
 * ═══ WHAT EACH TEST IS FOR ═══
 *
 *   - the first test is the ship clause and goes red on master.
 *   - `the rail stays scaled` is the second half of the photograph (103+).
 *   - `anchored late too` pins the formula rather than a floor: a floor-only fix
 *     (withhold below N%) passes the first test and fails this one.
 *   - `no pre-game total` pins the fallback: withheld early, run-forward late.
 *   - #6831 and #9930 keep their refusals; their own suites still run.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";
import { liveProjectedTotal, RUN_FORWARD_MIN_ELAPSED } from "@/lib/marketMapUtils";

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
  source: "polymarket",
  market_type: "game_total",
  market_name: "Chicago White Sox vs Houston Astros: Total Runs",
  outcome_name: "Over",
  is_winner: null,
  resolution_source: null,
  movement: 0,
  period: null,
});

/** Event 15321836 — Chicago (away) at Houston (home), Bottom 1st, 4 – 1. */
function white_sox_at_astros(overrides: Record<string, unknown> = {}) {
  return {
    event_id: 15321836,
    home_team: "Houston Astros",
    away_team: "Chicago White Sox",
    home_score: 1,
    away_score: 4,
    status: "live",
    player_props: [],
    team_totals: [],
    period_markets: [],
    matchups: [],
    other: [],
    props_script: [],
    spreads: [],
    pace: {
      total_scored: 5,
      projected_total: 90,
      fraction_elapsed: 0.056,
      time_remaining_display: "51:00 left",
    },
    // The three rungs production served, verbatim.
    totals: [totalRung(6.5, 0.965), totalRung(7.5, 0.94), totalRung(8.5, 0.865)],
    ...overrides,
  };
}

function renderHtml(overrides: Record<string, unknown> = {}, props: Record<string, unknown> = {}) {
  return renderToStaticMarkup(
    <MarketMapSection
      gameMarkets={white_sox_at_astros(overrides) as never}
      eventStatus="live"
      homeTeam="Houston Astros"
      awayTeam="Chicago White Sox"
      homeAbbr="HOU"
      awayAbbr="CHW"
      homeWinProb={0.24}
      awayWinProb={0.76}
      overUnder={12.5}
      openingOverUnder={7.5}
      sportKey="baseball_mlb"
      {...props}
    />
  );
}

const renderCard = (o: Record<string, unknown> = {}, p: Record<string, unknown> = {}) =>
  visibleText(renderHtml(o, p));

describe("#9944 — an early run-forward is anchored to the pre-game total", () => {
  it("the photographed Bottom-1st card projects 12, not 90", () => {
    const text = renderCard();

    expect(text).not.toMatch(/Projected\s+90\b/);
    expect(text).not.toMatch(/90\.0/);
    // 5 + (1 − 0.056) × 7.5 = 12.08
    expect(text).toMatch(/Projected\s+12\b/);
    expect(text).toMatch(/12\.1/);
  });

  it("the rail stays scaled to the ladder, not stretched to 103+", () => {
    const text = renderCard();

    expect(text).not.toMatch(/103\+/);
    expect(text).not.toMatch(/\b52\b/);
  });

  it("CONTROL: the card keeps ACTUAL, PRE-GAME and its ladder", () => {
    const text = renderCard();

    expect(text).toMatch(/5 runs/);
    expect(text).toMatch(/Pre-game/);
    expect(text).toMatch(/Projection/);
  });

  it("anchored late too — the formula, not a floor", () => {
    // Late in the game with the served run-forward at 11: anchored it is
    // 6 + (1 − 0.6) × 7.5 = 9. A floor-only fix would print 11 here.
    const text = renderCard({
      pace: { total_scored: 6, projected_total: 11, fraction_elapsed: 0.6, time_remaining_display: "" },
    });
    expect(text).toMatch(/Projected\s+9\b/);
    expect(text).not.toMatch(/Projected\s+11\b/);
  });

  it("with no pre-game total: withheld early, the bare run-forward late", () => {
    const early = renderCard({}, { openingOverUnder: null });
    expect(early).not.toMatch(/Projected\s+\d/);

    const late = renderCard(
      { pace: { total_scored: 8, projected_total: 11, fraction_elapsed: 0.722, time_remaining_display: "" } },
      { openingOverUnder: null }
    );
    expect(late).toMatch(/Projected\s+11\b/);
  });

  it("CONTROL: the hero's projected final still wins", () => {
    const text = renderCard({}, { projectedFinal: { home: 5.2, away: 7.1 } });
    expect(text).toMatch(/Projected\s+12\b/);
  });
});

describe("liveProjectedTotal", () => {
  const pace = (scored: number, elapsed: number, runForward: number | null = null) => ({
    total_scored: scored,
    projected_total: runForward,
    fraction_elapsed: elapsed,
  });

  it("anchors to the pre-game total and ends at the tally", () => {
    expect(liveProjectedTotal(pace(5, 0.056, 90), 7.5)).toBeCloseTo(12.08, 2);
    expect(liveProjectedTotal(pace(5, 0.999, 5), 7.5)).toBeCloseTo(5.0075, 3);
  });

  it("keeps #6831 (nothing scored) and #9930 (no time left)", () => {
    expect(liveProjectedTotal(pace(0, 0.3, 0), 45)).toBeNull();
    expect(liveProjectedTotal(pace(6, 1, 6), 7)).toBeNull();
    expect(liveProjectedTotal(pace(-3, 0.5, -3), 7)).toBeNull();
    expect(liveProjectedTotal(null, 7)).toBeNull();
  });

  it("a payload with no fraction reads as it always did", () => {
    const noFraction = { total_scored: 60, projected_total: 108.5 } as never;
    expect(liveProjectedTotal(noFraction, 45)).toBe(108.5);
  });

  it("with no anchor, prints the run-forward only from half the game", () => {
    expect(liveProjectedTotal(pace(5, RUN_FORWARD_MIN_ELAPSED - 0.01, 10), null)).toBeNull();
    expect(liveProjectedTotal(pace(5, RUN_FORWARD_MIN_ELAPSED, 10), null)).toBe(10);
    expect(liveProjectedTotal(pace(5, 0.6, 10), 0)).toBe(10); // a 0 total is no anchor
  });
});
