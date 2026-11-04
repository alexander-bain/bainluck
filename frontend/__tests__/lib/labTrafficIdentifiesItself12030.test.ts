/**
 * #12030 — our own lab browsers identify themselves, and the visitor counts skip them.
 *
 * 216 of GA4's 224 web users in 28 days were the daily Browser audit (Azure
 * runners, "Desktop Chrome" = Windows and "Pixel 5" = Android, ~4 consent grants
 * per profile per run). The flag is `?bl_lab=<name>`, kept in localStorage for the
 * rest of that browser's visit. A marked visit: GA4 hits carry
 * `traffic_type: 'internal'`; Vercel Web Analytics drops it in `beforeSend`
 * (TelemetryGate). Consent behaves exactly as for a person.
 *
 * Driven against a fake window/gtag/localStorage like `analyticsInitContract`
 * (jest runs in `node`, no jsdom); the gate's wiring is read off its source.
 */

import fs from 'fs';
import path from 'path';

export {};

const FRONTEND = path.resolve(__dirname, '..', '..');
const MEASUREMENT_ID = 'G-TEST123';
const ORIGINAL_ENV = process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID;

type Store = Record<string, string>;

function fakeBrowser(opts: { search?: string; store?: Store; storageThrows?: boolean } = {}) {
  const store: Store = { ...(opts.store ?? {}) };
  const calls: unknown[][] = [];
  (global as unknown as { window: unknown }).window = {
    dataLayer: [],
    gtag: (...args: unknown[]) => calls.push(args),
    navigator: { userAgent: 'node' },
    location: { href: `http://localhost/${opts.search ?? ''}`, pathname: '/', search: opts.search ?? '' },
  };
  (global as unknown as { localStorage: unknown }).localStorage = {
    getItem: (k: string) => {
      if (opts.storageThrows) throw new Error('storage disabled');
      return k in store ? store[k] : null;
    },
    setItem: (k: string, v: string) => {
      if (opts.storageThrows) throw new Error('storage disabled');
      store[k] = v;
    },
    removeItem: (k: string) => {
      delete store[k];
    },
  };
  (global as unknown as { document: unknown }).document = { title: 'T', referrer: '' };
  return { store, calls };
}

function lab() {
  jest.resetModules();
  return require('@/lib/analytics/labTraffic') as typeof import('@/lib/analytics/labTraffic');
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

describe('the flag', () => {
  it('a person is not lab traffic', () => {
    fakeBrowser();
    expect(lab().readLabTraffic()).toBeNull();
  });

  it('?bl_lab=<name> marks the visit and is kept for the rest of it', () => {
    const { store } = fakeBrowser({ search: '?bl_lab=browser-audit' });
    const m = lab();
    expect(m.readLabTraffic()).toBe('browser-audit');
    expect(store[m.LAB_TRAFFIC_STORAGE_KEY]).toBe('browser-audit');
    // The next page of the same visit carries no query and is still marked.
    fakeBrowser({ store });
    expect(lab().readLabTraffic()).toBe('browser-audit');
  });

  it('a lab that writes the key before the first page script is marked', () => {
    fakeBrowser({ store: { bainluck_lab_traffic: 'browser-audit' } });
    expect(lab().readLabTraffic()).toBe('browser-audit');
  });

  it.each(['', 'Browser Audit', 'a/b', '<script>', 'x'.repeat(41)])(
    'refuses a malformed name %p',
    (name) => {
      fakeBrowser({ search: `?bl_lab=${encodeURIComponent(name)}`, store: { bainluck_lab_traffic: name } });
      expect(lab().readLabTraffic()).toBeNull();
    },
  );

  it('storage that throws still marks the page the URL marks, and never throws', () => {
    fakeBrowser({ search: '?bl_lab=probe', storageThrows: true });
    expect(lab().readLabTraffic()).toBe('probe');
    fakeBrowser({ storageThrows: true });
    expect(lab().readLabTraffic()).toBeNull();
  });

  it('server render is never lab traffic', () => {
    expect(lab().readLabTraffic()).toBeNull();
  });
});

describe('GA4: a marked visit is tagged internal, a person is not', () => {
  function init(opts: Parameters<typeof fakeBrowser>[0]) {
    jest.resetModules();
    process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID = MEASUREMENT_ID;
    const browser = fakeBrowser(opts);
    const core = require('@/lib/analytics/core') as typeof import('@/lib/analytics/core');
    core.initializeAnalytics();
    return browser.calls.filter((c) => c[0] === 'set');
  }

  it('the lab sets traffic_type internal alongside the platform', () => {
    const sets = init({ search: '?bl_lab=browser-audit' });
    expect(sets).toContainEqual(['set', expect.objectContaining({ traffic_type: 'internal' })]);
  });

  it('a person carries no traffic_type at all (control)', () => {
    const sets = init({});
    expect(sets.length).toBeGreaterThan(0);
    for (const call of sets) expect(call[1]).not.toHaveProperty('traffic_type');
  });
});

describe('Vercel Web Analytics: the gate drops a marked visit', () => {
  const gate = fs.readFileSync(path.join(FRONTEND, 'components', 'Analytics', 'TelemetryGate.tsx'), 'utf8');

  it('registers a beforeSend that returns null, only when readLabTraffic() marks the visit', () => {
    const effect = gate.slice(gate.indexOf('if (!readLabTraffic()) return;'));
    expect(effect.length).toBeGreaterThan(0);
    expect(gate).toContain("import { readLabTraffic } from '@/lib/analytics/labTraffic';");
    expect(effect).toMatch(/w\.va\('beforeSend', \(\) => null\)/);
    // Through Vercel's own command queue, so the D96 root-layout mount is untouched.
    expect(effect).toMatch(/\(w\.vaq = w\.vaq \|\| \[\]\)\.push\(args\)/);
  });
});

describe('the Browser audit identifies itself', () => {
  const fixture = fs.readFileSync(path.join(FRONTEND, 'e2e', 'fixtures', 'audit.ts'), 'utf8');

  it('every journey marks its context before the test body runs', () => {
    const journey = fixture.slice(fixture.indexOf('journey: async ({ page }, use, testInfo) => {'));
    expect(journey.indexOf('await markLabTraffic(page);')).toBeGreaterThan(0);
    expect(journey.indexOf('await markLabTraffic(page);')).toBeLessThan(journey.indexOf('await use(recorder);'));
  });

  it('it writes the site’s own key, and stubs only the counting beacons', () => {
    const { LAB_TRAFFIC_STORAGE_KEY } = lab();
    expect(fixture).toContain(`LAB_TRAFFIC_STORAGE_KEY = "${LAB_TRAFFIC_STORAGE_KEY}"`);
    expect(fixture).toContain('route.fulfill({ status: 204, body: "" })');
    // The page still loads gtag.js itself: only `/collect` and Vercel's view/event are stubbed.
    const beacon = fixture.slice(
      fixture.indexOf('export function isCountingBeacon'),
      fixture.indexOf('async function markLabTraffic'),
    );
    expect(beacon).toMatch(/parsed\.pathname\.includes\("\/collect"\)/);
    expect(beacon).toContain('"/_vercel/insights/view"');
    expect(beacon).not.toMatch(/googletagmanager|gtag\/js|speed-insights/);
  });
});
