/**
 * #8557 — A FINISHED BASEBALL GAME'S FIRST-FIVE CARD SAYS WHAT THE FIRST FIVE
 * INNINGS PRODUCED.
 *
 * Seen on production at 390px, 2026-09-25 ~06:10Z (shopper pass 0048),
 * `/events/15318086`, Mariners 4 – 6 Angels, FINAL. The full-game card graded
 * `FINAL 10 runs` and every line against it; directly below, the "First 5
 * innings runs map" drew an empty rail and five `Over N  100%` last quotes.
 *
 * The page already held the answer: `/api/events/15318086/history` served
 * `period: "End 5th"`, 4-3, so the first five innings produced 7. The half
 * cards found their boundary with `halftime|^ht$|end of 2nd`, which baseball's
 * `End 5th` never matches, so there was no first-period score, no FINAL marker
 * and no grade. The live card had the same hole from the other side:
 * `detectCurrentHalf` sent `Top 3rd` to its "2H" default and then looked for a
 * halftime row baseball never writes.
 *
 * ## What makes this suite non-vacuous
 *
 * Every arm renders the REAL `MarketMapSection` over the specimen's own
 * `half_total` rows (`/api/events/15318086/game-markets`, 2026-09-25) and
 * asserts the card is STILL THERE by title before asserting anything about its
 * tiles, so a card that vanished fails rather than passes. The controls differ
 * from the defect arm in ONE input each: the ESPN history without its `End 5th`
 * row (kills a fix that grades without the number it grades against, and one
 * that falls back to a neighbouring inning), and the sport (a football page with
 * the same kind of history keeps grading on `Halftime`, so a fix that swapped the
 * vocabulary instead of declaring it per sport fails there).
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

/** The text of one summary tile, e.g. `Final 7 runs`. */
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

/** Each rung's verdict, bounded by the NEXT rung's label (see #6169's suite). */
function verdictsOf(text: string, thresholds: number[]): string[] {
  const body = text.slice(text.indexOf("Each line vs the final"));
  return thresholds.map((t, i) => {
    const at = body.indexOf(`Over ${t} `);
    if (at < 0) return `${t}:absent`;
    const next = i + 1 < thresholds.length ? body.indexOf(`Over ${thresholds[i + 1]} `, at) : -1;
    return `${t}:${body.slice(at + `Over ${t} `.length, next < 0 ? undefined : next).trim()}`;
  });
}

const HOME = "Seattle Mariners";
const AWAY = "Los Angeles Angels";
const THRESHOLDS = [2.5, 3.5, 4.5, 5.5, 6.5];

/** The specimen's `half_total` rows exactly as production served them, Over AND Under. */
const SETTLED_F5 = THRESHOLDS.flatMap((threshold) =>
  ["Over", "Under"].map((outcome_name) => ({
    market_type: "half_total",
    market_name: `Los Angeles Angels vs. Seattle Mariners: 1st 5 Innings O/U ${threshold}`,
    outcome_name,
    threshold,
    over_probability: 1.0,
    probability: null,
    period: null,
    source: "polymarket",
    is_winner: true,
    resolution_source: "api_settlement",
    movement: 0,
  }))
);

/** #8483's live Braves ladder under the same name shape: a ladder still quoting. */
const LIVE_F5 = [
  [2.5, 0.755],
  [3.5, 0.635],
  [4.5, 0.505],
  [5.5, 0.385],
  [6.5, 0.285],
].map(([threshold, over]) => ({
  market_type: "half_total",
  market_name: `Los Angeles Angels vs. Seattle Mariners: 1st 5 Innings O/U ${threshold}`,
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

type Row = { period?: string; home_score?: number; away_score?: number; timestamp?: string };

/** The specimen's served history rows around the boundary, plus its Final. */
const SEA_HISTORY: Row[] = [
  { period: "End 4th", home_score: 3, away_score: 1, timestamp: "2026-09-25T02:52:16Z" },
  { period: "Top 5th", home_score: 3, away_score: 3, timestamp: "2026-09-25T03:01:16Z" },
  { period: "Bottom 5th", home_score: 4, away_score: 3, timestamp: "2026-09-25T03:18:16Z" },
  { period: "End 5th", home_score: 4, away_score: 3, timestamp: "2026-09-25T03:19:17Z" },
  { period: "Top 6th", home_score: 4, away_score: 4, timestamp: "2026-09-25T03:21:17Z" },
  { period: "Bottom 9th", home_score: 4, away_score: 6, timestamp: "2026-09-25T04:25:17Z" },
  { period: "Final", home_score: 4, away_score: 6, timestamp: "2026-09-25T04:28:00Z" },
];

function render(opts: {
  rows: unknown[];
  status: string;
  home: number;
  away: number;
  history: Row[];
  sportKey?: string;
}): string {
  return renderToStaticMarkup(
    <MarketMapSection
      gameMarkets={
        {
          event_id: 15318086,
          home_team: HOME,
          away_team: AWAY,
          home_score: opts.home,
          away_score: opts.away,
          status: opts.status,
          player_props: [],
          team_totals: [],
          period_markets: opts.rows,
          matchups: [],
          other: [],
          pace: null,
          props_script: [],
          spreads: [],
          totals: [],
        } as never
      }
      eventStatus={opts.status}
      homeTeam={HOME}
      awayTeam={AWAY}
      homeAbbr="SEA"
      awayAbbr="LAA"
      sportKey={opts.sportKey ?? "baseball_mlb"}
      espnHistory={opts.history}
    />
  );
}

const finished = (history: Row[]) =>
  render({ rows: SETTLED_F5, status: "completed", home: 4, away: 6, history });

describe("#8557 the first-five card on a finished baseball page", () => {
  it("draws the first five innings' total as its FINAL, read from `End 5th`", () => {
    const html = finished(SEA_HISTORY);
    const text = visibleText(html);

    expect(text).toContain("First 5 innings runs map");
    expect(tileCount(html, "final")).toBe(1);
    expect(tileText(html, "final")).toBe("Final 7 runs");
  });

  it("grades every line against that 7, in the full-game card's words", () => {
    const text = visibleText(finished(SEA_HISTORY));

    expect(text).toContain("Each line vs the final");
    expect(text).not.toContain("Last quote for going over");
    expect(verdictsOf(text, THRESHOLDS)).toEqual(THRESHOLDS.map((t) => `${t}:cleared`));
  });

  it("control: with no `End 5th` row the card keeps today's quotes, not a neighbouring inning", () => {
    const html = finished(SEA_HISTORY.filter((r) => r.period !== "End 5th"));
    const text = visibleText(html);

    // Still the same card, so the absence below is not a card that vanished.
    expect(text).toContain("First 5 innings runs map");
    expect(tileCount(html, "final")).toBe(0);
    expect(text).toContain("Last quote for going over");
    expect(text).not.toContain("Each line vs the final");
  });

  it("control: a football page still finds its half at `Halftime`", () => {
    const html = render({
      rows: SETTLED_F5.map((r) => ({
        ...r,
        market_name: `DAL Cowboys vs NY Giants: 1st Half Total`,
        outcome_name: `${r.outcome_name} ${r.threshold} 1H points scored`,
        period: "1H",
      })),
      status: "completed",
      home: 28,
      away: 20,
      sportKey: "americanfootball_nfl",
      history: [
        { period: "End 5th", home_score: 0, away_score: 1, timestamp: "2026-09-14T00:30:00Z" },
        { period: "Halftime", home_score: 3, away_score: 1, timestamp: "2026-09-14T01:30:00Z" },
        { period: "Final", home_score: 28, away_score: 20, timestamp: "2026-09-14T03:28:00Z" },
      ],
    });

    expect(visibleText(html)).toContain("1st half points map");
    // 3 + 1 from Halftime — never the 0 + 1 an inning reader would take.
    expect(tileText(html, "final")).toBe("Final 4 points");
  });
});

describe("#8557 the first-five card during a baseball game", () => {
  const live = (history: Row[], home: number, away: number) =>
    render({ rows: LIVE_F5, status: "live", home, away, history });

  it("draws the running score as Actual while the first five are being played", () => {
    const html = live(
      [{ period: "Top 3rd", home_score: 2, away_score: 1, timestamp: "2026-09-25T02:21:38Z" }],
      2,
      1
    );

    expect(visibleText(html)).toContain("First 5 innings runs map");
    expect(tileText(html, "actual")).toBe("Actual 3 runs");
  });

  it("holds the `End 5th` score as the first five's Actual once the 6th starts", () => {
    const html = live(SEA_HISTORY.slice(0, 5), 4, 4);

    expect(visibleText(html)).toContain("First 5 innings runs map");
    // 4 + 3 at End 5th — not the 8 on the scoreboard in the 6th.
    expect(tileText(html, "actual")).toBe("Actual 7 runs");
  });

  it("control: in the 6th with no `End 5th` row it draws no Actual rather than a guess", () => {
    const html = live(
      SEA_HISTORY.slice(0, 5).filter((r) => r.period !== "End 5th"),
      4,
      4
    );

    expect(visibleText(html)).toContain("First 5 innings runs map");
    expect(tileCount(html, "actual")).toBe(0);
  });
});
