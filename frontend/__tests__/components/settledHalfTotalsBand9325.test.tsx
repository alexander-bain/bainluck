/**
 * #9325 — A SETTLED HALF TOTALS BAND ANSWERS TO THE SAME COUNT AS ITS PRE-GAME TILE.
 *
 * Settled `/events/15316429`, León 2–1 FC Juárez, 2H 3 goals, at 390px on
 * 2026-09-28 07:30Z, after #9318 went live on the half margin cards. The 2nd
 * half goals map read "2nd half goals distribution" over a rail shaded dark at
 * 3 and pale at 2 and 4, beside `FINAL 3 goals`, with no Pre-game tile and its
 * graded lines only in the tap popover. Every 2H `half_total` row served was
 * graded 1.0/0.0 — game, team and corners totals disagreeing — so
 * `densityDrawsShape` alone said yes while #5502's settled count said no.
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

const KALSHI_2H = "Leon vs Juarez: Second Half Total";

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

/** The 2nd half goals card's MARKUP, to the end of the section. */
function secondHalfGoalsCard(html: string): string {
  const start = html.indexOf("2nd half goals");
  expect(start).toBeGreaterThanOrEqual(0);
  return html.slice(start);
}

const segments = (html: string) => html.split("data-density-segment=").length - 1;
const inlineLadder = (html: string) => html.includes('data-inline-ladder="1"');

/** The 2H rungs repriced to a ladder that really quoted a line. */
function withQuoting2H(): PeriodTotalRow[] {
  const price: Record<number, number> = { 0.5: 0.9, 1.5: 0.7, 2.5: 0.45, 3.5: 0.25, 4.5: 0.1, 5.5: 0.04 };
  return ROWS.map((r) => {
    if (r.market_type !== "half_total" || r.period !== "2H") return r;
    const p = price[Number(r.threshold)];
    return p == null ? r : { ...r, over_probability: p };
  });
}

describe("#9325 settled León–Juárez: graded half totals are not a distribution", () => {
  it("the 2nd half goals card paints no band, says its lines settled, and prints them inline", () => {
    const card = secondHalfGoalsCard(render(ROWS));
    expect(segments(card)).toBe(0);
    expect(card).not.toMatch(/goals distribution/);
    expect(card).toMatch(/lines settled/);
    expect(inlineLadder(card)).toBe(true);
    expect(card).toMatch(/3 goals/);
  });

  it("CONTROL: the same settled page whose 2H ladder DID quote keeps its band", () => {
    // A gate keyed on `isDone` alone blanks this band too and fails here.
    const card = secondHalfGoalsCard(render(withQuoting2H()));
    expect(segments(card)).toBeGreaterThan(0);
    expect(card).toMatch(/2nd half goals distribution/);
    expect(inlineLadder(card)).toBe(false);
  });

  it("CONTROL: a quoting 2H ladder on a game still in play keeps its band", () => {
    const card = secondHalfGoalsCard(render(withQuoting2H(), "live"));
    expect(segments(card)).toBeGreaterThan(0);
    expect(card).toMatch(/2nd half goals distribution/);
  });

  it("the Kalshi 2H ladder in the specimen is graded, not quoting (fixture sanity)", () => {
    const kalshi = ROWS.filter((r) => r.market_name === KALSHI_2H);
    expect(kalshi.length).toBeGreaterThan(0);
    for (const r of kalshi) expect([0, 1]).toContain((r as { over_probability?: number }).over_probability);
  });
});
