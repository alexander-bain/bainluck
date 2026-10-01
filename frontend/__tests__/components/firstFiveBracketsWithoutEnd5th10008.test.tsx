/**
 * #10008 — A FINISHED MLB GAME'S FIRST-FIVE CARD SAYS WHAT THE FIRST FIVE
 * PRODUCED EVEN WHEN ESPN'S `End 5th` MOMENT WAS NEVER SAMPLED.
 *
 * Not a regression of #8557, which reads the `End 5th` row when it exists.
 *
 * Seen on production 2026-10-01 05:09Z at 390px: `/events/15321946`, Cubs 1 –
 * 4 Padres, FINAL. The full-game card read FINAL 5 runs; the "First 5 innings
 * runs map" below it drew an empty rail and three `Over N` last quotes. The
 * served history (12 rows, below verbatim) has no `End 5th`, but `Bottom 5th`
 * 1–4 and then `Bottom 6th` 1–4 pin the first five at 1–4: runs only go up.
 *
 * ## What makes this suite non-vacuous
 *
 * Every arm renders the REAL `MarketMapSection` over the specimen's own
 * `half_total` rows (`/api/events/15321946/game-markets`, 2026-10-01) and
 * asserts the card by title first, so a vanished card fails. The controls each
 * move ONE input so the two samples no longer agree (a run lands between them),
 * which kills a fix that takes either neighbouring inning instead of the bracket.
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

const HOME = "San Diego Padres";
const AWAY = "Chicago Cubs";
const THRESHOLDS = [2.5, 5.5, 6.5];

/** The specimen's `half_total` rows exactly as production served them. */
const SETTLED_F5 = [
  [2.5, "Over", 1.0, false, 0.32],
  [2.5, "Under", 1.0, null, -0.32],
  [5.5, "Under", 0.0005, null, 0.3295],
  [5.5, "Over", 0.0005, false, -0.3295],
  [6.5, "Under", 0.0005, null, 0.2245],
  [6.5, "Over", 0.0005, false, -0.2245],
].map(([threshold, outcome_name, over_probability, is_winner, movement]) => ({
  market_type: "half_total",
  market_name: `Chicago Cubs vs. San Diego Padres: 1st 5 Innings O/U ${threshold}`,
  outcome_name,
  threshold,
  over_probability,
  probability: null,
  period: null,
  source: "polymarket",
  is_winner,
  resolution_source: "clob_authoritative",
  movement,
}));

/** #8483's live ladder shape: still quoting. */
const LIVE_F5 = [
  [2.5, 0.9],
  [5.5, 0.3],
  [6.5, 0.2],
].map(([threshold, over]) => ({
  market_type: "half_total",
  market_name: `Chicago Cubs vs. San Diego Padres: 1st 5 Innings O/U ${threshold}`,
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

/** `/api/events/15321946/history` → `espn_history`, all 12 rows, verbatim. */
const CHC_SD_HISTORY: Row[] = [
  { timestamp: "2026-10-01T02:21:15.972096+00:00", period: "Bottom 1st", away_score: 0, home_score: 0 },
  { timestamp: "2026-10-01T02:49:16.697891+00:00", period: "Top 3rd", away_score: 0, home_score: 2 },
  { timestamp: "2026-10-01T02:53:16.373057+00:00", period: "Top 3rd", away_score: 0, home_score: 2 },
  { timestamp: "2026-10-01T03:02:16.261781+00:00", period: "Bottom 3rd", away_score: 0, home_score: 2 },
  { timestamp: "2026-10-01T03:09:16.789833+00:00", period: "Top 4th", away_score: 0, home_score: 2 },
  { timestamp: "2026-10-01T03:22:16.461928+00:00", period: "Bottom 4th", away_score: 1, home_score: 2 },
  { timestamp: "2026-10-01T03:30:16.251891+00:00", period: "Bottom 4th", away_score: 1, home_score: 4 },
  { timestamp: "2026-10-01T03:47:16.571386+00:00", period: "Bottom 5th", away_score: 1, home_score: 4 },
  { timestamp: "2026-10-01T04:06:17.253860+00:00", period: "Bottom 6th", away_score: 1, home_score: 4 },
  { timestamp: "2026-10-01T05:00:18.081898+00:00", period: "Top 9th", away_score: 1, home_score: 4 },
  { timestamp: "2026-10-01T05:01:17.699823+00:00", period: "Top 9th", away_score: 1, home_score: 4 },
  { timestamp: "2026-10-01T05:02:00+00:00", period: "Final", away_score: 1, home_score: 4 },
];

/** The same history with the `Bottom 6th` sample one Padres run higher. */
const RUN_BETWEEN_SAMPLES: Row[] = CHC_SD_HISTORY.map((r, i) =>
  i > CHC_SD_HISTORY.findIndex((x) => x.period === "Bottom 5th") ? { ...r, home_score: (r.home_score ?? 0) + 1 } : r
);

function render(opts: { rows: unknown[]; status: string; home: number; away: number; history: Row[] }): string {
  return renderToStaticMarkup(
    <MarketMapSection
      gameMarkets={
        {
          event_id: 15321946,
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
      homeAbbr="SD"
      awayAbbr="CHC"
      sportKey="baseball_mlb"
      espnHistory={opts.history}
    />
  );
}

describe("#10008 the first-five card on a finished game with no `End 5th` sample", () => {
  it("the specimen really has no `End 5th` row (the defect's precondition)", () => {
    expect(CHC_SD_HISTORY.some((r) => r.period === "End 5th")).toBe(false);
  });

  it("draws Final 5 runs from `Bottom 5th` 1–4 and `Bottom 6th` 1–4", () => {
    const html = render({ rows: SETTLED_F5, status: "completed", home: 4, away: 1, history: CHC_SD_HISTORY });
    const text = visibleText(html);

    expect(text).toContain("First 5 innings runs map");
    expect(tileCount(html, "final")).toBe(1);
    expect(tileText(html, "final")).toBe("Final 5 runs");
    expect(text).not.toContain("Last quote for going over");
  });

  it("grades each line against those 5 runs", () => {
    const text = visibleText(
      render({ rows: SETTLED_F5, status: "completed", home: 4, away: 1, history: CHC_SD_HISTORY })
    );

    expect(text).toContain("Each line vs the final");
    expect(verdictsOf(text, THRESHOLDS)).toEqual(["2.5:cleared", "5.5:not cleared", "6.5:not cleared"]);
  });

  it("control: a run between the two samples leaves the card on its quotes, not a guess", () => {
    expect(RUN_BETWEEN_SAMPLES.find((r) => r.period === "Bottom 5th")?.home_score).toBe(4);
    expect(RUN_BETWEEN_SAMPLES.find((r) => r.period === "Bottom 6th")?.home_score).toBe(5);
    const html = render({ rows: SETTLED_F5, status: "completed", home: 5, away: 1, history: RUN_BETWEEN_SAMPLES });
    const text = visibleText(html);

    expect(text).toContain("First 5 innings runs map");
    expect(tileCount(html, "final")).toBe(0);
    expect(text).toContain("Last quote for going over");
  });
});

describe("#10008 the first-five card live in the 7th with no `End 5th` sample", () => {
  const throughSeventh = CHC_SD_HISTORY.slice(0, 9);

  it("holds the bracketed 1–4 as the first five's Actual", () => {
    const html = render({ rows: LIVE_F5, status: "live", home: 4, away: 1, history: throughSeventh });

    expect(visibleText(html)).toContain("First 5 innings runs map");
    expect(tileText(html, "actual")).toBe("Actual 5 runs");
  });

  it("control: a scoreboard one run higher than the 6th's sample is still pinned by that sample", () => {
    const html = render({ rows: LIVE_F5, status: "live", home: 6, away: 1, history: throughSeventh });

    // 4 + 1 — never the 7 on the scoreboard.
    expect(tileText(html, "actual")).toBe("Actual 5 runs");
  });

  it("control: with only the scoreboard past the 5th and it moved, it draws no Actual", () => {
    const html = render({ rows: LIVE_F5, status: "live", home: 6, away: 1, history: CHC_SD_HISTORY.slice(0, 8).concat({ period: "Top 7th", timestamp: "2026-10-01T04:20:00Z" }) });

    expect(visibleText(html)).toContain("First 5 innings runs map");
    expect(tileCount(html, "actual")).toBe(0);
  });
});
