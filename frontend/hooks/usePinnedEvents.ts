/**
 * usePinnedEvents - Hook for managing pinned events
 *
 * Stores pinned event IDs in localStorage for persistence.
 * Syncs across browser tabs using storage events.
 *
 * When Firebase Auth is added, this can be upgraded to sync with the backend.
 */

import { useState, useEffect, useCallback } from 'react';

const STORAGE_KEY = 'oddsTracker_pinnedEvents';
const MAX_PINNED_EVENTS = 6;

interface UsePinnedEventsResult {
  /** Array of pinned event IDs */
  pinnedIds: number[];
  /** Check if an event is pinned */
  isPinned: (eventId: number) => boolean;
  /** Toggle pin status for an event */
  togglePin: (eventId: number) => void;
  /** Pin an event (no-op if already pinned or at max) */
  pin: (eventId: number) => boolean;
  /** Unpin an event */
  unpin: (eventId: number) => void;
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
    console.warn('Failed to save pinned events to localStorage');
  }
}

export function usePinnedEvents(): UsePinnedEventsResult {
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

  const isPinned = useCallback((eventId: number): boolean => {
    return pinnedIds.includes(eventId);
  }, [pinnedIds]);

  const pin = useCallback((eventId: number): boolean => {
    if (pinnedIds.includes(eventId)) return false;
    if (pinnedIds.length >= MAX_PINNED_EVENTS) return false;

    setPinnedIds(prev => [...prev, eventId]);
    return true;
  }, [pinnedIds]);

  const unpin = useCallback((eventId: number): void => {
    setPinnedIds(prev => prev.filter(id => id !== eventId));
  }, []);

  const togglePin = useCallback((eventId: number): void => {
    if (pinnedIds.includes(eventId)) {
      unpin(eventId);
    } else {
      pin(eventId);
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
    isMaxReached: pinnedIds.length >= MAX_PINNED_EVENTS,
  };
}
