'use client';

import { useEffect, useRef } from 'react';
import { usePathname } from 'next/navigation';
import { useAnalyticsContext } from '@/components/Analytics';
import type { PageViewParams } from '@/lib/analytics';

interface UsePageTrackingOptions {
  /** Page type for categorization */
  pageType: PageViewParams['page_type'];
  /** Custom page title (defaults to document.title) */
  pageTitle?: string;
  /** Additional parameters */
  additionalParams?: Partial<PageViewParams>;
  /** Dependencies that should trigger a re-track when changed */
  deps?: unknown[];
}

/**
 * Hook to track page views automatically
 *
 * Tracks page view on mount and when pathname changes.
 * Also handles referrer detection and navigation source tracking.
 */
export function usePageTracking({
  pageType,
  pageTitle,
  additionalParams = {},
  deps = [],
}: UsePageTrackingOptions): void {
  const pathname = usePathname();
  const { pageView } = useAnalyticsContext();
  const hasTracked = useRef(false);
  const lastPathname = useRef(pathname);
  const lastDeps = useRef(deps);

  useEffect(() => {
    // Determine if we should track
    const pathnameChanged = pathname !== lastPathname.current;
    const depsChanged = JSON.stringify(deps) !== JSON.stringify(lastDeps.current);
    const shouldTrack = !hasTracked.current || pathnameChanged || depsChanged;

    if (!shouldTrack) return;

    // Determine navigation source
    let navigationSource: PageViewParams['navigation_source'] = 'direct';
    if (typeof document !== 'undefined' && document.referrer) {
      try {
        const referrerUrl = new URL(document.referrer);
        const currentUrl = new URL(window.location.href);
        if (referrerUrl.hostname === currentUrl.hostname) {
          navigationSource = 'internal';
        } else {
          navigationSource = 'external';
        }
      } catch {
        navigationSource = 'external';
      }
    }

    // Get page title
    const title = pageTitle || (typeof document !== 'undefined' ? document.title : '');

    // Track page view
    pageView({
      page_type: pageType,
      page_path: pathname,
      page_title: title,
      referrer: typeof document !== 'undefined' ? document.referrer : undefined,
      navigation_source: navigationSource,
      ...additionalParams,
    });

    // Update refs
    hasTracked.current = true;
    lastPathname.current = pathname;
    lastDeps.current = deps;
  }, [pathname, pageType, pageTitle, additionalParams, deps, pageView]);
}

export default usePageTracking;
