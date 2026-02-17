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
        // Retry failed requests with exponential backoff
        errorRetryCount: 2,
        // Don't refetch on reconnect — let refreshInterval handle it
        revalidateOnReconnect: false,
      }}
    >
      {children}
    </SWRConfig>
  );
}
