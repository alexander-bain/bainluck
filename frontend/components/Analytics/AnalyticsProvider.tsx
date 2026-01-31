'use client';

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from 'react';
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
  }, []);

  // Handle consent change
  const setConsent = useCallback((level: 'all' | 'analytics' | 'none') => {
    setConsentState(level);
    storeConsent(level);
    updateConsent(level);
    setShowConsentBanner(false);
  }, []);

  // Dismiss banner (use default denied consent)
  const dismissBanner = useCallback(() => {
    setConsentState('none');
    storeConsent('none');
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
