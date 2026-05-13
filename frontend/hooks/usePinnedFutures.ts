/**
 * usePinnedFutures - Hook for managing pinned futures markets
 *
 * Uses localStorage for anonymous users, server-backed storage for
 * authenticated users. On sign-in, merges localStorage pins to the server
 * and fetches the merged set. Pin/unpin operations sync to the server
 * immediately when authenticated, enabling cross-platform sync (web + iOS).
 */

"use client";

import { useState, useEffect, useCallback, useRef } from 'react';
import { useAuthContext } from '@/components/AuthProvider';
import { fetchUserPins, addPin, removePin } from '@/lib/api';

const STORAGE_KEY = 'bainluck_pinnedFutures';
const MAX_PINNED_FUTURES = 6;

interface UsePinnedFuturesResult {
  /** Array of pinned futures IDs */
  pinnedIds: number[];
  /** Check if a futures market is pinned */
  isPinned: (futuresId: number) => boolean;
  /** Toggle pin status for a futures market */
  togglePin: (futuresId: number) => void;
  /** Pin a futures market (no-op if already pinned or at max) */
  pin: (futuresId: number) => boolean;
  /** Unpin a futures market */
  unpin: (futuresId: number) => void;
  /** Clear all pins */
  clearAll: () => void;
  /** Whether max pins have been reached */
  isMaxReached: boolean;
}

/**
 * Load pinned IDs from localStorage
 */
function loadPinnedIds(): number[] {
  if (typeof window === 'undefined') return [];

  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) return [];

    const parsed = JSON.parse(stored);
    if (Array.isArray(parsed) && parsed.every(id => typeof id === 'number')) {
      return parsed;
    }
    return [];
  } catch {
    return [];
  }
}

/**
 * Save pinned IDs to localStorage
 */
function savePinnedIds(ids: number[]): void {
  if (typeof window === 'undefined') return;

  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
  } catch {
    // localStorage might be full or disabled
    console.warn('Failed to save pinned futures to localStorage');
  }
}

export function usePinnedFutures(): UsePinnedFuturesResult {
  const [pinnedIds, setPinnedIds] = useState<number[]>([]);
  const { isAuthenticated, isLoading: authLoading } = useAuthContext();
  const hasLoadedFromServer = useRef(false);

  // Load from localStorage on mount (immediate, before server fetch completes)
  useEffect(() => {
    setPinnedIds(loadPinnedIds());
  }, []);

  // When authenticated, fetch server pins and merge with localStorage
  useEffect(() => {
    if (authLoading || !isAuthenticated || hasLoadedFromServer.current) return;

    let cancelled = false;

    (async () => {
      try {
        const serverPins = await fetchUserPins();
        if (cancelled) return;

        // Merge: server is the source of truth, but include any localStorage
        // pins not yet on the server (handles the case where user pinned
        // while offline or before this code deployed).
        const localPins = loadPinnedIds();
        const merged = Array.from(new Set([...serverPins.futures, ...localPins]));

        setPinnedIds(merged);
        savePinnedIds(merged);
        hasLoadedFromServer.current = true;

        // If localStorage had pins the server didn't, push them up
        const serverSet = new Set(serverPins.futures);
        const localOnly = localPins.filter(id => !serverSet.has(id));
        for (const id of localOnly) {
          try {
            await addPin('future', id);
          } catch {
            // Best-effort — don't block the UI
          }
        }
      } catch (err) {
        console.warn('Failed to fetch pins from server, using localStorage:', err);
        // Fall back to localStorage (already loaded)
      }
    })();

    return () => { cancelled = true; };
  }, [isAuthenticated, authLoading]);

  // Sync across browser tabs (localStorage events)
  useEffect(() => {
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY) {
        setPinnedIds(loadPinnedIds());
      }
    };

    window.addEventListener('storage', handleStorageChange);
    return () => window.removeEventListener('storage', handleStorageChange);
  }, []);

  // Save to localStorage whenever pinnedIds changes (cache for next load)
  useEffect(() => {
    savePinnedIds(pinnedIds);
  }, [pinnedIds]);

  const isPinned = useCallback((futuresId: number): boolean => {
    return pinnedIds.includes(futuresId);
  }, [pinnedIds]);

  const pin = useCallback((futuresId: number): boolean => {
    if (pinnedIds.includes(futuresId)) return false;
    if (pinnedIds.length >= MAX_PINNED_FUTURES) return false;

    setPinnedIds(prev => [...prev, futuresId]);

    // Sync to server
    if (isAuthenticated) {
      addPin('future', futuresId).catch(err =>
        console.warn('Failed to sync pin to server:', err)
      );
    }

    return true;
  }, [pinnedIds, isAuthenticated]);

  const unpin = useCallback((futuresId: number): void => {
    setPinnedIds(prev => prev.filter(id => id !== futuresId));

    // Sync to server
    if (isAuthenticated) {
      removePin('future', futuresId).catch(err =>
        console.warn('Failed to sync unpin to server:', err)
      );
    }
  }, [isAuthenticated]);

  const togglePin = useCallback((futuresId: number): void => {
    if (pinnedIds.includes(futuresId)) {
      unpin(futuresId);
    } else {
      pin(futuresId);
    }
  }, [pinnedIds, pin, unpin]);

  const clearAll = useCallback((): void => {
    // Remove each from server
    if (isAuthenticated) {
      for (const id of pinnedIds) {
        removePin('future', id).catch(err =>
          console.warn('Failed to remove pin from server:', err)
        );
      }
    }
    setPinnedIds([]);
  }, [isAuthenticated, pinnedIds]);

  return {
    pinnedIds,
    isPinned,
    togglePin,
    pin,
    unpin,
    clearAll,
    isMaxReached: pinnedIds.length >= MAX_PINNED_FUTURES,
  };
}
