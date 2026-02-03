'use client';

import { useEffect, useRef, useCallback } from 'react';
import { usePathname } from 'next/navigation';
import { useAnalyticsContext } from '@/components/Analytics';
import { GA_CONFIG, throttle } from '@/lib/analytics';
import type { ScrollDepthParams } from '@/lib/analytics';

interface UseScrollDepthOptions {
  /** Page type for categorization */
  pageType: ScrollDepthParams['page_type'];
  /** Event ID if on event detail page */
  eventId?: number;
  /** Whether tracking is enabled */
  enabled?: boolean;
}

/**
 * Hook to track scroll depth milestones
 *
 * Tracks when user scrolls past 25%, 50%, 75%, 90%, and 100% of the page.
 * Each milestone is only tracked once per page view.
 */
export function useScrollDepth({
  pageType,
  eventId,
  enabled = true,
}: UseScrollDepthOptions): void {
  const pathname = usePathname();
  const { track } = useAnalyticsContext();

  // Track which milestones have been reached
  const reachedMilestones = useRef<Set<number>>(new Set());
  const lastPathname = useRef(pathname);

  // Reset milestones when pathname changes
  useEffect(() => {
    if (pathname !== lastPathname.current) {
      reachedMilestones.current = new Set();
      lastPathname.current = pathname;
    }
  }, [pathname]);

  // Calculate scroll percentage
  const calculateScrollPercent = useCallback((): number => {
    if (typeof window === 'undefined') return 0;

    const scrollTop = window.scrollY || document.documentElement.scrollTop;
    const scrollHeight = document.documentElement.scrollHeight;
    const clientHeight = window.innerHeight;
    const scrollableHeight = scrollHeight - clientHeight;

    if (scrollableHeight <= 0) return 100;

    return Math.min(100, Math.round((scrollTop / scrollableHeight) * 100));
  }, []);

  // Check and track milestones
  const checkMilestones = useCallback(() => {
    if (!enabled) return;

    const scrollPercent = calculateScrollPercent();

    for (const milestone of GA_CONFIG.ENGAGEMENT.SCROLL_MILESTONES) {
      if (scrollPercent >= milestone && !reachedMilestones.current.has(milestone)) {
        reachedMilestones.current.add(milestone);

        track('scroll_depth', {
          page_type: pageType,
          depth_percent: milestone as 25 | 50 | 75 | 90 | 100,
          page_path: pathname,
          event_id: eventId,
        });
      }
    }
  }, [enabled, calculateScrollPercent, track, pageType, pathname, eventId]);

  // Throttled scroll handler
  const handleScroll = useRef(throttle(checkMilestones, GA_CONFIG.DEBOUNCE.SCROLL));

  // Set up scroll listener
  useEffect(() => {
    if (!enabled || typeof window === 'undefined') return;

    // Check initial position (in case page is already scrolled)
    checkMilestones();

    // Add scroll listener
    window.addEventListener('scroll', handleScroll.current, { passive: true });

    return () => {
      window.removeEventListener('scroll', handleScroll.current);
    };
  }, [enabled, checkMilestones]);
}

export default useScrollDepth;
