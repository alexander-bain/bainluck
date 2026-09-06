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

  // SUPERSEDED by #3575. This asserted that the six de-prefixed child titles
  // were "what a reader sees" — and they were, but none of them is an answer.
  // `Set 2 Winner 87%` does not say for whom; `Match O/U 21.5 50%` does not say
  // over or under. Shortening the string was a real improvement and still left
  // every number nameless. The wire has no side to recover for these rows, so
  // they go, and the sided rows the section was filtering take their place.
  test("a child title is never rendered as if it were an outcome", () => {
    const text = visible(render(1));
    for (const question of [
      "Set 2 Winner",
      "Set Handicap +/-1.5",
      "Total Sets O/U 2.5",
      "Game Spread +/-4.5",
      "Match O/U 21.5",
    ]) {
      expect(text).not.toContain(question);
    }
  });

  test("the sided row the section used to filter out is what renders instead", () => {
    // `Set 1 Winner: Pegula vs Fernandez | Yes = 0.0005` was in this very wire
    // the whole time, dropped by the `winner` keyword and by the two-row
    // win-prob test. It carries the same 0% the un-sided row carried, attached
    // to a name.
    expect(visible(render(1))).toContain("Pegula wins Set 1");
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
    // The row is not deleted — a reader can still see the market exists. Its
    // label is the sided one now (#3575), which is also proof the set number
    // survives being rewritten out of the rendered string.
    expect(text).toContain("Pegula wins Set 1");
  });

  test("THE OTHER DIRECTION: the set being played keeps its live bar", () => {
    // Gotcha #43. Over-suppression here would strip a live match of its prices.
    //
    // #3575 changed the arithmetic, and it is worth stating plainly: this used
    // to be 7 live bars out of 8 surviving rows, and seven of those eight rows
    // were un-sided child titles. Two rows survive now — `Jessica Pegula` and
    // `Pegula wins Set 1` — and BOTH name a side. The count fell; the number of
    // rows a reader can act on went from 1 to 2.
    const html = render(1);
    const bars = html.match(BAR) ?? [];
    expect(bars).toHaveLength(1);
    // Set 1 is decided, so the live bar that remains is the match row.
    expect(visible(html)).toContain("Jessica Pegula");
  });

  test("before any set is finished every row is live", () => {
    const html = render(0);
    expect(html.match(BAR) ?? []).toHaveLength(2);
    expect(visible(html)).not.toContain(SETTLED_QUOTE_PREFIX);
  });
});
