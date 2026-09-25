/**
 * #8617 (web Sportsbooks-table half) — "5 / 3" ON A COIN FLIP IS THE RUN LINE.
 *
 * A sportsbook's `projected_*_score` is solved from its spread point and
 * total, and for baseball that point is the RUN LINE: a ±1.5 handicap whatever
 * the matchup. #8621 stopped the Score Differential chart drawing it as a
 * margin; authority's producer fix (PR #8644) stops the poller STORING it, so
 * upcoming cards withhold on their own. What that cannot reach is a game the
 * poller has stopped visiting: every settled MLB page keeps its stored rows,
 * and the event page's Sportsbooks table printed them per book under
 * "(proj. score)". The table now asks the chart's question,
 * `sportsbookProjectionDrawable`.
 *
 * Fixture: `GET /api/events/15317642` (Rangers, completed 2-7) and
 * `GET /api/events?sport=americanfootball_nfl` row 14782154, 2026-09-25,
 * `bookmaker_odds` TRIMMED to the first three books (values verbatim). The NFL
 * row is the control: a football spread IS a margin and keeps printing.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import BookmakerTable from "@/components/BookmakerTable";
import type { BookmakerOddsDetail } from "@/lib/types";
import FIXTURE from "./fixtures/projScoreIsNotTheRunLine8617.json";

interface Row {
  sport: string;
  status: string;
  home_team: string;
  away_team: string;
  bookmaker_odds: BookmakerOddsDetail[];
}

const rows = FIXTURE as unknown as Record<string, Row>;
const MLB = rows["15317642"]; // settled; betanysports home 0.50, stored 4.8 – 3.2
const NFL = rows["14782154"]; // Texans @ Colts, stored 20.2 – 22.2

function table(event: Row, sportKey: string | undefined): string {
  return renderToStaticMarkup(
    <BookmakerTable
      bookmakerOdds={event.bookmaker_odds}
      homeTeam={event.home_team}
      awayTeam={event.away_team}
      sportKey={sportKey}
    />
  );
}

describe("#8617 — the specimen is what the issue says it is", () => {
  it("a settled MLB page serves a coin-flip book with a two-run projected margin", () => {
    expect(MLB.sport).toBe("baseball_mlb");
    expect(MLB.status).toBe("completed");
    const coinFlip = MLB.bookmaker_odds.find((b) => b.home_probability === 0.5)!;
    expect(Math.abs(coinFlip.projected_home_score! - coinFlip.projected_away_score!)).toBeGreaterThanOrEqual(1.5);
  });

  it("strawman: with no sport the table prints it", () => {
    expect(table(MLB, undefined)).toContain("(proj. score)");
  });
});

describe("#8617 — the event page's Sportsbooks table", () => {
  it("prints no projected scores for baseball", () => {
    const html = table(MLB, "baseball_mlb");
    expect(html).not.toContain("proj. score");
    expect(html).not.toContain('title="Projected score"');
    // The prices are still there: only the scoreline goes.
    expect(html).toContain("50.0%");
  });

  it("control: football keeps them", () => {
    const html = table(NFL, "americanfootball_nfl");
    expect(html).toContain("(proj. score)");
    expect(html).toContain('title="Projected score"');
  });

  it("the page hands the table its sport", () => {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const src: string = require("fs").readFileSync(
      require("path").join(__dirname, "../app/events/[id]/page.tsx"),
      "utf8"
    );
    const call = src.slice(src.indexOf("<BookmakerTable"), src.indexOf("/>", src.indexOf("<BookmakerTable")));
    expect(call).toContain("sportKey={event.sport");
  });
});
