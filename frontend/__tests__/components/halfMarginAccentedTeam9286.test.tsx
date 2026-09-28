/**
 * #9286 — AN ACCENTED TEAM'S MARGIN RUNGS LAND ON ITS OWN SIDE.
 *
 * Mystery-shopped on production at 390px, 2026-09-28 04:06Z, settled
 * `/events/15316429`, León 2–1 FC Juárez, Liga MX. The event stores `León`;
 * Kalshi writes `"Leon wins the 1H by more than 1.5 goals"`. The side check
 * lowercased both and never folded the accent, so `"león"` matched nothing and
 * every León rung was dropped: the 1H band leaned Juárez off one Juárez rung,
 * and the 2H "each line vs the final" ladder listed only `JUA by 1.5+`.
 *
 * The fixture is the served `period_markets` verbatim. Each render arm checks
 * that the Juárez line is still there, so a card that vanished cannot pass as
 * "León present".
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";
import { parseSpreadOutcome, parseSpreadRungs, type PeriodTotalRow } from "@/lib/marketMapUtils";
import specimen from "../fixtures/settledHalfMarginLeonJuarez9286.json";

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

/** The text of one half's margin card, from its title to the next card. */
function halfCard(text: string, half: "1st" | "2nd"): string {
  const start = text.indexOf(`${half} half margin`);
  expect(start).toBeGreaterThanOrEqual(0);
  const next = text.indexOf("half margin", start + `${half} half margin`.length + 20);
  const goals = text.indexOf("Goals maps", start);
  const ends = [next, goals].filter((i) => i > start);
  return text.slice(start, ends.length ? Math.min(...ends) : undefined);
}

describe("#9286 accented team names on the margin map", () => {
  it("the specimen is the accented-home, unaccented-venue shape", () => {
    expect(HOME).toBe("León");
    const kalshiLeon = ROWS.filter((r) => r.market_type === "half_spread" && r.outcome_name.startsWith("Leon "));
    expect(kalshiLeon).toHaveLength(2);
  });

  it("a Kalshi 'Leon' rung parses as León's (home) side", () => {
    const r = parseSpreadOutcome("Leon wins the 1H by more than 1.5 goals", 0.16, "kalshi", HOME, AWAY);
    expect(r).not.toBeNull();
    expect(r!.isHome).toBe(true);
    expect(r!.threshold).toBe(1.5);
    expect(r!.team).toBe(HOME);
  });

  it("folds the other direction too: venue 'Juárez' against a stored unaccented 'Juarez'", () => {
    const r = parseSpreadOutcome("Juárez -1.5", 0.3, "kalshi", "Club León", "Juarez City");
    expect(r).not.toBeNull();
    expect(r!.isHome).toBe(false);
  });

  it("a Polymarket numberless leg folds accents on both the cover team and the outcome", () => {
    const rungs = parseSpreadRungs(
      [
        { outcome_name: "León", probability: 0.4, source: "polymarket", market_name: "Spread: Leon (-1.5)" },
        { outcome_name: "FC Juarez", probability: 0.6, source: "polymarket", market_name: "Spread: Leon (-1.5)" },
      ] as never,
      HOME,
      AWAY,
      "goals"
    );
    expect(rungs).toHaveLength(1);
    expect(rungs[0].isHome).toBe(true);
    expect(rungs[0].probability).toBeCloseTo(0.4);
  });

  it("each half's ladder lists León's line beside Juárez's", () => {
    const text = render();
    for (const half of ["1st", "2nd"] as const) {
      const card = halfCard(text, half);
      expect(card).toContain("JUA by 1.5+");
      expect(card).toContain("LEO by 1.5+");
    }
  });
});
