// L2-195 — the framework-free async engine behind usePlayPool.
//
// C39 P2 found the L2-194 tests drove only the pure reducer/view helper: none
// exercised the real async pump, so async append reordering, caught-up retry
// offset behavior, refresh-from-zero, malformed pagination, and late-response
// cancellation were untested. Extracting the pump into this plain controller
// makes ALL of that deterministically testable in the node jest env with deferred
// page promises — `usePlayPool` becomes a thin useSyncExternalStore wrapper.

import type { FeedItem } from "@/lib/types";
import {
  initialPoolState,
  pendingFetch,
  reducePool,
  type PlayPoolAction,
  type PlayPoolPage,
  type PlayPoolState,
} from "@/lib/play/poolState";

export type FetchPlayPage = (
  offset: number,
  limit: number
) => Promise<PlayPoolPage>;

export interface PlayPoolController {
  getState(): PlayPoolState;
  subscribe(cb: () => void): () => void;
  /** Kick off the initial load. Idempotent and re-arms after dispose (Strict Mode). */
  start(): void;
  /** Resume at the current offset — error retry / scan continuation. */
  loadMore(): void;
  /** Alias of loadMore for the error "Try again" action. */
  retry(): void;
  /** Freshness pass from offset 0, deduping against consumed cards. */
  refresh(): void;
  /** Stop applying responses (unmount). Reversible via start() for Strict Mode. */
  dispose(): void;
}

export function createPlayPoolController(
  fetchPage: FetchPlayPage,
  pageSize: number
): PlayPoolController {
  let state = initialPoolState();
  let disposed = false;
  let started = false;
  const listeners = new Set<() => void>();

  const emit = () => {
    for (const cb of listeners) cb();
  };

  const apply = (action: PlayPoolAction) => {
    const next = reducePool(state, action);
    if (next === state) return;
    state = next;
    emit();
  };

  const pump = async () => {
    // Drain pages while the machine still wants more (initial load or an
    // auto-advance past an empty page). `inFlight` in the reducer guards against
    // a second concurrent pump; `disposed` drops any late response after unmount.
    while (pendingFetch(state)) {
      const gen = state.gen;
      const offset = state.offset;
      try {
        const page = await fetchPage(offset, pageSize);
        if (disposed) return;
        apply({
          type: "PAGE_OK",
          gen,
          items: page.items,
          hasMore: page.hasMore,
          pageSize,
        });
      } catch {
        if (disposed) return;
        apply({ type: "PAGE_ERR", gen });
      }
    }
  };

  return {
    getState: () => state,
    subscribe(cb) {
      listeners.add(cb);
      return () => {
        listeners.delete(cb);
      };
    },
    start() {
      disposed = false; // re-arm after a Strict-Mode simulated unmount
      if (started) return;
      started = true;
      apply({ type: "START_LOAD" });
      void pump();
    },
    loadMore() {
      if (state.inFlight || state.status === "exhausted") return;
      apply({ type: "START_LOAD" });
      void pump();
    },
    retry() {
      if (state.inFlight) return;
      apply({ type: "START_LOAD" });
      void pump();
    },
    refresh() {
      if (state.inFlight) return;
      apply({ type: "REFRESH" });
      void pump();
    },
    dispose() {
      disposed = true;
    },
  };
}

export type { FeedItem };
