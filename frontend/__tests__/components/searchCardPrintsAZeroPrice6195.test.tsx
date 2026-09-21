/**
 * #6195 — THE WEB HALF: A SEARCH CARD MUST PRINT `0%` FOR A RUNG WE KNOW IS 0%
 *
 * ## What a reader sees
 *
 * `?q=Super Bowl` draws *Sports Emmy Award for Outstanding Live Sports Special:
 * Championship Event?* (Kalshi market 13886744) as five rungs, of which FOUR were
 * a dash — NBA Finals, College Football Playoff, Super Bowl LX, The Masters —
 * while every one of those rows is stored `0.000000` and graded `api_settlement`.
 * A near-empty board on the surface a reader meets first, for a question we can
 * answer completely.
 *
 * ## Why this file exists SEPARATELY from the backend guard
 *
 * The backend repair (`c1c8dbeed`, CERT-3231) taught `_build_search_top_outcomes`
 * and `outcome_prints_a_price` to key on `value is None` instead of `not value`,
 * so the payload now carries `probability: 0.0` where it used to carry `null`.
 * That is only half the reader's path. The cert named the other half as its
 * nonblocking follow-up — `6195-PIN-ZERO-THROUGH-WEB-SEARCH-RENDER` — because the
 * web render was proved correct by CLIENT TRACING and pinned by NOTHING.
 *
 * Exact zero IS pinned today on the chart callout (#6858), the golf field floor
 * and the tournament slate/board. It is pinned nowhere on the search card path,
 * which is the one the new payload actually lands on. A guard on the surface that
 * changed is not a duplicate of guards on four surfaces that did not.
 *
 * ## The two ways this regresses, and why BOTH controls are here
 *
 * The render walks `formatProbability` → `probabilityParts`, and each has one
 * line standing between a stored zero and a lie:
 *
 *   1. `formatProbability` returns `"-"` on `prob === null || prob === undefined`.
 *      Rewritten as the shorter `if (!prob)` — which is exactly the mistake the
 *      BACKEND had made and this ship just deleted — every zero rung goes back to
 *      a dash, on the client this time.
 *   2. `probabilityParts` clamps a rounds-to-nothing value to `<1%` via
 *      `rounded <= 0 && prob > 0`. Drop the `&& prob > 0` and a *genuine* zero
 *      prints `<1%`: we would be telling a reader that an eliminated nominee is
 *      merely unlikely.
 *
 * Those two failures point in OPPOSITE directions — one erases the zero, the
 * other inflates it — so a test that only asserted "prints 0%" would catch the
 * first and a test that only asserted the UX-P046 floor would catch the second.
 * Both are asserted, and the `<1%` control below is what stops someone
 * "simplifying" the boundary rule to make this file pass.
 *
 * ## Fixture is the specimen
 *
 * All six rows, their verbatim names and their stored values are read from
 * production 2026-09-21 (`POST /api/admin/db-query`, market 13886744): one leg at
 * `0.990000` and five at a literal `0.000000`, every one graded `api_settlement`,
 * all sharing `last_updated 2026-08-06 20:49:38Z`. The market's own `status` is
 * `open` — which is why the card takes its numeric branch at all and does not
 * print the `Won`/`Lost` verdicts of #5552 over these legs.
 *
 * Absent is not zero (ruling 051). The null control is the other half of the
 * claim: this ship makes a PRICED-AT-NOTHING leg print a number, and it must
 * leave a leg we hold no price for printing a dash.
 *
 * ## Mutation-checked 3/3, with the counts, because this file is a PIN
 *
 * The render is already correct, so every assertion here is green on arrival and
 * none of them is red-first. A characterisation test that was never observed to
 * fail is indistinguishable from one that cannot, so each guarded line was broken
 * in turn and the kills recorded:
 *
 *   | mutant | edit | failed |
 *   |---|---|---|
 *   | M1 | `formatProbability`: `prob === null \|\| prob === undefined` → `!prob` | 4/4 |
 *   | M2 | `probabilityParts`: drop `&& prob > 0` from the `<1%` clamp | 3/4 |
 *   | M3 | `formatProbability`: return `"0%"` for null instead of `"-"` | 1/4 |
 *
 * M2 leaves "prints no dash" green on purpose — `<1%` is not a dash, and that
 * test is aimed at the erasure, not the inflation. M3 is killed by the ruling-051
 * control and by NOTHING ELSE, which is the evidence that the control is
 * load-bearing rather than decorative: delete it and a build that prints "0%"
 * over a price we do not have ships green.
 */

import { renderToStaticMarkup } from "react-dom/server";
import FuturesCard from "../../components/FuturesCard";
import { BELOW_ONE_PERCENT } from "../../lib/probabilityDisplay";
import type { FuturesMarket, FuturesOutcome } from "../../lib/types";

function outcome(
  id: number,
  name: string,
  probability: number | null,
): FuturesOutcome {
  return {
    id,
    name,
    probability,
    american_odds: null,
    rank: null,
    rank_change_24h: null,
    probability_change_24h: null,
    movement: null,
    opening_probability: null,
    opening_american_odds: null,
    // `api_settlement` on every row, exactly as production holds them. The market
    // is `open`, so #5552's verdict branch does not fire and these legs reach the
    // percentage cell — which is the whole point of the specimen.
    is_winner: false,
    resolution_source: "api_settlement",
    last_updated: "2026-08-06T20:49:38.248547+00:00",
  } as unknown as FuturesOutcome;
}

function market(outcomes: FuturesOutcome[]): FuturesMarket {
  return {
    id: 13886744,
    name: "Sports Emmy Award for Outstanding Live Sports Special: Championship Event?",
    description: null,
    source: "kalshi",
    category: null,
    sport: null,
    sport_name: null,
    llm_sport_category: "entertainment",
    external_id: null,
    mutually_exclusive: true,
    commence_time: null,
    resolution_date: null,
    outcome_count: outcomes.length,
    created_at: null,
    updated_at: null,
    status: "open",
    top_outcomes: outcomes,
    outcomes,
  } as unknown as FuturesMarket;
}

/** The production specimen's six rows, verbatim. */
const SPECIMEN: FuturesOutcome[] = [
  outcome(89617305, "FOX MLB: World Series", 0.99),
  outcome(89617306, "NBA Finals", 0),
  outcome(89617307, "College Football Playoff", 0),
  outcome(89617308, "Super Bowl LX", 0),
  outcome(89617309, "The Masters", 0),
  outcome(89617310, "Tie", 0),
];

/**
 * The text of each row's PERCENTAGE CELL, in render order.
 *
 * 🔴 NOT a substring search for `0%`. Every row also draws a mini bar whose
 * inline style is `width:0%` for exactly the legs under test, so
 * `expect(html).toContain("0%")` passes on a card that prints five dashes — it
 * would be an assertion that cannot fail, which is worse than no assertion.
 * Read the cell, and prove the reader is holding five of them before reading any.
 */
function probabilityCells(m: FuturesMarket): string[] {
  const html = renderToStaticMarkup(<FuturesCard market={m} />);
  if (!/role="progressbar"/.test(html)) {
    throw new Error(
      "no outcome rows rendered — the extractor is blind, not the card empty",
    );
  }
  return [
    ...html.matchAll(
      /<span class="font-mono text-sm tabular-nums[^"]*">([^<]*)<\/span>/g,
    ),
  ].map((match) => decodeEntities(match[1]));
}

/**
 * `renderToStaticMarkup` escapes the text it renders, so UX-P046's `<1%` arrives
 * here as `&lt;1%` and a comparison against `BELOW_ONE_PERCENT` fails on a card
 * that is drawing exactly the right thing. Decoded in ONE pass over an alternation
 * rather than by chaining `.replace` calls: a chain that handles `&amp;` before
 * the others turns a literal `&amp;lt;` into `<` (a double decode), so the order
 * of the clauses would silently decide the answer.
 */
const ENTITIES: Record<string, string> = {
  "&lt;": "<",
  "&gt;": ">",
  "&quot;": '"',
  "&#x27;": "'",
  "&amp;": "&",
};

function decodeEntities(text: string): string {
  return text.replace(
    /&(?:lt|gt|quot|#x27|amp);/g,
    (entity) => ENTITIES[entity] ?? entity,
  );
}

describe("#6195 — the web search card prints a stored zero as a number", () => {
  it("prints 0% on every eliminated rung of the production specimen", () => {
    const cells = probabilityCells(market(SPECIMEN));
    // The card slices to five rows, leader first (#2789), so the reader sees the
    // 99% winner and four of the five zeros.
    expect(cells).toHaveLength(5);
    expect(cells[0]).toBe("99%");
    expect(cells.slice(1)).toEqual(["0%", "0%", "0%", "0%"]);
  });

  it("prints no dash at all on a card whose every row we can price", () => {
    // The defect as the reader met it: four of five rows a dash. Asserted over
    // the CELLS, so the hyphens inside class names and timestamps cannot satisfy
    // it, and asserted as "none" rather than "not the first one".
    for (const cell of probabilityCells(market(SPECIMEN))) {
      expect(cell).not.toBe("-");
      expect(cell).not.toBe("—");
    }
  });

  it("still prints a dash for a leg we hold NO price for (absent is not zero)", () => {
    // Ruling 051. The one distinction this ship must not flatten — without it the
    // whole file is satisfied by `formatProbability` returning "0%" for anything.
    //
    // FIVE legs, not the specimen's six, and that is not a convenience: the card
    // slices to five leader-first (#2789), and an unpriced leg sorts to the BOTTOM,
    // so on a six-row market it is the row the slice drops. Written as six, this
    // control renders `["99%", "0%", "0%", "0%", "0%"]` and asserts nothing about
    // absence at all — it passes against a build that prints "0%" for null, which
    // is the precise defect it exists to catch. Measured, not reasoned: that is the
    // array this test returned before the fixture was shortened.
    const withNull = [
      SPECIMEN[0],
      outcome(89617306, "NBA Finals", null),
      ...SPECIMEN.slice(2, 5),
    ];
    const cells = probabilityCells(market(withNull));
    expect(cells).toHaveLength(5);
    expect(cells.filter((c) => c === "-")).toHaveLength(1);
    // And the OTHER zeros are untouched by their neighbour's absence.
    expect(cells.filter((c) => c === "0%")).toHaveLength(3);
  });

  it("keeps UX-P046's floor: a small-but-real price is <1%, never 0%", () => {
    // The opposite regression. `probabilityParts` separates these two with
    // `rounded <= 0 && prob > 0`; delete that clause to make a genuine zero print
    // `<1%`, or delete the zero handling to make this row print `0%`, and one of
    // these two assertions fails either way.
    const withTinyPrice = [
      SPECIMEN[0],
      outcome(89617306, "NBA Finals", 0.0004),
      ...SPECIMEN.slice(2),
    ];
    const cells = probabilityCells(market(withTinyPrice));
    expect(cells).toContain(BELOW_ONE_PERCENT);
    expect(cells).toContain("0%");
  });
});
