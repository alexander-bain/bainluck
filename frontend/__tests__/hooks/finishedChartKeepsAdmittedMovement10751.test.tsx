/**
 * #10751 — when a game finishes, its chart keeps the real pre-finish movement
 * it already drew while the independent history read catches up.
 *
 * MOUNTED, not modelled (the #9051 / #10200 harness method). What is REAL:
 * `useLiveEventStream` — the hook, its controller, its one interval — over a
 * fake `EventSource` the test drives, including the disable that follows a
 * completed detail; the installed `swr` with the page's two keys (detail and
 * the `keepPreviousData` history key), so a history request can stay PENDING
 * while the old successful body is still held; the page's push write through
 * `applyLiveFrame`; and the page's chart composition, carried line for line
 * and PINNED by the structural test below against `app/events/[id]/page.tsx`.
 *
 * WHAT IS LEFT OUT, AND WHY IT DOES NOT TOUCH THE QUESTION: the page's 3,000
 * lines of render tree (the readable chart is proved separately, through the
 * real `OddsChart` at 390px, in `OddsChartLiveTail.test.tsx`), the folded
 * refetch branches of the push effect (every frame here is a valid newer write
 * to the one row the hero reads, so the page takes its final branch) and the
 * poll cadence (reads are driven explicitly).
 *
 * THE DEFECT, at fbe550ded4. While quotes are eligible the page merges the
 * session's admitted frames into the served body. A completed detail ends
 * eligibility, the page passes `[]`, and `mergeLiveChartHistory` hands back the
 * OLD served body — so the excursion the reader was just looking at vanishes
 * until the history read returns, although the hook still holds every frame.
 *
 * Network is a list of deferred promises the test resolves in its own order;
 * time is fake (`jest.useFakeTimers`, `Date.now` included). No assertion
 * branches on the wall clock (gotcha #44).
 */

import "../helpers/minimalDom";
import React, { act, useEffect, useMemo, useRef } from "react";
import { createRoot, type Root } from "react-dom/client";
import fs from "fs";
import path from "path";
import useSWR, { SWRConfig } from "swr";

import { useLiveEventStream, type LiveFrame } from "../../hooks/useLiveEventStream";
import { applyLiveFrame } from "../../lib/eventLivePush";
import { canSubscribeEventQuotes } from "../../lib/eventQuoteStream";
import { pinChartEdgeToHero } from "../../lib/chartEdgePin";
import {
  admitChartFrames,
  appendHeroObservation,
  finishedChartFrames,
  mergeLiveChartHistory,
  type AdmittedChartFrames,
} from "../../lib/liveChartHistory";

const PAGE = fs.readFileSync(path.join(__dirname, "../../app/events/[id]/page.tsx"), "utf8");

// ── a fake EventSource the test drives ─────────────────────────────────────
class FakeEventSource {
  static all: FakeEventSource[] = [];
  readyState = 0;
  closed = false;
  private listeners = new Map<string, ((e: unknown) => void)[]>();
  constructor(readonly url: string) {
    FakeEventSource.all.push(this);
  }
  addEventListener(type: string, fn: (e: unknown) => void) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), fn]);
  }
  close() {
    this.closed = true;
    this.readyState = 2;
  }
  emit(type: string, data?: unknown) {
    if (type === "open") this.readyState = 1;
    for (const fn of this.listeners.get(type) ?? []) fn(data === undefined ? {} : { data });
  }
}
(globalThis as Record<string, unknown>).EventSource = FakeEventSource;

// ── fixtures ────────────────────────────────────────────────────────────────
const A = 15329101;
const B = 15329102;
const T0 = Date.UTC(2026, 9, 8, 19, 0, 0);
const T = (s: number) => new Date(T0 + s * 1000).toISOString();

type Detail = {
  id: number;
  status: string;
  completed_at: string | null;
  hero_probability: number;
  hero_probability_away: number;
  hero_probability_source: string;
  hero_probability_observed_at: string | null;
  blend_fold_revision: Record<string, number> | null;
  win_probability_sources: Record<string, { value: number; updated_at: string }>;
};
type Point = { timestamp: string; home_probability: number };
type History = {
  event_id: number;
  status: string;
  completed_at: string | null;
  aggregate_line: Point[];
  win_prob_history: Record<string, { timestamp: string; home_probability: number; away_probability: number }[]>;
  blend_edge_pinned: boolean;
};

const liveDetail = (id = A): Detail => ({
  id, status: "live", completed_at: null,
  hero_probability: 0.40, hero_probability_away: 0.60, hero_probability_source: "blend",
  hero_probability_observed_at: T(0), blend_fold_revision: { [id]: 221 },
  win_probability_sources: {
    kalshi: { value: 0.41, updated_at: T(0) },
    polymarket: { value: 0.39, updated_at: T(-20) },
  },
});
/** The ordinary finished detail: settled result, a same-row vector at least
 * as new as anything drawn, and a completion stamp after the last frame. */
const completedDetail = (id = A, rev = 225, completedAt: string | null = T(300)): Detail => ({
  id, status: "completed", completed_at: completedAt,
  hero_probability: 1, hero_probability_away: 0, hero_probability_source: "settled",
  hero_probability_observed_at: null, blend_fold_revision: { [id]: rev },
  win_probability_sources: liveDetail(id).win_probability_sources,
});
const source = (points: [number, number][]) =>
  points.map(([s, p]) => ({ timestamp: T(s), home_probability: p, away_probability: 1 - p }));
/** The served two-source body the page held before the game ended: a real
 * backend blend line stopping at T0. */
const oldHistory = (id = A): History => ({
  event_id: id, status: "live", completed_at: null,
  aggregate_line: [{ timestamp: T(-600), home_probability: 0.38 }, { timestamp: T(0), home_probability: 0.40 }],
  win_prob_history: { kalshi: source([[-600, 0.39], [0, 0.41]]), polymarket: source([[-600, 0.37], [-20, 0.39]]) },
  blend_edge_pinned: true,
});

/** One row's write, `rev` keyed by that row (PR #9078's `build_frame`). */
const frame = (s: number, p: number, rev: number, id = A) => JSON.stringify({
  event_id: id, p, source: "kalshi", source_value: p, updated_at: T(s), status: "live",
  rev: { [id]: rev },
} satisfies LiveFrame);

/** Distinct minutes 19:01, 19:02, 19:03 — a real spike and its reversal. */
const MOVEMENT: [number, number, number][] = [[65, 0.42, 222], [125, 0.55, 223], [185, 0.43, 224]];

// ── deferred network ────────────────────────────────────────────────────────
class Deferred<V> {
  promise: Promise<V>;
  resolve!: (v: V) => void;
  constructor() {
    this.promise = new Promise((r) => { this.resolve = r; });
  }
}
type Net = { details: Deferred<Detail>[]; histories: Deferred<History>[] };

type Seen = {
  event?: Detail;
  aggregate: Point[];
  bank: number;
  status: string;
};
let seen: Seen = { aggregate: [], bank: 0, status: "" };
let handles: { refreshEvent: () => Promise<unknown>; refreshHistory: () => Promise<unknown> } | null = null;

// ── the harness: the page's detail/history/stream wiring and its composition ─
function ChartPage({ net, eventId }: { net: Net; eventId: number }) {
  const { data: event, mutate: refreshEvent } = useSWR(
    ["event", eventId],
    () => { const d = new Deferred<Detail>(); net.details.push(d); return d.promise; },
  );
  const { data: servedHistory, mutate: refreshHistory } = useSWR(
    ["history", eventId, false],
    () => { const d = new Deferred<History>(); net.histories.push(d); return d.promise; },
    { keepPreviousData: true },
  );
  handles = { refreshEvent: () => refreshEvent(), refreshHistory: () => refreshHistory() };

  // ── app/events/[id]/page.tsx — the hook, as the page calls it ──────────────
  const quoteEligible = canSubscribeEventQuotes(event);
  const { frame: liveFrame, chartPoints, status: reportedStreamStatus } = useLiveEventStream(eventId, quoteEligible);

  // ── the push effect's final branch, as the page writes it ──────────────────
  useEffect(() => {
    if (!liveFrame || liveFrame.event_id !== eventId) return;
    if (liveFrame.p === null || liveFrame.p === undefined) return;
    const frame = { ...liveFrame, p: liveFrame.p };
    refreshEvent((prev) => applyLiveFrame(prev, frame), { revalidate: false });
  }, [liveFrame, refreshEvent, eventId]);

  // ── app/events/[id]/page.tsx — the chart composition, carried (PINNED) ─────
  const admittedChartRef = useRef<AdmittedChartFrames | null>(null);
  const historyData = useMemo(
    () => {
      if (admittedChartRef.current?.eventId !== eventId) admittedChartRef.current = null;
      if (quoteEligible) admittedChartRef.current = admitChartFrames(eventId, chartPoints, event);
      const frames = quoteEligible
        ? admittedChartRef.current?.points ?? []
        : finishedChartFrames(admittedChartRef.current, eventId, event, servedHistory);
      const pushed = mergeLiveChartHistory(servedHistory, frames);
      const joined = pushed !== servedHistory ? pushed : pinChartEdgeToHero(servedHistory, event);
      return quoteEligible ? appendHeroObservation(joined, event, servedHistory) : joined;
    },
    [servedHistory, event, quoteEligible, chartPoints, eventId],
  );

  seen = {
    event,
    aggregate: historyData?.aggregate_line ?? [],
    bank: chartPoints.length,
    status: reportedStreamStatus,
  };
  return <>{`${event?.status ?? "loading"}|${historyData?.aggregate_line?.length ?? 0}`}</>;
}

// ── mount / drive helpers ───────────────────────────────────────────────────
async function settle() {
  await act(async () => {
    for (let i = 0; i < 12; i += 1) await Promise.resolve();
  });
}

const doc = document as unknown as { createElement: (t: string) => Element; body: { appendChild: (c: unknown) => void } };

async function mountPage(eventId = A) {
  const net: Net = { details: [], histories: [] };
  const container = doc.createElement("div");
  doc.body.appendChild(container);
  const root: Root = createRoot(container);
  let id = eventId;
  const render = () => root.render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <ChartPage net={net} eventId={id} />
    </SWRConfig>,
  );
  await act(async () => { render(); });
  await settle();
  const stream = () => FakeEventSource.all[FakeEventSource.all.length - 1];
  return {
    net,
    stream,
    async emit(type: string, data?: unknown) {
      await act(async () => { stream().emit(type, data); });
      await settle();
    },
    async resolveDetail(d: Detail) {
      net.details[net.details.length - 1].resolve(d);
      await settle();
    },
    async resolveHistory(h: History) {
      net.histories[net.histories.length - 1].resolve(h);
      await settle();
    },
    /** An ordinary detail read; the test resolves it. */
    async readDetail() {
      await act(async () => { void handles?.refreshEvent(); });
      await settle();
    },
    /** An ordinary history read; left PENDING until the test resolves it. */
    async readHistory() {
      await act(async () => { void handles?.refreshHistory(); });
      await settle();
    },
    async navigate(next: number) {
      id = next;
      await act(async () => { render(); });
      await settle();
    },
    unmount: () => act(() => { root.unmount(); }),
  };
}

/** Live page with the old served body and three admitted distinct-minute frames. */
async function livePageWithMovement() {
  const page = await mountPage();
  await page.resolveDetail(liveDetail());
  await page.resolveHistory(oldHistory());
  await page.emit("open");
  for (const [s, p, rev] of MOVEMENT) await page.emit("probability", frame(s, p, rev));
  return page;
}

const at = (s: number) => seen.aggregate.find((point) => point.timestamp === T(s))?.home_probability;

beforeEach(() => {
  jest.useFakeTimers();
  jest.setSystemTime(new Date(T0 + 200_000));
  FakeEventSource.all = [];
  handles = null;
  seen = { aggregate: [], bank: 0, status: "" };
});
afterEach(() => {
  jest.useRealTimers();
});

// ─────────────────────────────────────────────────────────────────────────────
describe("structural pin: the harness carries the page's own composition", () => {
  it("app/events/[id]/page.tsx still reads as the lines ChartPage mounts", () => {
    expect(PAGE).toContain("const quoteEligible = canSubscribeEventQuotes(event);");
    expect(PAGE).toMatch(/chartPoints,\s*status: reportedStreamStatus,\s*recoveryGeneration,\s*\} = useLiveEventStream\(eventId, quoteEligible\);/);
    expect(PAGE).toMatch(/if \(liveFrame\.p === null \|\| liveFrame\.p === undefined\) return;\s*latestLiveFrameRef\.current = liveFrame;\s*const frame = \{ \.\.\.liveFrame, p: liveFrame\.p \};\s*refreshEvent\(/);
    expect(PAGE.match(/\(prev\) => applyLiveFrame\(prev, frame\),/g)).toHaveLength(1);
    expect(PAGE).toMatch(/\(prev\) => applyLiveFrame\(prev, frame\),[^]{0,300}\{ revalidate: false \}/);
    expect(PAGE).toContain('["history", eventId, fullHistoryRequested]');
    expect(PAGE).toMatch(/keepPreviousData: true,\s*\}\s*\);/);
    // The composition, line for line, in order.
    const carried = [
      "const admittedChartRef = useRef<AdmittedChartFrames | null>(null);",
      "const historyData = useMemo(",
      "if (admittedChartRef.current?.eventId !== eventId) admittedChartRef.current = null;",
      "if (quoteEligible) admittedChartRef.current = admitChartFrames(eventId, chartPoints, event);",
      "const frames = quoteEligible",
      "? admittedChartRef.current?.points ?? []",
      ": finishedChartFrames(admittedChartRef.current, eventId, event, servedHistory);",
      "const pushed = mergeLiveChartHistory(servedHistory, frames);",
      "const joined = pushed !== servedHistory ? pushed : pinChartEdgeToHero(servedHistory, event);",
      "return quoteEligible ? appendHeroObservation(joined, event, servedHistory) : joined;",
      "[servedHistory, event, quoteEligible, chartPoints, eventId],",
    ];
    let from = 0;
    for (const line of carried) {
      const index = PAGE.indexOf(line, from);
      expect([line, index >= 0]).toEqual([line, true]);
      from = index + line.length;
    }
    // One admission site, one finished site: no second path that reads the raw bank.
    expect(PAGE.match(/admitChartFrames\(/g)).toHaveLength(1);
    expect(PAGE.match(/finishedChartFrames\(/g)).toHaveLength(1);
    expect(PAGE).not.toMatch(/quoteChartFrames\(/);
  });
});

describe("#10751 a finished game keeps the movement it already drew", () => {
  it("pre-finish: the three admitted distinct-minute observations are in the chart input", async () => {
    const page = await livePageWithMovement();
    expect(seen.event?.status).toBe("live");
    expect(seen.bank).toBe(3);
    expect([at(65), at(125), at(185)]).toEqual([0.42, 0.55, 0.43]);
    await page.unmount();
  });

  it("finish while the old history is pending: the drawn movement stays, the settled hero rules, the stream is closed", async () => {
    const page = await livePageWithMovement();
    await page.readHistory(); // the ordinary next history read, still in flight
    expect(page.net.histories).toHaveLength(2);
    await page.readDetail();
    await page.resolveDetail(completedDetail());

    // The finished detail is authoritative and the transport stood down…
    expect(seen.event?.status).toBe("completed");
    expect(seen.event?.hero_probability_source).toBe("settled");
    expect(page.stream().closed).toBe(true);
    expect(seen.status).toBe("idle");
    // …and the hook still holds its bank (the loss is the page's, not the hook's).
    expect(seen.bank).toBe(3);

    // THE SHIP: the observations the reader just saw remain, at their own
    // clocks and values, on the old served body.
    expect([at(65), at(125), at(185)]).toEqual([0.42, 0.55, 0.43]);
    expect(at(0)).toBe(0.40);
    // No result endpoint, no invented point.
    expect(seen.aggregate.map((point) => point.home_probability)).not.toContain(1);
    expect(seen.aggregate.map((point) => point.timestamp)).toEqual([T(-600), T(0), T(65), T(125), T(185)]);
    await page.unmount();
  });

  it("the history read lands: its exact-time correction wins, the other retained observations survive", async () => {
    const page = await livePageWithMovement();
    await page.readHistory();
    await page.readDetail();
    await page.resolveDetail(completedDetail());
    // The finished body: persisted through T125 (corrected to 54%), completed at T300.
    const finished: History = {
      ...oldHistory(), status: "completed", completed_at: T(300), blend_edge_pinned: false,
      aggregate_line: [...oldHistory().aggregate_line, { timestamp: T(125), home_probability: 0.54 }],
    };
    await page.resolveHistory(finished);
    expect([at(65), at(125), at(185)]).toEqual([0.42, 0.54, 0.43]);
    expect(seen.aggregate.filter((point) => point.timestamp === T(125))).toHaveLength(1);
    await page.unmount();
  });

  it("a frame delivered after the finish never joins: the stream is closed and nothing new is admitted", async () => {
    const page = await livePageWithMovement();
    const closedStream = page.stream();
    await page.readHistory();
    await page.readDetail();
    await page.resolveDetail(completedDetail());
    expect(closedStream.closed).toBe(true);
    await page.emit("probability", frame(240, 0.9, 224 + 1));
    expect(at(240)).toBeUndefined();
    expect(seen.aggregate.map((point) => point.timestamp)).toEqual([T(-600), T(0), T(65), T(125), T(185)]);
    await page.unmount();
  });

  it("CONTROL: a terminal vector BEHIND the drawn frames keeps the old behaviour", async () => {
    const page = await livePageWithMovement();
    await page.readHistory();
    await page.readDetail();
    await page.resolveDetail(completedDetail(A, 223));
    expect(seen.event?.status).toBe("completed");
    expect([at(65), at(125), at(185)]).toEqual([undefined, undefined, undefined]);
    await page.unmount();
  });

  it("CONTROL: no completion stamp on the finished detail keeps the old behaviour", async () => {
    const page = await livePageWithMovement();
    await page.readHistory();
    await page.readDetail();
    await page.resolveDetail(completedDetail(A, 225, null));
    expect([at(65), at(125), at(185)]).toEqual([undefined, undefined, undefined]);
    await page.unmount();
  });

  it("navigation to another event carries nothing across, and the old bank is never admitted there", async () => {
    const page = await livePageWithMovement();
    await page.navigate(B);
    await page.resolveDetail(completedDetail(B, 900));
    await page.resolveHistory(oldHistory(B));
    expect(seen.event?.id).toBe(B);
    expect(seen.bank).toBe(0);
    expect(seen.aggregate.map((point) => point.timestamp)).toEqual([T(-600), T(0)]);
    await page.unmount();
  });
});
