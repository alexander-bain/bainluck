/**
 * Analytics Module - Main Entry Point
 *
 * Usage:
 *
 * ```typescript
 * import { analytics } from '@/lib/analytics';
 *
 * // Track a page view
 * analytics.pageView({
 *   page_type: 'home',
 *   page_path: '/',
 *   page_title: 'Bain Luck - Home',
 * });
 *
 * // Track an event
 * analytics.track('event_card_click', {
 *   event_id: 123,
 *   sport: 'basketball_nba',
 *   // ... other params
 * });
 *
 * // Set user (on login)
 * analytics.setUser('user_123');
 *
 * // Update consent
 * analytics.updateConsent('all');
 * ```
 */

export * from './types';
export * from './config';
export * from './sanitize';
export {
  initializeAnalytics,
  isAnalyticsReady,
  updateConsent,
  isConsentGranted,
  setUserId,
  setUserProperties,
  trackEvent,
  trackPageView,
  recordEventViewed,
  recordFilterUsed,
  recordChartViewed,
  getSessionEngagement,
  sendSessionEngagement,
  debounce,
  throttle,
  calculateMinutesToStart,
  isCloseGame,
  getUserId,
} from './core';

// ============================================================================
// Convenience API
// ============================================================================

import {
  initializeAnalytics,
  updateConsent,
  setUserId,
  setUserProperties,
  trackEvent,
  trackPageView,
  recordEventViewed,
  recordFilterUsed,
  recordChartViewed,
  sendSessionEngagement,
} from './core';
import type { AnalyticsEventMap, AnalyticsEventName, UserProperties } from './types';

/**
 * Main analytics object with convenient methods
 */
export const analytics = {
  /**
   * Initialize analytics (call once on app load)
   */
  init: initializeAnalytics,

  /**
   * Track a page view
   */
  pageView: trackPageView,

  /**
   * Track any event
   */
  track: <E extends AnalyticsEventName>(
    eventName: E,
    params: AnalyticsEventMap[E],
    options?: { immediate?: boolean }
  ) => trackEvent(eventName, params, options),

  /**
   * Set user ID (on login)
   */
  setUser: setUserId,

  /**
   * Clear user ID (on logout)
   */
  clearUser: () => setUserId(undefined),

  /**
   * Set user properties
   */
  setUserProperties,

  /**
   * Update consent settings
   */
  updateConsent,

  /**
   * Record that an event detail page was viewed
   */
  recordEventViewed,

  /**
   * Record that filters were used
   */
  recordFilterUsed,

  /**
   * Record that charts were viewed
   */
  recordChartViewed,

  /**
   * Send session engagement (on page unload)
   */
  sendSessionEngagement,
};

export default analytics;
