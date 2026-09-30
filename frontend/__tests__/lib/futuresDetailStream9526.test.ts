import { createFuturesDetailReconciler, createFuturesReadScheduler, reconcileFuturesHistory } from '../../lib/futuresDetailStream';
import type { FuturesMarketDetailResponse, FuturesHistoryResponse } from '../../lib/types';

const clock = (second: number) => `2030-01-01T00:00:${String(second).padStart(2, '0')}Z`;
function market(a: number | null = .3, b: number | null = .7, timeA: string | null = clock(1), timeB: string | null = clock(1)) {
  return { id: 7, status: 'open', source: 'kalshi', external_id: 'k7', bookmakers: ['kalshi'],
    outcomes: [{ id: 1, probability: a, last_updated: timeA, is_winner: null },
      { id: 2, probability: b, last_updated: timeB, is_winner: null }] } as FuturesMarketDetailResponse;
}
function history(value: number, second: number): FuturesHistoryResponse {
  return { market_id: 7, market_name: 'A', hours: 168, outcomes: [{ outcome_id: 1, name: 'A',
    history: [{ timestamp: clock(second), probability: value, american_odds: null, bookmaker: 'kalshi' }] }] };
}
const drain = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };

test('each outcome orders its own quote, and retained values cannot change provider', () => {
  const r = createFuturesDetailReconciler(market());
  const next = r.adopt(market(.4, .6, clock(2), clock(0)));
  expect(next.outcomes.map(row => row.probability)).toEqual([.4, .7]);
  expect(r.adopt({ ...market(.5, .8, clock(3), null), source: 'polymarket' })).toBe(next);
  expect(r.adopt(market(.9, .7, clock(2), clock(1))).outcomes[0].probability).toBe(.4);
});

test.each([clock(1), null])('withdrawal %s hides price without fabricated clock; cached quote cannot revive it', time => {
  const r = createFuturesDetailReconciler(market());
  expect(r.adopt(market(null, .7, time)).outcomes[0]).toMatchObject({ probability: null, last_updated: time });
  expect(r.adopt(market()).outcomes[0].probability).toBeNull();
  expect(r.adopt(market(.9, .7, null)).outcomes[0].probability).toBeNull();
  expect(r.adopt(market(.4, .7, clock(2))).outcomes[0].probability).toBe(.4);
});

test('initial unknown-clock withdrawal is also fenced; older null cannot erase newer quote', () => {
  const r = createFuturesDetailReconciler(market(null, .7, null));
  expect(r.adopt(market(.9, .7, null)).outcomes[0].probability).toBeNull();
  expect(r.adopt(market(.4, .7, clock(2))).outcomes[0].probability).toBe(.4);
  expect(r.adopt(market(null, .7, clock(1))).outcomes[0].probability).toBe(.4);
});

test('settled winner survives stale open responses and conflicting verdicts', () => {
  const r = createFuturesDetailReconciler(market());
  const final = { ...market(1, 0, null, null), status: 'resolved' as const };
  final.outcomes[0].is_winner = true;
  final.outcomes[1].is_winner = false;
  expect(r.adopt(final)).toBe(final);
  expect(r.adopt(market())).toBe(final);
  const conflicting = { ...final, outcomes: final.outcomes.map(row => ({ ...row, is_winner: !row.is_winner })) };
  expect(r.adopt(conflicting)).toBe(final);
});

test('history never invents points or replaces a newer tail with delayed data', () => {
  const prior = history(.4, 2);
  expect(reconcileFuturesHistory(prior, history(.3, 1)).outcomes[0]).toBe(prior.outcomes[0]);
  expect(reconcileFuturesHistory(prior, history(.8, 2)).outcomes[0]).toBe(prior.outcomes[0]);
  expect(reconcileFuturesHistory(prior, history(.5, 3)).outcomes[0].history).toEqual(history(.5, 3).outcomes[0].history);
  expect(reconcileFuturesHistory(prior, { ...history(.3, 1), hours: 24 }).hours).toBe(24);
});

test('one inflight read and one trailing read preserve bursts with a two-second dispatch floor', async () => {
  let now = 0;
  let finish!: () => void;
  const read = jest.fn(() => new Promise<void>(resolve => { finish = resolve; }));
  const r = createFuturesReadScheduler({ now: () => now, read });
  r.request(); r.request(); r.request();
  expect(read).toHaveBeenCalledTimes(1);
  finish(); await drain(); now = 1999; r.tick();
  expect(read).toHaveBeenCalledTimes(1);
  now = 2000; r.tick(); expect(read).toHaveBeenCalledTimes(2);
  finish(); await drain(); r.stop();
});

test('429 honors server cooldown and failed final read retries with no further invalidation', async () => {
  let now = 0;
  const read = jest.fn().mockRejectedValueOnce({ status: 429, retryAfterMs: 70000 }).mockResolvedValue(undefined);
  const r = createFuturesReadScheduler({ now: () => now, read });
  r.request(); await drain(); now = 60000; r.request(); r.tick();
  expect(read).toHaveBeenCalledTimes(1);
  now = 70000; r.tick(); await drain(); expect(read).toHaveBeenCalledTimes(2);
  r.stop();
});

test('last transport failure remains owed, hiding aborts and fences its callback', async () => {
  let now = 0, current!: () => boolean;
  const read = jest.fn().mockRejectedValueOnce(new Error('network')).mockImplementationOnce(async (_signal, isCurrent) => { current = isCurrent; });
  const r = createFuturesReadScheduler({ now: () => now, read });
  r.request(); await drain(); now = 59999; r.tick(); expect(read).toHaveBeenCalledTimes(1);
  now = 60000; r.tick(); await drain(); expect(current()).toBe(true);
  r.setVisible(false); expect(current()).toBe(false); now = 120000; r.tick(); expect(read).toHaveBeenCalledTimes(2);
  r.stop();
});

test('an authoritative result permits its final chart value at the same snapshot clock', () => {
  const final = { ...market(1, 0), status: 'resolved' as const };
  final.outcomes[0].is_winner = true;
  expect(reconcileFuturesHistory(history(.4, 2), history(1, 2), final).outcomes[0].history[0].probability).toBe(1);
});

test('explicit settled loser remains graded when a delayed payload forgets its verdict', () => {
  const settled = { ...market(1, 0), status: 'resolved' as const };
  settled.outcomes[0].is_winner = true;
  settled.outcomes[1].is_winner = false;
  const r = createFuturesDetailReconciler(settled);
  const forgotten = { ...settled, outcomes: settled.outcomes.map(row => ({ ...row, is_winner: row.id === 2 ? null : row.is_winner })) };
  expect(r.adopt(forgotten).outcomes[1].is_winner).toBe(false);
});

test('equivalent ISO encodings cannot sneak a conflicting equal-instant history tail through', () => {
  const prior = history(.4, 2), conflict = history(.8, 2);
  conflict.outcomes[0].history[0].timestamp = '2030-01-01T00:00:02.000+00:00';
  expect(reconcileFuturesHistory(prior, conflict).outcomes[0]).toBe(prior.outcomes[0]);
});

test('mutually exclusive fields adopt one normalized divisor and never mix old/new vectors', () => {
  const old = { ...market(.3, .7), mutually_exclusive: true };
  const r = createFuturesDetailReconciler(old);
  const normalized = { ...market(.4, .6, clock(2), clock(1)), mutually_exclusive: true };
  expect(r.adopt(normalized)).toBe(normalized);
  const mixedAge = { ...market(.5, .5, clock(3), clock(0)), mutually_exclusive: true };
  expect(r.adopt(mixedAge)).toBe(normalized);
  const withdrawn = { ...market(null, 1, clock(2), clock(1)), mutually_exclusive: true };
  expect(r.adopt(withdrawn)).toBe(withdrawn);
});

test('microsecond observation advances and regressions stay ordered within one millisecond', () => {
  const r = createFuturesDetailReconciler(market(.3, .7, '2030-01-01T00:00:01.000001Z'));
  expect(r.adopt(market(.4, .7, '2030-01-01T00:00:01.000002Z')).outcomes[0].probability).toBe(.4);
  expect(r.adopt(market(.9, .7, '2030-01-01T00:00:01.000001Z')).outcomes[0].probability).toBe(.4);
});
