/**
 * #9315 — A SETTLED HALF MARGIN CARD NEEDS #5502'S TWO RUNGS, NOT ONE.
 *
 * Settled `/events/15316429`, León 2–1 FC Juárez, 1H 0–0, at 390px on
 * 2026-09-28 06:43Z. The 1st half margin card read
 *
 *   PRE-GAME  LEO by 1.5+        FINAL  Tied
 *
 * — León expected to win the first half by two, on a match whose full-game card
 * expected LEO by 1+ and whose goals card expected three goals in all. The only
 * priced 1st-half margin rung is Kalshi "Leon wins the 1H by more than 1.5
 * goals" at 0.16, a leftover last trade on a settled market (`is_winner:
 * false`); Juárez's is 0.02 and the Polymarket half spreads are graded 1.0 or
 * unpriced. One rung inside the 0.15–0.85 band passed `probabilitiesQuoteALine`
 * and `closest50` lifted it into a Pre-game tile.
 *
 * The half TOTALS card has refused exactly this since #5502 (one interior rung
 * after the whistle is settlement's leftover, a real line leaves two). The
 * margin twin never moved onto that rule; #9286 made León's accented rung parse
 * and exposed it here.
 *
 * The fixture is the served `period_markets` verbatim, all 96 rows (#9307's).
 * Tiles are counted through `data-tile`; every card in this section is one of
 * the four half maps, so the counts are theirs.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";
import { countInteriorRungs, type PeriodTotalRow } from "@/lib/marketMapUtils";
import specimen from "../fixtures/settledHalfOverAxisUnderLeonJuarez9307.json";

const ROWS = specimen.period_markets as unknown as PeriodTotalRow[];
const HOME = specimen.home_team; // "León"
const AWAY = specimen.away_team; // "FC Juarez"

const KALSHI_1H = "Leon vs Juarez: First Half Spread";

function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&[a-z#0-9]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function tileCount(html: string, key: string): number {
  return html.split(`data-tile="${key}"`).length - 1;
}

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

/** The 1st half margin card's text, up to the 2nd half card. */
function firstHalfCard(text: string): string {
  const start = text.indexOf("1st half margin");
  expect(start).toBeGreaterThanOrEqual(0);
  const end = text.indexOf("2nd half margin", start);
  expect(end).toBeGreaterThan(start);
  return text.slice(start, end);
}

/** The Kalshi 1H rungs repriced to a ladder that really quoted a line. */
function withQuotingKalshi1H(): PeriodTotalRow[] {
  return ROWS.map((r) =>
    r.market_type === "half_spread" && r.market_name === KALSHI_1H
      ? { ...r, probability: /^Leon/.test(r.outcome_name || "") ? 0.4 : 0.2 }
      : r
  );
}

describe("#9315 settled León–Juárez: one leftover rung is not a pre-game line", () => {
  it("the specimen's 1st half margin ladder has exactly one rung in the band", () => {
    const probs = ROWS.filter((r) => r.market_type === "half_spread" && r.period === "1H")
      .map((r) => r.probability)
      .filter((p): p is number => typeof p === "number");
    expect(countInteriorRungs(probs)).toBe(1);
    const kalshi = ROWS.filter((r) => r.market_name === KALSHI_1H).map((r) => [r.outcome_name, r.probability]);
    expect(kalshi).toContainEqual(["Leon wins the 1H by more than 1.5 goals", 0.16]);
  });

  it("the 1st half card prints FINAL Tied and its graded lines, and no Pre-game", () => {
    const html = render(ROWS);
    const card = firstHalfCard(visibleText(html));
    // Still here, still settled, still carrying León's rung (#9286) — as a
    // graded line under the final, which is what a 16% leftover is.
    expect(card).toMatch(/Final Tied/);
    expect(card).toMatch(/LEO by 1\.5\+ not cleared/);
    expect(card).not.toMatch(/Pre-game/i);
    expect(tileCount(html, "proj")).toBe(0);
    expect(tileCount(html, "final")).toBe(4);
  });

  it("CONTROL: the same settled page whose 1H ladder DID quote keeps its Pre-game", () => {
    // Two rungs in the band — #5143/#5488's finished-and-quoting control. A fix
    // keyed on `isDone` alone deletes this tile too and fails here.
    const html = render(withQuotingKalshi1H());
    const card = firstHalfCard(visibleText(html));
    expect(tileCount(html, "proj")).toBe(1);
    expect(card).toMatch(/Pre-game/);
    expect(card).toMatch(/Final Tied/);
  });

  it("CONTROL: the same rows on a game still in play keep #7639's one-rung reading", () => {
    // The settled count is scoped to a finished GAME. In play, a finished half
    // with one interior rung is #5502's quoting case and keeps its marker; the
    // 2nd half (0.01 / unpriced) has none and draws none.
    const html = render(ROWS, "live");
    expect(tileCount(html, "proj")).toBe(1);
    expect(firstHalfCard(visibleText(html))).toMatch(/LEO by 1\.5\+/);
  });
});
