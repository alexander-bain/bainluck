/**
 * #10265 + #10266 — the question page (`/futures/[id]`), reached from a live
 * game's Bigger Picture card.
 *
 * #10265: the back control was a hard link to /discover, so a reader who came
 * from `/events/15318028` (Pitt @ Virginia Tech, 4th quarter) lost the game.
 * It now goes back in history when the entry behind it is ours.
 *
 * #10266: on `/futures/231` the trend chart dealt its colours in the history
 * response's order, which changes with the range: Pittsburgh red on 1M and
 * blue on 1W. The page now passes the market's own outcome order.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import oddsVerified from "./fixtures/verifiedTitle10224/detail-odds-verified.json";
import { canGoBackInApp, followBackInApp, type InAppBackEnv } from "@/lib/inAppBack";
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

describe("#10265 the question page's back control", () => {
  const ORIGIN = "https://bainluck.com";
  const env = (over: Partial<InAppBackEnv>): InAppBackEnv => ({
    location: { origin: ORIGIN, pathname: "/futures/231" },
    historyLength: 3,
    referrer: "",
    documentLoadUrl: `${ORIGIN}/futures/231`,
    ...over,
  });

  it("goes back in the app after a client-side move from the game page (the specimen walk)", () => {
    expect(canGoBackInApp(env({ documentLoadUrl: `${ORIGIN}/events/15318028` }))).toBe(true);
    // The tab first loaded Discover from a search engine, then moved in-app.
    expect(
      canGoBackInApp(env({ documentLoadUrl: `${ORIGIN}/`, referrer: "https://www.google.com/" })),
    ).toBe(true);
  });

  it("goes back in the app when the document was loaded from one of our pages", () => {
    expect(canGoBackInApp(env({ referrer: `${ORIGIN}/events/15318028` }))).toBe(true);
  });

  it("CONTROLS: keeps the Discover link for a fresh tab, a shared link, an outside referrer", () => {
    // A link opened in a new tab carries our referrer but has nothing behind it.
    expect(canGoBackInApp(env({ historyLength: 1, referrer: `${ORIGIN}/events/1` }))).toBe(false);
    expect(canGoBackInApp(env({ historyLength: 1, documentLoadUrl: `${ORIGIN}/events/1` }))).toBe(false);
    // Loaded here, from outside.
    expect(canGoBackInApp(env({ referrer: "https://t.co/abc" }))).toBe(false);
    expect(canGoBackInApp(env({}))).toBe(false);
    // A range tap rewrites the query only; same path is not a move.
    expect(canGoBackInApp(env({ documentLoadUrl: `${ORIGIN}/futures/231?range=1W` }))).toBe(false);
    // Nothing readable falls back to the old behaviour.
    expect(canGoBackInApp(env({ documentLoadUrl: null }))).toBe(false);
    expect(canGoBackInApp(env({ documentLoadUrl: "https://elsewhere.example/x" }))).toBe(false);
  });

  const click = (over: Partial<Parameters<typeof followBackInApp>[0]> = {}) => {
    const e = {
      button: 0, metaKey: false, ctrlKey: false, shiftKey: false, altKey: false,
      preventDefault: jest.fn(),
      ...over,
    };
    return e;
  };

  it("a plain click goes back and stops the link; a modified or middle click is left to the link", () => {
    const back = jest.fn();
    const plain = click();
    expect(followBackInApp(plain, true, back)).toBe(true);
    expect(plain.preventDefault).toHaveBeenCalled();
    expect(back).toHaveBeenCalledTimes(1);

    for (const over of [{ metaKey: true }, { ctrlKey: true }, { shiftKey: true }, { altKey: true }, { button: 1 }]) {
      const e = click(over);
      expect(followBackInApp(e, true, back)).toBe(false);
      expect(e.preventDefault).not.toHaveBeenCalled();
    }
    expect(back).toHaveBeenCalledTimes(1);
  });

  it("CONTROL: with nothing of ours behind the page, the click is the Discover link's", () => {
    const back = jest.fn();
    const e = click();
    expect(followBackInApp(e, false, back)).toBe(false);
    expect(e.preventDefault).not.toHaveBeenCalled();
    expect(back).not.toHaveBeenCalled();
  });

  it("the server render keeps the Discover link and label (the page cannot know the history yet)", () => {
    const html = pageAt(WINDOW_1M);
    expect(html).toMatch(/<a [^>]*href="\/discover"[^>]*>(?:(?!<\/a>)[\s\S])*Back to Discover<\/a>/);
  });
});
