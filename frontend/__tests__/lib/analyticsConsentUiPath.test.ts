/**
 * L2-222 Item 2 (#1453) — ONE UI path to a consent decision, and copy that
 * cannot lie.
 *
 * Two defects, both about a decision being made in more than one place:
 *
 *  1. **The delayed banner outlived the question.** `AnalyticsProvider` armed a
 *     1.5s timer whenever nothing was stored, and nothing cancelled it. Granting
 *     from `/preferences` (or another tab) at t=0.4s left the timer armed, so at
 *     t=1.5s the banner appeared asking something already answered — and its
 *     buttons would then overwrite that answer.
 *  2. **The banner bypassed the transition planner.** It called
 *     `setTelemetryConsent` directly while `/preferences` went through
 *     `applyTelemetryChange`. A Decline on a page where providers were already
 *     live therefore persisted the denial and left them running, because only
 *     the planner knows a live→dead transition needs a hard reload.
 *
 * The raise rule now lives in a pure, injectable scheduler so the timing matrix
 * is provable under fake timers in this repo's DOM-free jest environment.
 */

export {}; // ensure module scope

import {
  startConsentBannerScheduler,
  CONSENT_BANNER_DELAY_MS,
} from '@/lib/analytics/consentBanner';
import { telemetryStatusText } from '@/components/Analytics/TelemetryPreferences';
import type { ConsentLevel } from '@/lib/analytics/telemetryConsent';

/** A minimal stand-in for the consent store: readable + subscribable. */
function fakeStore(initial: ConsentLevel = null) {
  let current = initial;
  const listeners = new Set<() => void>();
  return {
    get: () => current,
    set(level: ConsentLevel) {
      current = level;
      for (const fn of Array.from(listeners)) fn();
    },
    subscribe(fn: () => void) {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
    listenerCount: () => listeners.size,
  };
}

describe('the delayed banner never outlives the question', () => {
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => jest.useRealTimers());

  it('raises the banner at 1.5s when nobody has chosen', () => {
    const store = fakeStore(null);
    const visible: boolean[] = [];
    startConsentBannerScheduler({
      getConsent: store.get,
      subscribe: store.subscribe,
      setVisible: (v) => visible.push(v),
    });

    jest.advanceTimersByTime(CONSENT_BANNER_DELAY_MS - 1);
    expect(visible).toEqual([]);
    jest.advanceTimersByTime(1);
    expect(visible).toEqual([true]);
  });

  it('a Preferences GRANT before 1.5s never produces a stale banner', () => {
    const store = fakeStore(null);
    const visible: boolean[] = [];
    startConsentBannerScheduler({
      getConsent: store.get,
      subscribe: store.subscribe,
      setVisible: (v) => visible.push(v),
    });

    jest.advanceTimersByTime(400);
    store.set('analytics'); // …from /preferences, not from the banner

    jest.advanceTimersByTime(5000);
    expect(visible).not.toContain(true);
    expect(visible).toEqual([false]);
  });

  it('a Preferences DENIAL before 1.5s never produces a stale banner either', () => {
    const store = fakeStore(null);
    const visible: boolean[] = [];
    startConsentBannerScheduler({
      getConsent: store.get,
      subscribe: store.subscribe,
      setVisible: (v) => visible.push(v),
    });
    jest.advanceTimersByTime(100);
    store.set('none');
    jest.advanceTimersByTime(5000);
    expect(visible).not.toContain(true);
  });

  it('an ANOTHER-TAB choice before 1.5s cancels it too', () => {
    // Same mechanism: the cross-tab adopter writes through the store, and the
    // scheduler subscribes to the store, so it needs no knowledge of tabs.
    const store = fakeStore(null);
    const visible: boolean[] = [];
    startConsentBannerScheduler({
      getConsent: store.get,
      subscribe: store.subscribe,
      setVisible: (v) => visible.push(v),
    });
    jest.advanceTimersByTime(900);
    store.set('none');
    jest.advanceTimersByTime(5000);
    expect(visible).not.toContain(true);
  });

  it('re-checks at fire time even with NO subscription notification', () => {
    // Belt and braces: a choice that lands without notifying must still not be
    // asked about. Subscribe is a no-op here.
    let level: ConsentLevel = null;
    const visible: boolean[] = [];
    startConsentBannerScheduler({
      getConsent: () => level,
      subscribe: () => () => {},
      setVisible: (v) => visible.push(v),
    });
    level = 'analytics';
    jest.advanceTimersByTime(5000);
    expect(visible).not.toContain(true);
  });

  it('never arms when a choice already exists', () => {
    const store = fakeStore('none');
    const visible: boolean[] = [];
    startConsentBannerScheduler({
      getConsent: store.get,
      subscribe: store.subscribe,
      setVisible: (v) => visible.push(v),
    });
    jest.advanceTimersByTime(5000);
    expect(visible).toEqual([false]);
  });

  it('dispose clears the timer and unsubscribes', () => {
    const store = fakeStore(null);
    const visible: boolean[] = [];
    const stop = startConsentBannerScheduler({
      getConsent: store.get,
      subscribe: store.subscribe,
      setVisible: (v) => visible.push(v),
    });
    expect(store.listenerCount()).toBe(1);
    stop();
    jest.advanceTimersByTime(5000);
    expect(visible).toEqual([]);
    expect(store.listenerCount()).toBe(0);
  });
});

// ============================================================================
// One transition planner for every decline/revoke
// ============================================================================

describe('every decline/revoke routes through the transition planner', () => {
  it('a stale denial on a page with LIVE providers persists then reloads', () => {
    jest.resetModules();
    process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID = 'G-TEST123';
    const store: Record<string, string> = { bainluck_consent: 'analytics' };
    (global as unknown as { window: unknown }).window = {
      dataLayer: [],
      gtag: () => {},
      navigator: { userAgent: 'node' },
      location: { href: 'http://localhost/', pathname: '/' },
    };
    (global as unknown as { localStorage: unknown }).localStorage = {
      getItem: (k: string) => (k in store ? store[k] : null),
      setItem: (k: string, v: string) => {
        store[k] = v;
      },
      removeItem: (k: string) => delete store[k],
    };
    (global as unknown as { document: unknown }).document = { title: 'T', referrer: '' };

    const consent = require('@/lib/analytics/telemetryConsent');
    const revoke = require('@/lib/analytics/telemetryRevoke');
    consent.initTelemetryConsent();

    const order: string[] = [];
    const plan = revoke.applyTelemetryChange('none', {
      setConsent: (l: 'all' | 'analytics' | 'none') => {
        order.push('write');
        return consent.setTelemetryConsent(l);
      },
      reload: () => order.push('reload'),
    });

    // Verified-persist THEN reload — never the other way round.
    expect(order).toEqual(['write', 'reload']);
    expect(store.bainluck_consent).toBe('none');
    expect(plan.persistence).toBe('saved');
    expect(plan.reloaded).toBe(true);

    delete (global as unknown as { window?: unknown }).window;
    delete (global as unknown as { localStorage?: unknown }).localStorage;
    delete (global as unknown as { document?: unknown }).document;
  });
});

// ============================================================================
// Status copy: no false "saved" / "off"
// ============================================================================

describe('the Preferences status sentence cannot overclaim', () => {
  const durable = { hydrated: true, notDurable: false };
  const fragile = { hydrated: true, notDurable: true };

  it('says nothing definite before hydration', () => {
    expect(telemetryStatusText('none', { hydrated: false, notDurable: false })).toBe(
      'Checking your saved choice…',
    );
  });

  it('a durable denial may say OFF flatly', () => {
    expect(telemetryStatusText('none', durable)).toBe('Analytics is OFF. None of those load.');
  });

  it('a NON-durable denial must not say a bare "OFF"', () => {
    const text = telemetryStatusText('none', fragile);
    expect(text).not.toBe('Analytics is OFF. None of those load.');
    expect(text).toContain('would not save');
    expect(text).toContain('reload');
  });

  it('a NON-durable grant is equally qualified', () => {
    const text = telemetryStatusText('analytics', fragile);
    expect(text).toContain('would not save');
  });

  it('the undecided state says nothing loads', () => {
    expect(telemetryStatusText(null, durable)).toContain("haven't chosen yet");
  });

  it('never claims a provider the app does not load', () => {
    for (const level of [null, 'none', 'analytics', 'all'] as ConsentLevel[]) {
      for (const opts of [durable, fragile]) {
        const text = telemetryStatusText(level, opts).toLowerCase();
        expect(text).not.toContain('advertis');
        expect(text).not.toContain('marketing');
      }
    }
  });
});
