/**
 * #9318 — A SETTLED HALF MARGIN BAND ANSWERS TO THE SAME COUNT AS ITS PRE-GAME TILE.
 *
 * Settled `/events/15316429`, León 2–1 FC Juárez, 1H 0–0, at 390px on
 * 2026-09-28 07:05Z, after #9315 went live. The Pre-game tile was gone, but the
 * 1st half margin card still read "1st half margin distribution" over a rail
 * shaded pale at JUA by 1 and dark at LEO by 1, beside `FINAL Tied`, with its
 * graded lines only in the tap popover. The band is built from the same rows
 * #9315 refused as a line: Polymarket half spreads graded 1.0 and Kalshi's
 * leftover 0.16. Settlement prices make a shape, so `densityDrawsShape` alone
 * said yes.
 *
 * The fixture is the served `period_markets` verbatim (#9307's 96 rows).
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";
import type { PeriodTotalRow } from "@/lib/marketMapUtils";
import specimen from "../fixtures/settledHalfOverAxisUnderLeonJuarez9307.json";

const ROWS = specimen.period_markets as unknown as PeriodTotalRow[];
const HOME = specimen.home_team;
const AWAY = specimen.away_team;

const KALSHI_1H = "Leon vs Juarez: First Half Spread";

function render(rows: PeriodTotalRow[], status: "completed" | "live" = "completed"): string {
  return renderToStaticMarkup(
    <MarketMapSection
      gameMarkets={
        {
          event_id: specimen.event_id,
          home_team: HOME,
          away_team: AWAY,
          home_score: specimen.home_score,
          away_score: specimen.away_score,
          status,
          player_props: [],
          team_totals: [],
          period_markets: rows,
          matchups: [],
          other: [],
          pace: null,
          props_script: [],
          spreads: [],
          totals: [],
        } as never
      }
      eventStatus={status}
      homeTeam={HOME}
      awayTeam={AWAY}
      homeAbbr="LEO"
      awayAbbr="JUA"
      sportKey="soccer_mexico_ligamx"
    />
  );
}

/** The 1st half margin card's MARKUP, up to the 2nd half card. */
function firstHalfCard(html: string): string {
  const start = html.indexOf("1st half margin");
  expect(start).toBeGreaterThanOrEqual(0);
  const end = html.indexOf("2nd half margin", start);
  expect(end).toBeGreaterThan(start);
  return html.slice(start, end);
}

const segments = (html: string) => html.split("data-density-segment=").length - 1;
const inlineLadder = (html: string) => html.includes('data-inline-ladder="1"');

/** The Kalshi 1H rungs repriced to a ladder that really quoted a line (#9315's control). */
function withQuotingKalshi1H(): PeriodTotalRow[] {
  return ROWS.map((r) =>
    r.market_type === "half_spread" && r.market_name === KALSHI_1H
      ? { ...r, probability: /^Leon/.test(r.outcome_name || "") ? 0.4 : 0.2 }
      : r
  );
}

describe("#9318 settled León–Juárez: settlement leftovers are not a distribution", () => {
  it("the 1st half card paints no band, says its lines settled, and prints them inline", () => {
    const card = firstHalfCard(render(ROWS));
    expect(segments(card)).toBe(0);
    expect(card).not.toMatch(/margin distribution/);
    expect(card).toMatch(/lines settled/);
    expect(inlineLadder(card)).toBe(true);
    expect(card).toMatch(/Tied/);
  });

  it("CONTROL: the same settled page whose 1H ladder DID quote keeps its band", () => {
    // A gate keyed on `isDone` alone blanks this band too and fails here.
    const card = firstHalfCard(render(withQuotingKalshi1H()));
    expect(segments(card)).toBe(12);
    expect(card).toMatch(/1st half margin distribution/);
    expect(inlineLadder(card)).toBe(false);
  });

  it("CONTROL: the same rows on a game still in play keep their band", () => {
    const card = firstHalfCard(render(ROWS, "live"));
    expect(segments(card)).toBe(12);
    expect(card).toMatch(/1st half margin distribution/);
  });
});
