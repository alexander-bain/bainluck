/**
 * #10646 (parent #10090) — MOUNTED: one held opening page, one pushed frame,
 * a fresh pair that fails or comes back behind, then silence. Does the page's
 * cache — what the hero and chart read — reach the coherent pair anyway?
 *
 * WHAT IS REAL: react-dom over `helpers/minimalDom`, the installed `swr` with
 * two cache entries (detail and history, as the page keys them per event), and
 * the page's OWN paired-read callback and `[foldedRefetch]` scheduler factory,
 * lifted from `app/events/[id]/page.tsx` with the TypeScript AST and evaluated
 * inside the component every render, as the page does — so nothing here is a
 * hand copy that can drift. They run over the real `createFoldedRefetchScheduler`,
 * `canSubscribeEventQuotes`, `quotePairCoversTrigger`, `keepNewerHeldHeadline`
 * and `historyRangeParam`. The push effect's quote branch is carried and PINNED
 * by the structural test (the #9051 / #10200 harnesses' method).
 *
 * WHAT IS SIMPLIFIED: the stream is a `liveFrame` prop, the boot fetchers are
 * plain deferreds (no poll cadence, so no timer fires a read the test did not
 * ask for), and the render prints the cached numbers rather than the hero
 * component. Time is fake (`jest.useFakeTimers`, `Date.now` included).
 */
import "../helpers/minimalDom";
import React, { act, useEffect, useRef, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import fs from "fs";
import path from "path";
import vm from "vm";
import ts from "typescript";
import useSWR, { SWRConfig } from "swr";

import type { LiveFrame } from "../../hooks/useLiveEventStream";
import { createFoldedRefetchScheduler } from "../../lib/foldedRefetchScheduler";
import { canSubscribeEventQuotes, quotePairCoversTrigger } from "../../lib/eventQuoteStream";
import { frameInvalidatesFoldedBlend } from "../../lib/eventLivePush";
import { keepNewerHeldHeadline } from "../../lib/reconcileEventPoll";
import { historyRangeParam } from "../../lib/event/historyRange";
import { EVENT_BOOT_HISTORY_HOURS } from "../../lib/event/detailBoot";

const PAGE = fs.readFileSync(path.join(__dirname, "../../app/events/[id]/page.tsx"), "utf8");
const FOLDED_FRAME_REFETCH_MS = Number(PAGE.match(/const FOLDED_FRAME_REFETCH_MS = (\d+)/)![1]);

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
const PAIR = pageScript((n, tree) => (ts.isBinaryExpression(n) &&
  n.left.getText(tree) === "pairedQuoteReadRef.current" && ts.isArrowFunction(n.right))
  ? n.right.getText(tree) : undefined);
const FACTORY = pageScript((n, tree) => {
  if (!ts.isVariableDeclaration(n) || n.name.getText(tree) !== "[foldedRefetch]" ||
      !n.initializer || !ts.isCallExpression(n.initializer)) return undefined;
  const init = n.initializer.arguments[0];
  return init && ts.isArrowFunction(init) ? init.body.getText(tree) : undefined;
});

// ── network ─────────────────────────────────────────────────────────────────
type Detail = {
  id: number; status: string; completed_at?: string | null;
  hero_probability: number; hero_probability_source: string;
  blend_fold_revision?: Record<string, number>;
};
type History = {
  event_id: number; blend_edge_pinned?: boolean;
  blend_edge_fold_revision?: Record<string, number>; aggregate_line: { home_probability: number }[];
};

class Deferred<T> {
  promise: Promise<T>;
  resolve!: (v: T) => void;
  reject!: (e: Error) => void;
  constructor() {
    this.promise = new Promise<T>((res, rej) => { this.resolve = res; this.reject = rej; });
  }
}
type Req<T> = { eventId: number; fresh: boolean; d: Deferred<T> };
type Net = { details: Req<Detail>[]; histories: Req<History>[] };

const A = 15324742;
const B = 15324650;
const opening = (id: number): Detail => ({ id, status: "scheduled", hero_probability: 0.4, hero_probability_source: "opening" });
const blend = (id: number, rev: number): Detail => ({
  id, status: "scheduled", hero_probability: 0.52, hero_probability_source: "blend", blend_fold_revision: { 900: rev },
});
const history = (id: number, rev: number, p: number): History => ({
  event_id: id, blend_edge_pinned: true, blend_edge_fold_revision: { 900: rev }, aggregate_line: [{ home_probability: p }],
});
const frame = (id: number, rev: number): LiveFrame => ({
  event_id: id, p: 0.52, source: "kalshi", source_value: 0.52,
  updated_at: "2026-10-06T20:00:05Z", status: "scheduled", rev: { 900: rev },
});

// ── the harness: the page's held quote wiring ───────────────────────────────
function HeldPage({ net, eventId, liveFrame }: { net: Net; eventId: number; liveFrame: LiveFrame | null }) {
  const fetchEvent = (id: number, fresh = false) => {
    const d = new Deferred<Detail>(); net.details.push({ eventId: id, fresh, d }); return d.promise;
  };
  const fetchEventHistory = (id: number, _hours: number, _range: unknown, fresh = false) => {
    const d = new Deferred<History>(); net.histories.push({ eventId: id, fresh, d }); return d.promise;
  };
  const { data: event, mutate: refreshEvent } = useSWR(["event", eventId], () => fetchEvent(eventId));
  const fullHistoryRequested = false;
  const { data: historyData, mutate: refreshHistory } = useSWR(
    ["history", eventId], () => fetchEventHistory(eventId, EVENT_BOOT_HISTORY_HOURS, historyRangeParam(false)),
  );
  const [, setLastRefresh] = useState(0);
  const freshNextEventReadRef = useRef(false);
  const heldEventRef = useRef<Detail | undefined>(undefined);
  heldEventRef.current = event;
  // ── app/events/[id]/page.tsx — these lines as the page writes them ────────
  const pairedQuoteReadRef = useRef<(() => Promise<unknown>) | null>(null);
  const quoteTriggerRef = useRef<LiveFrame | null>(null);
  const recoveryIntentRef = useRef(0);
  const quoteReadLifetimeRef = useRef(0);
  const quoteEventIdRef = useRef(eventId);
  if (quoteEventIdRef.current !== eventId) quoteTriggerRef.current = null;
  quoteEventIdRef.current = eventId;
  const refreshEventRef = useRef(refreshEvent);
  refreshEventRef.current = refreshEvent;
  const [foldedRefetch] = useState(() => FACTORY.runInNewContext({
    createFoldedRefetchScheduler, canSubscribeEventQuotes, FOLDED_FRAME_REFETCH_MS, Date,
    recoveryIntentRef, quoteReadLifetimeRef, quoteTriggerRef, pairedQuoteReadRef, freshNextEventReadRef, refreshEventRef, heldEventRef,
  }) as ReturnType<typeof createFoldedRefetchScheduler>);
  useEffect(() => () => foldedRefetch.cancel(), [foldedRefetch]);

  useEffect(() => {
    if (!liveFrame || liveFrame.event_id !== eventId) return;
    const held = heldEventRef.current;
    if (held && canSubscribeEventQuotes(held) && (
      liveFrame.p === null || held.hero_probability_source !== "blend" ||
      (liveFrame.status && liveFrame.status !== held.status) ||
      (held.status !== "live" && frameInvalidatesFoldedBlend(held, liveFrame))
    )) {
      quoteTriggerRef.current = liveFrame;
      foldedRefetch.request();
      return;
    }
  }, [liveFrame, eventId, foldedRefetch]);

  const quoteHistoryRangeRef = useRef(fullHistoryRequested);
  quoteHistoryRangeRef.current = fullHistoryRequested;
  const refreshHistoryRef = useRef(refreshHistory);
  refreshHistoryRef.current = refreshHistory;
  pairedQuoteReadRef.current = PAIR.runInNewContext({
    eventId, fullHistoryRequested, fetchEvent, fetchEventHistory, EVENT_BOOT_HISTORY_HOURS, historyRangeParam,
    quotePairCoversTrigger, keepNewerHeldHeadline, setLastRefresh, Date,
    recoveryIntentRef, quoteReadLifetimeRef, quoteTriggerRef, quoteEventIdRef, quoteHistoryRangeRef, refreshHistoryRef, refreshEventRef, heldEventRef,
  });

  if (!event || !historyData) return <>loading</>;
  const chart = historyData.aggregate_line[historyData.aggregate_line.length - 1]?.home_probability;
  return <>{`${event.id}|${Math.round(event.hero_probability * 100)}|${event.hero_probability_source}|${Math.round(chart * 100)}`}</>;
}

// ── mount / drive ───────────────────────────────────────────────────────────
async function settle() {
  await act(async () => { for (let i = 0; i < 12; i += 1) await Promise.resolve(); });
}
const doc = document as unknown as { createElement: (t: string) => Element; body: { appendChild: (c: unknown) => void } };

async function mount(id = A) {
  const net: Net = { details: [], histories: [] };
  const container = doc.createElement("div");
  doc.body.appendChild(container);
  const root: Root = createRoot(container);
  let eventId = id;
  let liveFrame: LiveFrame | null = null;
  const render = () => root.render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0, revalidateOnFocus: false }}>
      <HeldPage net={net} eventId={eventId} liveFrame={liveFrame} />
    </SWRConfig>,
  );
  const bootRead = async (target: number) => {
    await settle();
    net.details.filter((r) => r.eventId === target && !r.fresh).forEach((r) => r.d.resolve(opening(target)));
    net.histories.filter((r) => r.eventId === target && !r.fresh).forEach((r) => r.d.resolve(history(target, 11, 0.4)));
    await settle();
  };
  await act(async () => { render(); });
  await bootRead(id);
  const freshPairs = (target = A) => net.details.filter((r) => r.fresh && r.eventId === target).length;
  const lastPair = () => ({
    detail: net.details.filter((r) => r.fresh).at(-1)!.d,
    history: net.histories.filter((r) => r.fresh).at(-1)!.d,
  });
  return {
    net, freshPairs, lastPair,
    read: () => container.textContent ?? "",
    async push(f: LiveFrame) { liveFrame = f; await act(async () => { render(); }); await settle(); },
    async navigate(target: number) { eventId = target; liveFrame = null; await act(async () => { render(); }); await bootRead(target); },
    async advance(ms: number) { await act(async () => { await jest.advanceTimersByTimeAsync(ms); }); await settle(); },
    unmount: () => act(() => { root.unmount(); }),
  };
}

beforeEach(() => {
  jest.useFakeTimers();
  jest.setSystemTime(new Date(Date.UTC(2026, 9, 6, 20, 0, 0)));
});
afterEach(() => {
  jest.useRealTimers();
});

// ─────────────────────────────────────────────────────────────────────────────
describe("structural pin: the harness carries the page's push-effect quote branch", () => {
  it("app/events/[id]/page.tsx still reads as the lines HeldPage mounts", () => {
    expect(PAGE).toMatch(/if \(quoteEventIdRef\.current !== eventId\) quoteTriggerRef\.current = null;\s*quoteEventIdRef\.current = eventId;/);
    expect(PAGE).toMatch(/if \(held && canSubscribeEventQuotes\(held\) && \(\s*liveFrame\.p === null \|\| held\.hero_probability_source !== "blend" \|\|\s*\(liveFrame\.status && liveFrame\.status !== held\.status\) \|\|\s*\(held\.status !== "live" && frameInvalidatesFoldedBlend\(held, liveFrame\)\)\s*\)\) \{\s*quoteTriggerRef\.current = liveFrame;\s*foldedRefetch\.request\(\);\s*return;\s*\}/);
    expect(PAGE).toMatch(/const quoteHistoryRangeRef = useRef\(fullHistoryRequested\);\s*quoteHistoryRangeRef\.current = fullHistoryRequested;/);
    expect(PAGE).toMatch(/useEffect\(\(\) => \(\) => foldedRefetch\.cancel\(\), \[foldedRefetch\]\);/);
  });
});

describe.each([
  ["a rejected detail half", (p: { detail: Deferred<Detail>; history: Deferred<History> }) => {
    p.detail.reject(new Error("temporary read failure")); p.history.resolve(history(A, 12, 0.52));
  }],
  ["a detail behind the frame", (p: { detail: Deferred<Detail>; history: Deferred<History> }) => {
    p.detail.resolve(blend(A, 11)); p.history.resolve(history(A, 12, 0.52));
  }],
  ["a history behind the frame", (p: { detail: Deferred<Detail>; history: Deferred<History> }) => {
    p.detail.resolve(blend(A, 12)); p.history.resolve(history(A, 11, 0.47));
  }],
] as const)("#10646 mounted: %s, then a quiet stream", (_name, failFirst) => {
  it("the page reaches the coherent pair on one retry, without a second frame or a half-adopted pair", async () => {
    const page = await mount();
    expect(page.read()).toBe(`${A}|40|opening|40`);
    await page.push(frame(A, 12));
    expect(page.freshPairs()).toBe(1);
    failFirst(page.lastPair());
    await settle();
    // Refused whole: neither the headline nor the chart moved.
    expect(page.read()).toBe(`${A}|40|opening|40`);
    await page.advance(FOLDED_FRAME_REFETCH_MS - 1);
    expect(page.freshPairs()).toBe(1);
    await page.advance(1);
    expect(page.freshPairs()).toBe(2);
    const retry = page.lastPair();
    retry.detail.resolve(blend(A, 12));
    retry.history.resolve(history(A, 12, 0.52));
    await settle();
    expect(page.read()).toBe(`${A}|52|blend|52`);
    await page.advance(10_000);
    expect(page.freshPairs()).toBe(2);
    await page.unmount();
  });
});

describe("#10646 mounted bounds", () => {
  it("a pair that keeps failing is retried once, then the page holds its opening value and waits", async () => {
    const page = await mount();
    await page.push(frame(A, 12));
    page.lastPair().detail.reject(new Error("offline"));
    page.lastPair().history.reject(new Error("offline"));
    await settle();
    await page.advance(FOLDED_FRAME_REFETCH_MS);
    expect(page.freshPairs()).toBe(2);
    page.lastPair().detail.reject(new Error("offline"));
    page.lastPair().history.reject(new Error("offline"));
    await settle();
    await page.advance(10_000);
    expect(page.freshPairs()).toBe(2);
    expect(page.read()).toBe(`${A}|40|opening|40`);
    await page.unmount();
  });

  it("navigating away while the retry is queued retires it — no fresh read for either event", async () => {
    const page = await mount();
    await page.push(frame(A, 12));
    page.lastPair().detail.resolve(blend(A, 11));
    page.lastPair().history.resolve(history(A, 12, 0.52));
    await settle();
    await page.navigate(B);
    expect(page.read()).toBe(`${B}|40|opening|40`);
    const reads = page.net.details.length;
    await page.advance(10_000);
    expect(page.freshPairs(A)).toBe(1);
    expect(page.freshPairs(B)).toBe(0);
    // Not turned into an unrelated detail read for the new page either.
    expect(page.net.details.length).toBe(reads);
    await page.unmount();
  });

  it("unmounting while the retry is queued cancels it", async () => {
    const page = await mount();
    await page.push(frame(A, 12));
    page.lastPair().detail.resolve(blend(A, 11));
    page.lastPair().history.resolve(history(A, 12, 0.52));
    await settle();
    const reads = page.net.details.length;
    await page.unmount();
    await act(async () => { await jest.advanceTimersByTimeAsync(10_000); });
    expect(page.freshPairs(A)).toBe(1);
    expect(page.net.details.length).toBe(reads);
  });
});
