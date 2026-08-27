/**
 * UX-P144 — `/api/feed/interactions` is consent-gated and batched.
 *
 * WHY THIS FILE EXISTS. `lib/discoverInteractions.ts` had no test at all, and
 * it was the one engagement rail on Discover that never asked for consent. It
 * POSTed every card a reader scrolled past — session id attached — whether they
 * had declined the banner or never answered it. The GA4 event fired on the same
 * line was gated; the localStorage profile never leaves the device; this call
 * did neither.
 *
 * It also sent ONE cross-origin request per card impression against an endpoint
 * that has always accepted 50 per request, so an ordinary scroll spent the
 * reader's own 60/minute anonymous budget on impression beacons. The 429s that
 * followed are cross-origin and unreadable to the page, so they surfaced as
 * opaque CORS console errors — which is how one client defect arrived on the
 * board as ~20 separate `console.no_errors` / `network.no_unexpected_failures`
 * issues across the `consent.*` journeys.
 *
 * The two arms are tested together because they are one defect: the denied
 * reader must produce ZERO requests, and the granted reader must produce ONE.
 *
 * There is no jsdom in this repo (`testEnvironment: "node"`), so this drives a
 * fake window/localStorage exactly as `analyticsTelemetryConsent.test.ts` does.
 */

export {}; // ensure module scope

import type { MarketShape } from '@/lib/marketShape';

type StoredConsent = 'all' | 'analytics' | 'none';

/** The subset of `RequestInit` this module sends, as the assertions read it. */
interface SentInit {
  method: string;
  headers: Record<string, string>;
  body: string;
  keepalive: boolean;
}

type FetchMock = jest.Mock<Promise<{ ok: boolean }>, [string, SentInit]>;

interface Harness {
  di: typeof import('@/lib/discoverInteractions');
  consent: typeof import('@/lib/analytics/telemetryConsent');
  fetchMock: FetchMock;
  store: Record<string, string>;
  /** Listeners the module registered on the fake window, by event name. */
  listeners: Record<string, Array<() => void>>;
  /** Bodies of every POST that actually left, parsed. */
  sentBatches: () => Array<{ interactions: unknown[]; provenance: string }>;
}

function setup(stored?: StoredConsent): Harness {
  jest.resetModules();
  jest.useFakeTimers();

  const store: Record<string, string> = {};
  if (stored) store['bainluck_consent'] = stored;

  const listeners: Record<string, Array<() => void>> = {};
  // The params are declared so `mock.calls` is typed as `[string, SentInit]`
  // rather than `[]` — otherwise every assertion below reads index 1 of an
  // empty tuple and the typecheck ratchet catches what jest cannot.
  const fetchMock: FetchMock = jest.fn((_url: string, _init: SentInit) =>
    Promise.resolve({ ok: true }),
  );

  (global as unknown as { fetch: unknown }).fetch = fetchMock;
  (global as unknown as { window: unknown }).window = {
    dataLayer: [],
    gtag: () => {},
    navigator: { userAgent: 'node' },
    location: { href: 'http://localhost/', pathname: '/' },
    addEventListener: (name: string, fn: () => void) => {
      (listeners[name] ||= []).push(fn);
    },
    dispatchEvent: () => true,
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

  const consent = require('@/lib/analytics/telemetryConsent') as Harness['consent'];
  const di = require('@/lib/discoverInteractions') as Harness['di'];

  // Hydrate the authority from the stored choice, the way AnalyticsProvider does.
  consent.initTelemetryConsent();

  return {
    di,
    consent,
    fetchMock,
    store,
    listeners,
    sentBatches: () =>
      fetchMock.mock.calls.map((c) => JSON.parse(c[1].body)),
  };
}

afterEach(() => {
  jest.useRealTimers();
});

const ITEM = {
  content_type: 'futures' as const,
  item_id: 1,
  category: 'politics',
  item_name: 'Test market',
  score: 50,
  market_type: 'claim' as MarketShape,
};

function item(id: number) {
  return { ...ITEM, item_id: id, item_name: `Market ${id}` };
}

// ===========================================================================
// The pure gate
// ===========================================================================

describe('mayCaptureDiscoverInteraction', () => {
  it('DENIES an undecided reader — null is a denial, not a soft default', () => {
    const h = setup();
    expect(h.di.mayCaptureDiscoverInteraction(null)).toBe(false);
  });

  it('DENIES an explicit decline', () => {
    const h = setup();
    expect(h.di.mayCaptureDiscoverInteraction('none')).toBe(false);
  });

  it('allows both grant levels', () => {
    const h = setup();
    expect(h.di.mayCaptureDiscoverInteraction('analytics')).toBe(true);
    expect(h.di.mayCaptureDiscoverInteraction('all')).toBe(true);
  });
});

// ===========================================================================
// Arm 1 — no grant, no request (the consent.* family)
// ===========================================================================

describe('consent gate at the wire', () => {
  it('sends NOTHING for a reader who has not answered the banner', () => {
    const h = setup(); // consent.untouched
    h.di.sendDiscoverInteraction(item(1), 'impression', 0, 'viewport');
    jest.advanceTimersByTime(10_000);
    expect(h.fetchMock).not.toHaveBeenCalled();
  });

  it('sends NOTHING after an explicit Decline', () => {
    const h = setup('none'); // consent.decline
    h.di.sendDiscoverInteraction(item(1), 'impression', 0, 'viewport');
    h.di.sendDiscoverInteraction(item(2), 'detail_click', 1);
    jest.advanceTimersByTime(10_000);
    expect(h.fetchMock).not.toHaveBeenCalled();
  });

  it('sends NOTHING even when a whole screenful of cards scrolls past', () => {
    const h = setup('none');
    for (let i = 0; i < 40; i += 1) {
      h.di.sendDiscoverInteraction(item(i), 'impression', i, 'viewport');
    }
    jest.advanceTimersByTime(10_000);
    expect(h.fetchMock).not.toHaveBeenCalled();
  });

  it('drops a batch queued BEFORE a revoke — a queued event must not land after it', () => {
    // consent.grant_then_revoke / consent.deferred_event.
    const h = setup('all');
    h.di.sendDiscoverInteraction(item(1), 'impression', 0, 'viewport');
    expect(h.di.peekPendingDiscoverInteractions()).toHaveLength(1);

    h.store['bainluck_consent'] = 'none';
    h.consent.__resetTelemetryConsentForTests();
    h.consent.initTelemetryConsent();

    jest.advanceTimersByTime(10_000);
    expect(h.fetchMock).not.toHaveBeenCalled();
    expect(h.di.peekPendingDiscoverInteractions()).toHaveLength(0);
  });

  it('does not send a denied reader’s queue on page hide either', () => {
    const h = setup('none');
    h.di.sendDiscoverInteraction(item(1), 'impression', 0, 'viewport');
    for (const fn of h.listeners['pagehide'] || []) fn();
    expect(h.fetchMock).not.toHaveBeenCalled();
  });
});

// ===========================================================================
// Arm 2 — a grant produces ONE request, not one per card
// ===========================================================================

describe('batching', () => {
  it('coalesces a screenful of impressions into a SINGLE request', () => {
    const h = setup('all');
    for (let i = 0; i < 12; i += 1) {
      h.di.sendDiscoverInteraction(item(i), 'impression', i, 'viewport');
    }
    // Nothing has left yet — the batch is still gathering.
    expect(h.fetchMock).not.toHaveBeenCalled();

    jest.advanceTimersByTime(2000);

    expect(h.fetchMock).toHaveBeenCalledTimes(1);
    const [batch] = h.sentBatches();
    expect(batch.interactions).toHaveLength(12);
    expect(batch.provenance).toBe('user');
  });

  it('never exceeds the server’s 50-per-request contract', () => {
    const h = setup('all');
    for (let i = 0; i < 50; i += 1) {
      h.di.sendDiscoverInteraction(item(i), 'impression', i, 'viewport');
    }
    // The 50th fills the batch and sends it immediately, without waiting.
    expect(h.fetchMock).toHaveBeenCalledTimes(1);
    expect(h.sentBatches()[0].interactions).toHaveLength(50);

    for (let i = 50; i < 60; i += 1) {
      h.di.sendDiscoverInteraction(item(i), 'impression', i, 'viewport');
    }
    jest.advanceTimersByTime(2000);
    expect(h.fetchMock).toHaveBeenCalledTimes(2);
    expect(h.sentBatches()[1].interactions).toHaveLength(10);
  });

  it('preserves every field the endpoint validates', () => {
    const h = setup('all');
    h.di.sendDiscoverInteraction(item(7), 'detail_click', 3, 'card');
    jest.advanceTimersByTime(2000);

    expect(h.sentBatches()[0].interactions[0]).toEqual({
      action: 'detail_click',
      item_type: 'futures',
      item_id: '7',
      category: 'politics',
      item_name: 'Market 7',
      score: 50,
      rank: 4, // positionIndex + 1
      surface: 'web',
      source: 'card',
      market_type: 'claim',
    });
  });

  it('flushes what is queued when the page goes away', () => {
    const h = setup('all');
    h.di.sendDiscoverInteraction(item(1), 'impression', 0, 'viewport');
    h.di.sendDiscoverInteraction(item(2), 'impression', 1, 'viewport');
    expect(h.fetchMock).not.toHaveBeenCalled();

    for (const fn of h.listeners['pagehide'] || []) fn();

    expect(h.fetchMock).toHaveBeenCalledTimes(1);
    expect(h.sentBatches()[0].interactions).toHaveLength(2);
  });

  it('sends the session id and the user provenance header', () => {
    const h = setup('all');
    h.di.sendDiscoverInteraction(item(1), 'like', 0);
    jest.advanceTimersByTime(2000);

    const init = h.fetchMock.mock.calls[0][1];
    expect(init.method).toBe('POST');
    expect(init.keepalive).toBe(true);
    expect(init.headers['X-Discover-Provenance']).toBe('user');
    expect(init.headers['x-session-id']).toBeTruthy();
  });

  it('a rejected request never surfaces to the caller', () => {
    const h = setup('all');
    h.fetchMock.mockImplementationOnce(() => Promise.reject(new Error('429')));
    expect(() => {
      h.di.sendDiscoverInteraction(item(1), 'impression', 0, 'viewport');
      jest.advanceTimersByTime(2000);
    }).not.toThrow();
  });
});
