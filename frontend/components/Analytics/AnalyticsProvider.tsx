'use client';

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from 'react';
import { usePathname } from 'next/navigation';
import { SEARCH_DEST_KEY, SEARCH_DEST_MAX_AGE_MS, type SearchDestCrumb } from '@/lib/searchFunnel';
import {
  getStoredConsent,
  storeConsent,
  updateConsent,
  setUserId,
  setUserProperties,
  trackEvent,
  trackPageView,
  recordEventViewed,
  recordFilterUsed,
  recordChartViewed,
  type AnalyticsEventMap,
  type AnalyticsEventName,
  type UserProperties,
} from '@/lib/analytics';

// ============================================================================
// Context Types
// ============================================================================

type ConsentLevel = 'all' | 'analytics' | 'none' | null;

interface AnalyticsContextValue {
  /** Current consent level (null = not yet chosen) */
  consent: ConsentLevel;
  /** Whether consent banner should be shown */
  showConsentBanner: boolean;
  /** Update consent level */
  setConsent: (level: 'all' | 'analytics' | 'none') => void;
  /** Dismiss banner without choice (uses defaults) */
  dismissBanner: () => void;
  /** Track an event */
  track: <E extends AnalyticsEventName>(
    eventName: E,
    params: AnalyticsEventMap[E]
  ) => void;
  /** Track a page view */
  pageView: (params: AnalyticsEventMap['page_view']) => void;
  /** Set user ID (on login) */
  setUser: (userId: string | undefined) => void;
  /** Set user properties */
  setProperties: (properties: Partial<UserProperties>) => void;
  /** Record event viewed (for session stats) */
  recordEvent: (eventId: number, sport?: string) => void;
  /** Record filter used */
  recordFilter: () => void;
  /** Record chart viewed */
  recordChart: () => void;
}

// ============================================================================
// Context
// ============================================================================

const AnalyticsContext = createContext<AnalyticsContextValue | null>(null);

// ============================================================================
// Provider Component
// ============================================================================

interface AnalyticsProviderProps {
  children: ReactNode;
}

export function AnalyticsProvider({ children }: AnalyticsProviderProps) {
  const [consent, setConsentState] = useState<ConsentLevel>(null);
  const [showConsentBanner, setShowConsentBanner] = useState(false);
  const [isInitialized, setIsInitialized] = useState(false);
  const pathname = usePathname();

  // Check for stored consent on mount
  useEffect(() => {
    const stored = getStoredConsent();
    if (stored) {
      setConsentState(stored);
      updateConsent(stored);
      setShowConsentBanner(false);
    } else {
      // No stored consent - show banner after a short delay
      // This avoids layout shift on initial load
      const timer = setTimeout(() => {
        setShowConsentBanner(true);
      }, 1500);
      return () => clearTimeout(timer);
    }
    setIsInitialized(true);

    // Return visit tracking
    try {
      const lastVisit = localStorage.getItem('bainluck_last_visit');
      const sessionCount = parseInt(localStorage.getItem('bainluck_session_count') || '0', 10) + 1;
      localStorage.setItem('bainluck_session_count', String(sessionCount));
      const now = new Date().toISOString().split('T')[0];
      localStorage.setItem('bainluck_last_visit', now);
      if (lastVisit && lastVisit !== now) {
        const daysSince = Math.round(
          (new Date(now).getTime() - new Date(lastVisit).getTime()) / 86400000
        );
        if (daysSince > 0) {
          trackEvent('return_visit', {
            days_since_last: daysSince,
            session_number: sessionCount,
          }, { immediate: true });
        }
      }
    } catch { /* localStorage unavailable */ }
  }, []);

  // SEARCH funnel step 4 (measurement_spec §2): the "Lisa metric". When the route
  // changes to a non-search destination and a fresh search-click breadcrumb exists,
  // emit `destination_engaged` once the user engages (first scroll, or a >=4s dwell).
  // The breadcrumb is consumed immediately so a bounce (navigating away before
  // engaging) correctly yields no event, and engagement is only ever attributed to
  // the FIRST destination after the click.
  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (!pathname || pathname.startsWith('/search')) return;

    let raw: string | null = null;
    try {
      raw = sessionStorage.getItem(SEARCH_DEST_KEY);
    } catch {
      return;
    }
    if (!raw) return;

    try {
      sessionStorage.removeItem(SEARCH_DEST_KEY);
    } catch { /* ignore */ }

    let crumb: SearchDestCrumb;
    try {
      crumb = JSON.parse(raw) as SearchDestCrumb;
    } catch {
      return;
    }
    if (Date.now() - (crumb.ts || 0) > SEARCH_DEST_MAX_AGE_MS) return;

    const start = Date.now();
    let fired = false;
    const fire = () => {
      if (fired) return;
      fired = true;
      trackEvent('destination_engaged', {
        query: crumb.query,
        result_type: crumb.result_type,
        result_id: crumb.result_id,
        rank: crumb.rank,
        dwell_ms: Date.now() - start,
        surface: 'search',
      }, { immediate: true });
    };

    const timer = window.setTimeout(fire, 4000);
    const onScroll = () => fire();
    window.addEventListener('scroll', onScroll, { passive: true, once: true });

    return () => {
      window.clearTimeout(timer);
      window.removeEventListener('scroll', onScroll);
    };
  }, [pathname]);

  // Handle consent change
  const setConsent = useCallback((level: 'all' | 'analytics' | 'none') => {
    setConsentState(level);
    storeConsent(level);
    updateConsent(level);
    setShowConsentBanner(false);
  }, []);

  // Dismiss banner = explicit denial. Persist AND push a denied consent update
  // (previously it stored 'none' but never told gtag, leaving default state).
  const dismissBanner = useCallback(() => {
    setConsentState('none');
    storeConsent('none');
    updateConsent('none');
    setShowConsentBanner(false);
  }, []);

  // Track event wrapper
  const track = useCallback(<E extends AnalyticsEventName>(
    eventName: E,
    params: AnalyticsEventMap[E]
  ) => {
    trackEvent(eventName, params);
  }, []);

  // Page view wrapper
  const pageView = useCallback((params: AnalyticsEventMap['page_view']) => {
    trackPageView(params);
  }, []);

  // Set user wrapper
  const setUser = useCallback((userId: string | undefined) => {
    setUserId(userId);
    if (userId) {
      setUserProperties({ login_status: 'logged_in' });
    } else {
      setUserProperties({ login_status: 'anonymous' });
    }
  }, []);

  // Set properties wrapper
  const setProperties = useCallback((properties: Partial<UserProperties>) => {
    setUserProperties(properties);
  }, []);

  // Record event wrapper
  const recordEvent = useCallback((eventId: number, sport?: string) => {
    recordEventViewed(eventId, sport);
  }, []);

  // Record filter wrapper
  const recordFilter = useCallback(() => {
    recordFilterUsed();
  }, []);

  // Record chart wrapper
  const recordChart = useCallback(() => {
    recordChartViewed();
  }, []);

  const value: AnalyticsContextValue = {
    consent,
    showConsentBanner,
    setConsent,
    dismissBanner,
    track,
    pageView,
    setUser,
    setProperties,
    recordEvent,
    recordFilter,
    recordChart,
  };

  return (
    <AnalyticsContext.Provider value={value}>
      {children}
    </AnalyticsContext.Provider>
  );
}

// ============================================================================
// Hook
// ============================================================================

/**
 * Hook to access analytics context
 */
export function useAnalyticsContext(): AnalyticsContextValue {
  const context = useContext(AnalyticsContext);
  if (!context) {
    throw new Error('useAnalyticsContext must be used within an AnalyticsProvider');
  }
  return context;
}

export default AnalyticsProvider;
