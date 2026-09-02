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
 * WHAT IS NOT HERE, AND WHY (LAT-P197, Alex ruling D30). Vercel Speed Insights
 * is NOT gated and is deliberately absent from this file. It sets no cookie,
 * reads no storage and carries no identifier — it reports how fast the page
 * rendered — so it is strictly-necessary performance telemetry that needs no
 * consent, and gating it produced a speed measurement describing only the
 * subset of visitors who had already answered a banner. It mounts
 * unconditionally in `app/layout.tsx`. Adding it back to this component would
 * silently re-narrow that measurement, so a guard test
 * (`__tests__/lib/speedInsightsPreConsent.test.ts`) reds if this file's CODE
 * names it — comments, like this one, are stripped before that check, or the
 * guard would only be asserting that nobody explained themselves.
 *
 * `useSyncExternalStore` is deliberate: the decision lives in a framework-free
 * store so it can be unit-tested without a DOM, and the server snapshot is
 * always "nothing enabled" so SSR/hydration can never emit before the client
 * has read the persisted choice.
 */

import { useSyncExternalStore, useEffect } from 'react';
import { Analytics } from '@vercel/analytics/next';
import {
  initTelemetryConsent,
  getTelemetryDecision,
  getServerTelemetryDecision,
  subscribeTelemetryConsent,
} from '@/lib/analytics';
import WebVitalsReporter from './WebVitalsReporter';
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
      {decision.vercelAnalytics && <Analytics />}
      {decision.webVitals && <WebVitalsReporter />}
    </>
  );
}

export default TelemetryGate;
