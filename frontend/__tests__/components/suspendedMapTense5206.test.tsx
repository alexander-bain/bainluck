/**
 * #5206 — A MATCH NOBODY REPORTED STOPS BEING GIVEN A FORECAST.
 *
 * Read on production at 12:17Z on 2026-09-11, `/events/15310116`. The hero was
 * correct — "No result reported" — and one card below it:
 *
 *   > SCORING MAP
 *   >   Scoring map                                      Projected 3
 *   >   Over 2.5 · 47%
 *
 * A forecast, under a hero that had just said nobody knows how this went. The
 * web twin of #4018 (iOS, fixed), and #4018's line applies verbatim: *a forecast
 * and a result are two questions and they get two predicates.*
 *
 * ── WHY THE FALL-THROUGH HAPPENS ─────────────────────────────────────────────
 *
 * `MarketMapSection` derives `status = isLive ? "live" : isDone ? "done" :
 * "pre"`. A `suspended` event is neither, so it lands in `"pre"` — the branch
 * that draws a `Projection` mark and a `Projected N` headline. This is the exact
 * fall-through `lib/eventState.ts`'s module docstring was written to refuse, one
 * branch over: it warns that an unrecognised status buckets into the upcoming
 * branch and renders a START TIME; here the upcoming branch renders a FORECAST.
 *
 * ── WHY THE FIX IS A TENSE AND NOT A FOURTH STATE ────────────────────────────
 *
 * `status` is a three-value type threaded through twenty call sites and into
 * `MarketMap` itself. Widening it would touch every one of them for a question
 * only two of them ask. What is actually wrong is narrower than the state: the
 * MARKS ARE IN THE WRONG TENSE. The number the market quoted before the match is
 * still true and still worth showing — calling it a *projection* is the lie.
 *
 * So an unreported match reuses the vocabulary this file already owns for
 * exactly this reason (`type: "pre" / label: "Pre-game"`, which the `done` arm
 * and the half-maps' `isDone ? "pre" : "proj"` already emit). The ladder, the
 * density and the distribution are untouched — those state what the market says,
 * not what will happen.
 *
 * ── WHAT MUST NOT MOVE, AND IS ASSERTED BELOW ────────────────────────────────
 *
 * Deleting the word "Projection" would satisfy the ship assertions and break all
 * of these, so each is a control: a scheduled game still gets its projection; a
 * finished game is unchanged; the map still DRAWS (the failure mode of a
 * suppression fix is a card that reads as failed-to-load); and a caller that
 * passes no flag at all behaves exactly as it does today.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";
import { hasNoReportedResult, UPCOMING_GRACE_MS } from "@/lib/eventState";

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
 * The same served shape `pregameMapTense3593` uses, for the same reason: four
 * separated totals rungs so the band really paints a distribution, and a run
 * line so the margin rail draws too. Both rails must be checked — the bug report
 * showed the scoring map, and the margin map falls through identically.
 */
function fixture(overrides: Record<string, unknown> = {}) {
  return {
    event_id: 15310116,
    home_team: "Philadelphia Phillies",
    away_team: "Atlanta Braves",
    home_score: null,
    away_score: null,
    status: "suspended",
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
      { threshold: 2.5, over_probability: 0.71, source: "polymarket", market_type: "game_total", market_name: "Phillies vs. Braves: O/U 2.5", outcome_name: "Over", is_winner: null, resolution_source: null, movement: 0, period: null },
      { threshold: 3.5, over_probability: 0.52, source: "polymarket", market_type: "game_total", market_name: "Phillies vs. Braves: O/U 3.5", outcome_name: "Over", is_winner: null, resolution_source: null, movement: 0, period: null },
      { threshold: 4.5, over_probability: 0.33, source: "polymarket", market_type: "game_total", market_name: "Phillies vs. Braves: O/U 4.5", outcome_name: "Over", is_winner: null, resolution_source: null, movement: 0, period: null },
      { threshold: 5.5, over_probability: 0.18, source: "polymarket", market_type: "game_total", market_name: "Phillies vs. Braves: O/U 5.5", outcome_name: "Over", is_winner: null, resolution_source: null, movement: 0, period: null },
    ],
    ...overrides,
  };
}

function render(
  eventStatus: string,
  noResultReported: boolean | undefined,
  overrides: Record<string, unknown> = {}
) {
  return visibleText(
    renderToStaticMarkup(
      <MarketMapSection
        gameMarkets={fixture(overrides) as never}
        eventStatus={eventStatus}
        homeTeam="Philadelphia Phillies"
        awayTeam="Atlanta Braves"
        homeAbbr="PHI"
        awayAbbr="ATL"
        homeWinProb={0.5}
        awayWinProb={0.5}
        homeSpread={-1.5}
        overUnder={8}
        /* #5414/CERT-2674: the frozen pre-game line, which every real MLB card
           carries (380 of 380 events measured over 30 days) and which this
           fixture predates. It is here so the payload matches production, not
           to satisfy an assertion: the `Pre-game` marker is now drawn only when
           there IS a pre-game reading, and a fixture without one would make the
           finished-game CONTROL below assert the absence of a marker rather
           than the tense of the card, which is not what #5206 is about. Same
           values as the latest snapshot above, so nothing this file measures
           moves. */
        openingHomeSpread={-1.5}
        openingOverUnder={8}
        sportKey="baseball_mlb"
        noResultReported={noResultReported}
      />
    )
  );
}

describe("#5206 — a match nobody reported is given no forecast", () => {
  it("the suspended card drops the Projected headline and the Projection mark", () => {
    const text = render("suspended", true);

    // The card really did draw. Without this the two negatives below would pass
    // against a map that was never rendered at all — which is precisely the
    // failure mode of fixing this by suppression.
    expect(text).toContain("Runs map");

    expect(text).not.toContain("Projected 8");
    expect(text).not.toContain("Projection");
  });

  it("it keeps the quote, in the past tense, rather than showing nothing", () => {
    const text = render("suspended", true);
    // The pre-game number is still true and still worth showing; only its tense
    // was wrong. A fix that blanked the mark would pass the test above.
    expect(text).toContain("Pre-game");
  });

  it("the margin rail is fixed too, not just the totals rail the bug showed", () => {
    const text = render("suspended", true);
    // Both rails share the `status === "pre"` branch, and the bug report only
    // ever showed the scoring map. A fix applied to one rail passes a test that
    // reads the whole card unless the other rail is named.
    expect(text).toContain("Run margin map");
    expect(text).not.toContain("Projection");
  });

  it("the distribution and the ladder are untouched — this is a tense, not a suppression", () => {
    const text = render("suspended", true);
    // What the market says is not a claim about what will happen, so it stays.
    expect(text).toContain("Expected runs distribution");
    expect(text).toContain("Expected run-margin distribution");
  });

  /** ── CONTROLS ─────────────────────────────────────────────────────────── */

  it("a SCHEDULED game still gets its projection — the control", () => {
    const text = render("scheduled", false);
    expect(text).toContain("Projected 8");
    expect(text).toContain("Projection");
  });

  it("a caller that passes no flag behaves exactly as it does today", () => {
    // Every existing call site but the event page passes nothing. The prop
    // defaults to false, so this change is inert for all of them.
    const text = render("scheduled", undefined);
    expect(text).toContain("Projected 8");
    expect(text).toContain("Projection");
  });

  it("a FINISHED game is unchanged", () => {
    const text = render("completed", false, {
      home_score: 4,
      away_score: 2,
      status: "completed",
    });
    expect(text).not.toContain("Projected 8");
    expect(text).toContain("Pre-game");
  });

  /**
   * The predicate is the page's, and it covers BOTH shapes that reach this
   * component as one — a `suspended` row, and a `scheduled` row whose kickoff
   * has passed without anyone reporting anything (#3211).
   *
   * gotcha #44: offset from an injected anchor, never branch on the real clock.
   */
  it("both unreported shapes answer the same predicate", () => {
    const now = Date.parse("2026-09-11T12:00:00Z");
    const longPast = new Date(now - UPCOMING_GRACE_MS - 60_000).toISOString();
    const justNow = new Date(now - 60_000).toISOString();

    expect(hasNoReportedResult("suspended", null, now)).toBe(true);
    expect(hasNoReportedResult("scheduled", longPast, now)).toBe(true);

    // Still plausibly about to start, and a live game, are both forecastable.
    expect(hasNoReportedResult("scheduled", justNow, now)).toBe(false);
    expect(hasNoReportedResult("live", longPast, now)).toBe(false);
  });
});
