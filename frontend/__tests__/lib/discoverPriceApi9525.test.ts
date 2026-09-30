import { fetchDiscoverPriceCards, setAuthTokenGetter } from '../../lib/api';

const originalFetch = global.fetch;
afterEach(() => { global.fetch = originalFetch; setAuthTokenGetter(null); });

test('a price-card429 reaches its dispatcher immediately with cooldown; no hidden retry', async () => {
  const fetch = jest.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'slow down', retry_after: 17 }), {
    status: 429, headers: { 'content-type': 'application/json', 'retry-after': '17' },
  }));
  global.fetch = fetch;
  await expect(fetchDiscoverPriceCards([1], [2])).rejects.toMatchObject({ status: 429, retryAfterMs: 17_000 });
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(fetch.mock.calls[0][0]).toContain('/api/feed/price-cards?event_ids=1&market_ids=2');
  expect(fetch.mock.calls[0][1]).toMatchObject({ cache: 'no-store' });
});

test('an already-aborted price-card read never dispatches HTTP', async () => {
  const fetch = jest.fn(); global.fetch = fetch;
  const controller = new AbortController(); controller.abort();
  await expect(fetchDiscoverPriceCards([1], [], controller.signal)).rejects.toMatchObject({ name: 'AbortError' });
  expect(fetch).not.toHaveBeenCalled();
});

test('a successful price-card read keeps the exact authoritative response body', async () => {
  const body = { items: [], dispositions: { 'event-1': 'unresolved' }, built_at: 123 };
  global.fetch = jest.fn().mockResolvedValue(new Response(JSON.stringify(body), { status: 200 }));
  await expect(fetchDiscoverPriceCards([1], [])).resolves.toEqual(body);
});
