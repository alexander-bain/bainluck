/**
 * L2-190 Item 1 — denied-by-default consent contract.
 *
 * Exercises the core consent state machine that AnalyticsProvider / ConsentBanner
 * drive: default is DENIED, no event emits before an explicit grant, a stored
 * grant applies deterministically at init, denial persists across "reload", and
 * every ads state stays denied because the product has no ads.
 *
 * There is no jsdom in this repo, so we drive the module directly against a fake
 * window/gtag/localStorage — the same functions the provider calls.
 */

export {}; // ensure module scope (isolates top-level decls from sibling tests)

type GtagCall = unknown[];

interface Harness {
  core: typeof import('@/lib/analytics/core');
  config: typeof import('@/lib/analytics/config');
  calls: GtagCall[];
  store: Record<string, string>;
  eventCalls: () => GtagCall[];
  consentCalls: () => GtagCall[];
}

const ORIGINAL_ENV = process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID;

function setup(opts: { stored?: 'all' | 'analytics' | 'none'; configured?: boolean } = {}): Harness {
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
  const gtag = (...args: unknown[]) => {
    calls.push(args);
  };

  (global as unknown as { window: unknown }).window = {
    dataLayer: [],
    gtag,
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

  const core = require('@/lib/analytics/core') as typeof import('@/lib/analytics/core');
  const config = require('@/lib/analytics/config') as typeof import('@/lib/analytics/config');
  return {
    core,
    config,
    calls,
    store,
    eventCalls: () => calls.filter((c) => c[0] === 'event'),
    consentCalls: () => calls.filter((c) => c[0] === 'consent'),
  };
}

afterEach(() => {
  delete (global as unknown as { window?: unknown }).window;
  delete (global as unknown as { localStorage?: unknown }).localStorage;
  delete (global as unknown as { document?: unknown }).document;
});

afterAll(() => {
  if (ORIGINAL_ENV === undefined) delete process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID;
  else process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID = ORIGINAL_ENV;
});

describe('consent — first visit, no choice', () => {
  it('defaults to denied and emits NO event before a grant', () => {
    const h = setup({});
    h.core.initializeAnalytics();
    expect(h.core.isConsentGranted()).toBe(false);
    h.core.trackEvent('feed_refresh', { trigger: 'auto', new_items_count: 3 });
    expect(h.eventCalls()).toHaveLength(0);
  });
});

describe('consent — stored choices apply at init', () => {
  it('a stored analytics grant enables emission deterministically', () => {
    const h = setup({ stored: 'analytics' });
    h.core.initializeAnalytics();
    expect(h.core.isConsentGranted()).toBe(true);
    h.core.trackEvent('feed_refresh', { trigger: 'auto', new_items_count: 1 });
    expect(h.eventCalls()).toHaveLength(1);
  });

  it('a stored denial keeps emission off (denial persists across reload)', () => {
    const h = setup({ stored: 'none' });
    h.core.initializeAnalytics();
    expect(h.core.isConsentGranted()).toBe(false);
    h.core.trackEvent('feed_refresh', { trigger: 'auto', new_items_count: 1 });
    expect(h.eventCalls()).toHaveLength(0);
  });
});

describe('consent — explicit choices via updateConsent (Accept / Analytics only / Decline)', () => {
  it('Accept grants analytics but never grants ads', () => {
    const h = setup({});
    h.core.initializeAnalytics();
    h.core.updateConsent('all');
    expect(h.core.isConsentGranted()).toBe(true);
    const last = h.consentCalls().at(-1)!;
    expect(last[1]).toBe('update');
    expect(last[2]).toMatchObject({
      analytics_storage: 'granted',
      ad_storage: 'denied',
      ad_user_data: 'denied',
      ad_personalization: 'denied',
    });
    h.core.trackEvent('feed_refresh', { trigger: 'manual', new_items_count: 0 });
    expect(h.eventCalls()).toHaveLength(1);
  });

  it('Analytics only grants analytics, ads denied', () => {
    const h = setup({});
    h.core.initializeAnalytics();
    h.core.updateConsent('analytics');
    expect(h.core.isConsentGranted()).toBe(true);
    expect(h.consentCalls().at(-1)![2]).toMatchObject({
      analytics_storage: 'granted',
      ad_storage: 'denied',
    });
  });

  it('Decline (and Dismiss, which calls the same path) denies everything and stops emission', () => {
    const h = setup({});
    h.core.initializeAnalytics();
    h.core.updateConsent('all'); // grant first
    h.core.updateConsent('none'); // then decline / dismiss
    expect(h.core.isConsentGranted()).toBe(false);
    expect(h.consentCalls().at(-1)![2]).toMatchObject({
      analytics_storage: 'denied',
      ad_storage: 'denied',
      ad_user_data: 'denied',
      ad_personalization: 'denied',
    });
    const before = h.eventCalls().length;
    h.core.trackEvent('feed_refresh', { trigger: 'auto', new_items_count: 2 });
    expect(h.eventCalls().length).toBe(before); // no new event
  });
});

describe('consent — no-ads product invariant', () => {
  it('every preset keeps ads-related states denied', () => {
    const h = setup({});
    for (const preset of [h.config.GA_CONFIG.DEFAULT_CONSENT, h.config.GA_CONFIG.GRANTED_CONSENT, h.config.GA_CONFIG.ANALYTICS_ONLY_CONSENT]) {
      expect(preset.ad_storage).toBe('denied');
      expect(preset.ad_user_data).toBe('denied');
      expect(preset.ad_personalization).toBe('denied');
    }
    expect(h.config.GA_CONFIG.DEFAULT_CONSENT.analytics_storage).toBe('denied');
  });
});

describe('consent — unconfigured (no measurement id)', () => {
  it('never initializes and never emits', () => {
    const h = setup({ stored: 'all', configured: false });
    expect(h.config.isAnalyticsConfigured()).toBe(false);
    h.core.initializeAnalytics();
    // Grant would normally enable emission; with no id, init no-ops.
    h.core.updateConsent('all');
    h.core.trackEvent('feed_refresh', { trigger: 'auto', new_items_count: 1 });
    expect(h.eventCalls()).toHaveLength(0);
    // Nothing was configured on gtag either.
    expect(h.calls.filter((c) => c[0] === 'config')).toHaveLength(0);
  });
});
