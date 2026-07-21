"use client";

import { SWRConfig } from "swr";
import type { ReactNode } from "react";

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
        // Don't refetch on reconnect — let refreshInterval handle it
        revalidateOnReconnect: false,
      }}
    >
      {children}
    </SWRConfig>
  );
}
