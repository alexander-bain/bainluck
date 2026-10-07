/** #10666: actual hook/controller into AST-extracted application page callbacks.
 * No prototype source transformations; mocked EventSource and controlled HTTP/clocks.
 * Minimal DOM prints the two cached values, not the actual hero/chart components.
 * Boot fixture is scheduled/opening; normal polling and browser networking omitted.
 */
import "../helpers/minimalDom";
import { createReconnectCatchup } from "../../lib/reconnectCatchup";
import { createLiveStreamController, type StreamHandle } from "../../lib/liveStreamController";
import React, { act, useEffect, useRef, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import fs from "fs";
import path from "path";
import vm from "vm";
import ts from "typescript";
import useSWR, { SWRConfig } from "swr";

import { useLiveEventStream, type LiveFrame } from "../../hooks/useLiveEventStream";
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
function effectScript(contains: string) {
  return pageScript((n, tree) => {
    if (!ts.isCallExpression(n) || n.expression.getText(tree) !== 'useEffect') return undefined;
    const callback=n.arguments[0];
    return callback && ts.isArrowFunction(callback) && callback.getText(tree).includes(contains)
      ? callback.getText(tree) : undefined;
  });
}
const RECOVERY_EFFECT = effectScript('createReconnectCatchup');
const NOTIFY_EFFECT = effectScript('recoveryRef.current?.recover');

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
function HeldPage({ net, eventId, candidate, enabled }: { net: Net; eventId: number; candidate: boolean; enabled: boolean }) {
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
  const {frame: liveFrame, recoveryGeneration} = useLiveEventStream(eventId, candidate && enabled);
  const quoteEligible = canSubscribeEventQuotes(event) && enabled;
  const freshNextEventReadRef = useRef(false);
  const heldEventRef = useRef<Detail | undefined>(undefined);
  heldEventRef.current = event;
  // ── app/events/[id]/page.tsx — these lines as the page writes them ────────
  const pairedQuoteReadRef = useRef<(() => Promise<unknown>) | null>(null);
  const quoteTriggerRef = useRef<LiveFrame | null>(null);
  const recoveryIntentRef = useRef(0);
  const quoteReadLifetimeRef = useRef(0);
  const quoteEventIdRef = useRef(eventId);
  if (quoteEventIdRef.current !== eventId) { quoteTriggerRef.current = null; recoveryIntentRef.current = 0; }
  quoteEventIdRef.current = eventId;
  const refreshEventRef = useRef(refreshEvent);
  refreshEventRef.current = refreshEvent;
  const [foldedRefetch] = useState(() => FACTORY.runInNewContext({
    createFoldedRefetchScheduler, canSubscribeEventQuotes, FOLDED_FRAME_REFETCH_MS, Date,
    quoteTriggerRef, recoveryIntentRef, quoteReadLifetimeRef, pairedQuoteReadRef, freshNextEventReadRef, refreshEventRef, heldEventRef,
  }) as ReturnType<typeof createFoldedRefetchScheduler>);
  useEffect(() => () => foldedRefetch.cancel(), [foldedRefetch]);
  const recoveryRef = useRef<ReturnType<typeof createReconnectCatchup> | null>(null);
  useEffect(RECOVERY_EFFECT.runInNewContext({
    quoteEligible, createReconnectCatchup, canSubscribeEventQuotes, heldEventRef,
    recoveryIntentRef, quoteReadLifetimeRef, recoveryRef, foldedRefetch,
  }), [eventId, quoteEligible, foldedRefetch]);
  useEffect(NOTIFY_EFFECT.runInNewContext({quoteEligible, recoveryGeneration, recoveryRef}),
    [recoveryGeneration, quoteEligible, eventId]);


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
    quoteTriggerRef, recoveryIntentRef, quoteReadLifetimeRef, quoteEventIdRef, quoteHistoryRangeRef, refreshHistoryRef, refreshEventRef, heldEventRef,
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

async function mount(candidate = true, id = A) {
  const net: Net = { details: [], histories: [] };
  const container = doc.createElement("div");
  doc.body.appendChild(container);
  const root: Root = createRoot(container);
  let eventId = id;
  let enabled = true;
  const render = () => root.render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0, revalidateOnFocus: false }}>
      <HeldPage net={net} eventId={eventId} candidate={candidate} enabled={enabled} />
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
    async recover(epoch: number) { await act(async () => { sources.at(-1)?.emit("resync", JSON.stringify({generation:epoch})); }); await settle(); },
    async push(f: LiveFrame) { await act(async () => { sources.at(-1)?.emit("probability", JSON.stringify(f)); }); await settle(); },
    async navigate(target: number) { eventId = target; await act(async () => { render(); }); await bootRead(target); },
    async advance(ms: number) { await act(async () => { await jest.advanceTimersByTimeAsync(ms); }); await settle(); },
    async enable(next: boolean) { enabled=next; await act(async()=>{render();}); await settle(); },
    unmount: () => act(() => { root.unmount(); }),
  };
}

const sources: HookSource[]=[];
const originalEventSource=globalThis.EventSource;
class HookSource implements StreamHandle {
  readyState=1;
  listeners=new Map<string,(event:unknown)=>void>();
  constructor(_url:string){sources.push(this);}
  close(){this.readyState=2;}
  addEventListener(name:string,listener:(event:unknown)=>void){this.listeners.set(name,listener);}
  emit(name:string,data?:string){this.listeners.get(name)?.({data});}
}
beforeEach(() => {
  sources.length=0;
  globalThis.EventSource=HookSource as unknown as typeof EventSource;
  jest.spyOn(Math, 'random').mockReturnValue(150/4900);
  jest.useFakeTimers();
  jest.setSystemTime(new Date(Date.UTC(2026, 9, 6, 20, 0, 0)));
});
afterEach(() => {
  globalThis.EventSource=originalEventSource;
  jest.restoreAllMocks();
  jest.useRealTimers();
});


describe("#10666 mounted recovery candidate", () => {
  it("baseline receives no missed quote and does not initiate early catch-up", async () => {
    const p = await mount(false); await p.recover(1); await p.advance(5000);
    expect(p.freshPairs()).toBe(0); expect(p.read()).toBe(`${A}|40|opening|40`);
    await p.unmount();
  });
  it("one recovery reaches the coherent pair without any new venue frame", async () => {
    const p = await mount(); await p.recover(1); await p.advance(249);
    expect(p.freshPairs()).toBe(0); await p.advance(1); expect(p.freshPairs()).toBe(1);
    const pair = p.lastPair(); pair.detail.resolve(blend(A,12)); pair.history.resolve(history(A,12,.52));
    await settle(); expect(p.read()).toBe(`${A}|52|blend|52`);
    await p.advance(10000); expect(p.freshPairs()).toBe(1); await p.unmount();
  });
  it("an incoherent pair is withheld and one quiet retry pays recovery", async () => {
    const p = await mount(); await p.recover(1); await p.advance(250);
    p.lastPair().detail.resolve(blend(A,12)); p.lastPair().history.resolve(history(A,11,.47));
    await settle(); expect(p.read()).toBe(`${A}|40|opening|40`);
    await p.advance(1000); expect(p.freshPairs()).toBe(2);
    p.lastPair().detail.resolve(blend(A,12)); p.lastPair().history.resolve(history(A,12,.52));
    await settle(); expect(p.read()).toBe(`${A}|52|blend|52`); await p.unmount();
  });
  it("failed halves stop after one bounded retry", async () => {
    const p = await mount(); await p.recover(1); await p.advance(250);
    for (let i=0;i<2;i++) {
      p.lastPair().detail.reject(new Error("offline")); p.lastPair().history.reject(new Error("offline"));
      await settle(); await p.advance(1000);
    }
    await p.advance(10000); expect(p.freshPairs()).toBe(2);
    expect(p.read()).toBe(`${A}|40|opening|40`); await p.unmount();
  });
  it("twenty coalesced generations schedule one initial pair", async () => {
    const p = await mount(); for (let i=1;i<=20;i++) await p.recover(i);
    await p.advance(250); expect(p.freshPairs()).toBe(1); await p.unmount();
  });
  it("navigation cancels queued catch-up without reading either event", async () => {
    const p = await mount(); await p.recover(1); await p.navigate(B); await p.advance(5000);
    expect(p.freshPairs(A)).toBe(0); expect(p.freshPairs(B)).toBe(0); await p.unmount();
  });
  it("late old-event responses cannot overwrite the newly held page", async () => {
    const p = await mount(); await p.recover(1); await p.advance(250); const old=p.lastPair();
    await p.navigate(B); old.detail.resolve(blend(A,12)); old.history.resolve(history(A,12,.52));
    await settle(); expect(p.read()).toBe(`${B}|40|opening|40`); await p.unmount();
  });
  it("healthy quiet page performs no recovery work", async () => {
    const p=await mount(); await p.advance(10000); expect(p.freshPairs()).toBe(0); await p.unmount();
  });
});

class LabSource implements StreamHandle {
  readyState=1;
  listeners = new Map<string, (event:unknown)=>void>();
  close(){this.readyState=2;}
  addEventListener(name:string, fn:(event:unknown)=>void){this.listeners.set(name,fn);}
  emit(name:string,data?:string){this.listeners.get(name)?.({data});}
}
it("private Redis resync wire drives mounted paired catch-up without closing transport", async()=>{
  const wire=JSON.parse(fs.readFileSync(path.join(__dirname,"../fixtures/reconnectResyncWire10666.json"),"utf8"));
  expect(wire.stream_retained).toBe(true);
  const p=await mount(); const stream=new LabSource(); const epochs:number[]=[];
  const controller=createLiveStreamController({open:()=>stream,now:Date.now,onFrame:()=>{},
    onDeliveringChange:()=>{},onRecovery:g=>epochs.push(g)});
  controller.start();
  for(const chunk of wire.wire){
    const name=/^event: (.+)$/m.exec(chunk)?.[1];const data=/^data: (.+)$/m.exec(chunk)?.[1];
    if(name)stream.emit(name,data);
  }
  expect(epochs).toEqual([1]);expect(stream.readyState).toBe(1);expect(controller.state.connections).toBe(1);
  await p.recover(epochs[0]); await p.advance(250);
  p.lastPair().detail.resolve(blend(A,12));p.lastPair().history.resolve(history(A,12,.52));
  await settle(); expect(p.read()).toBe(`${A}|52|blend|52`);
  expect(stream.readyState).toBe(1);controller.stop();await p.unmount();
});
it("recovery ordinals survive a replacement transport with a restarted server generation",()=>{
 const sources:LabSource[]=[];const epochs:number[]=[];let time=1000;
 const c=createLiveStreamController({open:()=>{const s=new LabSource();sources.push(s);return s;},now:()=>time,onFrame:()=>{},onDeliveringChange:()=>{},onRecovery:g=>epochs.push(g)});
 c.start();sources[0].emit('open');sources[0].emit('resync','{"generation":9}');
 sources[0].emit('resync','{"generation":9}');sources[0].emit('resync','{"generation":8}');
 sources[0].emit('reconnect');time+=1000;c.tick();sources[1].emit('open');
 sources[0].emit('resync','{"generation":10}');sources[1].emit('resync','{"generation":1}');
 expect(epochs).toEqual([1,2]);c.stop();
});
it("corrupt recovery generations do no work",()=>{
 const s=new LabSource();const calls:number[]=[];const c=createLiveStreamController({open:()=>s,now:Date.now,onFrame:()=>{},onDeliveringChange:()=>{},onRecovery:g=>calls.push(g)});
 c.start();for(const data of ['oops','{}','{"generation":0}','{"generation":-1}','{"generation":1.5}','{"generation":"1"}'])s.emit('resync',data);
 expect(calls).toEqual([]);c.stop();s.emit('resync','{"generation":1}');expect(calls).toEqual([]);
});

it("recovery does not erase a newer quote revision already waiting for a pair",async()=>{
 const p=await mount();await p.recover(1);await p.push(frame(A,13));const old=p.lastPair();
 await p.advance(250);old.detail.resolve(blend(A,12));old.history.resolve(history(A,12,.52));
 await settle();expect(p.read()).toBe(`${A}|40|opening|40`);
 await p.advance(1000);expect(p.freshPairs()).toBe(2);
 p.lastPair().detail.resolve(blend(A,13));p.lastPair().history.resolve(history(A,13,.52));
 await settle();expect(p.read()).toBe(`${A}|52|blend|52`);await p.unmount();
});
it("terminal pair retires catch-up that was queued before the result",async()=>{
 const p=await mount();await p.recover(1);await p.push({...frame(A,12),status:'final'});
 p.lastPair().detail.resolve({...blend(A,12),status:'final',hero_probability:1});
 p.lastPair().history.resolve(history(A,12,1));await settle();
 await p.advance(5000);expect(p.freshPairs()).toBe(1);expect(p.read()).toBe(`${A}|100|blend|100`);await p.unmount();
});

it("independent: a resync during an older outstanding pair retains a second PAIRED read", async () => {
  const p = await mount();
  await p.recover(1); await p.advance(250);
  const old = p.lastPair();
  // Second Redis rebuild loses the last quote after the first reads started.
  await p.recover(2); await p.advance(250);
  old.detail.resolve(blend(A,12)); old.history.resolve(history(A,12,.52));
  await settle();
  await p.advance(1000);
  expect(p.freshPairs()).toBe(2);
  p.lastPair().detail.resolve(blend(A,13)); p.lastPair().history.resolve(history(A,13,.56));
  await settle(); await p.unmount();
});

it("independent: coherent new fold after contributor removal can replace held fold", async () => {
  const p = await mount();
  await p.recover(1); await p.advance(250);
  p.lastPair().detail.resolve({...blend(A,12), blend_fold_revision:{900:12,901:4}});
  p.lastPair().history.resolve({...history(A,12,.52), blend_edge_fold_revision:{900:12,901:4}});
  await settle(); expect(p.read()).toBe(`${A}|52|blend|52`);
  await p.recover(2); await p.advance(1000);
  p.lastPair().detail.resolve({...blend(A,13),hero_probability:.56});
  p.lastPair().history.resolve(history(A,13,.56));
  await settle();
  expect(p.read()).toBe(`${A}|56|blend|56`);
  await p.unmount();
});


it("independent: server generation reset on browser reconnect of SAME EventSource is accepted", () => {
  const stream = new LabSource(); const epochs:number[]=[];
  const c=createLiveStreamController({open:()=>stream,now:Date.now,onFrame:()=>{},onDeliveringChange:()=>{},onRecovery:g=>epochs.push(g)});
  c.start(); stream.emit('open'); stream.emit('resync','{"generation":9}');
  // Native EventSource retries itself without constructing a new handle.
  stream.readyState=0; stream.emit('error');
  stream.readyState=1; stream.emit('open');
  // The new request can land on a new worker with generation reset to 1.
  stream.emit('resync','{"generation":1}');
  c.stop(); expect(epochs).toEqual([1,2]);
});


it("independent correction: history must cover fetched detail even with a quote trigger", async () => {
  const p = await mount();
  await p.recover(1); await p.push(frame(A,12));
  await p.advance(250);
  const old = p.lastPair();
  old.detail.resolve({...blend(A,13),hero_probability:.56});
  old.history.resolve(history(A,12,.52));
  await settle();
  const observed = p.read();
  await p.unmount();
  // A newer pair can retry. A coherent-looking older trigger cannot license
  // rendering headline 56 above history 52 from a different revision.
  expect(observed).toBe(`${A}|40|opening|40`);
});


it("same-event enabled toggle retires old work and accepts restarted server generation", async () => {
  const p=await mount(); await p.recover(1); await p.advance(250);
  p.lastPair().detail.resolve(blend(A,12)); p.lastPair().history.resolve(history(A,12,.52));
  await settle(); expect(p.freshPairs()).toBe(1);
  const old=sources.at(-1)!;
  await p.enable(false); await p.enable(true); await p.advance(5000);
  expect(old.readyState).toBe(2); expect(p.freshPairs()).toBe(1);
  await p.recover(1); await p.advance(250); expect(p.freshPairs()).toBe(2);
  p.lastPair().detail.resolve(blend(A,13)); p.lastPair().history.resolve(history(A,13,.56));
  await settle(); await p.unmount();
});
it("disabled lifetime cancels queued jitter and rejects late same-event pair", async () => {
  const p=await mount(); await p.recover(1); await p.enable(false); await p.advance(5000);
  expect(p.freshPairs()).toBe(0);
  await p.enable(true); await p.recover(1); await p.advance(250);
  const old=p.lastPair(); await p.enable(false); await p.enable(true);
  old.detail.resolve(blend(A,12)); old.history.resolve(history(A,12,.52));
  await settle(); expect(p.read()).toBe(`${A}|40|opening|40`);
  await p.advance(5000); expect(p.freshPairs()).toBe(1);
  await p.recover(1); await p.advance(250); expect(p.freshPairs()).toBe(2);
  await p.unmount();
});
it("a recovery pair older than the held headline cannot replace its chart", async () => {
  const p=await mount(); await p.recover(1); await p.advance(250);
  p.lastPair().detail.resolve({...blend(A,13),hero_probability:.56});
  p.lastPair().history.resolve(history(A,13,.56)); await settle();
  await p.recover(2); await p.advance(1000);
  p.lastPair().detail.resolve(blend(A,12)); p.lastPair().history.resolve(history(A,12,.52));
  await settle(); expect(p.read()).toBe(`${A}|56|blend|56`);
  await p.unmount();
});
it.each([[-1,100],[0,100],[100000,4999],[NaN,4999],[Infinity,4999]])(
  "recovery jitter %s is bounded to %sms", async (chosen,expected) => {
    const called=jest.fn(); const c=createReconnectCatchup(called,()=>chosen);
    c.recover(1); c.recover(2);
    await jest.advanceTimersByTimeAsync(expected-1); expect(called).not.toHaveBeenCalled();
    await jest.advanceTimersByTimeAsync(1); expect(called).toHaveBeenCalledTimes(1);
    expect(called).toHaveBeenCalledWith(2); c.cancel();
  },
);
