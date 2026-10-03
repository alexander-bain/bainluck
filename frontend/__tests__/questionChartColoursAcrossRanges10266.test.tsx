/**
 * #10266 — the question page's trend chart keeps each team's colour when the
 * reader changes range.
 *
 * On `/futures/231` the chart dealt its colours in the history response's
 * order, which changes with `hours=`: Pittsburgh red on 1M and blue on 1W.
 * The page now passes the market's own outcome order (`seriesOrder`), and a
 * line's colour belongs to its outcome's place in that order, so it survives a
 * range whose response is in another order OR holds a different set of lines
 * (sol's review of 69e3879d91: with Rams absent on a sparse range, 49ers slid
 * from green to red).
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import oddsVerified from "./fixtures/verifiedTitle10224/detail-odds-verified.json";
import { inFixedSeriesOrder } from "@/lib/futuresDetailDisplay";
import { ELIMINATED_SERIES_COLOR, SERIES_COLORS, fixedOrderSeriesColors } from "@/lib/seriesColors";
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
/** A sparse range: Rams has no history in this window at all. */
const WINDOW_SPARSE = [NINERS, BILLS];

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
type Line = typeof BILLS & { eliminated?: boolean };
function chartAt(
  window: Line[],
  seriesOrder?: { id: number; name: string }[],
  outcomeColors?: Map<number, string>,
): string {
  return renderToStaticMarkup(
    <FuturesChart historyData={window} onToggleOutcome={() => {}} seriesOrder={seriesOrder} outcomeColors={outcomeColors} />,
  );
}
const ORDER = [BILLS, RAMS, NINERS].map((o) => ({ id: o.outcome_id, name: o.name }));

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

  it("the question page keeps a surviving team's colour when another team is missing from the range (sol's subset case)", () => {
    const full = legendColours(pageAt(WINDOW_1M));
    const sparse = legendColours(pageAt(WINDOW_SPARSE));
    expect([...sparse.keys()]).toEqual(["Buffalo Bills", "San Francisco 49ers"]);
    expect(sparse.get("San Francisco 49ers")).toBe(full.get("San Francisco 49ers"));
    expect(sparse.get("Buffalo Bills")).toBe(full.get("Buffalo Bills"));
  });

  it("the chart with an order colours by it, on a reordered and on a sparse window", () => {
    const a = legendColours(chartAt(WINDOW_1M, ORDER));
    expect(legendColours(chartAt(WINDOW_1W, ORDER))).toEqual(a);
    const sparse = legendColours(chartAt(WINDOW_SPARSE, ORDER));
    expect(sparse.get("San Francisco 49ers")).toBe(a.get("San Francisco 49ers"));
  });

  it("an explicit override and eliminated grey still win over the fixed-order colour", () => {
    const override = new Map([[NINERS.outcome_id, "#123456"]]);
    expect(legendColours(chartAt(WINDOW_1M, ORDER, override)).get("San Francisco 49ers")).toBe("#123456");
    const out = legendColours(chartAt([BILLS, { ...RAMS, eliminated: true }, NINERS], ORDER));
    expect(out.get("Los Angeles Rams")).toBe(ELIMINATED_SERIES_COLOR.toLowerCase());
    // The grey line takes no colour, and the others keep theirs.
    expect(out.get("San Francisco 49ers")).toBe(legendColours(chartAt(WINDOW_1M, ORDER)).get("San Francisco 49ers"));
  });

  it("fixedOrderSeriesColors: top-of-board colours never move; a deep outcome stays distinct from the drawn lines", () => {
    const board = Array.from({ length: 14 }, (_, i) => ({ id: 100 + i, name: `Team ${i}` }));
    const drawn = (ids: number[]) => ids.map((outcome_id) => ({ outcome_id }));
    const all = fixedOrderSeriesColors(drawn([100, 101, 102]), board, SERIES_COLORS);
    const some = fixedOrderSeriesColors(drawn([102]), board, SERIES_COLORS);
    expect(some.get(102)).toBe(all.get(102));
    expect(all.get(102)).toBe(SERIES_COLORS[2]);
    // Rank 10 cycles onto rank 0's colour; drawn together they must still differ.
    const deep = fixedOrderSeriesColors(drawn([100, 110]), board, SERIES_COLORS);
    expect(deep.get(100)).toBe(SERIES_COLORS[0]);
    expect(deep.get(110)).not.toBe(deep.get(100));
    // Drawn alone, the deep outcome takes its own cycled colour.
    expect(fixedOrderSeriesColors(drawn([110]), board, SERIES_COLORS).get(110)).toBe(SERIES_COLORS[0]);
    // A skipped (eliminated) line takes no colour.
    expect(fixedOrderSeriesColors([{ outcome_id: 100, skip: true }], board, SERIES_COLORS).has(100)).toBe(false);
  });

  it("fixedOrderSeriesColors keeps a party line on its party colour (#8095)", () => {
    const board = [{ id: 1, name: "Republicans" }, { id: 2, name: "Democrats" }];
    const out = fixedOrderSeriesColors([{ outcome_id: 1 }, { outcome_id: 2 }], board, SERIES_COLORS);
    expect(out.get(2)).toBe(SERIES_COLORS[0]); // Democrats blue
    expect(out.get(1)).toBe(SERIES_COLORS[1]); // Republicans red
  });

  it("inFixedSeriesOrder orders by the list, puts unnamed ids after in response order, and never changes the set", () => {
    const rows = [{ outcome_id: 9 }, { outcome_id: 3 }, { outcome_id: 7 }, { outcome_id: 1 }];
    expect(inFixedSeriesOrder(rows, [1, 3]).map((r) => r.outcome_id)).toEqual([1, 3, 9, 7]);
    expect(inFixedSeriesOrder(rows, []).map((r) => r.outcome_id)).toEqual([9, 3, 7, 1]);
    expect(inFixedSeriesOrder(rows, undefined)).not.toBe(rows);
    expect(inFixedSeriesOrder(rows, [5, 6])).toEqual(rows);
  });
});
