/**
 * #8008 — /politics section headers do not draw a dead "View all →" span.
 *
 * Every section header with `count > 10` previously drew:
 *   `<span class="sectionLink">View all →</span>`
 * styled with `cursor: pointer`, no `href`, and no click handler, because the
 * `/api/politics` endpoint serves curated top slices per theme (`10 shown · N total`)
 * without separate full-list routes.
 *
 *   TZ=UTC npx jest --testPathPatterns=politicsNoDeadViewAll8008
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type { PoliticsData, PoliticsMarketRow } from "@/lib/api";

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({
    data: (global as never as { __PAYLOAD__: unknown }).__PAYLOAD__,
    error: undefined,
  }),
}));
jest.mock("@/hooks", () => ({
  usePageTracking: () => undefined,
  useScrollDepth: () => undefined,
  useEngagementTime: () => undefined,
}));

import PoliticsPage from "@/app/politics/page";

const SAMPLE_MARKET: PoliticsMarketRow = {
  q: "When will the Senate vote on the SAVE America Act?",
  prob: 6.5,
  src: "kalshi",
  market_id: 5466697,
  top_outcomes: [
    { name: "Before Nov 3, 2026", prob: 6.5 },
    { name: "Before Oct 1, 2026", prob: 1.0 },
  ],
  outcome_count: 12,
  more_count: 0,
};

function allSevenPopulatedPayload(): PoliticsData {
  return {
    total_markets: 2513,
    updated_at: "2026-11-08T14:00:00+00:00",
    themes: {
      presidential: {
        count: 391,
        headline_q: "Who wins the 2028 presidential election?",
        candidates: [
          { name: "JD Vance", party: "R", merged: 28, kalshi: 28, poly: 28, change_7d: null, history: [] },
          { name: "Gavin Newsom", party: "D", merged: 19, kalshi: 19, poly: 19, change_7d: null, history: [] },
        ],
        has_dual_source: true,
        kalshi_market_id: 1,
        poly_market_id: 2,
        side_markets: [],
      },
      congressional: {
        count: 851,
        markets: [SAMPLE_MARKET],
        chamber_control: { senate: null, house: null },
        senate_map: null,
      },
      gubernatorial: { count: 306, markets: [SAMPLE_MARKET] },
      policy: { count: 294, markets: [SAMPLE_MARKET] },
      scotus: { count: 16, markets: [SAMPLE_MARKET] },
      international: { count: 472, markets: [SAMPLE_MARKET] },
      other: { count: 183, markets: [SAMPLE_MARKET] },
    },
    cross_source: [],
    by_source: { kalshi: 1200, polymarket: 1313 },
  };
}

describe("#8008 — /politics section headers do not render a dead 'View all →' control", () => {
  test("none of the seven sections with count > 10 renders 'View all' while keeping honest count captions", () => {
    (global as never as { __PAYLOAD__: unknown }).__PAYLOAD__ = allSevenPopulatedPayload();
    const html = renderToStaticMarkup(<PoliticsPage />);

    expect(html).not.toContain("View all");
    expect(html).toContain("2 candidates · 391 markets");
    expect(html).toContain("1 shown · 851 total");
    expect(html).toContain("1 shown · 306 total");
    expect(html).toContain("1 shown · 294 total");
    expect(html).toContain("1 shown · 16 total");
    expect(html).toContain("1 shown · 472 total");
    expect(html).toContain("1 shown · 183 total");
  });
});
