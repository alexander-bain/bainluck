"use client";

import { useEffect, useRef } from "react";
import { useAuthContext } from "@/components/AuthProvider";
import { fetchUserPreferences, updateSportAffinities } from "@/lib/api";

const STORAGE_KEY = "bainluck_categoryInterests";
const SYNC_DONE_KEY = "bainluck_interestsSyncedToServer";

/**
 * One-time migration of localStorage category interests to server on first sign-in.
 * Merge strategy: takes max of localStorage and server values per category.
 * Same pattern as usePinSync.
 */
export function useInterestSync() {
  const { isAuthenticated, isLoading } = useAuthContext();
  const hasSynced = useRef(false);

  useEffect(() => {
    if (isLoading || !isAuthenticated || hasSynced.current) return;

    if (typeof window !== "undefined" && localStorage.getItem(SYNC_DONE_KEY)) {
      hasSynced.current = true;
      return;
    }

    // Read localStorage interests
    let localInterests: Record<string, number> = {};
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) localInterests = JSON.parse(stored);
    } catch {
      // ignore
    }

    // No local interests to migrate
    if (Object.keys(localInterests).length === 0) {
      hasSynced.current = true;
      if (typeof window !== "undefined") {
        localStorage.setItem(SYNC_DONE_KEY, "true");
      }
      return;
    }

    // Fetch server interests, merge, save
    fetchUserPreferences()
      .then(async (prefs) => {
        const serverInterests = prefs.sport_affinities || {};
        const merged: Record<string, number> = { ...serverInterests };

        for (const [key, value] of Object.entries(localInterests)) {
          merged[key] = Math.max(merged[key] ?? 0, value);
        }

        await updateSportAffinities(merged);
        hasSynced.current = true;
        if (typeof window !== "undefined") {
          localStorage.setItem(SYNC_DONE_KEY, "true");
        }
      })
      .catch((err) => {
        console.warn("Failed to sync interests to server:", err);
      });
  }, [isAuthenticated, isLoading]);
}
