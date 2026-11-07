// #12283 — a finished game costs nothing live.
//
// Atlas, Sat Nov 7 (#12278): a finished NBA game's page (15342680) fetched
// `game-markets?fresh=true` (~967 KB, 423 market ids) and then opened nine 50-id
// `/api/markets/stream` connections for markets that were all settled. The API
// answered 409 to each and 429 to the ninth, and the page kept re-reading the
// fresh catalog every 60 s.
//
// Now: the served body names only markets the stream would admit (backend), and a
// finished game whose body names none is SETTLED: no stream, and its reads take the
// cached tier. A finished game with an open winner market is not settled yet.
import '../helpers/minimalDom';
import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { useGameMarketsStream } from '../../hooks/useGameMarketsStream';
import { useMarketStream } from '../../hooks/useMarketStream';
import { fetchFreshGameMarkets, settledGameMarkets, type LiveGameMarkets } from '../../lib/gameMarketsStream';

jest.mock('../../hooks/useMarketStream', () => ({ useMarketStream: jest.fn() }));
jest.mock('../../lib/gameMarketsStream', () => ({
  ...jest.requireActual('../../lib/gameMarketsStream'), fetchFreshGameMarkets: jest.fn(),
}));
const fetcher = fetchFreshGameMarkets as jest.Mock;
const stream = useMarketStream as jest.Mock;
// The hook holds each game's reconciler across mounts (#10285), so every test is its own game.
let game = 100;
const body = (status: string, ids: number[], id = game) =>
  ({ event_id: id, status, totals: [], player_props: [], other: [], stream_market_ids: ids } as unknown as LiveGameMarkets);

let root: Root | undefined;
function mount(finished: () => boolean) {
  const container = document.createElement('div'); document.body.appendChild(container);
  root = createRoot(container);
  const id = game;
  function Harness() { useGameMarketsStream(id, id, finished()); return null; }
  const render = () => act(() => { root!.render(<Harness />); });
  render();
  return render;
}
const drain = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };
const minute = async () => { await act(async () => { jest.advanceTimersByTime(60_250); await drain(); }); };
const lastStream = () => stream.mock.calls.at(-1)[0] as { marketIds: number[]; enabled: boolean };
const tiers = () => fetcher.mock.calls.map(call => (call[2] ?? true) ? 'fresh' : 'cached');

beforeEach(() => {
  jest.useFakeTimers(); fetcher.mockReset(); stream.mockClear(); game += 1;
  jest.spyOn(document, 'addEventListener').mockImplementation(() => {});
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
});
afterEach(() => { if (root) act(() => root!.unmount()); root = undefined; jest.restoreAllMocks(); jest.useRealTimers(); });

test('a finished game with nothing open: cached reads only, and no stream subscription', async () => {
  fetcher.mockResolvedValue(body('completed', []));
  mount(() => true);
  await act(drain);
  await minute(); await minute();
  expect(tiers()).toEqual(['cached', 'cached', 'cached']);
  expect(lastStream().enabled).toBe(false);
});

test('a finished game whose winner market is still open keeps its one stream and fresh reads', async () => {
  fetcher.mockResolvedValue(body('completed', [42]));
  mount(() => true);
  await act(drain);
  expect(lastStream()).toMatchObject({ enabled: true, marketIds: [42] });
  await minute();
  expect(tiers()).toEqual(['cached', 'fresh']);
});

test('a live page reads fresh and streams; once the game ends settled it stops both', async () => {
  let status = 'in_progress', ids = [1, 2, 3];
  fetcher.mockImplementation(async () => body(status, ids));
  mount(() => false);
  await act(drain);
  expect(lastStream()).toMatchObject({ enabled: true, marketIds: [1, 2, 3] });
  status = 'completed'; ids = [];
  await minute();
  expect(lastStream().enabled).toBe(false);
  await minute();
  expect(tiers()).toEqual(['fresh', 'fresh', 'cached']);
});

test('settledGameMarkets: finished AND nothing the stream would admit', () => {
  expect(settledGameMarkets(body('completed', []))).toBe(true);
  expect(settledGameMarkets(body('final', []))).toBe(true);
  expect(settledGameMarkets(body('completed', [42]))).toBe(false);
  expect(settledGameMarkets(body('in_progress', []))).toBe(false);
  expect(settledGameMarkets(undefined)).toBe(false);
});

describe('fetchFreshGameMarkets tier', () => {
  const real = jest.requireActual('../../lib/gameMarketsStream') as typeof import('../../lib/gameMarketsStream');
  test('the cached tier drops ?fresh=true and no-store; the default stays fresh', async () => {
    const spy = jest.fn(async () => ({ ok: true, json: async () => body('completed', []) }));
    (global as unknown as { fetch: unknown }).fetch = spy;
    await real.fetchFreshGameMarkets(7, new AbortController().signal, false);
    await real.fetchFreshGameMarkets(7, new AbortController().signal);
    const [cached, fresh] = spy.mock.calls as unknown as [string, RequestInit][];
    expect(cached[0]).toMatch(/\/api\/events\/7\/game-markets$/);
    expect(cached[1].cache).toBe('default');
    expect(fresh[0]).toMatch(/\/api\/events\/7\/game-markets\?fresh=true$/);
    expect(fresh[1].cache).toBe('no-store');
  });
});
