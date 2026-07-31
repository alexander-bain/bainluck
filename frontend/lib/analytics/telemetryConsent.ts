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

import {
  GA_CONFIG,
  getStoredConsent,
  storeConsent,
  isAnalyticsConfigured,
  type ConsentPersistResult,
} from './config';
import { updateConsent, flushWithheldPageView } from './core';

export type ConsentLevel = 'all' | 'analytics' | 'none' | null;

/**
 * Durability of the CURRENT choice.
 *  - `'unknown'`  — no explicit choice has been recorded yet.
 *  - `'saved'`    — written and read back exactly; it survives a reload.
 *  - `'unavailable'` — the choice is honoured for this document only. Durable
 *    storage refused it (private mode, quota, a no-op shim). Recoverable: the
 *    user can retry, and the UI must not claim the choice was saved.
 */
export type ConsentPersistence = 'unknown' | ConsentPersistResult;

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
let persistence: ConsentPersistence = 'unknown';
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
  // A choice we read back OUT of storage is durable by definition.
  persistence = current ? 'saved' : 'unknown';
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
 * Durability of the current choice. `'unavailable'` is the recoverable failure
 * state: the choice is in force for this document but will not survive a
 * reload, so the UI must say so rather than claim "saved".
 */
export function getConsentPersistence(): ConsentPersistence {
  return persistence;
}

/**
 * Record an explicit choice. This is the ONLY supported way to change consent:
 * it persists, updates GA Consent Mode + the emission gate, releases the page
 * view withheld before the grant, and then notifies provider gates.
 *
 * Returns whether the choice is DURABLE. The in-memory effect is applied either
 * way — a browser that refuses to remember a denial must still honour it now —
 * but callers that are about to reload, or about to tell the user their choice
 * was saved, have to check this first (L2-222 Item 1).
 */
export function setTelemetryConsent(
  level: 'all' | 'analytics' | 'none',
): ConsentPersistResult {
  initialized = true;
  current = level;
  // Verified write: `'saved'` only after an exact readback (see config.ts).
  persistence = storeConsent(level);
  // Opens (or closes) the emission gate. On a denial this also clears the
  // withheld page view, so the flush below can only ever fire after a grant.
  updateConsent(level);
  // Release the ONE page view withheld before the choice — the route the user
  // is on right now. Not a replay: only the latest withheld view is kept.
  flushWithheldPageView();
  recompute();
  notify();
  return persistence as ConsentPersistResult;
}

// ============================================================================
// Cross-tab synchronization (L2-222 Item 1)
// ============================================================================

/**
 * What an external storage change did. Returned so the caller (and the tests)
 * can assert the loop guards directly rather than inferring them from effects.
 */
export type ExternalConsentOutcome =
  /** Not our key, not a real change, or an unparseable value — nothing done. */
  | 'ignored'
  /** Adopted in this tab; providers were already permitted by the new level. */
  | 'applied'
  /** Adopted AND this tab must reload to actually unload live providers. */
  | 'applied_requires_reload';

/**
 * Adopt a consent change made in ANOTHER tab.
 *
 * Two tabs sharing one origin share one consent store, so a revoke in tab B
 * left tab A running every provider while its own UI happily said "off" on next
 * render. This closes tab A's gate from tab B's write.
 *
 * The guards are the whole design:
 *  - **Only our key.** Any other storage write is ignored.
 *  - **Only valid values.** A corrupted/deleted value is ignored rather than
 *    coerced — silently treating garbage as a denial would flip a grant the
 *    user never revoked, and treating it as a grant would be worse.
 *  - **Only real changes.** Same-value events are ignored. This is the loop
 *    guard: we never write back to storage here, and a no-op cannot re-notify.
 *  - **Denial closes the gate IMMEDIATELY**, before any reload decision. The
 *    reload is what unloads already-executed provider scripts, but the
 *    in-document emission gate must not wait for it.
 *  - **Reload only after verified stored denial.** We re-read the store and
 *    require it to still say `'none'`. A reload triggered by an event we
 *    could not confirm would come back up on whatever is actually stored,
 *    which may be the grant we just tried to leave.
 */
export function handleExternalConsentChange(
  key: string | null,
  newValue: string | null,
  opts: { gaConfigured?: boolean } = {},
): ExternalConsentOutcome {
  if (key !== GA_CONFIG.CONSENT_STORAGE_KEY) return 'ignored';
  if (newValue !== 'all' && newValue !== 'analytics' && newValue !== 'none') {
    return 'ignored';
  }
  if (newValue === current) return 'ignored';

  const gaConfigured = opts.gaConfigured ?? isAnalyticsConfigured();
  const before = decideTelemetry(current, { gaConfigured });

  initialized = true;
  current = newValue;
  // The other tab did the writing. Re-writing here is what would create a
  // storage-event ping-pong, so this path deliberately never calls storeConsent.
  persistence = 'saved';
  updateConsent(newValue);
  if (isAnalyticsGranted(newValue)) {
    // A grant arriving from another tab still owes this tab's current page.
    flushWithheldPageView();
  }
  recompute();
  notify();

  const after = decideTelemetry(newValue, { gaConfigured });
  const wasLive =
    before.googleAnalytics || before.vercelAnalytics || before.speedInsights || before.webVitals;
  const nowLive =
    after.googleAnalytics || after.vercelAnalytics || after.speedInsights || after.webVitals;
  if (!(wasLive && !nowLive)) return 'applied';

  // Verify the denial is really what is stored before reloading on it.
  return getStoredConsent() === newValue ? 'applied_requires_reload' : 'applied';
}

export interface ConsentSyncDeps {
  addEventListener?: (type: 'storage', handler: (e: StorageEvent) => void) => void;
  removeEventListener?: (type: 'storage', handler: (e: StorageEvent) => void) => void;
  reload?: () => void;
  gaConfigured?: boolean;
}

/**
 * Install the cross-tab listener. Returns an unsubscribe function. No-op (and
 * still safe to call) when there is no `window`.
 */
export function startTelemetryConsentSync(deps: ConsentSyncDeps = {}): () => void {
  const add =
    deps.addEventListener ??
    (typeof window === 'undefined'
      ? undefined
      : (window.addEventListener.bind(window) as ConsentSyncDeps['addEventListener']));
  const remove =
    deps.removeEventListener ??
    (typeof window === 'undefined'
      ? undefined
      : (window.removeEventListener.bind(window) as ConsentSyncDeps['removeEventListener']));
  if (!add) return () => {};

  const reload =
    deps.reload ??
    (() => {
      if (typeof window !== 'undefined') window.location.reload();
    });

  const handler = (e: StorageEvent) => {
    const outcome = handleExternalConsentChange(e.key, e.newValue, {
      gaConfigured: deps.gaConfigured,
    });
    if (outcome === 'applied_requires_reload') reload();
  };

  add('storage', handler);
  return () => remove?.('storage', handler);
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
  persistence = 'unknown';
  snapshot = NOTHING;
  listeners.clear();
}
