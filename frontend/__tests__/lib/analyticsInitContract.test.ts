/**
 * L2-203 — GA4 init/config + single-page-view contract hardening.
 *
 * L2-190 (d38a7e2a) landed the actual fixes: denied-by-default consent, a single
 * page_view per navigation (the duplicate `gtag('config')` re-send removed),
 * env-configured measurement id, and logout identity clearing. Those are covered
 * by analyticsConsent / analyticsPageView / analyticsSanitize.
 *
 * This file adds the acceptance assertions L2-203 names that those suites did not
 * yet make explicit — all at the core-module level, since the repo runs jest in a
 * `node` environment with no jsdom (so React hook/remount rendering cannot be
 * exercised here without an infra change that is out of this queue's scope):
 *
 *   Item 2 — the single-page-view MECHANISM: GA4 auto page_view is disabled at
 *     config time (`send_page_view: false`), so the manual `page_view` event is
 *     the sole source; a denied session emits zero page_views; an unconfigured
 *     (absent id) build emits zero; rapid navigation emits exactly N.
 *   Item 1 — "no duplicate script initialization or event replay": a second
 *     `initializeAnalytics()` is idempotent (no second GA4 config), and a stored
 *     grant applied at init does not replay historical events.
 *   Consent race — a page_view attempted before init is dropped, and works only
 *     after init + explicit grant.
 *
 * Driven directly against a fake window/gtag/localStorage, mirroring the sibling
 * suites.
 */

export {}; // ensure module scope (isolates top-level decls from sibling tests)

type GtagCall = unknown[];

const ORIGINAL_ENV = process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID;
const MEASUREMENT_ID = 'G-TEST123';

interface Harness {
  core: typeof import('@/lib/analytics/core');
  config: typeof import('@/lib/analytics/config');
  calls: GtagCall[];
  store: Record<string, string>;
  pageViewEvents: () => GtagCall[];
  eventCalls: () => GtagCall[];
  /** `gtag('config', MEASUREMENT_ID, {...})` calls (the GA4 property config). */
  ga4ConfigCalls: () => GtagCall[];
}

function setup(opts: { stored?: 'all' | 'analytics' | 'none'; configured?: boolean } = {}): Harness {
  const { stored, configured = true } = opts;
  jest.resetModules();
  if (configured) {
    process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID = MEASUREMENT_ID;
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
    pageViewEvents: () => calls.filter((c) => c[0] === 'event' && c[1] === 'page_view'),
    eventCalls: () => calls.filter((c) => c[0] === 'event'),
    ga4ConfigCalls: () => calls.filter((c) => c[0] === 'config' && c[1] === MEASUREMENT_ID),
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

describe('init — GA4 auto page_view disabled (single-page-view mechanism)', () => {
  it('configures the property with send_page_view:false so GA never auto-fires a page view', () => {
    const h = setup({});
    h.core.initializeAnalytics();
    const cfg = h.ga4ConfigCalls();
    expect(cfg).toHaveLength(1);
    expect(cfg[0][2]).toMatchObject({ send_page_view: false });
  });
});

describe('init — idempotent (no duplicate script initialization / config replay)', () => {
  it('a second initializeAnalytics() does not re-configure the GA4 property', () => {
    const h = setup({});
    h.core.initializeAnalytics();
    h.core.initializeAnalytics();
    h.core.initializeAnalytics();
    // Only the first init configures the property; later calls short-circuit.
    expect(h.ga4ConfigCalls()).toHaveLength(1);
  });

  it('applying a stored grant at init does not replay any historical page_view/event', () => {
    const h = setup({ stored: 'all' });
    h.core.initializeAnalytics();
    // Consent is granted from storage, but nothing was tracked yet → no replay.
    expect(h.pageViewEvents()).toHaveLength(0);
    expect(h.eventCalls()).toHaveLength(0);
  });
});

describe('page_view — consent gate produces zero in denied/unconfigured states', () => {
  it('a denied (no-choice) session emits zero page_views', () => {
    const h = setup({});
    h.core.initializeAnalytics(); // no grant → denied
    h.core.trackPageView({ page_type: 'home', page_path: '/', page_title: 'Home' });
    h.core.trackPageView({ page_type: 'discover', page_path: '/discover', page_title: 'Discover' });
    expect(h.pageViewEvents()).toHaveLength(0);
  });

  it('an explicitly-declined session emits zero page_views', () => {
    const h = setup({});
    h.core.initializeAnalytics();
    h.core.updateConsent('none');
    h.core.trackPageView({ page_type: 'home', page_path: '/', page_title: 'Home' });
    expect(h.pageViewEvents()).toHaveLength(0);
  });

  it('an unconfigured build (absent measurement id) emits zero page_views', () => {
    const h = setup({ stored: 'all', configured: false });
    h.core.initializeAnalytics();
    h.core.updateConsent('all');
    h.core.trackPageView({ page_type: 'home', page_path: '/', page_title: 'Home' });
    expect(h.pageViewEvents()).toHaveLength(0);
  });
});

describe('page_view — exactly one per navigation after consent (rapid navigation)', () => {
  it('N rapid trackPageView calls emit exactly N page_views (one per route transition)', () => {
    const h = setup({});
    h.core.initializeAnalytics();
    h.core.updateConsent('all');
    const routes: Array<{ page_type: 'home' | 'discover' | 'event_detail'; page_path: string }> = [
      { page_type: 'home', page_path: '/' },
      { page_type: 'discover', page_path: '/discover' },
      { page_type: 'event_detail', page_path: '/event/1' },
      { page_type: 'event_detail', page_path: '/event/2' },
      { page_type: 'discover', page_path: '/discover' },
    ];
    for (const r of routes) {
      h.core.trackPageView({ page_type: r.page_type, page_path: r.page_path, page_title: r.page_path });
    }
    expect(h.pageViewEvents()).toHaveLength(routes.length);
    // And none of them went out as a gtag('config') re-send (only the init config).
    expect(h.ga4ConfigCalls()).toHaveLength(1);
  });
});

describe('consent race — ordering of init vs. grant vs. track', () => {
  it('a page_view attempted before init is dropped; it works only after init + grant', () => {
    const h = setup({});
    // Before init: gtag exists (fake) but the module is not initialized.
    h.core.trackPageView({ page_type: 'home', page_path: '/', page_title: 'Home' });
    expect(h.pageViewEvents()).toHaveLength(0);

    h.core.initializeAnalytics();
    // Initialized but not yet granted → still dropped.
    h.core.trackPageView({ page_type: 'home', page_path: '/', page_title: 'Home' });
    expect(h.pageViewEvents()).toHaveLength(0);

    h.core.updateConsent('all');
    h.core.trackPageView({ page_type: 'discover', page_path: '/discover', page_title: 'Discover' });
    expect(h.pageViewEvents()).toHaveLength(1);
  });
});
