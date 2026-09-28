/**
 * #9474 — a /politics card names no "Leader" on a market whose legs can all be true.
 *
 * ═══ WHAT A READER SAW, production 2026-09-28 22:05Z at 390px ═══
 *
 *     Will the House pass a cap on federal student loan interest rates?
 *     LEADER  Before Jan 3, 2027                                      11%
 *             Before Dec 12, 2026                                      8%
 *
 * The latest deadline always scores highest on a deadline ladder ("Before Jan 3"
 * includes "Before Dec 12"), and on a pick-several list like "Who will Donald
 * Trump sue in 2026?" every row can come true, so neither has a leader. 57 of
 * the 68 cards served that minute were `mutually_exclusive = false` and all 57
 * said "Leader". The server now sends the flag; the card drops the word, keeps the row.
 *
 *   TZ=UTC npx jest --testPathPatterns=politicsCardNamesNoLeaderOnANonExclusiveMarket9474
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
    updated_at: "2026-09-28T22:05:00+00:00",
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

// Served 2026-09-28 22:05Z, with the flag the fixed server adds.
const STUDENT_LOAN_CAP: PoliticsMarketRow = {
  q: "Will the House pass a cap on federal student loan interest rates?",
  prob: 10.5,
  src: "kalshi",
  market_id: 59693681,
  top_outcomes: [
    { name: "Before Jan 3, 2027", prob: 10.5 },
    { name: "Before Dec 12, 2026", prob: 7.5 },
    { name: "Before Oct 2, 2026", prob: 4.5 },
  ],
  outcome_count: 3,
  more_count: 0,
  mutually_exclusive: false,
};
const TRUMP_SUES: PoliticsMarketRow = {
  q: "Who will Donald Trump sue in 2026?",
  prob: 13.5,
  src: "kalshi",
  market_id: 59693684,
  top_outcomes: [
    { name: "Center for American Progress", prob: 13.5 },
    { name: "Trevor Noah", prob: 10.5 },
    { name: "Michael Wolff", prob: 8.0 },
  ],
  outcome_count: 4,
  more_count: 1,
  mutually_exclusive: false,
};
// One winner: a real leader. The control.
const NEXT_POPE: PoliticsMarketRow = {
  q: "Who will the next Pope be?",
  prob: 6.3,
  src: "kalshi",
  market_id: 108219,
  top_outcomes: [
    { name: "Luis Antonio Tagle", prob: 6.3 },
    { name: "Pietro Parolin", prob: 4.8 },
    { name: "Pierbattista Pizzaballa", prob: 3.8 },
  ],
  outcome_count: 7,
  more_count: 4,
  mutually_exclusive: true,
};

function render(rows: PoliticsMarketRow[]): string {
  (global as never as { __PAYLOAD__: unknown }).__PAYLOAD__ = payload(rows);
  return renderToStaticMarkup(React.createElement(PoliticsPage));
}

describe("a market whose legs can all be true names no leader", () => {
  const markup = render([STUDENT_LOAN_CAP, TRUMP_SUES, NEXT_POPE]);

  it.each([
    ["deadline ladder", STUDENT_LOAN_CAP],
    ["pick-several list", TRUMP_SUES],
  ])("%s: no 'Leader', every row and number still printed", (_kind, row) => {
    const text = cardText(markup, row.market_id);
    expect(text).not.toMatch(/\bLeader\b/i);
    for (const o of row.top_outcomes) {
      expect(text).toContain(o.name);
      expect(text).toContain(`${Math.round(o.prob)}%`);
    }
  });

  it("a one-winner field still says Leader over its first row", () => {
    const text = cardText(markup, NEXT_POPE.market_id);
    expect(text).toMatch(/Leader Luis Antonio Tagle 6%/);
  });
});

describe("a payload or row without the flag", () => {
  it("keeps the word — only an explicit false removes it", () => {
    const { mutually_exclusive: _omit, ...older } = STUDENT_LOAN_CAP;
    void _omit;
    const markup = render([older, { ...TRUMP_SUES, mutually_exclusive: null }]);
    expect(cardText(markup, older.market_id)).toMatch(/Leader Before Jan 3, 2027/);
    expect(cardText(markup, TRUMP_SUES.market_id)).toMatch(/Leader Center for American Progress/);
  });
});
