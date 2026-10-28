/**
 * #11588 — a game page held open through the final ends its chart on the
 * winner, the same as a fresh load.
 *
 * MOUNTED, the #10751 harness (`finishedChartKeepsAdmittedMovement10751`):
 * the real `useLiveEventStream` over a fake `EventSource`, the installed `swr`
 * with the page's detail and `keepPreviousData` history keys, the page's push
 * write through `applyLiveFrame`, and the page's chart composition carried line
 * for line (PINNED below and in the #10751 suite).
 *
 * THE DEFECT, at 534d8748. Production 15334266 (Grizzlies @ Warriors), web,
 * one page, no reload: at the final the hero read Final / Grizzlies WON, but
 * the line ended on a live 82% and the resting readout read 71%; a fresh load
 * ended on 100%. The finished history the page polled DID carry the result —
 * the backend appends it as the blend line's LAST element, out of time order,
 * at the minute play ended (floored), and tags it `evidence.kind: "final"` on
 * every source series. The page merged its retained live observations into
 * that body: a reading later in the result's minute won the minute, the
 * source readings carried the series past the result, and the re-sort put a
 * post-final market point last, which is what the readout reads.
 *
 * Network is deferred promises the test resolves in its own order; time is
 * fake. No assertion branches on the wall clock (gotcha #44).
 */

import "../helpers/minimalDom";
import React, { act, useCallback, useMemo, useRef, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import fs from "fs";
import path from "path";
import useSWR, { SWRConfig } from "swr";

import { useLiveEventStream, type LiveFrame } from "../../hooks/useLiveEventStream";
import { applyLiveFrame } from "../../lib/eventLivePush";
import { frameCarriesUnpricedSnapshot } from "../../lib/sourceSnapshot";
import { canSubscribeEventQuotes } from "../../lib/eventQuoteStream";
import { pinChartEdgeToHero } from "../../lib/chartEdgePin";
import { latestBlendPoint } from "../../lib/eventKeyStats";
import {
  admitChartFrames,
  appendHeroObservation,
  admitCurrentSourceObservations,
  appendAdmittedSourceObservations,
  finishedChartFrames,
  mergeLiveChartHistory,
  type AdmittedChartFrames,
} from "../../lib/liveChartHistory";

const PAGE = fs.readFileSync(path.join(__dirname, "../../app/events/[id]/page.tsx"), "utf8");

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
const A = 15334266;
const T0 = Date.UTC(2026, 9, 24, 4, 50, 0);
const T = (s: number) => new Date(T0 + s * 1000).toISOString();

type SourceReading = { value: number; updated_at: string };
type Detail = {
  id: number;
  status: string;
  completed_at: string | null;
  hero_probability: number;
  hero_probability_away: number;
  hero_probability_source: string;
  hero_probability_observed_at: string | null;
  blend_fold_revision: Record<string, number> | null;
  win_probability_sources: Record<string, SourceReading>;
};
type Point = { timestamp: string; home_probability: number };
type WpPoint = { timestamp: string; home_probability: number; away_probability: number | null; evidence?: { kind: string } };
type History = {
  event_id: number;
  status: string;
  completed_at: string | null;
  aggregate_line: Point[];
  win_prob_history: Record<string, WpPoint[]>;
  blend_edge_pinned: boolean;
};

const liveDetail = (): Detail => ({
  id: A, status: "live", completed_at: null,
  hero_probability: 0.40, hero_probability_away: 0.60, hero_probability_source: "blend",
  hero_probability_observed_at: T(0), blend_fold_revision: { [A]: 221 },
  win_probability_sources: { kalshi: { value: 0.41, updated_at: T(0) } },
});
/** Home (Warriors) lost; the play ended inside 04:54 and the row was written at 04:54:35. */
const completedDetail = (): Detail => ({
  ...liveDetail(), status: "completed", completed_at: T(275),
  hero_probability: 0, hero_probability_away: 1, hero_probability_source: "settled",
  hero_probability_observed_at: null, blend_fold_revision: { [A]: 230 },
});
const wp = (points: [number, number][]): WpPoint[] =>
  points.map(([s, p]) => ({ timestamp: T(s), home_probability: p, away_probability: 1 - p }));
const liveHistory = (): History => ({
  event_id: A, status: "live", completed_at: null,
  aggregate_line: [{ timestamp: T(-600), home_probability: 0.38 }, { timestamp: T(0), home_probability: 0.40 }],
  win_prob_history: { kalshi: wp([[-600, 0.39], [0, 0.41]]) },
  blend_edge_pinned: true,
});
/** The finished body as `/history` serves it: persisted minutes, a post-final
 * market minute (04:55), and the RESULT appended last at 04:54:00 — the minute
 * play ended, floored — tagged `final` on the source series. */
const RESULT_AT = 240;
const settledHistory = (): History => ({
  event_id: A, status: "completed", completed_at: T(275),
  aggregate_line: [
    { timestamp: T(-600), home_probability: 0.38 }, { timestamp: T(0), home_probability: 0.40 },
    { timestamp: T(60), home_probability: 0.42 }, { timestamp: T(120), home_probability: 0.55 },
    { timestamp: T(180), home_probability: 0.43 }, { timestamp: T(300), home_probability: 0.29 },
    { timestamp: T(RESULT_AT), home_probability: 0 },
  ],
  win_prob_history: {
    kalshi: [
      ...wp([[-600, 0.39], [0, 0.41], [65, 0.42], [125, 0.55], [185, 0.43]]),
      { ...wp([[230, 0.18]])[0], evidence: { kind: "terminal_row" } },
      { ...wp([[RESULT_AT, 0]])[0], evidence: { kind: "final" } },
    ],
  },
  blend_edge_pinned: false,
});
/** The same finished body before the result was appended: the history has not caught up. */
const unsettledFinishedHistory = (): History => {
  const body = settledHistory();
  return {
    ...body,
    aggregate_line: body.aggregate_line.slice(0, -1),
    win_prob_history: { kalshi: body.win_prob_history.kalshi.slice(0, -1) },
  };
};

const frame = (s: number, p: number, rev: number) => JSON.stringify({
  event_id: A, p, source: "kalshi", source_value: p, updated_at: T(s), status: "live",
  rev: { [A]: rev },
} satisfies LiveFrame);

/** Distinct minutes 04:51–04:53, then the last live reading INSIDE the result's minute (04:54:15). */
const movementEndingOn = (last: number): [number, number, number][] =>
  [[65, 0.42, 222], [125, 0.55, 223], [185, 0.43, 224], [255, last, 225]];

// ── deferred network ────────────────────────────────────────────────────────
class Deferred<V> {
  promise: Promise<V>;
  resolve!: (v: V) => void;
  constructor() {
    this.promise = new Promise((r) => { this.resolve = r; });
  }
}
type Net = { details: Deferred<Detail>[]; histories: Deferred<History>[] };

type Seen = { event?: Detail; history?: History };
let seen: Seen = {};
let handles: { refreshEvent: () => Promise<unknown>; refreshHistory: () => Promise<unknown> } | null = null;

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

  const applyPushedFrame = useCallback((liveFrame: LiveFrame) => {
    if (liveFrame.event_id !== eventId) return;
    if (liveFrame.p === null || liveFrame.p === undefined || frameCarriesUnpricedSnapshot(liveFrame)) return;
    const frame = { ...liveFrame, p: liveFrame.p };
    refreshEvent((prev) => applyLiveFrame(prev, frame), { revalidate: false });
  }, [refreshEvent, eventId]);

  const quoteEligible = canSubscribeEventQuotes(event);
  const { chartPoints } = useLiveEventStream(eventId, quoteEligible, applyPushedFrame, undefined, event?.blend_fold_revision);

  // ── app/events/[id]/page.tsx — the chart composition, carried (PINNED) ─────
  const [sourceObservationVersion] = useState(0);
  const admittedChartRef = useRef<AdmittedChartFrames | null>(null);
  const historyData = useMemo(
    () => {
      if (admittedChartRef.current?.eventId !== eventId) admittedChartRef.current = null;
      if (quoteEligible) admittedChartRef.current = admitCurrentSourceObservations(
        admitChartFrames(eventId, chartPoints, event), admittedChartRef.current, servedHistory, event,
      );
      const frames = quoteEligible
        ? admittedChartRef.current?.points ?? []
        : finishedChartFrames(admittedChartRef.current, eventId, event, servedHistory);
      const observed = appendAdmittedSourceObservations(servedHistory, admittedChartRef.current, event);
      const pushed = mergeLiveChartHistory(observed, frames);
      const joined = pushed !== observed ? pushed : pinChartEdgeToHero(observed, event);
      return quoteEligible
        ? appendHeroObservation(joined, event, servedHistory)
        : joined;
    },
    [servedHistory, event, quoteEligible, chartPoints, eventId, sourceObservationVersion],
  );

  seen = { event, history: historyData };
  return <>{`${event?.status ?? "loading"}|${historyData?.aggregate_line?.length ?? 0}`}</>;
}

async function settle() {
  await act(async () => {
    for (let i = 0; i < 12; i += 1) await Promise.resolve();
  });
}

const doc = document as unknown as { createElement: (t: string) => Element; body: { appendChild: (c: unknown) => void } };

async function mountPage() {
  const net: Net = { details: [], histories: [] };
  const container = doc.createElement("div");
  doc.body.appendChild(container);
  const root: Root = createRoot(container);
  await act(async () => {
    root.render(
      <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
        <ChartPage net={net} eventId={A} />
      </SWRConfig>,
    );
  });
  await settle();
  const stream = () => FakeEventSource.all[FakeEventSource.all.length - 1];
  return {
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
    async readDetail() {
      await act(async () => { void handles?.refreshEvent(); });
      await settle();
    },
    async readHistory() {
      await act(async () => { void handles?.refreshHistory(); });
      await settle();
    },
    unmount: () => act(() => { root.unmount(); }),
  };
}

/** Held through the final: live, four frames, the result detail, then the
 * finished history read the open page polls. */
async function heldThroughFinal(lastLive: number, finished: History) {
  const page = await mountPage();
  await page.resolveDetail(liveDetail());
  await page.resolveHistory(liveHistory());
  await page.emit("open");
  for (const [s, p, rev] of movementEndingOn(lastLive)) await page.emit("probability", frame(s, p, rev));
  await page.readHistory();
  await page.readDetail();
  await page.resolveDetail(completedDetail());
  await page.resolveHistory(finished);
  return page;
}

/** What the chart's result minute draws: one reading per minute, the last written wins. */
const resultMinute = (line: Point[]) => {
  const minute = Math.floor(Date.parse(T(RESULT_AT)) / 60_000);
  return line.filter((p) => Math.floor(Date.parse(p.timestamp) / 60_000) === minute).at(-1)?.home_probability;
};

beforeEach(() => {
  jest.useFakeTimers();
  jest.setSystemTime(new Date(T0 + 200_000));
  FakeEventSource.all = [];
  handles = null;
  seen = {};
});
afterEach(() => {
  jest.useRealTimers();
});

describe("structural pin: the harness carries the page's finished arm", () => {
  it("app/events/[id]/page.tsx still composes the chart through the same two finished-arm calls", () => {
    expect(PAGE).toContain(": finishedChartFrames(admittedChartRef.current, eventId, event, servedHistory);");
    expect(PAGE).toContain("const observed = appendAdmittedSourceObservations(servedHistory, admittedChartRef.current, event);");
    expect(PAGE).toContain("const pushed = mergeLiveChartHistory(observed, frames);");
  });
});

describe("#11588 a page held through the final ends on the winner, like a fresh load", () => {
  // Either side: the last live reading favours the side that lost (71% home),
  // or the winner short of the result (18% home = 82% away, production's line).
  it.each([
    ["the loser", 0.71],
    ["the winner short of 100%", 0.18],
  ])("last live reading in the final minute favours %s: the line, its minute and the readout all end on the result", async (_side, lastLive) => {
    const page = await heldThroughFinal(lastLive, settledHistory());
    expect(seen.event?.status).toBe("completed");
    expect(page.stream().closed).toBe(true);

    // The readout reads the last element; the result minute keeps its last reading.
    expect(latestBlendPoint(seen.history?.aggregate_line)).toBe(0);
    expect(resultMinute(seen.history!.aggregate_line)).toBe(0);
    // No live reading lands on the source series after the result.
    expect(seen.history?.win_prob_history.kalshi.at(-1)).toEqual(
      { timestamp: T(RESULT_AT), home_probability: 0, away_probability: 1, evidence: { kind: "final" } },
    );
    // A fresh load draws the served body exactly; the held page now does too.
    expect(seen.history).toEqual(settledHistory());
    await page.unmount();
  });

  it("CONTROL (#10751 unchanged): before the history carries the result, the movement already drawn stays", async () => {
    const page = await heldThroughFinal(0.18, unsettledFinishedHistory());
    const line = seen.history!.aggregate_line;
    // The four admitted frames ride on the finished-but-unsettled body at their own clocks.
    expect(line.find((p) => p.timestamp === T(255))?.home_probability).toBe(0.18);
    expect(line.find((p) => p.timestamp === T(125))?.home_probability).toBe(0.55);
    expect(line.map((p) => p.home_probability)).not.toContain(0);
    await page.unmount();
  });

  it("CONTROL: the result body that lands after the unsettled one replaces the retained readings", async () => {
    const page = await heldThroughFinal(0.18, unsettledFinishedHistory());
    expect(seen.history?.aggregate_line.some((p) => p.timestamp === T(255))).toBe(true);
    await page.readHistory();
    await page.resolveHistory(settledHistory());
    expect(seen.history).toEqual(settledHistory());
    expect(latestBlendPoint(seen.history?.aggregate_line)).toBe(0);
    await page.unmount();
  });
});
