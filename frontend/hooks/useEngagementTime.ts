'use client';

import { useEffect, useRef, useCallback } from 'react';
import { usePathname } from 'next/navigation';
import { useAnalyticsContext } from '@/components/Analytics';
import {
  GA_CONFIG,
  nextEngagementObservation,
  EMPTY_ENGAGEMENT_LEDGER,
  type EngagementLedger,
} from '@/lib/analytics';
import type { TimeOnPageParams } from '@/lib/analytics';

interface UseEngagementTimeOptions {
  /** Page type for categorization */
  pageType: TimeOnPageParams['page_type'];
  /** Event ID if on event detail page */
  eventId?: number;
  /** Whether tracking is enabled */
  enabled?: boolean;
}

interface EngagementState {
  /** When the user arrived on this page */
  startTime: number;
  /** Total time user has been actively engaged */
  activeTime: number;
  /** Whether user is currently active (tab visible) */
  isActive: boolean;
  /** Last time we recorded activity */
  lastActiveTime: number;
  /**
   * What this page has ALREADY reported. Every trigger emits only the delta
   * since the last emission, so a hide → unload → cleanup burst can no longer
   * report the same seconds three times (C90 P2).
   */
  ledger: EngagementLedger;
}

/**
 * Hook to track time spent on page
 *
 * Distinguishes between:
 * - Total time on page (including when tab is hidden)
 * - Active time (only when tab is visible and user is engaged)
 *
 * Sends engagement event when user leaves the page.
 */
export function useEngagementTime({
  pageType,
  eventId,
  enabled = true,
}: UseEngagementTimeOptions): void {
  const pathname = usePathname();
  const { track } = useAnalyticsContext();

  // Engagement state
  const state = useRef<EngagementState>({
    startTime: Date.now(),
    activeTime: 0,
    isActive: true,
    lastActiveTime: Date.now(),
    ledger: EMPTY_ENGAGEMENT_LEDGER,
  });

  const lastPathname = useRef(pathname);

  // Update active time
  const updateActiveTime = useCallback(() => {
    if (state.current.isActive) {
      const now = Date.now();
      state.current.activeTime += now - state.current.lastActiveTime;
      state.current.lastActiveTime = now;
    }
  }, []);

  // Send time on page event
  const sendTimeOnPage = useCallback(() => {
    if (!enabled) return;

    updateActiveTime();

    // Emit only what has NOT been reported for this page yet. `null` means the
    // trigger added nothing worth sending — the normal outcome for the second
    // and third fire of one hide → unload → cleanup burst.
    const observation = nextEngagementObservation({
      elapsedTotalMs: Date.now() - state.current.startTime,
      elapsedActiveMs: state.current.activeTime,
      ledger: state.current.ledger,
      minFirstSeconds: GA_CONFIG.ENGAGEMENT.MIN_ENGAGED_TIME,
    });
    if (!observation) return;

    // Commit the ledger BEFORE emitting so a re-entrant trigger (unload firing
    // during the same tick) cannot double-report the same span.
    state.current.ledger = observation.ledger;

    track('time_on_page', {
      page_type: pageType,
      seconds: observation.seconds,
      page_path: lastPathname.current,
      event_id: eventId,
      active_time_seconds: observation.activeSeconds,
    });
  }, [enabled, updateActiveTime, track, pageType, eventId]);

  // Handle visibility change
  const handleVisibilityChange = useCallback(() => {
    if (document.visibilityState === 'hidden') {
      // User switched away - update active time and pause
      updateActiveTime();
      state.current.isActive = false;

      // Send engagement data (user might not come back)
      sendTimeOnPage();
    } else {
      // User came back - resume tracking
      state.current.isActive = true;
      state.current.lastActiveTime = Date.now();
    }
  }, [updateActiveTime, sendTimeOnPage]);

  // Reset state when pathname changes
  useEffect(() => {
    if (pathname !== lastPathname.current) {
      // Send time for previous page
      sendTimeOnPage();

      // Reset state for new page — including a fresh ledger, so the new page
      // is measured from zero and re-honors the engagement floor.
      state.current = {
        startTime: Date.now(),
        activeTime: 0,
        isActive: !document.hidden,
        lastActiveTime: Date.now(),
        ledger: EMPTY_ENGAGEMENT_LEDGER,
      };
      lastPathname.current = pathname;
    }
  }, [pathname, sendTimeOnPage]);

  // Set up visibility listener
  useEffect(() => {
    if (!enabled || typeof document === 'undefined') return;

    document.addEventListener('visibilitychange', handleVisibilityChange);

    // Also send on beforeunload for reliability
    const handleUnload = () => {
      sendTimeOnPage();
    };
    window.addEventListener('beforeunload', handleUnload);

    // Periodic update of active time (every 30 seconds)
    const interval = setInterval(() => {
      if (state.current.isActive) {
        updateActiveTime();
      }
    }, 30000);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('beforeunload', handleUnload);
      clearInterval(interval);
      // Send final time on cleanup
      sendTimeOnPage();
    };
  }, [enabled, handleVisibilityChange, sendTimeOnPage, updateActiveTime]);
}

export default useEngagementTime;
