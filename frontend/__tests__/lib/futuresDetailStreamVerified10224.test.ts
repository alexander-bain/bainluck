/**
 * #10224 — the detail reconciler and API methods under `representation`.
 *
 * Source mode keeps every #9526 fence (that file still runs unchanged). A
 * verified answer is ONE composite: its values move under unchanged row clocks
 * when a sibling venue quotes, so it is adopted whole — and a fall back to
 * source mode must not carry a single verified value into a source-labelled
 * page.
 */
import oddsVerified from "../fixtures/verifiedTitle10224/detail-odds-verified.json";
import oddsRefused from "../fixtures/verifiedTitle10224/detail-odds-refused.json";
import kalshiVerified from "../fixtures/verifiedTitle10224/detail-kalshi-verified.json";
import kalshiDefault from "../fixtures/verifiedTitle10224/detail-kalshi-default.json";
import { createFuturesDetailReconciler, createFuturesReadScheduler } from "@/lib/futuresDetailStream";
import { createMarketStreamController } from "@/lib/marketStreamController";
import { fetchFuturesMarket, fetchProbabilityTimeline } from "@/lib/api";
import type { FuturesMarketDetailResponse } from "@/lib/types";

const detail = (x: unknown) => structuredClone(x) as FuturesMarketDetailResponse;
const BUFFALO = 643833;
const buffalo = (m: FuturesMarketDetailResponse) => m.outcomes.find((o) => o.id === BUFFALO)!;

describe("reconciler", () => {
  it("adopts a sibling-only verified move under an unchanged row clock", () => {
    const r = createFuturesDetailReconciler(detail(kalshiVerified));
    const next = detail(kalshiVerified);
    buffalo(next).probability = 0.135;
    expect(buffalo(next).last_updated).toBe(buffalo(detail(kalshiVerified)).last_updated);
    expect(buffalo(r.adopt(next)).probability).toBe(0.135);
  });

  it("CONTROL: the same move in source mode is still fenced by the row clock (#9526)", () => {
    const r = createFuturesDetailReconciler(detail(kalshiDefault));
    const next = detail(kalshiDefault);
    const before = buffalo(next).probability;
    buffalo(next).probability = 0.5;
    expect(buffalo(r.adopt(next)).probability).toBe(before);
  });

  it("a fall back to source carries no verified value, even with older row clocks", () => {
    const r = createFuturesDetailReconciler(detail(kalshiVerified));
    const fallback = detail(kalshiDefault);
    fallback.outcomes.forEach((o) => { o.last_updated = "2020-01-01T00:00:00+00:00"; });
    const out = r.adopt(fallback);
    expect(out).toBe(fallback);
    expect(out.representation).toBeUndefined();
    expect(out.outcomes.some((o) => o.contributing_sources !== undefined)).toBe(false);
  });

  it("source → verified is adopted whole", () => {
    const r = createFuturesDetailReconciler(detail(oddsRefused));
    const verified = detail(oddsVerified);
    expect(r.adopt(verified)).toBe(verified);
  });

  it("CONTROL: a settled verdict still outranks a later open verified body", () => {
    const settled = detail(kalshiDefault);
    settled.status = "resolved";
    settled.outcomes.forEach((o, i) => { o.is_winner = i === 0; });
    const r = createFuturesDetailReconciler(settled);
    expect(r.adopt(detail(kalshiVerified))).toBe(settled);
  });
});

describe("API methods: default URLs unchanged, opt-in appends one parameter", () => {
  const calls: string[] = [];
  let body: unknown = {};
  beforeEach(() => {
    calls.length = 0;
    global.fetch = jest.fn(async (url: string) => {
      calls.push(String(url));
      return { ok: true, status: 200, json: async () => body, headers: new Headers() };
    }) as unknown as typeof fetch;
  });
  const path = (u: string) => u.replace(/^https?:\/\/[^/]+/, "");

  it("detail", async () => {
    body = detail(oddsVerified);
    await fetchFuturesMarket(86832);
    await fetchFuturesMarket(86832, { fresh: true });
    await fetchFuturesMarket(86832, { representation: "verified_title" });
    await fetchFuturesMarket(86832, { fresh: true, representation: "verified_title" });
    await fetchFuturesMarket(86832, { representation: "source" });
    expect(calls.map(path)).toEqual([
      "/api/futures/86832",
      "/api/futures/86832?fresh=true",
      "/api/futures/86832?representation=verified_title",
      "/api/futures/86832?fresh=true&representation=verified_title",
      "/api/futures/86832",
    ]);
  });

  it("timeline", async () => {
    body = { market_id: 86832, outcomes: [], timeline: [] };
    await fetchProbabilityTimeline(86832, 10, 168);
    await fetchProbabilityTimeline(86832, 50, 168, { representation: "verified_title" });
    expect(calls.map(path)).toEqual([
      "/api/futures/86832/probability-timeline?top=10&hours=168",
      "/api/futures/86832/probability-timeline?top=50&hours=168&representation=verified_title",
    ]);
  });

  it("an opted-in verified body is sanitized; a default body is returned as served", async () => {
    const served = detail(oddsVerified);
    served.outcomes[0].rank_change_24h = 3;
    body = served;
    expect((await fetchFuturesMarket(86832, { representation: "verified_title" })).outcomes[0].rank_change_24h).toBeNull();
    expect((await fetchFuturesMarket(86832)).outcomes[0].rank_change_24h).toBe(3);
  });
});

test.each(["quote", "terminal"])("recovery owes a paced canonical REST %s without another market frame", async kind => {
  const initial = detail(kalshiDefault);
  const recovered = detail(kalshiDefault);
  recovered.outcomes.forEach((row, i) => {
    row.last_updated = new Date(Date.parse(row.last_updated!) + 1000).toISOString();
    row.probability = i === 0 ? 1 : 0;
    if (kind === "terminal") row.is_winner = i === 0;
  });
  if (kind === "terminal") recovered.status = "resolved";
  let served = initial;
  global.fetch = jest.fn(async () => ({
    ok: true, status: 200, json: async () => served, headers: new Headers(),
  })) as unknown as typeof fetch;
  let now = 0;
  const reconciler = createFuturesDetailReconciler(initial);
  const read = jest.fn(async (_signal: AbortSignal, current: () => boolean) => {
    const body = await fetchFuturesMarket(initial.id, { fresh: true });
    if (current()) reconciler.adopt(body);
  });
  const scheduler = createFuturesReadScheduler({ now: () => now, read });
  const listeners = new Map<string, (event: unknown) => void>();
  const wire = {
    readyState: 1,
    addEventListener: (name: string, callback: (event: unknown) => void) => { listeners.set(name, callback); },
    close: jest.fn(),
  };
  const controller = createMarketStreamController({
    marketIds: [initial.id], now: () => now, open: () => wire,
    onInvalidate: ids => { expect(ids).toEqual([initial.id]); scheduler.request(); },
  });
  const drain = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };
  try {
    controller.start();
    listeners.get("open")?.({ data: "{}" });
    await drain();
    served = recovered;
    now = 1000;
    listeners.get("resync")?.({ data: '{"generation":1}' });
    listeners.get("resync")?.({ data: '{"generation":1}' });
    listeners.get("heartbeat")?.({ data: "{}" });
    expect(read).toHaveBeenCalledTimes(1);
    expect(reconciler.current()).toBe(initial);
    now = 1999; scheduler.tick();
    expect(read).toHaveBeenCalledTimes(1);
    now = 2000; scheduler.tick(); await drain();
    expect(read).toHaveBeenCalledTimes(2);
    expect(reconciler.current()).toBe(recovered);
    if (kind === "terminal") expect(reconciler.current().outcomes[0].is_winner).toBe(true);
    expect(wire.close).not.toHaveBeenCalled();
  } finally {
    controller.stop(); scheduler.stop();
  }
});
