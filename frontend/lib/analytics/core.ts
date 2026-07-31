/**
 * Core Google Analytics 4 Functions
 *
 * This module provides type-safe wrappers around gtag.js
 * with support for:
 * - Consent Mode v2
 * - User-ID for cross-platform tracking
 * - Custom events with rich parameters
 * - Performance-optimized tracking (requestIdleCallback)
 */

import { GA_CONFIG, getPlatform, getStoredConsent, isAnalyticsConfigured } from './config';
import { sanitizeEvent } from './sanitize';
import type {
  AnalyticsEventMap,
  AnalyticsEventName,
  ConsentSettings,
  UserProperties,
} from './types';

// ============================================================================
// Type Definitions for gtag
// ============================================================================

type GtagFunction = (...args: any[]) => void;

declare global {
  interface Window {
    gtag: GtagFunction;
    dataLayer: unknown[];
  }
}

// ============================================================================
// State
// ============================================================================

let isInitialized = false;
let currentUserId: string | undefined;
/**
 * Whether the user has granted analytics consent. DENIED by default: no event
 * is emitted until an explicit stored/current choice grants it. `updateConsent`
 * is the only writer.
 */
let analyticsConsentGranted = false;
let sessionStartTime = Date.now();
let pagesViewed = 0;
/**
 * The page view withheld because consent was not yet granted. Only the MOST
 * RECENT one is kept: on a grant we owe the user's CURRENT page exactly once,
 * not a replay of everything they browsed while undecided. Cleared on denial.
 */
let withheldPageView: AnalyticsEventMap['page_view'] | null = null;
let eventsViewed = new Set<number>();
let sportsViewed = new Set<string>();
let usedFilters = false;
let viewedCharts = false;

// ============================================================================
// Initialization
// ============================================================================

/**
 * Initialize Google Analytics with consent mode
 */
export function initializeAnalytics(): void {
  if (typeof window === 'undefined' || isInitialized) return;
  // No measurement id → analytics is disabled entirely (never send to an
  // unexpected property). GoogleAnalytics.tsx also skips loading gtag.js.
  if (!isAnalyticsConfigured()) return;

  // Initialize dataLayer
  window.dataLayer = window.dataLayer || [];

  // Only create gtag function if not already defined by the inline script
  // The inline script in GoogleAnalytics.tsx defines it correctly
  if (typeof window.gtag !== 'function') {
    // eslint-disable-next-line prefer-rest-params
    window.gtag = function gtag() {
      // Must use arguments, not rest params, for gtag to work correctly
      window.dataLayer.push(arguments);
    };
  }

  // Set default consent (denied until user accepts)
  window.gtag('consent', 'default', GA_CONFIG.DEFAULT_CONSENT);

  // Check for stored consent and apply it
  const storedConsent = getStoredConsent();
  if (storedConsent) {
    updateConsent(storedConsent);
  }

  // Initialize gtag with timestamp
  window.gtag('js', new Date());

  // Configure GA4 with enhanced measurement disabled (we'll track manually for more control)
  window.gtag('config', GA_CONFIG.MEASUREMENT_ID, {
    send_page_view: false, // We'll send manually with rich params
    debug_mode: GA_CONFIG.DEBUG_MODE,
    // Custom dimensions
    custom_map: {
      dimension1: 'login_status',
      dimension2: 'platform',
      dimension3: 'preferred_sport',
    },
  });

  // Set platform
  window.gtag('set', {
    platform: getPlatform(),
  });

  sessionStartTime = Date.now();
  isInitialized = true;

  if (GA_CONFIG.DEBUG_MODE) {
    console.log('[Analytics] Initialized with Measurement ID:', GA_CONFIG.MEASUREMENT_ID);
  }
}

/**
 * Check if analytics is ready
 */
export function isAnalyticsReady(): boolean {
  return isInitialized && typeof window !== 'undefined' && typeof window.gtag === 'function';
}

// ============================================================================
// Consent Management
// ============================================================================

/**
 * Update consent settings
 */
export function updateConsent(level: 'all' | 'analytics' | 'none'): void {
  let consent: ConsentSettings;

  switch (level) {
    case 'all':
      consent = GA_CONFIG.GRANTED_CONSENT;
      break;
    case 'analytics':
      consent = GA_CONFIG.ANALYTICS_ONLY_CONSENT;
      break;
    case 'none':
    default:
      consent = {
        analytics_storage: 'denied' as const,
        ad_storage: 'denied' as const,
        ad_user_data: 'denied' as const,
        ad_personalization: 'denied' as const,
      };
      break;
  }

  // Update the local emission gate FIRST so it holds even if gtag is not yet
  // ready — no event is emitted until analytics is explicitly granted.
  analyticsConsentGranted = consent.analytics_storage === 'granted';

  // A denial must not leave a page view sitting in the buffer: if the user
  // later grants, they are owed the page they are on THEN, not the one they
  // declined on.
  if (!analyticsConsentGranted) {
    withheldPageView = null;
  }

  if (isAnalyticsReady()) {
    window.gtag('consent', 'update', consent);
  }

  if (GA_CONFIG.DEBUG_MODE) {
    console.log('[Analytics] Consent updated:', level, consent);
  }
}

/**
 * Whether analytics consent is currently granted (test/introspection helper).
 */
export function isConsentGranted(): boolean {
  return analyticsConsentGranted;
}

// ============================================================================
// User Identity
// ============================================================================

/**
 * Set user ID for cross-platform tracking
 */
export function setUserId(userId: string | undefined): void {
  if (!isAnalyticsReady()) return;

  currentUserId = userId;

  // Set on login; on logout explicitly push `user_id: null` so GA drops the
  // previously-configured identity before any subsequent anonymous event —
  // clearing the local ref alone left the id configured in gtag.
  window.gtag('config', GA_CONFIG.MEASUREMENT_ID, {
    user_id: userId ?? null,
  });

  if (GA_CONFIG.DEBUG_MODE) {
    console.log('[Analytics] User ID set:', userId ?? '(cleared)');
  }
}

/**
 * Set user properties
 */
export function setUserProperties(properties: Partial<UserProperties>): void {
  if (!isAnalyticsReady()) return;

  window.gtag('set', 'user_properties', properties);

  if (GA_CONFIG.DEBUG_MODE) {
    console.log('[Analytics] User properties set:', properties);
  }
}

/**
 * Get current user ID
 */
export function getUserId(): string | undefined {
  return currentUserId;
}

// ============================================================================
// Event Tracking
// ============================================================================

/**
 * Track an analytics event with type safety
 *
 * Uses requestIdleCallback for non-critical events to avoid blocking the main thread
 */
export function trackEvent<E extends AnalyticsEventName>(
  eventName: E,
  params: AnalyticsEventMap[E],
  options: { immediate?: boolean } = {}
): void {
  if (!isAnalyticsReady()) {
    if (GA_CONFIG.DEBUG_MODE) {
      console.log('[Analytics] Event queued (not ready):', eventName, params);
    }
    return;
  }

  // Consent gate: emit NOTHING until analytics is explicitly granted.
  if (!analyticsConsentGranted) {
    if (GA_CONFIG.DEBUG_MODE) {
      console.log('[Analytics] Event dropped (consent not granted):', eventName);
    }
    return;
  }

  const sendEvent = () => {
    // Add common parameters
    const enrichedParams = {
      ...params,
      // Timestamp for when event occurred
      event_timestamp: new Date().toISOString(),
      // Session info
      session_id: sessionStartTime.toString(),
      // Platform
      platform: getPlatform(),
    };

    // Central sanitation boundary: drop unknown events, strip unknown/PII
    // params, and reduce raw queries to bounded metadata before gtag sees them.
    const sanitized = sanitizeEvent(
      eventName,
      enrichedParams as unknown as Record<string, unknown>,
    );
    if (!sanitized) {
      if (GA_CONFIG.DEBUG_MODE) {
        console.log('[Analytics] Event dropped (unknown/blocked):', eventName);
      }
      return;
    }

    window.gtag('event', sanitized.name, sanitized.params);

    if (GA_CONFIG.DEBUG_MODE) {
      console.log('[Analytics] Event tracked:', sanitized.name, sanitized.params);
    }
  };

  // Use requestIdleCallback for non-critical events
  if (options.immediate || typeof requestIdleCallback === 'undefined') {
    sendEvent();
  } else {
    requestIdleCallback(sendEvent, { timeout: 2000 });
  }
}

/**
 * Track page view with rich parameters
 */
export function trackPageView(params: AnalyticsEventMap['page_view']): void {
  // Withhold rather than drop whenever we cannot emit YET — either consent is
  // not granted, or gtag has not finished loading. `trackEvent` would silently
  // discard both, which is why the landing page of a first-time visitor who
  // then pressed Accept — and of a returning visitor whose stored grant beat
  // gtag.js to the effect — was never counted (C90 P3). Keep ONLY the latest,
  // so the flush emits the current route and never replays a session.
  if (!analyticsConsentGranted || !isAnalyticsReady()) {
    withheldPageView = params;
    return;
  }

  pagesViewed++;

  // Exactly one page_view per call. GA4 auto page_view is disabled
  // (`send_page_view: false`), so this custom event is the single source of
  // truth — the previous extra `gtag('config', …)` re-send double-counted.
  trackEvent('page_view', params, { immediate: true });
}

/**
 * Emit the page view withheld before the grant — the user's CURRENT page,
 * exactly once. Called by the consent authority immediately after a grant.
 *
 * Returns whether an event was emitted. When gtag is not ready yet the buffer
 * is deliberately RETAINED (not dropped) so the landing page is still owed;
 * the next navigation overwrites it, so this can never emit a stale route.
 */
export function flushWithheldPageView(): boolean {
  if (!analyticsConsentGranted || !withheldPageView) return false;
  if (!isAnalyticsReady()) return false;

  const params = withheldPageView;
  withheldPageView = null;
  pagesViewed++;
  trackEvent('page_view', params, { immediate: true });
  return true;
}

/** Test/introspection helper: the currently withheld page view, if any. */
export function peekWithheldPageView(): AnalyticsEventMap['page_view'] | null {
  return withheldPageView;
}

// ============================================================================
// Session Tracking Helpers
// ============================================================================

/**
 * Record that an event was viewed (for session stats)
 */
export function recordEventViewed(eventId: number, sport?: string): void {
  eventsViewed.add(eventId);
  if (sport) {
    sportsViewed.add(sport);
  }
}

/**
 * Record that filters were used
 */
export function recordFilterUsed(): void {
  usedFilters = true;
}

/**
 * Record that charts were viewed
 */
export function recordChartViewed(): void {
  viewedCharts = true;
}

/**
 * Get session engagement data
 */
export function getSessionEngagement(): AnalyticsEventMap['session_engagement'] {
  return {
    events_viewed_count: eventsViewed.size,
    sports_browsed: Array.from(sportsViewed),
    pages_viewed: pagesViewed,
    session_duration_seconds: Math.round((Date.now() - sessionStartTime) / 1000),
    used_filters: usedFilters,
    viewed_charts: viewedCharts,
  };
}

/**
 * Send session engagement event (call on page unload)
 */
export function sendSessionEngagement(): void {
  const engagement = getSessionEngagement();

  // Only send if there was meaningful engagement
  if (engagement.pages_viewed > 0 || engagement.events_viewed_count > 0) {
    // Use sendBeacon for reliability on page unload
    if (isAnalyticsReady()) {
      trackEvent('session_engagement', engagement, { immediate: true });
    }
  }
}

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Debounce function for frequent events
 */
export function debounce<T extends (...args: any[]) => void>(
  func: T,
  wait: number
): (...args: Parameters<T>) => void {
  let timeout: ReturnType<typeof setTimeout> | null = null;

  return (...args: Parameters<T>) => {
    if (timeout) {
      clearTimeout(timeout);
    }
    timeout = setTimeout(() => {
      func(...args);
    }, wait);
  };
}

/**
 * Throttle function for scroll/resize events
 */
export function throttle<T extends (...args: any[]) => void>(
  func: T,
  limit: number
): (...args: Parameters<T>) => void {
  let inThrottle = false;

  return (...args: Parameters<T>) => {
    if (!inThrottle) {
      func(...args);
      inThrottle = true;
      setTimeout(() => {
        inThrottle = false;
      }, limit);
    }
  };
}

/**
 * Calculate minutes until/since event start
 */
export function calculateMinutesToStart(commenceTime: string): number {
  const start = new Date(commenceTime).getTime();
  const now = Date.now();
  return Math.round((start - now) / (1000 * 60));
}

/**
 * Determine if a game is "close" (within 10% of 50/50)
 */
export function isCloseGame(homeProb: number | null | undefined): boolean {
  if (homeProb === null || homeProb === undefined) return false;
  return Math.abs(homeProb - 0.5) < 0.1;
}
