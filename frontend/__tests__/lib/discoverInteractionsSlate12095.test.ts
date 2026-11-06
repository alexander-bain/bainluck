/**
 * #12095 (Decide 37-B) — Discover events carry the slate they were served in.
 *
 * The slate is the feed's `edition` plus its `ranker_version`. The server sends
 * `ranker_version` only while `RANKING_SNAPSHOTS` is on, so with the switch off
 * no event gains a field: the queued item must be exactly what it was.
 *
 * Same fake window/localStorage harness as `discoverInteractionsConsent.test.ts`
 * (the jest environment here is `node`).
 */

export {};

import type { MarketShape } from '@/lib/marketShape';

type DI = typeof import('@/lib/discoverInteractions');

function setup(): DI {
  jest.resetModules();
  jest.useFakeTimers();
  const store: Record<string, string> = { bainluck_consent: 'all' };
  (global as unknown as { fetch: unknown }).fetch = jest.fn(() => Promise.resolve({ ok: true }));
  (global as unknown as { window: unknown }).window = {
    dataLayer: [],
    gtag: () => {},
    navigator: { userAgent: 'node' },
    location: { href: 'http://localhost/', pathname: '/' },
    addEventListener: () => {},
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
  const consent = require('@/lib/analytics/telemetryConsent') as typeof import('@/lib/analytics/telemetryConsent');
  const di = require('@/lib/discoverInteractions') as DI;
  di.setDiscoverLearningGate(() => true);
  consent.initTelemetryConsent();
  return di;
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

describe('#12095 slate fields on Discover events', () => {
  it('adds nothing while the server sends no ranker_version (switch off)', () => {
    const di = setup();
    di.noteDiscoverSlate({ edition: 'ae0bc760eb204e34' });
    di.sendDiscoverInteraction(ITEM, 'unlike', 2);
    const [queued] = di.peekPendingDiscoverInteractions();
    expect(queued).toEqual({
      action: 'unlike',
      item_type: 'futures',
      item_id: '1',
      category: 'politics',
      item_name: 'Test market',
      score: 50,
      rank: 3,
      surface: 'web',
      source: 'card',
      market_type: 'claim',
    });
  });

  it('carries the slate id, ranker version and position once the server names them', () => {
    const di = setup();
    di.noteDiscoverSlate({ edition: 'ae0bc760eb204e34', ranker_version: '0123456789ab' });
    di.sendDiscoverInteraction(ITEM, 'impression', 0, 'viewport');
    const [queued] = di.peekPendingDiscoverInteractions();
    expect(queued.slate_id).toBe('ae0bc760eb204e34');
    expect(queued.ranker_version).toBe('0123456789ab');
    expect(queued.rank).toBe(1);
  });

  it('a later page without the version clears the slate', () => {
    const di = setup();
    di.noteDiscoverSlate({ edition: 'a', ranker_version: 'v' });
    di.noteDiscoverSlate({ edition: 'b' });
    di.sendDiscoverInteraction(ITEM, 'like', 0);
    const [queued] = di.peekPendingDiscoverInteractions();
    expect('slate_id' in queued).toBe(false);
    expect('ranker_version' in queued).toBe(false);
  });
});
