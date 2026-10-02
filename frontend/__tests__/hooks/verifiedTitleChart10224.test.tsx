/**
 * #10224 — the verified title detail's chart and stream, driven through real
 * SWR and the real hooks, over the server's own route fixtures (see
 * `__tests__/lib/verifiedTitleDetail10224.test.ts` for their provenance).
 *
 * Two requests can describe two moments. The chart is re-asked ONCE per
 * detail/range generation when its current column disagrees with the hero, a
 * disagreement after that keeps the history and drops current metadata, and a
 * response for a range the reader has left never lands on the chart.
 */
import "../helpers/minimalDom";
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { SWRConfig } from "swr";
import oddsVerified from "../fixtures/verifiedTitle10224/detail-odds-verified.json";
import oddsDefault from "../fixtures/verifiedTitle10224/detail-odds-default.json";
import kalshiVerified from "../fixtures/verifiedTitle10224/detail-kalshi-verified.json";
import kalshiDefault from "../fixtures/verifiedTitle10224/detail-kalshi-default.json";
import oddsTimeline from "../fixtures/verifiedTitle10224/timeline-odds-verified.json";
import kalshiTimeline from "../fixtures/verifiedTitle10224/timeline-kalshi-verified.json";
import type { FuturesMarketDetailResponse, ProbabilityTimelineResponse } from "@/lib/types";

const mockTimeline = jest.fn();
const mockMarket = jest.fn();
const mockHistory = jest.fn();
jest.mock("@/lib/api", () => ({
  fetchProbabilityTimeline: (...args: unknown[]) => mockTimeline(...args),
  fetchFuturesMarket: (...args: unknown[]) => mockMarket(...args),
  fetchFuturesHistory: (...args: unknown[]) => mockHistory(...args),
}));
let invalidate: ((ids: number[]) => void) | null = null;
jest.mock("@/hooks/useMarketStream", () => ({
  useMarketStream: (o: { onInvalidate: (ids: number[]) => void }) => { invalidate = o.onInvalidate; },
}));

import { useVerifiedTitleChart, type VerifiedTitleChart } from "@/hooks/useVerifiedTitleChart";
import { useFuturesDetailStream } from "@/hooks/useFuturesDetailStream";

const clone = <T,>(x: unknown) => structuredClone(x) as T;
const detail = (x: unknown) => clone<FuturesMarketDetailResponse>(x);
const timeline = (x: unknown) => clone<ProbabilityTimelineResponse>(x);
const BUFFALO_ODDS = 1309486;
const BUFFALO_KALSHI = 643833;

class Deferred<T> {
  promise: Promise<T>;
  resolve!: (v: T) => void;
  constructor() { this.promise = new Promise((r) => { this.resolve = r; }); }
}
const flush = async () => {
  for (let round = 0; round < 4; round++) {
    for (let i = 0; i < 20; i++) await Promise.resolve();
    await new Promise((r) => setTimeout(r, 2));
  }
};
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

let root: Root;
let container: unknown;
beforeEach(() => {
  mockTimeline.mockReset(); mockMarket.mockReset(); mockHistory.mockReset();
  invalidate = null;
  container = (document as unknown as { createElement: (t: string) => unknown }).createElement("div");
  root = createRoot(container as Element);
});
afterEach(async () => { await act(async () => root.unmount()); });

/* ───────────────────────── useVerifiedTitleChart ───────────────────────── */

let seen: VerifiedTitleChart | null = null;
function ChartProbe(props: { market: FuturesMarketDetailResponse; hours: number; heroId: number | null; settle: number }) {
  seen = useVerifiedTitleChart({ marketId: props.market.id, ...props, retrySettleMs: props.settle });
  return null;
}
const provider = () => new Map();
async function renderChart(market: FuturesMarketDetailResponse, hours = 168, heroId: number | null = BUFFALO_ODDS, settle = 0) {
  await act(async () => {
    root.render(
      <SWRConfig value={{ provider, dedupingInterval: 0 }}>
        <ChartProbe market={market} hours={hours} heroId={heroId} settle={settle} />
      </SWRConfig>,
    );
  });
  await act(flush);
}
const newer = () => {
  const t = timeline(oddsTimeline);
  t.outcomes.find((m) => m.id === BUFFALO_ODDS)!.current_probability = 0.135;
  return t;
};

describe("useVerifiedTitleChart", () => {
  it("CONTROL: a source-mode detail asks nothing and owns no chart", async () => {
    await renderChart(detail(oddsDefault));
    expect(mockTimeline).not.toHaveBeenCalled();
    expect(seen!.active).toBe(false);
    expect(seen!.history).toBeUndefined();
    expect(seen!.label).toBeNull();
  });

  it("a verified detail asks the opted-in timeline once and labels its own history", async () => {
    mockTimeline.mockResolvedValue(timeline(oddsTimeline));
    await renderChart(detail(oddsVerified));
    expect(mockTimeline).toHaveBeenCalledTimes(1);
    expect(mockTimeline).toHaveBeenCalledWith(86832, 50, 168, { representation: "verified_title" });
    expect(seen!.verdict).toBe("agree");
    expect(seen!.label).toBe("Sportsbooks history");
    expect(seen!.history!.outcomes.every((o) => o.current_price_available === true)).toBe(true);
  });

  it("same mode, newer value: one retry; persistent mismatch keeps history, drops current", async () => {
    mockTimeline.mockResolvedValue(newer());
    const market = detail(oddsVerified);
    await renderChart(market);
    expect(mockTimeline).toHaveBeenCalledTimes(2);
    expect(seen!.verdict).toBe("persistent");
    const buffalo = seen!.history!.outcomes.find((o) => o.outcome_id === BUFFALO_ODDS)!;
    expect(buffalo.history.length).toBe((oddsTimeline as ProbabilityTimelineResponse).timeline.length);
    expect(seen!.history!.outcomes.every((o) => !("current_price_available" in o))).toBe(true);
    expect(seen!.label).toBe("Sportsbooks history");
    // No loop: re-rendering the same generation asks nothing more.
    await renderChart(market);
    expect(mockTimeline).toHaveBeenCalledTimes(2);
  });

  it("a retry that comes back agreeing restores the current column", async () => {
    mockTimeline.mockResolvedValueOnce(newer()).mockResolvedValue(timeline(oddsTimeline));
    await renderChart(detail(oddsVerified));
    expect(mockTimeline).toHaveBeenCalledTimes(2);
    expect(seen!.verdict).toBe("agree");
  });

  it("a new detail generation (refresh/stream read) earns exactly one more retry", async () => {
    mockTimeline.mockResolvedValue(newer());
    await renderChart(detail(oddsVerified));
    expect(mockTimeline).toHaveBeenCalledTimes(2);
    await renderChart(detail(oddsVerified)); // a new object: the next detail read
    expect(mockTimeline).toHaveBeenCalledTimes(3);
    expect(seen!.verdict).toBe("persistent");
  });

  it("a stream read's paired timeline inside the settle window spends no retry", async () => {
    mockTimeline.mockResolvedValue(timeline(oddsTimeline));
    await renderChart(detail(oddsVerified), 168, BUFFALO_ODDS, 200);
    expect(mockTimeline).toHaveBeenCalledTimes(1);
    // The stream adopts its detail first: Buffalo moved to 13.5%…
    const moved = detail(oddsVerified);
    moved.outcomes.find((o) => o.id === BUFFALO_ODDS)!.probability = 0.135;
    await renderChart(moved, 168, BUFFALO_ODDS, 200);
    expect(seen!.verdict).toBe("retry");
    // …and its paired timeline lands a moment later.
    await act(async () => { await seen!.adopt(newer(), 168); await flush(); });
    expect(seen!.verdict).toBe("agree");
    await act(async () => { await sleep(300); await flush(); });
    expect(mockTimeline).toHaveBeenCalledTimes(1);
  });

  it("CONTROL: a mismatch that outlives the settle window does retry, once", async () => {
    mockTimeline.mockResolvedValue(newer());
    await renderChart(detail(oddsVerified), 168, BUFFALO_ODDS, 50);
    await act(async () => { await sleep(150); await flush(); });
    expect(mockTimeline).toHaveBeenCalledTimes(2);
    await act(async () => { await sleep(150); await flush(); });
    expect(mockTimeline).toHaveBeenCalledTimes(2);
    expect(seen!.verdict).toBe("persistent");
  });

  it("a range left behind never lands: the late 1W answer cannot overwrite 1M", async () => {
    const week = new Deferred<ProbabilityTimelineResponse>();
    const month = new Deferred<ProbabilityTimelineResponse>();
    mockTimeline.mockImplementation((_id: number, _top: number, hours: number) =>
      hours === 168 ? week.promise : month.promise);
    const market = detail(oddsVerified);
    await renderChart(market, 168);
    await renderChart(market, 720);
    const monthBody = { ...timeline(oddsTimeline), hours: 720 };
    await act(async () => { month.resolve(monthBody); await flush(); });
    await act(async () => { week.resolve({ ...timeline(oddsTimeline), hours: 168 }); await flush(); });
    expect(seen!.history!.hours).toBe(720);
    expect(seen!.verdict).toBe("agree");
  });

  it("a stream timeline for another range is refused; for this range it is adopted", async () => {
    mockTimeline.mockResolvedValue(timeline(oddsTimeline));
    await renderChart(detail(oddsVerified));
    const stale = { ...timeline(oddsTimeline), market_name: "STALE" };
    await act(async () => { await seen!.adopt(stale, 720); await flush(); });
    expect(seen!.history!.market_name).toBe("NFL Super Bowl Winner");
    const fresh = { ...timeline(oddsTimeline), market_name: "FRESH" };
    await act(async () => { await seen!.adopt(fresh, 168); await flush(); });
    expect(seen!.history!.market_name).toBe("FRESH");
    expect(mockTimeline).toHaveBeenCalledTimes(1);
  });

  it("refresh re-asks the chart", async () => {
    mockTimeline.mockResolvedValue(timeline(oddsTimeline));
    await renderChart(detail(oddsVerified));
    await act(async () => { await seen!.refresh(); await flush(); });
    expect(mockTimeline).toHaveBeenCalledTimes(2);
  });
});

/* ──────────────────────── useFuturesDetailStream ──────────────────────── */

const setMarket = jest.fn(async (_m: FuturesMarketDetailResponse) => undefined);
const setHistory = jest.fn(async () => undefined);
const setTimeline = jest.fn(async (_t: ProbabilityTimelineResponse, _h: number) => undefined);
function StreamProbe(props: { market: FuturesMarketDetailResponse; hours: number }) {
  useFuturesDetailStream({
    marketId: props.market.id, market: props.market, history: undefined, historyHours: props.hours,
    setMarket, setHistory, representation: "verified_title", setTimeline,
  });
  return null;
}
async function renderStream(market: FuturesMarketDetailResponse, hours = 168) {
  await act(async () => { root.render(<StreamProbe market={market} hours={hours} />); });
  await act(flush);
}

describe("useFuturesDetailStream, opted in", () => {
  beforeEach(() => { setMarket.mockClear(); setHistory.mockClear(); setTimeline.mockClear(); });

  it("a verified page re-reads opted-in detail + timeline, and adopts a sibling-only move", async () => {
    const held = detail(kalshiVerified);
    const next = detail(kalshiVerified);
    // A sibling venue quoted: the value moved, this row's own clock did not.
    next.outcomes.find((o) => o.id === BUFFALO_KALSHI)!.probability = 0.135;
    mockMarket.mockResolvedValue(next);
    mockTimeline.mockResolvedValue(timeline(kalshiTimeline));
    await renderStream(held);
    await act(async () => { invalidate!([held.id]); await flush(); });
    expect(mockMarket).toHaveBeenCalledWith(40533, expect.objectContaining({ fresh: true, representation: "verified_title" }));
    expect(mockTimeline).toHaveBeenCalledWith(40533, 50, 168, expect.objectContaining({ fresh: true, representation: "verified_title" }));
    expect(mockHistory).not.toHaveBeenCalled();
    expect(setMarket.mock.calls[0][0].outcomes.find((o) => o.id === BUFFALO_KALSHI)!.probability).toBe(0.135);
    expect(setTimeline).toHaveBeenCalledWith(expect.objectContaining({ market_id: 40533 }), 168);
  });

  it("a timeline answer for a range the reader has left is refused", async () => {
    const held = detail(kalshiVerified);
    const late = new Deferred<ProbabilityTimelineResponse>();
    mockMarket.mockResolvedValue(detail(kalshiVerified));
    mockTimeline.mockReturnValue(late.promise);
    await renderStream(held, 168);
    await act(async () => { invalidate!([held.id]); await flush(); });
    await renderStream(held, 720);
    await act(async () => { late.resolve(timeline(kalshiTimeline)); await flush(); });
    expect(setTimeline).not.toHaveBeenCalled();
  });

  it("CONTROL: a source-mode page keeps reading /history, still opted in on detail", async () => {
    const held = detail(kalshiDefault);
    mockMarket.mockResolvedValue(detail(kalshiDefault));
    mockHistory.mockResolvedValue({ market_id: 40533, market_name: "x", hours: 168, outcomes: [] });
    await renderStream(held);
    await act(async () => { invalidate!([held.id]); await flush(); });
    expect(mockHistory).toHaveBeenCalledTimes(1);
    expect(mockTimeline).not.toHaveBeenCalled();
    expect(mockMarket).toHaveBeenCalledWith(40533, expect.objectContaining({ representation: "verified_title" }));
  });
});
