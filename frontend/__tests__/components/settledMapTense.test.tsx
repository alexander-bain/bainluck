/**
 * #3136 — A FINISHED MATCH PAGE STOPS PROMISING A NUMBER IT WILL NEVER HAVE,
 * AND ONE CARD STOPS BEING ANNOUNCED AS SEVERAL.
 *
 * Alex, phone-width LOOK of `/events/15301243` (Wu 0–3 Alcaraz, FINAL, played
 * the day before):
 *
 *   > GAMES MAPS
 *   >   Games map
 *   >   The scoreboard reports sets, this market quotes games —
 *   >   we do not hold the games played yet.
 *   >   PRE-GAME 29
 *
 *   > 1. `PRE-GAME` is the only reading shown, on a match that finished
 *   >    yesterday.
 *   > 2. "we do not hold the games played **yet**" — the *yet* is a promise
 *   >    about a match still in progress. This one is complete.
 *   > 3. The section heading is `GAMES MAPS`, plural, over a single card.
 *
 * ── WHAT THIS SUITE COVERS, AND WHAT IT DELIBERATELY DOES NOT ────────────────
 *
 * Points 2 and 3. **Point 1 is not fixed and is not asserted here**, because
 * the number it wants does not exist in anything this page fetches. Measured
 * against production on 2026-09-05, on Alex's own event:
 *
 *     /api/events/15301243            home_score 0, away_score 3   (SETS)
 *     /api/events/15301243/history    espn_history      0 entries
 *                                     score_history     4 entries, all SETS
 *                                     period_markers    0 entries
 *
 * There is no games-played count on this page to show, so a `FINAL` marker
 * would have to be invented — which is the exact defect ux/1034 B5 removed.
 * That half is filed on #3136 as blocked on the backend serving the tennis
 * line score. What ships is the two halves that need no new data: the page
 * stops making a promise nothing will keep, and stops miscounting itself.
 *
 * ── AND THEN POINT 1 SHIPPED TOO (live/073) ─────────────────────────────────
 *
 * The backend the paragraph above is waiting on landed: the tennis authority
 * pass writes ESPN's per-set line onto the event and `/api/events/{id}` serves
 * it as `linescore`, so `6-3, 6-4, 6-1` — 26 games — is a number this page
 * holds rather than one it would have to invent. The last describe block below
 * is point 1, and it keeps the arm above as its control: with no line, the
 * card says exactly what it says today, in the tense #3136 gave it.
 *
 * ── THE CONTROLS ARE THE SUITE ───────────────────────────────────────────────
 *
 * Every assertion runs against a second arm that must NOT change:
 *
 *   - tense:   the same fixture rendered LIVE still says "yet". A tense fix
 *              that fired on every status would pass every FINAL assertion
 *              below and quietly tell an in-play reader the count is never
 *              coming.
 *   - heading: a column holding TWO cards is still plural. A blanket
 *              singularisation would pass the one-card assertions and break
 *              every NFL page, which has full-game + 1H + 2H.
 *   - sport:   a point sport prints no mismatch sentence at all.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";
import { mapColumnHeading, playedCountAbsence, sportVocab } from "@/lib/marketMapUtils";

function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&[a-z]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Event 15301243's own `game-markets` body, trimmed to the fields these maps
 * read, taken verbatim from production on 2026-09-05.
 *
 * The two `game_total` rows are the REAL ones and they are kept as served —
 * including the `threshold: 1.0` on a market named `Set 1 Games O/U 10.5`,
 * which is a backend threshold-parse bug filed separately. It is left in on
 * purpose: this fixture's job is to be the page Alex looked at, not a tidied
 * version of it, and the heading/tense behaviour must hold on the real thing.
 */
function markets() {
  return {
    event_id: 15301243,
    home_team: "Wu Yibing",
    away_team: "Carlos Alcaraz",
    home_score: 0,
    away_score: 3,
    status: "completed",
    player_props: [],
    team_totals: [],
    period_markets: [],
    matchups: [],
    other: [],
    pace: null,
    props_script: [],
    spreads: [],
    totals: [
      { threshold: 1.0, over_probability: 0.0005, source: "polymarket", market_type: "game_total", market_name: "Wu vs. Alcaraz: Set 1 Games O/U 10.5", outcome_name: "Under", is_winner: true, resolution_source: "clean_resolution", movement: 0.2395, period: null },
      { threshold: 3.5, over_probability: 0.0005, source: "polymarket", market_type: "game_total", market_name: "Yibing Wu vs. Carlos Alcaraz: Total Sets O/U 3.5", outcome_name: "Under", is_winner: null, resolution_source: null, movement: 0.4845, period: null },
    ],
  };
}

/** The same body plus a 1H total, so the totals column holds TWO cards. */
function marketsWithHalf() {
  return {
    ...markets(),
    period_markets: [
      { threshold: 9.5, over_probability: 0.55, probability: 0.55, source: "kalshi", market_type: "half_total", market_name: "Set 1 Total Games", outcome_name: "Over 9.5 games", period: "1H" },
      { threshold: 10.5, over_probability: 0.38, probability: 0.38, source: "kalshi", market_type: "half_total", market_name: "Set 1 Total Games", outcome_name: "Over 10.5 games", period: "1H" },
    ],
  };
}

/**
 * The line `/api/events/15301243` serves since live/073, verbatim: ESPN's
 * competition 182723 in OUR home/away order, and our row has Wu at home.
 *
 * 8 games to 18 — 26 played, against the 29 the market quoted pre-game.
 */
const WU_ALCARAZ_LINE = {
  sets: [[3, 6], [4, 6], [1, 6]] as [number, number][],
  home_games: 8,
  away_games: 18,
  source: "espn",
};

function renderMaps(
  sportKey: string,
  eventStatus: string,
  // `object`, not `ReturnType<typeof markets>`: the base fixture's empty arrays
  // infer as `never[]`, so the two-card variant below cannot satisfy it.
  body: object = markets(),
  linescore: typeof WU_ALCARAZ_LINE | null = null,
) {
  return renderToStaticMarkup(
    <MarketMapSection
      gameMarkets={body as never}
      eventStatus={eventStatus}
      homeTeam="Wu Yibing"
      awayTeam="Carlos Alcaraz"
      homeAbbr="WY"
      awayAbbr="CA"
      homeWinProb={0.01}
      awayWinProb={0.99}
      homeSpread={6.5}
      overUnder={29}
      sportKey={sportKey}
      linescore={linescore}
    />
  );
}

describe("#3136 — the promise, in the match's own tense", () => {
  it("a FINISHED match is not told the count is still coming", () => {
    const text = visibleText(renderMaps("tennis_atp_us_open", "completed"));

    // The card is still here and still says which two units it refuses to
    // mix — this is a tense fix, not another suppression.
    expect(text).toContain("The scoreboard reports sets, this market quotes games");
    expect(text).toContain("we did not record the games played");

    // The promise is gone. Asserted on the whole rendered card rather than on
    // the sentence alone: the word must not survive anywhere on it.
    expect(text).not.toContain("yet");
  });

  it("an IN-PLAY match still is — the control", () => {
    const text = visibleText(renderMaps("tennis_atp_us_open", "live"));
    expect(text).toContain("we do not hold the games played yet");
    expect(text).not.toContain("we did not record");
  });

  it("says nothing of the sort on a point sport — the control", () => {
    const text = visibleText(renderMaps("basketball_nba", "completed"));
    expect(text).not.toContain("The scoreboard reports");
    expect(text).not.toContain("games played");
  });

  /**
   * The helper, directly. Both surfaces that owe this sentence call it, and the
   * empty-unit arm is the one an undeclared sport would otherwise hit — a bare
   * `the  played` with a double space, the same class #2441 fixed for titles.
   */
  it("puts the clause in one place, and survives an undeclared unit", () => {
    expect(playedCountAbsence("games", true)).toBe("we did not record the games played");
    expect(playedCountAbsence("games", false)).toBe("we do not hold the games played yet");
    expect(playedCountAbsence("", true)).toBe("we did not record the played count");
    expect(playedCountAbsence("", false)).toBe("we do not hold the played count yet");
  });
});

describe("#3136 — a column heading counts its cards", () => {
  it("a single-card totals column is singular", () => {
    const text = visibleText(renderMaps("tennis_atp_us_open", "completed"));
    // The tennis totals column holds exactly one card (no halves in tennis).
    expect(text).toContain("Games map");
    expect(text).not.toContain("Games maps");
  });

  it("a two-card totals column is still plural — the control", () => {
    const text = visibleText(
      renderMaps("tennis_atp_us_open", "completed", marketsWithHalf())
    );
    expect(text).toContain("Games maps");
  });

  /**
   * The helper, over every declared vocabulary plus the undeclared fallback.
   *
   * The singular is the DECLARED title rather than the plural with an `s`
   * chopped off, so a title that does not end in " map" cannot be mangled;
   * the plural keeps #2442's construction verbatim.
   */
  it("pluralises from the declared title, never by mangling it", () => {
    for (const key of [
      "tennis_atp_us_open", "baseball_mlb", "icehockey_nhl",
      "soccer_epl", "basketball_nba", "americanfootball_nfl", "cricket_ipl",
    ]) {
      const vocab = sportVocab(key);
      expect(mapColumnHeading(vocab.totalTitle, 1)).toBe(vocab.totalTitle);
      expect(mapColumnHeading(vocab.marginTitle, 1)).toBe(vocab.marginTitle);
      expect(mapColumnHeading(vocab.totalTitle, 3)).toMatch(/ maps$/);
      expect(mapColumnHeading(vocab.marginTitle, 3)).toMatch(/ maps$/);
    }

    // Zero cards never reaches a heading (the column does not render), but the
    // helper must not invent a plural for it either.
    expect(mapColumnHeading("Games map", 0)).toBe("Games map");
    expect(mapColumnHeading("Games map", 2)).toBe("Games maps");
    // A title with no " map" suffix is left alone rather than sliced.
    expect(mapColumnHeading("Scoring", 2)).toBe("Scoring maps");
  });
});

/**
 * live/073 — POINT 1: THE DIAL LANDS WHERE THE MATCH DID.
 *
 * `PRE-GAME 29` was the only reading on a match that finished the day before,
 * because the two numbers on the scoreboard beside it are SETS and this rail is
 * drawn in GAMES. It now has both readings, off the line the API serves.
 *
 * The specimen is Alex's own event, and the numbers asserted are its numbers:
 * 26 games played against a 29 pre-game quote. A test that only proved "a
 * marker appears when a linescore is present" would pass against a mechanism
 * that never fires on the real payload, which is exactly how the previous
 * attempt at this ship died.
 */
describe("live/073 — where it landed, not just what was expected", () => {
  it("a FINISHED match shows the games it was actually played to", () => {
    const text = visibleText(
      renderMaps("tennis_atp_us_open", "completed", markets(), WU_ALCARAZ_LINE)
    );

    // Both readings, and the sentence that stood in for the missing one is gone.
    expect(text).toContain("Final");
    expect(text).toContain("26 games");
    expect(text).toContain("Pre-game");
    expect(text).not.toContain("we did not record the games played");
    expect(text).not.toContain("The scoreboard reports sets");
  });

  it("and grades itself against the quote, like every scored sport", () => {
    const text = visibleText(
      renderMaps("tennis_atp_us_open", "completed", markets(), WU_ALCARAZ_LINE)
    );

    expect(text).toContain("Total: expected vs final");
    expect(text).toContain("Where it landed vs what was expected");
  });

  it("an IN-PLAY match shows the games played SO FAR", () => {
    const text = visibleText(
      renderMaps("tennis_atp_us_open", "live", markets(), {
        sets: [[3, 6], [1, 3]] as [number, number][],
        home_games: 4,
        away_games: 9,
        source: "espn",
      })
    );

    expect(text).toContain("13 games");
    expect(text).not.toContain("we do not hold the games played yet");
  });

  it("THE CONTROL: with no line, the card is exactly what #3136 left", () => {
    const text = visibleText(renderMaps("tennis_atp_us_open", "completed"));

    expect(text).toContain("The scoreboard reports sets, this market quotes games");
    expect(text).toContain("we did not record the games played");
    expect(text).not.toContain("Final");
  });

  it("THE CONTROL: an empty line is an absence, not a 0 – 0", () => {
    const text = visibleText(
      renderMaps("tennis_atp_us_open", "completed", markets(), {
        sets: [] as [number, number][],
        home_games: 0,
        away_games: 0,
        source: "espn",
      })
    );

    expect(text).toContain("we did not record the games played");
    expect(text).not.toContain("0 games");
  });

  it("THE CONTROL: a point sport ignores the field entirely", () => {
    /* An NBA page's scoreboard already counts the unit. If a linescore ever
       appeared on one, the scoreboard still wins — `playedUnits` reads it
       first, and this is the arm that stops a stray key rewriting a score. */
    const nba = { ...markets(), home_score: 112, away_score: 108 };
    const text = visibleText(
      renderMaps("basketball_nba", "completed", nba, WU_ALCARAZ_LINE)
    );

    expect(text).toContain("220 points");
    expect(text).not.toContain("26 points");
    expect(text).not.toContain("games");
  });
});
