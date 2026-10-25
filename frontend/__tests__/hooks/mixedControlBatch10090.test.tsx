/** #10090: every frame of a React batch reaches the page, not only the last.
 * Real hook + controller, fake EventSource, minimal DOM; the page's own push
 * callback, lifted from `app/events/[id]/page.tsx` with the TypeScript AST.
 * The detail cache is React state (the page's swr cache stands in), so the
 * held event a callback reads is the one the last render committed, as on the
 * page. Before the fix the page acted on the batch's last frame only: a newer
 * price followed by an older invalidation (rev 12482 p=.23537, then rev 12481
 * p=null) left the headline on the old price until history answered, while
 * the chart banked both.
 */
import "../helpers/minimalDom";
import React, { act, useState } from "react";
import { createRoot } from "react-dom/client";
import fs from "fs";
import path from "path";
import vm from "vm";
import ts from "typescript";

import { heldFrameAfter, useLiveEventStream, type LiveFrame } from "../../hooks/useLiveEventStream";
import { adoptFoldedQuote, applyLiveFrame, applyLiveFrameRail, frameInvalidatesFoldedBlend } from "../../lib/eventLivePush";
import { frameFoldOrder } from "../../lib/foldRevision";
import { frameCarriesUnpricedSnapshot, snapshotRailPaysPricelessTrigger } from "../../lib/sourceSnapshot";
import { canSubscribeEventQuotes } from "../../lib/eventQuoteStream";

const PAGE = fs.readFileSync(path.join(__dirname, "../../app/events/[id]/page.tsx"), "utf8");
const tree = ts.createSourceFile("page.tsx", PAGE, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
let callbackText: string | undefined;
(function visit(node: ts.Node) {
  if (ts.isVariableDeclaration(node) && node.name.getText(tree) === "applyPushedFrame" &&
      node.initializer && ts.isCallExpression(node.initializer) &&
      node.initializer.expression.getText(tree) === "useCallback") {
    callbackText = node.initializer.arguments[0].getText(tree);
  }
  ts.forEachChild(node, visit);
})(tree);
if (!callbackText) throw new Error("page push callback missing");
const CALLBACK = new vm.Script(ts.transpileModule(`(${callbackText})`, {
  compilerOptions: { target: ts.ScriptTarget.ES2020 },
}).outputText);

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
type Held = {
  id: number; status: string; hero_probability: number; hero_probability_source: string;
  hero_probability_observed_at: string; blend_fold_revision: Record<string, number>;
  win_probability_sources: Record<string, unknown>;
};
const held = (): Held => ({
  id: EID, status: "live", hero_probability: 0.25, hero_probability_source: "blend",
  hero_probability_observed_at: "2026-10-11T21:50:05+00:00",
  blend_fold_revision: { [EID]: 12480 }, win_probability_sources: {},
});
const older: LiveFrame = {
  event_id: EID, p: 0.234736, source: "betting", source_value: 0.2359,
  rev: { [EID]: 12481 }, updated_at: "2026-10-11T21:50:11.014347+00:00", status: "live",
};
const newer: LiveFrame = {
  event_id: EID, p: 0.23537, source: "polymarket", source_value: 0.225,
  rev: { [EID]: 12482 }, updated_at: "2026-10-11T21:50:11.623585+00:00", status: "live",
};
// The control: the older revision with no price and no source value.
const olderControl: LiveFrame = { ...older, p: null, source_value: null };

type Seen = {
  cache: Held; chartPoints: number; status: string; connected: boolean;
  requests: number; trigger: LiveFrame | null; latest: LiveFrame | null; applied: LiveFrame[];
};
let seen: Seen;

function HeldPage({ throwOn }: { throwOn?: (f: LiveFrame) => boolean }) {
  const [cache, setCache] = useState(held);
  const [refs] = useState(() => ({
    heldEventRef: { current: undefined as Held | undefined },
    quoteTriggerRef: { current: null as LiveFrame | null },
    sourceAddedHistoryRef: { current: null },
    latestLiveFrameRef: { current: null as LiveFrame | null },
    pairJournalRef: { current: null }, // #10090 G1: no paired read in flight here
    requests: 0,
    applied: [] as LiveFrame[],
  }));
  // The page assigns this during render, from the swr data.
  refs.heldEventRef.current = cache;
  const [applyPushedFrame] = useState(() => {
    const body = CALLBACK.runInNewContext({
      eventId: EID, ...refs,
      foldedRefetch: { request: () => { refs.requests += 1; } },
      refreshEvent: (update: (prev: Held) => Held, options: unknown) => {
        expect(options).toEqual({ revalidate: false });
        setCache(prev => update(prev));
        // SWR mutate returns a promise; source-addition reads are scheduled
        // only after that write. This fixture's legacy frames add no snapshot.
        return Promise.resolve();
      },
      setLastRefresh: () => {},
      Date, adoptFoldedQuote, applyLiveFrame, frameInvalidatesFoldedBlend, canSubscribeEventQuotes, heldFrameAfter,
      applyLiveFrameRail, frameCarriesUnpricedSnapshot, frameFoldOrder, snapshotRailPaysPricelessTrigger,
    }) as (f: LiveFrame) => void;
    return (f: LiveFrame) => {
      refs.applied.push(f);
      if (throwOn?.(f)) throw new Error("consumer bug");
      body(f);
    };
  });
  const stream = useLiveEventStream(EID, true, applyPushedFrame);
  seen = {
    cache, chartPoints: stream.chartPoints.length, status: stream.status, connected: stream.connected,
    requests: refs.requests, trigger: refs.quoteTriggerRef.current,
    latest: refs.latestLiveFrameRef.current, applied: refs.applied,
  };
  return <span>{cache.hero_probability}</span>;
}

async function deliverInOneBatch(frames: LiveFrame[], throwOn?: (f: LiveFrame) => boolean) {
  const el = document.createElement("div");
  document.body.appendChild(el);
  const root = createRoot(el);
  try {
    await act(async () => { root.render(<HeldPage throwOn={throwOn} />); });
    const stream = FakeEventSource.all.at(-1)!;
    await act(async () => {
      stream.emit("open");
      for (const f of frames) stream.emit("probability", f);
    });
    return seen!;
  } finally {
    await act(async () => root.unmount());
    document.body.removeChild(el);
  }
}

describe("#10090 a price and a control in one batch both reach the page", () => {
  test("newer price, then the older invalidation (the reproduced pair): headline adopts the price AND the read is owed", async () => {
    const s = await deliverInOneBatch([newer, olderControl]);
    expect(s.applied).toEqual([newer, olderControl]);
    expect(s.cache.hero_probability).toBe(0.23537);
    expect(s.cache.blend_fold_revision).toEqual({ [EID]: 12482 });
    // The invalidation still asks for the paired detail/history read.
    expect(s.requests).toBe(1);
    expect(s.trigger).toEqual(olderControl);
    // The chart banks the price; a priceless control is not a point.
    expect(s.chartPoints).toBe(1);
  });

  test("older invalidation, then the newer price: the price lands and the read is still owed", async () => {
    const s = await deliverInOneBatch([olderControl, newer]);
    expect(s.cache.hero_probability).toBe(0.23537);
    expect(s.requests).toBe(1);
    expect(s.trigger).toEqual(olderControl);
  });

  test("a newer invalidation after a price keeps the price it was handed and asks for the read", async () => {
    const newerControl: LiveFrame = { ...newer, p: null, source_value: null, rev: { [EID]: 12483 } };
    const s = await deliverInOneBatch([newer, newerControl]);
    expect(s.cache.hero_probability).toBe(0.23537);
    expect(s.requests).toBe(1);
    expect(s.trigger).toEqual(newerControl);
  });

  test("a status change in the batch is still routed to the read, never written as a price", async () => {
    const final: LiveFrame = { ...older, rev: { [EID]: 12483 }, status: "final" };
    const s = await deliverInOneBatch([newer, final]);
    expect(s.cache.hero_probability).toBe(0.23537);
    expect(s.cache.status).toBe("live");
    expect(s.requests).toBe(1);
    expect(s.trigger).toEqual(final);
  });

  test("two prices, newer first: the headline and the poll's replay frame both keep the newer one", async () => {
    const s = await deliverInOneBatch([newer, older]);
    expect(s.applied).toEqual([newer, older]);
    expect(s.cache.hero_probability).toBe(0.23537);
    expect(s.latest).toEqual(newer);
    expect(s.requests).toBe(0);
  });

  test("another event's frame in the batch writes nothing", async () => {
    const other: LiveFrame = { ...newer, event_id: EID + 1, rev: { [EID + 1]: 1 } };
    const s = await deliverInOneBatch([other]);
    expect(s.cache).toEqual(held());
    expect(s.requests).toBe(0);
    expect(s.latest).toBeNull();
  });

  test("a consumer that throws does not stop the transport or the frames behind it", async () => {
    jest.useFakeTimers();
    try {
      const s = await deliverInOneBatch([newer, olderControl], f => f.p !== null);
      // The throwing frame wrote nothing; the next frame was still delivered.
      expect(s.applied.map(f => f.p)).toEqual([0.23537, null]);
      expect(s.requests).toBe(1);
      expect(s.chartPoints).toBe(1);
      expect(s.status).toBe("open");
      expect(s.connected).toBe(true);
      // The error is reported, off the transport's stack.
      expect(() => jest.runOnlyPendingTimers()).toThrow("consumer bug");
    } finally {
      jest.clearAllTimers();
      jest.useRealTimers();
    }
  });
});
