/**
 * Google Analytics Configuration
 */

export const GA_CONFIG = {
  /**
   * GA4 Measurement ID — read from the environment, never hardcoded.
   *
   * `NEXT_PUBLIC_GA_MEASUREMENT_ID` is a public, build-time-inlined value (a GA
   * measurement id is not a secret). When it is absent, analytics is DISABLED
   * (`isAnalyticsConfigured()` → false) rather than silently sending hits to an
   * unexpected/hardcoded property. Set it in `.env.production` (committed) and
   * the Vercel dashboard for production builds.
   */
  MEASUREMENT_ID: process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID,

  /** Enable debug mode in development */
  DEBUG_MODE: process.env.NODE_ENV === 'development',

  /**
   * Consent defaults — DENIED by default (Consent Mode v2). No analytics
   * storage until the user makes an explicit choice; every ads-related state
   * stays denied because the product has no ads.
   */
  DEFAULT_CONSENT: {
    analytics_storage: 'denied' as const,
    ad_storage: 'denied' as const,
    ad_user_data: 'denied' as const,
    ad_personalization: 'denied' as const,
  },

  /**
   * Consent when the user accepts. The product has no ads, so ads states stay
   * denied even on "Accept" — only analytics is granted.
   */
  GRANTED_CONSENT: {
    analytics_storage: 'granted' as const,
    ad_storage: 'denied' as const,
    ad_user_data: 'denied' as const,
    ad_personalization: 'denied' as const,
  },

  /** Consent when user accepts analytics only (identical: no ads product) */
  ANALYTICS_ONLY_CONSENT: {
    analytics_storage: 'granted' as const,
    ad_storage: 'denied' as const,
    ad_user_data: 'denied' as const,
    ad_personalization: 'denied' as const,
  },

  /** Local storage key for consent */
  CONSENT_STORAGE_KEY: 'bainluck_consent',

  /** Local storage key for user preferences */
  USER_PREFS_STORAGE_KEY: 'bainluck_analytics_prefs',

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
 * Whether analytics is configured to run. False when
 * `NEXT_PUBLIC_GA_MEASUREMENT_ID` is unset — in that case we never load gtag,
 * never initialize, and never emit, rather than sending to an unexpected
 * property. Callers should short-circuit on this.
 */
export function isAnalyticsConfigured(): boolean {
  return (
    typeof GA_CONFIG.MEASUREMENT_ID === 'string' &&
    GA_CONFIG.MEASUREMENT_ID.length > 0
  );
}

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
 * Whether a consent write is actually durable.
 *
 * `'saved'` is only returned after an EXACT readback of the value we just
 * wrote. `'unavailable'` means the choice is in effect for this document but
 * will NOT survive a reload.
 */
export type ConsentPersistResult = 'saved' | 'unavailable';

/**
 * Store the consent preference and PROVE it landed (L2-222 Item 1 / #1453).
 *
 * BEFORE: this swallowed every failure. Safari private mode, a full quota, and
 * a no-op storage shim all looked identical to success, so the UI said "saved"
 * and the revoke path hard-reloaded into a document that read the OLD grant
 * back — the reload re-enabled exactly what the user had just switched off, and
 * nothing anywhere could tell. A silent no-op write is the worst case for a
 * consent store precisely because the recovery (say so, keep the in-memory
 * denial) is cheap and the failure is invisible.
 *
 * NOW: write, then read back and compare EXACTLY. A throwing store, a quota
 * rejection, and a shim whose `setItem` does nothing are all reported as
 * `'unavailable'`. Callers must not claim "saved", and must not reload on the
 * strength of a write they cannot verify.
 */
export function storeConsent(consent: 'all' | 'analytics' | 'none'): ConsentPersistResult {
  if (typeof window === 'undefined') return 'unavailable';

  try {
    localStorage.setItem(GA_CONFIG.CONSENT_STORAGE_KEY, consent);
  } catch {
    // Throwing store (Safari private mode, quota exceeded, blocked origin).
    return 'unavailable';
  }

  try {
    // The no-op case: `setItem` accepted the call and stored nothing. Only an
    // exact match counts — a stale prior value reads back fine but is a lie.
    return localStorage.getItem(GA_CONFIG.CONSENT_STORAGE_KEY) === consent
      ? 'saved'
      : 'unavailable';
  } catch {
    return 'unavailable';
  }
}
