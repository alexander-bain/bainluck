/**
 * Analytics Components
 *
 * 🔴 LAT-P204 — THIS BARREL IS ON THE BLOCKING ENTRY PATH OF EVERY ROUTE.
 *
 * Sixteen modules import `useAnalyticsContext` from here — FeedCard, BottomNav,
 * Footer, DesktopNav, four hooks, and so on — and a barrel is imported whole.
 * So every symbol re-exported below travelled into the entry chunk of every
 * page that wanted one React hook. Measured on a clean build of `/`: chunk 5647
 * was 32,702 raw / 9,068 brotli of BLOCKING javascript containing the consent
 * banner, the gtag.js wrapper, and `TelemetryPreferences` — a component only
 * `/preferences` can ever render.
 *
 * Rule for this file: re-export ONLY what a caller reaches through the barrel.
 * Anything mounted from exactly one place is imported from its own module by
 * that place. `__tests__/lib/analyticsBarrelEntryCost.test.ts` fails if this
 * list grows a symbol nobody imports from here.
 *
 * NOT re-exported, deliberately:
 *   GoogleAnalytics, WebVitalsReporter — lazily imported by TelemetryGate, which
 *     is where the consent decision that permits them is made. Re-exporting them
 *     would put them straight back into every entry graph and silently undo the
 *     split.
 *   TelemetryPreferences — `/preferences` imports it directly.
 */

export { AnalyticsProvider, useAnalyticsContext } from './AnalyticsProvider';
export { ConsentBanner } from './ConsentBanner';
export { TelemetryGate } from './TelemetryGate';
