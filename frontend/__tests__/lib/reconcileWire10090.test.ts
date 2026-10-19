/**
 * #10090 G1 — the `reconcile` control on the wire (the real controller), and
 * the scheduler rail that keeps an owed floor alive with no retry cap.
 */
import {
  DATA_SILENCE_TIMEOUT_MS,
  TICK_INTERVAL_MS,
  createLiveStreamController,
  type LiveTransportStatus,
  type StreamHandle,
} from "@/lib/liveStreamController";
import { createFoldedRefetchScheduler } from "@/lib/foldedRefetchScheduler";
import type { ReconcileControl } from "@/lib/reconcileControl";

class FakeSource implements StreamHandle {
  readyState = 1;
  private listeners = new Map<string, ((event: unknown) => void)[]>();
  addEventListener(type: string, listener: (event: unknown) => void) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
  }
  close() { this.readyState = 2; }
  emit(type: string, data?: string) {
    for (const listener of this.listeners.get(type) ?? []) listener(data === undefined ? {} : { data });
  }
}

function harness() {
  let clock = 1_000_000;
  const sources: FakeSource[] = [];
  const controls: ReconcileControl[] = [];
  const frames: unknown[] = [];
  const recoveries: number[] = [];
  const delivering: boolean[] = [];
  const statuses: LiveTransportStatus[] = [];
  const controller = createLiveStreamController({
    open: () => { const source = new FakeSource(); sources.push(source); return source; },
    now: () => clock,
    onFrame: (frame) => frames.push(frame),
    onDeliveringChange: (value) => delivering.push(value),
    onStatusChange: (status) => statuses.push(status),
    onRecovery: (ordinal) => recoveries.push(ordinal),
    onReconcile: (control) => controls.push(control),
  });
  return {
    controller, sources, controls, frames, recoveries, delivering, statuses,
    advance(ms: number) { clock += ms; },
  };
}

const CONTROL = JSON.stringify({ event_id: 15332323, custody_id: "owed-1", removal_rev: { 15332402: 1129 } });

describe("#10090 the controller's reconcile listener", () => {
  it("hands a valid control to the page and nothing else: no frame, recovery, delivery or status change", () => {
    const h = harness();
    h.controller.start();
    h.sources[0].emit("open");
    const before = { delivering: [...h.delivering], statuses: [...h.statuses] };
    h.sources[0].emit("reconcile", CONTROL);
    expect(h.controls).toEqual([{ eventId: 15332323, custodyId: "owed-1", floor: { 15332402: 1129 } }]);
    expect(h.frames).toEqual([]);
    expect(h.recoveries).toEqual([]);
    expect(h.delivering).toEqual(before.delivering);
    expect(h.statuses).toEqual(before.statuses);
  });

  it("controls alone do not postpone the data-silence fallback", () => {
    const h = harness();
    h.controller.start();
    h.sources[0].emit("open");
    for (let at = 0; at <= DATA_SILENCE_TIMEOUT_MS; at += TICK_INTERVAL_MS) {
      h.sources[0].emit("heartbeat", "{}");
      h.sources[0].emit("reconcile", CONTROL);
      h.advance(TICK_INTERVAL_MS);
      h.controller.tick();
    }
    expect(h.delivering.at(-1)).toBe(false);
    expect(h.statuses.at(-1)).toBe("quiet");
    expect(h.controls.length).toBeGreaterThan(10);
  });

  it("a malformed or price-shaped control is dropped; the stream stays open", () => {
    const h = harness();
    h.controller.start();
    h.sources[0].emit("open");
    h.sources[0].emit("reconcile", "{");
    h.sources[0].emit("reconcile", JSON.stringify({ event_id: 15332323, custody_id: "x", removal_rev: { 1: 1 }, p: 0.4 }));
    expect(h.controls).toEqual([]);
    expect(h.sources[0].readyState).toBe(1);
  });

  it("a control on a replaced socket is ignored; the new socket's own control is delivered", () => {
    const h = harness();
    h.controller.start();
    const first = h.sources[0];
    first.emit("open");
    first.emit("reconnect", JSON.stringify({ reason: "max_age" }));
    h.advance(1_000);
    h.controller.tick();
    expect(h.sources).toHaveLength(2);
    first.emit("reconcile", CONTROL);
    expect(h.controls).toHaveLength(0);
    h.sources[1].emit("open");
    h.sources[1].emit("reconcile", CONTROL);
    expect(h.controls).toHaveLength(1);
  });

  it("resync keeps its own generation rule: a reconcile does not consume or advance it", () => {
    const h = harness();
    h.controller.start();
    h.sources[0].emit("open");
    h.sources[0].emit("reconcile", CONTROL);
    h.sources[0].emit("resync", JSON.stringify({ generation: 1 }));
    expect(h.recoveries).toEqual([1]);
    expect(h.controls).toHaveLength(1);
  });
});

describe("#10090 the scheduler keeps an owed floor alive with no retry cap", () => {
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => jest.useRealTimers());
  const flush = async () => { for (let i = 0; i < 10; i += 1) await Promise.resolve(); };

  it("retries 1, 2, 4 … s apart, capped, one read in flight, until paid", async () => {
    let owed = true;
    const starts: number[] = [];
    let active = 0;
    let maxActive = 0;
    const scheduler = createFoldedRefetchScheduler(async () => {
      starts.push(Date.now());
      active += 1; maxActive = Math.max(maxActive, active);
      await Promise.resolve();
      active -= 1;
      throw new Error("offline");
    }, 1000, Date.now, undefined, { owed: () => owed, delayMs: (n) => Math.min(8000, 1000 * 2 ** (n - 1)) });
    const t0 = Date.now();
    scheduler.request();
    for (let i = 0; i < 80; i += 1) { await flush(); jest.advanceTimersByTime(500); }
    const gaps = starts.slice(1).map((at, i) => at - starts[i]);
    expect(gaps.slice(0, 6)).toEqual([1000, 2000, 4000, 8000, 8000, 8000]);
    expect(starts[0]).toBe(t0);
    expect(maxActive).toBe(1);
    const count = starts.length;
    owed = false;
    for (let i = 0; i < 40; i += 1) { await flush(); jest.advanceTimersByTime(500); }
    expect(starts.length).toBe(count);
    scheduler.cancel();
  });

  it("a fresh request restarts the ladder instead of waiting out a long backoff", async () => {
    const starts: number[] = [];
    const scheduler = createFoldedRefetchScheduler(async () => { starts.push(Date.now()); }, 1000, Date.now,
      undefined, { owed: () => true, delayMs: () => 30_000 });
    scheduler.request();
    await flush();
    jest.advanceTimersByTime(2000);
    scheduler.request();
    await flush();
    expect(starts).toHaveLength(2);
    scheduler.cancel();
  });

  it("cancel retires an armed backoff", async () => {
    let calls = 0;
    const scheduler = createFoldedRefetchScheduler(async () => { calls += 1; }, 1000, Date.now,
      undefined, { owed: () => true, delayMs: () => 1000 });
    scheduler.request();
    await flush();
    scheduler.cancel();
    jest.advanceTimersByTime(60_000);
    await flush();
    expect(calls).toBe(1);
  });
});
