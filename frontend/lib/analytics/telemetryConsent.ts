/**
 * The single web telemetry consent authority (L2-218, Item 1 / #1453).
 *
 * BEFORE: the consent state machine governed only the custom GA wrapper.
 * `<Analytics />` (Vercel Analytics) and `<SpeedInsights />` were mounted
 * unconditionally in the root layout, so "Decline" could not stop them and the
 * banner overstated what the choice did (C90 P1).
 *
 * NOW: every non-essential web telemetry provider — GA, Vercel Analytics,
 * Vercel Speed Insights, and the custom Web Vitals rail — reads its enablement
 * from THIS module, and only this module writes the persisted choice. There is
 * one decision function (`decideTelemetry`) and one store; a provider cannot
 * drift from the banner because there is nowhere else to ask.
 *
 * Design notes:
 *  - The store is framework-free and synchronously readable so it can back
 *    `useSyncExternalStore` in a client component AND be unit-tested without a
 *    DOM (this repo's jest runs in `node`, no jsdom).
 *  - `decideTelemetry` is pure: given a consent level it returns which
 *    providers may run. Everything user-visible about the choice is derived
 *    from it, including the banner copy contract test.
 *  - Writing consent is a single call (`setTelemetryConsent`) that persists,
 *    pushes the GA Consent Mode update, flushes a page view withheld before the
 *    grant, and notifies subscribers — in that order.
 */

import { getStoredConsent, storeConsent, isAnalyticsConfigured } from './config';
import { updateConsent, flushWithheldPageView } from './core';

export type ConsentLevel = 'all' | 'analytics' | 'none' | null;

/**
 * Which non-essential telemetry providers may run. `essential` behavior (the
 * consent choice itself, auth, app functionality) is not represented here — it
 * is never gated and never sends telemetry.
 */
export interface TelemetryDecision {
  /** Custom GA4 rail (gtag.js + `trackEvent`). */
  googleAnalytics: boolean;
  /** `@vercel/analytics` — page/visitor counts sent to Vercel. */
  vercelAnalytics: boolean;
  /** `@vercel/speed-insights` — RUM performance beacons sent to Vercel. */
  speedInsights: boolean;
  /** Custom Core Web Vitals events (ride the GA rail). */
  webVitals: boolean;
}

const NOTHING: TelemetryDecision = {
  googleAnalytics: false,
  vercelAnalytics: false,
  speedInsights: false,
  webVitals: false,
};

/**
 * Whether a consent level counts as an analytics grant. `null` (no choice yet)
 * and `'none'` are BOTH denials — first visit must produce zero non-essential
 * telemetry, exactly like an explicit Decline.
 */
export function isAnalyticsGranted(consent: ConsentLevel): boolean {
  return consent === 'all' || consent === 'analytics';
}

/**
 * The pure decision. One grant governs every provider; the only asymmetry is
 * that the GA rail additionally requires a configured measurement id (without
 * one we never load gtag.js at all, rather than send to an unexpected
 * property). Vercel's providers need no id, so a missing GA id must not
 * silently re-enable them.
 */
export function decideTelemetry(
  consent: ConsentLevel,
  opts: { gaConfigured?: boolean } = {},
): TelemetryDecision {
  if (!isAnalyticsGranted(consent)) return NOTHING;
  const gaConfigured = opts.gaConfigured ?? isAnalyticsConfigured();
  return {
    googleAnalytics: gaConfigured,
    vercelAnalytics: true,
    speedInsights: true,
    webVitals: gaConfigured,
  };
}

// ============================================================================
// Store
// ============================================================================

let current: ConsentLevel = null;
let initialized = false;
const listeners = new Set<() => void>();
/** Recomputed on every change so `useSyncExternalStore` gets a stable ref. */
let snapshot: TelemetryDecision = NOTHING;

function recompute(): void {
  snapshot = decideTelemetry(current);
}

function notify(): void {
  for (const fn of Array.from(listeners)) {
    try {
      fn();
    } catch {
      /* a bad subscriber must never break the consent rail */
    }
  }
}

/**
 * Hydrate the authority from the persisted choice. Idempotent — safe under
 * React Strict Mode double-invocation and repeated provider remounts. Returns
 * the resolved level.
 */
export function initTelemetryConsent(): ConsentLevel {
  if (initialized) return current;
  initialized = true;
  current = getStoredConsent();
  recompute();
  if (current) {
    // Re-assert the stored choice on the GA rail. `updateConsent` is the only
    // writer of the emission gate and is safe to call before gtag is ready.
    updateConsent(current);
  }
  notify();
  return current;
}

/** The current persisted/chosen level (`null` = no choice made yet). */
export function getTelemetryConsent(): ConsentLevel {
  return current;
}

/** The current provider decision. Stable reference between changes. */
export function getTelemetryDecision(): TelemetryDecision {
  return snapshot;
}

/** SSR snapshot: nothing is ever enabled during server render. */
export function getServerTelemetryDecision(): TelemetryDecision {
  return NOTHING;
}

/**
 * Record an explicit choice. This is the ONLY supported way to change consent:
 * it persists, updates GA Consent Mode + the emission gate, releases the page
 * view withheld before the grant, and then notifies provider gates.
 */
export function setTelemetryConsent(level: 'all' | 'analytics' | 'none'): void {
  initialized = true;
  current = level;
  storeConsent(level);
  // Opens (or closes) the emission gate. On a denial this also clears the
  // withheld page view, so the flush below can only ever fire after a grant.
  updateConsent(level);
  // Release the ONE page view withheld before the choice — the route the user
  // is on right now. Not a replay: only the latest withheld view is kept.
  flushWithheldPageView();
  recompute();
  notify();
}

/** Subscribe to decision changes. Returns an unsubscribe function. */
export function subscribeTelemetryConsent(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/**
 * Test-only reset. Production code never calls this; the store is otherwise
 * process-lifetime state (jest isolates via `jest.resetModules()`).
 */
export function __resetTelemetryConsentForTests(): void {
  current = null;
  initialized = false;
  snapshot = NOTHING;
  listeners.clear();
}
