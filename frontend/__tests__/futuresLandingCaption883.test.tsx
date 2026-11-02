/**
 * #883 — the futures/props landing page's caption describes the drawn line over
 * the range on screen and dates it; it no longer prints an undated "from
 * opening" comparison of two numbers the chart does not draw.
 *
 * Rendered through the real page over the #10224 fixture for 86832 (NFL title
 * board), with a `/history` answer whose leading drawn line (Buffalo) rose
 * across three days. The hero's served opening on that fixture is unrelated to
 * this window, which is exactly the case the old caption got wrong.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import oddsVerified from "./fixtures/verifiedTitle10224/detail-odds-verified.json";

jest.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ replace: () => {}, push: () => {} }),
}));

const point = (day: number, p: number | null) => ({
  timestamp: new Date(Date.UTC(2026, 9, day, 12)).toISOString(), probability: p, american_odds: null, bookmaker: "consensus",
});
let HISTORY: unknown = null;
let MARKET: unknown = null;
jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    if (key == null) return { data: undefined, error: undefined, isLoading: false, mutate: () => {} };
    const k = key as unknown[];
    if (k[0] === "futures-market") return { data: structuredClone(MARKET), error: undefined, isLoading: false, mutate: () => {} };
    if (k[0] === "futures-history") return { data: structuredClone(HISTORY), error: undefined, isLoading: false, mutate: () => {} };
    return { data: undefined, error: undefined, isLoading: false, mutate: () => {} };
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

function caption(history: unknown): string | null {
  HISTORY = history;
  MARKET = oddsVerified;
  const html = renderToStaticMarkup(<FuturesDetailPage params={{ id: "86832" }} />);
  const m = html.match(/data-testid="futures-trend-caption"[^>]*>([\s\S]*?)<\/p>/);
  return m ? m[1] : null;
}

const history = (bills: ReturnType<typeof point>[]) => ({
  market_id: 86832, market_name: "x", hours: 168, total_data_points: bills.length * 2, sparse: false,
  outcomes: [
    { outcome_id: 1309486, name: "Buffalo Bills", history: bills },
    { outcome_id: 1309485, name: "Los Angeles Rams", history: [point(1, 0.11), point(4, 0.11)] },
  ],
});

describe("#883 futures landing caption", () => {
  it("names the drawn leader's move over the visible range, dated, in whole points", () => {
    const text = caption(history([point(1, 0.08), point(2, 0.1), point(4, 0.1125)]));
    expect(text).toBe("Buffalo Bills up 3 pts since Oct 1.");
  });

  it("never prints the undated opening comparison", () => {
    const text = caption(history([point(1, 0.08), point(4, 0.1125)]));
    expect(text).not.toMatch(/from opening/);
  });

  it("CONTROL: a leading line with one priced point prints no caption at all", () => {
    expect(caption(history([point(1, null), point(4, 0.1125)]))).toBeNull();
  });
});
