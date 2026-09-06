/**
 * #2555 item 3 — "1 games".
 *
 * The shopper's card, verbatim from production (`/events/15303395`, Potapova v
 * Anisimova, live, 1st set, ESPN board `Anisimova 1 / Potapova 0`):
 *
 *   GAMES MAP
 *     Games map
 *     ACTUAL              PRE-GAME
 *     1 games             20
 *
 * Items 1 (wrong unit) and 2 (wrong scale) of that issue were fixed by ux/1034
 * B5 and #3161 and are NOT re-tested here — the re-measure on 2026-09-05
 * confirmed both, and a test that re-asserts them would just be a second owner
 * of somebody else's invariant. This is item 3, which was still live.
 *
 * ── THE CAUSE ────────────────────────────────────────────────────────────────
 *
 * `SportScoringVocab` has carried `unitSingular` since #2441 — `"game"` beside
 * `"games"`, `"run"` beside `"runs"`. `withUnit` simply never read it, so every
 * card that reached exactly one printed the plural.
 *
 * ── WHY THE HELPER AND BOTH CALL SITES ───────────────────────────────────────
 *
 * `withUnit` has two consumers that reach a reader, and they were written
 * eight months apart:
 *
 *   1. `MarketMapSection` — the ACTUAL / half-total tiles, which is where the
 *      shopper saw it;
 *   2. `ScoreDifferentialChart`'s unit note (#3240) — "Keys has won 1 games to
 *      Zheng's 0", a full sentence, where a plural after "1" is louder still.
 *
 * A unit test on the helper alone would pass while a call site formatted its
 * own string inline, so both are rendered here. And the helper's own arms cover
 * what the call sites cannot reach: `UNSCORED_IN_POINTS`, whose `unit` AND
 * `unitSingular` are both deliberately empty so an undeclared sport prints the
 * number a market quoted and no unit this file guessed.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";
import ScoreDifferentialChart from "@/components/ScoreDifferentialChart";
import { withUnit, sportVocab, UNSCORED_IN_POINTS } from "@/lib/marketMapUtils";

const TENNIS = sportVocab("tennis_wta_us_open");
const BASEBALL = sportVocab("baseball_mlb");

function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&#x27;/g, "'")
    .replace(/&#39;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&[a-z]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

describe("#2555 item 3 — withUnit reads the singular the vocab already carries", () => {
  it("exactly one takes the SINGULAR", () => {
    expect(withUnit(1, TENNIS)).toBe("1 game");
    expect(withUnit(1, BASEBALL)).toBe("1 run");
  });

  it("everything that is not one keeps the plural", () => {
    // 0 is plural in English, and so is every count above one.
    expect(withUnit(0, TENNIS)).toBe("0 games");
    expect(withUnit(2, TENNIS)).toBe("2 games");
    expect(withUnit(21, TENNIS)).toBe("21 games");
    // Not an integer: "1.5 games" is correct, and must not singularise just
    // because it starts with a 1.
    expect(withUnit(1.5, TENNIS)).toBe("1.5 games");
  });

  it("a pre-formatted STRING is treated as its number", () => {
    // Callers pass both; `Number()` is what makes the two agree.
    expect(withUnit("1", TENNIS)).toBe("1 game");
    expect(withUnit("2", TENNIS)).toBe("2 games");
  });

  it("an UNDECLARED sport still prints a bare number and no invented unit", () => {
    // `UNSCORED_IN_POINTS.unit` is deliberately "" — the reason this helper
    // exists at all. Singularising must not resurrect a unit or a double space.
    expect(withUnit(1, UNSCORED_IN_POINTS)).toBe("1");
    expect(withUnit(7, UNSCORED_IN_POINTS)).toBe("7");
    expect(withUnit(1, UNSCORED_IN_POINTS)).not.toContain(" ");
  });
});

/* ── call site 1: the tile the shopper photographed ────────────────────────── */

const ONE_GAME_LINE = { sets: [[1, 0]] as [number, number][], home_games: 1, away_games: 0, source: "espn" };
const MANY_GAMES_LINE = { sets: [[6, 4]] as [number, number][], home_games: 6, away_games: 4, source: "espn" };

function totalRow(threshold: number, over: number) {
  return {
    threshold,
    over_probability: over,
    source: "kalshi",
    market_type: "game_total",
    market_name: `Total Games O/U ${threshold}`,
    outcome_name: "Over",
    is_winner: null,
    resolution_source: null,
    movement: 0,
    period: null,
  };
}

function renderMap(linescore: object) {
  return visibleText(
    renderToStaticMarkup(
      <MarketMapSection
        gameMarkets={{
          event_id: 15303395,
          home_team: "Anna Potapova",
          away_team: "Amanda Anisimova",
          home_score: null,
          away_score: null,
          status: "live",
          player_props: [], team_totals: [], period_markets: [], matchups: [], other: [],
          pace: null, props_script: [], spreads: [],
          totals: [totalRow(20.5, 0.63), totalRow(22.5, 0.38)],
        } as never}
        eventStatus="live"
        homeTeam="Anna Potapova"
        awayTeam="Amanda Anisimova"
        homeAbbr="POT"
        awayAbbr="ANI"
        homeWinProb={0.4}
        awayWinProb={0.6}
        homeSpread={-1.5}
        sportKey="tennis_wta_us_open"
        linescore={linescore as never}
      />
    )
  );
}

describe("#2555 item 3 — the Games map tile", () => {
  it("a match one game in says '1 game', not '1 games'", () => {
    const text = renderMap(ONE_GAME_LINE);

    expect(text).toContain("1 game");
    expect(text).not.toContain("1 games"); // <- the defect, verbatim
  });

  it("CONTROL — a match ten games in still says 'games'", () => {
    // A fix that simply switched the vocab to the singular would break this.
    const text = renderMap(MANY_GAMES_LINE);

    expect(text).toContain("10 games");
    expect(text).not.toContain("10 game ");
  });
});

/* ── call site 2: the unit note under the differential chart (#3240) ───────── */

const HISTORY = [
  { timestamp: "2026-09-05T15:05:00Z", home_probability: 0.55, away_probability: 0.45, projected_home_score: 11.4, projected_away_score: 10.2, bookmaker_count: 8 },
  { timestamp: "2026-09-05T15:25:00Z", home_probability: 0.61, away_probability: 0.39, projected_home_score: 11.9, projected_away_score: 9.8, bookmaker_count: 9 },
];

function renderNote(linescore: object) {
  return visibleText(
    renderToStaticMarkup(
      <ScoreDifferentialChart
        history={HISTORY as never}
        homeTeam="Madison Keys"
        awayTeam="Qinwen Zheng"
        commenceTime="2026-09-05T15:00:00Z"
        isLive
        eventStatus="live"
        currentHomeScore={1}
        currentAwayScore={0}
        sportKey="tennis_wta_us_open"
        linescore={linescore as never}
        // The note only names the count when there is no totals map to defer to.
        totalsMapPresent={false}
      />
    )
  );
}

describe("#2555 item 3 — the differential chart's unit note", () => {
  it("the sentence says 'has won 1 game', not 'has won 1 games'", () => {
    const text = renderNote({ sets: [[1, 0]] as [number, number][], home_games: 1, away_games: 0, source: "espn" });

    expect(text).toContain("1 game");
    expect(text).not.toContain("1 games");
  });

  it("CONTROL — the same sentence keeps the plural at six", () => {
    const text = renderNote({ sets: [[6, 4]] as [number, number][], home_games: 6, away_games: 4, source: "espn" });

    expect(text).toContain("6 games");
  });
});
