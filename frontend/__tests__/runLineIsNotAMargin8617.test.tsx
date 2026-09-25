/**
 * #8617 — THE RUN LINE IS NOT A PROJECTED MARGIN.
 *
 * `/events/15318166`, Mets @ Rangers, Final 3–1, read at 390px 2026-09-25
 * ~12:50Z. The game was priced 55% pregame, and the Score Differential chart's
 * green "Projected margin" line sat flat at +1.5 for the Rangers from the first
 * pitch, 0–0 in the top of the 1st. It read as "Rangers by 1.5" for a coin flip.
 *
 * The served projection is `projected_home_score - projected_away_score`, which
 * the backend solves from each sportsbook's spread point and total. For baseball
 * that point is the RUN LINE: a ±1.5 handicap whatever the matchup, with the
 * price doing the work. Every sportsbook on this game opened at +1.5 (5.0 – 3.5
 * on a total of 8.5; DraftKings' 4.8 – 3.2 is the same line on a total of 8,
 * each side rounded to one decimal).
 * In-game the books step it to ±2.5 / ±3.5, which is still a handicap and not a
 * median. #8613 fixed the stat model reading the same number as a margin; this
 * is the chart's half, and the page gate that opens the card.
 *
 * Fixture: `GET /api/events/15318166/history`, 2026-09-25 ~12:55Z. `history`,
 * `score_history` and `espn_history` are verbatim and complete.
 * `bookmaker_history` is TRIMMED to three of its nineteen books (draftkings,
 * fanduel, betmgm), values verbatim. The claim is about what those lines are,
 * not about how many there are.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "fs";
import { join } from "path";

import ScoreDifferentialChart from "@/components/ScoreDifferentialChart";
import { sportVocab } from "@/lib/marketMapUtils";
import { sportsbookProjectionDrawable } from "@/lib/scoreDifferentialHeading";

const MLB = JSON.parse(
  readFileSync(
    join(__dirname, "fixtures/runLineIsNotAMargin.15318166.mlb-final.3books.json"),
    "utf8"
  )
);

/** A trusted prediction-market implied spread, borrowed from #7660's live
 *  wire. Its arms are read off a threshold ladder, so they ARE margins, and
 *  #8617 must not take them down with the run line. */
const PM_LIVE = JSON.parse(
  readFileSync(join(__dirname, "fixtures/impliedSpread.14780544.live.json"), "utf8")
);

const EVENT_PAGE_SOURCE = readFileSync(
  join(__dirname, "../app/events/[id]/page.tsx"),
  "utf8"
);

type Point = { projected_home_score: number | null; projected_away_score: number | null };

function diffs(points: Point[]): number[] {
  return points
    .filter((p) => p.projected_home_score != null && p.projected_away_score != null)
    .map((p) => Math.round(((p.projected_home_score as number) - (p.projected_away_score as number)) * 10) / 10);
}

function seriesAttr(markup: string, attr: string): string | null {
  const m = markup.match(new RegExp(`${attr}="([^"]*)"`));
  return m ? m[1] : null;
}

function renderChart(
  wire: Record<string, unknown>,
  sportKey: string,
  overrides: Record<string, unknown> = {}
): string {
  return renderToStaticMarkup(
    React.createElement(ScoreDifferentialChart, {
      history: wire.history as never,
      homeTeam: wire.home_team as string,
      awayTeam: wire.away_team as string,
      commenceTime: wire.commence_time as string,
      scoreHistory: wire.score_history as never,
      espnHistory: wire.espn_history as never,
      bookmakerHistory: wire.bookmaker_history as never,
      eventStatus: wire.status as string,
      sportKey,
      pmSpreadData: wire.pm_spread_data as never,
      ...overrides,
    } as never)
  );
}

describe("#8617 — the wire holds a run line, not a margin", () => {
  it("strawman: the specimen is what the issue says it is", () => {
    expect(MLB.event_id).toBe(15318166);
    expect(MLB.home_team).toBe("Texas Rangers");
    expect(MLB.status).toBe("completed");
    expect(MLB.score_history.at(-1)).toMatchObject({ home_score: 3, away_score: 1 });

    // Every sportsbook's opening projection is the run line, +1.5 — within the
    // 0.1 the backend's per-side rounding can add (4.75 – 3.25 → 4.8 – 3.2).
    for (const book of ["draftkings", "fanduel", "betmgm"]) {
      expect(Math.abs(diffs(MLB.bookmaker_history[book])[0] - 1.5)).toBeLessThan(0.11);
    }
    // And the aggregate the green line is drawn from is +1.5 most of the game.
    const agg = diffs(MLB.history);
    expect(agg.length).toBeGreaterThan(200);
    expect(agg.filter((d) => d === 1.5).length / agg.length).toBeGreaterThan(0.4);
  });
});

describe("#8617 — the chart", () => {
  it("THE SHIP: an MLB card draws the played score and no sportsbook projection", () => {
    const markup = renderChart(MLB, "baseball_mlb");
    expect(seriesAttr(markup, "data-projected-series")).toBe("false");
    expect(seriesAttr(markup, "data-actual-series")).toBe("true");
    // The gray per-sportsbook lines are the same run line, one book at a time,
    // so their footnote goes with them.
    expect(markup).not.toContain("Each gray line is one of the sportsbooks");
    expect(markup).not.toContain("Score data is not available");
  });

  it("THE DIFFERENTIAL: identical bytes under a sport whose spread IS a margin still draw it", () => {
    // A gate keyed on the payload's shape, on `status`, or on the ±1.5 values
    // themselves passes the ship arm and fails this one.
    const markup = renderChart(MLB, "americanfootball_nfl");
    expect(seriesAttr(markup, "data-projected-series")).toBe("true");
    expect(markup).toContain("Each gray line is one of the sportsbooks");
  });

  it("CONTROL: prediction-market implied spreads survive on a live baseball game", () => {
    const markup = renderChart(MLB, "baseball_mlb", {
      eventStatus: "in_progress",
      isLive: true,
      pmSpreadData: PM_LIVE.pm_spread_data,
    });
    expect(seriesAttr(markup, "data-projected-series")).toBe("false");
    expect(seriesAttr(markup, "data-implied-spread-series")).toBe("polymarket");
  });

  it("CONTROL: a baseball game with no played score and only the run line renders no card body", () => {
    const markup = renderChart(MLB, "baseball_npb", { scoreHistory: [], espnHistory: [] });
    expect(markup).toContain("Score data is not available");
  });
});

describe("#8617 — the rule and its one reader on the page", () => {
  it("baseball says no; every other declared sport and the default keep the status quo", () => {
    for (const key of ["baseball_mlb", "baseball_npb", "baseball_kbo"]) {
      expect(sportVocab(key).sportsbookSpreadIsAMargin).toBe(false);
      expect(sportsbookProjectionDrawable(key)).toBe(false);
    }
    // Hockey's puck line has the same shape but no page specimen yet — named
    // here so a change to it is a decision, not a drift.
    for (const key of [
      "icehockey_nhl",
      "americanfootball_nfl",
      "basketball_nba",
      "soccer_epl",
      "tennis_atp_us_open",
      "esports",
      undefined,
    ]) {
      expect(sportsbookProjectionDrawable(key)).toBe(true);
    }
  });

  it("the event page's card gate asks the same question the chart does", () => {
    // Without it, a baseball game with no played score would open a card over
    // the chart's "not available" stub — the empty chrome L2-112 Item 4 bans.
    const gate = EVENT_PAGE_SOURCE.slice(
      EVENT_PAGE_SOURCE.indexOf("const hasScoreDiffData"),
      EVENT_PAGE_SOURCE.indexOf("const scoreDiffHeading")
    );
    expect(gate).toContain("sportsbookProjectionDrawable(event?.sport");
    expect(gate).toContain("projected_home_score != null");
  });
});
