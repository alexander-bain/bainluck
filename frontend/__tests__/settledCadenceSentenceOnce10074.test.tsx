/**
 * #10074 — A SETTLED BOARD SAID "Final — prices no longer update" TWICE.
 *
 * `bainluck.com/futures/60544002` at 390px, 2026-10-01 13:34Z, Probability Trend card:
 *
 *     1W  1M  All
 *     Final — prices no longer update
 *        [icon]
 *     Limited price history available
 *     Final — prices no longer update
 *
 * The served `/history` (same minute): `sparse: true`, ONE outcome with ONE point
 * (`bookmaker: settlement`, 1.0). The page hands the range controls the cadence
 * sentence on a sparse board, and `FuturesChart`'s under-two-points empty state
 * printed it again. Now the page computes the sentence once and tells the chart it
 * is on screen; the chart's other call sites pass nothing and keep their line.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ replace: () => {}, push: () => {} }),
}));

let ACTIVE_MARKET: unknown = null;
let ACTIVE_HISTORY: unknown = null;

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    if (key == null) return { data: undefined, error: null, isLoading: false };
    const tag = Array.isArray(key) ? key[0] : key;
    if (tag === "futures-market") {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      return { data: ACTIVE_MARKET as any, error: null, isLoading: false, mutate: () => {} };
    }
    if (tag === "futures-history") {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      return { data: ACTIVE_HISTORY as any, error: null, isLoading: false, mutate: () => {} };
    }
    return { data: undefined, error: null, isLoading: false, mutate: () => {} };
  },
}));

jest.mock("@/hooks", () => ({
  usePageTracking: () => {},
  useScrollDepth: () => {},
  useEngagementTime: () => {},
  usePinnedFutures: () => ({ isPinned: () => false, togglePin: () => {}, isMaxReached: false }),
}));

jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));

import FuturesDetailPage from "../app/futures/[id]/page";
import { FuturesChart } from "@/components/FuturesChart";

const CADENCE = "Final — prices no longer update";

function count(html: string, needle: string): number {
  return html.split(needle).length - 1;
}

function settledBoard(status: string) {
  return {
    id: 60544002,
    name: "Zbigniew Nocun vs Adam Staniczek",
    status,
    source: "kalshi",
    category: "mma",
    llm_sport_category: "mma",
    market_type: null,
    mutually_exclusive: true,
    outcome_count: 2,
    prices_withheld: 0,
    bookmakers: ["kalshi"],
    resolution_date: "2026-09-27T00:00:00+00:00",
    updated_at: "2026-10-01T12:18:13+00:00",
    outcomes: [
      { id: 226341650, name: "Zbigniew Nocun", probability: null, rank: 1,
        opening_probability: null, probability_change_24h: null, american_odds: null,
        opening_american_odds: null, is_winner: status === "resolved" ? true : null,
        resolution_source: status === "resolved" ? "api_settlement" : null,
        last_updated: "2026-10-01T12:18:13+00:00" },
      { id: 226341651, name: "Adam Staniczek", probability: null, rank: 2,
        opening_probability: null, probability_change_24h: null, american_odds: null,
        opening_american_odds: null, is_winner: status === "resolved" ? false : null,
        resolution_source: status === "resolved" ? "api_settlement" : null,
        last_updated: "2026-10-01T12:18:13+00:00" },
    ],
  };
}

/** `/api/futures/60544002/history` as served 2026-10-01 13:4xZ. */
function servedHistory(sparse: boolean) {
  return {
    market_id: 60544002,
    market_name: "Zbigniew Nocun vs Adam Staniczek",
    hours: 8760,
    actual_hours: 8760,
    outcomes: [
      {
        outcome_id: 226341650,
        name: "Zbigniew Nocun",
        history: [
          { timestamp: "2026-09-04T02:00:16+00:00", probability: 1.0, american_odds: null, bookmaker: "settlement" },
        ],
        eliminated: false,
        eliminated_at: null,
      },
    ],
    round_boundaries: null,
    leaderboard: null,
    total_data_points: 0,
    coverage_start: "2026-09-04T02:00:16+00:00",
    coverage_end: "2026-09-04T02:00:16+00:00",
    coverage_hours: 0,
    observation_times: 1,
    sparse,
  };
}

function render(market: unknown, history: unknown): string {
  ACTIVE_MARKET = market;
  ACTIVE_HISTORY = history;
  return renderToStaticMarkup(<FuturesDetailPage params={{ id: "60544002" }} />);
}

describe("#10074 the settled cadence sentence prints once", () => {
  it("the specimen prints it exactly once, beside the empty-chart line", () => {
    const html = render(settledBoard("resolved"), servedHistory(true));
    expect(html).toContain("Limited price history available");
    expect(count(html, CADENCE)).toBe(1);
  });

  it("CONTROL: not sparse ⇒ the header is silent and the chart keeps its own line", () => {
    const html = render(settledBoard("resolved"), servedHistory(false));
    expect(html).toContain("Limited price history available");
    expect(count(html, CADENCE)).toBe(1);
  });

  it("CONTROL: an open sparse board says nothing about cadence", () => {
    const html = render(settledBoard("open"), servedHistory(true));
    expect(count(html, CADENCE)).toBe(0);
  });
});

describe("FuturesChart cadenceNoteShown", () => {
  const thin = [
    {
      outcome_id: 1,
      name: "A",
      history: [{ timestamp: "2026-09-04T02:00:16+00:00", probability: 1.0, american_odds: null, bookmaker: "settlement" }],
    },
  ];

  it("other call sites (prop absent) keep the settled line", () => {
    const html = renderToStaticMarkup(
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      <FuturesChart historyData={thin as any} selectedOutcomes={new Set([1])} onToggleOutcome={() => {}} settled />,
    );
    expect(count(html, CADENCE)).toBe(1);
  });

  it("drops it when the caller says it is already on screen", () => {
    const html = renderToStaticMarkup(
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      <FuturesChart historyData={thin as any} selectedOutcomes={new Set([1])} onToggleOutcome={() => {}} settled cadenceNoteShown />,
    );
    expect(html).toContain("Limited price history available");
    expect(count(html, CADENCE)).toBe(0);
  });
});
