/**
 * Making a revoke TRUTHFUL (L2-220 Item 2 / #1453).
 *
 * L2-219 made every non-essential provider mount through one consent gate, so
 * a *declined* visit never loads them. What it could not make true is a
 * grant→revoke on a page where they are ALREADY RUNNING:
 *
 *  - `next/script` does not remove an injected `<script>` on unmount — that is
 *    its documented behavior, not a bug we can configure away. Once gtag.js has
 *    executed, `window.gtag` and `window.dataLayer` exist for the lifetime of
 *    the document.
 *  - `@vercel/analytics` and `@vercel/speed-insights` likewise inject their
 *    script into `<head>` and register listeners; unmounting the React
 *    component does not unload the script or detach what it already bound.
 *
 * So React unmount is NOT teardown, and gating the mount alone would let the
 * UI claim "off" while beacons kept leaving the page. Rather than pretend, a
 * revoke persists the denial and then performs ONE bounded hard reload: the
 * next document starts from the stored `'none'`, so the gate mounts nothing and
 * the providers are genuinely gone.
 *
 * The reload is deliberately narrow. It fires only on the transition that needs
 * it — something was live, nothing is permitted now — so choosing "off" when
 * already off, or granting (where mounting is sufficient), never reloads.
 *
 * Everything here is pure or dependency-injected, so the whole matrix is
 * testable in this repo's DOM-free jest environment.
 */

import { isAnalyticsConfigured, type ConsentPersistResult } from './config';
import {
  decideTelemetry,
  getTelemetryConsent,
  setTelemetryConsent,
  type ConsentLevel,
  type TelemetryDecision,
} from './telemetryConsent';

/** Whether any non-essential provider is permitted to run under a decision. */
export function anyProviderEnabled(decision: TelemetryDecision): boolean {
  return (
    decision.googleAnalytics ||
    decision.vercelAnalytics ||
    decision.speedInsights ||
    decision.webVitals
  );
}

export interface TelemetryChangePlan {
  /** Whether the stored choice actually changes. */
  persist: boolean;
  /**
   * Whether the change requires a hard reload to be true. Only a
   * live-providers → no-providers transition does; see the module comment.
   */
  requiresReload: boolean;
  /**
   * Whether the write was verifiably durable (`'saved'` only after an exact
   * readback). Present on the value `applyTelemetryChange` returns; the pure
   * planner cannot know it.
   */
  persistence?: ConsentPersistResult;
  /**
   * Whether the reload actually happened. A reload that `requiresReload` asked
   * for but durability withheld is the ONE case where these differ — see
   * `applyTelemetryChange`.
   */
  reloaded?: boolean;
}

/**
 * The pure decision about what a consent change requires. Split out from the
 * side effects so the reload rule itself is directly assertable.
 */
export function planTelemetryChange(
  prev: ConsentLevel,
  next: 'all' | 'analytics' | 'none',
  opts: { gaConfigured?: boolean } = {},
): TelemetryChangePlan {
  const gaConfigured = opts.gaConfigured ?? isAnalyticsConfigured();
  const before = decideTelemetry(prev, { gaConfigured });
  const after = decideTelemetry(next, { gaConfigured });

  return {
    persist: prev !== next,
    // Was something actually running that the new choice forbids? Note this is
    // keyed on providers, not on the raw level: `null → 'none'` is a denial but
    // nothing was ever mounted, so it needs no reload.
    requiresReload: anyProviderEnabled(before) && !anyProviderEnabled(after),
  };
}

/** Injection seam so the side-effecting path is testable without a DOM. */
export interface TelemetryChangeDeps {
  getConsent?: () => ConsentLevel;
  setConsent?: (level: 'all' | 'analytics' | 'none') => ConsentPersistResult | void;
  reload?: () => void;
  gaConfigured?: boolean;
}

function defaultReload(): void {
  if (typeof window === 'undefined') return;
  window.location.reload();
}

/**
 * Apply a consent change end-to-end.
 *
 * ORDER IS THE CONTRACT: the denial is persisted through the single writer
 * FIRST — which also closes the emission gate, pushes the Consent Mode update
 * and discards any withheld page view — and only then does the reload happen.
 * A reload that beat the write would come back up still granted; a write with
 * no reload would leave the loaded providers running. Returns the plan that was
 * executed.
 *
 * DURABILITY GATES THE RELOAD (L2-222 Item 1). The write is now verified by
 * readback, and an unverifiable write must NOT be followed by a reload: the new
 * document would read whatever is actually stored — quite possibly the grant the
 * user just revoked — and come back up with every provider running, having
 * thrown away the in-memory denial that was at least holding in this document.
 * Staying put with the gate closed is strictly better than reloading into the
 * old choice, so on `'unavailable'` we keep the page and let the UI say the
 * choice could not be saved.
 */
export function applyTelemetryChange(
  next: 'all' | 'analytics' | 'none',
  deps: TelemetryChangeDeps = {},
): TelemetryChangePlan {
  const read = deps.getConsent ?? getTelemetryConsent;
  const write = deps.setConsent ?? setTelemetryConsent;
  const reload = deps.reload ?? defaultReload;

  const prev = read();
  const plan = planTelemetryChange(prev, next, { gaConfigured: deps.gaConfigured });

  // Always write, even when the level is unchanged: re-asserting is harmless
  // and keeps "the store reflects the last explicit choice" true.
  const persistence: ConsentPersistResult = write(next) ?? 'saved';

  const reloaded = plan.requiresReload && persistence === 'saved';
  if (reloaded) {
    reload();
  }

  return { ...plan, persistence, reloaded };
}
