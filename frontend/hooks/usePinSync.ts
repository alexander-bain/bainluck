/**
 * usePinSync - One-way migration of localStorage pins to the server on first login.
 *
 * When a user signs in for the first time, this hook:
 * 1. Reads pinned event/futures IDs from localStorage
 * 2. POSTs them to the server (merges with any existing server pins)
 * 3. Marks the migration as done so it doesn't repeat
 *
 * The existing usePinnedEvents/usePinnedFutures hooks continue to use
 * localStorage for now. A future phase will replace them with server-backed
 * hooks that read/write via the API.
 */

"use client";

import { useEffect, useRef } from "react";
import { useAuthContext } from "@/components/AuthProvider";
import { syncPins } from "@/lib/api";

const EVENTS_KEY = "oddsTracker_pinnedEvents";
const FUTURES_KEY = "oddsTracker_pinnedFutures";
const SYNC_DONE_KEY = "oddsTracker_pinsSyncedToServer";

function loadLocalPins(key: string): number[] {
  if (typeof window === "undefined") return [];
  try {
    const stored = localStorage.getItem(key);
    if (!stored) return [];
    const parsed = JSON.parse(stored);
    if (Array.isArray(parsed) && parsed.every((id: unknown) => typeof id === "number")) {
      return parsed;
    }
    return [];
  } catch {
    return [];
  }
}

export function usePinSync() {
  const { isAuthenticated, isLoading } = useAuthContext();
  const hasSynced = useRef(false);

  useEffect(() => {
    if (isLoading || !isAuthenticated || hasSynced.current) return;

    // Check if we've already synced for this user
    if (typeof window !== "undefined" && localStorage.getItem(SYNC_DONE_KEY)) {
      hasSynced.current = true;
      return;
    }

    const events = loadLocalPins(EVENTS_KEY);
    const futures = loadLocalPins(FUTURES_KEY);

    // Only sync if there are localStorage pins to migrate
    if (events.length === 0 && futures.length === 0) {
      hasSynced.current = true;
      if (typeof window !== "undefined") {
        localStorage.setItem(SYNC_DONE_KEY, "true");
      }
      return;
    }

    // Sync to server
    syncPins({ events, futures })
      .then(() => {
        hasSynced.current = true;
        if (typeof window !== "undefined") {
          localStorage.setItem(SYNC_DONE_KEY, "true");
        }
      })
      .catch((err) => {
        console.warn("Failed to sync pins to server:", err);
        // Don't mark as done — will retry on next mount
      });
  }, [isAuthenticated, isLoading]);
}
