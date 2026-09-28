/**
 * #9307 — A SERVED UNDER ROW'S GRADE IS ALREADY ON THE OVER AXIS.
 *
 * Settled `/events/15316429`, León 2–1 FC Juárez, 1H 0–0. At 04:20Z both half
 * margin cards printed FINAL (`Tied`, `LEO by 1`); by 06:10Z 80 Polymarket
 * half rows had attached and both FINALs were gone. The route serves a totals
 * row's `is_winner` on the over axis whichever leg it came from (#6239,
 * `_settled_over_verdict`): stored market 62498004 "1st Half O/U 0.5" has
 * Under = won, served as the Under row's `is_winner: false` ("the over lost").
 * `halfRungRowGrade` flipped Under rows a second time, so no split of the final
 * agreed with every grade and #9108's half scores came back `null`.
 *
 * The fixture is the served `period_markets` verbatim, all 96 rows.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";
import { halfRungRowGrade, settledHalfScoresFromGrades, type PeriodTotalRow } from "@/lib/marketMapUtils";
import specimen from "../fixtures/settledHalfOverAxisUnderLeonJuarez9307.json";

const ROWS = specimen.period_markets as unknown as PeriodTotalRow[];
const HOME = specimen.home_team; // "León"
const AWAY = specimen.away_team; // "FC Juarez"

function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&[a-z#0-9]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function render(): string {
  return visibleText(
    renderToStaticMarkup(
      <MarketMapSection
        gameMarkets={
          {
            event_id: specimen.event_id,
            home_team: HOME,
            away_team: AWAY,
            home_score: specimen.home_score,
            away_score: specimen.away_score,
            status: "completed",
            player_props: [],
            team_totals: [],
            period_markets: ROWS,
            matchups: [],
            other: [],
            pace: null,
            props_script: [],
            spreads: [],
            totals: [],
          } as never
        }
        eventStatus="completed"
        homeTeam={HOME}
        awayTeam={AWAY}
        homeAbbr="LEO"
        awayAbbr="JUA"
        sportKey="soccer_mexico_ligamx"
      />
    )
  );
}

/** One half's margin card, from its title to the next card's. */
function halfCard(text: string, half: "1st" | "2nd"): string {
  const start = text.indexOf(`${half} half margin`);
  expect(start).toBeGreaterThanOrEqual(0);
  const ends = [
    text.indexOf("half margin", start + `${half} half margin`.length + 20),
    text.indexOf("Goals maps", start),
  ].filter((i) => i > start);
  return text.slice(start, ends.length ? Math.min(...ends) : undefined);
}

describe("#9307 over-axis Under rows on settled León–Juárez", () => {
  it("the specimen carries served Polymarket Under rows on the over axis", () => {
    const o05 = ROWS.filter(
      (r) => r.market_type === "half_total" && r.market_name === "Club León FC vs. FC Juárez: 1st Half O/U 0.5"
    );
    expect(o05.map((r) => [r.outcome_name, r.is_winner]).sort()).toEqual([
      ["Over", false],
      ["Under", false],
    ]);
  });

  it("a scoreless half's O/U 0.5 pair reads 'missed', not a contradiction", () => {
    const o05 = ROWS.filter(
      (r) => r.market_type === "half_total" && r.market_name === "Club León FC vs. FC Juárez: 1st Half O/U 0.5"
    );
    expect(halfRungRowGrade(o05, true)).toBe("missed");
  });

  it("the half scores come out of the grades as 0–0 then 2–1", () => {
    expect(settledHalfScoresFromGrades(ROWS, "completed", 2, 1, HOME, AWAY, "goals")).toEqual({
      h1Home: 0,
      h1Away: 0,
      h2Home: 2,
      h2Away: 1,
    });
  });

  it("each half margin card prints its FINAL", () => {
    const text = render();
    const first = halfCard(text, "1st");
    const second = halfCard(text, "2nd");
    expect(first).toMatch(/Final Tied/);
    expect(second).toMatch(/Final LEO by 1\b/);
    // #9286 stays paid on the same page: León's line is on the card.
    expect(first).toContain("LEO by 1.5+");
  });
});
