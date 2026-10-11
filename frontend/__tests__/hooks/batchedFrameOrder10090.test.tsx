/** #10090: a React batch never hands the page an older price than it received.
 * Real hook + controller, fake EventSource, minimal DOM. The two frames are the
 * production pair from event 14781713 (v5650): rev 12482 then the older 12481
 * in one chunk. Before the fix the headline held 12481 for 1.2 s while the
 * chart, which banks every frame, moved in 21 ms.
 */
import "../helpers/minimalDom";
import React, { act } from "react";
import { createRoot } from "react-dom/client";

import { heldFrameAfter, useLiveEventStream, type LiveFrame } from "../../hooks/useLiveEventStream";
import { applyLiveFrame } from "../../lib/eventLivePush";

class FakeEventSource {
  static all: FakeEventSource[] = [];
  readyState = 0;
  listeners = new Map<string, ((e: unknown) => void)[]>();
  constructor(readonly url: string) { FakeEventSource.all.push(this); }
  addEventListener(k: string, f: (e: unknown) => void) {
    this.listeners.set(k, [...(this.listeners.get(k) ?? []), f]);
  }
  close() { this.readyState = 2; }
  emit(k: string, v?: unknown) {
    if (k === "open") this.readyState = 1;
    for (const f of this.listeners.get(k) ?? []) f(v === undefined ? {} : { data: JSON.stringify(v) });
  }
}
(globalThis as Record<string, unknown>).EventSource = FakeEventSource;

const EID = 14781713;
const older: LiveFrame = {
  event_id: EID, p: 0.234736, source: "betting", source_value: 0.2359,
  rev: { [EID]: 12481 }, updated_at: "2026-10-11T21:50:11.014347+00:00", status: "live",
};
const newer: LiveFrame = {
  event_id: EID, p: 0.23537, source: "polymarket", source_value: 0.225,
  rev: { [EID]: 12482 }, updated_at: "2026-10-11T21:50:11.623585+00:00", status: "live",
};

let seen: ReturnType<typeof useLiveEventStream>;
function Mounted() {
  seen = useLiveEventStream(EID, true);
  return <span>{seen.frame?.p}</span>;
}

async function deliverInOneBatch(frames: LiveFrame[]) {
  const el = document.createElement("div");
  document.body.appendChild(el);
  const root = createRoot(el);
  try {
    await act(async () => { root.render(<Mounted />); });
    const stream = FakeEventSource.all.at(-1)!;
    await act(async () => {
      stream.emit("open");
      for (const f of frames) stream.emit("probability", f);
    });
    return { frame: seen!.frame, chartPoints: seen!.chartPoints };
  } finally {
    await act(async () => root.unmount());
    document.body.removeChild(el);
  }
}

describe("#10090 batched frames reach the page in revision order", () => {
  test.each([
    ["in order", [older, newer]],
    ["reversed, as production delivered it", [newer, older]],
  ])("%s: the page sees the newest price and the chart keeps both", async (_label, frames) => {
    const { frame, chartPoints } = await deliverInOneBatch(frames);
    expect(chartPoints).toHaveLength(2);
    expect(frame?.rev).toEqual({ [EID]: 12482 });
    expect(frame?.p).toBe(0.23537);
  });

  test("the headline the page folds from that frame is the newer price", async () => {
    const { frame } = await deliverInOneBatch([newer, older]);
    const held = {
      status: "live", hero_probability: 0.25, hero_probability_source: "blend",
      hero_probability_observed_at: "2026-10-11T21:50:05+00:00",
      blend_fold_revision: { [EID]: 12480 }, win_probability_sources: {},
    };
    // The page narrows `p` the same way before it folds a frame.
    if (typeof frame?.p !== "number") throw new Error("expected a priced frame");
    const next = applyLiveFrame(held, { ...frame, p: frame.p }) as typeof held;
    expect(next.hero_probability).toBe(0.23537);
    expect(next.blend_fold_revision).toEqual({ [EID]: 12482 });
  });

  test.each([-0.1, 1.1])(
    "a newer price of %s the page would refuse does not hide the valid older one",
    async (invalid) => {
      const { frame } = await deliverInOneBatch([{ ...newer, p: invalid }, older]);
      expect(frame?.p).toBe(0.234736);
      expect(frame?.rev).toEqual({ [EID]: 12481 });
    },
  );

  test.each([0, 1])("a newer price of exactly %s still keeps the older one out", async (edge) => {
    const { frame } = await deliverInOneBatch([{ ...newer, p: edge }, older]);
    expect(frame?.p).toBe(edge);
    expect(frame?.rev).toEqual({ [EID]: 12482 });
  });
});

describe("heldFrameAfter keeps an older price out and changes nothing else", () => {
  test.each<[string, LiveFrame]>([
    ["inside [0, 1]", newer],
    ["held at exactly 0", { ...newer, p: 0 }],
    ["held at exactly 1", { ...newer, p: 1 }],
  ])("strictly older priced frame on the same row keeps the held one (%s)", (_label, held) => {
    expect(heldFrameAfter(held, older)).toBe(held);
    expect(heldFrameAfter(held, { ...older, p: 0 })).toBe(held);
  });

  test.each<[string, LiveFrame | null, LiveFrame]>([
    ["nothing held yet", null, older],
    ["newer revision", older, newer],
    ["same revision (a quote upgrade)", newer, { ...older, rev: { [EID]: 12482 } }],
    ["another event (navigation)", newer, { ...older, event_id: EID + 1, rev: { [EID + 1]: 1 } }],
    ["older frame with no price (an invalidation)", newer, { ...older, p: null }],
    ["held frame with no price", { ...newer, p: null }, older],
    ["held frame priced below 0", { ...newer, p: -0.1 }, older],
    ["held frame priced above 1", { ...newer, p: 1.1 }, older],
    ["older frame priced outside [0, 1]", newer, { ...older, p: 1.1 }],
    ["older frame with a different status (a final)", newer, { ...older, status: "final" }],
    ["older frame carrying a folded quote", newer, { ...older, folded_quote: null }],
    ["older frame announcing a pending fold", newer, { ...older, folded_quote_pending: true }],
    ["older frame with no revision", newer, { ...older, rev: undefined }],
    ["held frame with no revision", { ...newer, rev: null }, older],
    ["revisions on different rows", newer, { ...older, rev: { 99: 1 } }],
    ["multi-row revision", newer, { ...older, rev: { [EID]: 12481, 99: 1 } }],
  ])("%s: the arriving frame replaces the held one", (_label, previous, next) => {
    expect(heldFrameAfter(previous, next)).toBe(next);
  });
});
