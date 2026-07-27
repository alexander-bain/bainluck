// L2-195 — the async pump behind usePlayPool, driven with DEFERRED page promises
// (C39 P2: L2-194 tested only the pure reducer). These exercise the real fetch
// orchestration a hook mount would: async append while a page is in flight, error
// then retry at the SAME offset, freshness refresh from offset zero deduping
// consumed cards, bounded empty-page scanning, malformed-payload rejection, and
// late-response cancellation after dispose.

import {
  createPlayPoolController,
  type FetchPlayPage,
} from "@/lib/play/poolController";
import { validatePage, type PlayPoolPage } from "@/lib/play/poolState";
import type { FeedItem } from "@/lib/types";

const PAGE = 120;

function fut(id: number): FeedItem {
  return {
    type: "futures",
    score: 1,
    reason: "",
    headline: null,
    data: { id, top_outcomes: [{ name: `O${id}`, probability: 0.6 }] } as unknown as FeedItem["data"],
  };
}

interface Deferred<T> {
  promise: Promise<T>;
  resolve: (v: T) => void;
  reject: (e?: unknown) => void;
}
function deferred<T>(): Deferred<T> {
  let resolve!: (v: T) => void;
  let reject!: (e?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

// Flush microtasks + a macrotask so a resolved fetch lets the pump resume and
// apply its PAGE_OK/PAGE_ERR, then issue the next fetch if it still wants one.
const flush = () => new Promise((r) => setTimeout(r, 0));

// A fetchPage seam recording every call and handing back a controllable promise.
function scriptedFetch() {
  const calls: { offset: number; d: Deferred<PlayPoolPage> }[] = [];
  const fetchPage: FetchPlayPage = (offset) => {
    const d = deferred<PlayPoolPage>();
    calls.push({ offset, d });
    return d.promise;
  };
  return { calls, fetchPage };
}

function ids(items: FeedItem[]): number[] {
  return items.map((it) => (it.data as { id: number }).id);
}

describe("createPlayPoolController — deferred async pump", () => {
  it("start() loads the first page and settles to ready", async () => {
    const { calls, fetchPage } = scriptedFetch();
    const c = createPlayPoolController(fetchPage, PAGE);
    c.start();
    expect(calls[0].offset).toBe(0);
    expect(c.getState().status).toBe("loading");

    calls[0].d.resolve({ items: [fut(1), fut(2)], hasMore: true });
    await flush();
    expect(c.getState().status).toBe("ready");
    expect(ids(c.getState().items)).toEqual([1, 2]);
    expect(c.getState().offset).toBe(PAGE);
  });

  it("append while a page is in flight preserves the existing deck, then appends", async () => {
    const { calls, fetchPage } = scriptedFetch();
    const c = createPlayPoolController(fetchPage, PAGE);
    c.start();
    calls[0].d.resolve({ items: [fut(1), fut(2)], hasMore: true });
    await flush();

    c.loadMore();
    // Page 2 is pending — the deck under the child is untouched.
    expect(c.getState().status).toBe("loading");
    expect(ids(c.getState().items)).toEqual([1, 2]);
    expect(calls[1].offset).toBe(PAGE);

    calls[1].d.resolve({ items: [fut(2), fut(3)], hasMore: true }); // fut(2) is a dup
    await flush();
    expect(ids(c.getState().items)).toEqual([1, 2, 3]); // append-only, deduped
  });

  it("error retries at the SAME offset and recovers (never advances past the tail)", async () => {
    const { calls, fetchPage } = scriptedFetch();
    const c = createPlayPoolController(fetchPage, PAGE);
    c.start();
    calls[0].d.reject(new Error("network"));
    await flush();
    expect(c.getState().status).toBe("error");
    expect(c.getState().offset).toBe(0); // failed request did NOT advance the offset

    c.retry();
    expect(calls[1].offset).toBe(0); // same offset
    calls[1].d.resolve({ items: [fut(1)], hasMore: true });
    await flush();
    expect(c.getState().status).toBe("ready");
    expect(ids(c.getState().items)).toEqual([1]);
  });

  it("refresh restarts at offset 0 and surfaces a new first-page card without replaying", async () => {
    const { calls, fetchPage } = scriptedFetch();
    const c = createPlayPoolController(fetchPage, PAGE);
    c.start();
    calls[0].d.resolve({ items: [fut(1), fut(2)], hasMore: false });
    await flush();
    expect(c.getState().status).toBe("exhausted");
    expect(c.getState().offset).toBe(PAGE);

    c.refresh();
    expect(calls[1].offset).toBe(0); // freshness pass from page zero
    // Newest-first: a brand-new card ahead of the two already-consumed ones.
    calls[1].d.resolve({ items: [fut(9), fut(1), fut(2)], hasMore: false });
    await flush();
    expect(ids(c.getState().items)).toEqual([1, 2, 9]); // only fut(9) appended
    expect(c.getState().status).toBe("exhausted");
  });

  it("scans through empty pages but stops at the cap (no infinite loop)", async () => {
    const { calls, fetchPage } = scriptedFetch();
    const c = createPlayPoolController(fetchPage, PAGE);
    c.start();
    // Every page is empty with hasMore=true; the pump auto-advances, bounded.
    let i = 0;
    while (c.getState().status === "loading" && i < 20) {
      calls[i].d.resolve({ items: [], hasMore: true });
      await flush();
      i += 1;
    }
    expect(c.getState().status).toBe("ready"); // paused, not exhausted
    expect(c.getState().emptyScan).toBe(5); // MAX_EMPTY_SCAN
    expect(c.getState().items).toHaveLength(0);
  });

  it("a malformed page (contract error) routes to the retryable error state", async () => {
    // The default fetch validates the raw payload; simulate that here.
    const raw = { items: null, has_more: true };
    const fetchPage: FetchPlayPage = async () => {
      const p = validatePage(raw); // throws PlayPageContractError
      return p;
    };
    const c = createPlayPoolController(fetchPage, PAGE);
    c.start();
    await flush();
    expect(c.getState().status).toBe("error");
    expect(c.getState().status).not.toBe("exhausted");
  });

  it("a response that resolves after dispose() is ignored (unmount cancellation)", async () => {
    const { calls, fetchPage } = scriptedFetch();
    const c = createPlayPoolController(fetchPage, PAGE);
    c.start();
    c.dispose(); // unmount before the page resolves
    calls[0].d.resolve({ items: [fut(1)], hasMore: true });
    await flush();
    // No PAGE_OK applied: the deck stays empty (the stale response was dropped).
    expect(c.getState().items).toHaveLength(0);
  });

  it("notifies subscribers on state changes", async () => {
    const { calls, fetchPage } = scriptedFetch();
    const c = createPlayPoolController(fetchPage, PAGE);
    let hits = 0;
    const unsub = c.subscribe(() => {
      hits += 1;
    });
    c.start();
    calls[0].d.resolve({ items: [fut(1)], hasMore: true });
    await flush();
    expect(hits).toBeGreaterThan(0);
    unsub();
  });
});
