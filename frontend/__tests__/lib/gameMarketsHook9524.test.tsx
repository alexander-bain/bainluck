import '../helpers/minimalDom';
import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { useGameMarketsStream } from '../../hooks/useGameMarketsStream';
import { useMarketStream } from '../../hooks/useMarketStream';
import { fetchFreshGameMarkets, type LiveGameMarkets } from '../../lib/gameMarketsStream';
jest.mock('../../hooks/useMarketStream', () => ({ useMarketStream: jest.fn() }));
jest.mock('../../lib/gameMarketsStream', () => ({ ...jest.requireActual('../../lib/gameMarketsStream'), fetchFreshGameMarkets: jest.fn() }));
const fetcher = fetchFreshGameMarkets as jest.Mock;
const stream = useMarketStream as jest.Mock;
const body = (id = 7) => ({ event_id: id, status: 'scheduled', totals: [], player_props: [], other: [], stream_market_ids: Array.from({ length: 101 }, (_, i) => i + 1) } as unknown as LiveGameMarkets);
let root: Root | undefined;
let visibilityListener: (() => void) | undefined;
function renderHook<P>(hook: (props: P) => ReturnType<typeof useGameMarketsStream>, options?: { initialProps: P }) {
  const result = { current: undefined as unknown as ReturnType<typeof useGameMarketsStream> };
  const container = document.createElement('div'); document.body.appendChild(container);
  root = createRoot(container);
  function Harness({ value }: { value: P }) { result.current = hook(value); return <>{result.current.data?.event_id ?? 'loading'}</>; }
  const render = (value: P) => act(() => { root!.render(<Harness value={value} />); });
  render(options?.initialProps as P);
  return { result, rerender: render, unmount: () => act(() => { root!.unmount(); root = undefined; }) };
}
const drain = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };
beforeEach(() => { jest.useFakeTimers(); fetcher.mockReset(); stream.mockClear(); visibilityListener = undefined; jest.spyOn(document, 'addEventListener').mockImplementation((type, callback) => { if (type === 'visibilitychange') visibilityListener = callback as () => void; }); Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' }); });
afterEach(() => { if (root) act(() => root!.unmount()); root = undefined; jest.restoreAllMocks(); jest.useRealTimers(); });

test('scheduled held page reads fresh immediately and subscribes all101 IDs without a page refresh', async () => {
  fetcher.mockResolvedValue(body());
  const view = renderHook(() => useGameMarketsStream(7, 7));
  await act(drain);
  expect(view.result.current.data?.event_id).toBe(7);
  expect(stream.mock.calls.at(-1)[0].marketIds).toHaveLength(101);
  act(() => stream.mock.calls.at(-1)[0].onInvalidate([70]));
  expect(fetcher).toHaveBeenCalledTimes(1);
  await act(async () => { jest.advanceTimersByTime(2000); await drain(); });
  expect(fetcher).toHaveBeenCalledTimes(2);
  view.unmount();
});
test('route navigation aborts and refuses old delayed body', async () => {
  let finish!: (body: LiveGameMarkets) => void;
  fetcher.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; })).mockResolvedValue(body(8));
  const view = renderHook(({ id }) => useGameMarketsStream(id, id), { initialProps: { id: 7 } });
  const oldSignal = fetcher.mock.calls[0][1] as AbortSignal;
  view.rerender({ id: 8 }); await act(drain);
  expect(oldSignal.aborted).toBe(true);
  await act(async () => { finish(body(7)); await drain(); });
  expect(view.result.current.data?.event_id).toBe(8);
  view.unmount();
});
test('hidden page does no work; visibility returns owed read and429 honors cooldown', async () => {
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' });
  fetcher.mockRejectedValueOnce({ status: 429, retryAfterMs: 70000 }).mockResolvedValue(body());
  const view = renderHook(() => useGameMarketsStream(7, 7));
  expect(fetcher).not.toHaveBeenCalled();
  await act(async () => { Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' }); visibilityListener?.(); await drain(); });
  expect(fetcher).toHaveBeenCalledTimes(1);
  await act(async () => { jest.advanceTimersByTime(60000); await drain(); });
  expect(fetcher).toHaveBeenCalledTimes(1);
  await act(async () => { jest.advanceTimersByTime(10000); await drain(); });
  expect(fetcher).toHaveBeenCalledTimes(2);
  expect(view.result.current.data?.event_id).toBe(7);
  view.unmount();
});
