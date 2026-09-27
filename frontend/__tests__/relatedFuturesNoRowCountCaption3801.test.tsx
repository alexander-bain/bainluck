/**
 * #3801 — "BIGGER PICTURE" NEVER PRINTS THE PAYLOAD'S ROW COUNT.
 *
 * ═══ WHAT WAS ON PRODUCTION ═══
 *
 * `/events/14781701` (Chiefs @ Dolphins), 2026-09-27 02:2xZ, 390px: the section
 * drew two team cards (each side's championship path, one Mahomes awards row)
 * and the footer under them read **"1350 related futures from multiple
 * sources"**. `GET /api/events/14781701/related-futures`: 767 home rows + 583
 * away rows = `total_count` 1350. The caption counted every raw outcome row the
 * backend returned; the cards draw a handful of them. 17 of 17 sampled event
 * pages overstated the same way.
 *
 * ═══ THE REPAIR ═══
 *
 * Not a better count. A count of related futures is a coverage number, and a
 * coverage number is not reader prose (notice 34) — the cards are the content.
 * The footer is gone; `total_count` rides the section root as
 * `data-related-futures-total` so a probe can still read it.
 *
 * ═══ BOTH DIRECTIONS ═══
 *
 * Deleting the whole section would also remove the caption, so every case here
 * also asserts the two cards the specimen drew are still drawn.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import RelatedFutures from "@/components/RelatedFutures";
import type { RelatedFuture, RelatedFuturesResponse } from "@/lib/types";

const EVENT_ID = 14781701;
const HOME = "Miami Dolphins";
const AWAY = "Kansas City Chiefs";
const SPECIMEN_TOTAL = 1350; // 767 + 583, the served `total_count`

function row(over: Partial<RelatedFuture> = {}): RelatedFuture {
  return {
    market_id: 7001,
    market_name: "Pro Football Champion",
    clean_label: "Pro Football Champion",
    display_category: "playoff_path",
    market_tier: 1,
    category: "championship",
    source: "kalshi",
    outcome_id: 9001,
    outcome_name: "Miami",
    probability: 0.04,
    american_odds: null,
    probability_change_24h: null,
    opening_probability: null,
    rank: 1,
    relevance_score: 10,
    relevance_reason: "championship",
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

function render(total: number): string {
  swrPayload = {
    event_id: EVENT_ID,
    home_team: HOME,
    away_team: AWAY,
    home_team_futures: [row()],
    away_team_futures: [
      row({
        market_id: 7002,
        outcome_id: 9002,
        outcome_name: "Kansas City",
        probability: 0.16,
      }),
    ],
    series_markets: [],
    total_count: total,
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
      homeTeamColor: "#008E97",
      awayTeamColor: "#E31837",
    }),
  );
}

/** What a reader sees: the markup with every tag (and its attributes) removed. */
function visibleText(html: string): string {
  return html.replace(/<[^>]*>/g, " ");
}

describe("#3801 — the Bigger Picture footer does not print a row count", () => {
  it("STRAWMAN: the reader-text check does catch the old footer", () => {
    // Without this the assertions below could pass because `visibleText`
    // strips everything. The old footer's exact markup must fail them.
    const old =
      '<div class="text-center pt-2 mt-3"><span class="text-[9px] text-text-muted">1350 related futures from multiple sources</span></div>';
    expect(visibleText(old)).toContain(String(SPECIMEN_TOTAL));
    expect(visibleText(old)).toMatch(/related futures/i);
  });

  it("THE SPECIMEN: two cards draw, and no count of 1350 is printed under them", () => {
    const html = render(SPECIMEN_TOTAL);
    const text = visibleText(html);

    // The section and both cards are still here — this is not a suppression.
    expect(html).toContain("Bigger Picture");
    expect(html).toContain('data-testid="home-team-card"');
    expect(html).toContain('data-testid="away-team-card"');

    // …and the reader is told nothing about how many rows the payload held.
    expect(text).not.toContain(String(SPECIMEN_TOTAL));
    expect(text).not.toMatch(/related futures/i);
    expect(text).not.toMatch(/from multiple sources/i);
  });

  it("THE NUMBER IS KEPT for probes, on the section root", () => {
    const html = render(SPECIMEN_TOTAL);
    expect(html).toMatch(
      new RegExp(`^<div data-related-futures-total="${SPECIMEN_TOTAL}"`),
    );
  });

  it("an honest total prints nothing either — the count is gone, not re-derived", () => {
    // Two rows, two cards: a count that happened to be right is still a
    // coverage number, so it does not come back when it matches.
    const text = visibleText(render(2));
    expect(text).not.toMatch(/related futures/i);
  });
});
