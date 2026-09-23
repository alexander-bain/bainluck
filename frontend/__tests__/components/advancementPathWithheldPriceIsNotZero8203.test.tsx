/**
 * #8203 — A CHAMPIONSHIP RUNG NOBODY PRICED STOPS PRINTING `0%`.
 *
 * ═══ WHAT WAS ON PRODUCTION ═══
 *
 * `/events/15316874` (Athletics vs Los Angeles Angels), Bigger Picture → Season
 * context, photographed at 390px 2026-09-23 08:18Z and re-read off
 * `/api/events/15316874/related-futures` at 09:4xZ the same morning:
 *
 *     Athletics   61-95 · #4 West
 *     CHAMPIONSHIP PATH
 *     World Series Champion     [empty bar]     0%
 *
 *     Angels      60-96 · #5 West
 *     CHAMPIONSHIP PATH
 *     World Series Champion     [empty bar]     0%
 *
 * One rung each, and the only season context either club was given. The wire
 * said `probability: null` on both rows (`opening_probability: 0.005`, source
 * `kalshi`), so the page was not reporting a price — it was inventing one, and
 * on a *World Series Champion* rung `0%` reads as "this club cannot win".
 *
 * ═══ WHY THE FORMATTER DID NOT SAVE IT ═══
 *
 * `AdvancementPath` already routes every rung through `formatProbabilityPercent`
 * precisely so that "only a genuine 0 or 1 prints as one" (#7687). It did its
 * job. The zero was manufactured one file upstream, by `RelatedFutures`'
 * `prob: f.probability || 0`, so what reached the formatter WAS a genuine zero
 * and printing it was correct. Even the stale opening price would have printed
 * `<1%`.
 *
 * That is why the arms below run in BOTH places. A component-only suite passes
 * while the page lies (the component was never wrong), and a caller-only suite
 * pins a coercion without proving what the markup does with the null it now
 * lets through. The join is the defect.
 *
 * ═══ WHY THE LEAGUE-CONTEXT PATH WAS NEVER THE CULPRIT ═══
 *
 * `ctxToFutures` filters `teamCtx.cells[col.key] != null` before it builds a
 * row, and the tennis caller's `toStages` filters the same way. Both other
 * producers of these rungs already drop an unpriced one. Only the raw-futures
 * fallback — reached when `league_context` is absent, which it is on this event
 * — passed the API's rows through untouched, and that branch coerced. The fix
 * therefore had to change what the fallback SENDS and what the component
 * DRAWS, and the null-payload arm below asserts the fallback is the branch
 * under test by serving no `league_context` at all.
 *
 * ═══ THE TREATMENT IS #8067'S, NOT A NEW ONE ═══
 *
 * `SpecialEventMarkets` answered this exact question yesterday for a withdrawn
 * 1st-Touchdown leg: "the row keeps its name and shows nothing. Not a dash, not
 * 'no price', not a parenthetical ... And no bar — the bar is a picture of a
 * quantity, so a zero-width one is the same false zero drawn instead of
 * written." This is the third surface in that family (#6138, #8067) and it gets
 * the same answer, so the em-dash arm below is a real assertion and not a
 * formality: `NO_READING` exists in `probabilityDisplay` and would have been the
 * easy thing to reach for.
 *
 * ═══ BOTH DIRECTIONS (gotcha #43) ═══
 *
 * "Never prints 0%" is passed perfectly by a component that has stopped drawing
 * rungs, and "drops the bar" by one that draws no bars at all. So every
 * suppression arm is paired with a control on the values that MUST be
 * unaffected: a rung genuinely quoted at 0 still prints `0%` and a real zero is
 * the one value this fix must not swallow; a 1% rung still prints and still
 * draws a visible bar; the unpriced rung keeps its label; and a mixed ladder
 * proves the two can sit in one list.
 *
 *   npx jest --testPathPatterns=advancementPathWithheldPriceIsNotZero8203
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import AdvancementPath, {
  type AdvancementStage,
} from "../../components/event/AdvancementPath";
import RelatedFutures from "../../components/RelatedFutures";
import { NO_READING } from "../../lib/probabilityDisplay";
import type { RelatedFuture, RelatedFuturesResponse } from "../../lib/types";

let swrPayload: RelatedFuturesResponse;

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({
    data: swrPayload,
    error: undefined,
    isLoading: false,
    mutate: () => undefined,
  }),
}));

/** The served values, verbatim from the specimen. */
const WITHHELD = null;
const STALE_OPENING = 0.005;
/** A real quote of nought — the control this fix must not swallow. */
const GENUINE_ZERO = 0;
/** Small but real: must still print, and must still draw a bar. */
const BARELY_POSSIBLE = 0.01;

function stage(over: Partial<AdvancementStage>): AdvancementStage {
  return {
    label: "World Series Champion",
    prob: WITHHELD,
    change: null,
    resolved: false,
    ...over,
  };
}

function draw(stages: AdvancementStage[]): string {
  return renderToStaticMarkup(React.createElement(AdvancementPath, { stages }));
}

/**
 * The stage row for one label, sliced out of the markup.
 *
 * Backtracks to the row's opening `<`. Slicing from the ATTRIBUTE leaves a
 * headless tag — `data-stage="…" data-probability="0" >` with no `<` in front
 * of it — which `readoutOf`'s tag-stripper cannot see and therefore hands back
 * as visible text, attribute values and all. The row for a genuine zero would
 * then "print" the `0` out of `data-probability`.
 */
function rowFor(html: string, label: string): string {
  const attr = html.indexOf(`data-stage="${label}"`);
  expect(attr).toBeGreaterThan(-1);
  const start = html.lastIndexOf("<", attr);
  const next = html.indexOf('data-testid="advancement-stage"', attr + 1);
  return html.slice(start, next === -1 ? undefined : html.lastIndexOf("<", next));
}

/**
 * The words a reader sees in one row, with the markup taken out.
 *
 * SEPARATE FROM THE MARKUP ASSERTIONS ON PURPOSE. "This row prints no
 * percentage" is a claim about TEXT, and `expect(html).not.toContain("%")` is
 * not that claim: a bar's `style="width: 0%"` puts a `%` in the markup, so the
 * raw-markup form passes and fails for reasons that have nothing to do with
 * what is written on the row. It was green on the fix and red on the pre-fix
 * tree for the bar, not for the readout — right answer, wrong question. So the
 * readout arms read text and the bar arms read markup, and neither can be
 * satisfied by the other's subject.
 */
function readoutOf(html: string, label: string): string {
  return rowFor(html, label)
    .replace(/<[^>]+>/g, " ")
    .replace(/&[a-z]+;/g, " ")
    .replace(/\s+/g, " ")
    .replace(label, "")
    .trim();
}

describe("#8203 the component refuses to draw a price nobody quoted", () => {
  test("the census is not vacuous: this component really does print percentages", () => {
    // Every suppression arm below would pass against a component that had
    // stopped rendering numbers at all. It has not.
    expect(draw([stage({ prob: 0.12 })])).toContain("12%");
  });

  test("a withheld rung prints no percentage", () => {
    const readout = readoutOf(draw([stage({ prob: WITHHELD })]), "World Series Champion");
    expect(readout).not.toMatch(/%/);
    // The row is empty beyond its name. Not "0%", and not anything else either.
    expect(readout).toBe("");
  });

  test("a withheld rung keeps its name", () => {
    // The row is not dropped. The reader is told the market exists; they are
    // simply not told a price, which is the whole of what we know.
    expect(draw([stage({ prob: WITHHELD })])).toContain("World Series Champion");
  });

  test("a withheld rung's label column keeps the width the priced rows use", () => {
    // #8067's rail has no fixed columns and puts its label in `flex-1`. Copying
    // that here is the tempting move and it is wrong: in a mixed ladder the
    // unpriced row's label would take the whole width while its neighbours stay
    // at `w-36`, and every label in the list stops lining up. The mutation
    // sweep found this unguarded — the claim was in a comment and nowhere else.
    const withheld = rowFor(draw([stage({ prob: WITHHELD })]), "World Series Champion");
    const priced = rowFor(draw([stage({ prob: 0.23 })]), "World Series Champion");
    expect(withheld).toContain("w-36 shrink-0");
    expect(priced).toContain("w-36 shrink-0");
  });

  test("a withheld rung draws no bar, not a zero-width one", () => {
    const html = draw([stage({ prob: WITHHELD })]);
    // The track carries the fill. A zero-width fill inside a visible track is
    // the same false zero, drawn instead of written.
    expect(html).not.toContain("bg-violet-400");
    expect(html).not.toContain("width:0%");
  });

  test("a withheld rung is not given a dash either (#8067's wording)", () => {
    // Not a formality. `formatProbabilityPercent` ALREADY answers a non-finite
    // input with `NO_READING`, so before this fix the component handed a null
    // rendered exactly that em dash — the pre-fix tree fails this arm on the
    // dash, not on a `0%`. Leaving it would have been the smallest possible
    // change and the wrong one: #8067 ruled the space is left empty rather than
    // marked, because a dash in a value column is still a mark in the shape of
    // an answer.
    expect(readoutOf(draw([stage({ prob: WITHHELD })]), "World Series Champion")).not.toContain(
      NO_READING,
    );
  });

  test("the stale opening price is not substituted for the missing one", () => {
    // 0.005 is what the payload carries beside the null. It is a price from
    // whenever the market opened, not a current one, and printing it would
    // trade a false zero for a false quote.
    const readout = readoutOf(draw([stage({ prob: WITHHELD })]), "World Series Champion");
    expect(readout).not.toContain("1%");
    expect(readout).not.toContain(`${STALE_OPENING}`);
  });

  test("CONTROL: a rung genuinely quoted at zero still prints 0%", () => {
    // The distinction this whole fix rests on. A market that has actually
    // priced an outcome at nought is making a claim, and we report it.
    const html = draw([stage({ prob: GENUINE_ZERO })]);
    expect(html).toContain("0%");
    expect(html).toContain('data-probability="0"');
  });

  test("CONTROL: a 1% rung still prints and still draws a visible bar", () => {
    const html = draw([stage({ prob: BARELY_POSSIBLE })]);
    expect(html).toContain("1%");
    expect(html).toContain("bg-violet-400");
    expect(html).toContain("width:1%");
  });

  test("CONTROL: a clinched rung outranks an absent price", () => {
    // `resolved` sits ABOVE the withheld branch, as #8067's verdict does: a
    // settlement is the better answer wherever there is one and needs no price
    // to be true. Neither caller reports one today (#7687), so this pins the
    // ordering for the payload that eventually does.
    const html = draw([stage({ prob: WITHHELD, resolved: true })]);
    expect(html).toContain("clinched");
    expect(html).toContain("width:100%");
  });

  test("a mixed ladder suppresses only the unpriced rung", () => {
    // Both `/events/15317392` and `/events/15313464` serve several of these at
    // once, and a league can price some rungs and not others. Row-local, not
    // list-wide.
    const html = draw([
      stage({ label: "World Series Champion", prob: WITHHELD }),
      stage({ label: "NL Champion", prob: 0.23 }),
    ]);
    expect(readoutOf(html, "World Series Champion")).toBe("");
    expect(readoutOf(html, "NL Champion")).toContain("23%");
    // And the priced rung keeps its bar while the unpriced one has none.
    expect(rowFor(html, "NL Champion")).toContain("bg-violet-400");
    expect(rowFor(html, "World Series Champion")).not.toContain("bg-violet-400");
  });

  test("a withheld rung shows no 24h move either", () => {
    // A delta is a statement about the level we are declining to state.
    const readout = readoutOf(
      draw([stage({ prob: WITHHELD, change: 0.021 })]),
      "World Series Champion",
    );
    expect(readout).not.toContain("2.1");
    expect(readout).not.toContain("↑");
    expect(readout).toBe("");
  });

  test("CONTROL: a PRICED rung still shows its 24h move", () => {
    // The arm above must not be passed by a component that stopped drawing
    // moves at all — #7745's polarity rule renders here.
    const readout = readoutOf(
      draw([stage({ prob: 0.23, change: 0.021 })]),
      "World Series Champion",
    );
    expect(readout).toContain("2.1");
    expect(readout).toContain("↑");
  });
});

/**
 * The payload arm. Drives the real `RelatedFutures` with the served shape, so
 * the caller's coercion is under test and not just the component's refusal.
 */

/**
 * The A's `World Series Champion` row, VERBATIM off
 * `GET /api/events/15316874/related-futures` (build `v4963`, 2026-09-23).
 *
 * Copied rather than minimised because `display_category` is load-bearing and
 * invisible: `categorizeFutures` admits a rung to the championship ladder only
 * on `display_category === "playoff_path"`, and a plausible-looking
 * `"championship"` — which is what this row's own `category` field says — puts
 * the row in no group at all, renders an empty page and passes every
 * suppression assertion below for the wrong reason. The first draft of this
 * fixture made exactly that substitution; the vacuity control caught it.
 */
function future(over: Partial<RelatedFuture>): RelatedFuture {
  return {
    market_id: 275,
    market_name: "Pro Baseball Champion",
    clean_label: "World Series Champion",
    display_category: "playoff_path",
    merge_group: "world_series_champion",
    playoff_stage: "Championship",
    playoff_stage_type: "championship",
    stage_order: 5,
    market_tier: 1,
    category: "championship",
    source: "kalshi",
    outcome_id: 2344,
    outcome_name: "A's",
    probability: WITHHELD,
    american_odds: null,
    probability_change_24h: null,
    opening_probability: STALE_OPENING,
    rank: 18,
    relevance_score: 33.5,
    relevance_reason: "championship context",
    last_updated: "2026-09-23T06:09:44.397091+00:00",
    next_update_expected: "2026-09-23T09:45:00+00:00",
    resolution_date: "2026-11-01T04:00:00+00:00",
    bookmaker_count: 1,
    all_sources: ["kalshi", "polymarket"],
    source_count: 2,
    ...over,
  } as RelatedFuture;
}

function drawPage(homeFutures: RelatedFuture[]): string {
  swrPayload = {
    event_id: 15316874,
    home_team: "Athletics",
    away_team: "Los Angeles Angels",
    home_team_futures: homeFutures,
    away_team_futures: [],
    series_markets: [],
    total_count: homeFutures.length,
    // ABSENT, exactly as the specimen serves it. This is what routes the rows
    // through the raw-futures fallback, which is the branch that coerced.
    league_context: null,
  } as unknown as RelatedFuturesResponse;
  return renderToStaticMarkup(
    React.createElement(RelatedFutures, {
      eventId: 15316874,
      homeTeam: "Athletics",
      awayTeam: "Los Angeles Angels",
    } as never),
  );
}

describe("#8203 the served null survives the caller", () => {
  test("the census is not vacuous: this payload really does reach a path rung", () => {
    // If the section did not render at all, every assertion below would pass
    // against an empty string.
    const html = drawPage([future({ probability: 0.23 })]);
    expect(html).toContain("World Series Champion");
    expect(html).toContain("23%");
  });

  test("the served null does not become 0% on the page", () => {
    const html = drawPage([future({ probability: WITHHELD })]);
    expect(html).toContain("World Series Champion");
    expect(html).not.toContain("0%");
  });

  test("CONTROL: a served zero still reaches the page as 0%", () => {
    expect(drawPage([future({ probability: GENUINE_ZERO })])).toContain("0%");
  });
});
