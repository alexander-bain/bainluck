/**
 * #10200 (child of #9655) — ONE MOUNTED HELD PAGE, through the real transport
 * controller and the page's real adoption wiring, reading the chart status.
 *
 * WHAT IS REAL HERE: `useLiveEventStream` (the hook, its controller, its one
 * interval) over a fake `EventSource` the test drives; the installed `swr` with
 * the page's key and fetcher (`fetchEventWithLiveFrame` with its held-event
 * getter); the page's push effect as `app/events/[id]/page.tsx` writes it,
 * including the refuse-and-refetch branch and the real
 * `createFoldedRefetchScheduler`; `applyLiveFrame`; and the page's status
 * wiring — the accepted price clock, `stepConnectionTracker`,
 * `presentConnectionStatus`. The page is a default export with no seam, so
 * those lines are carried here and PINNED by the structural test at the top,
 * which fails if they are no longer the page's (the #9051 harness's method).
 *
 * WHAT IS SIMPLIFIED, AND WHY IT DOES NOT TOUCH THE QUESTION: the poll cadence
 * is left off (a REST adoption is driven explicitly with `poll()`, so no timer
 * fires a request the test did not ask for), the paired quote read is absent
 * (the scheduler falls through to the detail refetch, its second branch), and
 * the printed percent is `round(hero_probability × 100)` rather than the full
 * `resolveProbability` — the status compares what the hero prints, and on a
 * live blend that is this number.
 *
 * Network is a list of deferred promises the test resolves; time is fake
 * (`jest.useFakeTimers`, `Date.now` included). No assertion branches on the
 * wall clock (gotcha #44).
 */

import "../helpers/minimalDom";
import React, { act, useEffect, useRef, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import fs from "fs";
import path from "path";
import useSWR, { SWRConfig } from "swr";

import { useLiveEventStream, type LiveFrame } from "../../hooks/useLiveEventStream";
import { applyLiveFrame, frameInvalidatesFoldedBlend } from "../../lib/eventLivePush";
import { canSubscribeEventQuotes } from "../../lib/eventQuoteStream";
import { fetchEventWithLiveFrame } from "../../lib/reconcileEventPoll";
import { createFoldedRefetchScheduler, takeFreshRead } from "../../lib/foldedRefetchScheduler";
import { isFinishedStatus } from "../../lib/eventState";
import { DATA_SILENCE_TIMEOUT_MS, TICK_INTERVAL_MS } from "../../lib/liveStreamController";
import {
  CONNECTION_FEEDBACK_MS,
  EMPTY_CONNECTION_TRACKER,
  presentConnectionStatus,
  stepConnectionTracker,
  type ConnectionTracker,
} from "../../lib/event/liveConnectionStatus";

const PAGE = fs.readFileSync(path.join(__dirname, "../../app/events/[id]/page.tsx"), "utf8");
const FOLDED_FRAME_REFETCH_MS = Number(PAGE.match(/const FOLDED_FRAME_REFETCH_MS = (\d+)/)![1]);

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

// ── deferred network ────────────────────────────────────────────────────────
type Held = {
  id: number;
  status: string;
  hero_probability: number;
  hero_probability_away: number;
  hero_probability_source: string;
  hero_probability_observed_at: string;
  win_probability_sources: Record<string, { value: number; updated_at: string }>;
};
class Deferred {
  promise: Promise<Held>;
  resolve!: (v: Held) => void;
  constructor() {
    this.promise = new Promise((r) => { this.resolve = r; });
  }
}

const A = 15320001;
const B = 15320002;
const T0 = Date.UTC(2026, 9, 2, 20, 0, 0);
const T = (s: number) => new Date(T0 + s * 1000).toISOString();

function held(args: { id?: number; p: number; at: string; status?: string }): Held {
  return {
    id: args.id ?? A,
    status: args.status ?? "live",
    hero_probability: args.p,
    hero_probability_away: 1 - args.p,
    hero_probability_source: "blend",
    hero_probability_observed_at: args.at,
    win_probability_sources: { kalshi: { value: args.p, updated_at: args.at } },
  };
}

function frame(args: { id?: number; p: number | null; at: string }): string {
  return JSON.stringify({
    event_id: args.id ?? A,
    p: args.p,
    source: "kalshi",
    source_value: args.p,
    updated_at: args.at,
    status: "live",
  } satisfies LiveFrame);
}

// ── the harness: the page's held-event + status wiring ──────────────────────
type Net = { requests: Deferred[] };

function HeldPage({ net, eventId }: { net: Net; eventId: number }) {
  const freshNextEventReadRef = useRef(false);
  const latestLiveFrameRef = useRef<LiveFrame | null>(null);
  const heldEventRef = useRef<Held | undefined>(undefined);
  const connectionTrackerRef = useRef<ConnectionTracker>(EMPTY_CONNECTION_TRACKER);

  const { data: event, mutate: refreshEvent } = useSWR(
    ["event", eventId],
    () => fetchEventWithLiveFrame(
      () => { takeFreshRead(freshNextEventReadRef); const d = new Deferred(); net.requests.push(d); return d.promise; },
      () => latestLiveFrameRef.current,
      () => null,
      () => heldEventRef.current,
    ),
  );
  heldEventRef.current = event;
  // The test's handle on the page's `refreshEvent`, for an explicit REST read.
  currentMutate = () => refreshEvent();
  const pairedQuoteReadRef = useRef<(() => Promise<unknown>) | null>(null);
  const quoteTriggerRef = useRef<LiveFrame | null>(null);
  const quoteEventIdRef = useRef(eventId);
  if (quoteEventIdRef.current !== eventId) quoteTriggerRef.current = null;
  quoteEventIdRef.current = eventId;
  const refreshEventRef = useRef(refreshEvent);
  refreshEventRef.current = refreshEvent;
  const [foldedRefetch] = useState(() => createFoldedRefetchScheduler(
    () => {
      if (quoteTriggerRef.current && pairedQuoteReadRef.current) return pairedQuoteReadRef.current();
      freshNextEventReadRef.current = true;
      return refreshEventRef.current();
    }, FOLDED_FRAME_REFETCH_MS,
  ));
  useEffect(() => () => foldedRefetch.cancel(), [foldedRefetch]);
  // The page re-renders at least once a second on its countdown tick, which is
  // what lets a receipt expire on screen. Stood in for here (pinned below).
  const [, setTick] = useState(0);
  useEffect(() => {
    const interval = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(interval);
  }, []);

  const quoteEligible = canSubscribeEventQuotes(event);
  const {
    frame: liveFrame,
    connected: streamConnected,
    status: reportedStreamStatus,
  } = useLiveEventStream(eventId, quoteEligible);
  const streamStatus = reportedStreamStatus ?? (streamConnected ? "open" : "idle");

  // ── app/events/[id]/page.tsx — the push effect, as the page writes it ──────
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
    if (frameInvalidatesFoldedBlend(heldEventRef.current, liveFrame)) {
      foldedRefetch.request();
      return;
    }
    if (liveFrame.p === null || liveFrame.p === undefined) return;
    latestLiveFrameRef.current = liveFrame;
    const frame = { ...liveFrame, p: liveFrame.p };
    refreshEvent(
      (prev) => applyLiveFrame(prev, frame),
      { revalidate: false },
    );
  }, [liveFrame, refreshEvent, eventId, foldedRefetch]);

  // The page returns its loading view here; the status is drawn only below.
  if (!event) return <>loading</>;

  // ── app/events/[id]/page.tsx — the status wiring, as the page writes it ────
  const freshestSourceStamp = Object.values(event.win_probability_sources)[0]?.updated_at ?? null;
  const homePct = Math.round(event.hero_probability * 100);
  const awayPct = 100 - homePct;
  const connectionTerminalLabel = isFinishedStatus(event.status) ? "Finished" : null;
  const acceptedPriceClock = event.hero_probability_observed_at ?? freshestSourceStamp;
  connectionTrackerRef.current = stepConnectionTracker(
    connectionTrackerRef.current,
    {
      eventId,
      status: streamStatus,
      priceObservedAt: acceptedPriceClock,
      valueKey: homePct === null ? null : `${homePct}/${awayPct ?? ""}`,
      terminal: Boolean(connectionTerminalLabel),
    },
    Date.now(),
  );
  const presentation = presentConnectionStatus(
    connectionTrackerRef.current,
    { status: streamStatus, terminalLabel: connectionTerminalLabel, priceMayBeOld: false, scoreMayBeOld: false },
    Date.now(),
  );
  return <>{`${homePct}|${presentation.label}|${presentation.announcement}|${acceptedPriceClock}`}</>;
}

// ── mount / drive helpers ───────────────────────────────────────────────────
async function settle() {
  await act(async () => {
    for (let i = 0; i < 12; i += 1) await Promise.resolve();
  });
}

const doc = document as unknown as { createElement: (t: string) => Element; body: { appendChild: (c: unknown) => void } };

async function mountHeldPage(first: Held) {
  const net: Net = { requests: [] };
  const container = doc.createElement("div");
  doc.body.appendChild(container);
  const root: Root = createRoot(container);
  let eventId = first.id;
  const render = () => root.render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <HeldPage net={net} eventId={eventId} />
    </SWRConfig>,
  );
  await act(async () => { render(); });
  await settle();
  net.requests[0].resolve(first);
  await settle();
  const seen: string[] = [];
  const read = () => {
    const [pct, label, announcement, clock] = (container.textContent ?? "").split("|");
    seen.push(label);
    return { pct, label, announcement, clock };
  };
  const stream = () => FakeEventSource.all[FakeEventSource.all.length - 1];
  return {
    net,
    read,
    seen,
    stream,
    async emit(type: string, data?: unknown) {
      await act(async () => { stream().emit(type, data); });
      await settle();
    },
    async resolveLast(h: Held) {
      net.requests[net.requests.length - 1].resolve(h);
      await settle();
    },
    /** A REST read the page adopts — the poll, or the refetch after `closed`. */
    async poll() {
      await act(async () => { void currentMutate?.(); });
      await settle();
    },
    async advance(ms: number) {
      await act(async () => { jest.advanceTimersByTime(ms); });
      await settle();
    },
    async navigate(id: number) {
      eventId = id;
      await act(async () => { render(); });
      await settle();
    },
    unmount: () => act(() => { root.unmount(); }),
  };
}

// The page's `refreshEvent`, reachable for an explicit REST read.
let currentMutate: (() => Promise<unknown>) | null = null;

beforeEach(() => {
  jest.useFakeTimers();
  jest.setSystemTime(new Date(T0));
  FakeEventSource.all = [];
  currentMutate = null;
});
afterEach(() => {
  jest.useRealTimers();
});

// ─────────────────────────────────────────────────────────────────────────────
describe("structural pin: the harness carries the page's own wiring", () => {
  it("app/events/[id]/page.tsx still reads as the lines HeldPage mounts", () => {
    // The fetcher, with the held-event getter a REST read reconciles against.
    expect(PAGE).toMatch(/fetchEventWithLiveFrame\(\s*\(\) => fetchEvent\(eventId, takeFreshRead\(freshNextEventReadRef\)\),\s*\(\) => latestLiveFrameRef\.current,\s*\(\) => latestBlendEdgeRef\.current,\s*\(\) => heldEventRef\.current,/);
    // The scheduler and its two branches.
    expect(PAGE).toMatch(/createFoldedRefetchScheduler\(\s*\(\) => \{\s*if \(\(quoteTriggerRef\.current \|\| recoveryIntentRef\.current\) && pairedQuoteReadRef\.current\) return pairedQuoteReadRef\.current\(\);\s*freshNextEventReadRef\.current = true;\s*return refreshEventRef\.current\(\);\s*\}, FOLDED_FRAME_REFETCH_MS,/);
    // The hook, its status, and the fallback for a stream that reports only `connected`.
    expect(PAGE).toMatch(/status: reportedStreamStatus,\s*recoveryGeneration,\s*\} = useLiveEventStream\(eventId, quoteEligible\);/);
    expect(PAGE).toMatch(/const streamStatus = reportedStreamStatus \?\? \(streamConnected \? "open" : "idle"\);/);
    // The push effect: refuse-and-refetch first, then the one guarded write.
    expect(PAGE).toMatch(/if \(held && canSubscribeEventQuotes\(held\) && \(\s*liveFrame\.p === null \|\| held\.hero_probability_source !== "blend" \|\|\s*\(liveFrame\.status && liveFrame\.status !== held\.status\) \|\|\s*\(held\.status !== "live" && frameInvalidatesFoldedBlend\(held, liveFrame\)\)\s*\)\) \{\s*quoteTriggerRef\.current = liveFrame;\s*foldedRefetch\.request\(\);\s*return;\s*\}/);
    expect(PAGE).toMatch(/if \(liveFrame\.p === null \|\| liveFrame\.p === undefined\) return;\s*latestLiveFrameRef\.current = liveFrame;\s*const frame = \{ \.\.\.liveFrame, p: liveFrame\.p \};\s*refreshEvent\(/);
    expect(PAGE.match(/applyLiveFrame\(prev, frame\)/g)).toHaveLength(1);
    // The status wiring: the ACCEPTED clock, and one step per render from the held result.
    expect(PAGE).toMatch(/const acceptedPriceClock = event\.hero_probability_observed_at \?\? freshestSourceStamp;/);
    expect(PAGE).toMatch(/connectionTrackerRef\.current = stepConnectionTracker\(\s*connectionTrackerRef\.current,\s*\{\s*eventId,\s*status: streamStatus,\s*priceObservedAt: acceptedPriceClock,/);
    expect(PAGE).toMatch(/valueKey: homePct === null \? null : `\$\{homePct\}\/\$\{awayPct \?\? ""\}`,\s*terminal: Boolean\(connectionTerminalLabel\),\s*\},\s*Date\.now\(\),/);
    expect(PAGE).toMatch(/const connectionPresentation = presentConnectionStatus\(\s*connectionTrackerRef\.current,\s*\{\s*status: streamStatus,\s*terminalLabel: connectionTerminalLabel,/);
    // The once-a-second re-render the harness stands in for: the countdown tick.
    expect(PAGE).toMatch(/const interval = setInterval\(\(\) => \{\s*const elapsed = Date\.now\(\) - lastRefresh;[\s\S]{0,160}setCountdown\(Math\.ceil\(remaining \/ 1000\)\);\s*\}, 100\);/);
    // The status is never fed the raw frame.
    expect(PAGE).not.toMatch(/stepConnectionTracker\([^)]*liveFrame/);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
const RECEIPTS = ["Updated", "Connected · no change", "No change", "Updates resumed"];

describe("#10200 quiet is quiet: open, heartbeat-only, publication silence", () => {
  it("connecting → connected and waiting; heartbeats earn nothing; silence reads checking; the clock never restamps", async () => {
    const page = await mountHeldPage(held({ p: 0.6, at: T(0) }));
    expect(page.read().label).toBe("Connecting");
    await page.emit("open");
    expect(page.read()).toMatchObject({ pct: "60", label: "Connected · waiting", clock: T(0) });

    // Heartbeats every 20s, the controller ticking on its own interval.
    for (let s = 0; s < DATA_SILENCE_TIMEOUT_MS + 20_000; s += 20_000) {
      await page.advance(20_000);
      await page.emit("heartbeat");
      page.read();
    }
    expect(page.read()).toMatchObject({ pct: "60", label: "Connected · checking", clock: T(0) });
    // Not one receipt across the whole quiet spell, and the socket stayed open.
    expect(page.seen.filter((l) => RECEIPTS.includes(l))).toEqual([]);
    expect(page.stream().closed).toBe(false);
    page.unmount();
  });

  it("an open socket without any observation is never \"Updated\"", async () => {
    const page = await mountHeldPage(held({ p: 0.6, at: T(0) }));
    await page.emit("open");
    await page.advance(TICK_INTERVAL_MS * 3);
    expect(page.read().label).toBe("Connected · waiting");
    page.unmount();
  });
});

describe("#10200 receipts come from adoption, never from arrival", () => {
  it("an accepted change: the hero moves and the status reads Updated, briefly", async () => {
    const page = await mountHeldPage(held({ p: 0.6, at: T(0) }));
    await page.emit("open");
    jest.setSystemTime(T0 + 5_000);
    await page.emit("probability", frame({ p: 0.64, at: T(5) }));
    expect(page.read()).toMatchObject({ pct: "64", label: "Updated", clock: T(5) });
    await page.advance(CONNECTION_FEEDBACK_MS);
    expect(page.read()).toMatchObject({ pct: "64", label: "Connected · waiting" });
    page.unmount();
  });

  it("an accepted newer observation with the same printed value reads no change — no motion", async () => {
    const page = await mountHeldPage(held({ p: 0.6, at: T(0) }));
    await page.emit("open");
    await page.emit("probability", frame({ p: 0.601, at: T(5) }));
    expect(page.read()).toMatchObject({ pct: "60", label: "Connected · no change", clock: T(5) });
    page.unmount();
  });

  it("a STALE frame the page refuses earns nothing; a DUPLICATE of the held clock earns nothing", async () => {
    const page = await mountHeldPage(held({ p: 0.6, at: T(10) }));
    await page.emit("open");
    await page.emit("probability", frame({ p: 0.7, at: T(4) }));
    expect(page.read()).toMatchObject({ pct: "60", label: "Connected · waiting", clock: T(10) });
    await page.emit("probability", frame({ p: 0.6, at: T(10) }));
    expect(page.read()).toMatchObject({ pct: "60", label: "Connected · waiting", clock: T(10) });
    expect(page.seen.filter((l) => RECEIPTS.includes(l))).toEqual([]);
    page.unmount();
  });

  it("a p=null invalidation earns its receipt only when the refetched fold is ADOPTED", async () => {
    const page = await mountHeldPage(held({ p: 0.6, at: T(0) }));
    await page.emit("open");
    const before = page.net.requests.length;
    await page.emit("probability", frame({ p: null, at: T(6) }));
    // The frame arrived and asked for a refetch; nothing was adopted yet.
    expect(page.net.requests.length).toBe(before + 1);
    expect(page.read()).toMatchObject({ pct: "60", label: "Connected · waiting", clock: T(0) });
    await page.resolveLast(held({ p: 0.66, at: T(6) }));
    expect(page.read()).toMatchObject({ pct: "66", label: "Updated", clock: T(6) });
    page.unmount();
  });

  it("a frame for another event is not this page's", async () => {
    const page = await mountHeldPage(held({ p: 0.6, at: T(0) }));
    await page.emit("open");
    await page.emit("probability", frame({ id: B, p: 0.9, at: T(9) }));
    expect(page.read()).toMatchObject({ pct: "60", label: "Connected · waiting", clock: T(0) });
    page.unmount();
  });
});

describe("#10200 interruption, reopen, recovery", () => {
  it("a real error reads interrupted; the reopen alone reads connected; the next ADOPTED observation reads resumed", async () => {
    const page = await mountHeldPage(held({ p: 0.6, at: T(0) }));
    await page.emit("open");
    page.stream().readyState = 0; // EventSource is retrying by itself
    await page.emit("error");
    expect(page.read()).toMatchObject({
      label: "Updates interrupted · reconnecting",
      announcement: "Updates interrupted · reconnecting",
    });

    await page.emit("open");
    // The socket is back; nothing new has been adopted, so nothing is claimed current.
    expect(page.read()).toMatchObject({ pct: "60", label: "Connected · waiting", clock: T(0) });

    // An unchanged value still earns the recovery — it is a new observation.
    await page.emit("probability", frame({ p: 0.6, at: T(8) }));
    expect(page.read()).toMatchObject({ pct: "60", label: "Updates resumed", announcement: "Updates resumed", clock: T(8) });
    page.unmount();
  });
});

describe("#10200 the server's scheduled rollover (Sol's review of 0b89d9a8b5)", () => {
  it("reads a still Connecting while the old socket is closed, never interrupted, and connected only once the next one opens", async () => {
    const page = await mountHeldPage(held({ p: 0.6, at: T(0) }));
    await page.emit("open");
    const old = page.stream();
    await page.emit("reconnect");
    expect(old.closed).toBe(true);
    expect(page.read()).toMatchObject({ pct: "60", label: "Connecting", announcement: "", clock: T(0) });
    // The hook's own interval opens the replacement after the backoff.
    await page.advance(TICK_INTERVAL_MS * 2);
    expect(page.stream()).not.toBe(old);
    expect(page.read().label).toBe("Connecting");
    await page.emit("open");
    expect(page.read()).toMatchObject({ pct: "60", label: "Connected · waiting", clock: T(0) });
    expect(page.seen).not.toContain("Updates interrupted · reconnecting");
    expect(page.seen.filter((l) => RECEIPTS.includes(l))).toEqual([]);
    page.unmount();
  });
});

describe("#10200 the finish", () => {
  it("the server's close reads checking; the adopted final reads Finished; nothing after it moves", async () => {
    const page = await mountHeldPage(held({ p: 0.6, at: T(0) }));
    await page.emit("open");
    const stream = page.stream();
    await page.emit("closed");
    expect(page.read().label).toBe("Checking for updates");

    await page.poll();
    await page.resolveLast(held({ p: 1, at: T(30), status: "completed" }));
    expect(page.read()).toMatchObject({ label: "Finished", announcement: "Finished" });

    // A late frame on the old transport, then a late REST read with a newer
    // clock: the finish overrides both.
    await act(async () => { stream.emit("probability", frame({ p: 0.3, at: T(40) })); });
    await settle();
    await page.poll();
    await page.resolveLast(held({ p: 1, at: T(45), status: "completed" }));
    expect(page.read().label).toBe("Finished");
    expect(page.seen.slice(page.seen.indexOf("Finished"))).not.toEqual(expect.arrayContaining(RECEIPTS));
    page.unmount();
  });
});

describe("#10200 navigation resets", () => {
  it("event B never inherits event A's interruption, receipt or transport word", async () => {
    const page = await mountHeldPage(held({ id: A, p: 0.6, at: T(0) }));
    await page.emit("open");
    page.stream().readyState = 0;
    await page.emit("error");
    expect(page.read().label).toBe("Updates interrupted · reconnecting");
    const streamA = page.stream();

    await page.navigate(B);
    await page.resolveLast(held({ id: B, p: 0.3, at: T(1) }));
    expect(streamA.closed).toBe(true);
    expect(page.stream()).not.toBe(streamA);
    expect(page.read()).toMatchObject({ pct: "30", label: "Connecting", announcement: "" });

    await page.emit("open");
    expect(page.read().label).toBe("Connected · waiting");
    // B's first new observation is an ordinary receipt — the interruption was A's.
    await page.emit("probability", frame({ id: B, p: 0.31, at: T(3) }));
    expect(page.read()).toMatchObject({ pct: "31", label: "Updated" });
    page.unmount();
  });
});
