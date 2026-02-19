/**
 * usePinnedFutures - Hook for managing pinned futures markets
 *
 * Stores pinned futures IDs in localStorage for persistence.
 * Syncs across browser tabs using storage events.
 *
 * When Firebase Auth is added, this can be upgraded to sync with the backend.
 */

import { useState, useEffect, useCallback } from 'react';

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

  // Load from localStorage on mount (client-side only)
  useEffect(() => {
    setPinnedIds(loadPinnedIds());
  }, []);

  // Sync across browser tabs
  useEffect(() => {
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY) {
        setPinnedIds(loadPinnedIds());
      }
    };

    window.addEventListener('storage', handleStorageChange);
    return () => window.removeEventListener('storage', handleStorageChange);
  }, []);

  // Save to localStorage whenever pinnedIds changes
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
    return true;
  }, [pinnedIds]);

  const unpin = useCallback((futuresId: number): void => {
    setPinnedIds(prev => prev.filter(id => id !== futuresId));
  }, []);

  const togglePin = useCallback((futuresId: number): void => {
    if (pinnedIds.includes(futuresId)) {
      unpin(futuresId);
    } else {
      pin(futuresId);
    }
  }, [pinnedIds, pin, unpin]);

  const clearAll = useCallback((): void => {
    setPinnedIds([]);
  }, []);

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
