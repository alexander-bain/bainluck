/**
 * usePinnedEvents - Hook for managing pinned events
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

const STORAGE_KEY = 'bainluck_pinnedEvents';
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
        const merged = Array.from(new Set([...serverPins.events, ...localPins]));

        setPinnedIds(merged);
        savePinnedIds(merged);
        hasLoadedFromServer.current = true;

        // If localStorage had pins the server didn't, push them up
        const serverSet = new Set(serverPins.events);
        const localOnly = localPins.filter(id => !serverSet.has(id));
        for (const id of localOnly) {
          try {
            await addPin('event', id);
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

  const isPinned = useCallback((eventId: number): boolean => {
    return pinnedIds.includes(eventId);
  }, [pinnedIds]);

  const pin = useCallback((eventId: number): boolean => {
    if (pinnedIds.includes(eventId)) return false;
    if (pinnedIds.length >= MAX_PINNED_EVENTS) return false;

    setPinnedIds(prev => [...prev, eventId]);

    // Sync to server
    if (isAuthenticated) {
      addPin('event', eventId).catch(err =>
        console.warn('Failed to sync pin to server:', err)
      );
    }

    return true;
  }, [pinnedIds, isAuthenticated]);

  const unpin = useCallback((eventId: number): void => {
    setPinnedIds(prev => prev.filter(id => id !== eventId));

    // Sync to server
    if (isAuthenticated) {
      removePin('event', eventId).catch(err =>
        console.warn('Failed to sync unpin to server:', err)
      );
    }
  }, [isAuthenticated]);

  const togglePin = useCallback((eventId: number): void => {
    if (pinnedIds.includes(eventId)) {
      unpin(eventId);
    } else {
      pin(eventId);
    }
  }, [pinnedIds, pin, unpin]);

  const clearAll = useCallback((): void => {
    // Remove each from server
    if (isAuthenticated) {
      for (const id of pinnedIds) {
        removePin('event', id).catch(err =>
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
    isMaxReached: pinnedIds.length >= MAX_PINNED_EVENTS,
  };
}
