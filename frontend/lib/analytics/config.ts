/**
 * Google Analytics Configuration
 */

export const GA_CONFIG = {
  /** GA4 Measurement ID */
  MEASUREMENT_ID: 'G-CY59Q6K975',

  /** Enable debug mode in development */
  DEBUG_MODE: process.env.NODE_ENV === 'development',

  /** Consent defaults - analytics enabled by default for US users */
  DEFAULT_CONSENT: {
    analytics_storage: 'granted' as const,
    ad_storage: 'denied' as const,
    ad_user_data: 'denied' as const,
    ad_personalization: 'denied' as const,
  },

  /** Consent when user accepts all */
  GRANTED_CONSENT: {
    analytics_storage: 'granted' as const,
    ad_storage: 'granted' as const,
    ad_user_data: 'granted' as const,
    ad_personalization: 'granted' as const,
  },

  /** Consent when user accepts analytics only */
  ANALYTICS_ONLY_CONSENT: {
    analytics_storage: 'granted' as const,
    ad_storage: 'denied' as const,
    ad_user_data: 'denied' as const,
    ad_personalization: 'denied' as const,
  },

  /** Local storage key for consent */
  CONSENT_STORAGE_KEY: 'oddstracker_consent',

  /** Local storage key for user preferences */
  USER_PREFS_STORAGE_KEY: 'oddstracker_analytics_prefs',

  /** Debounce times (ms) */
  DEBOUNCE: {
    SCROLL: 500,
    HOVER: 300,
    RESIZE: 250,
  },

  /** Engagement thresholds */
  ENGAGEMENT: {
    /** Scroll depth milestones to track */
    SCROLL_MILESTONES: [25, 50, 75, 90, 100] as const,
    /** Time thresholds for engagement tracking (seconds) */
    TIME_MILESTONES: [10, 30, 60, 120, 300] as const,
    /** Minimum time on page to count as engaged (seconds) */
    MIN_ENGAGED_TIME: 10,
  },

  /** Batch settings for impressions */
  IMPRESSION_BATCH: {
    /** Max items per batch */
    SIZE: 10,
    /** Delay before sending batch (ms) */
    DELAY: 1000,
  },
} as const;

/**
 * Platform detection
 */
export function getPlatform(): 'web' | 'ios' | 'android' {
  if (typeof window === 'undefined') return 'web';

  const userAgent = window.navigator.userAgent.toLowerCase();

  // Check if running in a webview (future app integration)
  if ((window as unknown as { ReactNativeWebView?: unknown }).ReactNativeWebView) {
    if (/iphone|ipad|ipod/.test(userAgent)) return 'ios';
    if (/android/.test(userAgent)) return 'android';
  }

  return 'web';
}

/**
 * Get stored consent preference
 */
export function getStoredConsent(): 'all' | 'analytics' | 'none' | null {
  if (typeof window === 'undefined') return null;

  try {
    const stored = localStorage.getItem(GA_CONFIG.CONSENT_STORAGE_KEY);
    if (stored === 'all' || stored === 'analytics' || stored === 'none') {
      return stored;
    }
    return null;
  } catch {
    return null;
  }
}

/**
 * Store consent preference
 */
export function storeConsent(consent: 'all' | 'analytics' | 'none'): void {
  if (typeof window === 'undefined') return;

  try {
    localStorage.setItem(GA_CONFIG.CONSENT_STORAGE_KEY, consent);
  } catch {
    // Silently fail if localStorage is not available
  }
}
