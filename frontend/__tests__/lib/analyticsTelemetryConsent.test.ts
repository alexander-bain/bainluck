/**
 * L2-219 Item 1 (#1453) — the ONE web telemetry consent + delivery authority.
 *
 * Covers the three C90 defects this queue closes:
 *   P1 — Vercel Analytics / Speed Insights ignored the consent choice entirely.
 *        Now every provider reads `decideTelemetry`, so "Decline" really is
 *        zero non-essential telemetry.
 *   P3 — the first-time visitor's LANDING page view was dropped (emitted before
 *        the grant, discarded by the consent gate). It is now withheld and
 *        released exactly once on the grant — the current route, never a replay.
 *
 * There is no jsdom in this repo, so the store is driven directly against a fake
 * window/gtag/localStorage — the same functions the provider and gate call.
 */

export {}; // ensure module scope

type GtagCall = unknown[];

interface Harness {
  consent: typeof import('@/lib/analytics/telemetryConsent');
  core: typeof import('@/lib/analytics/core');
  calls: GtagCall[];
  store: Record<string, string>;
  eventCalls: () => GtagCall[];
  pageViewCalls: () => GtagCall[];
}

const ORIGINAL_ENV = process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID;

function setup(
  opts: { stored?: 'all' | 'analytics' | 'none'; configured?: boolean } = {},
): Harness {
  const { stored, configured = true } = opts;
  jest.resetModules();
  if (configured) {
    process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID = 'G-TEST123';
  } else {
    delete process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID;
  }

  const store: Record<string, string> = {};
  if (stored) store['bainluck_consent'] = stored;
  const calls: GtagCall[] = [];

  (global as unknown as { window: unknown }).window = {
    dataLayer: [],
    gtag: (...args: unknown[]) => calls.push(args),
    navigator: { userAgent: 'node' },
    location: { href: 'http://localhost/', pathname: '/' },
  };
  (global as unknown as { localStorage: unknown }).localStorage = {
    getItem: (k: string) => (k in store ? store[k] : null),
    setItem: (k: string, v: string) => {
      store[k] = v;
    },
    removeItem: (k: string) => {
      delete store[k];
    },
  };
  (global as unknown as { document: unknown }).document = { title: 'T', referrer: '' };

  const core = require('@/lib/analytics/core') as Harness['core'];
  const consent = require('@/lib/analytics/telemetryConsent') as Harness['consent'];

  return {
    consent,
    core,
    calls,
    store,
    eventCalls: () => calls.filter((c) => c[0] === 'event'),
    pageViewCalls: () => calls.filter((c) => c[0] === 'event' && c[1] === 'page_view'),
  };
}

afterEach(() => {
  if (ORIGINAL_ENV === undefined) {
    delete process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID;
  } else {
    process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID = ORIGINAL_ENV;
  }
});

const PAGE = {
  page_type: 'home' as const,
  page_path: '/',
  page_title: 'Bain Luck',
};

// ============================================================================
// decideTelemetry — the pure decision every provider reads
// ============================================================================

describe('decideTelemetry', () => {
  it('enables NOTHING before a choice is made', () => {
    const h = setup();
    expect(h.consent.decideTelemetry(null, { gaConfigured: true })).toEqual({
      googleAnalytics: false,
      vercelAnalytics: false,
      speedInsights: false,
      webVitals: false,
    });
  });

  it('enables NOTHING on an explicit decline — including the Vercel providers (C90 P1)', () => {
    const h = setup();
    const decision = h.consent.decideTelemetry('none', { gaConfigured: true });
    expect(decision.vercelAnalytics).toBe(false);
    expect(decision.speedInsights).toBe(false);
    expect(decision.googleAnalytics).toBe(false);
    expect(decision.webVitals).toBe(false);
  });

  it('enables every provider on a grant', () => {
    const h = setup();
    for (const level of ['all', 'analytics'] as const) {
      expect(h.consent.decideTelemetry(level, { gaConfigured: true })).toEqual({
        googleAnalytics: true,
        vercelAnalytics: true,
        speedInsights: true,
        webVitals: true,
      });
    }
  });

  it('treats "Accept" and "Analytics only" identically — the product has no ads, and the banner says so', () => {
    const h = setup();
    expect(h.consent.decideTelemetry('all', { gaConfigured: true })).toEqual(
      h.consent.decideTelemetry('analytics', { gaConfigured: true }),
    );
  });

  it('a missing GA measurement id disables the GA rail WITHOUT re-enabling Vercel', () => {
    const h = setup({ configured: false });
    const decision = h.consent.decideTelemetry('all', { gaConfigured: false });
    expect(decision.googleAnalytics).toBe(false);
    expect(decision.webVitals).toBe(false);
    // Vercel needs no id — a missing GA id must not silently turn it off either.
    expect(decision.vercelAnalytics).toBe(true);
    expect(decision.speedInsights).toBe(true);
  });
});

// ============================================================================
// Store lifecycle
// ============================================================================

describe('consent store lifecycle', () => {
  it('first visit: no stored choice, nothing enabled, nothing persisted', () => {
    const h = setup();
    expect(h.consent.initTelemetryConsent()).toBeNull();
    expect(h.consent.getTelemetryDecision().vercelAnalytics).toBe(false);
    expect(h.store['bainluck_consent']).toBeUndefined();
  });

  it('a stored grant is applied at init and enables the providers', () => {
    const h = setup({ stored: 'analytics' });
    expect(h.consent.initTelemetryConsent()).toBe('analytics');
    const decision = h.consent.getTelemetryDecision();
    expect(decision.vercelAnalytics).toBe(true);
    expect(decision.speedInsights).toBe(true);
    expect(h.core.isConsentGranted()).toBe(true);
  });

  it('a stored denial keeps every provider off across a reload', () => {
    const h = setup({ stored: 'none' });
    expect(h.consent.initTelemetryConsent()).toBe('none');
    expect(h.consent.getTelemetryDecision()).toEqual({
      googleAnalytics: false,
      vercelAnalytics: false,
      speedInsights: false,
      webVitals: false,
    });
    expect(h.core.isConsentGranted()).toBe(false);
  });

  it('init is idempotent under Strict Mode double-invoke and remounts', () => {
    const h = setup({ stored: 'all' });
    const notifications: number[] = [];
    h.consent.subscribeTelemetryConsent(() => notifications.push(1));

    h.consent.initTelemetryConsent();
    const first = h.consent.getTelemetryDecision();
    h.consent.initTelemetryConsent();
    h.consent.initTelemetryConsent();

    // Hydration notifies ONCE (subscribers must re-read the resolved choice);
    // every later invocation is silent and returns the identical snapshot ref,
    // so useSyncExternalStore cannot loop or tear.
    expect(h.consent.getTelemetryDecision()).toBe(first);
    expect(notifications.length).toBe(1);
  });

  it('the server snapshot never enables anything', () => {
    const h = setup({ stored: 'all' });
    h.consent.initTelemetryConsent();
    expect(h.consent.getServerTelemetryDecision()).toEqual({
      googleAnalytics: false,
      vercelAnalytics: false,
      speedInsights: false,
      webVitals: false,
    });
  });

  it('persists the choice and notifies subscribers exactly once per change', () => {
    const h = setup();
    h.consent.initTelemetryConsent();
    let notified = 0;
    const unsubscribe = h.consent.subscribeTelemetryConsent(() => {
      notified += 1;
    });

    h.consent.setTelemetryConsent('all');
    expect(notified).toBe(1);
    expect(h.store['bainluck_consent']).toBe('all');

    unsubscribe();
    h.consent.setTelemetryConsent('none');
    expect(notified).toBe(1); // unsubscribed
    expect(h.store['bainluck_consent']).toBe('none');
  });

  it('revoking a grant turns every provider back off', () => {
    const h = setup({ stored: 'all' });
    h.consent.initTelemetryConsent();
    expect(h.consent.getTelemetryDecision().vercelAnalytics).toBe(true);

    h.consent.setTelemetryConsent('none');
    expect(h.consent.getTelemetryDecision().vercelAnalytics).toBe(false);
    expect(h.consent.getTelemetryDecision().speedInsights).toBe(false);
    expect(h.core.isConsentGranted()).toBe(false);
  });

  it('a throwing subscriber cannot break the consent rail', () => {
    const h = setup();
    h.consent.initTelemetryConsent();
    h.consent.subscribeTelemetryConsent(() => {
      throw new Error('bad subscriber');
    });
    let reached = false;
    h.consent.subscribeTelemetryConsent(() => {
      reached = true;
    });

    expect(() => h.consent.setTelemetryConsent('all')).not.toThrow();
    expect(reached).toBe(true);
  });
});

// ============================================================================
// Landing-page delivery (C90 P3) — no loss, no replay, no duplicate
// ============================================================================

describe('withheld page view', () => {
  it('emits NOTHING before a choice, but does not lose the landing page', () => {
    const h = setup();
    h.consent.initTelemetryConsent();
    h.core.initializeAnalytics();

    h.core.trackPageView(PAGE);

    expect(h.pageViewCalls()).toHaveLength(0);
    expect(h.core.peekWithheldPageView()).toEqual(PAGE);
  });

  it('a grant releases the landing page view exactly once', () => {
    const h = setup();
    h.consent.initTelemetryConsent();
    h.core.initializeAnalytics();
    h.core.trackPageView(PAGE);

    h.consent.setTelemetryConsent('all');

    const views = h.pageViewCalls();
    expect(views).toHaveLength(1);
    expect((views[0][2] as Record<string, unknown>).page_path).toBe('/');
    expect(h.core.peekWithheldPageView()).toBeNull();
  });

  it('emits the CURRENT route only — it does not replay pre-consent navigation', () => {
    const h = setup();
    h.consent.initTelemetryConsent();
    h.core.initializeAnalytics();

    h.core.trackPageView({ ...PAGE, page_path: '/' });
    h.core.trackPageView({ ...PAGE, page_path: '/discover' });
    h.core.trackPageView({ ...PAGE, page_path: '/politics' });

    h.consent.setTelemetryConsent('analytics');

    const views = h.pageViewCalls();
    expect(views).toHaveLength(1);
    expect((views[0][2] as Record<string, unknown>).page_path).toBe('/politics');
  });

  it('a decline emits nothing and discards the withheld view', () => {
    const h = setup();
    h.consent.initTelemetryConsent();
    h.core.initializeAnalytics();
    h.core.trackPageView(PAGE);

    h.consent.setTelemetryConsent('none');

    expect(h.pageViewCalls()).toHaveLength(0);
    expect(h.core.peekWithheldPageView()).toBeNull();
  });

  it('declining then later granting does NOT resurrect the declined page view', () => {
    const h = setup();
    h.consent.initTelemetryConsent();
    h.core.initializeAnalytics();
    h.core.trackPageView(PAGE);

    h.consent.setTelemetryConsent('none');
    h.consent.setTelemetryConsent('all');

    expect(h.pageViewCalls()).toHaveLength(0);
  });

  it('a second flush cannot double-count the same page view', () => {
    const h = setup();
    h.consent.initTelemetryConsent();
    h.core.initializeAnalytics();
    h.core.trackPageView(PAGE);

    h.consent.setTelemetryConsent('all');
    expect(h.core.flushWithheldPageView()).toBe(false);
    expect(h.pageViewCalls()).toHaveLength(1);
  });

  it('after a grant, page views emit directly with no withholding', () => {
    const h = setup({ stored: 'all' });
    h.consent.initTelemetryConsent();
    h.core.initializeAnalytics();

    h.core.trackPageView({ ...PAGE, page_path: '/discover' });

    expect(h.pageViewCalls()).toHaveLength(1);
    expect(h.core.peekWithheldPageView()).toBeNull();
  });

  it('a stored grant that beats gtag readiness still delivers the landing page once', () => {
    // The returning-visitor race: consent is granted, but `initializeAnalytics`
    // has not run yet, so the rail is not emittable.
    const h = setup({ stored: 'all' });
    h.consent.initTelemetryConsent();

    h.core.trackPageView(PAGE);
    expect(h.pageViewCalls()).toHaveLength(0); // withheld, not dropped

    h.core.initializeAnalytics();
    expect(h.core.flushWithheldPageView()).toBe(true);
    expect(h.pageViewCalls()).toHaveLength(1);
  });
});
