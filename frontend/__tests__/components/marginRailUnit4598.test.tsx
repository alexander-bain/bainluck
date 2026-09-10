/**
 * #4598 — THE GAME MARGIN MAP STOPS DRAWING A SET SPREAD ON A GAMES AXIS.
 *
 * Read on production, 2026-09-09 19:24 PT, `/events/15308439` at 390px — the
 * US Open men's semi-final, Tiafoe (home) v Shelton (away), hours before it is
 * played. Two numbers on ONE card:
 *
 *   > Game margin map                                  SHE 73%
 *   > Expected margin distribution
 *   >   PROJECTION
 *   >   TIA by 1.5+
 *   >   SHE by 6+ ──────────── 0 ─────●────── TIA by 6+
 *
 * The hero of the same page reads Tiafoe **27%**. The card projects the player
 * it gives a 27% chance of winning to win by a game and a half.
 *
 * ── WHERE THE 1.5 CAME FROM (measured, `/api/events/15308439/game-markets`) ──
 *
 *     Ben Shelton wins by over 1.5 sets    0.305   kalshi
 *     Frances Tiafoe wins by over 1.5 sets 0.185   kalshi
 *     Ben Shelton -1.5 games               0.185   kalshi
 *     Ben Shelton -4.5 games               0.185   kalshi
 *     Ben Shelton -7.5 games               0.185   kalshi
 *
 * `parseSpreadOutcome` read the side and the last number and nothing else, so
 * `wins by over 1.5 SETS` and `-1.5 GAMES` both keyed `A|1.5`. Two prices 12
 * points apart on what the ladder believed was one rung, so
 * `collapseDuplicateRungs` withheld it — correctly, given what it was told.
 * That deleted the only real GAME rung near the middle and left three rungs at
 * 0.185, of which the first in source order is `Frances Tiafoe wins by over
 * 1.5 sets`. Tennis declares `hasDerivedSpread: false` (#2441), so the marker
 * comes from that fallback, and the rail printed a SET margin in GAMES.
 *
 * ── WHY THE FIX IS A UNIT AND NOT A SIGN CHECK ───────────────────────────────
 *
 * "Suppress the marker when it disagrees with the favourite" would have hidden
 * this one and kept the underlying fault: a ladder that folds two questions
 * into one rung mis-shades its band, withholds real rungs, and would happily
 * print `TIA by 1.5+` on a card where Tiafoe WAS favourite. The rung either
 * belongs on a rail measured in games or it does not.
 *
 * `unit: null` — every points sport, `"Lakers -4.5"` — is "not stated" and is
 * kept, or this fix empties every NBA and NFL margin map. That case is the
 * control at the foot of this file, and it is a real control: it exercises the
 * same call with the same rail and asserts the rung survives.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";
import {
  parseSpreadOutcome,
  spreadRungMatchesRail,
  sportVocab,
} from "@/lib/marketMapUtils";

function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&#x27;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&[a-z]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** Event 15308439 as production served it, trimmed to the fields these maps read. */
function tiafoeShelton(overrides: Record<string, unknown> = {}) {
  const spread = (outcome: string, probability: number) => ({
    market_name: outcome.includes("sets")
      ? "Frances Tiafoe vs Ben Shelton: Set Spread"
      : "Frances Tiafoe vs Ben Shelton: Game Spread",
    outcome_name: outcome,
    threshold: null,
    probability,
    source: "kalshi",
    is_winner: null,
    resolution_source: null,
  });
  return {
    event_id: 15308439,
    home_team: "Frances Tiafoe",
    away_team: "Ben Shelton",
    home_score: null,
    away_score: null,
    status: "scheduled",
    player_props: [],
    team_totals: [],
    period_markets: [],
    matchups: [],
    other: [],
    pace: null,
    props_script: [],
    // Source order matters and is production's: the set rungs come first, which
    // is why the tie-break among the three 0.185 rungs landed on Tiafoe.
    spreads: [
      spread("Ben Shelton wins by over 1.5 sets", 0.305),
      spread("Frances Tiafoe wins by over 1.5 sets", 0.185),
      spread("Ben Shelton -1.5 games", 0.185),
      spread("Ben Shelton -4.5 games", 0.185),
      spread("Ben Shelton -7.5 games", 0.185),
    ],
    totals: [
      {
        threshold: 34.5,
        over_probability: 0.695,
        source: "kalshi",
        market_type: "game_total",
        market_name: "Frances Tiafoe vs Ben Shelton: Total Games",
        outcome_name: "Over 34.5 games",
        is_winner: null,
        resolution_source: null,
        movement: 0,
        period: null,
      },
    ],
    ...overrides,
  };
}

function renderSF(overrides: Record<string, unknown> = {}) {
  return visibleText(
    renderToStaticMarkup(
      <MarketMapSection
        gameMarkets={tiafoeShelton(overrides) as never}
        eventStatus="scheduled"
        homeTeam="Frances Tiafoe"
        awayTeam="Ben Shelton"
        homeAbbr="TIA"
        awayAbbr="SHE"
        homeWinProb={0.275}
        awayWinProb={0.725}
        homeSpread={4.5}
        overUnder={39.9}
        sportKey="tennis_atp_us_open"
      />
    )
  );
}

describe("#4598 — a rung belongs to the rail's own unit", () => {
  it("THE DEFECT: the projection named the player the hero gives 27%", () => {
    const text = renderSF();
    // The card really rendered — without this the assertion below could pass
    // against a map that was never drawn.
    expect(text).toContain("Game margin map");
    // The set rung is gone, so the marker is a GAME rung and it names the
    // favourite the rest of the page names.
    expect(text).not.toContain("TIA by 1.5+");
    expect(text).toContain("SHE by 1.5+");
  });

  it("the marker never contradicts the win probability on this payload", () => {
    const text = renderSF();
    const projection = /Projection\s+(TIA|SHE|Tied) by/i.exec(text.replace(/\s+/g, " "));
    expect(projection).not.toBeNull();
    // Shelton is 72.5% on this card; a projection naming Tiafoe is the defect.
    expect(projection![1]).toBe("SHE");
  });

  it("the ladder stops mixing set rungs into a games rail", () => {
    const text = renderSF();
    // Three game rungs at 1.5 / 4.5 / 7.5 remain, all Shelton's…
    expect(text).toContain("SHE by 4.5+");
    expect(text).toContain("SHE by 7.5+");
    // …and the LADDER lists no Tiafoe margin, because the venue quoted none in
    // games. Read the ladder only: `TIA by 6+` is the rail's right-hand END
    // LABEL, it is correct, and a bare `not.toContain("TIA by")` would delete
    // the axis to satisfy itself.
    const ladder = text.slice(text.indexOf("Chance of winning by"));
    expect(ladder).toContain("SHE by 1.5+");
    expect(ladder).not.toMatch(/TIA by \d/);
  });

  it("parseSpreadOutcome reports the unit the venue quoted, or null", () => {
    const p = (outcome: string) =>
      parseSpreadOutcome(outcome, 0.5, "kalshi", "Frances Tiafoe", "Ben Shelton");
    expect(p("Ben Shelton -1.5 games")!.unit).toBe("games");
    expect(p("Ben Shelton wins by over 1.5 sets")!.unit).toBe("sets");
    // A singular is reported plural, so it can be compared with the vocab's
    // own `unit` without a second spelling rule.
    expect(p("Ben Shelton wins by 1 game")!.unit).toBe("games");
    // The points sports state nothing, which is NOT the same as stating points.
    expect(p("Ben Shelton -4.5")!.unit).toBeNull();
  });

  /**
   * THE CONTROL, and it has to be at the RENDER to be one.
   *
   * A control's job here is to fail if this fix empties a points sport's rail,
   * which means it must be able to RUN against the code before the fix. The
   * two assertions below it call `spreadRungMatchesRail` — a new export — so
   * against the old code they throw rather than pass, and a test that cannot
   * execute the old path is not a fence around it however control-shaped it
   * reads (ux/1165's `a2c32f61`, the same trap from the other end). This one
   * renders a basketball card through the same component and asserts the rung
   * survives; it passes on BOTH arms, which is what makes it evidence.
   */
  it("THE CONTROL — a points card's rail is untouched, before and after", () => {
    const nbaSpread = (outcome: string, probability: number) => ({
      market_name: "Lakers vs. Celtics: Point Spread",
      outcome_name: outcome,
      threshold: null,
      probability,
      source: "kalshi",
      is_winner: null,
      resolution_source: null,
    });
    const text = visibleText(
      renderToStaticMarkup(
        <MarketMapSection
          gameMarkets={
            tiafoeShelton({
              home_team: "Los Angeles Lakers",
              away_team: "Boston Celtics",
              spreads: [
                nbaSpread("Los Angeles Lakers -4.5", 0.44),
                nbaSpread("Boston Celtics -4.5", 0.38),
                nbaSpread("Los Angeles Lakers -9.5", 0.22),
              ],
              totals: [],
            }) as never
          }
          eventStatus="scheduled"
          homeTeam="Los Angeles Lakers"
          awayTeam="Boston Celtics"
          homeAbbr="LAL"
          awayAbbr="BOS"
          homeWinProb={0.55}
          awayWinProb={0.45}
          homeSpread={-4.5}
          overUnder={220}
          sportKey="basketball_nba"
        />
      )
    );
    expect(text).toContain("Margin map");
    expect(text).toContain("LAL by 4.5+");
    expect(text).toContain("LAL by 9.5+");
    expect(text).toContain("BOS by 4.5+");
  });

  it("a rung that states no unit is kept on every rail", () => {
    const lakers = parseSpreadOutcome("Los Angeles Lakers -4.5", 0.5, "kalshi", "Los Angeles Lakers", "Boston Celtics")!;
    expect(lakers.unit).toBeNull();
    expect(spreadRungMatchesRail(lakers, sportVocab("basketball_nba").unit)).toBe(true);
    // …and on a rail whose sport we have not declared, so `UNSCORED_IN_POINTS`
    // keeps showing exactly what a venue quoted and nothing else.
    const cricket = parseSpreadOutcome("India -1.5 runs", 0.5, "kalshi", "India", "Australia")!;
    expect(cricket.unit).toBe("runs");
    expect(spreadRungMatchesRail(cricket, sportVocab("cricket_ipl").unit)).toBe(true);
  });

  it("and a games rung is refused by a runs rail, which is the whole rule", () => {
    const rung = parseSpreadOutcome("Ben Shelton -1.5 games", 0.5, "kalshi", "Frances Tiafoe", "Ben Shelton")!;
    expect(spreadRungMatchesRail(rung, sportVocab("tennis_atp").unit)).toBe(true);
    expect(spreadRungMatchesRail(rung, sportVocab("baseball_mlb").unit)).toBe(false);
  });
});
