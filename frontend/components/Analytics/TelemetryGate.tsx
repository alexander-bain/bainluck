'use client';

/**
 * TelemetryGate (L2-219, Item 1 / #1453).
 *
 * BEFORE: `<Analytics />` (Vercel Analytics) and `<SpeedInsights />` were
 * mounted unconditionally in the root layout. They shipped beacons on the very
 * first paint — before the banner appeared — and kept shipping them after
 * "Decline", because the consent state machine governed only the GA rail. The
 * banner therefore overstated what the choice did (C90 P1).
 *
 * NOW: every non-essential provider is mounted from THIS component, and whether
 * it mounts at all is read from the one consent authority
 * (`lib/analytics/telemetryConsent`). A provider that is not permitted is never
 * rendered, so it cannot load its script or send a beacon — enforcement is by
 * absence, not by an internal opt-out flag we would have to trust.
 *
 * `useSyncExternalStore` is deliberate: the decision lives in a framework-free
 * store so it can be unit-tested without a DOM, and the server snapshot is
 * always "nothing enabled" so SSR/hydration can never emit before the client
 * has read the persisted choice.
 */

import { useSyncExternalStore, useEffect } from 'react';
import { Analytics } from '@vercel/analytics/next';
import { SpeedInsights } from '@vercel/speed-insights/next';
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
      {decision.speedInsights && <SpeedInsights />}
      {decision.webVitals && <WebVitalsReporter />}
    </>
  );
}

export default TelemetryGate;
