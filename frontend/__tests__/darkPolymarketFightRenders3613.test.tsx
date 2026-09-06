/**
 * #3613 / CERT-2111 — the captured Polymarket price actually REACHES THE READER.
 *
 * ═══ WHY THIS FILE EXISTS ═══
 *
 * The backend half of #3613 gives a dark, event-linked Polymarket market its
 * first outcome row, at the venue's own price. CERT-2103 withheld the token
 * because a row in a table is not a ship; the repair pointed the guard at
 * `/related-futures`, and CERT-2111 then measured the rest of the path and
 * found the ship still invisible for a reason no backend test could see:
 *
 *     `categorizeFutures()` in `components/RelatedFutures.tsx` buckets on
 *     `display_category`, and it has NO bucket for "championship".
 *
 * A Polymarket game moneyline is born labelled `championship`, so the row was
 * served, dropped, and the section never rendered. The pass now corrects that
 * one display label on the rows it prices, and this file is the arm that proves
 * the correction is what puts the fight on the page.
 *
 * ═══ THE PAYLOAD IS NOT INVENTED ═══
 *
 * `ROW` is the exact shape `_build_related_futures` serves for the specimen
 * after the pass runs — the same fields the real-Postgres round trip
 * (`backend/tests/integration/test_dark_polymarket_selector_real_postgres.py`,
 * "THE GAP-CREATE..."/"the reader can actually see it" arms) asserts on, with
 * the venue's own 0.295. If the backend stops serving this shape, that file
 * goes red; if the frontend stops rendering it, this one does.
 *
 * ═══ THE CONTROL ═══
 *
 * `renders nothing when the row is still labelled championship` re-runs the
 * IDENTICAL payload with the pre-fix label. It must render no fighter and no
 * price. Without it a green above proves only that a component renders a row it
 * is given — not that the label is what was wrong.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import RelatedFutures from "@/components/RelatedFutures";
import type { RelatedFuturesResponse } from "@/lib/types";

const EVENT_ID = 15305793;
const FIGHTER = "Ozzy Diaz";
const MARKET_NAME =
  "UFC 331: Ozzy Diaz vs. Ryan Gandra (Middleweight, Early Prelims)";

/** The venue's price for the specimen, read from Gamma 2026-09-06 17:00Z. */
const PRICE = 0.295;

const ROW = (displayCategory: string) => ({
  market_id: 60280227,
  market_name: MARKET_NAME,
  clean_label: MARKET_NAME,
  display_category: displayCategory,
  merge_group: null,
  playoff_stage: null,
  playoff_stage_type: null,
  stage_order: null,
  market_tier: 5,
  category: displayCategory,
  source: "polymarket",
  outcome_id: 991,
  outcome_name: FIGHTER,
  external_id: "0xf5200af3",
  probability: PRICE,
  american_odds: 239,
  probability_change_24h: null,
  opening_probability: PRICE,
  rank: 1,
  relevance_score: 60,
  relevance_reason: "game market",
  last_updated: "2026-09-06T17:00:00+00:00",
  next_update_expected: "2026-09-06T18:30:00+00:00",
  resolution_date: null,
  bookmaker_count: 1,
});

const payload = (displayCategory: string): RelatedFuturesResponse =>
  ({
    event_id: EVENT_ID,
    home_team: "Gandra",
    away_team: "Diaz",
    home_team_futures: [],
    // The classifier puts the fighter on the away side — his name matches the
    // away team pattern. Which side is not the claim; being SERVED is.
    away_team_futures: [ROW(displayCategory)],
    series_markets: [],
    total_count: 1,
    summary: null,
    event_status: "scheduled",
    box_score: null,
    league_context: null,
  }) as unknown as RelatedFuturesResponse;

let swrPayload: RelatedFuturesResponse = payload("game_prop");

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({
    data: swrPayload,
    error: undefined,
    isLoading: false,
    mutate: () => undefined,
  }),
}));

function renderWith(displayCategory: string): string {
  swrPayload = payload(displayCategory);
  return renderToStaticMarkup(
    React.createElement(RelatedFutures, {
      eventId: EVENT_ID,
      homeTeam: "Gandra",
      awayTeam: "Diaz",
      sportKey: "mma_mixed_martial_arts",
      // The specimen's page has no game-markets section at all — that is the
      // bug's own starting condition. Passing `true` here would suppress the
      // stat-props section for an unrelated reason and hide the thing under
      // test.
      hasGameMarkets: false,
      eventStatus: "scheduled",
    }),
  );
}

/**
 * Every percentage the component prints, in order.
 *
 * An equality on an extracted number, never `toContain("30%")` on the whole
 * document: this page draws gauges for anything it is given, so a substring
 * search would pass on a number that came from somewhere else entirely. The
 * extractor reports its own yield for the same reason.
 */
function renderedPercents(html: string): string[] {
  const re = /tabular-nums[^>]*>(\d+)%<\/span>/g;
  const found: string[] = [];
  let m: RegExpExecArray | null;
  while ((m = re.exec(html)) !== null) found.push(m[1]);
  return found;
}

describe("#3613 / CERT-2111 — the dark fight's price reaches the page", () => {
  it("renders the fighter under Game props once the row is a game prop", () => {
    const html = renderWith("game_prop");

    expect(html).toContain("Game props");
    expect(html).toContain(FIGHTER);
  });

  it("prints the venue's own number and not some other one", () => {
    const html = renderWith("game_prop");

    // The component renders whole percent, so the venue's 0.295 reads "30%".
    // That is a display rounding of the number we captured — the claim under
    // test is that the number came from the payload, which the second arm
    // below is what actually establishes.
    expect(renderedPercents(html)).toEqual([String(Math.round(PRICE * 100))]);
  });

  it("follows the payload's price rather than a constant", () => {
    // #1578's phantom midpoint is 0.5 — the value a page showing a made-up
    // number would print. Rendering the same row at the phantom price must
    // print 50%, which proves the 30% above is read from the row and not baked
    // into the component or into this fixture's markup.
    swrPayload = {
      ...payload("game_prop"),
      away_team_futures: [{ ...ROW("game_prop"), probability: 0.5 }],
    } as unknown as RelatedFuturesResponse;
    const html = renderToStaticMarkup(
      React.createElement(RelatedFutures, {
        eventId: EVENT_ID,
        homeTeam: "Gandra",
        awayTeam: "Diaz",
        sportKey: "mma_mixed_martial_arts",
        hasGameMarkets: false,
        eventStatus: "scheduled",
      }),
    );
    expect(renderedPercents(html)).toEqual(["50"]);
  });

  it("renders nothing when the row is still labelled championship", () => {
    const html = renderWith("championship");

    expect(html).not.toContain(FIGHTER);
    expect(renderedPercents(html)).toEqual([]);
  });
});
