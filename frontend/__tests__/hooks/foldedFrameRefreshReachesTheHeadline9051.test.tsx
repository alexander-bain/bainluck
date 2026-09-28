/**
 * #9051 — after a raw-row frame invalidates a FOLDED headline, does the
 * already-open page reach the authoritative folded value, even when no
 * further frame arrives?
 *
 * MOUNTED, not modelled. `HeldEvent` below is the event page's held-event
 * wiring, assembled from the page's own exports and its own lines: the real
 * `useSWR` (installed swr, the page's key shape, `fetchEventWithLiveFrame` as
 * the fetcher with all four of the page's getters, `makeEventRefreshInterval`
 * as the cadence), the real `createFoldedRefetchScheduler`, the real
 * `frameInvalidatesFoldedBlend` / `applyLiveFrame` / `edgeInvalidatesHeldBlend`
 * / `adoptNewerBlendEdge`, and the page's two effects (push, history edge) as
 * `app/events/[id]/page.tsx` writes them. The page is a default export with no
 * seam, so those effect bodies are carried here and PINNED: the structural test
 * at the top reads the page and fails if the lines it carries are no longer
 * the page's. Network is a list of deferred promises the test resolves in the
 * order it chooses; time is fake (`jest.useFakeTimers`, `Date.now` included).
 *
 * The page's render tree is not mounted: it is 3,000 lines of chart and rail
 * components that need a browser. The question here is answered by the cache
 * the hero reads, which the harness prints as text. The DOM is
 * `helpers/minimalDom.ts` — enough for react-dom to mount one text node, no
 * jsdom, nothing added to package.json.
 *
 * ═══ WHAT THIS PINS (found at 95bcc174, repaired by ux at e24de556a) ═══
 *
 * At 95bcc174 the push effect, on a frame the folded hero refused, started
 * `refreshEvent()` and then in the same tick wrote the frame through
 * `refreshEvent(applyLiveFrame, {revalidate: false})` — a no-op write, and a
 * MUTATION to swr. swr@2.4.1 discards a revalidation whose request started
 * before a later mutation began (`dist/index/index.js`, "other mutation(s)
 * overlapped with the current revalidation" → `onDiscarded`), so the
 * authoritative refresh completed and was thrown away, on every frame, and the
 * page held the pre-removal value until the stream-connected 120 s poll. A
 * second refused frame inside the 5 s floor, followed by silence, was never
 * refetched at all. `mechanism` proves the swr behaviour on swr alone; the
 * cases below prove the page's wiring no longer trips it. On the 95bcc174
 * wiring this suite reads 3 failed / 6 passed (case 1, both of case 2).
 */

import "../helpers/minimalDom";
import React, { act, useEffect, useMemo, useRef, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import fs from "fs";
import path from "path";
import useSWR, { SWRConfig } from "swr";
import { applyLiveFrame, frameInvalidatesFoldedBlend, makeEventRefreshInterval } from "../../lib/eventLivePush";
import { fetchEventWithLiveFrame } from "../../lib/reconcileEventPoll";
import { createFoldedRefetchScheduler } from "../../lib/foldedRefetchScheduler";
import {
  adoptNewerBlendEdge,
  edgeInvalidatesHeldBlend,
  servedBlendEdgeObservation,
  type BlendEdgeObservation,
} from "../../lib/blendObservationClock";
import type { LiveFrame } from "../../hooks/useLiveEventStream";

// ── the page's constants, read from the page so they cannot drift ───────────
const PAGE = fs.readFileSync(path.join(__dirname, "../../app/events/[id]/page.tsx"), "utf8");
const constant = (name: string) => Number(PAGE.match(new RegExp(`const ${name} = (\\d+)`))![1]);
const LIVE_REFRESH_INTERVAL = constant("LIVE_REFRESH_INTERVAL");
const SCHEDULED_REFRESH_INTERVAL = constant("SCHEDULED_REFRESH_INTERVAL");
const FOLDED_FRAME_REFETCH_MS = constant("FOLDED_FRAME_REFETCH_MS");

// ── deferred network ────────────────────────────────────────────────────────
type Held = {
  id: number;
  status: string;
  home_score: number | null;
  away_score: number | null;
  hero_probability: number;
  hero_probability_away: number;
  hero_probability_source: string;
  hero_probability_observed_at: string;
  blend_fold_revision: Record<string, number>;
  win_probability_sources: Record<string, { value: number; updated_at: string }>;
};

class Deferred {
  promise: Promise<Held>;
  resolve!: (v: Held) => void;
  constructor() {
    this.promise = new Promise((r) => { this.resolve = r; });
  }
}

const EVENT_ID = 14781697;
const T = (s: number) => new Date(Date.UTC(2026, 8, 27, 20, 0, s)).toISOString();

function folded(args: {
  p: number; observedAt: string; revision: Record<string, number>;
  score?: [number, number]; sources?: Record<string, { value: number; updated_at: string }>;
}): Held {
  return {
    id: EVENT_ID,
    status: "live",
    home_score: args.score?.[0] ?? 3,
    away_score: args.score?.[1] ?? 1,
    hero_probability: args.p,
    hero_probability_away: 1 - args.p,
    hero_probability_source: "blend",
    hero_probability_observed_at: args.observedAt,
    blend_fold_revision: args.revision,
    win_probability_sources: args.sources ?? {
      kalshi: { value: args.p + 0.02, updated_at: T(10) },
      polymarket: { value: args.p - 0.02, updated_at: args.observedAt },
    },
  };
}

/** A pushed frame: one row's write, `rev` keyed by that row (PR #9078's `build_frame`). */
function frame(args: { rev: number; row?: string; p: number; at: string }): LiveFrame {
  return {
    event_id: EVENT_ID,
    p: args.p,
    source: "kalshi",
    source_value: args.p,
    updated_at: args.at,
    status: "live",
    rev: { [args.row ?? "100"]: args.rev },
  };
}

// ── the harness: the page's held-event wiring ───────────────────────────────
type Net = { requests: Deferred[]; landed: Held[]; discarded: number };

function HeldEvent(props: { net: Net; liveFrame: LiveFrame | null; servedHistory: unknown }) {
  const { net, liveFrame, servedHistory } = props;
  const eventId = EVENT_ID;
  const streamConnectedRef = useRef(true); // the stream is delivering: the 120 s poll stands down
  const latestLiveFrameRef = useRef<LiveFrame | null>(null);
  const latestBlendEdgeRef = useRef<BlendEdgeObservation | null>(null);
  const heldEventRef = useRef<Held | undefined>(undefined);
  const eventPollInterval = useMemo(
    () => makeEventRefreshInterval(streamConnectedRef, {
      live: LIVE_REFRESH_INTERVAL,
      scheduled: SCHEDULED_REFRESH_INTERVAL,
    }),
    [],
  );
  const { data: event, mutate: refreshEvent } = useSWR(
    ["event", eventId],
    () => fetchEventWithLiveFrame(
      () => { const d = new Deferred(); net.requests.push(d); return d.promise; },
      () => latestLiveFrameRef.current,
      () => latestBlendEdgeRef.current,
      () => heldEventRef.current,
    ),
    {
      refreshInterval: eventPollInterval,
      onSuccess: (data) => { net.landed.push(data); },
      onDiscarded: () => { net.discarded += 1; },
    },
  );
  heldEventRef.current = event;
  const refreshEventRef = useRef(refreshEvent);
  refreshEventRef.current = refreshEvent;
  const [foldedRefetch] = useState(() => createFoldedRefetchScheduler(
    () => { void refreshEventRef.current(); }, FOLDED_FRAME_REFETCH_MS,
  ));
  useEffect(() => () => foldedRefetch.cancel(), [foldedRefetch]);

  // ── app/events/[id]/page.tsx — the push effect, as the page writes it ──────
  useEffect(() => {
    if (!liveFrame || liveFrame.event_id !== eventId) return;
    if (frameInvalidatesFoldedBlend(heldEventRef.current, liveFrame)) {
      foldedRefetch.request();
      return;
    }
    // #9294: contributor notifications invalidate the fold without carrying
    // an adoptable price. Never install one as a price or replay it on a poll.
    if (liveFrame.p === null || liveFrame.p === undefined) return;
    latestLiveFrameRef.current = liveFrame;
    const frame = { ...liveFrame, p: liveFrame.p };
    refreshEvent(
      (prev) => applyLiveFrame(prev, frame),
      { revalidate: false },
    );
  }, [liveFrame, refreshEvent, eventId, foldedRefetch]);

  // ── app/events/[id]/page.tsx — the history-edge effect, as the page writes it
  useEffect(() => {
    const edge = servedBlendEdgeObservation(servedHistory as Parameters<typeof servedBlendEdgeObservation>[0]);
    latestBlendEdgeRef.current = edge;
    if (!edge) return;
    if (edgeInvalidatesHeldBlend(heldEventRef.current, edge)) {
      foldedRefetch.request();
      return;
    }
    refreshEvent((prev) => adoptNewerBlendEdge(prev, edge), { revalidate: false });
  }, [servedHistory, refreshEvent, foldedRefetch]);

  if (!event) return <>loading</>;
  return (
    <>
      {`${event.hero_probability.toFixed(2)}|${JSON.stringify(event.blend_fold_revision)}|${event.home_score}-${event.away_score}|${event.status}`}
    </>
  );
}

// ── mount / drive helpers ───────────────────────────────────────────────────
async function settle() {
  // The swr revalidation chain is several microtask hops (fetch → reconcile →
  // setCache); no timers are involved, so a handful of turns drains it.
  await act(async () => {
    for (let i = 0; i < 12; i += 1) await Promise.resolve();
  });
}

const doc = document as unknown as { createElement: (t: string) => Element; body: { appendChild: (c: unknown) => void } };

async function mountHeldEvent() {
  const net: Net = { requests: [], landed: [], discarded: 0 };
  const container = doc.createElement("div");
  doc.body.appendChild(container);
  const root: Root = createRoot(container);
  let current: { liveFrame: LiveFrame | null; servedHistory: unknown } = { liveFrame: null, servedHistory: null };
  const render = () => {
    root.render(
      <SWRConfig value={{ provider: () => new Map() }}>
        <HeldEvent net={net} liveFrame={current.liveFrame} servedHistory={current.servedHistory} />
      </SWRConfig>,
    );
  };
  await act(async () => { render(); });
  await settle();
  return {
    net,
    text: () => container.textContent,
    async deliver(liveFrame: LiveFrame) {
      current = { ...current, liveFrame };
      await act(async () => { render(); });
      await settle();
    },
    async serveHistory(servedHistory: unknown) {
      current = { ...current, servedHistory };
      await act(async () => { render(); });
      await settle();
    },
    async resolve(i: number, held: Held) {
      net.requests[i].resolve(held);
      await settle();
    },
    async advance(ms: number) {
      await act(async () => { jest.advanceTimersByTime(ms); });
      await settle();
    },
    unmount: () => act(() => { root.unmount(); }),
  };
}

beforeEach(() => {
  jest.useFakeTimers();
  jest.setSystemTime(new Date(T(20)));
});
afterEach(() => {
  jest.useRealTimers();
});

// ─────────────────────────────────────────────────────────────────────────────
describe("structural pin: the harness carries the page's own wiring", () => {
  it("app/events/[id]/page.tsx still reads as the lines HeldEvent mounts", () => {
    // The fetcher, with the held-event getter the poll reconciles against.
    expect(PAGE).toMatch(/fetchEventWithLiveFrame\(\s*\(\) => fetchEvent\(eventId, heldEventRef\.current\?\.status === "live"\),\s*\(\) => latestLiveFrameRef\.current,\s*\(\) => latestBlendEdgeRef\.current,\s*\(\) => heldEventRef\.current,/);
    expect(PAGE).toMatch(/refreshInterval: eventPollInterval/);
    // The scheduler, built once, torn down with the page.
    expect(PAGE).toMatch(/createFoldedRefetchScheduler\(\s*\(\) => \{ void refreshEventRef\.current\(\); \}, FOLDED_FRAME_REFETCH_MS,/);
    expect(PAGE).toMatch(/useEffect\(\(\) => \(\) => foldedRefetch\.cancel\(\), \[foldedRefetch\]\)/);
    // The push effect: a refused frame requests a refetch and writes NOTHING.
    expect(PAGE).toMatch(/if \(frameInvalidatesFoldedBlend\(heldEventRef\.current, liveFrame\)\) \{\s*foldedRefetch\.request\(\);\s*return;\s*\}/);
    expect(PAGE).toMatch(/\(prev\) => applyLiveFrame\(prev, frame\),/);
    expect(PAGE).toMatch(/\}, \[liveFrame, refreshEvent, eventId, foldedRefetch\]\);/);
    expect(PAGE.indexOf("frameInvalidatesFoldedBlend(heldEventRef.current, liveFrame)"))
      .toBeLessThan(PAGE.indexOf("if (liveFrame.p === null"));
    // The history effect: an incomparable edge requests a refetch and writes NOTHING.
    expect(PAGE).toMatch(/if \(edgeInvalidatesHeldBlend\(heldEventRef\.current, edge\)\) \{\s*foldedRefetch\.request\(\);\s*return;\s*\}/);
    expect(PAGE).toMatch(/refreshEvent\(\(prev\) => adoptNewerBlendEdge\(prev, edge\), \{ revalidate: false \}\);/);
    // Exactly one place applies a frame, and it is guarded: the 95bcc174 shape
    // (`void refreshEvent();` beside the frame write) is gone.
    expect(PAGE.match(/applyLiveFrame\(prev, frame\)/g)).toHaveLength(1);
    expect(PAGE).not.toMatch(/foldedRefetchAtRef/);
  });
});

describe("mechanism: the installed swr discards a revalidation that a same-tick no-op mutation overlaps", () => {
  it("mutate() then mutate(prev => prev, {revalidate:false}) throws the fetched value away", async () => {
    // swr alone — no page code. This is why the page must not write the cache
    // in the tick it asks for a refetch, as a fact on swr@2.4.1 as installed.
    const requests: Deferred[] = [];
    let discarded = 0;
    let mutateRef: ((...a: unknown[]) => unknown) | null = null;
    function Probe() {
      const { data, mutate } = useSWR(
        "probe",
        () => { const d = new Deferred(); requests.push(d); return d.promise; },
        { onDiscarded: () => { discarded += 1; } },
      );
      mutateRef = mutate as (...a: unknown[]) => unknown;
      return <>{data ? String(data.hero_probability) : "loading"}</>;
    }
    const container = doc.createElement("div");
    const root = createRoot(container);
    await act(async () => {
      root.render(<SWRConfig value={{ provider: () => new Map() }}><Probe /></SWRConfig>);
    });
    await settle();
    await act(async () => { requests[0].resolve(folded({ p: 0.6, observedAt: T(12), revision: { "100": 5 } })); });
    await settle();
    expect(container.textContent).toBe("0.6");

    // The page's sequence at 95bcc174, verbatim in shape.
    act(() => {
      void mutateRef!();
      void mutateRef!((prev: unknown) => prev, { revalidate: false });
    });
    expect(requests).toHaveLength(2);
    await act(async () => { requests[1].resolve(folded({ p: 0.4, observedAt: T(12), revision: { "100": 6 } })); });
    await settle();

    expect(discarded).toBe(1);
    expect(container.textContent).toBe("0.6"); // the authoritative 0.4 never reached the cache
    act(() => { root.unmount(); });
  });
});

describe("#9051 case 1: a folded-frame invalidation reaches the authoritative folded headline", () => {
  it("60% folded → raw-row frame → the real refresh's 40% lands with its vector, score kept", async () => {
    const page = await mountHeldEvent();
    expect(page.net.requests).toHaveLength(1);
    await page.resolve(0, folded({ p: 0.6, observedAt: T(12), revision: { "100": 5, "101": 3 } }));
    expect(page.text()).toBe('0.60|{"100":5,"101":3}|3-1|live');

    // A write to row 100 (the canonical) that the folded hero cannot take.
    await page.deliver(frame({ rev: 6, p: 0.55, at: T(16) }));
    expect(page.net.requests).toHaveLength(2); // the folded detail refresh was requested
    expect(page.text()).toBe('0.60|{"100":5,"101":3}|3-1|live'); // and the raw frame did not land

    // The authoritative fold: 40%, paired with the newer vector, dated by an
    // OLDER surviving quote (T12 < the frame's T16) — the shape a removal leaves.
    await page.resolve(1, folded({
      p: 0.4, observedAt: T(12), revision: { "100": 6, "101": 3 }, score: [3, 2],
    }));

    expect(page.text()).toBe('0.40|{"100":6,"101":3}|3-2|live');
    expect(page.net.landed.map((h) => h.hero_probability)).toEqual([0.6, 0.4]);
    expect(page.net.discarded).toBe(0); // nothing the page wrote threw the refresh away
    await page.unmount();
  });
});

describe("#9051 case 2: the last invalidation of a burst, then silence, still refreshes", () => {
  it("a second frame inside the floor after the first request's snapshot is refetched on a coalesced timer", async () => {
    const page = await mountHeldEvent();
    await page.resolve(0, folded({ p: 0.6, observedAt: T(12), revision: { "100": 5, "101": 3 } }));

    // t=0: frame A → request 1 (its server snapshot is taken now).
    await page.deliver(frame({ rev: 6, p: 0.55, at: T(20) }));
    expect(page.net.requests).toHaveLength(2);

    // t=2s: frame B, inside FOLDED_FRAME_REFETCH_MS. No immediate request …
    await page.advance(2000);
    await page.deliver(frame({ rev: 7, p: 0.5, at: T(22) }));
    expect(page.net.requests).toHaveLength(2);

    // … then the stream goes quiet. Request 1 answers with the snapshot from
    // BEFORE frame B's write.
    await page.resolve(1, folded({ p: 0.45, observedAt: T(12), revision: { "100": 6, "101": 3 } }));
    expect(page.text()).toBe('0.45|{"100":6,"101":3}|3-1|live');

    // Nothing else arrives. By the end of the floor the page must have asked
    // again on its own — no frame, no 120 s poll.
    await page.advance(FOLDED_FRAME_REFETCH_MS - 2000);
    expect(page.net.requests).toHaveLength(3);
    await page.resolve(2, folded({ p: 0.4, observedAt: T(12), revision: { "100": 7, "101": 3 } }));
    expect(page.text()).toBe('0.40|{"100":7,"101":3}|3-1|live');

    // And it asks exactly once: silence past the floor makes no further request
    // short of the poll cadence.
    await page.advance(SCHEDULED_REFRESH_INTERVAL - FOLDED_FRAME_REFETCH_MS - 1000);
    expect(page.net.requests).toHaveLength(3);
    await page.unmount();
  });

  it("discriminating order: the coalesced refresh answers first, the earlier snapshot cannot roll it back", async () => {
    const page = await mountHeldEvent();
    await page.resolve(0, folded({ p: 0.6, observedAt: T(12), revision: { "100": 5, "101": 3 } }));
    await page.deliver(frame({ rev: 6, p: 0.55, at: T(20) }));
    await page.advance(1000);
    await page.deliver(frame({ rev: 7, p: 0.5, at: T(21) }));
    await page.advance(FOLDED_FRAME_REFETCH_MS - 1000);
    expect(page.net.requests).toHaveLength(3);

    // The later request answers first, with the newer fold.
    await page.resolve(2, folded({ p: 0.4, observedAt: T(12), revision: { "100": 7, "101": 3 } }));
    expect(page.text()).toBe('0.40|{"100":7,"101":3}|3-1|live');
    // The earlier request answers late, with the older fold: refused.
    await page.resolve(1, folded({ p: 0.45, observedAt: T(12), revision: { "100": 6, "101": 3 } }));
    expect(page.text()).toBe('0.40|{"100":7,"101":3}|3-1|live');
    await page.unmount();
  });
});

describe("healthy controls", () => {
  it("an ordinary single-row push lands promptly, keeps score and status, requests nothing", async () => {
    const page = await mountHeldEvent();
    await page.resolve(0, folded({ p: 0.6, observedAt: T(12), revision: { "100": 5 } }));
    await page.deliver(frame({ rev: 6, p: 0.58, at: T(16) }));
    expect(page.net.requests).toHaveLength(1);
    expect(page.text()).toBe('0.58|{"100":6}|3-1|live');
    await page.unmount();
  });

  it("a delayed older response cannot roll back accepted provenance", async () => {
    const page = await mountHeldEvent();
    await page.resolve(0, folded({ p: 0.6, observedAt: T(12), revision: { "100": 5 } }));
    // A poll in flight (the 120 s cadence) …
    await page.advance(SCHEDULED_REFRESH_INTERVAL);
    expect(page.net.requests).toHaveLength(2);
    // … a newer frame lands while it flies …
    await page.deliver(frame({ rev: 7, p: 0.62, at: T(20) }));
    expect(page.text()).toBe('0.62|{"100":7}|3-1|live');
    // … and the poll answers with the OLDER write.
    await page.resolve(1, folded({ p: 0.58, observedAt: T(18), revision: { "100": 6 } }));
    expect(page.text()).toBe('0.62|{"100":7}|3-1|live');
    await page.unmount();
  });

  it("a burst of refused frames coalesces refresh work instead of looping", async () => {
    const page = await mountHeldEvent();
    await page.resolve(0, folded({ p: 0.6, observedAt: T(12), revision: { "100": 5, "101": 3 } }));
    // Seven frames, one per second, on a hero that refuses every one of them.
    for (let s = 0; s <= 6; s += 1) {
      if (s > 0) await page.advance(1000);
      await page.deliver(frame({ rev: 6 + s, p: 0.55, at: T(20 + s) }));
    }
    // Leading at t=0, one at the floor (t=5), one trailing for t=6: never one per frame.
    await page.advance(FOLDED_FRAME_REFETCH_MS);
    expect(page.net.requests.length - 1).toBeLessThanOrEqual(3);
    const asked = page.net.requests.length;
    // Silence: nothing more until the poll cadence.
    await page.advance(SCHEDULED_REFRESH_INTERVAL - FOLDED_FRAME_REFETCH_MS * 3);
    expect(page.net.requests).toHaveLength(asked);
    await page.unmount();
  });

  it("a history edge newer than the held fold moves the headline through the same cache", async () => {
    const page = await mountHeldEvent();
    await page.resolve(0, folded({ p: 0.6, observedAt: T(12), revision: { "100": 5, "101": 3 } }));
    await page.serveHistory({
      blend_edge_pinned: true,
      blend_edge_observed_at: T(14),
      blend_edge_fold_revision: { "100": 6, "101": 3 },
      aggregate_line: [{ timestamp: T(14), home_probability: 0.5 }],
    });
    expect(page.net.requests).toHaveLength(1);
    expect(page.text()).toBe('0.50|{"100":6,"101":3}|3-1|live');
    await page.unmount();
  });

  it("an incomparable history edge (a twin left the fold) requests the authoritative detail and writes nothing", async () => {
    const page = await mountHeldEvent();
    await page.resolve(0, folded({ p: 0.6, observedAt: T(12), revision: { "100": 5, "101": 3 } }));
    await page.serveHistory({
      blend_edge_pinned: true,
      blend_edge_observed_at: T(14),
      blend_edge_fold_revision: { "100": 6 },
      aggregate_line: [{ timestamp: T(14), home_probability: 0.5 }],
    });
    expect(page.net.requests).toHaveLength(2);
    expect(page.text()).toBe('0.60|{"100":5,"101":3}|3-1|live');
    await page.resolve(1, folded({ p: 0.5, observedAt: T(14), revision: { "100": 6 } }));
    expect(page.text()).toBe('0.50|{"100":6}|3-1|live'); // the changed fold is adopted whole
    await page.unmount();
  });
});


describe("#9294: contributor invalidations have no adoptable price", () => {
  it("a price-less sibling hint refreshes the held fold without inventing a price", async () => {
    const page = await mountHeldEvent();
    await page.resolve(0, folded({ p: 0.06, observedAt: T(12), revision: { "100": 5, "101": 3 } }));
    const hint: LiveFrame = JSON.parse(JSON.stringify({
      event_id: EVENT_ID, origin_event_id: 101, invalidation: true,
      p: null, source: null, source_value: null, updated_at: T(16),
      status: "live", rev: { "101": 4 },
    }));
    await page.deliver(hint);
    expect(page.net.requests).toHaveLength(2);
    expect(page.text()).toBe('0.06|{"100":5,"101":3}|3-1|live');
    await page.resolve(1, folded({ p: 0.045, observedAt: T(16), revision: { "100": 5, "101": 4 } }));
    expect(page.text()).toBe('0.04|{"100":5,"101":4}|3-1|live');
    expect(page.net.discarded).toBe(0);
    await page.unmount();
  });
});
