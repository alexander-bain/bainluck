/**
 * #8346 — the event page's "Bigger Picture" header stops printing
 * "cross-source aggregated", pipeline vocabulary a reader gets nothing from
 * (notice 34). Seen on /events/15313873 at 390px, 2026-09-24 04:45Z.
 *
 * Harness is #3417's: SWR returns a related-futures payload whose rows open
 * the section, so the header is ON the page when the assertion runs — a
 * section that renders null would pass "no caption" vacuously.
 *
 *   TZ=UTC npx jest --testPathPatterns=biggerPictureNoPipelineCaption8346
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import RelatedFutures from "@/components/RelatedFutures";
import type { RelatedFuture, RelatedFuturesResponse } from "@/lib/types";

const EVENT_ID = 15309061;
const HOME = "Zverev";
const AWAY = "Khachanov";

function row(over: Partial<RelatedFuture> = {}): RelatedFuture {
  return {
    market_id: 7001,
    market_name: "Set 1 Winner: Alexander Zverev vs Karen Khachanov",
    display_category: "game_prop",
    market_tier: 5,
    category: "game",
    source: "kalshi",
    outcome_id: 9001,
    outcome_name: HOME,
    probability: 0.62,
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
  default: () => ({ data: swrPayload, error: undefined, isLoading: false, mutate: () => undefined }),
}));

function render(): string {
  const home = [row()];
  const away = [row({ market_id: 7002, outcome_id: 9002, outcome_name: AWAY, probability: 0.38 })];
  swrPayload = {
    event_id: EVENT_ID,
    home_team: HOME,
    away_team: AWAY,
    home_team_futures: home,
    away_team_futures: away,
    series_markets: [],
    total_count: home.length + away.length,
    summary: null,
    event_status: "scheduled",
    box_score: null,
    league_context: null,
  } as RelatedFuturesResponse;
  return renderToStaticMarkup(
    React.createElement(RelatedFutures, { eventId: EVENT_ID, homeTeam: HOME, awayTeam: AWAY }),
  );
}

describe("#8346 · the Bigger Picture header carries no pipeline caption", () => {
  it("the section renders (so the next assertion is not vacuous)", () => {
    const html = render();
    expect(html).toContain("Bigger Picture");
    expect(html).toContain("Season context");
  });

  it("no 'cross-source' wording in the section", () => {
    expect(render()).not.toMatch(/cross-source/i);
  });
});
