import { createPriceDelivery } from '../../lib/discover/priceDelivery';
import type { DiscoverPriceCards } from '../../lib/discover/priceRefresh';
import type { FeedItem } from '../../lib/types';

const response: DiscoverPriceCards = { items: [], dispositions: {}, built_at: 1 };
const item = (id: number) => ({ type: 'futures', data: { id } } as unknown as FeedItem);
function rig(count = 1) {
  let visible = Array.from({ length: count }, (_, i) => item(i + 1));
  const fetch = jest.fn<Promise<DiscoverPriceCards>, [FeedItem[], AbortSignal]>().mockResolvedValue(response);
  const accept = jest.fn();
  const delivery = createPriceDelivery({ visible: () => visible, fetch, accept, now: () => Date.now(), setTimer: setTimeout, clearTimer: clearTimeout });
  return { delivery, fetch, accept, visible: (items: FeedItem[]) => { visible = items; } };
}
beforeEach(() => { jest.useFakeTimers(); jest.setSystemTime(0); });
afterEach(() => { jest.useRealTimers(); });

test('a burst coalesces and every batch observes the two-second dispatch floor', async () => {
  const r = rig(75); r.delivery.start();
  await jest.advanceTimersByTimeAsync(0);
  expect(r.fetch.mock.calls[0][0]).toHaveLength(50);
  for (let i = 0; i < 1000; i++) r.delivery.invalidate();
  await jest.advanceTimersByTimeAsync(1999);
  expect(r.fetch).toHaveBeenCalledTimes(1);
  await jest.advanceTimersByTimeAsync(1);
  expect(r.fetch).toHaveBeenCalledTimes(2);
  expect((r.fetch.mock.calls[1][0][0].data as { id: number }).id).toBe(51);
  await jest.advanceTimersByTimeAsync(2000);
  expect(r.fetch).toHaveBeenCalledTimes(3);
  await jest.advanceTimersByTimeAsync(2000);
  expect(r.fetch).toHaveBeenCalledTimes(3);
  r.delivery.stop();
});
test('429 cools down across hide/show and retries without a new push', async () => {
  const r = rig();
  r.fetch.mockRejectedValueOnce({ status: 429, retryAfterMs: 17_000 });
  r.delivery.start(); await jest.advanceTimersByTimeAsync(0);
  r.delivery.stop(); r.delivery.start();
  for (let i = 0; i < 100; i++) r.delivery.invalidate();
  await jest.advanceTimersByTimeAsync(16_999);
  expect(r.fetch).toHaveBeenCalledTimes(1);
  await jest.advanceTimersByTimeAsync(1);
  expect(r.fetch).toHaveBeenCalledTimes(2);
  r.delivery.stop();
});
test('an unknown429 and a failed last read recover after sixty seconds without more frames', async () => {
  const r = rig(); r.fetch.mockRejectedValueOnce({ status: 429 }).mockRejectedValueOnce(new Error('offline'));
  r.delivery.start(); await jest.advanceTimersByTimeAsync(0);
  await jest.advanceTimersByTimeAsync(59_999); expect(r.fetch).toHaveBeenCalledTimes(1);
  await jest.advanceTimersByTimeAsync(1); expect(r.fetch).toHaveBeenCalledTimes(2);
  await jest.advanceTimersByTimeAsync(60_000); expect(r.fetch).toHaveBeenCalledTimes(3);
  r.delivery.stop();
});
test('no overlapping requests; teardown aborts and late responses cannot paint', async () => {
  const r = rig(); let resolve!: (value: DiscoverPriceCards) => void;
  r.fetch.mockImplementationOnce(() => new Promise(done => { resolve = done; }));
  r.delivery.start(); await jest.advanceTimersByTimeAsync(0);
  r.delivery.invalidate(); await jest.advanceTimersByTimeAsync(5000);
  expect(r.fetch).toHaveBeenCalledTimes(1);
  const signal = r.fetch.mock.calls[0][1];
  r.delivery.stop(); expect(signal.aborted).toBe(true);
  resolve(response); await Promise.resolve(); await Promise.resolve();
  expect(r.accept).not.toHaveBeenCalled();
  await jest.advanceTimersByTimeAsync(120_000); expect(r.fetch).toHaveBeenCalledTimes(1);
});
test('visibility changes while waiting prevent reads and paint for removed identities', async () => {
  const r = rig(); r.delivery.start(); await jest.advanceTimersByTimeAsync(0);
  r.delivery.invalidate(); r.visible([]);
  await jest.advanceTimersByTimeAsync(2000);
  expect(r.fetch).toHaveBeenCalledTimes(1);
  r.delivery.stop();
});
test('healthy heartbeat-only silence still reconciles authoritative REST', async () => {
  const r = rig(); r.delivery.start(); await jest.advanceTimersByTimeAsync(0);
  await jest.advanceTimersByTimeAsync(60_000);
  await jest.advanceTimersByTimeAsync(1); // run the fallback's newly queued dispatch
  expect(r.fetch).toHaveBeenCalledTimes(2);
  r.delivery.stop();
});
