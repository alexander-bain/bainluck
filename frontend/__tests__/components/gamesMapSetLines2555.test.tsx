/**
 * #2555 — A TENNIS GAMES MAP DRAWS ONLY THE MATCH'S GAME COUNT.
 *
 * `/events/15322596` (M15 Ann Arbor, Bonding v Mesarovic, 2026-10-01) served
 * four Polymarket `game_total` rows, all `period: null`, outcome "Over"/"Under":
 *
 *   Total Sets O/U 2.5        — a SETS line
 *   Set 1 Games O/U 8.5/9.5/10.5 — first-set-only game lines
 *
 * The Games map drew all four as one match ladder headed "PRE-GAME 3", and
 * while live its caption said the market "quotes games" over the sets line.
 * None of the four is the match's game count, so the card must not render —
 * and the page's `totalsMapRenders` (which the Score Differential note asks)
 * must give the same answer as the card.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";
import {
  gameTotalFitsMatchRail,
  gameTotalUnitOf,
  selectGameTotalRungs,
  sportVocab,
  totalsMapRenders,
} from "@/lib/marketMapUtils";

const TENNIS = sportVocab("tennis_atp_challenger");
const NBA = sportVocab("basketball_nba");
const MLB = sportVocab("baseball_mlb");

/** Verbatim from production `/api/events/15322596/game-markets`, 20:34Z. */
const SPECIMEN_TOTALS = [
  { threshold: 2.5, over_probability: 0.0045, source: "polymarket", market_type: "game_total", market_name: "Oliver Bonding vs. Marko Mesarovic: Total Sets O/U 2.5", outcome_name: "Under", is_winner: null, resolution_source: null, movement: 0.2705, period: null },
  { threshold: 8.5, over_probability: 0.0045, source: "polymarket", market_type: "game_total", market_name: "Bonding vs. Mesarovic: Set 1 Games O/U 8.5", outcome_name: "Over", is_winner: null, resolution_source: null, movement: -0.09, period: null },
  { threshold: 9.5, over_probability: 1.0, source: "polymarket", market_type: "game_total", market_name: "Bonding vs. Mesarovic: Set 1 Games O/U 9.5", outcome_name: "Over", is_winner: true, resolution_source: "clob_authoritative", movement: 0.0045, period: null },
  { threshold: 10.5, over_probability: 0.095, source: "polymarket", market_type: "game_total", market_name: "Bonding vs. Mesarovic: Set 1 Games O/U 10.5", outcome_name: "Under", is_winner: null, resolution_source: null, movement: null, period: null },
];

/** A real match game line beside them — the one row that belongs on the rail. */
const MATCH_GAMES = {
  threshold: 21.5, over_probability: 0.52, source: "polymarket", market_type: "game_total",
  market_name: "Bonding vs. Mesarovic: Total Games O/U 21.5", outcome_name: "Over",
  is_winner: null, resolution_source: null, movement: 0, period: null,
};

const SPREADS = [
  { market_name: "Bonding vs. Mesarovic: Game Handicap", outcome_name: "Oliver Bonding -2.5 games", threshold: 2.5, probability: 0.55, source: "kalshi", is_winner: null, resolution_source: null },
];

function markets(totals: unknown[]) {
  return {
    event_id: 15322596, home_team: "Oliver Bonding", away_team: "Marko Mesarovic",
    home_score: null, away_score: null, status: "live", player_props: [], team_totals: [],
    period_markets: [], matchups: [], other: [], pace: null, props_script: [],
    spreads: SPREADS, totals,
  };
}

function renderMaps(totals: unknown[]): string {
  return renderToStaticMarkup(
    <MarketMapSection
      gameMarkets={markets(totals) as never}
      eventStatus="live"
      homeTeam="Oliver Bonding"
      awayTeam="Marko Mesarovic"
      homeAbbr="BON"
      awayAbbr="MES"
      homeWinProb={0.8}
      awayWinProb={0.2}
      homeSpread={-2.5}
      overUnder={null as never}
      sportKey="tennis_atp_challenger"
    />
  ).replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
}

describe("#2555 the tennis Games map draws only match game lines", () => {
  it("reads the unit from the words around O/U, not from any unit word in the title", () => {
    expect(gameTotalUnitOf("Bonding vs. Mesarovic: Total Sets O/U 2.5")).toBe("sets");
    expect(gameTotalUnitOf("Bonding vs. Mesarovic: Total Games O/U 21.5")).toBe("games");
    expect(gameTotalUnitOf("Keys vs Zheng: Total Games")).toBe("games");
    // A postseason title carries "Game" and counts runs.
    expect(gameTotalUnitOf("Dodgers vs Padres Game 3: Total Runs O/U 7.5")).toBe("runs");
    expect(gameTotalUnitOf("Chiefs vs Bills: O/U 47.5")).toBeNull();
    expect(gameTotalUnitOf(undefined)).toBeNull();
  });

  it("refuses a single-set row and, on a two-unit sport, a row in the other unit", () => {
    expect([TENNIS.unit, TENNIS.scoreboardUnit]).toEqual(["games", "sets"]);
    expect(gameTotalFitsMatchRail("Bonding vs. Mesarovic: Set 1 Games O/U 8.5", TENNIS)).toBe(false);
    expect(gameTotalFitsMatchRail("Sinner vs Alcaraz: 2nd Set Total Games", TENNIS)).toBe(false);
    expect(gameTotalFitsMatchRail("Bonding vs. Mesarovic: Total Sets O/U 2.5", TENNIS)).toBe(false);
    expect(gameTotalFitsMatchRail("Bonding vs. Mesarovic: Total Games O/U 21.5", TENNIS)).toBe(true);
    expect(gameTotalFitsMatchRail("Match O/U 21.5", TENNIS)).toBe(true);
  });

  it("a single-unit sport keeps every row it kept before", () => {
    expect(NBA.scoreboardUnit).toBe("");
    expect(gameTotalFitsMatchRail("Dodgers vs Padres Game 3: Total Runs O/U 7.5", MLB)).toBe(true);
    expect(gameTotalFitsMatchRail("Chiefs vs Bills: O/U 47.5", NBA)).toBe(true);
    expect(gameTotalFitsMatchRail("Lakers vs Celtics: Total Games", NBA)).toBe(true);
    expect(gameTotalFitsMatchRail(null, NBA)).toBe(true);
    expect(gameTotalFitsMatchRail("Total Sets O/U 3.5", undefined)).toBe(true);
  });

  it("selects none of the specimen's four rows, and only the match line when one is served", () => {
    expect(selectGameTotalRungs(SPECIMEN_TOTALS, "live", TENNIS)).toEqual([]);
    const withMatch = selectGameTotalRungs([...SPECIMEN_TOTALS, MATCH_GAMES], "live", TENNIS);
    expect(withMatch.map((t) => t.threshold)).toEqual([21.5]);
  });

  it("strawman: without the rail unit the sets line is still drawn (the gate is load-bearing)", () => {
    expect(selectGameTotalRungs(SPECIMEN_TOTALS, "live").map((t) => t.threshold)).toEqual([2.5]);
  });

  it("the card renders no Games map from the specimen, and the page's predicate agrees", () => {
    const html = renderMaps(SPECIMEN_TOTALS);
    expect(html).not.toContain("Games map");
    expect(html).not.toMatch(/Over (2|8|9|10)\.5/);
    // The games handicap's own map stays; its caption is true there.
    expect(html).toContain("Game margin map");
    expect(totalsMapRenders(markets(SPECIMEN_TOTALS) as never, "live", TENNIS)).toBe(false);
  });

  it("with a real match line the card draws it alone, and the predicate agrees", () => {
    const html = renderMaps([...SPECIMEN_TOTALS, MATCH_GAMES]);
    expect(html).toContain("Games map");
    expect(html).toContain("Over 21.5");
    expect(html).not.toMatch(/Over (2|8|9|10)\.5/);
    expect(totalsMapRenders(markets([...SPECIMEN_TOTALS, MATCH_GAMES]) as never, "live", TENNIS)).toBe(true);
  });
});
