/**
 * #5143 — A SETTLED HALF POINTS MAP STOPS PRINTING A FORECAST IT DOES NOT HAVE.
 *
 * Mystery-shopped on production at 390px, 2026-09-11 00:15 PT, `/events/14632820`
 * (SF@LAR, the Thursday-night opener, Final 27-7). Scrolling POINTS MAPS:
 *
 *   Total: expected vs final    PRE-GAME 41    FINAL 34 points
 *   1st half points map         PRE-GAME  8    FINAL 17 points
 *   2nd half points map         PRE-GAME  8    FINAL 17 points
 *
 * Two halves each expected to produce 8 points inside a game expected to
 * produce 41 — and the same 8 twice, off two unrelated ladders.
 *
 * ═══ THE 8 IS THE LOWEST RUNG OF A SETTLED LADDER ═══
 *
 * `#5013` gave this card `ladderQuotesALine`: a ladder with no rung between
 * 0.15 and 0.85 has stopped quoting and cannot say where the line is. Its guard
 * carried a `!isDone` carve-out so a finished game keeps its card, on the
 * reasoning that "what that card carries is the half's actual score, not a
 * forecast". The card carries BOTH, and the carve-out let the forecast through.
 *
 * Measured from the served payload the same minute, monotone-cleaned exactly as
 * `selectHalfTotalRungs` does:
 *
 *   1st Half Total  7.5→0.99  10.5→0.99  14.5→0.99  17.5→0.01 …   interior: none
 *   2nd Half Total  7.5→0.99  10.5→0.99  21.5→0.01  24.5→0.01 …   interior: none
 *
 * Every rung is ~49 points from a coin flip, so the closest-to-50% reduce keeps
 * the FIRST — the lowest threshold. 7.5 rounds to 8, on both. The full-game card
 * escapes only because it has a real line to fall back on
 * (`overUnder ?? ouLine.threshold`); a half has none.
 *
 * ═══ WHAT MAKES THIS SUITE NON-VACUOUS ═══
 *
 * "No Pre-game tile" is also what a card that failed to render looks like, and
 * what a guard that suppressed the whole finished card would produce. So every
 * arm renders the REAL `MarketMapSection`, the defect arm asserts the card is
 * STILL THERE with its FINAL tile, and the two controls differ from it only in
 * the twelve probabilities on the ladders — a fix keyed on `isDone` instead of
 * on the ladder fails the first control, and one that suppressed the card fails
 * the defect arm's own FINAL assertion.
 *
 * Tiles are asserted through `data-tile`, not through the words: "Pre-game"
 * appears on other cards in this section and the digit 8 appears inside ladder
 * labels like "Over 28.5".
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

/** How many summary tiles of this kind the section drew. */
function tileCount(html: string, key: string): number {
  return html.split(`data-tile="${key}"`).length - 1;
}

const THRESHOLDS = [7.5, 10.5, 14.5, 17.5, 20.5, 21.5, 24.5, 28.5, 31.5, 35.5, 38.5, 42.5];

/** SF@LAR's ladders as production served them AFTER the whistle: a step. */
const SETTLED_1H = [0.99, 0.99, 0.99, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01];
const SETTLED_2H = [0.99, 0.99, 0.98, 0.97, 0.96, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01];

/** The same rungs while the venue was still quoting (#5013's live fixture). */
const LIVE_1H = [0.975, 0.925, 0.865, 0.745, 0.635, 0.59, 0.43, 0.285, 0.175, 0.105, 0.045, 0.025];
const LIVE_2H = [0.93, 0.91, 0.83, 0.72, 0.62, 0.58, 0.43, 0.3, 0.23, 0.15, 0.14, 0.12];

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

/** Enough ESPN history for `deriveHalfScores` to split 27-7 into 17 and 17. */
const ESPN_HISTORY = [
  { period: "1st Quarter", home_score: 0, away_score: 7, timestamp: "2026-09-11T00:45:00Z" },
  { period: "Halftime", home_score: 7, away_score: 10, timestamp: "2026-09-11T01:40:00Z" },
  { period: "4th Quarter", home_score: 7, away_score: 27, timestamp: "2026-09-11T03:20:00Z" },
];

function markets(firstHalf: number[], secondHalf: number[]) {
  return {
    event_id: 14632820,
    home_team: "Los Angeles Rams",
    away_team: "San Francisco 49ers",
    home_score: 7,
    away_score: 27,
    status: "completed",
    player_props: [],
    team_totals: [],
    period_markets: [...half("1H", firstHalf), ...half("2H", secondHalf)],
    matchups: [],
    other: [],
    pace: null,
    props_script: [],
    spreads: [],
    totals: [],
  };
}

/**
 * The section as the finished event page mounts it. No `spreads` and no
 * `totals`, so the only cards in the markup are the two half points maps and
 * every `data-tile` below belongs to one of them.
 */
function renderMaps(
  firstHalf: number[],
  secondHalf: number[],
  eventStatus: "completed" | "scheduled" = "completed"
): string {
  return renderToStaticMarkup(
    <MarketMapSection
      gameMarkets={markets(firstHalf, secondHalf) as never}
      eventStatus={eventStatus}
      homeTeam="Los Angeles Rams"
      awayTeam="San Francisco 49ers"
      homeAbbr="LAR"
      awayAbbr="SF"
      sportKey="americanfootball_nfl"
      espnHistory={ESPN_HISTORY}
    />
  );
}

describe("#5143 a settled half card keeps its score and drops its fake line", () => {
  it("prints no Pre-game tile on the page Alex would have read", () => {
    const html = renderMaps(SETTLED_1H, SETTLED_2H);
    const text = visibleText(html);

    // The card is still here. This is the half that makes the assertion below
    // an assertion rather than a description of a card that vanished.
    expect(text).toContain("1st half points map");
    expect(text).toContain("2nd half points map");
    expect(tileCount(html, "final")).toBe(2);
    expect(text).toContain("17 points");

    // And the number that was never a forecast is gone from both.
    expect(tileCount(html, "pre")).toBe(0);
  });

  it("CONTROL: a finished game whose ladders DID quote keeps its Pre-game", () => {
    // Same event, same status, same everything — only the twelve probabilities
    // on each ladder differ. A fix keyed on `isDone` rather than on the ladder
    // deletes these two tiles as well and fails here.
    const html = renderMaps(LIVE_1H, LIVE_2H);

    expect(tileCount(html, "pre")).toBe(2);
    expect(tileCount(html, "final")).toBe(2);
    expect(visibleText(html)).toContain("2nd half points map");
  });

  it("CONTROL: #5013 is intact — an unfinished game drops the dead card whole", () => {
    // The half that has stopped quoting does not render at all before the
    // final, because there the card IS its line and there is no score to keep.
    const html = renderMaps(LIVE_1H, SETTLED_2H, "scheduled");
    const text = visibleText(html);

    expect(text).toContain("1st half points map");
    expect(text).not.toContain("2nd half points map");
    expect(tileCount(html, "pre")).toBe(1);
  });

  it("CONTROL: an unfinished game with two live ladders keeps both lines", () => {
    const html = renderMaps(LIVE_1H, LIVE_2H, "scheduled");

    expect(tileCount(html, "pre")).toBe(2);
    expect(tileCount(html, "final")).toBe(0);
  });
});
