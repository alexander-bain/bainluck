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
import dynamic from 'next/dynamic';
import {
  initTelemetryConsent,
  getTelemetryDecision,
  getServerTelemetryDecision,
  subscribeTelemetryConsent,
} from '@/lib/analytics';

/**
 * LAT-P204: the gated providers are LAZY, and that is the whole cut.
 *
 * Enforcement was already by absence — a provider the decision does not permit
 * is never rendered, so it never loads its script and never sends a beacon.
 * But `import` is not `render`. Statically importing them here put gtag.js's
 * wrapper, Vercel Analytics and the web-vitals reporter into the BLOCKING entry
 * chunk of every route, so a visitor who declined — or who has not been asked
 * yet, which is every cold first load — downloaded the code for three rails
 * they will never run before the first card could be drawn.
 *
 * `TelemetryGate` is a Client Component, so `dynamic()` here is a real split
 * point. That is not a given: the same three calls written in `app/layout.tsx`
 * would split nothing, because a Server Component turns every client module it
 * names into a client reference of its own entry chunk and webpack has lost the
 * split point before `React.lazy` ever sees it (LAT-P200 / DeferredChrome.tsx).
 *
 * The consent contract is unchanged and, if anything, stronger: the decision
 * still governs whether the component renders at all, and now the bytes are not
 * even fetched until it does. `ssr: false` matches what the gate already did —
 * `getServerTelemetryDecision()` is all-false, so none of these has ever been
 * part of the server render.
 */
const Analytics = dynamic(
  () => import('@vercel/analytics/next').then((m) => m.Analytics),
  { ssr: false },
);
const GoogleAnalytics = dynamic(
  () => import('./GoogleAnalytics').then((m) => m.GoogleAnalytics),
  { ssr: false },
);
const WebVitalsReporter = dynamic(() => import('./WebVitalsReporter'), { ssr: false });

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
