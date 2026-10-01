/**
 * #9977 — A LIVE BASEBALL GAME'S FIRST-FIVE CARD KEEPS ITS ACTUAL BETWEEN
 * HALF-INNING CHANGES.
 *
 * Seen on production at 390px, 2026-10-01 01:09Z and 01:34Z (no refresh),
 * `/events/15321907`, Red Sox @ Yankees, live. The full-game Runs map drew
 * `ACTUAL 1 run`; the "First 5 innings runs map" directly below drew only its
 * Pre-game tile, in the 5th inning.
 *
 * `/api/events/15321907/history` served 28 `espn_history` rows: the 11 written
 * at a half-inning change carry `period` (`Top 1st`, … `End 3rd`), the 17
 * written every ~2 minutes in between carry `period: null`. `detectCurrentHalf`
 * read only the LAST row, so whenever that was a null sample it knew no half,
 * and the Actual tile went with it.
 *
 * ## What makes this suite non-vacuous
 *
 * Every arm renders the REAL `MarketMapSection` and asserts the card by title
 * before asserting its tiles, so a vanished card fails rather than passes. The
 * defect arms END on a null sample (the specimen's own row shape and times);
 * the controls change one input each: a history ending on its period row (the
 * case that already worked, which must not move), the 6th inning behind a null
 * sample (the `End 5th` path must still hold the first five's score, not take the
 * scoreboard), and a history whose rows NEVER name a period (still no guess).
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

function tileCount(html: string, key: string): number {
  return html.split(`data-tile="${key}"`).length - 1;
}

function tileText(html: string, key: string): string {
  const at = html.indexOf(`data-tile="${key}"`);
  if (at < 0) return "";
  const open = html.lastIndexOf("<", at);
  const tag = html.slice(open + 1).match(/^[a-z0-9]+/i)?.[0] ?? "div";
  let depth = 0;
  const re = new RegExp(`<(/?)${tag}\\b[^>]*>`, "gi");
  re.lastIndex = open;
  let m: RegExpExecArray | null;
  while ((m = re.exec(html))) {
    depth += m[1] ? -1 : 1;
    if (depth === 0) return visibleText(html.slice(open, re.lastIndex));
  }
  return visibleText(html.slice(open));
}

const HOME = "New York Yankees";
const AWAY = "Boston Red Sox";

/** A first-five ladder still quoting, the shape #8557's suite uses. */
const LIVE_F5 = [
  [2.5, 0.62],
  [3.5, 0.45],
  [4.5, 0.3],
].map(([threshold, over]) => ({
  market_type: "half_total",
  market_name: `Boston Red Sox vs. New York Yankees: 1st 5 Innings O/U ${threshold}`,
  outcome_name: "Over",
  threshold,
  over_probability: over,
  probability: null,
  period: null,
  source: "polymarket",
  is_winner: null,
  resolution_source: null,
  movement: 0,
}));

type Row = { period: string | null; home_score: number; away_score: number; timestamp: string };

/** The specimen's served rows, 01:01Z–01:10Z: a period row, then null samples. */
const IN_THE_FOURTH: Row[] = [
  { period: "Bottom 3rd", home_score: 0, away_score: 0, timestamp: "2026-10-01T01:01:20Z" },
  { period: null, home_score: 0, away_score: 0, timestamp: "2026-10-01T01:02:04Z" },
  { period: "End 3rd", home_score: 0, away_score: 0, timestamp: "2026-10-01T01:05:15Z" },
  { period: "Top 4th", home_score: 0, away_score: 0, timestamp: "2026-10-01T01:08:24Z" },
  { period: null, home_score: 1, away_score: 0, timestamp: "2026-10-01T01:10:04Z" },
  { period: null, home_score: 1, away_score: 0, timestamp: "2026-10-01T01:12:04Z" },
];

const PAST_THE_FIFTH: Row[] = [
  { period: "Bottom 5th", home_score: 2, away_score: 0, timestamp: "2026-10-01T01:40:00Z" },
  { period: "End 5th", home_score: 2, away_score: 0, timestamp: "2026-10-01T01:46:00Z" },
  { period: "Top 6th", home_score: 2, away_score: 0, timestamp: "2026-10-01T01:48:00Z" },
  { period: null, home_score: 2, away_score: 1, timestamp: "2026-10-01T01:52:00Z" },
];

function live(history: Row[], home: number, away: number): string {
  return renderToStaticMarkup(
    <MarketMapSection
      gameMarkets={
        {
          event_id: 15321907,
          home_team: HOME,
          away_team: AWAY,
          home_score: home,
          away_score: away,
          status: "live",
          player_props: [],
          team_totals: [],
          period_markets: LIVE_F5,
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
      homeAbbr="NYY"
      awayAbbr="BOS"
      sportKey="baseball_mlb"
      espnHistory={history as never}
    />
  );
}

describe("#9977 the live first-five card between half-inning changes", () => {
  it("draws the running score as Actual when the last row is a null-period sample", () => {
    const html = live(IN_THE_FOURTH, 1, 0);

    expect(visibleText(html)).toContain("First 5 innings runs map");
    expect(tileText(html, "actual")).toBe("Actual 1 run");
  });

  it("still holds the `End 5th` score in the 6th when the last row is a null sample", () => {
    const html = live(PAST_THE_FIFTH, 2, 1);

    expect(visibleText(html)).toContain("First 5 innings runs map");
    // 2 + 0 at End 5th — not the 3 on the scoreboard in the 6th.
    expect(tileText(html, "actual")).toBe("Actual 2 runs");
  });

  it("control: a history ending on its period row draws the same Actual it always did", () => {
    const html = live(IN_THE_FOURTH.slice(0, 4), 0, 0);

    expect(visibleText(html)).toContain("First 5 innings runs map");
    expect(tileText(html, "actual")).toBe("Actual 0 runs");
  });

  it("control: a history that never names a period draws no Actual rather than a guess", () => {
    const html = live(
      IN_THE_FOURTH.map((r) => ({ ...r, period: null })),
      1,
      0
    );

    expect(visibleText(html)).toContain("First 5 innings runs map");
    expect(tileCount(html, "actual")).toBe(0);
  });
});
