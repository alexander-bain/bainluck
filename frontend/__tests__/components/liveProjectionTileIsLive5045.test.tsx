/**
 * #5045 — ON A LIVE CARD, `PRE-GAME` AND `PROJECTION` ARE TWO DIFFERENT NUMBERS.
 *
 * ═══ THE DEFECT, AND WHY ITS FILED DIAGNOSIS IS NOW INVERTED ═══
 *
 * The margin map's live arm built both tiles from one variable, so they could
 * never disagree — a card whose whole grammar is "where it's heading vs what
 * was expected" printed one number twice and invited the reader to compare a
 * value with itself.
 *
 * #5045 was filed against the code as it stood on 9/10, where that one variable
 * was the LIVE derived spread: the `Projection` label was honest and `Pre-game`
 * was the lie, and a pre-game number was seen to change teams mid-game.
 * #5414 then repointed it at the frozen opening line. That fixed `Pre-game`
 * and handed the same defect to the other tile: a pre-game quantity wearing a
 * forward-looking word. **The lie changed sides rather than going away**, which
 * is why the issue's own two options no longer read correctly against the file.
 *
 * ═══ THE SPECIMEN ═══
 *
 * Production, 2026-09-12 13:50Z, `/events/15297956` — Genoa 0-1 Frosinone,
 * live at 19', served under sport key `soccer_italy_serie_a`. Payload and
 * frame read in the SAME command, because every number on this card moves and
 * two reads minutes apart would be a transition, not a disagreement:
 *
 *   | source                          | value | what the card should say |
 *   |---------------------------------|-------|--------------------------|
 *   | `opening_odds.spread`           | -0.5  | PRE-GAME `GEN by 0.5+`   |
 *   | `current_odds.spread`           | +0.5  | PROJECTION `FRO by 0.5+` |
 *   | `current_odds.home_probability` | 0.2958 (card header read `FRO 66%`) |
 *   | projected score                 | 1.0 — 1.5                            |
 *
 * The card printed `GEN by 0.5+` in BOTH tiles: it named Genoa as the projected
 * winner on a screen whose own header said Frosinone 66% and whose own ACTUAL
 * said `FRO by 1+`. Three of the four numbers on one card said Frosinone.
 *
 * The `1st half` margin map beside it read `FRO by 1.5+` — correct, off its own
 * live ladder. That is the working control on the same screen, and the shape
 * the fix copies.
 *
 * ⚠️ It is NOT a sign bug. The comment on #5045 hypothesising that `projValue`
 * was inverted or mis-sourced is refuted by the stored value itself:
 * `opening_home_spread` is `-0.5`, so `-(-0.5)` is `+0.5`, so home, so `GEN`.
 * The arithmetic was right all along and the tense was wrong.
 *
 * ═══ WHAT EACH TEST IS FOR ═══
 *
 * The first pair is the specimen, and the `not.toMatch` in it is the assertion
 * that goes red on master. The rest are CONTROLS, because every arm of this
 * branch can be made to pass by deleting a tile: the `pre` and `done` arms must
 * be untouched, tennis must keep the one tile it is entitled to, and each tile
 * must still appear alone when only its own number exists.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";

function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&#x27;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&[a-z]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

const spreadRung = (matchup: string, outcome: string, probability: number) => ({
  market_name: `${matchup}: Game Spread`,
  outcome_name: outcome,
  threshold: null,
  probability,
  source: "kalshi",
  is_winner: null,
  resolution_source: null,
});

/**
 * Event 15297956 — Genoa (home) v Frosinone (away), live 0-1.
 *
 * The ladder is priced so the closest-to-even rung is `Genoa -1.5`. That
 * matters: it is a THIRD candidate answer, distinct from both the opening
 * (-0.5) and the current (+0.5) line, so a test that reads `GEN by 1.5+` has
 * caught the rung fallback leaking rather than either tense.
 */
function genoaFrosinone(overrides: Record<string, unknown> = {}) {
  const m = "Genoa vs Frosinone";
  return {
    event_id: 15297956,
    home_team: "Genoa",
    away_team: "Frosinone",
    home_score: 0,
    away_score: 1,
    status: "live",
    player_props: [],
    team_totals: [],
    period_markets: [],
    matchups: [],
    other: [],
    pace: null,
    props_script: [],
    spreads: [
      spreadRung(m, "Genoa -1.5", 0.49),
      spreadRung(m, "Genoa -2.5", 0.31),
      spreadRung(m, "Genoa -3.5", 0.14),
    ],
    totals: [],
    ...overrides,
  };
}

function renderGenoa(props: Record<string, unknown> = {}, eventStatus = "live") {
  return visibleText(
    renderToStaticMarkup(
      <MarketMapSection
        gameMarkets={genoaFrosinone({ status: eventStatus }) as never}
        eventStatus={eventStatus}
        homeTeam="Genoa"
        awayTeam="Frosinone"
        homeAbbr="GEN"
        awayAbbr="FRO"
        homeWinProb={0.2958}
        awayWinProb={0.7042}
        sportKey="soccer_italy_serie_a"
        {...props}
      />
    )
  );
}

/**
 * The same card as a tennis match, which declares `hasDerivedSpread: false`
 * (#2441). Live, so it reaches the same arm.
 */
function renderTennisLive(props: Record<string, unknown> = {}) {
  const m = "Alexander Zverev vs Karen Khachanov";
  return visibleText(
    renderToStaticMarkup(
      <MarketMapSection
        gameMarkets={
          {
            event_id: 15309206,
            home_team: "Alexander Zverev",
            away_team: "Karen Khachanov",
            home_score: null,
            away_score: null,
            status: "live",
            player_props: [],
            team_totals: [],
            period_markets: [],
            matchups: [],
            other: [],
            pace: null,
            props_script: [],
            spreads: [
              spreadRung(m, "Alexander Zverev -2.5 games", 0.52),
              spreadRung(m, "Alexander Zverev -5.5 games", 0.34),
            ],
            totals: [],
          } as never
        }
        eventStatus="live"
        homeTeam="Alexander Zverev"
        awayTeam="Karen Khachanov"
        homeAbbr="ZVE"
        awayAbbr="KHA"
        homeWinProb={0.7966}
        awayWinProb={0.2034}
        sportKey="tennis_atp_us_open"
        {...props}
      />
    )
  );
}

describe("#5045 — the live Projection tile holds a live number", () => {
  it("THE FIX: the two tiles name the two different teams the two tenses imply", () => {
    const text = renderGenoa({ openingHomeSpread: -0.5, homeSpread: 0.5 });
    // The card drew at all. Without this every assertion below would pass
    // against a map that never rendered.
    expect(text).toContain("Goal margin map");
    expect(text).toMatch(/Pre-game\s+GEN by 0\.5\+/);
    expect(text).toMatch(/Projection\s+FRO by 0\.5\+/);
  });

  it("THE DEFECT: the Projection tile never restates the pre-game number", () => {
    // This is the assertion that is red on master, and it is the reader's
    // complaint stated exactly: the projected winner is not the side the live
    // market has at 30%.
    const text = renderGenoa({ openingHomeSpread: -0.5, homeSpread: 0.5 });
    expect(text).not.toMatch(/Projection\s+GEN by/);
    // …and the pre-game tile did not drift onto the live number either. The
    // fix is a split, not a swap.
    expect(text).not.toMatch(/Pre-game\s+FRO by/);
  });

  it("the ACTUAL tile is untouched, so the card still reads as one sentence", () => {
    const text = renderGenoa({ openingHomeSpread: -0.5, homeSpread: 0.5 });
    expect(text).toMatch(/Actual\s+FRO by 1\+/);
  });

  it("NEGATIVE CONTROL — no live spread: PRE-GAME alone, and no invented Projection", () => {
    // A tile with nothing true to say says nothing (notice 34). The failure
    // this guards is the tempting one: falling back to `projValue` so the
    // layout keeps its third tile, which is the defect restored.
    const text = renderGenoa({ openingHomeSpread: -0.5 });
    expect(text).toMatch(/Pre-game\s+GEN by 0\.5\+/);
    expect(text).not.toContain("Projection");
    // Not a deleted card: rail and ladder both still drawn.
    expect(text).toContain("Goal margin map");
    expect(text).toContain("GEN by 1.5+"); // the honest ladder rung
  });

  it("CONTROL — no opening line: PROJECTION alone, drawn from the live spread", () => {
    // The other side of the control above, or "one guard per tile" degenerates
    // into "the Projection tile depends on the opening line", which is the
    // coupling being removed.
    const text = renderGenoa({ homeSpread: 0.5 });
    expect(text).toMatch(/Projection\s+FRO by 0\.5\+/);
    expect(text).not.toContain("Pre-game");
  });

  it("a live spread of exactly 0.0 is a line, not the absence of one", () => {
    // `0` is falsy and every test between the payload and the marker is
    // `!= null`. A pick'em live at level must read Tied, not lose its tile.
    const text = renderGenoa({ openingHomeSpread: -0.5, homeSpread: 0 });
    expect(text).toMatch(/Projection\s+Tied/);
  });

  it("CONTROL — tennis keeps its Pre-game tile and draws no live projection", () => {
    // #2441: this page may not invent a spread for a sport with no points. The
    // opening line is a quote a venue published and survives; the derived live
    // one is the number that ruling governs, so the honest pair here is one
    // tile, not two.
    const text = renderTennisLive({ openingHomeSpread: -5.5, homeSpread: -7.9 });
    expect(text).toMatch(/Pre-game\s+ZVE by 5\.5\+/);
    expect(text).not.toContain("Projection");
    expect(text).not.toContain("ZVE by 7.9+");
  });

  it("CONTROL — the scheduled arm is untouched", () => {
    // Before kickoff the two tenses coincide, the marker is `Projection`, and
    // #5414's rule that the opening line outranks the latest snapshot still
    // owns that arm. If this goes red the change has leaked out of `live`.
    const text = renderGenoa({ openingHomeSpread: -0.5, homeSpread: 0.5 }, "scheduled");
    expect(text).toMatch(/Projection\s+GEN by 0\.5\+/);
    expect(text).not.toMatch(/Projection\s+FRO by 0\.5\+/);
  });

  it("CONTROL — the settled arm gains no Projection tile", () => {
    // The `done` arm draws PRE-GAME and FINAL. A live snapshot's spread is
    // emphatically not a thing to show after the whistle, and #5414's tense
    // rule is what keeps it out.
    const text = renderGenoa({ openingHomeSpread: -0.5, homeSpread: 0.5 }, "completed");
    expect(text).toMatch(/Pre-game\s+GEN by 0\.5\+/);
    expect(text).not.toContain("Projection");
    expect(text).not.toContain("FRO by 0.5+");
  });
});
