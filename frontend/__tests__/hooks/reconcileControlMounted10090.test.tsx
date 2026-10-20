/**
 * #10090 G1 — MOUNTED: a held LIVE page owes a `reconcile` floor (a source was
 * withdrawn) while prices keep moving. Does the page's cache — what the hero,
 * rail and chart read — lose the removed source, without the headline going
 * back, without another price, control or tap, and without reopening a final?
 *
 * WHAT IS REAL: react-dom over `helpers/minimalDom`; the installed `swr`; the
 * real `useLiveEventStream` → `createLiveStreamController` over a mocked
 * EventSource; and, lifted from `app/events/[id]/page.tsx` with the TypeScript
 * AST (no hand copy), the page's event fetcher, `onSuccess`, `applyPushedFrame`,
 * `applyReconcileControl`, `[foldedRefetch]` scheduler, recovery effect, paired
 * read and history-edge effect, over the real ordered adopters.
 *
 * WHAT IS SIMPLIFIED: no poll cadence (the test revalidates by hand), deferred
 * fetches, fake timers, and the render prints the cached hero / rail / revision
 * / chart edge instead of the components.
 */
import "../helpers/minimalDom";
import React, { act, useCallback, useEffect, useRef, useState, useMemo } from "react";
import { createRoot, type Root } from "react-dom/client";
import fs from "fs";
import path from "path";
import vm from "vm";
import ts from "typescript";
import useSWR, { SWRConfig } from "swr";

import { heldFrameAfter, useLiveEventStream } from "../../hooks/useLiveEventStream";
import type { StreamHandle } from "../../lib/liveStreamController";
import { createReconnectCatchup } from "../../lib/reconnectCatchup";
import { createFoldedRefetchScheduler, takeFreshRead } from "../../lib/foldedRefetchScheduler";
import { canSubscribeEventQuotes, coversQuoteRevision, quotePairCoversTrigger } from "../../lib/eventQuoteStream";
import { adoptFoldedQuote, applyLiveFrame, applyLiveFrameRail, frameInvalidatesFoldedBlend } from "../../lib/eventLivePush";
import { frameFoldOrder } from "../../lib/foldRevision";
import { frameCarriesUnpricedSnapshot, snapshotRailPaysPricelessTrigger } from "../../lib/sourceSnapshot";
import { carryNewerHeldState, fetchEventWithLiveFrame, keepNewerHeldHeadline } from "../../lib/reconcileEventPoll";
import { adoptNewerBlendEdge, edgeInvalidatesHeldBlend, servedBlendEdgeObservation } from "../../lib/blendObservationClock";
import { historyRangeParam } from "../../lib/event/historyRange";
import { EVENT_BOOT_HISTORY_HOURS } from "../../lib/event/detailBoot";
import {
  createReconcileLedger, createWriteJournal, rebaseOnCoveringRead, reconcileFloorCoverage, replayJournaledPoll,
  servedHistoryIsNewer,
} from "../../lib/reconcileControl";

import * as chart from "../../lib/liveChartHistory";
import * as pin from "../../lib/chartEdgePin";

const PAGE = fs.readFileSync(path.join(__dirname, "../../app/events/[id]/page.tsx"), "utf8");
const FOLDED_FRAME_REFETCH_MS = Number(PAGE.match(/const FOLDED_FRAME_REFETCH_MS = (\d+)/)![1]);
const LIVE_REFRESH_INTERVAL = Number(PAGE.match(/const LIVE_REFRESH_INTERVAL = (\d+)/)![1]);

function pageScript(pick: (n: ts.Node, tree: ts.SourceFile) => string | undefined): vm.Script {
  const tree = ts.createSourceFile("page.tsx", PAGE, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  let found: string | undefined;
  const visit = (n: ts.Node) => { found ??= pick(n, tree); ts.forEachChild(n, visit); };
  visit(tree);
  if (!found) throw new Error("page expression not found");
  return new vm.Script(ts.transpileModule(`(${found})`, {
    compilerOptions: { target: ts.ScriptTarget.ES2020 },
  }).outputText);
}
const firstArgOf = (callee: string, contains: string) => pageScript((n, tree) => {
  if (!ts.isCallExpression(n) || n.expression.getText(tree) !== callee) return undefined;
  const fn = n.arguments[0];
  return fn && ts.isArrowFunction(fn) && fn.getText(tree).includes(contains) ? fn.getText(tree) : undefined;
});
const RETRY_DELAY = pageScript((n, tree) => (ts.isVariableDeclaration(n) &&
  n.name.getText(tree) === "reconcileRetryDelayMs" && n.initializer) ? n.initializer.getText(tree) : undefined);
const FETCHER = pageScript((n, tree) => (ts.isCallExpression(n) && n.expression.getText(tree) === "useSWR" &&
  n.arguments[0]?.getText(tree) === '["event", eventId]') ? n.arguments[1].getText(tree) : undefined);
const ON_SUCCESS = pageScript((n, tree) => (ts.isPropertyAssignment(n) && n.name.getText(tree) === "onSuccess" &&
  ts.isArrowFunction(n.initializer) && n.initializer.getText(tree).includes("storedEventRef"))
  ? n.initializer.getText(tree) : undefined);
const PUSH = firstArgOf("useCallback", "adoptFoldedQuote(held, liveFrame, eventId)");
const CONTROL = firstArgOf("useCallback", "reconcileLedger.owe");
const FACTORY = pageScript((n, tree) => {
  if (!ts.isVariableDeclaration(n) || n.name.getText(tree) !== "[foldedRefetch]" ||
      !n.initializer || !ts.isCallExpression(n.initializer)) return undefined;
  const init = n.initializer.arguments[0];
  return init && ts.isArrowFunction(init) ? init.body.getText(tree) : undefined;
});
const RECOVERY_EFFECT = firstArgOf("useEffect", "createReconnectCatchup");
const PAIR = pageScript((n, tree) => (ts.isBinaryExpression(n) &&
  n.left.getText(tree) === "pairedQuoteReadRef.current" && ts.isArrowFunction(n.right))
  ? n.right.getText(tree) : undefined);
const HISTORY_MEMO = firstArgOf("useMemo", "admitCurrentSourceObservations");
const HISTORY_DEPS = pageScript((n, tree) => ts.isVariableDeclaration(n) && n.name.getText(tree) === "historyData" && n.initializer && ts.isCallExpression(n.initializer) ? n.initializer.arguments[1].getText(tree) : undefined);
const EDGE_EFFECT = firstArgOf("useEffect", "servedBlendEdgeObservation(servedHistory)");

// ── fixtures ────────────────────────────────────────────────────────────────
const E = 15332323;
const B = 15332999;
const T = (rev: number) => new Date(Date.UTC(2026, 9, 19, 1, 0, rev)).toISOString();
const src = (value: number, rev: number) => ({ value, updated_at: T(rev), display_name: "x", type: "market", color: "#000" });
type Rail = Record<string, ReturnType<typeof src>>;
type Detail = {
  id: number; status: string; sport: string; completed_at?: string | null;
  hero_probability: number; hero_probability_away: number | null; hero_probability_source: string;
  hero_probability_observed_at: string | null; blend_fold_revision?: Record<string, number>;
  win_probability_sources: Rail; home_score?: number | null; away_score?: number | null;
};
type History = {
  event_id: number; blend_edge_pinned: boolean; blend_edge_observed_at: string | null;
  blend_edge_fold_revision: Record<string, number> | null;
  history_fold_revision?: unknown;
  aggregate_line: { timestamp: string; home_probability: number }[];
};
const live = (rev: number, p: number, rail: Rail, id = E): Detail => ({
  id, status: "live", sport: "nfl", hero_probability: p, hero_probability_away: 1 - p,
  hero_probability_source: "blend", hero_probability_observed_at: T(rev),
  blend_fold_revision: { [id]: rev }, win_probability_sources: rail,
});
const final = (rev: number): Detail => ({
  ...live(rev, 1, { kalshi: src(1, rev) }), status: "completed", completed_at: T(rev),
  hero_probability_source: "settled",
});
const history = (rev: number, p: number, id = E): History => ({
  event_id: id, blend_edge_pinned: true, blend_edge_observed_at: T(rev), blend_edge_fold_revision: { [id]: rev },
  aggregate_line: [{ timestamp: T(rev), home_probability: p }],
});
// What the route serves when the line's right edge is not a "now" claim (no
// line, a stale pre-match line, outside the edge window): no pin, no revision.
const unpinned = (rev: number, p: number, id = E): History => ({
  ...history(rev, p, id), blend_edge_pinned: false, blend_edge_observed_at: null, blend_edge_fold_revision: null,
});
const withPm = (rev: number) => ({ kalshi: src(0.56, rev), polymarket: src(0.5, rev - 1) });
const frame = (rev: number, p: number, source = "kalshi") => JSON.stringify({
  event_id: E, p, source, source_value: p, updated_at: T(rev), status: "live", rev: { [E]: rev },
});
// #10090 source_snapshot: the same frame plus the write's complete source map.
const snapFrame = (rev: number, p: number, rail: Rail | Record<string, unknown>, over: Record<string, unknown> = {}) =>
  JSON.stringify({ ...JSON.parse(frame(rev, p)), source_snapshot: { event_id: E, rev: { [E]: rev }, win_probability_sources: rail }, ...over });
const control = (custody: string, floor: number, id = E) =>
  JSON.stringify({ event_id: id, custody_id: custody, removal_rev: { [id]: floor } });

// ── network ─────────────────────────────────────────────────────────────────
class Deferred<T> {
  promise: Promise<T>;
  resolve!: (v: T) => void;
  reject!: (e: Error) => void;
  constructor() { this.promise = new Promise<T>((res, rej) => { this.resolve = res; this.reject = rej; }); }
}
type Req<T> = { eventId: number; fresh: boolean; d: Deferred<T>; at: number; options?: unknown; done?: boolean };
type Net = { details: Req<Detail>[]; histories: Req<History>[] };

const harness: {
  revalidate?: () => unknown; revalidateHistory?: () => unknown; ledger?: ReturnType<typeof createReconcileLedger>;
  event?: Detail; fullHistory?: boolean; renderedHistory?: any;
  quoteTrigger?: () => unknown; sourceHistory?: () => unknown;
} = {};

function HeldPage({ net, eventId }: { net: Net; eventId: number }) {
  const fetchEvent = (id: number, fresh = false, options?: unknown) => {
    const d = new Deferred<Detail>(); net.details.push({ eventId: id, fresh, d, at: Date.now(), options }); return d.promise;
  };
  const fetchEventHistory = (id: number, _h: number, _r: unknown, fresh = false, options?: unknown) => {
    const d = new Deferred<History>(); net.histories.push({ eventId: id, fresh, d, at: Date.now(), options }); return d.promise;
  };
  const freshNextEventReadRef = useRef(false);
  const latestLiveFrameRef = useRef(null);
  const latestBlendEdgeRef = useRef(null);
  const heldEventRef = useRef<Detail | undefined>(undefined);
  const storedEventRef = useRef<Detail | undefined>(undefined);
  const pairJournalRef = useRef(null);
  const [, setLastRefresh] = useState(0);
  const { data: event, mutate: refreshEvent } = useSWR(["event", eventId], FETCHER.runInNewContext({
    fetchEventWithLiveFrame, fetchEvent, eventId, takeFreshRead, freshNextEventReadRef, pairJournalRef,
    replayJournaledPoll, keepNewerHeldHeadline, latestLiveFrameRef, latestBlendEdgeRef, heldEventRef,
  }), { onSuccess: ON_SUCCESS.runInNewContext({ storedEventRef, setLastRefresh, Date }) });
  harness.revalidate = () => refreshEvent();
  harness.event = event;
  heldEventRef.current = event;
  const fullHistoryRequested = harness.fullHistory ?? false;
  const { data: servedHistory, mutate: refreshHistory } = useSWR(["history", eventId],
    () => fetchEventHistory(eventId, EVENT_BOOT_HISTORY_HOURS, historyRangeParam(false)));
  harness.revalidateHistory = () => refreshHistory();

  const pairedQuoteReadRef = useRef<(() => Promise<unknown>) | null>(null);
  const quoteTriggerRef = useRef(null);
  const sourceAddedHistoryRef = useRef(null);
  harness.quoteTrigger = () => quoteTriggerRef.current;
  harness.sourceHistory = () => sourceAddedHistoryRef.current;
  const recoveryIntentRef = useRef(0);
  const quoteReadLifetimeRef = useRef(0);
  const reconcileIntentRef = useRef(false);
  const [reconcileLedger] = useState(createReconcileLedger);
  harness.ledger = reconcileLedger;
  const quoteEventIdRef = useRef(eventId);
  if (quoteEventIdRef.current !== eventId) reconcileLedger.clear();
  if (quoteEventIdRef.current !== eventId) { recoveryIntentRef.current = 0; quoteTriggerRef.current = null; sourceAddedHistoryRef.current = null; }
  quoteEventIdRef.current = eventId;
  const refreshEventRef = useRef(refreshEvent);
  refreshEventRef.current = refreshEvent;
  const [foldedRefetch] = useState(() => FACTORY.runInNewContext({
    createFoldedRefetchScheduler, canSubscribeEventQuotes, reconcileIntentRef, FOLDED_FRAME_REFETCH_MS, Date, reconcileLedger,
    reconcileRetryDelayMs: RETRY_DELAY.runInNewContext({ LIVE_REFRESH_INTERVAL, Math }),
    quoteTriggerRef, recoveryIntentRef, pairedQuoteReadRef, freshNextEventReadRef, refreshEventRef, heldEventRef,
  }) as ReturnType<typeof createFoldedRefetchScheduler>);
  useEffect(() => () => foldedRefetch.cancel(), [foldedRefetch]);

  const reconcileCatchupRef = useRef(null);
  const reconcileOrdinalRef = useRef(0);
  const applyPushedFrame = useCallback(PUSH.runInNewContext({
    eventId, heldEventRef, adoptFoldedQuote, pairJournalRef, refreshEvent, setLastRefresh, Date, reconcileCatchupRef, reconcileOrdinalRef,
    canSubscribeEventQuotes, quoteTriggerRef, sourceAddedHistoryRef, foldedRefetch, frameInvalidatesFoldedBlend,
    latestLiveFrameRef, heldFrameAfter, applyLiveFrame,
    applyLiveFrameRail, frameCarriesUnpricedSnapshot, frameFoldOrder, snapshotRailPaysPricelessTrigger,
  }), [refreshEvent, eventId, foldedRefetch]);
  const applyReconcileControl = useCallback(CONTROL.runInNewContext({
    eventId, canSubscribeEventQuotes, heldEventRef, reconcileLedger, Date,
    reconcileCatchupRef, reconcileOrdinalRef,
  }), [eventId, reconcileLedger]);
  const quoteEligible = canSubscribeEventQuotes(event);
  const { chartPoints } = useLiveEventStream(eventId, quoteEligible, applyPushedFrame, applyReconcileControl);
  const [sourceObservationVersion, setSourceObservationVersion] = useState(0);
  const admittedChartRef = useRef<chart.AdmittedChartFrames | null>(null);
  const renderedHistory = useMemo(HISTORY_MEMO.runInNewContext({ ...chart, ...pin, eventId, event, servedHistory, quoteEligible, chartPoints, admittedChartRef }), HISTORY_DEPS.runInNewContext({servedHistory, event, quoteEligible, chartPoints, eventId, sourceObservationVersion}));
  harness.renderedHistory = renderedHistory;
  const recoveryRef = useRef(null);
  useEffect(RECOVERY_EFFECT.runInNewContext({
    quoteEligible, createReconnectCatchup, canSubscribeEventQuotes, reconcileIntentRef, heldEventRef, recoveryRef,
    reconcileCatchupRef, reconcileLedger, recoveryIntentRef, quoteReadLifetimeRef, foldedRefetch, quoteTriggerRef, sourceAddedHistoryRef,
  }), [eventId, quoteEligible, foldedRefetch, reconcileLedger]);

  const quoteHistoryRangeRef = useRef(fullHistoryRequested);
  quoteHistoryRangeRef.current = fullHistoryRequested;
  const refreshHistoryRef = useRef(refreshHistory);
  refreshHistoryRef.current = refreshHistory;
  pairedQuoteReadRef.current = PAIR.runInNewContext({
    ...chart, admittedChartRef, setSourceObservationVersion,
    eventId, fullHistoryRequested, fetchEvent, fetchEventHistory, EVENT_BOOT_HISTORY_HOURS, historyRangeParam,
    createWriteJournal, rebaseOnCoveringRead, reconcileFloorCoverage, servedHistoryIsNewer, latestBlendEdgeRef, pairJournalRef, reconcileLedger, storedEventRef,
    quotePairCoversTrigger, coversQuoteRevision, sourceAddedHistoryRef, keepNewerHeldHeadline, carryNewerHeldState, canSubscribeEventQuotes, setLastRefresh, Date,
    quoteTriggerRef, recoveryIntentRef, quoteReadLifetimeRef, quoteEventIdRef, quoteHistoryRangeRef,
    refreshHistoryRef, refreshEventRef, heldEventRef,
  });
  const holdsHeadline = event !== undefined;
  useEffect(EDGE_EFFECT.runInNewContext({
    servedBlendEdgeObservation, servedHistory, latestBlendEdgeRef, holdsHeadline, edgeInvalidatesHeldBlend,
    heldEventRef, foldedRefetch, pairJournalRef, adoptNewerBlendEdge, refreshEvent,
  }), [servedHistory, refreshEvent, foldedRefetch, holdsHeadline]);

  if (!event || !servedHistory) return <>loading</>;
  const rail = Object.keys(event.win_probability_sources ?? {}).sort().join("+");
  const rev = Object.values(event.blend_fold_revision ?? {}).join(",");
  const edge = servedHistory.aggregate_line.at(-1)?.home_probability ?? NaN;
  return <>{`${event.status}|${Math.round(event.hero_probability * 100)}|${rail}|r${rev}|c${Math.round(edge * 100)}`}</>;
}

// ── stream ──────────────────────────────────────────────────────────────────
const sources: HookSource[] = [];
const originalEventSource = globalThis.EventSource;
class HookSource implements StreamHandle {
  readyState = 1;
  listeners = new Map<string, (event: unknown) => void>();
  constructor(readonly url: string) { sources.push(this); }
  close() { this.readyState = 2; }
  addEventListener(name: string, listener: (event: unknown) => void) { this.listeners.set(name, listener); }
  emit(name: string, data?: string) { this.listeners.get(name)?.({ data }); }
}

async function settle() {
  await act(async () => { for (let i = 0; i < 12; i += 1) await Promise.resolve(); });
}
const doc = document as unknown as { createElement: (t: string) => Element; body: { appendChild: (c: unknown) => void } };

async function mount(boot: Detail = live(10, 0.55, withPm(10)), bootHistory: History = history(10, 0.55)) {
  const net: Net = { details: [], histories: [] };
  const container = doc.createElement("div");
  doc.body.appendChild(container);
  const root: Root = createRoot(container);
  let eventId = boot.id;
  const render = () => root.render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0, revalidateOnFocus: false }}>
      <HeldPage net={net} eventId={eventId} />
    </SWRConfig>,
  );
  const bootRead = async (target: number, d: Detail, h: History) => {
    await settle();
    net.details.filter((r) => r.eventId === target && !r.fresh).forEach((r) => r.d.resolve(d));
    net.histories.filter((r) => r.eventId === target && !r.fresh).forEach((r) => r.d.resolve(h));
    await settle();
  };
  await act(async () => { render(); });
  await bootRead(eventId, boot, bootHistory);
  const pairs = (target = E) => net.details.filter((r) => r.fresh && r.eventId === target);
  const pending = () => {
    const d = net.details.filter((r) => r.fresh).at(-1)!;
    const h = net.histories.filter((r) => r.fresh).at(-1)!;
    return { detail: d.d, history: h.d, at: d.at };
  };
  const emit = async (name: string, data?: string) => {
    await act(async () => { sources.at(-1)?.emit(name, data); });
    await settle();
  };
  return {
    net, pairs, pending, emit,
    read: () => container.textContent ?? "",
    push: (rev: number, p: number, source = "kalshi") => emit("probability", frame(rev, p, source)),
    control: (custody: string, floor: number, id = E) => emit("reconcile", control(custody, floor, id)),
    async answer(d: Detail | Error, h: History | Error) {
      const pair = pending();
      if (d instanceof Error) pair.detail.reject(d); else pair.detail.resolve(d);
      if (h instanceof Error) pair.history.reject(h); else pair.history.resolve(h);
      await settle();
    },
    async setFullHistory(full: boolean) { harness.fullHistory = full; await act(async () => { render(); }); await settle(); },
    async navigate(target: number, d: Detail, h: History) {
      eventId = target; await act(async () => { render(); }); await bootRead(target, d, h);
    },
    async advance(ms: number) { await act(async () => { await jest.advanceTimersByTimeAsync(ms); }); await settle(); },
    unmount: () => act(() => { root.unmount(); }),
  };
}

beforeEach(() => {
  sources.length = 0;
  harness.fullHistory = undefined;
  globalThis.EventSource = HookSource as unknown as typeof EventSource;
  jest.spyOn(Math, "random").mockReturnValue(150 / 4900); // catch-up jitter = 250 ms
  jest.useFakeTimers();
  jest.setSystemTime(new Date(Date.UTC(2026, 9, 19, 8, 0, 0)));
});
afterEach(() => {
  globalThis.EventSource = originalEventSource;
  jest.restoreAllMocks();
  jest.useRealTimers();
});

describe("#10090 G1 mounted: an owed reconcile floor on a busy live page", () => {
  it("boots holding the source that will be withdrawn", async () => {
    const p = await mount();
    expect(p.read()).toBe("live|55|kalshi+polymarket|r10|c55");
    expect(sources).toHaveLength(1);
    await p.unmount();
  });

  it("every read overtaken by newer prices: the FIRST covering read still pays, headline never goes back", async () => {
    const p = await mount();
    await p.control("owed-1", 11);
    expect(p.pairs()).toHaveLength(0); // jitter
    await p.advance(250);
    expect(p.pairs()).toHaveLength(1);
    // Two prices land while the read is out; the read itself was built at rev 12.
    await p.push(12, 0.6);
    await p.push(13, 0.62);
    expect(p.read()).toBe("live|62|kalshi+polymarket|r13|c55");
    await p.answer(live(12, 0.6, { kalshi: src(0.6, 12) }), history(12, 0.6));
    expect(p.read()).toBe("live|62|kalshi|r13|c60");
    expect(harness.ledger!.owed()).toBe(false);
    // Prices keep moving: no read per tick, nothing owed.
    for (let rev = 14; rev < 34; rev += 1) { await p.push(rev, 0.6 + (rev % 3) / 100); await p.advance(1000); }
    expect(p.pairs()).toHaveLength(1);
    expect(p.read()).toMatch(/^live\|6\d\|kalshi\|r33\|/);
    await p.unmount();
  });

  it("six reads in a row, each overtaken in flight by two prices: paid by the first, at most one read", async () => {
    const p = await mount();
    await p.control("owed-1", 11);
    await p.advance(250);
    let rev = 12;
    for (let cycle = 0; cycle < 6 && p.pairs().length > cycle; cycle += 1) {
      const built = rev;
      await p.push(++rev, 0.6 + cycle / 100);
      await p.push(++rev, 0.61 + cycle / 100);
      await p.answer(live(built, 0.6, { kalshi: src(0.6, built) }), history(built, 0.6));
      await p.advance(LIVE_REFRESH_INTERVAL);
    }
    expect(p.read()).toBe(`live|61|kalshi|r${rev}|c60`);
    expect(p.pairs()).toHaveLength(1);
    expect(harness.ledger!.owed()).toBe(false);
    await p.unmount();
  });

  it("a folded (twin) headline: a full fold that lands in flight is replayed onto the covering read", async () => {
    const TWIN = 15332402;
    const folded = (e: number, t: number, p: number, rail: Rail): Detail =>
      ({ ...live(e, p, rail), blend_fold_revision: { [E]: e, [TWIN]: t } });
    const foldedHistory = (e: number, t: number, p: number): History =>
      ({ ...history(e, p), blend_edge_fold_revision: { [E]: e, [TWIN]: t } });
    const p = await mount(folded(10, 5, 0.55, withPm(10)), foldedHistory(10, 5, 0.55));
    await p.emit("reconcile", JSON.stringify({ event_id: E, custody_id: "twin-pm", removal_rev: { [TWIN]: 6 } }));
    await p.advance(250);
    expect(p.pairs()).toHaveLength(1);
    const quote = {
      event_id: E, hero_probability: 0.64, hero_probability_away: 0.36, hero_probability_source: "blend",
      hero_probability_observed_at: T(11), blend_fold_revision: { [E]: 11, [TWIN]: 6 },
      win_probability_sources: { kalshi: src(0.64, 11) }, hero_sportsbook_count: 0,
      status: "live", sport: "nfl", hero_settled_result: null,
    };
    await p.emit("folded_probability", JSON.stringify({
      event_id: E, p: 0.64, source: "kalshi", source_value: 0.64, updated_at: T(11), status: "live",
      rev: { [E]: 11 }, folded_quote_pending: false, folded_quote: quote,
    }));
    expect(p.read()).toBe("live|64|kalshi|r11,6|c55");
    await p.answer(folded(10, 6, 0.6, { kalshi: src(0.6, 10) }), foldedHistory(10, 6, 0.6));
    expect(p.read()).toBe("live|64|kalshi|r11,6|c60");
    expect(harness.ledger!.owed()).toBe(false);
    await p.advance(60_000);
    expect(p.pairs()).toHaveLength(1);
    await p.unmount();
  });

  it("a control that arrives AFTER a newer sibling price is still owed and paid", async () => {
    const p = await mount();
    await p.push(12, 0.6);
    expect(p.read()).toBe("live|60|kalshi+polymarket|r12|c55");
    await p.control("owed-1", 11);
    await p.advance(250);
    await p.answer(live(12, 0.6, { kalshi: src(0.6, 12) }), history(12, 0.6));
    expect(p.read()).toBe("live|60|kalshi|r12|c60");
    await p.unmount();
  });

  it("failed, stale and half reads keep it owed; it resumes by itself 1, 2, 4, 8 s apart, one read at a time", async () => {
    const p = await mount();
    await p.control("owed-1", 11);
    await p.advance(250);
    const starts = [p.pending().at];
    await p.answer(new Error("offline"), new Error("offline"));
    for (const [wait, d, h] of [
      [1000, live(10, 0.55, withPm(10)), history(10, 0.55)],                 // a cached read below the floor
      [2000, live(12, 0.6, { kalshi: src(0.6, 12) }), new Error("history")], // half a pair
      [4000, live(12, 0.6, { kalshi: src(0.6, 12) }), history(10, 0.55)],    // history below the floor
    ] as const) {
      await p.advance(wait - 1);
      expect(p.pairs()).toHaveLength(starts.length);
      await p.advance(1);
      expect(p.pairs()).toHaveLength(starts.length + 1);
      starts.push(p.pending().at);
      await p.answer(d as Detail, h as History | Error);
      expect(p.read()).toBe("live|55|kalshi+polymarket|r10|c55");
      expect(harness.ledger!.owed()).toBe(true);
    }
    await p.advance(8000);
    expect(p.pairs()).toHaveLength(5);
    await p.answer(live(12, 0.6, { kalshi: src(0.6, 12) }), history(12, 0.6));
    expect(p.read()).toBe("live|60|kalshi|r12|c60");
    expect(starts.slice(1).map((at, i) => at - starts[i])).toEqual([1000, 2000, 4000]);
    expect(harness.ledger!.earliestOwedAt()).toBeNull();
    await p.advance(120_000);
    expect(p.pairs()).toHaveLength(5);
    await p.unmount();
  });

  it("D4: a covering detail with an UNPINNED history fixes the rail but never pays; failed and stale reads keep it; a pinned covering history pays by itself", async () => {
    const p = await mount();
    await p.control("owed-1", 11);
    await p.advance(250);
    expect(p.pairs()).toHaveLength(1);
    await p.push(12, 0.6);
    await p.push(13, 0.62);
    // The detail is post-removal; the chart half makes no revision claim.
    await p.answer(live(12, 0.6, { kalshi: src(0.6, 12) }), unpinned(12, 0.6));
    expect(p.read()).toBe("live|62|kalshi|r13|c60");
    expect(harness.ledger!.owed()).toBe(true);
    // No price, control or tap from here on: the page asks again by itself.
    await p.advance(999);
    expect(p.pairs()).toHaveLength(1);
    await p.advance(1);
    expect(p.pairs()).toHaveLength(2);
    await p.answer(new Error("offline"), new Error("offline"));
    expect(harness.ledger!.owed()).toBe(true);
    await p.advance(2000);
    expect(p.pairs()).toHaveLength(3);
    // A stale pair: a cached detail below the floor and the old pinned chart.
    await p.answer(live(10, 0.55, withPm(10)), history(10, 0.55));
    expect(p.read()).toBe("live|62|kalshi|r13|c60");
    expect(harness.ledger!.owed()).toBe(true);
    await p.advance(4000);
    expect(p.pairs()).toHaveLength(4);
    // Unpinned again: still unproven, however many times it is read.
    await p.answer(live(13, 0.62, { kalshi: src(0.62, 13) }), unpinned(13, 0.62));
    expect(harness.ledger!.owed()).toBe(true);
    await p.advance(8000);
    expect(p.pairs()).toHaveLength(5);
    await p.answer(live(13, 0.62, { kalshi: src(0.62, 13) }), history(13, 0.62));
    expect(p.read()).toBe("live|62|kalshi|r13|c62");
    expect(harness.ledger!.owed()).toBe(false);
    expect(harness.ledger!.earliestOwedAt()).toBeNull();
    await p.advance(120_000);
    expect(p.pairs()).toHaveLength(5);
    await p.unmount();
  });

  it("D4: a pinned history edge with no revision to order never pays either", async () => {
    const p = await mount();
    await p.control("owed-1", 11);
    await p.advance(250);
    await p.answer(live(12, 0.6, { kalshi: src(0.6, 12) }), { ...history(12, 0.6), blend_edge_fold_revision: null });
    expect(harness.ledger!.owed()).toBe(true);
    await p.advance(1000);
    expect(p.pairs()).toHaveLength(2);
    await p.answer(live(12, 0.6, { kalshi: src(0.6, 12) }), history(12, 0.6));
    expect(p.read()).toBe("live|60|kalshi|r12|c60");
    expect(harness.ledger!.owed()).toBe(false);
    await p.unmount();
  });

  it("the retry interval never exceeds the live poll, however long it stays unpaid", async () => {
    const p = await mount();
    await p.control("owed-1", 11);
    await p.advance(250);
    const waits: number[] = [];
    for (let i = 0; i < 9; i += 1) {
      const count = p.pairs().length;
      await p.answer(new Error("offline"), new Error("offline"));
      const answeredAt = Date.now();
      while (p.pairs().length === count) await p.advance(500);
      waits.push(p.pending().at - answeredAt);
    }
    expect(waits).toEqual([1000, 2000, 4000, 8000, 16000, 32000, 32000, 32000, 32000]);
    expect(Math.max(...waits)).toBe(LIVE_REFRESH_INTERVAL);
    expect(harness.ledger!.owed()).toBe(true);
    await p.unmount();
  });

  it("a read that missed what the page already held is refused, not rolled back to; the next one pays", async () => {
    const p = await mount();
    await p.push(13, 0.63);
    await p.push(14, 0.64);
    await p.control("owed-1", 11);
    await p.advance(250);
    await p.answer(live(12, 0.6, { kalshi: src(0.6, 12) }), history(12, 0.6));
    expect(p.read()).toBe("live|64|kalshi+polymarket|r14|c55");
    await p.advance(1000);
    await p.answer(live(15, 0.65, { kalshi: src(0.65, 15) }), history(15, 0.65));
    expect(p.read()).toBe("live|65|kalshi|r15|c65");
    await p.unmount();
  });

  it("a poll that lands newer than the read while it is out is replayed onto it, not lost", async () => {
    const p = await mount();
    await p.control("owed-1", 11);
    await p.advance(250);
    harness.revalidate!();
    await settle();
    p.net.details.filter((r) => !r.fresh).at(-1)!.d.resolve(live(13, 0.63, { kalshi: src(0.63, 13) }));
    await settle();
    expect(p.read()).toBe("live|63|kalshi|r13|c55");
    await p.answer(live(12, 0.6, { kalshi: src(0.6, 12) }), history(12, 0.6));
    expect(p.read()).toBe("live|63|kalshi|r13|c60");
    expect(harness.ledger!.owed()).toBe(false);
    await p.advance(60_000);
    expect(p.pairs()).toHaveLength(1);
    await p.unmount();
  });

  it("a newer chart edge adopted while the read is out is replayed onto it, not lost", async () => {
    const p = await mount();
    await p.control("owed-1", 11);
    await p.advance(250);
    harness.revalidateHistory!();
    await settle();
    p.net.histories.filter((r) => !r.fresh).at(-1)!.d.resolve(history(13, 0.63));
    await settle();
    expect(p.read()).toBe("live|63|kalshi+polymarket|r13|c63");
    await p.answer(live(12, 0.6, { kalshi: src(0.6, 12) }), history(12, 0.6));
    // The newer served chart stays: the read's own history would take rev 13's observations off it.
    expect(p.read()).toBe("live|63|kalshi|r13|c63");
    expect(harness.ledger!.owed()).toBe(false);
    await p.advance(60_000);
    expect(p.pairs()).toHaveLength(1);
    await p.unmount();
  });

  it("a control in the same tick as a stored-but-unrendered result reads nothing", async () => {
    const p = await mount();
    harness.revalidate!();
    await settle();
    await act(async () => {
      p.net.details.filter((r) => !r.fresh).at(-1)!.d.resolve(final(20));
      for (let i = 0; i < 6; i += 1) await Promise.resolve();
      sources.at(-1)?.emit("reconcile", control("owed-1", 11));
    });
    await settle();
    await p.advance(60_000);
    expect(p.pairs()).toHaveLength(0);
    expect(harness.ledger!.owed()).toBe(false);
    expect(p.read()).toBe("completed|100|kalshi|r20|c55");
    await p.unmount();
  });

  it("the two halves need only cover the floor: a history a write behind the detail is adopted", async () => {
    const p = await mount();
    await p.control("owed-1", 11);
    await p.advance(250);
    await p.answer(live(13, 0.62, { kalshi: src(0.62, 13) }), history(12, 0.6));
    expect(p.read()).toBe("live|62|kalshi|r13|c60");
    expect(harness.ledger!.owed()).toBe(false);
    await p.unmount();
  });

  it("a burst of controls is one read; a control replayed after payment (reconnect) reads nothing", async () => {
    const p = await mount();
    for (let i = 0; i < 20; i += 1) await p.control(i % 2 ? "owed-a" : "owed-b", 11);
    await p.advance(250);
    expect(p.pairs()).toHaveLength(1);
    await p.answer(live(12, 0.6, { kalshi: src(0.6, 12) }), history(12, 0.6));
    expect(harness.ledger!.owed()).toBe(false);
    // The server rolls the stream over and re-sends the retained control on the new socket.
    await p.emit("reconnect", JSON.stringify({ reason: "max_age" }));
    await p.advance(1000);
    expect(sources).toHaveLength(2);
    await p.emit("open");
    await p.control("owed-a", 11);
    await p.advance(10_000);
    expect(p.pairs()).toHaveLength(1);
    await p.unmount();
  });

  it("owed across a rollover: the new socket's own control coalesces onto the same debt", async () => {
    const p = await mount();
    await p.control("owed-1", 11);
    await p.emit("reconnect", JSON.stringify({ reason: "max_age" }));
    await p.advance(1000);
    expect(sources).toHaveLength(2);
    await p.emit("open");
    await p.control("owed-1", 11);
    expect(p.pairs()).toHaveLength(1); // the original jitter fired during the rollover wait
    await p.answer(live(12, 0.6, { kalshi: src(0.6, 12) }), history(12, 0.6));
    expect(p.read()).toBe("live|60|kalshi|r12|c60");
    await p.advance(10_000);
    expect(p.pairs()).toHaveLength(1);
    await p.unmount();
  });

  it("a control for another event is not this page's debt", async () => {
    const p = await mount();
    await p.control("owed-1", 11, B);
    await p.advance(10_000);
    expect(p.pairs()).toHaveLength(0);
    await p.unmount();
  });

  it("a final page owes nothing: a late control reads nothing and reopens nothing", async () => {
    const p = await mount(final(20), history(20, 1));
    expect(sources).toHaveLength(0);
    await p.unmount();
    // The stream's last control raced the result: the page has stored final, React has not rendered it.
    const q = await mount();
    harness.revalidate!();
    await settle();
    q.net.details.filter((r) => !r.fresh).at(-1)!.d.resolve(final(20));
    await q.control("owed-1", 11);
    await q.advance(10_000);
    expect(q.pairs()).toHaveLength(0);
    expect(q.read()).toBe("completed|100|kalshi|r20|c55");
    await q.unmount();
  });

  it("a result stored while the owed read is out wins, and retires the debt", async () => {
    const p = await mount();
    await p.control("owed-1", 11);
    await p.advance(250);
    harness.revalidate!();
    await settle();
    p.net.details.filter((r) => !r.fresh).at(-1)!.d.resolve(final(20));
    await settle();
    await p.answer(live(12, 0.6, { kalshi: src(0.6, 12) }), history(12, 0.6));
    expect(p.read()).toBe("completed|100|kalshi|r20|c55");
    expect(harness.ledger!.owed()).toBe(false);
    await p.advance(120_000);
    expect(p.pairs()).toHaveLength(1);
    await p.unmount();
  });

  it("navigation retires the debt: no read for either event", async () => {
    const p = await mount();
    await p.control("owed-1", 11);
    await p.navigate(B, live(5, 0.4, { kalshi: src(0.4, 5) }, B), history(5, 0.4, B));
    await p.advance(60_000);
    expect(p.pairs(E)).toHaveLength(0);
    expect(p.pairs(B)).toHaveLength(0);
    expect(harness.ledger!.owed()).toBe(false);
    await p.unmount();
  });
});

// ── Authority G1 REVISE (0930Z) F1/F2 and Latency COST-REVISE (0931Z) R1/R2 ──
describe("#10090 G1 repairs mounted: a journaled poll never steps the page back, and an owed floor is paced", () => {
  const TWIN = 15332402;
  const scheduled = (rev: number, rail: Rail): Detail =>
    ({ ...live(rev, 0.55, rail), status: "scheduled", home_score: null, away_score: null });

  it("F1: a cached poll that lands mid-pair cannot put a live 7-0 game back to scheduled", async () => {
    const p = await mount(scheduled(10, withPm(10)));
    expect(p.read()).toBe("scheduled|55|kalshi+polymarket|r10|c55");
    await p.control("owed-1", 11);
    await p.advance(250);
    expect(p.pairs()).toHaveLength(1);
    // The 32 s poll answers from a cache built before kickoff and the removal.
    harness.revalidate!();
    await settle();
    p.net.details.filter((r) => !r.fresh).at(-1)!.d.resolve(scheduled(10, withPm(10)));
    await settle();
    await p.answer({ ...live(11, 0.55, { kalshi: src(0.55, 11) }), home_score: 7, away_score: 0 }, history(11, 0.55));
    expect(p.read()).toBe("live|55|kalshi|r11|c55");
    expect([harness.event!.home_score, harness.event!.away_score]).toEqual([7, 0]);
    expect(harness.ledger!.owed()).toBe(false);
    await p.unmount();
  });

  it("F2: an incomparable pre-removal poll (a twin joined in between) cannot restore the removed source", async () => {
    const p = await mount();
    await p.control("owed-1", 11);
    await p.advance(250);
    harness.revalidate!();
    await settle();
    p.net.details.filter((r) => !r.fresh).at(-1)!.d.resolve(live(10, 0.55, withPm(10)));
    await settle();
    expect(p.read()).toBe("live|55|kalshi+polymarket|r10|c55");
    await p.answer(
      { ...live(11, 0.6, { kalshi: src(0.6, 11) }), blend_fold_revision: { [E]: 11, [TWIN]: 3 } },
      { ...history(11, 0.6), blend_edge_fold_revision: { [E]: 11, [TWIN]: 3 } },
    );
    // Ledger first: with the replay rule mutated off, the written-value check
    // must leave this owed (refused), never paid with the source back.
    expect(harness.ledger!.owed()).toBe(false);
    expect(p.read()).toBe("live|60|kalshi|r11,3|c60");
    await p.unmount();
  });

  it("Latency R1: an unpayable floor on a folded page, invalidated every second for 60 s, makes ladder pairs only", async () => {
    const folded = (e: number, p: number, rail: Rail): Detail => ({ ...live(e, p, rail), blend_fold_revision: { [E]: e, [TWIN]: 5 } });
    const foldedHistory = (e: number, p: number): History => ({ ...history(e, p), blend_edge_fold_revision: { [E]: e, [TWIN]: 5 } });
    const p = await mount(folded(10, 0.55, withPm(10)), foldedHistory(10, 0.55));
    const fresh = () => p.net.details.filter((r) => r.fresh);
    const pairStarts = () => p.net.histories.filter((r) => r.fresh).map((r) => r.at);
    const drain = async () => {
      for (const r of p.net.details) if (r.fresh && !r.done) { r.done = true; r.d.resolve(folded(10, 0.55, withPm(10))); }
      for (const r of p.net.histories) if (r.fresh && !r.done) { r.done = true; r.d.resolve(foldedHistory(10, 0.55)); }
      await settle();
    };
    const t0 = Date.now();
    // A D3 row the detail vector never carries: "a missing row never covers".
    await p.emit("reconcile", JSON.stringify({ event_id: E, custody_id: "never", removal_rev: { 999: 1 } }));
    for (let second = 0; second < 60; second += 1) {
      await p.push(11 + second, 0.55); // a raw-row frame on a folded hero: an invalidation
      await drain();
      await p.advance(1000);
      await drain();
    }
    expect(harness.ledger!.owed()).toBe(true);
    // The control's jitter (250 ms, held to the 1 s window by the t=0
    // invalidation's read), then the ladder's 1, 2, 4, 8, 16 s steps; the next
    // (32 s) falls at 64 s. Not one pair per invalidation.
    expect(pairStarts().map((at) => at - t0)).toEqual([1000, 2000, 4000, 8000, 16_000, 32_000]);
    // Every other read the invalidations asked for is the old detail-only one.
    expect(fresh()).toHaveLength(61);
    await p.unmount();
  });

  it("Latency R2: an owed pair's halves are single requests, and a 429's wait holds the next pair", async () => {
    const p = await mount();
    await p.control("owed-1", 11);
    await p.advance(250);
    expect(p.pairs()).toHaveLength(1);
    const pairOptions = () => [p.net.details.filter((r) => r.fresh).at(-1)!.options, p.net.histories.filter((r) => r.fresh).at(-1)!.options];
    expect(pairOptions()).toEqual([{ maxRetries: 0 }, { maxRetries: 0 }]);
    const throttled = Object.assign(new Error("429"), { retryAfterMs: 20_000 });
    await p.answer(throttled, history(10, 0.55));
    await p.advance(19_999);
    expect(p.pairs()).toHaveLength(1);
    await p.advance(1);
    expect(p.pairs()).toHaveLength(2);
    expect(pairOptions()).toEqual([{ maxRetries: 0 }, { maxRetries: 0 }]);
    await p.answer(live(12, 0.6, { kalshi: src(0.6, 12) }), history(12, 0.6));
    expect(p.read()).toBe("live|60|kalshi|r12|c60");
    expect(harness.ledger!.owed()).toBe(false);
    // A price-trigger pair keeps the existing apiFetch retries (explicit scope).
    await p.emit("probability", JSON.stringify({ event_id: E, p: null, source: "kalshi", updated_at: T(13), status: "live", rev: { [E]: 13 } }));
    await p.advance(1000);
    expect(p.pairs()).toHaveLength(3);
    expect(pairOptions()).toEqual([undefined, undefined]);
    await p.unmount();
  });

  // Authority G1R REVISE (1000Z) R2: only the floors the DETAIL covered are paid.
  it("Authority R2: a frame replayed mid-pair cannot pay a floor the detail never covered; the page asks again", async () => {
    const p = await mount(live(9, 0.55, withPm(9)), history(9, 0.55));
    await p.control("owed-1", 10); // an earlier removal the detail will cover
    await p.control("owed-2", 12); // Polymarket withdrawn at 12
    await p.advance(250);
    expect(p.pairs()).toHaveLength(1);
    // The post-removal price lands while the read is out ...
    await p.push(12, 0.6);
    // ... and the detail was built at 11: it still folds Polymarket. The
    // pinned chart edge is already at 12.
    await p.answer(live(11, 0.58, withPm(11)), history(12, 0.6));
    expect(p.read()).toBe("live|60|kalshi+polymarket|r12|c60");
    // Ledger first: the replayed frame raised the written revision to 12, but
    // the rail it kept is the detail's, so the withdrawal is still owed.
    expect(harness.ledger!.owed()).toBe(true);
    expect(harness.ledger!.floors()).toEqual([{ [E]: 12 }]);
    await p.advance(1000);
    expect(p.pairs()).toHaveLength(2);
    await p.answer(live(12, 0.6, { kalshi: src(0.6, 12) }), history(12, 0.6));
    expect(p.read()).toBe("live|60|kalshi|r12|c60");
    expect(harness.ledger!.owed()).toBe(false);
    await p.unmount();
  });
});

// ── #10090 source_snapshot: a coherent rail on every newer price ────────────
// (reconciliation-contract-20261019/NATIVE-SOURCE-SNAPSHOT-CONSUMER-CONTRACT.md,
// ROOT-COHERENT-RAIL-PAYMENT-DECISION.md.) A snapshot proves only the rail it
// replaces: it pays no floor and no history on web.
describe("#10090 source_snapshot mounted: the rail moves with the price", () => {
  const kalshi = (rev: number, v = 0.6) => ({ kalshi: src(v, rev) });

  it("a newer snapshot takes the whole rail with the price: the withdrawn source leaves before any read", async () => {
    const p = await mount();
    await p.emit("probability", snapFrame(11, 0.58, kalshi(11, 0.58)));
    expect(p.read()).toBe("live|58|kalshi|r11|c55");
    expect(p.net.details.filter((r) => r.fresh)).toHaveLength(0);
    await p.advance(60_000);
    expect(p.pairs()).toHaveLength(0);
    await p.unmount();
  });

  it("removal then genuine re-addition follow quote order; an older poll restores nothing", async () => {
    const p = await mount();
    await p.emit("probability", snapFrame(11, 0.58, kalshi(11, 0.58)));
    await p.emit("probability", snapFrame(12, 0.57, withPm(12)));
    expect(p.read()).toBe("live|57|kalshi+polymarket|r12|c55");
    await p.emit("probability", snapFrame(13, 0.6, kalshi(13)));
    expect(p.read()).toBe("live|60|kalshi|r13|c55");
    harness.revalidate!();
    await settle();
    p.net.details.filter((r) => !r.fresh).at(-1)!.d.resolve(live(12, 0.57, withPm(12)));
    await settle();
    expect(p.read()).toBe("live|60|kalshi|r13|c55");
    await p.unmount();
  });

  it("an equal, older or refused snapshot is exactly today's frame", async () => {
    const p = await mount();
    await p.emit("probability", snapFrame(10, 0.7, kalshi(10, 0.7)));
    expect(p.read()).toBe("live|55|kalshi+polymarket|r10|c55");
    // Identity mismatch: the frame is legacy — p moves, the rail keeps Polymarket.
    await p.emit("probability", snapFrame(11, 0.58, kalshi(11, 0.58), { source_snapshot: {
      event_id: E, rev: { [E]: 12 }, win_probability_sources: kalshi(11, 0.58) } }));
    expect(p.read()).toBe("live|58|kalshi+polymarket|r11|c55");
    await p.unmount();
  });

  it("continuous snapshots overtake every read: the first pinned covering history pays; unpinned or failed history stays owed", async () => {
    const p = await mount();
    await p.control("owed-1", 11);
    await p.advance(250);
    expect(p.pairs()).toHaveLength(1);
    await p.emit("probability", snapFrame(12, 0.6, kalshi(12)));
    await p.emit("probability", snapFrame(13, 0.62, kalshi(13, 0.62)));
    expect(p.read()).toBe("live|62|kalshi|r13|c55");
    // The rail on screen already covers the floor; an unpinned history still proves nothing.
    await p.answer(live(12, 0.6, kalshi(12)), unpinned(12, 0.6));
    expect(p.read()).toBe("live|62|kalshi|r13|c60");
    expect(harness.ledger!.owed()).toBe(true);
    await p.advance(1000);
    expect(p.pairs()).toHaveLength(2);
    await p.emit("probability", snapFrame(14, 0.63, kalshi(14, 0.63)));
    await p.answer(new Error("503"), new Error("503"));
    expect(harness.ledger!.owed()).toBe(true);
    await p.advance(2000);
    expect(p.pairs()).toHaveLength(3);
    await p.emit("probability", snapFrame(15, 0.64, kalshi(15, 0.64)));
    await p.emit("probability", snapFrame(16, 0.65, kalshi(16, 0.65)));
    await p.answer(live(14, 0.63, kalshi(14, 0.63)), history(14, 0.63));
    expect(p.read()).toBe("live|65|kalshi|r16|c63");
    expect(harness.ledger!.owed()).toBe(false);
    for (let rev = 17; rev < 30; rev += 1) { await p.emit("probability", snapFrame(rev, 0.6, kalshi(rev))); await p.advance(1000); }
    expect(p.pairs()).toHaveLength(3);
    await p.unmount();
  });

  it("a snapshot replayed onto a detail below the floor fixes the rail but pays nothing (web keeps G1's detail rule)", async () => {
    const p = await mount(live(9, 0.55, withPm(9)), history(9, 0.55));
    await p.control("owed-1", 10);
    await p.control("owed-2", 12);
    await p.advance(250);
    await p.emit("probability", snapFrame(12, 0.6, kalshi(12)));
    await p.answer(live(11, 0.58, withPm(11)), history(12, 0.6));
    expect(p.read()).toBe("live|60|kalshi|r12|c60");
    expect(harness.ledger!.floors()).toEqual([{ [E]: 12 }]);
    await p.advance(1000);
    expect(p.pairs()).toHaveLength(2);
    await p.answer(live(12, 0.6, kalshi(12)), history(12, 0.6));
    expect(harness.ledger!.owed()).toBe(false);
    await p.unmount();
  });

  it.each([
    ["an empty map", {}],
    ["only the sportsbook count", { betting_book_count: { value: 3, display_name: "Books", type: "count", color: "#000" } }],
  ])("an unpriced snapshot (%s) writes nothing and asks the pair; a priced one past it clears that debt", async (_n, rail) => {
    const p = await mount();
    await p.emit("probability", snapFrame(11, 0.5, rail));
    expect(p.read()).toBe("live|55|kalshi+polymarket|r10|c55");
    await p.advance(1000);
    expect(p.pairs()).toHaveLength(1);
    // A source returns before the read lands: its complete rail covers what the trigger owed.
    await p.emit("probability", snapFrame(12, 0.6, kalshi(12)));
    expect(p.read()).toBe("live|60|kalshi|r12|c55");
    await p.answer(new Error("503"), new Error("503"));
    await p.advance(60_000);
    expect(p.pairs()).toHaveLength(1);
    expect(p.read()).toBe("live|60|kalshi|r12|c55");
    await p.unmount();
  });

  it("without the later priced snapshot the unpriced trigger stays owed and retries", async () => {
    const p = await mount();
    await p.emit("probability", snapFrame(11, 0.5, {}));
    await p.advance(1000);
    expect(p.pairs()).toHaveLength(1);
    await p.answer(new Error("503"), new Error("503"));
    await p.advance(60_000);
    expect(p.pairs().length).toBeGreaterThan(1);
    await p.unmount();
  });

  it("a final frame carrying a snapshot leaves the rail and asks the read; a snapshot after the final does nothing", async () => {
    const p = await mount();
    await p.emit("probability", snapFrame(11, 1, kalshi(11, 1), { status: "completed" }));
    expect(p.read()).toBe("live|55|kalshi+polymarket|r10|c55");
    await p.advance(1000);
    expect(p.pairs()).toHaveLength(1);
    await p.answer(final(11), history(11, 1));
    expect(p.read()).toMatch(/^completed\|100\|kalshi\|/);
    await p.emit("probability", snapFrame(12, 0.6, kalshi(12)));
    expect(p.read()).toMatch(/^completed\|100\|kalshi\|/);
    await p.unmount();
  });

  it("a folded page treats a raw frame carrying a snapshot exactly as the same frame without one", async () => {
    const folded = () => ({ ...live(10, 0.55, withPm(10)), blend_fold_revision: { [E]: 10, [B]: 4 } });
    const run = async (data: string) => {
      const p = await mount(folded());
      await p.emit("probability", data);
      await p.advance(1000);
      const out = { read: p.read(), details: p.net.details.length, pairs: p.pairs().length };
      await p.unmount();
      return out;
    };
    const legacy = await run(frame(11, 0.58));
    const withSnapshot = await run(snapFrame(11, 0.58, kalshi(11, 0.58)));
    expect(withSnapshot).toEqual(legacy);
    expect(withSnapshot.read).toBe("live|55|kalshi+polymarket|r10,4|c55");
  });
});

describe("#10090 history coverage mounted: a complete unpinned chart finishes recovery", () => {
  const post = (rev: number) => live(rev, 0.6, { kalshi: src(0.6, rev) });
  // A valid unpinned chart whose right edge is NOT the hero (0.5 vs 0.6): one
  // remaining source, an old genuine edge. Nothing may be forced onto it.
  const covered = (rev: number, vector: unknown, id = E): History =>
    ({ ...unpinned(rev, 0.5, id), history_fold_revision: vector });

  it("an unpinned history whose complete-build vector covers the floor pays it, with no further quote, and the chart keeps its own edge", async () => {
    const p = await mount();
    await p.control("owed-1", 11);
    await p.advance(250);
    await p.push(13, 0.62);
    await p.answer(post(12), covered(12, { [E]: 12 }));
    expect(p.read()).toBe("live|62|kalshi|r13|c50");
    expect(harness.ledger!.owed()).toBe(false);
    expect(harness.ledger!.earliestOwedAt()).toBeNull();
    await p.advance(120_000);
    expect(p.pairs()).toHaveLength(1);
    // A replayed control for the paid custody reads nothing.
    await p.control("owed-1", 11);
    await p.advance(5_000);
    expect(p.pairs()).toHaveLength(1);
    await p.unmount();
  });

  it("the vector never pays for a detail below the floor: the rail half must qualify too", async () => {
    const p = await mount();
    await p.control("owed-1", 11);
    await p.advance(250);
    // Not a reconcile pair: it is adopted as an ordinary same-revision read
    // (its chart is written, as before), and pays nothing.
    await p.answer(live(10, 0.55, withPm(10)), covered(12, { [E]: 12 }));
    expect(p.read()).toBe("live|55|kalshi+polymarket|r10|c50");
    expect(harness.ledger!.owed()).toBe(true);
    await p.advance(1000);
    expect(p.pairs()).toHaveLength(2);
    await p.answer(post(12), covered(12, { [E]: 12 }));
    expect(p.read()).toBe("live|60|kalshi|r12|c50");
    expect(harness.ledger!.owed()).toBe(false);
    await p.unmount();
  });

  it("null, absent, malformed, partial, old, other-event and failed coverage stay owed; the next correct read completes it without a quote", async () => {
    const p = await mount();
    await p.control("owed-1", 11);
    await p.advance(250);
    const refused: Array<History | Error> = [
      covered(12, null),
      unpinned(12, 0.5),
      covered(12, { [E]: "12" }),
      covered(12, [12]),
      covered(12, { [E]: 12.5 }),
      covered(12, { [E]: 2 ** 53 }),
      covered(12, {}),
      covered(12, { [B]: 12 }),            // the floor's row is missing
      covered(12, { [E]: 10 }),            // below the floor
      covered(12, { [E]: 12 }, B),         // another event's history
      { ...covered(12, { [E]: 12 }), blend_edge_pinned: true, blend_edge_fold_revision: { [E]: 10 } },
      new Error("history"),
    ];
    let waited = 0;
    for (const h of refused) {
      const count = p.pairs().length;
      await p.answer(post(12), h);
      expect(harness.ledger!.owed()).toBe(true);
      while (p.pairs().length === count) { await p.advance(500); waited += 500; }
    }
    expect(waited).toBeGreaterThan(0);
    const count = p.pairs().length;
    await p.answer(post(12), covered(12, { [E]: 13, [B]: 4 }));
    expect(harness.ledger!.owed()).toBe(false);
    await p.advance(120_000);
    expect(p.pairs()).toHaveLength(count);
    await p.unmount();
  });

  it("a covering vector for a range the page no longer draws pays nothing; the next read on the new range does", async () => {
    const p = await mount();
    await p.control("owed-1", 11);
    await p.advance(250);
    await p.setFullHistory(true);
    await p.answer(post(12), covered(12, { [E]: 12 }));
    expect(p.read()).toBe("live|55|kalshi+polymarket|r10|c55");
    expect(harness.ledger!.owed()).toBe(true);
    await p.advance(1000);
    expect(p.pairs()).toHaveLength(2);
    await p.answer(post(12), covered(12, { [E]: 12 }));
    expect(harness.ledger!.owed()).toBe(false);
    await p.unmount();
  });

  it("a covering vector from a pair of an earlier page lifetime pays nothing, even back on the same event", async () => {
    const p = await mount();
    await p.control("owed-1", 11);
    await p.advance(250);
    const old = { d: p.pending().detail, h: p.pending().history };
    await p.navigate(B, live(20, 0.4, withPm(20), B), history(20, 0.4, B));
    await p.navigate(E, live(10, 0.55, withPm(10)), history(10, 0.55));
    // The server re-sends the unretired control on the new stream.
    await p.control("owed-1", 11);
    old.d.resolve(post(12));
    old.h.resolve(covered(12, { [E]: 12 }));
    await settle();
    expect(p.read()).toBe("live|55|kalshi+polymarket|r10|c55");
    expect(harness.ledger!.owed()).toBe(true);
    // The new lifetime asks by itself, and its own covering read pays.
    for (let i = 0; i < 8 && p.pairs().length === 1; i += 1) await p.advance(500);
    expect(p.pairs()).toHaveLength(2);
    await p.answer(post(12), covered(12, { [E]: 12 }));
    expect(harness.ledger!.owed()).toBe(false);
    await p.unmount();
  });

  it("a result stored while a covering unpinned read is out still wins", async () => {
    const p = await mount();
    await p.control("owed-1", 11);
    await p.advance(250);
    harness.revalidate!();
    await settle();
    p.net.details.filter((r) => !r.fresh).at(-1)!.d.resolve(final(20));
    await settle();
    await p.answer(post(12), covered(12, { [E]: 12 }));
    expect(p.read()).toBe("completed|100|kalshi|r20|c55");
    expect(harness.ledger!.owed()).toBe(false);
    await p.advance(120_000);
    expect(p.pairs()).toHaveLength(1);
    await p.unmount();
  });
});

// ── #10090 state window (LIVE-STATE-WINDOW-CONSUMER-CONTRACT.md v3) ─────────
describe("#10090 state window mounted: a same-revision read never puts the game back", () => {
  const at = (second: number) => `2026-10-19T01:00:${String(second).padStart(2, "0")}.000000+00:00`;
  const stamped = (d: Detail, from: number, to: number) =>
    ({ ...d, state_read_not_before: at(from), state_read_not_after: at(to) }) as Detail;
  const kickoff = (rev: number, rail: Rail): Detail =>
    ({ ...live(rev, 0.55, rail), status: "scheduled", home_score: null, away_score: null });
  type Page = Awaited<ReturnType<typeof mount>>;
  const poll = async (p: Page, d: Detail) => {
    harness.revalidate!();
    await settle();
    p.net.details.filter((r) => !r.fresh).at(-1)!.d.resolve(d);
    await settle();
  };
  const score = () => [harness.event!.home_score, harness.event!.away_score];

  it("X1 poll: a scheduled detail read before kickoff lands after the live 0-0 page — the page stays live", async () => {
    const p = await mount(stamped({ ...live(10, 0.55, withPm(10)), home_score: 0, away_score: 0 }, 20, 21));
    await poll(p, stamped(kickoff(10, withPm(10)), 10, 11));
    expect(p.read()).toBe("live|55|kalshi+polymarket|r10|c55");
    expect(score()).toEqual([0, 0]);
    expect(sources).toHaveLength(1);
    await p.unmount();
  });

  it("X2 poll: a 0-0 read before the touchdown lands after the 7-0 page — the page stays 7-0", async () => {
    const p = await mount(stamped({ ...live(10, 0.55, withPm(10)), home_score: 7, away_score: 0 }, 20, 21));
    await poll(p, stamped({ ...live(10, 0.55, withPm(10)), home_score: 0, away_score: 0 }, 10, 11));
    expect(score()).toEqual([7, 0]);
    await p.unmount();
  });

  it("a real correction (later window, lower score) and an overlapping window are adopted as today", async () => {
    const p = await mount(stamped({ ...live(10, 0.55, withPm(10)), home_score: 7, away_score: 0 }, 20, 21));
    await poll(p, stamped({ ...live(10, 0.55, withPm(10)), home_score: 0, away_score: 0 }, 30, 31));
    expect(score()).toEqual([0, 0]);
    await poll(p, stamped({ ...live(10, 0.55, withPm(10)), home_score: 3, away_score: 0 }, 25, 40));
    expect(score()).toEqual([3, 0]);
    await p.unmount();
  });

  it("C3 poll: a final read later is never reopened by a cached live poll — kept whole", async () => {
    const held = stamped(final(20), 20, 21);
    const p = await mount(held, history(20, 1));
    await poll(p, stamped(live(30, 0.55, withPm(30)), 10, 11));
    expect(p.read()).toBe("completed|100|kalshi|r20|c100");
    expect(harness.event).toEqual(held);
    expect(sources).toHaveLength(0);
    await p.unmount();
  });

  it("pair site: a covering read built before kickoff, landing after the stored live poll, pays without stepping back", async () => {
    const p = await mount(stamped(kickoff(10, withPm(10)), 10, 11));
    await p.control("owed-1", 11);
    await p.advance(250);
    expect(p.pairs()).toHaveLength(1);
    harness.revalidate!();
    await settle();
    // In ONE tick: the poll stores live 0-0 (read at 30 s), and the pair's
    // detail (read at 20 s, before kickoff) lands before React renders it.
    await act(async () => {
      p.net.details.filter((r) => !r.fresh).at(-1)!.d.resolve(
        stamped({ ...live(10, 0.55, withPm(10)), home_score: 0, away_score: 0 }, 30, 31));
      for (let i = 0; i < 12; i += 1) await Promise.resolve();
      const pair = p.pending();
      pair.detail.resolve(stamped(kickoff(11, { kalshi: src(0.55, 11) }), 20, 21));
      pair.history.resolve(history(11, 0.55));
      for (let i = 0; i < 12; i += 1) await Promise.resolve();
    });
    await settle();
    expect(p.read()).toBe("live|55|kalshi|r11|c55");
    expect(score()).toEqual([0, 0]);
    expect(harness.event!).toMatchObject({ state_read_not_before: at(30) });
    expect(harness.ledger!.owed()).toBe(false);
    await p.unmount();
  });
});


// Attempt155 uses the page's actual historyData memo, not aggregate_line alone.
const blend155 = (pm: number) => (0.617 * 1.5 + pm * 0.8) / 2.3;
const detail155 = (rev: number, pm: number) => live(rev, blend155(pm), {espn: src(0.617, 10), polymarket: src(pm, rev)});
const history155 = (rev: number): History => ({ ...unpinned(10, blend155(0.66)), history_fold_revision: { [E]: rev },
  win_prob_history: { polymarket: [{ timestamp: T(10), home_probability: 0.66, away_probability: 0.34 }] },
} as History);
const has155 = (rev: number, pm: number) => harness.renderedHistory?.win_prob_history?.polymarket?.some((p: any) => p.timestamp === T(rev) && p.home_probability === pm);
function receipt155(name: string, p: Awaited<ReturnType<typeof mount>>) {
  if (!process.env.ATTEMPT155_RECEIPTS) return;
  fs.mkdirSync(process.env.ATTEMPT155_RECEIPTS, {recursive: true});
  fs.writeFileSync(path.join(process.env.ATTEMPT155_RECEIPTS, name + ".json"), JSON.stringify({ at: Date.now(), event: harness.event, renderedHistory: harness.renderedHistory, owed: harness.ledger?.owed(), pairs: p.pairs().length }, null, 2));
}
describe("Attempt155 recovered source read through the mounted page memo", () => {
  it("stale first pair retains debt, covering pair banks final source during silence", async () => {
    const p = await mount(detail155(10, 0.66), history155(10));
    try {
      await p.control(`normal-price:${E}:11`, 11);
      await p.advance(250);
      await p.answer(detail155(10, 0.66), history155(10));
      expect(harness.ledger!.owed()).toBe(true);
      await p.advance(1000);
      expect(p.pairs()).toHaveLength(2);
      await p.answer(detail155(11, 0.78), history155(11));
      receipt155("stale-first-adopted", p);
      await p.advance(35000);
      receipt155("stale-first-silence", p);
      expect(harness.event?.blend_fold_revision).toEqual({[E]:11});
      expect(harness.event?.hero_probability).toBeCloseTo(blend155(0.78), 6);
      expect(has155(11, 0.78)).toBe(true);
      expect(harness.ledger!.owed()).toBe(false);
      expect(p.pairs()).toHaveLength(2);
    } finally { await p.unmount(); }
  });
  it("newer push preserves latest headline AND the received earlier source excursion", async () => {
    const p = await mount(detail155(10, 0.66), history155(10));
    try {
      await p.control(`normal-price:${E}:11`, 11);
      await p.advance(250);
      await p.advance(50);
      await p.emit("probability", JSON.stringify({...JSON.parse(frame(12, blend155(0.66), "polymarket")), source_value: 0.66}));
      await p.advance(100);
      await p.answer(detail155(11, 0.78), history155(11));
      receipt155("overtaken-adopted", p);
      await p.advance(35000);
      receipt155("overtaken-silence", p);
      expect(harness.event?.blend_fold_revision).toEqual({[E]:12});
      expect(harness.event?.hero_probability).toBeCloseTo(blend155(0.66), 6);
      expect(has155(12, 0.66)).toBe(true);
      expect(harness.ledger!.owed()).toBe(false);
      expect(p.pairs()).toHaveLength(1);
      expect(has155(11, 0.78)).toBe(true);
    } finally { await p.unmount(); }
  });
});

// Independent review155: newer served history must remain the bank's source authority,
// and a recovered reading must reach the memo when SWR keeps both identities.
describe("Attempt155 independent review controls", () => {
  it("review155 older pair must not erase a newer served-source excursion",async()=>{
    const base={...history(10,.66),history_fold_revision:{[E]:10},win_prob_history:{polymarket:[{timestamp:T(0),home_probability:.5}]}};
    const p=await mount(live(10,.66,{polymarket:src(.66,10)}),base);
    try {
      await p.control(`normal-price:${E}:11`,11); await p.advance(250);
      const newer={...history(12,.55),history_fold_revision:{[E]:12},win_prob_history:{polymarket:[{timestamp:T(0),home_probability:.5}],kalshi:[{timestamp:T(0),home_probability:.5}]}};
      for(const [rev,value] of [[12,.55],[13,.6]]){
        harness.revalidate!(); await settle();
        p.net.details.filter(r=>!r.fresh).at(-1)!.d.resolve(live(rev,value,{polymarket:src(.66,10),kalshi:src(value,rev)})); await settle();
        if(rev===12){
          harness.revalidateHistory!(); await settle();
          p.net.histories.filter(r=>!r.fresh).at(-1)!.d.resolve(newer); await settle();
        }
      }
      const has=()=>harness.renderedHistory?.win_prob_history?.kalshi?.some((q:any)=>q.timestamp===T(12)&&q.home_probability===.55);
      expect(has()).toBe(true);
      await p.answer(live(11,.78,{polymarket:src(.78,11)}),{...history(11,.78),history_fold_revision:{[E]:11},win_prob_history:{polymarket:[{timestamp:T(0),home_probability:.5}]}} as History);
      expect(harness.event?.blend_fold_revision).toEqual({[E]:13});
      expect(harness.renderedHistory?.history_fold_revision).toEqual({[E]:12});
      harness.revalidate!(); await settle();
      p.net.details.filter(r=>!r.fresh).at(-1)!.d.resolve(live(14,.61,{polymarket:src(.66,10),kalshi:src(.61,14)})); await settle();
      expect(has()).toBe(true);
    }finally{await p.unmount();}
  });
  it("review155 recovered reading triggers actual memo when adopted pair is otherwise unchanged",async()=>{
    const base={...history(10,.66),history_fold_revision:{[E]:10},win_prob_history:{polymarket:[{timestamp:T(0),home_probability:.5}]}};
    const p=await mount(live(10,.66,{polymarket:src(.66,10)}),base);
    try {
      await p.control(`normal-price:${E}:11`,11); await p.advance(250);
      const newer={...history(12,.55),history_fold_revision:{[E]:12},win_prob_history:{polymarket:[{timestamp:T(0),home_probability:.5}],kalshi:[{timestamp:T(0),home_probability:.5}]}};
      for(const [rev,value] of [[12,.55],[13,.6]]){
        harness.revalidate!(); await settle();
        p.net.details.filter(r=>!r.fresh).at(-1)!.d.resolve(live(rev,value,{polymarket:src(.66,12),kalshi:src(value,rev)})); await settle();
        if(rev===12){
          harness.revalidateHistory!(); await settle();
          p.net.histories.filter(r=>!r.fresh).at(-1)!.d.resolve(newer); await settle();
        }
      }
      const has=()=>harness.renderedHistory?.win_prob_history?.kalshi?.some((q:any)=>q.timestamp===T(12)&&q.home_probability===.55);
      expect(has()).toBe(true);
      await p.answer(live(11,.78,{polymarket:src(.78,11)}),{...history(11,.78),history_fold_revision:{[E]:11},win_prob_history:{polymarket:[{timestamp:T(0),home_probability:.5}]}} as History);
      expect(harness.event?.blend_fold_revision).toEqual({[E]:13});
      expect(harness.renderedHistory?.history_fold_revision).toEqual({[E]:12});
      await p.advance(35000);
      expect(harness.renderedHistory?.win_prob_history?.polymarket?.some((q:any)=>q.timestamp===T(11)&&q.home_probability===.78)).toBe(true);
      harness.revalidate!(); await settle();
      p.net.details.filter(r=>!r.fresh).at(-1)!.d.resolve(live(14,.61,{polymarket:src(.66,12),kalshi:src(.61,14)})); await settle();
      expect(has()).toBe(true);
    }finally{await p.unmount();}
  });
});


describe("176 new source chart admission", () => {
  it("reads authoritative history promptly for a newly admitted source, then ordinary prices need no reads", async () => {
    const one={polymarket:src(.55,10)};
    const noBlend={...unpinned(10,.55),aggregate_line:[]};
    const p=await mount(live(10,.55,one),noBlend);
    try {
      await p.emit("probability",snapFrame(11,.62,withPm(11)));
      expect(p.read()).toContain("live|62|kalshi+polymarket|r11");
      expect(p.pairs()).toHaveLength(0);
      await p.advance(250);
      expect(p.pairs()).toHaveLength(1);
      expect(p.net.histories.filter(r=>r.fresh)).toHaveLength(1);
      await p.answer(live(11,.62,withPm(11)),history(11,.62));
      expect(p.read()).toContain("c62");
      for(let rev=12;rev<22;rev++) {
        await p.emit("probability",snapFrame(rev,.63,withPm(rev)));
        await p.advance(250);
      }
      expect(p.pairs()).toHaveLength(1);
    } finally {await p.unmount();}
  });
});


describe("176 source addition while reads are busy",()=>{
 it("a refused older frame cannot invent an added-source history obligation",async()=>{
  const p=await mount(live(10,.55,{polymarket:src(.55,10)}),{...unpinned(10,.55),aggregate_line:[]});
  try {
   await act(async()=>{
    sources.at(-1)!.emit("probability",snapFrame(12,.62,{polymarket:src(.62,12)}));
    sources.at(-1)!.emit("probability",snapFrame(11,.61,withPm(11)));
   });
   await settle();
   expect(p.read()).toContain("live|62|polymarket|r12");
   expect(p.pairs()).toHaveLength(0);
  } finally {await p.unmount();}
 });
});


describe("176 R1 bounded source-added history debt", () => {
  const empty = (rev: number): History => ({
    ...unpinned(rev, .62), history_fold_revision: { [E]: rev }, aggregate_line: [],
  });
  it("retries an adopted empty unpinned history once, then draws the pinned edge", async () => {
    const p = await mount(live(10, .55, { polymarket: src(.55, 10) }), empty(10));
    try {
      await p.emit("probability", snapFrame(11, .62, withPm(11)));
      await p.advance(250);
      expect(p.pairs()).toHaveLength(1);
      await p.answer(live(11, .62, withPm(11)), empty(11));
      expect(p.read()).toContain("cNaN");
      await p.advance(1000);
      expect(p.pairs()).toHaveLength(2);
      expect(p.pairs()[1].at - p.pairs()[0].at).toBe(1000);
      await p.answer(live(11, .62, withPm(11)), history(11, .62));
      expect(p.read()).toContain("c62");
      await p.advance(32000);
      expect(p.pairs()).toHaveLength(2);
    } finally { await p.unmount(); }
  });
  it("expires after a second empty history without a third pair or retained trigger", async () => {
    const p = await mount(live(10, .55, { polymarket: src(.55, 10) }), empty(10));
    try {
      await p.emit("probability", snapFrame(11, .62, withPm(11)));
      await p.advance(250);
      await p.answer(live(11, .62, withPm(11)), empty(11));
      await p.advance(1000);
      expect(p.pairs()).toHaveLength(2);
      await p.answer(live(11, .62, withPm(11)), empty(11));
      await p.advance(32000);
      expect(p.pairs()).toHaveLength(2);
      expect(p.read()).toContain("cNaN");
      await p.emit("probability", snapFrame(12, .63, withPm(12)));
      await p.advance(1000);
      expect(p.pairs()).toHaveLength(2);
      expect(harness.quoteTrigger!()).toBeNull();
      expect(harness.sourceHistory!()).toBeNull();
      expect(p.net.histories.filter(r => r.fresh)).toHaveLength(2);
    } finally { await p.unmount(); }
  });
  it("expires the bounded obligation after two thrown pairs", async () => {
    const p = await mount(live(10, .55, { polymarket: src(.55, 10) }), empty(10));
    try {
      await p.emit("probability", snapFrame(11, .62, withPm(11)));
      await p.advance(250);
      await p.answer(new Error("offline"), new Error("offline"));
      await p.advance(1000);
      expect(p.pairs()).toHaveLength(2);
      await p.answer(new Error("offline"), new Error("offline"));
      await p.advance(32000);
      expect(p.pairs()).toHaveLength(2);
      expect(harness.quoteTrigger!()).toBeNull();
      expect(harness.sourceHistory!()).toBeNull();
    } finally { await p.unmount(); }
  });
  it("terminal adoption retires the pending source-added retry", async () => {
    const p = await mount(live(10, .55, { polymarket: src(.55, 10) }), empty(10));
    try {
      await p.emit("probability", snapFrame(11, .62, withPm(11)));
      await p.advance(250);
      await p.answer(live(11, .62, withPm(11)), empty(11));
      harness.revalidate!(); await settle();
      p.net.details.filter(r => !r.fresh).at(-1)!.d.resolve(final(12));
      await settle();
      await p.advance(32000);
      expect(p.read()).toContain("completed|100");
      expect(p.pairs()).toHaveLength(1);
      expect(harness.quoteTrigger!()).toBeNull();
      expect(harness.sourceHistory!()).toBeNull();
    } finally { await p.unmount(); }
  });
  it("navigation retires an in-flight source-added pair without adopting it on the new page", async () => {
    const p = await mount(live(10, .55, { polymarket: src(.55, 10) }), empty(10));
    try {
      await p.emit("probability", snapFrame(11, .62, withPm(11)));
      await p.advance(250);
      await p.navigate(B, live(20, .72, withPm(20), B), history(20, .72, B));
      await p.answer(live(11, .62, withPm(11)), history(11, .62));
      await p.advance(32000);
      expect(p.read()).toContain("r20|c72");
      expect(p.pairs(B)).toHaveLength(0);
      expect(harness.quoteTrigger!()).toBeNull();
      expect(harness.sourceHistory!()).toBeNull();
    } finally { await p.unmount(); }
  });

});
