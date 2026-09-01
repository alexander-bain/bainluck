/**
 * A SPORT GETS FURNITURE THAT IS TRUE FOR IT (#2441).
 *
 * Alex, on `/events/15293846` — a US Open match — on 2026-08-31:
 *
 *     PRE-GAME BER +4.5 … Total: expected vs final — PRE-GAME 40 … Margin:
 *     expected vs final … WAW by 18+ / BER by 18+
 *
 *     Tennis has no point spread and no 40-point total. This is a generic event
 *     template applied to a sport it does not fit, and it is the clearest
 *     single tell that the page was not built for tennis.
 *
 * ═══ WHAT THE FIX ACTUALLY IS, AND WHAT THIS FILE THEREFORE HOLDS ═══
 *
 * Not "add tennis". The old `sportVocab` named three sports and **fell through
 * to points for everything else**, so the bug was the DEFAULT, and adding a
 * fourth branch would have left the next sport to be discovered by Alex the
 * same way.
 *
 * The polarity is inverted instead: a sport gets scoring furniture only by
 * being NAMED with its unit and its scale, and `UNSCORED_IN_POINTS` — what an
 * unrecognised key gets — declares `hasDerivedSpread: false`.
 *
 * So the load-bearing assertion in this file is not the tennis one. It is
 * **`an undeclared sport inherits nobody's units`**: that is the one that fails
 * if someone re-adds a points default, and it is the one that makes the fix
 * accrue to sports nobody has thought about yet, which is the acceptance
 * criterion Alex actually set for this whole issue set.
 *
 * ═══ WHY THE SECTIONS ARE NOT SUPPRESSED FOR TENNIS ═══
 *
 * A tennis match really does have a game-spread market (Kalshi quotes
 * `Berrettini -1.5 games`) and a game total (`Over 34.5 games`) — measured on
 * `/api/events/15293846/game-markets`, three of each. Those are true and worth
 * showing. What was false was the UNIT they were drawn in, the ±18 scale, and
 * `current_odds.home_spread` — a points figure a model derived from the
 * moneyline, which on this match was **-4.3** and rendered as `BER +4.5`.
 *
 * So the ladder survives and the fabricated marker does not. A guard that
 * asserted the whole section disappears would be pinning the wrong fix.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";
import { sportVocab, UNSCORED_IN_POINTS } from "@/lib/marketMapUtils";

function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&[a-z]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** The real shape of `/api/events/15293846/game-markets`, trimmed. */
function tennisMarkets() {
  return {
    event_id: 15293846,
    home_team: "Matteo Berrettini",
    away_team: "Stan Wawrinka",
    home_score: null,
    away_score: null,
    status: "closed",
    player_props: [],
    team_totals: [],
    period_markets: [],
    matchups: [],
    other: [],
    pace: null,
    props_script: [],
    spreads: [
      { market_name: "Matteo Berrettini vs Stan Wawrinka: Game Spread", outcome_name: "Matteo Berrettini -1.5 games", threshold: 1.5, probability: 0.72, source: "kalshi", is_winner: null, resolution_source: null },
      { market_name: "Matteo Berrettini vs Stan Wawrinka: Game Spread", outcome_name: "Matteo Berrettini -3.5 games", threshold: 3.5, probability: 0.55, source: "kalshi", is_winner: null, resolution_source: null },
      { market_name: "Matteo Berrettini vs Stan Wawrinka: Game Spread", outcome_name: "Stan Wawrinka -1.5 games", threshold: 1.5, probability: 0.21, source: "kalshi", is_winner: null, resolution_source: null },
    ],
    totals: [
      { threshold: 34.5, over_probability: 0.64, source: "kalshi", market_type: "game_total", market_name: "Matteo Berrettini vs Stan Wawrinka: Total Games", outcome_name: "Over 34.5 games", is_winner: null, resolution_source: null, movement: -0.035, period: null },
      { threshold: 39.5, over_probability: 0.52, source: "kalshi", market_type: "game_total", market_name: "Matteo Berrettini vs Stan Wawrinka: Total Games", outcome_name: "Over 39.5 games", is_winner: null, resolution_source: null, movement: 0, period: null },
    ],
  };
}

function renderTennis(overrides: Record<string, unknown> = {}) {
  return renderToStaticMarkup(
    <MarketMapSection
      gameMarkets={tennisMarkets() as never}
      eventStatus="closed"
      homeTeam="Matteo Berrettini"
      awayTeam="Stan Wawrinka"
      homeAbbr="BER"
      awayAbbr="WAW"
      homeWinProb={0.8411}
      awayWinProb={0.1589}
      // The exact derived value production served for this match.
      homeSpread={-4.3}
      overUnder={40.3}
      sportKey="tennis_atp_us_open"
      {...overrides}
    />
  );
}

describe("#2441 — the registry, not a default", () => {
  it("gives an UNDECLARED sport nobody else's units — the assertion the whole fix rests on", () => {
    // A sport key nothing in the registry matches. Before #2441 this returned
    // basketball's furniture: "points", and a rail reaching ±18.
    for (const key of ["cricket_ipl", "darts_pdc", "chess_candidates", "cycling_tour", ""]) {
      const v = sportVocab(key);
      expect(v).toEqual(UNSCORED_IN_POINTS);
      expect(v.unit).toBe("");
      expect(v.marginRange).toBe(6);
      // The one that matters: we do not draw a spread we invented for a sport
      // we have not described.
      expect(v.hasDerivedSpread).toBe(false);
    }
    expect(sportVocab(undefined).hasDerivedSpread).toBe(false);
  });

  it("declares tennis in games, at a tennis scale, with no derived spread", () => {
    const v = sportVocab("tennis_atp_us_open");
    expect(v.unit).toBe("games");
    expect(v.totalTitle).toBe("Games map");
    expect(v.marginRange).toBe(6);
    expect(v.hasDerivedSpread).toBe(false);
    expect(sportVocab("tennis_wta_us_open")).toEqual(v);
  });

  it("leaves the point sports exactly as they were", () => {
    // The regression that would be invisible: this ship must not quietly
    // renarrow basketball's rail or take its projection away.
    for (const key of ["basketball_nba", "americanfootball_nfl"]) {
      const v = sportVocab(key);
      expect(v.unit).toBe("points");
      expect(v.marginRange).toBe(18);
      expect(v.hasDerivedSpread).toBe(true);
    }
    for (const key of ["baseball_mlb", "icehockey_nhl", "soccer_epl"]) {
      const v = sportVocab(key);
      expect(v.marginRange).toBe(5);
      expect(v.hasDerivedSpread).toBe(true);
    }
    expect(sportVocab("baseball_mlb").unit).toBe("runs");
    expect(sportVocab("icehockey_nhl").unit).toBe("goals");
  });
});

/**
 * ⚠️ EVERY ASSERTION BELOW IS DELIBERATELY GRAMMAR-NEUTRAL.
 *
 * `program/ux-172` (#2442) is relabelling these same rungs from `BER +1.5` to
 * `BER by 1.5+` in the same review batch. The two branches merge clean by
 * `git merge-tree`, and a test here that pinned either WORDING would still go
 * red the moment the other landed — disjoint files colliding semantically.
 *
 * So this file asserts what #2441 actually owns — the UNIT, the SCALE, and
 * whether a derived spread is drawn at all — by matching the competitor and the
 * number without the connective between them. It passes on both grammars, and
 * it is #2442's own guard that pins #2442's wording.
 */
describe("#2441 — the rendered tennis page", () => {
  const settled = visibleText(renderTennis());
  const text = visibleText(renderTennis({ eventStatus: "scheduled" }));

  it("renders the section at all, and titles it in the sport's own unit", () => {
    // Otherwise every absence below is the emptiness of a component that
    // returned null, which would pass this file while shipping nothing.
    expect(text.length).toBeGreaterThan(40);
    expect(text).toContain("Game margin map");
    expect(settled.length).toBeGreaterThan(40);
  });

  it("never reaches 18 — the basketball rail Alex read", () => {
    for (const t of [text, settled]) {
      expect(t).not.toContain("18+");
      expect(t).not.toMatch(/\b18\b/);
      // And it DOES reach the tennis distance, so the absence above is a
      // narrower rail rather than no rail at all.
      expect(t).toMatch(/\b6\b/);
    }
  });

  it("never draws the derived points spread over a sport with no points", () => {
    // `homeSpread={-4.3}` goes in — the exact figure production's points model
    // produced for this match. Nothing resembling it may come out.
    for (const t of [text, settled]) {
      expect(t).not.toContain("4.3");
      expect(t).not.toMatch(/BER\D{0,6}4[.\d]*/);
    }
  });

  it("keeps every market a venue actually quoted", () => {
    // The half of the section that was TRUE. A fix that suppressed the
    // sections outright would pass every test above and fail this one — which
    // is why it is here. Matched without the connective, so #2442's relabel
    // does not turn this red.
    expect(text).toMatch(/BER\D{0,6}1\.5/);
    expect(text).toMatch(/BER\D{0,6}3\.5/);
    expect(text).toMatch(/WAW\D{0,6}1\.5/);
    // The real game totals survive too.
    expect(text).toContain("34.5");
    expect(text).toContain("39.5");
  });

  it("says games, and never points", () => {
    for (const t of [text, settled]) {
      expect(t).not.toMatch(/\bpoints?\b/i);
      expect(t).not.toMatch(/\bruns?\b/i);
    }
    expect(text).toMatch(/\bgames?\b/i);
  });
});

describe("#2441 — a point sport still gets its projection", () => {
  it("draws the derived spread where a derived spread is a real quantity", () => {
    const text = visibleText(
      renderToStaticMarkup(
        <MarketMapSection
          gameMarkets={
            {
              ...tennisMarkets(),
              home_team: "Los Angeles Lakers",
              away_team: "Boston Celtics",
              spreads: [
                { market_name: "Lakers vs Celtics: Spread", outcome_name: "Los Angeles Lakers -4.5", threshold: 4.5, probability: 0.52, source: "kalshi", is_winner: null, resolution_source: null },
                { market_name: "Lakers vs Celtics: Spread", outcome_name: "Boston Celtics -1.5", threshold: 1.5, probability: 0.41, source: "kalshi", is_winner: null, resolution_source: null },
              ],
              totals: [],
            } as never
          }
          eventStatus="scheduled"
          homeTeam="Los Angeles Lakers"
          awayTeam="Boston Celtics"
          homeAbbr="LAL"
          awayAbbr="BOS"
          homeWinProb={0.62}
          awayWinProb={0.38}
          homeSpread={-6}
          overUnder={220}
          sportKey="basketball_nba"
        />
      )
    );
    // The projection survives for the sport it is true for — this is the
    // over-correction guard, and it is why the tennis gate is a capability
    // rather than a deletion. Grammar-neutral for the same reason as above.
    expect(text).toMatch(/LAL\D{0,6}6\b/);
    // The full basketball rail, unchanged.
    expect(text).toContain("18+");
  });
});
