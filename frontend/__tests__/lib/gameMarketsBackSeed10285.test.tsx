// #10285: Back to a finished game page must render its props and Additional Markets in the first
// frame, from the body the page last adopted, or the browser restores the scroll against a page
// that is 1,125px short and the reader lands far below the card they tapped.
import '../helpers/minimalDom';
import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { useGameMarketsStream } from '../../hooks/useGameMarketsStream';
import { fetchFreshGameMarkets, type LiveGameMarkets } from '../../lib/gameMarketsStream';
jest.mock('../../hooks/useMarketStream', () => ({ useMarketStream: jest.fn() }));
jest.mock('../../lib/gameMarketsStream', () => ({ ...jest.requireActual('../../lib/gameMarketsStream'), fetchFreshGameMarkets: jest.fn() }));
const fetcher = fetchFreshGameMarkets as jest.Mock;

const other = (outcome: string, probability: number, outcomeId: number) =>
  ({ market_name: 'Winning margin', outcome_name: outcome, probability, source: 'kalshi', _market_id: 500, contributor_outcome_ids: [outcomeId] });
const body = (id: number, extra: Partial<LiveGameMarkets> = {}, revisedAt = '2026-10-03T04:00:00Z') => ({
  event_id: id, status: 'completed', home_score: 31, away_score: 24, totals: [], player_props: [],
  other: [other('Home by 1-6', 0.97, 1), other('Away by 1-6', 0.02, 2)],
  outcome_market_ids: { 1: 500, 2: 500 }, outcome_revision_at: { 1: revisedAt, 2: revisedAt }, ...extra,
} as unknown as LiveGameMarkets);
const never = () => new Promise<LiveGameMarkets>(() => undefined);

let root: Root | undefined;
const seen: (LiveGameMarkets | undefined)[] = [];
function mount(id: number) {
  const container = document.createElement('div'); document.body.appendChild(container);
  root = createRoot(container);
  function Harness() { const { data } = useGameMarketsStream(id, id); seen.push(data); return null; }
  act(() => { root!.render(<Harness />); });
  return { last: () => seen.at(-1), unmount: () => act(() => { root!.unmount(); root = undefined; }) };
}
const drain = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };
beforeEach(() => { jest.useFakeTimers(); fetcher.mockReset(); seen.length = 0; Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' }); });
afterEach(() => { if (root) act(() => root!.unmount()); root = undefined; jest.useRealTimers(); });

test('a remounted game page renders its last body in the FIRST frame, then still reads fresh', async () => {
  fetcher.mockResolvedValueOnce(body(101));
  const first = mount(101); await act(drain);
  expect(first.last()?.other).toHaveLength(2);
  first.unmount();

  let finish!: (b: LiveGameMarkets) => void;
  fetcher.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  seen.length = 0;
  const back = mount(101);
  expect(seen[0]?.event_id).toBe(101);
  expect(seen[0]?.other).toHaveLength(2);
  expect(fetcher).toHaveBeenCalledTimes(2);

  await act(async () => { finish(body(101, { other: [other('Home by 1-6', 0.99, 1), other('Away by 1-6', 0.01, 2)] } as Partial<LiveGameMarkets>, '2026-10-03T04:05:00Z')); await drain(); });
  expect((back.last()?.other as unknown as { probability: number }[])[0].probability).toBe(0.99);
  back.unmount();
});

test('the held body seeds the reconciler, so a read it refuses is refused after Back too', async () => {
  fetcher.mockResolvedValueOnce(body(102));
  const first = mount(102); await act(drain); first.unmount();

  // A finished game whose next read says it is in play again is refused by the reconciler while the
  // page stays mounted. Without the seed the remounted reconciler would adopt it as a first read.
  fetcher.mockResolvedValueOnce(body(102, { status: 'in_progress', home_score: 30 } as Partial<LiveGameMarkets>));
  const back = mount(102); await act(drain);
  expect(fetcher).toHaveBeenCalledTimes(2);
  expect(back.last()?.status).toBe('completed');
  expect(back.last()?.home_score).toBe(31);
  back.unmount();
});

test('another game never renders a held body that is not its own', async () => {
  fetcher.mockResolvedValueOnce(body(103));
  const first = mount(103); await act(drain); first.unmount();
  fetcher.mockImplementation(never);
  seen.length = 0;
  const other104 = mount(104);
  expect(seen.every(data => data === undefined)).toBe(true);
  other104.unmount();
});

test('only the most recent eight games are held', async () => {
  for (const id of [201, 202, 203, 204, 205, 206, 207, 208, 209]) {
    fetcher.mockResolvedValueOnce(body(id));
    const view = mount(id); await act(drain); view.unmount();
  }
  fetcher.mockImplementation(never);
  seen.length = 0;
  const evicted = mount(201);
  expect(seen[0]).toBeUndefined();
  evicted.unmount();
  seen.length = 0;
  const kept = mount(209);
  expect(seen[0]?.event_id).toBe(209);
  kept.unmount();
});
