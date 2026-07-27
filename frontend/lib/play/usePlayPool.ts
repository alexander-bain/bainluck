"use client";

// L2-194 / L2-195 — thin React wrapper around the framework-free pool controller.
// All state + async orchestration lives in poolController.ts + poolState.ts (both
// unit-tested in the node jest env with deferred page promises); this file only
// binds the controller to React via useSyncExternalStore and wires mount/unmount.
// `fetchPage` is injectable so loading/retry/refresh/exhaustion paths can be
// driven deterministically without a live feed.

import { useEffect, useRef, useSyncExternalStore } from "react";
import { fetchFeed } from "@/lib/api";
import type { FeedItem } from "@/lib/types";
import { filterKidSafe } from "@/lib/play/kidSafe";
import {
  validatePage,
  type PlayPoolPage,
  type PlayPoolStatus,
} from "@/lib/play/poolState";
import {
  createPlayPoolController,
  type FetchPlayPage,
} from "@/lib/play/poolController";

export const PLAY_PAGE_SIZE = 120;
export type { PlayPoolPage, FetchPlayPage };

// Default page source: the real feed, kid-safe-filtered. `validatePage` asserts
// the pagination contract (typed `items`/`has_more`) BEFORE we trust it — a
// malformed/decoded-wrong payload throws, and the pump routes it to the retryable
// error state instead of faking exhaustion or scanning past the end (C39 P2).
const defaultFetchPage: FetchPlayPage = async (offset, limit) => {
  const res = await fetchFeed({
    limit,
    offset,
    event_pct: 0.3,
    include_futures: true,
    include_events: true,
  });
  const page = validatePage(res);
  return { items: filterKidSafe(page.items), hasMore: page.hasMore };
};

export interface PlayPoolController {
  pool: FeedItem[];
  status: PlayPoolStatus;
  hasMore: boolean;
  malformed: number;
  loadMore: () => void;
  retry: () => void;
  refresh: () => void;
}

export function usePlayPool(
  fetchPage: FetchPlayPage = defaultFetchPage,
  pageSize: number = PLAY_PAGE_SIZE
): PlayPoolController {
  // Create the controller exactly once; it survives Strict-Mode simulated
  // remounts (refs persist), so start()/dispose() re-arm rather than re-create.
  const ctrlRef = useRef<ReturnType<typeof createPlayPoolController> | null>(null);
  if (ctrlRef.current === null) {
    ctrlRef.current = createPlayPoolController(fetchPage, pageSize);
  }
  const ctrl = ctrlRef.current;

  const state = useSyncExternalStore(ctrl.subscribe, ctrl.getState, ctrl.getState);

  useEffect(() => {
    ctrl.start();
    return () => ctrl.dispose();
  }, [ctrl]);

  return {
    pool: state.items,
    status: state.status,
    hasMore: state.hasMore,
    malformed: state.malformed,
    loadMore: ctrl.loadMore,
    retry: ctrl.retry,
    refresh: ctrl.refresh,
  };
}
