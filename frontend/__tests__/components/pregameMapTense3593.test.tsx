/**
 * #3593 — A GAME THAT HAS NOT STARTED STOPS BEING TOLD WHERE ITS RUNS LANDED.
 *
 * Read on production at phone width on 2026-09-06, `/events/15305464`,
 * Phillies vs Braves, event status `scheduled`, hours before first pitch:
 *
 *   > RUNS MAP
 *   >   Runs map                                        Projected 8
 *   >   Final runs distribution
 *   >   ██████░░████████░░░░░░░░░░░░░░░●░░░░░░░░░░░░
 *   >   0                     6                     12+
 *
 * "Projected 8" and "Final runs distribution" are one card making two claims
 * about one unplayed game. The margin map directly above it said "Final
 * run-margin distribution" for the same reason.
 *
 * ── THIS IS #3210's UNFINISHED THIRD ─────────────────────────────────────────
 *
 * #3210 found that ONE sentence was serving every tense and gave two of them
 * their own arm — settled ("Where it landed vs what was expected") and live
 * ("Where it's heading vs what was expected"), both gated on a scoreboard. The
 * pre-game case is the fall-through, so it kept reaching the literal `"Final"`,
 * and #3210's own header recorded that as `(where it may land; unchanged)`.
 * `liveMapTense3210.test.tsx` then pinned it with a test whose name began
 * "still says Final games distribution — the control". It was never a control.
 * A test can hold a bug in place as firmly as code, and this one did for a day.
 *
 * ── WHY THE FALL-THROUGH IS WIDER THAN "PRE-GAME" ────────────────────────────
 *
 * The live and settled arms are gated on `scored`/`hasScoreboard`, not on
 * status alone. So a LIVE card with no played count also falls through here,
 * and it must not say "Final" either. That is why `distributionTense` keys on
 * `status === "done"` and returns "Expected" for everything else, rather than
 * keying on `status === "pre"`.
 *
 * ── WHAT MUST NOT MOVE ───────────────────────────────────────────────────────
 *
 * A settled card still says "Final". The band-shape rule (#3210) still wins:
 * a card with no shape says "Two lines quoted" in EVERY tense and never calls
 * itself a distribution at all. `unitMismatchNote` still outranks all of it.
 * Each of those is asserted below, because a blanket rewrite of the word
 * "Final" would satisfy the ship assertions and break every one of them.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";
import { distributionTense } from "@/lib/marketMapUtils";

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
 * Event 15305464's served shape, trimmed to the fields these maps read.
 *
 * The four totals rungs are the market names production actually served on
 * that card — they are four DIFFERENT players' `Total Bases` props landing in
 * the `game_total` bucket, which is its own bug (#3594) and deliberately not
 * this one's. They are reproduced verbatim rather than tidied because the band
 * they paint is what put the wrong sentence on screen, and a fixture that
 * quietly fixed them would be testing a card production never served.
 *
 * FOUR rungs at four separated probabilities, so `densityDrawsShape` is true
 * and the subtitle really is the distribution sentence. With a flat band the
 * card says "Four lines quoted" instead and every assertion here would pass
 * against a sentence this fix does not touch.
 */
function phillipsBraves(overrides: Record<string, unknown> = {}) {
  return {
    event_id: 15305464,
    home_team: "Philadelphia Phillies",
    away_team: "Atlanta Braves",
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
    spreads: [
      { market_name: "Phillies vs. Braves: Run Line", outcome_name: "Philadelphia Phillies -1.5", threshold: 1.5, probability: 0.44, source: "kalshi", is_winner: null, resolution_source: null },
      { market_name: "Phillies vs. Braves: Run Line", outcome_name: "Atlanta Braves -1.5", threshold: 1.5, probability: 0.38, source: "kalshi", is_winner: null, resolution_source: null },
    ],
    totals: [
      { threshold: 2.5, over_probability: 0.71, source: "polymarket", market_type: "game_total", market_name: "Brandon Marsh: Total Bases O/U 2.5", outcome_name: "Over", is_winner: null, resolution_source: null, movement: 0, period: null },
      { threshold: 3.5, over_probability: 0.52, source: "polymarket", market_type: "game_total", market_name: "Bryce Harper: Total Bases O/U 3.5", outcome_name: "Over", is_winner: null, resolution_source: null, movement: 0, period: null },
      { threshold: 4.5, over_probability: 0.33, source: "polymarket", market_type: "game_total", market_name: "Drake Baldwin: Total Bases O/U 4.5", outcome_name: "Over", is_winner: null, resolution_source: null, movement: 0, period: null },
      { threshold: 5.5, over_probability: 0.18, source: "polymarket", market_type: "game_total", market_name: "Drake Baldwin: Total Bases O/U 5.5", outcome_name: "Over", is_winner: null, resolution_source: null, movement: 0, period: null },
    ],
    ...overrides,
  };
}

function render(eventStatus: string, overrides: Record<string, unknown> = {}) {
  return visibleText(
    renderToStaticMarkup(
      <MarketMapSection
        gameMarkets={phillipsBraves(overrides) as never}
        eventStatus={eventStatus}
        homeTeam="Philadelphia Phillies"
        awayTeam="Atlanta Braves"
        homeAbbr="PHI"
        awayAbbr="ATL"
        homeWinProb={0.5}
        awayWinProb={0.5}
        homeSpread={-1.5}
        overUnder={8}
        sportKey="baseball_mlb"
      />
    )
  );
}

describe("#3593 — the pre-game map speaks in the pre-game tense", () => {
  it("the unplayed Phillies–Braves card does not call its band Final", () => {
    const text = render("scheduled");

    // The card this is about really did render, with the headline Alex would
    // have read beside the sentence. Without this the assertions below could
    // pass against a map that was never drawn.
    expect(text).toContain("Runs map");
    expect(text).toContain("Projected 8");

    expect(text).toContain("Expected runs distribution");
    expect(text).not.toContain("Final runs distribution");
  });

  it("fixes the margin rail on the same card, not just the totals rail", () => {
    const text = render("scheduled");
    expect(text).toContain("Expected run-margin distribution");
    expect(text).not.toContain("Final run-margin distribution");
  });

  /**
   * The whole point of #3210's live arm is that it is gated on a played count.
   * A live card without one falls through to this same sentence, and "Final" is
   * no more true there than it is pre-game.
   */
  it("a LIVE card with no played count is not told Final either", () => {
    const text = render("live");
    expect(text).not.toContain("Where it's heading");
    expect(text).toContain("Expected runs distribution");
    expect(text).not.toContain("Final runs distribution");
  });

  it("a FINISHED card still says Final — the control", () => {
    const text = render("completed", { home_score: 4, away_score: 2, status: "completed" });
    // With a scoreboard the settled arm wins outright, which is #2442's
    // wording and must survive untouched.
    expect(text).toContain("Where it landed vs what was expected");
    expect(text).not.toContain("Expected runs distribution");
  });

  /**
   * A finished game with NO score is the other half of the fall-through, and it
   * is the one case where "Final" is still the right word: the game is over,
   * we simply cannot say where it landed. This is what stops the fix being
   * "delete the word Final".
   */
  it("a FINISHED card with no score keeps Final — the control that matters", () => {
    const text = render("completed");
    expect(text).toContain("Final runs distribution");
    expect(text).not.toContain("Expected runs distribution");
  });

  /**
   * #3210's band rule outranks the tense rule in every tense. A card with no
   * shape names its rungs and does not call itself a distribution at all — so
   * the new word must not appear on one.
   */
  it("a shapeless band still names its lines instead, in every tense", () => {
    const flat = [
      { threshold: 7.5, over_probability: 0.5, source: "kalshi", market_type: "game_total", market_name: "Phillies vs. Braves: O/U 7.5", outcome_name: "Over", is_winner: null, resolution_source: null, movement: 0, period: null },
      { threshold: 8.5, over_probability: 0.5, source: "kalshi", market_type: "game_total", market_name: "Phillies vs. Braves: O/U 8.5", outcome_name: "Over", is_winner: null, resolution_source: null, movement: 0, period: null },
    ];
    for (const status of ["scheduled", "live", "completed"]) {
      const text = render(status, { totals: flat });
      expect(text).toContain("Two lines quoted");
      expect(text).not.toContain("Expected runs distribution");
      expect(text).not.toContain("Final runs distribution");
    }
  });

  /**
   * The tense is selected by status alone. A helper that read the sport would
   * pass every assertion above and regress the moment a new sport was declared.
   */
  it("the rule is one line and reads only the status", () => {
    expect(distributionTense("pre")).toBe("Expected");
    expect(distributionTense("live")).toBe("Expected");
    expect(distributionTense("done")).toBe("Final");
  });
});
