/**
 * L2-220 Item 2 (#1453) — a revoke that is TRUE, and reachable.
 *
 * L2-219 proved that a *declined* visit mounts no provider. The gap it left is
 * grant→revoke on a page where the providers are ALREADY RUNNING: `next/script`
 * does not remove an injected script on unmount, and the Vercel packages'
 * scripts and listeners survive their component too. So "unmount" is not
 * teardown, and the honest close is to persist the denial and hard-reload once.
 *
 * These tests pin the two halves of that contract:
 *   1. the reload rule — exactly which transitions need one, and that the
 *      denial is persisted BEFORE the reload (a reload that beat the write
 *      would come back up still granted);
 *   2. that after a revoke the GA rail emits nothing even though `window.gtag`
 *      and `window.dataLayer` still exist — the in-page half of "zero later
 *      requests", with the script-level half owed to the browser rail.
 *
 * No jsdom in this repo, so this drives the real modules against a fake
 * window/gtag/localStorage and an injected `reload` spy.
 */

export {}; // ensure module scope

type GtagCall = unknown[];

interface Harness {
  consent: typeof import('@/lib/analytics/telemetryConsent');
  revoke: typeof import('@/lib/analytics/telemetryRevoke');
  core: typeof import('@/lib/analytics/core');
  calls: GtagCall[];
  store: Record<string, string>;
  reloads: number;
  reload: () => void;
  eventCalls: () => GtagCall[];
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
  const revoke = require('@/lib/analytics/telemetryRevoke') as Harness['revoke'];

  const h: Harness = {
    consent,
    revoke,
    core,
    calls,
    store,
    reloads: 0,
    reload: () => {
      h.reloads += 1;
    },
    eventCalls: () => calls.filter((c) => c[0] === 'event'),
  };
  return h;
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
// The reload rule
// ============================================================================

describe('planTelemetryChange — when a reload is required', () => {
  it('requires a reload on grant → revoke: the providers are already loaded', () => {
    const h = setup();
    expect(
      h.revoke.planTelemetryChange('analytics', 'none', { gaConfigured: true }),
    ).toEqual({ persist: true, requiresReload: true });
    expect(h.revoke.planTelemetryChange('all', 'none', { gaConfigured: true })).toEqual({
      persist: true,
      requiresReload: true,
    });
  });

  it('does NOT reload a first-visit decline — nothing was ever mounted', () => {
    const h = setup();
    expect(h.revoke.planTelemetryChange(null, 'none', { gaConfigured: true })).toEqual({
      persist: true,
      requiresReload: false,
    });
  });

  it('does NOT reload when already declined', () => {
    const h = setup();
    expect(h.revoke.planTelemetryChange('none', 'none', { gaConfigured: true })).toEqual({
      persist: false,
      requiresReload: false,
    });
  });

  it('does NOT reload on a grant — mounting the providers is sufficient', () => {
    const h = setup();
    expect(h.revoke.planTelemetryChange('none', 'analytics', { gaConfigured: true }))
      .toEqual({ persist: true, requiresReload: false });
    expect(h.revoke.planTelemetryChange(null, 'all', { gaConfigured: true })).toEqual({
      persist: true,
      requiresReload: false,
    });
  });

  it('does NOT reload when the choice does not change the provider set', () => {
    const h = setup();
    // 'all' and 'analytics' are the same decision (there is no ads product).
    expect(
      h.revoke.planTelemetryChange('all', 'analytics', { gaConfigured: true })
        .requiresReload,
    ).toBe(false);
  });

  it('still reloads on revoke with NO measurement id — the Vercel providers were live', () => {
    // Regression guard: keying the reload on the GA rail alone would leave
    // Vercel Analytics + Speed Insights running on a build with no GA id.
    const h = setup({ configured: false });
    const plan = h.revoke.planTelemetryChange('analytics', 'none', { gaConfigured: false });
    expect(plan.requiresReload).toBe(true);
  });
});

describe('anyProviderEnabled', () => {
  it('is false only when every provider is off', () => {
    const h = setup();
    expect(
      h.revoke.anyProviderEnabled({
        googleAnalytics: false,
        vercelAnalytics: false,
        speedInsights: false,
        webVitals: false,
      }),
    ).toBe(false);
    expect(
      h.revoke.anyProviderEnabled({
        googleAnalytics: false,
        vercelAnalytics: false,
        speedInsights: true,
        webVitals: false,
      }),
    ).toBe(true);
  });
});

// ============================================================================
// applyTelemetryChange — order and effects
// ============================================================================

describe('applyTelemetryChange', () => {
  it('persists the denial BEFORE reloading', () => {
    const h = setup({ stored: 'analytics' });
    h.consent.initTelemetryConsent();

    const persistedAtReload: (string | null)[] = [];
    h.revoke.applyTelemetryChange('none', {
      reload: () => {
        h.reloads += 1;
        persistedAtReload.push(h.store['bainluck_consent'] ?? null);
      },
      gaConfigured: true,
    });

    expect(h.reloads).toBe(1);
    // The write had already landed when the reload fired — otherwise the next
    // document would come back up still granted.
    expect(persistedAtReload).toEqual(['none']);
  });

  it('reloads exactly once on a revoke', () => {
    const h = setup({ stored: 'all' });
    h.consent.initTelemetryConsent();
    h.revoke.applyTelemetryChange('none', { reload: h.reload, gaConfigured: true });
    expect(h.reloads).toBe(1);
  });

  it('never reloads on a grant', () => {
    const h = setup({ stored: 'none' });
    h.consent.initTelemetryConsent();
    h.revoke.applyTelemetryChange('analytics', { reload: h.reload, gaConfigured: true });
    expect(h.reloads).toBe(0);
    expect(h.store['bainluck_consent']).toBe('analytics');
    expect(h.consent.getTelemetryConsent()).toBe('analytics');
  });

  it('never reloads when opening preferences and cancelling (no call at all)', () => {
    const h = setup({ stored: 'analytics' });
    h.consent.initTelemetryConsent();
    // "Cancel" is simply not calling apply — the stored choice is untouched.
    expect(h.reloads).toBe(0);
    expect(h.store['bainluck_consent']).toBe('analytics');
  });

  it('turns every provider off in the decision after a revoke', () => {
    const h = setup({ stored: 'analytics' });
    h.consent.initTelemetryConsent();
    expect(h.revoke.anyProviderEnabled(h.consent.getTelemetryDecision())).toBe(true);

    h.revoke.applyTelemetryChange('none', { reload: h.reload, gaConfigured: true });

    const after = h.consent.getTelemetryDecision();
    expect(after).toEqual({
      googleAnalytics: false,
      vercelAnalytics: false,
      speedInsights: false,
      webVitals: false,
    });
  });

  it('notifies subscribers so the gate and the control both re-render', () => {
    const h = setup({ stored: 'analytics' });
    h.consent.initTelemetryConsent();
    let notifications = 0;
    h.consent.subscribeTelemetryConsent(() => {
      notifications += 1;
    });
    h.revoke.applyTelemetryChange('none', { reload: h.reload, gaConfigured: true });
    expect(notifications).toBeGreaterThan(0);
  });
});

// ============================================================================
// The in-page half of "zero later requests"
// ============================================================================

describe('after a revoke, the GA rail is silent even though the globals survive', () => {
  it('emits nothing through trackEvent once consent is revoked', () => {
    const h = setup({ stored: 'analytics' });
    h.core.initializeAnalytics();
    h.consent.initTelemetryConsent();

    // Granted: an event goes out.
    h.core.trackEvent('chart_view', { chart_type: 'probability' }, { immediate: true });
    expect(h.eventCalls().length).toBe(1);

    h.revoke.applyTelemetryChange('none', { reload: h.reload, gaConfigured: true });
    const afterRevoke = h.eventCalls().length;

    // `window.gtag` is STILL a function here — that is exactly the point. The
    // emission gate, not the absence of the global, is what stops this.
    expect(typeof (global as unknown as { window: { gtag: unknown } }).window.gtag).toBe(
      'function',
    );
    h.core.trackEvent('chart_view', { chart_type: 'probability' }, { immediate: true });
    h.core.trackEvent('share_scorecard', {
      accuracy_percent: 61,
      total_questions: 12,
      streak: 3,
    }, { immediate: true });
    expect(h.eventCalls().length).toBe(afterRevoke);
  });

  it('discards a page view withheld before the revoke — no current-route delivery', () => {
    const h = setup();
    h.core.initializeAnalytics();
    h.consent.initTelemetryConsent();

    // Undecided: the landing view is withheld, not dropped.
    h.core.trackPageView(PAGE);
    expect(h.core.peekWithheldPageView()).not.toBeNull();

    h.revoke.applyTelemetryChange('none', { reload: h.reload, gaConfigured: true });
    expect(h.core.peekWithheldPageView()).toBeNull();
    expect(h.eventCalls().filter((c) => c[1] === 'page_view').length).toBe(0);
  });

  it('pushes a Consent Mode update with every ads state denied on revoke', () => {
    const h = setup({ stored: 'analytics' });
    h.core.initializeAnalytics();
    h.consent.initTelemetryConsent();
    const before = h.calls.length;

    h.revoke.applyTelemetryChange('none', { reload: h.reload, gaConfigured: true });

    const updates = h.calls
      .slice(before)
      .filter((c) => c[0] === 'consent' && c[1] === 'update');
    expect(updates.length).toBeGreaterThan(0);
    const last = updates[updates.length - 1][2] as Record<string, string>;
    expect(last.analytics_storage).toBe('denied');
    expect(last.ad_storage).toBe('denied');
    expect(last.ad_user_data).toBe('denied');
    expect(last.ad_personalization).toBe('denied');
  });

  it('keeps every ads state denied on a GRANT too — the product has no ads', () => {
    const h = setup();
    h.core.initializeAnalytics();
    h.consent.initTelemetryConsent();
    h.revoke.applyTelemetryChange('all', { reload: h.reload, gaConfigured: true });

    const updates = h.calls.filter((c) => c[0] === 'consent' && c[1] === 'update');
    const last = updates[updates.length - 1][2] as Record<string, string>;
    expect(last.analytics_storage).toBe('granted');
    expect(last.ad_storage).toBe('denied');
    expect(last.ad_user_data).toBe('denied');
    expect(last.ad_personalization).toBe('denied');
  });

  it('a revoke→grant→revoke cycle reloads on each revoke and stays silent after', () => {
    const h = setup({ stored: 'analytics' });
    h.core.initializeAnalytics();
    h.consent.initTelemetryConsent();

    h.revoke.applyTelemetryChange('none', { reload: h.reload, gaConfigured: true });
    expect(h.reloads).toBe(1);
    h.revoke.applyTelemetryChange('analytics', { reload: h.reload, gaConfigured: true });
    expect(h.reloads).toBe(1); // grant does not reload
    h.revoke.applyTelemetryChange('none', { reload: h.reload, gaConfigured: true });
    expect(h.reloads).toBe(2);

    const after = h.eventCalls().length;
    h.core.trackEvent('chart_view', { chart_type: 'probability' }, { immediate: true });
    expect(h.eventCalls().length).toBe(after);
  });
});

// ============================================================================
// Remount / reload parity — the stored choice is what the next document reads
// ============================================================================

describe('reload / remount parity', () => {
  it('a fresh document after a revoke enables nothing', () => {
    const first = setup({ stored: 'analytics' });
    first.consent.initTelemetryConsent();
    first.revoke.applyTelemetryChange('none', { reload: first.reload, gaConfigured: true });
    expect(first.store['bainluck_consent']).toBe('none');

    // Simulate the reload: a brand-new module registry reading the same store.
    const second = setup({ stored: 'none' });
    second.consent.initTelemetryConsent();
    expect(second.revoke.anyProviderEnabled(second.consent.getTelemetryDecision())).toBe(
      false,
    );
    expect(second.consent.getServerTelemetryDecision()).toEqual({
      googleAnalytics: false,
      vercelAnalytics: false,
      speedInsights: false,
      webVitals: false,
    });
  });
});
