/**
 * #3240 — A TENNIS PAGE STOPS PROMISING A GAMES MAP IT DOES NOT DRAW.
 *
 * Seen on production at 390px on 2026-09-05, three specimens, two of them in
 * play in the same minute:
 *
 *   `/events/15304382` (Keys–Zheng)      linescore `sets [[2,1]]`, NO game-total
 *   `/events/15303007` (Osaka–Mertens)   same shape
 *   `/events/15303395` (Potapova–Anisimova)  `sets [[0,1]]`, HAS `Match O/U 21.5`
 *
 * All three printed, under Score Differential:
 *
 *   > The scoreboard reports sets, so the line below is the books' projected
 *   > game margin. **The games played are on the games map below.**
 *
 * and only the third had the card. The note was gated on the page HOLDING the
 * games (`playedUnits`); the card is gated on a game-total market existing to
 * build a rail from. Two facts, one condition, and they disagreed.
 *
 * ## What makes this suite non-vacuous
 *
 * The obvious test — hand `totalsMapPresent` to the chart and assert the
 * wording changes — proves the renderer branches and proves NOTHING about
 * whether the page can still compute that flag wrongly. It is the same shape
 * that let this bug ship: a value asserted in a fixture is not a value the
 * product derives.
 *
 * So every case here goes through `totalsMapRenders(gameMarkets)`, the helper
 * the page actually passes, and the decisive test is `it("agrees with the card
 * that renders")`: for each payload it renders the REAL `MarketMapSection` and
 * requires the predicate to equal whether a games map is actually in that
 * markup. Re-gate the card and this suite fails, which is the whole point —
 * the two conditions are pinned together rather than each pinned separately.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";
import ScoreDifferentialChart from "@/components/ScoreDifferentialChart";
import { totalsMapRenders } from "@/lib/marketMapUtils";

function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    // React escapes the apostrophe in `Zheng's` to `&#x27;`. Decode the
    // entities that carry meaning before blanking the rest, or every
    // possessive in this file becomes an unassertable `Zheng s`.
    .replace(/&#x27;|&#39;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&[a-z]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

const HISTORY = [
  { timestamp: "2026-09-05T15:05:00Z", home_probability: 0.55, away_probability: 0.45, projected_home_score: 11.4, projected_away_score: 10.2, bookmaker_count: 8 },
  { timestamp: "2026-09-05T15:25:00Z", home_probability: 0.61, away_probability: 0.39, projected_home_score: 11.9, projected_away_score: 9.8, bookmaker_count: 9 },
];

/** Keys–Zheng's line as ESPN wrote it: 2 games to 1, first set, live. */
const LINESCORE = { sets: [[2, 1]] as [number, number][], home_games: 2, away_games: 1, source: "espn" };

const DUEL_SPREADS = [
  { market_name: "Madison Keys vs Qinwen Zheng: Game Spread", outcome_name: "Madison Keys -1.5 games", threshold: 1.5, probability: 0.58, source: "kalshi", is_winner: null, resolution_source: null },
  { market_name: "Madison Keys vs Qinwen Zheng: Game Spread", outcome_name: "Qinwen Zheng -1.5 games", threshold: 1.5, probability: 0.34, source: "kalshi", is_winner: null, resolution_source: null },
];

const GAME_TOTALS = [
  { threshold: 20.5, over_probability: 0.63, source: "kalshi", market_type: "game_total", market_name: "Keys vs Zheng: Total Games", outcome_name: "Over 20.5 games", is_winner: null, resolution_source: null, movement: 0, period: null },
  { threshold: 22.5, over_probability: 0.38, source: "kalshi", market_type: "game_total", market_name: "Keys vs Zheng: Total Games", outcome_name: "Over 22.5 games", is_winner: null, resolution_source: null, movement: 0, period: null },
];

/** Both thresholds already resolved — rows exist, no rail can be drawn from them. */
const RESOLVED_TOTALS = GAME_TOTALS.map((t) => ({ ...t, over_probability: 0 }));

function markets(over: Partial<Record<string, unknown>> = {}) {
  return {
    event_id: 15304382,
    home_team: "Madison Keys",
    away_team: "Qinwen Zheng",
    home_score: 0,
    away_score: 0,
    status: "live",
    player_props: [],
    team_totals: [],
    period_markets: [],
    matchups: [],
    other: [],
    pace: null,
    props_script: [],
    spreads: [],
    totals: [],
    ...over,
  };
}

/** The page's own composition: the flag is DERIVED here, never handed in. */
function renderNote(gameMarkets: ReturnType<typeof markets>) {
  return renderToStaticMarkup(
    <ScoreDifferentialChart
      history={HISTORY as never}
      homeTeam="Madison Keys"
      awayTeam="Qinwen Zheng"
      commenceTime="2026-09-05T15:00:00Z"
      isLive
      eventStatus="live"
      currentHomeScore={0}
      currentAwayScore={1}
      sportKey="tennis_wta_us_open"
      linescore={LINESCORE}
      totalsMapPresent={totalsMapRenders(gameMarkets as never)}
    />
  );
}

function renderMaps(gameMarkets: ReturnType<typeof markets>) {
  return renderToStaticMarkup(
    <MarketMapSection
      gameMarkets={gameMarkets as never}
      eventStatus="live"
      homeTeam="Madison Keys"
      awayTeam="Qinwen Zheng"
      homeAbbr="KEY"
      awayAbbr="ZHE"
      homeWinProb={0.61}
      awayWinProb={0.39}
      homeSpread={-1.5}
      overUnder={21.5}
      sportKey="tennis_wta_us_open"
      linescore={LINESCORE}
    />
  );
}

/** Does a games map exist in this markup? Read off the column the reader sees. */
function drawsGamesMap(gameMarkets: ReturnType<typeof markets>): boolean {
  return visibleText(renderMaps(gameMarkets)).includes("Games map");
}

/** Every payload this suite reasons about, named the way the issue names them. */
const CASES = {
  "Keys–Zheng, no market maps at all": markets(),
  "Keys–Zheng, a duel spread and no game total": markets({ spreads: DUEL_SPREADS }),
  "Potapova–Anisimova, a game total": markets({ spreads: DUEL_SPREADS, totals: GAME_TOTALS }),
  "a game total whose thresholds have all resolved": markets({ spreads: DUEL_SPREADS, totals: RESOLVED_TOTALS }),
  "a game total and nothing else": markets({ totals: GAME_TOTALS }),
};

describe("#3240 — the pointer is gated on the card, not on holding the number", () => {
  /**
   * THE LOAD-BEARING TEST. Not "the predicate returns false on this fixture" —
   * that is a pinned constant and it rots the moment the card is re-gated.
   * This asserts the two conditions AGREE, on every payload, which is the
   * property the bug violated.
   */
  it("agrees with the card that renders", () => {
    for (const [name, gm] of Object.entries(CASES)) {
      expect([name, totalsMapRenders(gm as never)]).toEqual([name, drawsGamesMap(gm)]);
    }
  });

  it("states the count instead of pointing, when no games map is drawn", () => {
    for (const name of [
      "Keys–Zheng, no market maps at all",
      "Keys–Zheng, a duel spread and no game total",
    ] as const) {
      const text = visibleText(renderNote(CASES[name]));
      expect([name, text.includes("games map below")]).toEqual([name, false]);
      // …and the number the page knew and printed nowhere is now printed,
      // with the sides NAMED so it cannot be read in the hero's winner-first order.
      expect(text).toContain("Keys has won 2 games to Zheng's 1");
      // The independent first clause is untouched — only the pointer was wrong.
      expect(text).toContain("The scoreboard reports sets");
      expect(text).toContain("projected game margin");
    }
  });

  /**
   * THE CONTROL, and it is the reason the case above means anything: the same
   * note, the same linescore, one market added, and the pointer comes back.
   * A fix that simply deleted the sentence would pass every assertion above
   * and fail here.
   */
  it("still points at the games map on a page that draws one", () => {
    const gm = CASES["Potapova–Anisimova, a game total"];
    expect(drawsGamesMap(gm)).toBe(true);
    const text = visibleText(renderNote(gm));
    expect(text).toContain("The games played are on the games map below");
    expect(text).not.toContain("Keys has won 2 games");
  });

  /**
   * A NAIVE `totals.length > 0` PASSES EVERY TEST ABOVE AND FAILS THIS ONE.
   * The rows are present; the card is not, because a resolved threshold is
   * dropped before the rail is built. This is why the note asks the selector
   * rather than the payload.
   */
  it("does not point at a card that resolved thresholds emptied", () => {
    const gm = CASES["a game total whose thresholds have all resolved"];
    expect(gm.totals.length).toBe(2);
    expect(drawsGamesMap(gm)).toBe(false);
    expect(totalsMapRenders(gm as never)).toBe(false);
    expect(visibleText(renderNote(gm))).toContain("Keys has won 2 games to Zheng's 1");
  });

  /** A page holding no played count still says so, and points nowhere. */
  it("keeps the absence wording when the line has no sets on it", () => {
    const html = renderToStaticMarkup(
      <ScoreDifferentialChart
        history={HISTORY as never}
        homeTeam="Madison Keys"
        awayTeam="Qinwen Zheng"
        commenceTime="2026-09-05T15:00:00Z"
        isLive
        eventStatus="live"
        sportKey="tennis_wta_us_open"
        linescore={{ sets: [], home_games: 0, away_games: 0 }}
        totalsMapPresent={totalsMapRenders(CASES["Potapova–Anisimova, a game total"] as never)}
      />
    );
    const text = visibleText(html);
    expect(text).toContain("we do not hold the games played yet");
    expect(text).not.toContain("games map below");
  });

  /** Unchanged for every sport whose scoreboard counts its own unit. */
  it("prints no such note on a point sport", () => {
    const html = renderToStaticMarkup(
      <ScoreDifferentialChart
        history={HISTORY as never}
        homeTeam="Madison Keys"
        awayTeam="Qinwen Zheng"
        commenceTime="2026-09-05T15:00:00Z"
        isLive
        eventStatus="live"
        currentHomeScore={40}
        currentAwayScore={38}
        sportKey="basketball_nba"
        totalsMapPresent={false}
      />
    );
    expect(html).not.toContain('data-testid="score-diff-unit-note"');
  });

  /**
   * The default is the safe direction. A call site that forgets the prop
   * states the count — redundant at worst — rather than inventing a card.
   */
  it("points nowhere when the caller says nothing", () => {
    const html = renderToStaticMarkup(
      <ScoreDifferentialChart
        history={HISTORY as never}
        homeTeam="Madison Keys"
        awayTeam="Qinwen Zheng"
        commenceTime="2026-09-05T15:00:00Z"
        isLive
        eventStatus="live"
        sportKey="tennis_wta_us_open"
        linescore={LINESCORE}
      />
    );
    expect(visibleText(html)).not.toContain("games map below");
  });
});
