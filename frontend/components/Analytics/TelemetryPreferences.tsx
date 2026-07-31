'use client';

/**
 * The reachable telemetry control (L2-220 Item 2 / #1453).
 *
 * BEFORE: the consent banner was the ONLY way to express a choice, and it is
 * shown exactly once — `AnalyticsProvider` only raises it when nothing is
 * stored. So a user who pressed Accept had no way back: the banner never
 * returned, and no other surface could change the decision. "You can change
 * your preferences at any time" (banner copy) was not true.
 *
 * NOW: this section lives on `/preferences` and is linked from the footer of
 * every page, so the choice is reachable after it has been made. Turning
 * analytics off routes through `applyTelemetryChange`, which persists the
 * denial and then hard-reloads when providers are actually running — see
 * `lib/analytics/telemetryRevoke` for why unmounting is not teardown.
 *
 * The copy here states exactly what the code does, including the reload. It
 * makes no legal claim and names no provider the app does not load.
 */

import { useCallback, useEffect, useState } from 'react';
import {
  getTelemetryConsent,
  subscribeTelemetryConsent,
  initTelemetryConsent,
  type ConsentLevel,
} from '@/lib/analytics';
import { applyTelemetryChange } from '@/lib/analytics/telemetryRevoke';

export function TelemetryPreferences() {
  // `null` until the client has read the persisted choice — the server render
  // must not assert a state it cannot know.
  const [consent, setConsent] = useState<ConsentLevel>(null);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    const sync = () => setConsent(getTelemetryConsent());
    const unsubscribe = subscribeTelemetryConsent(sync);
    initTelemetryConsent();
    sync();
    setHydrated(true);
    return unsubscribe;
  }, []);

  const choose = useCallback((level: 'analytics' | 'none') => {
    // May hard-reload when providers are live; the denial is persisted first.
    applyTelemetryChange(level);
  }, []);

  const isOn = consent === 'all' || consent === 'analytics';
  const status = !hydrated
    ? 'Checking your saved choice…'
    : isOn
      ? 'Analytics is ON. Google Analytics, Vercel Analytics and Vercel Speed Insights load on this site.'
      : consent === 'none'
        ? 'Analytics is OFF. None of those load.'
        : "You haven't chosen yet, so nothing loads. Analytics is off until you turn it on.";

  return (
    <section
      id="telemetry"
      aria-labelledby="telemetry-heading"
      className="scroll-mt-20 bg-surface-card rounded-xl border border-surface-border p-4"
    >
      <h2
        id="telemetry-heading"
        className="text-sm font-semibold text-text-secondary uppercase tracking-wide mb-3"
      >
        Privacy &amp; analytics
      </h2>

      <p aria-live="polite" className="text-sm text-text-secondary leading-relaxed">
        {status}
      </p>

      <p className="mt-2 text-xs text-text-muted leading-relaxed">
        These measure which pages are used and how fast they load. We never send
        marketing or advertising signals. Turning analytics off reloads this page
        so the scripts that are already running are unloaded, not just hidden.
      </p>

      <div className="mt-4 flex flex-row gap-2 sm:gap-3">
        <button
          type="button"
          onClick={() => choose('analytics')}
          aria-pressed={hydrated && isOn}
          disabled={!hydrated}
          className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors disabled:opacity-50 ${
            hydrated && isOn
              ? 'bg-graphite text-white'
              : 'bg-surface-border text-text-primary hover:bg-slate/20'
          }`}
        >
          Allow analytics
        </button>
        <button
          type="button"
          onClick={() => choose('none')}
          aria-pressed={hydrated && !isOn}
          disabled={!hydrated}
          className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors disabled:opacity-50 ${
            hydrated && !isOn
              ? 'bg-graphite text-white'
              : 'bg-slate/10 text-text-secondary hover:bg-slate/20'
          }`}
        >
          Turn analytics off
        </button>
      </div>

      <p className="mt-3 text-xs text-text-muted">
        More detail in our{' '}
        <a href="/privacy" className="underline hover:text-text-secondary">
          Privacy Policy
        </a>
        .
      </p>
    </section>
  );
}

export default TelemetryPreferences;
