/**
 * #10090 — a committed price frame reaches the page in ONE render, with the
 * headline and the chart in the same commit.
 *
 * The page writes each frame to its SWR cache from `onFrame` (React renders a
 * store update synchronously), while the hook keeps the frame and the chart's
 * received points in ordinary state (rendered a scheduler task later). Before
 * the hook delivered a frame inside one `flushSync`, every frame rendered the
 * whole event page twice: the headline committed first, and the chart caught
 * up a task later — a paint could fall between them.
 *
 * WHAT IS REAL: react-dom over `helpers/minimalDom`, the installed `swr`, and
 * the real `useLiveEventStream` → `createLiveStreamController` over a mocked
 * EventSource. Frames are emitted OUTSIDE `act`, as a browser delivers them:
 * `act` batches everything to its own end and would hide the second render.
 */
import "../helpers/minimalDom";
import React, { useLayoutEffect } from "react";
import { createRoot } from "react-dom/client";
import useSWR, { SWRConfig } from "swr";

import { useLiveEventStream } from "../../hooks/useLiveEventStream";
import { createLiveStreamController, type StreamHandle } from "../../lib/liveStreamController";

type Listener = (event: unknown) => void;
class HookSource {
  static all: HookSource[] = [];
  readyState = 1;
  listeners = new Map<string, Listener[]>();
  constructor() { HookSource.all.push(this); }
  addEventListener(name: string, listener: Listener) {
    this.listeners.set(name, [...(this.listeners.get(name) ?? []), listener]);
  }
  close() { this.readyState = 2; }
  emit(name: string, data?: string) { for (const l of this.listeners.get(name) ?? []) l({ data }); }
}

const ID = 14632820;
const frame = (p: number, rev: number) => JSON.stringify({
  event_id: ID, p, source: "kalshi", source_value: p, status: "live",
  updated_at: new Date(Date.UTC(2026, 9, 29, 16, 0, rev)).toISOString(), rev: { [ID]: rev },
});

const commits: { headline: number; chart: number }[] = [];
function Page() {
  const { data, mutate } = useSWR<{ p: number }>(["event", ID], null, { fallbackData: { p: 0.5 } });
  const { chartPoints } = useLiveEventStream(ID, true, (f) => {
    // The page's own write: the frame IS the new value, no revalidation.
    void mutate(prev => ({ ...prev, p: f.p as number }), { revalidate: false });
  });
  useLayoutEffect(() => {
    commits.push({ headline: data!.p, chart: chartPoints.length });
  });
  return null;
}

const actEnvironment = globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT?: boolean; EventSource?: unknown };
const originalAct = actEnvironment.IS_REACT_ACT_ENVIRONMENT;
const originalEventSource = actEnvironment.EventSource;
beforeAll(() => {
  actEnvironment.IS_REACT_ACT_ENVIRONMENT = false;
  actEnvironment.EventSource = HookSource;
});
afterAll(() => {
  actEnvironment.IS_REACT_ACT_ENVIRONMENT = originalAct;
  actEnvironment.EventSource = originalEventSource;
});

const settle = () => new Promise(resolve => setTimeout(resolve, 20));

test("each committed frame renders once, headline and chart in the same commit", async () => {
  const root = createRoot(document.createElement("div") as unknown as Element);
  root.render(<SWRConfig value={{ provider: () => new Map() }}><Page /></SWRConfig>);
  try {
    await settle();
    const stream = HookSource.all.at(-1)!;
    stream.emit("open");
    await settle();

    for (const [p, rev] of [[0.51, 11], [0.53, 12], [0.52, 13]] as const) {
      const chartBefore = commits.at(-1)!.chart;
      commits.length = 0;
      stream.emit("probability", frame(p, rev));
      // Committed before the transport callback returns: nothing waits for a
      // microtask or a scheduler task, so no paint can show half the frame.
      expect(commits).toEqual([{ headline: p, chart: chartBefore + 1 }]);
      await settle();
      // And nothing renders the same frame a second time afterwards.
      expect(commits).toHaveLength(1);
    }
  } finally {
    root.unmount();
  }
});

describe("controller: `deliver` wraps one committed frame's delivery", () => {
  const harness = (deliver?: (run: () => void) => void) => {
    let handle: HookSource | null = null;
    const seen: string[] = [];
    // Every callback says whether it ran inside `deliver`.
    let depth = 0;
    const note = (what: string) => seen.push(depth ? `${what} (inside)` : what);
    const controller = createLiveStreamController({
      open: () => (handle = new HookSource()) as unknown as StreamHandle,
      now: () => 0,
      onFrame: f => note(`frame:${f.p}`),
      onDeliveringChange: d => note(`delivering:${d}`),
      onStatusChange: s => note(`status:${s}`),
      deliver: deliver && (run => { depth += 1; try { deliver(run); } finally { depth -= 1; } }),
    });
    controller.start();
    return { seen, emit: (name: string, data?: string) => handle!.emit(name, data), controller };
  };

  test("the frame, its delivering flip and its status change all run inside it", () => {
    const h = harness(run => run());
    h.emit("heartbeat");
    h.seen.length = 0;
    h.emit("probability", frame(0.6, 21));
    expect(h.seen).toEqual(["frame:0.6 (inside)", "delivering:true (inside)", "status:open (inside)"]);
  });

  test("a delivery that throws still leaves push delivering", () => {
    const h = harness(() => { throw new Error("render failed"); });
    expect(() => h.emit("probability", frame(0.6, 22))).toThrow("render failed");
    expect(h.seen).toEqual(["status:connecting", "delivering:true", "status:open"]);
    expect(h.controller.state.delivering).toBe(true);
    expect(h.controller.state.status).toBe("open");
  });

  test("omitted, the delivery simply runs", () => {
    const h = harness();
    h.emit("probability", frame(0.6, 23));
    expect(h.seen).toEqual(["status:connecting", "frame:0.6", "delivering:true", "status:open"]);
  });

  test("previews, controls and heartbeats never go through it", () => {
    let calls = 0;
    const h = harness(run => { calls += 1; run(); });
    h.emit("open");
    h.emit("heartbeat");
    h.emit("preview_v3", "{}");
    h.emit("fold_preview_floor", "{}");
    h.emit("reconcile", "{}");
    h.emit("resync", '{"generation":1}');
    expect(calls).toBe(0);
    h.emit("folded_probability", frame(0.6, 24));
    expect(calls).toBe(1);
  });
});
