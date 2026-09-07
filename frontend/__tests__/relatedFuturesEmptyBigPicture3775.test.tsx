/**
 * #3775 — "BIGGER PICTURE" NEVER OPENS OVER ZERO CARDS.
 *
 * ═══ WHAT ALEX SAW ═══
 *
 * `/events/15305644` (Dencheva vs Lachinova, `tennis_wta`) rendered the section
 * header **Bigger Picture** / `Season context`, the footer caption
 * **`2 related futures from multiple sources`**, and then **no cards at all**
 * before moving on to the next section. A section that announces two things and
 * shows none reads as a broken page, not an empty one.
 *
 * ═══ THE MECHANISM ═══
 *
 * The section gate and the section bodies counted different populations.
 *
 *     gate  (RelatedFutures)   homeCats.statProps.length + homeCats.games.length …
 *     body  (StatPropsSection) futures.filter(p != null && p > .02 && p < .98)
 *     body  (GameMarketsGrid)  the same, PLUS past games, cross-sport name
 *                              leaks, and dedupe by opponent
 *
 * So the gate counted PAYLOAD ROWS and the bodies counted SURVIVORS. Feed it a
 * page whose only related futures are settled — which is every event whose one
 * related market is its own head-to-head, once that match is decided — and the
 * gate opens the section while every body inside it returns `null`. The footer
 * then prints the backend's `total_count` over the emptiness.
 *
 * The repair is not a new guard: it is deleting the second population. The
 * filters were lifted into `visibleStatProps` / `visibleGameMarkets` and the
 * gate now counts their output, so the two numbers cannot drift again.
 *
 * ═══ WHY THE ASSERTIONS ARE ON MARKUP ═══
 *
 * The rows in the report survive `isRelevantGameProp` and survive
 * `categorizeFutures` — Alex ruled both out by hand before filing. Every unit
 * assertion on those helpers was green ON THE BUG. The only thing that can tell
 * "the section is suppressed" from "the section is drawn empty" is the served
 * body, so this file renders the real component and asserts on its HTML.
 *
 * ═══ BOTH DIRECTIONS (gotcha #43) ═══
 *
 * A test that only proved "the section disappears" would be passed perfectly by
 * deleting the section, which would be a far worse bug on the ~every page where
 * Bigger Picture is the point. Each suppression case below is paired with a
 * control that changes ONE field — the probability, or the date — and asserts
 * the section comes back with its cards.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import RelatedFutures from "@/components/RelatedFutures";
import type { RelatedFuture, RelatedFuturesResponse } from "@/lib/types";

const EVENT_ID = 15305644;
const HOME = "Dencheva";
const AWAY = "Lachinova";

/** A related-futures row, defaulted to the reported page's shape. */
function row(over: Partial<RelatedFuture> = {}): RelatedFuture {
  return {
    market_id: 7001,
    market_name: "Dencheva vs Lachinova",
    display_category: "game_prop",
    market_tier: 5,
    category: "game",
    source: "kalshi",
    outcome_id: 9001,
    outcome_name: "Dencheva",
    probability: 0.5,
    american_odds: null,
    probability_change_24h: null,
    opening_probability: null,
    rank: null,
    relevance_score: 1,
    relevance_reason: "same match",
    last_updated: null,
    next_update_expected: "",
    resolution_date: null,
    ...over,
  };
}

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

/**
 * Render the section for one payload.
 *
 * `homeStandings` / `awayStandings` are deliberately OMITTED and
 * `teamProgression` is left unset. Both are independent reasons for the section
 * to open (`hasStandings`, `hasGridProgression`), and either one would mask the
 * defect entirely — the section would render for a legitimate reason and the
 * suppression cases below would pass without proving anything. The reported
 * page has neither: a WTA first-rounder has no standings table and no grid.
 */
function render(futures: {
  home?: RelatedFuture[];
  away?: RelatedFuture[];
  total?: number;
}): string {
  const home = futures.home ?? [];
  const away = futures.away ?? [];
  swrPayload = {
    event_id: EVENT_ID,
    home_team: HOME,
    away_team: AWAY,
    home_team_futures: home,
    away_team_futures: away,
    series_markets: [],
    total_count: futures.total ?? home.length + away.length,
    summary: null,
    event_status: "scheduled",
    box_score: null,
    league_context: null,
  } as RelatedFuturesResponse;

  return renderToStaticMarkup(
    React.createElement(RelatedFutures, {
      eventId: EVENT_ID,
      homeTeam: HOME,
      awayTeam: AWAY,
    }),
  );
}

/**
 * The caption is the user-visible promise, so it is what the suppression cases
 * assert on — not the header. Anchored on the sentence Alex quoted.
 */
const CAPTION = /related futures from multiple sources/;

describe("#3775 — the section never announces futures it does not draw", () => {
  it("THE REPORTED PAGE: two settled game props draw nothing, so nothing renders", () => {
    // The exact shape of `/events/15305644`: the event's OWN head-to-head
    // market, returned once per side, decided — so both rows are pinned at the
    // rails that `StatPropsSection` drops.
    const html = render({
      home: [row({ probability: 0.99, outcome_id: 9001, outcome_name: HOME })],
      away: [
        row({
          probability: 0.01,
          outcome_id: 9002,
          outcome_name: AWAY,
          market_id: 7002,
        }),
      ],
      total: 2,
    });

    // The whole section is gone — header, body and caption together.
    expect(html).toBe("");
    expect(html).not.toMatch(CAPTION);
    expect(html).not.toContain("Bigger Picture");
  });

  it("CONTROL: the same two rows, still trading, DO open the section", () => {
    // One field differs from the case above — the probability. If this ever
    // fails, the repair has suppressed the section rather than reconciled it.
    const html = render({
      home: [row({ probability: 0.62, outcome_id: 9001, outcome_name: HOME })],
      away: [
        row({
          probability: 0.38,
          outcome_id: 9002,
          outcome_name: AWAY,
          market_id: 7002,
        }),
      ],
      total: 2,
    });

    expect(html).toContain("Bigger Picture");
    expect(html).toMatch(CAPTION);
    // …and the cards it promised are actually present.
    expect(html).toContain("Dencheva");
    expect(html).toContain("Lachinova");
  });

  it("THE GAME-MARKETS HALF: games already played draw nothing, so nothing renders", () => {
    // `GameMarketsGrid` drops past games in addition to settled ones, and the
    // gate counted them too. `display_category: "other"` is the `games` bucket.
    const html = render({
      home: [
        row({
          display_category: "other",
          market_name: "Dencheva vs Someone",
          probability: 0.55,
          resolution_date: "2020-01-01T00:00:00Z",
        }),
      ],
      total: 1,
    });

    expect(html).toBe("");
    expect(html).not.toMatch(CAPTION);
  });

  it("CONTROL: the same game, not yet played, DOES open the section", () => {
    // Only `resolution_date` moves.
    const html = render({
      home: [
        row({
          display_category: "other",
          market_name: "Dencheva vs Someone",
          probability: 0.55,
          resolution_date: "2099-01-01T00:00:00Z",
        }),
      ],
      total: 1,
    });

    expect(html).toContain("Bigger Picture");
    expect(html).toMatch(CAPTION);
  });

  it("a row with NO price is not a card either", () => {
    // `probability: null` reaches the same rail. Worth its own case because a
    // null is the one value a `p <= 0.02 || p >= 0.98` test written without the
    // null guard would let through as a drawn-but-blank card.
    const html = render({
      home: [row({ probability: null })],
      total: 1,
    });

    expect(html).toBe("");
  });

  it("the caption never promises more than the section can draw", () => {
    // The invariant behind all of the above, stated once. A payload whose
    // `total_count` is large but whose every row is settled must not print that
    // number: the backend's count is not evidence that anything is renderable.
    const settled = [
      row({ probability: 1.0, outcome_id: 9001 }),
      row({ probability: 0.0, outcome_id: 9002, market_id: 7002 }),
      row({ probability: 0.995, outcome_id: 9003, market_id: 7003 }),
    ];

    expect(render({ home: settled, total: 28 })).not.toContain("28");
  });
});
