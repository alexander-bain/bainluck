/**
 * #9109 follow-up — a /politics card's "+N more" counts the rows its page shows.
 *
 * ═══ WHAT A READER SAW, production 2026-09-27 12:25Z at 390px ═══
 *
 *     When will the Senate vote on the SAVE America Act?          +9 more
 *     LEADER  Before Nov 3, 2026                                       7%
 *             Before Oct 1, 2026                                       1%
 *
 * `/futures/5466697` — the page the card opens — shows those two rows and no
 * others. The badge was `outcome_count - 3`, which counts every rung the ladder
 * ever had, including the ten passed dates the page drops. 15 of the 25 badged
 * cards on the payload over-counted. The server now sends `more_count`, the
 * page's rows the card does not show; the card prints that.
 *
 * Mounted through the real page (its cards are module-locals of a route file,
 * see #6766's note), read as visible text.
 *
 *   TZ=UTC npx jest --testPathPatterns=politicsMoreBadgeCountsThePage9109
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

function payload(markets: PoliticsMarketRow[]): PoliticsData {
  return {
    total_markets: markets.length,
    updated_at: "2026-09-27T12:25:27+00:00",
    themes: {
      presidential: {
        count: 0,
        headline_q: null,
        candidates: [],
        has_dual_source: false,
        kalshi_market_id: null,
        poly_market_id: null,
        side_markets: [],
      },
      congressional: {
        count: 0,
        markets: [],
        chamber_control: { senate: null, house: null },
        senate_map: null,
      },
      gubernatorial: { count: 0, markets: [] },
      policy: { count: markets.length, markets },
      scotus: { count: 0, markets: [] },
      international: { count: 0, markets: [] },
      other: { count: 0, markets: [] },
    },
    cross_source: [],
    by_source: { kalshi: 1, polymarket: 1 },
  };
}

/** The visible text of the card linking to `/futures/<id>`. */
function cardText(markup: string, marketId: number): string {
  const at = markup.indexOf(`href="/futures/${marketId}"`);
  expect(at).toBeGreaterThanOrEqual(0);
  const next = markup.indexOf('href="/futures/', at + 1);
  return markup
    .slice(at, next < 0 ? markup.length : next)
    .replace(/<[^>]*>/g, " ")
    .replace(/\s+/g, " ");
}

function badge(text: string): string | null {
  const m = text.match(/\+(\d+) more/);
  return m ? m[0] : null;
}

// Served 2026-09-27 12:25Z, `more_count` as the fixed server computes it.
const SAVE_ACT: PoliticsMarketRow = {
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
const KASH_PATEL: PoliticsMarketRow = {
  q: "Kash Patel out as FBI Director?",
  prob: 16.5,
  src: "kalshi",
  market_id: 8817578,
  top_outcomes: [
    { name: "Before Dec 1, 2026", prob: 16.5 },
    { name: "Before Nov 1, 2026", prob: 7.5 },
    { name: "Before Oct 1, 2026", prob: 1.5 },
  ],
  outcome_count: 8,
  more_count: 0,
};
const CLOSEST_GOVERNOR: PoliticsMarketRow = {
  q: "Closest Governor race in 2026?",
  prob: 14,
  src: "kalshi",
  market_id: 108629,
  top_outcomes: [
    { name: "Georgia", prob: 14 },
    { name: "Arizona", prob: 12 },
    { name: "Michigan", prob: 10 },
  ],
  outcome_count: 22,
  more_count: 19,
};
// One live rung is unpriced: the card cannot show it, the page lists it.
const MIFEPRISTONE: PoliticsMarketRow = {
  q: "Will mail-order mifepristone access be restricted?",
  prob: 12,
  src: "kalshi",
  market_id: 25926800,
  top_outcomes: [{ name: "27JAN", prob: 12 }],
  outcome_count: 4,
  more_count: 1,
};

function render(rows: PoliticsMarketRow[]): string {
  (global as never as { __PAYLOAD__: unknown }).__PAYLOAD__ = payload(rows);
  return renderToStaticMarkup(React.createElement(PoliticsPage));
}

describe("the defect: the old sum over the served rows", () => {
  it("promised rows the page does not have", () => {
    expect(SAVE_ACT.outcome_count - 3).toBe(9);
    expect(KASH_PATEL.outcome_count - 3).toBe(5);
  });
});

describe("the card prints the page's count", () => {
  const markup = render([SAVE_ACT, KASH_PATEL, CLOSEST_GOVERNOR, MIFEPRISTONE]);

  it("SAVE America Act no longer says +9 more", () => {
    expect(badge(cardText(markup, SAVE_ACT.market_id))).toBeNull();
  });

  it("Kash Patel no longer says +5 more over the page's three rows", () => {
    expect(badge(cardText(markup, KASH_PATEL.market_id))).toBeNull();
  });

  it("a long live board keeps its badge", () => {
    expect(badge(cardText(markup, CLOSEST_GOVERNOR.market_id))).toBe("+19 more");
  });

  it("a card showing fewer than three rows counts from what it shows", () => {
    expect(badge(cardText(markup, MIFEPRISTONE.market_id))).toBe("+1 more");
  });
});

describe("a payload built before the server sent the count", () => {
  it("falls back to the old sum rather than dropping the badge", () => {
    const { more_count: _omit, ...older } = CLOSEST_GOVERNOR;
    void _omit;
    const markup = render([older]);
    expect(badge(cardText(markup, older.market_id))).toBe("+19 more");
  });
});
