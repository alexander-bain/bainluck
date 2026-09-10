'use client';

/**
 * TelemetryGate (L2-219, Item 1 / #1453).
 *
 * BEFORE: `<Analytics />` (Vercel Analytics) was mounted unconditionally in the
 * root layout. It shipped beacons on the very first paint — before the banner
 * appeared — and kept shipping them after "Decline", because the consent state
 * machine governed only the GA rail. The banner therefore overstated what the
 * choice did (C90 P1).
 *
 * NOW: every CONSENT-GATED provider is mounted from THIS component, and whether
 * it mounts at all is read from the one consent authority
 * (`lib/analytics/telemetryConsent`). A provider that is not permitted is never
 * rendered, so it cannot load its script or send a beacon — enforcement is by
 * absence, not by an internal opt-out flag we would have to trust.
 *
 * WHAT IS NOT HERE, AND WHY. Both of Vercel's COOKIELESS providers are absent
 * from this file deliberately, under two rulings a week apart, and each one
 * has a source-shaped guard test that reds if this file's CODE names it
 * (comments, like this one, are stripped before those checks, or the guards
 * would only be asserting that nobody explained themselves).
 *
 *  1. **Vercel Speed Insights** (LAT-P197, Alex ruling D30, 2026-09-01). It
 *     sets no cookie, reads no storage and carries no identifier — it reports
 *     how fast the page rendered — so it is strictly-necessary performance
 *     telemetry that needs no consent, and gating it produced a speed
 *     measurement describing only the subset of visitors who had already
 *     answered a banner. Guard: `__tests__/lib/speedInsightsPreConsent.test.ts`.
 *
 *  2. **Vercel Web Analytics** (`@vercel/analytics`, Alex ruling D96,
 *     2026-09-08, shipped by latency/313 for #4830). Same class, and the
 *     mis-gating cost more. It is cookieless — no cookie, no storage read, no
 *     cross-site identifier — and the number it produces is "how many people
 *     came", which is a question about STRANGERS. `decideTelemetry` treats a
 *     visitor who has made no choice yet as a denial, which is right for the
 *     identified rails and fatal here: a first visit emitted nothing at all,
 *     so the one population the count exists to see could never appear in it.
 *     Guard: `__tests__/lib/vercelAnalyticsPreConsent.test.ts`.
 *
 * The GA4 rail is the counter-example that keeps this from being a slope. It
 * loads gtag.js, sets cookies and carries an identifier, so it stays here, and
 * the banner's promise about it stays true.
 *
 * `useSyncExternalStore` is deliberate: the decision lives in a framework-free
 * store so it can be unit-tested without a DOM, and the server snapshot is
 * always "nothing enabled" so SSR/hydration can never emit before the client
 * has read the persisted choice.
 */

import { useSyncExternalStore, useEffect } from 'react';
import {
  initTelemetryConsent,
  getTelemetryDecision,
  getServerTelemetryDecision,
  subscribeTelemetryConsent,
} from '@/lib/analytics';
import WebVitalsReporter from './WebVitalsReporter';
import ScreenTimingReporter from './ScreenTimingReporter';
import { GoogleAnalytics } from './GoogleAnalytics';

export function TelemetryGate() {
  // Hydrate the authority from the persisted choice. Idempotent, so React
  // Strict Mode's double-invoke and any remount are both harmless.
  useEffect(() => {
    initTelemetryConsent();
  }, []);

  const decision = useSyncExternalStore(
    subscribeTelemetryConsent,
    getTelemetryDecision,
    getServerTelemetryDecision,
  );

  return (
    <>
      {/* gtag.js is loaded ONLY after a grant. Consent Mode's "denied" state
          still sends cookieless pings to Google, so a declined visit must not
          fetch the script at all — denial has to be enforced by absence. The
          inline init inside GoogleAnalytics still sets `denied` defaults before
          anything else runs, preserving the Consent Mode ordering contract. */}
      {decision.googleAnalytics && <GoogleAnalytics />}
      {decision.webVitals && <WebVitalsReporter />}
      {/* The felt number (latency/121). Gated with Web Vitals because it is the
          same class of thing — a page-performance metric carrying no identifier —
          and because it emits through gtag, which is not loaded before a grant
          anyway. The sampling bias that creates is stated in the component. */}
      {decision.webVitals && <ScreenTimingReporter />}
    </>
  );
}

export default TelemetryGate;
