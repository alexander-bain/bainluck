"use client";

import { SWRConfig, mutate } from "swr";
import type { ReactNode } from "react";
import { createPollRecovery } from "@/lib/pollRecovery";

/**
 * #5072 — the recovery scheduler for polled keys that have errored.
 *
 * Module scope, not a `useRef`: there is one SWR cache in the app and this
 * tracks state about it, so it must outlive any single render and be shared by
 * every subtree. It is inert until `onError` arms it, which cannot happen
 * during SSR, so constructing it at import time on the server costs nothing.
 */
const pollRecovery = createPollRecovery({
  mutate: (key) => mutate(key),
  setTimer: (fn, ms) => setTimeout(fn, ms),
  clearTimer: (handle) => clearTimeout(handle),
  // Written to match swr's own `isVisible`/`isOnline` defaults, including
  // their fail-open direction: a runtime that cannot answer is treated as
  // visible and online, because refusing to recover is the failure we are
  // fixing.
  isVisible: () =>
    typeof document === "undefined" || document.visibilityState !== "hidden",
  isOnline: () => typeof navigator === "undefined" || navigator.onLine !== false,
});

/**
 * Global SWR configuration to reduce redundant network requests
 * and improve perceived load times.
 */
export default function SWRProvider({ children }: { children: ReactNode }) {
  return (
    <SWRConfig
      value={{
        // Prevent duplicate requests within 5 seconds
        dedupingInterval: 5000,
        // Don't refetch when window regains focus (tabs, app switch)
        revalidateOnFocus: false,
        // Keep showing stale data while revalidating
        keepPreviousData: true,
        // Retry is owned by apiFetch (2 retries w/ exponential backoff on
        // timeout/network errors). Leaving SWR's retry on stacked a second
        // retry loop on top (up to ~9 attempts per failing key). #L2-137:
        // single source of retry — disable SWR's.
        shouldRetryOnError: false,
        // Don't refetch on reconnect — let refreshInterval handle it.
        //
        // #5072: that sentence was false for four years of this file's life.
        // `refreshInterval` REFUSES to fetch while the key is errored
        // (`swr@2.4.1`: `if (!getCache().error && …)`), so with retry, focus
        // and reconnect all off there was no path back at all — one 429 and a
        // page left open never asked again. `onError` below is what makes the
        // comment true.
        revalidateOnReconnect: false,
        // The single edge that arms recovery. It is the only SWR callback this
        // depends on, and deliberately so: four pages define their own
        // hook-level `onSuccess`, which SHADOWS a global one, so a global
        // `onSuccess` would silently never fire for exactly the live event
        // page this was filed against. No page defines a hook-level `onError`;
        // if one ever does, that key degrades to a single recovery attempt
        // rather than an endless one — still strictly better than the latch.
        onError: (error, key, config) =>
          pollRecovery.recordError(key, error, config?.refreshInterval),
      }}
    >
      {children}
    </SWRConfig>
  );
}
