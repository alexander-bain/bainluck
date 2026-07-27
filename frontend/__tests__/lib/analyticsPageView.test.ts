/**
 * L2-190 Item 2 — exactly-one page view + real identity clearing.
 *
 * - `trackPageView` emits exactly ONE `page_view` (the old extra
 *   `gtag('config', …)` page-view re-send is gone).
 * - On logout, GA's configured `user_id` is explicitly cleared (config with
 *   `user_id: null`) so a subsequent anonymous event carries no prior identity,
 *   and the identity never appears in event params either.
 *
 * Driven directly against a fake window/gtag (no jsdom in this repo).
 */

export {}; // ensure module scope (isolates top-level decls from sibling tests)

type GtagCall = unknown[];

const ORIGINAL_ENV = process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID;

function setup() {
  jest.resetModules();
  process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID = 'G-TEST123';
  const calls: GtagCall[] = [];
  const gtag = (...args: unknown[]) => calls.push(args);
  (global as unknown as { window: unknown }).window = {
    dataLayer: [],
    gtag,
    navigator: { userAgent: 'node' },
    location: { href: 'http://localhost/', pathname: '/' },
  };
  (global as unknown as { localStorage: unknown }).localStorage = {
    getItem: () => null,
    setItem: () => undefined,
    removeItem: () => undefined,
  };
  (global as unknown as { document: unknown }).document = { title: 'T', referrer: '' };
  const core = require('@/lib/analytics/core') as typeof import('@/lib/analytics/core');
  core.initializeAnalytics();
  core.updateConsent('all'); // grant so events actually emit
  return {
    core,
    calls,
    pageViewEvents: () => calls.filter((c) => c[0] === 'event' && c[1] === 'page_view'),
    configCalls: () => calls.filter((c) => c[0] === 'config'),
    eventCalls: () => calls.filter((c) => c[0] === 'event'),
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

describe('page view counting', () => {
  it('emits exactly one page_view per trackPageView call', () => {
    const h = setup();
    h.core.trackPageView({ page_type: 'discover', page_path: '/discover', page_title: 'Discover' });
    expect(h.pageViewEvents()).toHaveLength(1);
  });

  it('does NOT re-send a page view via gtag config (the double-count fix)', () => {
    const h = setup();
    const configsBefore = h.configCalls().length;
    h.core.trackPageView({ page_type: 'home', page_path: '/', page_title: 'Home' });
    // No new config call was made for the page view.
    expect(h.configCalls().length).toBe(configsBefore);
  });

  it('two navigations emit exactly two page_views', () => {
    const h = setup();
    h.core.trackPageView({ page_type: 'home', page_path: '/', page_title: 'Home' });
    h.core.trackPageView({ page_type: 'discover', page_path: '/discover', page_title: 'Discover' });
    expect(h.pageViewEvents()).toHaveLength(2);
  });
});

describe('identity clearing on logout', () => {
  it('sets user_id on login and clears it (user_id: null) on logout', () => {
    const h = setup();
    h.core.setUserId('firebase-uid-123');
    const afterLogin = h.configCalls().at(-1)!;
    expect(afterLogin[2]).toMatchObject({ user_id: 'firebase-uid-123' });

    h.core.setUserId(undefined); // logout
    const afterLogout = h.configCalls().at(-1)!;
    expect(afterLogout[2]).toMatchObject({ user_id: null });
  });

  it('an anonymous event after logout carries no user_id in its params', () => {
    const h = setup();
    h.core.setUserId('firebase-uid-123');
    h.core.setUserId(undefined);
    h.core.trackEvent('feed_refresh', { trigger: 'auto', new_items_count: 1 });
    const evt = h.eventCalls().at(-1)!;
    expect(evt[1]).toBe('feed_refresh');
    expect(evt[2]).not.toHaveProperty('user_id');
  });
});
