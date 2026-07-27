"use client";

// L2-194 — thin React wrapper around the pure poolState reducer. All decision
// logic lives in poolState.ts (unit-tested in the node jest env); this file only
// wires the async fetch pump, dedupe of concurrent requests, and unmount
// cancellation. `fetchPage` is injectable so the loading/retry/exhaustion paths
// can be driven deterministically in tests without a live feed.

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchFeed } from "@/lib/api";
import type { FeedItem } from "@/lib/types";
import { filterKidSafe } from "@/lib/play/kidSafe";
import {
  initialPoolState,
  pendingFetch,
  reducePool,
  type PlayPoolAction,
  type PlayPoolState,
  type PlayPoolStatus,
} from "@/lib/play/poolState";

export const PLAY_PAGE_SIZE = 120;

export interface PlayPoolPage {
  items: FeedItem[];
  hasMore: boolean;
}

export type FetchPlayPage = (
  offset: number,
  limit: number
) => Promise<PlayPoolPage>;

// Default page source: the real feed, kid-safe-filtered. Carries the server's
// has_more through untouched — the reducer keeps it separate from usable count.
const defaultFetchPage: FetchPlayPage = async (offset, limit) => {
  const res = await fetchFeed({
    limit,
    offset,
    event_pct: 0.3,
    include_futures: true,
    include_events: true,
  });
  return { items: filterKidSafe(res.items || []), hasMore: !!res.has_more };
};

export interface PlayPoolController {
  pool: FeedItem[];
  status: PlayPoolStatus;
  hasMore: boolean;
  loadMore: () => void;
  retry: () => void;
}

export function usePlayPool(
  fetchPage: FetchPlayPage = defaultFetchPage,
  pageSize: number = PLAY_PAGE_SIZE
): PlayPoolController {
  const [state, setState] = useState<PlayPoolState>(initialPoolState);
  const stateRef = useRef(state);
  const mountedRef = useRef(true);
  const didInit = useRef(false);

  // Keep a synchronous mirror of state so the async pump reads the freshest
  // offset/gen/inFlight without waiting for a React render.
  const dispatch = useCallback((action: PlayPoolAction) => {
    const next = reducePool(stateRef.current, action);
    if (next === stateRef.current) return;
    stateRef.current = next;
    setState(next);
  }, []);

  const pump = useCallback(async () => {
    // Fetch pages while the machine wants more (initial load or auto-advance
    // past an empty page). inFlight guards against a second concurrent pump.
    while (pendingFetch(stateRef.current)) {
      const gen = stateRef.current.gen;
      const offset = stateRef.current.offset;
      try {
        const page = await fetchPage(offset, pageSize);
        if (!mountedRef.current) return;
        dispatch({
          type: "PAGE_OK",
          gen,
          items: page.items,
          hasMore: page.hasMore,
          pageSize,
        });
      } catch {
        if (!mountedRef.current) return;
        dispatch({ type: "PAGE_ERR", gen });
      }
    }
  }, [fetchPage, pageSize, dispatch]);

  const loadMore = useCallback(() => {
    const s = stateRef.current;
    if (s.inFlight || s.status === "exhausted") return;
    dispatch({ type: "START_LOAD" });
    void pump();
  }, [dispatch, pump]);

  const retry = useCallback(() => {
    if (stateRef.current.inFlight) return;
    dispatch({ type: "START_LOAD" });
    void pump();
  }, [dispatch, pump]);

  useEffect(() => {
    mountedRef.current = true;
    if (!didInit.current) {
      didInit.current = true;
      dispatch({ type: "START_LOAD" });
      void pump();
    }
    return () => {
      mountedRef.current = false;
      // Bump the generation so any in-flight response is treated as stale even
      // if it resolves after unmount — the reducer ignores a mismatched gen.
      stateRef.current = { ...stateRef.current, gen: stateRef.current.gen + 1 };
    };
  }, [dispatch, pump]);

  return {
    pool: state.items,
    status: state.status,
    hasMore: state.hasMore,
    loadMore,
    retry,
  };
}
