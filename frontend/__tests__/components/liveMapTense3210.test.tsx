/**
 * #3210 — A MATCH IN PLAY STOPS BEING TOLD WHERE ITS GAMES "FINAL"-LY LANDED.
 *
 * `"Final games distribution"` was the `else` of `status === "done"`, so it
 * rendered on live matches too. Confirmed on production 2026-09-05 in a single
 * phone-width shot of `/events/15304420` (Bergs v van de Zandschulp, second set
 * in progress):
 *
 *   > Games map
 *   > Final games distribution
 *   >   ACTUAL 14 games        PRE-GAME 41
 *
 * The `ACTUAL` rung is counting games as they are played. The data is
 * present-tense and only the sentence is past-tense.
 *
 * ── THREE TENSES, NOT TWO ────────────────────────────────────────────────────
 *
 *   pre   — "Final games distribution"          (where it may land; unchanged)
 *   live  — "Where it's heading vs what was expected"
 *   done  — "Where it landed vs what was expected"   (#2442's wording; unchanged)
 *
 * The live arm is gated on the same `scored` the ACTUAL marker is gated on, so
 * the sentence promises a comparison exactly when the rail actually draws one.
 * A live match with no played count keeps the pre-game wording rather than
 * claiming to show where something is heading from one marker.
 *
 * ── THE CONTROLS ARE THE SUITE ───────────────────────────────────────────────
 *
 * Both untouched tenses are asserted on every fixture this suite moves. A
 * blanket rewrite that fired on all three statuses would satisfy every live
 * assertion below and quietly tell a pre-game reader the match is under way.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";

/**
 * `renderToStaticMarkup` escapes the apostrophe in "Where it's heading" to
 * `&#x27;`, and the named-entity strip every sibling suite uses does not touch
 * NUMERIC entities — so a substring assertion on the copy as a reader sees it
 * fails against markup that is perfectly correct. Decoded here rather than
 * worked around in the assertions: a test that has to spell the shipped
 * sentence differently from the way it ships is a test that stops matching it.
 */
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

/**
 * Event 15304420's shape, trimmed to the fields these maps read. The totals
 * rows carry a real game-total threshold so the totals map builds a density and
 * a subtitle at all.
 */
function markets(overrides: Record<string, unknown> = {}) {
  return {
    event_id: 15304420,
    home_team: "Zizou Bergs",
    away_team: "Botic van de Zandschulp",
    home_score: 1,
    away_score: 0,
    status: "live",
    player_props: [],
    team_totals: [],
    period_markets: [],
    matchups: [],
    other: [],
    pace: null,
    props_script: [],
    // A full-game spread pair, so the MARGIN map renders at all — without one
    // `marginData` returns null and every margin assertion below would pass
    // vacuously against a card that was never drawn.
    spreads: [
      { market_name: "Bergs vs. van de Zandschulp: Game Spread", outcome_name: "Zizou Bergs -2.5", threshold: 2.5, probability: 0.48, source: "kalshi", is_winner: null, resolution_source: null },
      { market_name: "Bergs vs. van de Zandschulp: Game Spread", outcome_name: "Botic van de Zandschulp -2.5", threshold: 2.5, probability: 0.52, source: "kalshi", is_winner: null, resolution_source: null },
    ],
    // FOUR rungs, and the count is load-bearing (#3210's second half). A
    // two-rung card produces one PDF point, paints an identically-coloured
    // segment across the whole rail, and therefore no longer calls itself a
    // "distribution" at all — it says "Two lines quoted" and names them. That
    // is the subject of `mapWithoutAShape3210.test.tsx`, not of this suite.
    // THIS suite is about which TENSE a status selects, so its fixture has to
    // be a card whose band really does draw a shape; otherwise every
    // "distribution" assertion below would be testing the flat-band rule
    // wearing the tense rule's name.
    totals: [
      { threshold: 42.5, over_probability: 0.33, source: "kalshi", market_type: "game_total", market_name: "Bergs vs. van de Zandschulp: Total Games O/U 42.5", outcome_name: "Over", is_winner: null, resolution_source: null, movement: 0.01, period: null },
      { threshold: 40.5, over_probability: 0.51, source: "kalshi", market_type: "game_total", market_name: "Bergs vs. van de Zandschulp: Total Games O/U 40.5", outcome_name: "Over", is_winner: null, resolution_source: null, movement: 0.02, period: null },
      { threshold: 38.5, over_probability: 0.64, source: "kalshi", market_type: "game_total", market_name: "Bergs vs. van de Zandschulp: Total Games O/U 38.5", outcome_name: "Over", is_winner: null, resolution_source: null, movement: 0.03, period: null },
      { threshold: 36.5, over_probability: 0.72, source: "kalshi", market_type: "game_total", market_name: "Bergs vs. van de Zandschulp: Total Games O/U 36.5", outcome_name: "Over", is_winner: null, resolution_source: null, movement: 0.03, period: null },
    ],
    ...overrides,
  };
}

/**
 * The line production served for this match mid-second-set: 6-3, 1-4 — seven
 * games each, 14 played, against the 41 the market quoted pre-game. This is
 * what makes `scored` non-null on a tennis page, via `playedUnits`.
 */
const BERGS_LINE = {
  sets: [
    [6, 3],
    [1, 4],
  ] as [number, number][],
  home_games: 7,
  away_games: 7,
  source: "espn",
};

function renderMaps(
  eventStatus: string,
  linescore: typeof BERGS_LINE | null = BERGS_LINE,
  body: object = markets()
) {
  return visibleText(
    renderToStaticMarkup(
      <MarketMapSection
        gameMarkets={body as never}
        eventStatus={eventStatus}
        homeTeam="Zizou Bergs"
        awayTeam="Botic van de Zandschulp"
        homeAbbr="ZB"
        awayAbbr="BVD"
        homeWinProb={0.41}
        awayWinProb={0.59}
        homeSpread={-2.5}
        overUnder={41}
        sportKey="tennis_atp_us_open"
        linescore={linescore}
      />
    )
  );
}

describe("#3210 — the games map speaks in the match's own tense", () => {
  it("an IN-PLAY match is not told where its games finally landed", () => {
    const text = renderMaps("live");

    // The rail really is drawing the played count — this is the fixture the
    // sentence is wrong about, not a hypothetical one.
    expect(text).toContain("14 games");

    expect(text).toContain("Where it's heading vs what was expected");
    expect(text).not.toContain("Final games distribution");
  });

  it("a FINISHED match still says where it landed — the control", () => {
    const text = renderMaps("completed");
    expect(text).toContain("Where it landed vs what was expected");
    expect(text).not.toContain("Where it's heading");
  });

  it("a PRE-GAME match still says Final games distribution — the control", () => {
    const text = renderMaps("scheduled");
    expect(text).toContain("Final games distribution");
    expect(text).not.toContain("Where it's heading");
    expect(text).not.toContain("Where it landed");
  });

  /**
   * The live arm is gated on the played count, not merely on the status. A
   * tennis match in play with NO line has nothing to compare against, so it
   * must not promise a comparison — it keeps the pre-game wording, which is
   * what the card said before this shipped.
   */
  it("a live match with no played count does not promise a comparison", () => {
    const text = renderMaps("live", null);
    expect(text).not.toContain("Where it's heading");
    // On a set-scored sport with no line, the subtitle is already spoken for:
    // `unitMismatchNote` takes precedence and says which two units the card
    // refuses to mix, in the in-play tense #3136 gave it. That sentence must
    // survive this change — the new arm sits BELOW it, not in front of it.
    expect(text).toContain("The scoreboard reports sets, this market quotes games");
    expect(text).toContain("we do not hold the games played yet");
  });

  /**
   * The margin map directly above the totals one had the identical `else`, and
   * is fixed in the same pass: leaving it would put "Final margin distribution"
   * and "Where it's heading vs what was expected" on two rails of one live
   * card, which reads worse than the bug did.
   */
  it("fixes the margin rail in the same tense, not just the totals rail", () => {
    expect(renderMaps("live")).not.toContain("Final margin distribution");
    // ...and a pre-game card keeps it.
    expect(renderMaps("scheduled")).toContain("margin distribution");
  });

  /**
   * A point sport is untouched in every tense. The fix is about which sentence
   * a status selects, and must not depend on the sport — but a basketball card
   * that changed wording here would be a silent regression on every NBA page.
   */
  it("a point sport reads the same three tenses — the control", () => {
    const nba = (status: string) =>
      visibleText(
        renderToStaticMarkup(
          <MarketMapSection
            gameMarkets={markets({ status, home_score: 58, away_score: 55 }) as never}
            eventStatus={status}
            homeTeam="Boston Celtics"
            awayTeam="Miami Heat"
            homeAbbr="BOS"
            awayAbbr="MIA"
            homeWinProb={0.6}
            awayWinProb={0.4}
            homeSpread={-4.5}
            overUnder={41}
            sportKey="basketball_nba"
          />
        )
      );

    expect(nba("live")).toContain("Where it's heading vs what was expected");
    expect(nba("completed")).toContain("Where it landed vs what was expected");
    expect(nba("scheduled")).toContain("Final points distribution");
  });
});
