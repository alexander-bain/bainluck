/**
 * Analytics Components
 *
 * 🔴 LAT-P204 (#2673) — THIS BARREL IS ON THE BLOCKING ENTRY PATH OF EVERY ROUTE.
 *
 * Fourteen modules import `useAnalyticsContext` from here — FeedCard, BottomNav,
 * Footer, DesktopNav, SearchBar, OddsChart, four hooks, and so on — and a barrel
 * is imported whole. So every symbol re-exported below travelled into the entry
 * chunk of every page that wanted one React hook, including `TelemetryPreferences`,
 * a component only `/preferences` can ever render.
 *
 * Rule for this file: re-export ONLY what a caller reaches through the barrel.
 * Anything mounted from exactly one place is imported from its own module by that
 * place. `__tests__/lib/analyticsBarrelEntryCost.test.ts` fails if this list grows
 * a symbol nobody imports from here.
 *
 * NOT re-exported, deliberately:
 *   GoogleAnalytics, WebVitalsReporter — lazily imported by TelemetryGate, which is
 *     where the consent decision that permits them is made. Re-exporting them would
 *     put them straight back into every entry graph and silently undo the cut.
 *   TelemetryPreferences — rendered only by `/preferences`, which imports it from
 *     its own module.
 */

export { AnalyticsProvider, useAnalyticsContext } from './AnalyticsProvider';
export { ConsentBanner } from './ConsentBanner';
export { TelemetryGate } from './TelemetryGate';
