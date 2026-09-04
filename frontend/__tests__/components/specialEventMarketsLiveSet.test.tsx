/**
 * live/065 (#2746) — THE MATCH PAGE'S EXTRA MARKETS, DURING THE US OPEN.
 *
 * Alex watches the finals on his phone. On 2026-09-04 at 09:58 PT, with the
 * women's match Pegula vs Fernandez live and Fernandez a set up, the section
 * under "Additional Markets" printed this, four wrapped lines per row:
 *
 *     US Open WTA: Jessica Pegula vs Leylah Fernandez Set 2 Winner    87%
 *     US Open WTA: Jessica Pegula vs Leylah Fernandez Set 1 Winner     0%
 *     US Open WTA: Jessica Pegula vs Leylah Fernandez Game Spread…    25%
 *
 * — every row repeating the heading directly above it, and the SET THAT WAS
 * ALREADY OVER still drawing a live bar at 0%.
 *
 * ── WHY THIS SUITE IS DIFFERENTIAL, LIKE `specialEventMarketsSettled` ────────
 *
 * `completedSets` is an optional prop threaded page → component → pure module,
 * which is exactly the shape that produced #2086: an optional prop declared,
 * passed, and destructured by nobody, invisible to tsc and to a grep. So the
 * load-bearing test renders the SAME payload with and without the count and
 * requires the markups to differ. Drop the prop anywhere along the thread and
 * the two renders collapse into one string.
 *
 * Gotcha #43's both-directions rule applies too: the danger of a "freeze the
 * decided rows" rule is that it freezes the LIVE ones, so the live rows are
 * asserted to keep their bars, by count.
 *
 * The fixture is the verbatim `other[]` array of
 * `GET /api/events/15301138/game-markets`, captured at the time above.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import SpecialEventMarkets from "../../components/SpecialEventMarkets";
import { SETTLED_QUOTE_PREFIX } from "@/lib/settledQuote";
import type { GameMarketsResponse } from "@/lib/api";

const MATCH = "US Open WTA: Jessica Pegula vs Leylah Fernandez";

/** Verbatim wire, all twelve rows — including the three the section filters. */
const WIRE = [
  { market_name: MATCH, outcome_name: "Jessica Pegula", probability: 0.675, source: "polymarket" },
  { market_name: "Pegula vs Fernandez", outcome_name: "Jessica Pegula", probability: 0.71, source: "kalshi" },
  { market_name: "Pegula vs Fernandez", outcome_name: "Leylah Fernandez", probability: 0.3, source: "kalshi" },
  { market_name: "Set 1 Winner: Pegula vs Fernandez", outcome_name: "No", probability: 0.999, source: "polymarket" },
  { market_name: "Set 1 Winner: Pegula vs Fernandez", outcome_name: "Yes", probability: 0.0005, source: "polymarket" },
  { market_name: MATCH, outcome_name: `${MATCH} Set 1 Winner`, probability: 0.0005, source: "polymarket" },
  { market_name: MATCH, outcome_name: `${MATCH} Set Handicap +/-1.5`, probability: 0.0005, source: "polymarket" },
  { market_name: MATCH, outcome_name: `${MATCH} Set 2 Winner`, probability: 0.865, source: "polymarket" },
  { market_name: MATCH, outcome_name: `${MATCH} Total Sets: O/U 2.5`, probability: 0.58, source: "polymarket" },
  { market_name: MATCH, outcome_name: `${MATCH} Game Spread +/-4.5`, probability: 0.25, source: "polymarket" },
  { market_name: MATCH, outcome_name: `${MATCH} Match O/U 21.5`, probability: 0.5, source: "polymarket" },
  { market_name: MATCH, outcome_name: `${MATCH} Match O/U 22.5`, probability: 0.5, source: "polymarket" },
];

function payload(): GameMarketsResponse {
  return {
    event_id: 15301138,
    home_team: "Jessica Pegula",
    away_team: "Leylah Fernandez",
    home_score: 0,
    away_score: 1,
    status: "live",
    totals: [],
    player_props: [],
    team_totals: [],
    spreads: [],
    period_markets: [],
    matchups: [],
    other: WIRE,
    pace: null,
  } as unknown as GameMarketsResponse;
}

const render = (completedSets?: number) =>
  renderToStaticMarkup(
    <SpecialEventMarkets data={payload()} eventStatus="live" completedSets={completedSets} />,
  );

/** The bar is a `<div>` whose inline width encodes the probability. */
const BAR = /style="width:\s*\d/g;

const visible = (html: string) =>
  html
    .replace(/<[^>]*>/g, " ")
    .replace(/&#x27;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&#x2F;/g, "/")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ");

describe("Additional Markets on a live tennis match: the rows say what they are", () => {
  test("no row repeats the match name — the heading says it once", () => {
    const text = visible(render(1));
    const occurrences = text.split("Jessica Pegula vs Leylah Fernandez").length - 1;
    expect(occurrences).toBe(1);
  });

  test("the distinguishing half of each child title is what a reader sees", () => {
    const text = visible(render(1));
    for (const label of [
      "Set 2 Winner",
      "Set 1 Winner",
      "Set Handicap +/-1.5",
      "Total Sets O/U 2.5",
      "Game Spread +/-4.5",
      "Match O/U 21.5",
    ]) {
      expect(text).toContain(label);
    }
  });

  test("a tour name is never printed where a player belongs", () => {
    // `US Open WTA: … Total Sets: O/U 2.5` used to parse to player "US Open
    // WTA" and render as a Player Prop, headed "Player Props · by statistic".
    const text = visible(render(1));
    expect(text).not.toContain("US Open WTA O/U");
    expect(text).not.toContain("Player Props");
  });
});

describe("Additional Markets on a live tennis match: a played set is not a chance", () => {
  test("THE REGRESSION GUARD: with and without the set count must differ", () => {
    // The #2086 shape: an optional prop dropped anywhere on the thread collapses
    // these two into one string, and no pixel has to be named for this to red.
    expect(render(1)).not.toEqual(render(undefined));
  });

  test("set 1 is over, so it states a last quote and loses its bar", () => {
    const text = visible(render(1));
    expect(text).toContain(`${SETTLED_QUOTE_PREFIX} 0%`);
    // The row is not deleted — a reader can still see the market exists.
    expect(text).toContain("Set 1 Winner");
  });

  test("THE OTHER DIRECTION: the set being played keeps its live bar", () => {
    // Gotcha #43. Over-suppression here would strip a live match of its prices.
    const html = render(1);
    const bars = html.match(BAR) ?? [];
    // Eight of the twelve wire rows survive the section's own filters (the
    // Kalshi win-prob pair and the two-sided "Set 1 Winner:" market are
    // dropped upstream); exactly one of the eight is decided.
    expect(bars).toHaveLength(7);
    expect(visible(html)).toContain("87%");
  });

  test("before any set is finished every row is live", () => {
    const html = render(0);
    expect(html.match(BAR) ?? []).toHaveLength(8);
    expect(visible(html)).not.toContain(SETTLED_QUOTE_PREFIX);
  });
});
