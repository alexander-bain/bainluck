/**
 * #10266 — the question page's trend chart keeps each team's colour when the
 * reader changes range.
 *
 * On `/futures/231` the chart dealt its colours in the history response's
 * order, which changes with `hours=`: Pittsburgh red on 1M and blue on 1W.
 * The page now passes the market's own outcome order (`seriesOrder`).
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import oddsVerified from "./fixtures/verifiedTitle10224/detail-odds-verified.json";
import { inFixedSeriesOrder } from "@/lib/futuresDetailDisplay";
import { FuturesChart } from "@/components/FuturesChart";

jest.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
}));

const point = (h: number, p: number) => ({
  timestamp: new Date(Date.UTC(2026, 9, 2, h)).toISOString(), probability: p, american_odds: null, bookmaker: "consensus",
});
const series = (outcome_id: number, name: string, p: number) => ({
  outcome_id, name, history: Array.from({ length: 12 }, (_, h) => point(h, p)),
});
// The fixture market's own outcome order is Bills, Rams, 49ers, Chiefs, ...
const BILLS = series(1309486, "Buffalo Bills", 0.11);
const RAMS = series(1309485, "Los Angeles Rams", 0.1);
const NINERS = series(1309494, "San Francisco 49ers", 0.09);
/** Two range windows of one board: the same three lines, the response in a
 *  different order each time (the 1M vs 1W shape on /futures/231). */
const WINDOW_1M = [NINERS, RAMS, BILLS];
const WINDOW_1W = [RAMS, BILLS, NINERS];

let HISTORY_OUTCOMES: unknown[] = [];
jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    const none = { data: undefined, error: undefined, isLoading: false, mutate: () => {} };
    if (key == null) return none;
    const k = key as unknown[];
    if (k[0] === "futures-market") {
      return { ...none, data: structuredClone(oddsVerified) };
    }
    if (k[0] === "futures-history") {
      return {
        ...none,
        data: {
          market_id: 86832, market_name: "x", hours: 168, total_data_points: 36, sparse: false,
          outcomes: structuredClone(HISTORY_OUTCOMES),
        },
      };
    }
    return none;
  },
}));
jest.mock("@/hooks", () => ({
  usePageTracking: () => {},
  useScrollDepth: () => {},
  useEngagementTime: () => {},
  usePinnedFutures: () => ({ isPinned: () => false, togglePin: () => {}, isMaxReached: false }),
}));
jest.mock("@/components/Analytics", () => ({ useAnalyticsContext: () => ({ track: () => {} }) }));
jest.mock("@/hooks/useMarketStream", () => ({ useMarketStream: () => {} }));

import FuturesDetailPage from "../app/futures/[id]/page";

/** name → colour, read off the chart's legend swatches. */
function legendColours(html: string): Map<string, string> {
  const out = new Map<string, string>();
  const re = /background-color:(#[0-9a-fA-F]{3,8})"><\/span><span class="text-text-primary[^"]*">([^<]+)</g;
  for (const m of html.matchAll(re)) out.set(m[2], m[1].toLowerCase());
  return out;
}
function pageAt(window: unknown[]): string {
  HISTORY_OUTCOMES = window;
  return renderToStaticMarkup(<FuturesDetailPage params={{ id: "86832" }} />);
}
function chartAt(window: typeof WINDOW_1M, seriesOrder?: number[]): string {
  return renderToStaticMarkup(
    <FuturesChart historyData={window} onToggleOutcome={() => {}} seriesOrder={seriesOrder} />,
  );
}

describe("#10266 a line keeps its colour across range chips", () => {
  it("the question page colours each team the same on two windows whose responses disagree on order", () => {
    const a = legendColours(pageAt(WINDOW_1M));
    const b = legendColours(pageAt(WINDOW_1W));
    expect([...a.keys()].sort()).toEqual(["Buffalo Bills", "Los Angeles Rams", "San Francisco 49ers"]);
    expect(b).toEqual(a);
    // Three lines, three colours.
    expect(new Set(a.values()).size).toBe(3);
    // And the legend reads in the market's order, not the response's.
    expect([...a.keys()]).toEqual(["Buffalo Bills", "Los Angeles Rams", "San Francisco 49ers"]);
  });

  it("STRAWMAN: without an order the chart recolours on the same two windows (the defect shape)", () => {
    const a = legendColours(chartAt(WINDOW_1M));
    const b = legendColours(chartAt(WINDOW_1W));
    expect(a.get("Buffalo Bills")).not.toBe(b.get("Buffalo Bills"));
  });

  it("the chart with an order colours by it", () => {
    const order = [BILLS.outcome_id, RAMS.outcome_id, NINERS.outcome_id];
    expect(legendColours(chartAt(WINDOW_1M, order))).toEqual(legendColours(chartAt(WINDOW_1W, order)));
  });

  it("inFixedSeriesOrder orders by the list, puts unnamed ids after in response order, and never changes the set", () => {
    const rows = [{ outcome_id: 9 }, { outcome_id: 3 }, { outcome_id: 7 }, { outcome_id: 1 }];
    expect(inFixedSeriesOrder(rows, [1, 3]).map((r) => r.outcome_id)).toEqual([1, 3, 9, 7]);
    expect(inFixedSeriesOrder(rows, []).map((r) => r.outcome_id)).toEqual([9, 3, 7, 1]);
    expect(inFixedSeriesOrder(rows, undefined)).not.toBe(rows);
    expect(inFixedSeriesOrder(rows, [5, 6])).toEqual(rows);
  });
});
