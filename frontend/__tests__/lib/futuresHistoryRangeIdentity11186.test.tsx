/** @jest-environment jsdom */
/** #11186: the real hook under real SWR keeps 1M and All in their own requested
 * range. For a market younger than 30 days both rungs ask for 720 hours and
 * only `range=full` tells them apart, so an hours-only fence lets a held body
 * of one range become the other range's parent, and the live re-read then
 * writes that mixture into the selected SWR key. */
import React, { useState } from 'react';
import { act } from 'react-dom/test-utils';
import { createRoot } from 'react-dom/client';
import useSWR, { SWRConfig, unstable_serialize } from 'swr';
import SWRProvider from '@/components/SWRProvider';
import { useFuturesDetailStream } from '@/hooks/useFuturesDetailStream';
import { fetchFuturesMarket, fetchFuturesHistory } from '@/lib/api';
import { historyAnswersRequest } from '@/lib/futuresDetailStream';
import { FULL_HISTORY_RANGE, type HistoryRangeRequest } from '@/lib/historyRange';
import { VERIFIED_TITLE } from '@/lib/verifiedTitleDetail';
import type { FuturesMarketDetailResponse, FuturesHistoryResponse } from '@/lib/types';
import canonical from '../fixtures/verifiedTitle10224/detail-kalshi-default.json';

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
const delay = (ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms));
async function until(predicate: () => boolean, what: string) {
  const deadline = Date.now() + 2000;
  while (!predicate()) {
    if (Date.now() > deadline) throw new Error(`boundary did not arrive: ${what}`);
    await act(async () => { await delay(5); });
  }
}
function deferred<T>() {
  let finish!: (value: T) => void;
  let resolved = false;
  const promise = new Promise<T>(done => { finish = done; });
  return { promise, resolve: (value: T) => { resolved = true; finish(value); }, resolved: () => resolved };
}

class Wire {
  static all: Wire[] = [];
  readyState = 1;
  listeners = new Map<string, (event: unknown) => void>();
  constructor(readonly url: string) { Wire.all.push(this); }
  addEventListener(name: string, callback: (event: unknown) => void) { this.listeners.set(name, callback); }
  close() { this.readyState = 2; }
  emit(name: string, data: unknown = {}) { this.listeners.get(name)?.({ data: JSON.stringify(data) }); }
}

const marketSeed = JSON.parse(JSON.stringify(canonical)) as FuturesMarketDetailResponse;
const chosen = marketSeed.outcomes.find(row => row.id === 643833)!;
const sibling = marketSeed.outcomes.find(row => row.id === 643829)!;
const HOURS = 720; // 1M and All are both 720h for a market younger than 30 days
const clock = (second: number) => '2030-01-01T00:00:0' + second + 'Z';
const ARCHIVE = '2029-10-01T00:00:00Z'; // older than 1M's window: only a full read draws it
type Range = HistoryRangeRequest | undefined;
type Route = 'page-hours' | 'page-full' | 'fresh-hours' | 'fresh-full';

/** One served body: Buffalo's tail at `second`, San Francisco's at `other`.
 * `full` stamps the server's `range=full` answer; `legacy` leaves it off, as a
 * server that ignores the option does. Two lines, because reconciliation keeps
 * or replaces each line separately: a wrong parent shows up as a MIXTURE. */
type Tail = { second: number; probability: number };
const body = (o: Tail & { other?: Tail; full?: boolean; archive?: boolean; legacy?: boolean }): FuturesHistoryResponse => {
  const line = (outcome: typeof chosen, tail: Tail) => ({ outcome_id: outcome.id, name: outcome.name, history: [
    ...(o.archive ? [{ timestamp: ARCHIVE, probability: .05, american_odds: null, bookmaker: 'consensus' }] : []),
    { timestamp: clock(0), probability: .1, american_odds: null, bookmaker: 'consensus' },
    { timestamp: clock(tail.second), probability: tail.probability, american_odds: null, bookmaker: 'consensus' },
  ] });
  return {
    market_id: marketSeed.id, market_name: marketSeed.name, hours: HOURS, actual_hours: HOURS,
    sparse: true, total_data_points: o.archive ? 6 : 4,
    ...(o.full && !o.legacy ? { history_range: { requested: FULL_HISTORY_RANGE, window_start: o.archive ? ARCHIVE : clock(0),
      window_start_basis: o.archive ? 'archive_first_interval' : 'hours', archive_coverage: o.archive ? 'complete' : null, thinned_outcomes: [] } } : {}),
    outcomes: [line(chosen, o), line(sibling, o.other ?? { second: 1, probability: .15 })],
  };
};

function rig(initial: Range, cached: Partial<Record<'hours' | 'full', FuturesHistoryResponse>>) {
  const marketKey = ['futures-market', marketSeed.id, VERIFIED_TITLE];
  const keyOf = (range: Range) => ['futures-history', marketSeed.id, HOURS, range ?? ''];
  const cache = new Map<string, { data: unknown; _k: unknown }>([[unstable_serialize(marketKey), { data: marketSeed, _k: marketKey }]]);
  if (cached.hours) cache.set(unstable_serialize(keyOf(undefined)), { data: cached.hours, _k: keyOf(undefined) });
  if (cached.full) cache.set(unstable_serialize(keyOf(FULL_HISTORY_RANGE)), { data: cached.full, _k: keyOf(FULL_HISTORY_RANGE) });
  const reads: Record<Route, ReturnType<typeof deferred<FuturesHistoryResponse>>[]> = { 'page-hours': [], 'page-full': [], 'fresh-hours': [], 'fresh-full': [] };
  const consumed: Record<Route, ReturnType<typeof deferred<FuturesHistoryResponse>>[]> = { 'page-hours': [], 'page-full': [], 'fresh-hours': [], 'fresh-full': [] };
  const offered: { range: Range; body: FuturesHistoryResponse }[] = [];
  let skew = 0;
  const realNow = Date.now;
  const previousFetch = global.fetch, previousWire = global.EventSource;
  Wire.all = [];
  global.EventSource = Wire as unknown as typeof EventSource;
  Date.now = () => realNow() + skew;
  global.fetch = jest.fn(async (input: unknown) => {
    const url = String(input);
    if (!url.includes('/history?')) return { ok: true, status: 200, json: async () => marketSeed, headers: { get: (): null => null } };
    const route = `${url.includes('fresh=true') ? 'fresh' : 'page'}-${url.includes('range=full') ? 'full' : 'hours'}` as Route;
    const read = deferred<FuturesHistoryResponse>(), done = deferred<FuturesHistoryResponse>();
    reads[route].push(read); consumed[route].push(done);
    const result = await read.promise;
    return { ok: true, status: 200, json: async () => { done.resolve(result); return result; }, headers: { get: (): null => null } };
  }) as unknown as typeof fetch;

  let select!: (range: Range) => void;
  function Caller() {
    const [range, setRange] = useState<Range>(initial);
    select = setRange;
    const { data: market, mutate: refreshMarket } = useSWR(
      marketKey, () => fetchFuturesMarket(marketSeed.id, { representation: VERIFIED_TITLE }),
      { refreshInterval: 0, keepPreviousData: true, revalidateOnFocus: false, revalidateOnReconnect: false },
    );
    // The page's own key shape and options (app/futures/[id]/page.tsx).
    const { data: historyData, mutate: refreshHistory } = useSWR(
      market ? keyOf(range) : null,
      () => fetchFuturesHistory(marketSeed.id, HOURS, undefined, undefined, undefined, range ? { range } : undefined),
      { keepPreviousData: true, revalidateOnFocus: false, revalidateOnReconnect: false },
    );
    useFuturesDetailStream({
      marketId: marketSeed.id, market, history: historyData, historyHours: HOURS, historyRange: range,
      setMarket: next => refreshMarket(next, { revalidate: false }),
      setHistory: next => { offered.push({ range, body: next }); return refreshHistory(next, { revalidate: false }); },
      representation: VERIFIED_TITLE,
    });
    return <output data-testid="history">{JSON.stringify(historyData ?? null)}</output>;
  }
  const container = document.createElement('div'); document.body.appendChild(container);
  const root = createRoot(container);
  const cacheBody = (range: Range) => cache.get(unstable_serialize(keyOf(range)))?.data as FuturesHistoryResponse | undefined;
  return {
    reads, consumed, offered, cacheBody,
    shown: () => JSON.parse(container.querySelector('[data-testid="history"]')!.textContent!) as FuturesHistoryResponse | null,
    async mount() {
      await act(async () => { root.render(<SWRConfig value={{ provider: () => cache }}><SWRProvider><Caller /></SWRProvider></SWRConfig>); });
      await until(() => Wire.all.length === 1, 'stream wire');
    },
    async select(range: Range) { await act(async () => { select(range); await delay(5); }); },
    /** A live invalidation frame; `later` moves past the scheduler's 2 s pacing. */
    async invalidate(later = false) {
      if (later) skew += 3_000;
      await act(async () => { Wire.all[Wire.all.length - 1].emit('market', { market_id: marketSeed.id, invalidation: true, terminal: false }); await delay(5); });
    },
    async resolve(route: Route, index: number, value: FuturesHistoryResponse) {
      await until(() => reads[route].length > index, `${route}#${index} dispatched`);
      await act(async () => { reads[route][index].resolve(value); await consumed[route][index].promise; await delay(15); });
    },
    async cleanup() {
      Object.values(reads).flat().forEach(read => read.resolve(body({ second: 0, probability: .1 })));
      await act(async () => { root.unmount(); await delay(10); });
      container.remove(); global.fetch = previousFetch; global.EventSource = previousWire; Date.now = realNow;
      expect(Wire.all.every(wire => wire.readyState === 2)).toBe(true);
    },
  };
}

const timestamps = (history: FuturesHistoryResponse | null | undefined) => history?.outcomes.flatMap(row => row.history.map(point => point.timestamp)) ?? [];

describe('#11186 requested-range identity at every held-history boundary (actual hook, actual SWR)', () => {
  // The selected tail is newer than (or ties, with a different price, against)
  // the fresh full read's tail: exactly what reconciliation keeps from a parent.
  test.each([
    ['older', { second: 5, probability: .5, other: { second: 1, probability: .15 } }],
    ['same_clock_conflict', { second: 3, probability: .5, other: { second: 1, probability: .15 } }],
  ] as const)('1M→All, equal hours, live invalidation during the pending All read (%s 1M tail)', async (_kind, monthTail) => {
    const month = body(monthTail);
    const allFresh = body({ second: 3, probability: .3, other: { second: 4, probability: .4 }, full: true, archive: true });
    const allPage = body({ second: 2, probability: .2, full: true, archive: true });
    const t = rig(undefined, { hours: month });
    try {
      await t.mount();
      await t.resolve('page-hours', 0, month);
      expect(t.shown()).toEqual(month);
      await t.select(FULL_HISTORY_RANGE);
      await until(() => t.reads['page-full'].length === 1, 'All page read pending');
      expect(t.shown()).toEqual(month); // keepPreviousData: the 1M body is on screen while All loads
      await t.invalidate();
      await t.resolve('fresh-full', 0, allFresh);
      // The All key holds the genuine All read — never the 1M row under All's metadata.
      expect(t.cacheBody(FULL_HISTORY_RANGE)).toEqual(allFresh);
      expect(t.shown()).toEqual(allFresh);
      expect(t.offered.every(({ range, body: offer }) => range === FULL_HISTORY_RANGE && offer.history_range?.requested === FULL_HISTORY_RANGE)).toBe(true);
      // Line by line: neither line carries the 1M body's points.
      t.shown()!.outcomes.forEach((row, i) => expect(row).toEqual(allFresh.outcomes[i]));
      // The superseded page read lands afterwards and cannot reinstate anything.
      await t.resolve('page-full', 0, allPage);
      expect(t.cacheBody(FULL_HISTORY_RANGE)).toEqual(allFresh);
      // 1M's own key is untouched.
      expect(t.cacheBody(undefined)).toEqual(month);
    } finally { await t.cleanup(); }
  }, 10000);

  test('All→1M, equal hours: archive rows outside 1M never enter the 1M key', async () => {
    const all = body({ second: 5, probability: .5, other: { second: 1, probability: .15 }, full: true, archive: true });
    const monthFresh = body({ second: 3, probability: .3, other: { second: 4, probability: .4 } });
    const t = rig(FULL_HISTORY_RANGE, { full: all });
    try {
      await t.mount();
      await t.resolve('page-full', 0, all);
      await t.select(undefined);
      await until(() => t.reads['page-hours'].length === 1, '1M page read pending');
      await t.invalidate();
      await t.resolve('fresh-hours', 0, monthFresh);
      expect(t.cacheBody(undefined)).toEqual(monthFresh);
      expect(timestamps(t.shown())).not.toContain(ARCHIVE);
      expect(t.offered.every(({ range }) => range === undefined)).toBe(true);
      expect(t.cacheBody(FULL_HISTORY_RANGE)).toEqual(all);
    } finally { await t.cleanup(); }
  }, 10000);

  // CONTROL (#10745 kept): a genuinely newer same-range parent the server marks
  // full still wins over an older pending fresh full read.
  test('control: a newer known-full All parent survives an older pending All read', async () => {
    const seed = body({ second: 1, probability: .1, full: true, archive: true });
    const parent = body({ second: 4, probability: .6, other: { second: 3, probability: .3 }, full: true, archive: true });
    const older = body({ second: 2, probability: .4, other: { second: 2, probability: .2 }, full: true, archive: true });
    const t = rig(FULL_HISTORY_RANGE, { full: seed });
    try {
      await t.mount();
      await t.invalidate();
      await until(() => t.reads['fresh-full'].length === 1 && t.reads['page-full'].length === 1, 'both reads pending');
      await t.resolve('page-full', 0, parent);
      expect(t.shown()).toEqual(parent);
      await t.resolve('fresh-full', 0, older);
      expect(t.offered).toHaveLength(0);
      expect(t.shown()).toEqual(parent);
    } finally { await t.cleanup(); }
  }, 10000);

  // CONTROL (#10745 kept): a newer incoming same-range observation is accepted.
  test('control: a newer fresh 1M read replaces the older 1M parent', async () => {
    const month = body({ second: 2, probability: .2 });
    const newer = body({ second: 6, probability: .7 });
    const t = rig(undefined, { hours: month });
    try {
      await t.mount();
      await t.resolve('page-hours', 0, month);
      await t.invalidate();
      await t.resolve('fresh-hours', 0, newer);
      expect(t.offered.map(offer => offer.body)).toEqual([newer]);
      expect(t.shown()).toEqual(newer);
    } finally { await t.cleanup(); }
  }, 10000);

  // A server that ignores `range=full` sends no `history_range`. Missing
  // metadata is never proof of a full parent, but the hook's OWN full request
  // is: after All→1M→All the cached All body — here a reconciled MERGE of two
  // of our own full reads, a new object no response ever was — still fences an
  // older full re-read, while an untagged 1M-shaped body never would.
  test('own-request identity: a legacy (no metadata) merged full body stays All\'s parent across a round trip', async () => {
    const month = body({ second: 1, probability: .1 });
    const first = body({ second: 4, probability: .6, other: { second: 3, probability: .3 }, full: true, legacy: true });
    // Buffalo advances, San Francisco regresses: the accepted body is a merge.
    const second = body({ second: 6, probability: .7, other: { second: 2, probability: .2 }, full: true, legacy: true });
    const older = body({ second: 2, probability: .4, other: { second: 2, probability: .2 }, full: true, legacy: true });
    const merged = { ...second, outcomes: [second.outcomes[0], first.outcomes[1]] };
    const t = rig(FULL_HISTORY_RANGE, {});
    try {
      await t.mount();
      await t.invalidate();
      await t.resolve('fresh-full', 0, first);
      expect(t.offered.map(offer => offer.body)).toEqual([first]);
      await t.resolve('page-full', 0, older); // the superseded page read changes nothing
      expect(t.shown()).toEqual(first);
      await t.invalidate(true);
      await t.resolve('fresh-full', 1, second);
      expect(t.shown()).toEqual(merged);
      await t.select(undefined);
      await t.resolve('page-hours', 0, month);
      expect(t.shown()).toEqual(month);
      await t.select(FULL_HISTORY_RANGE);
      expect(t.shown()).toEqual(merged);
      await t.invalidate(true);
      await t.resolve('fresh-full', 2, older);
      expect(t.offered).toHaveLength(2);
      expect(t.shown()).toEqual(merged);
    } finally { await t.cleanup(); }
  }, 10000);

  // A body nobody in this client requested (restored into the cache, never the
  // answer to one of our reads) carrying no metadata is unowned: hours alone
  // cannot tell it from a 1M answer, so the All worker must not adopt it.
  test('unowned: a cached All body without history_range that no request of ours produced is never All\'s parent', async () => {
    const unowned = body({ second: 5, probability: .5, full: true, legacy: true });
    const fresh = body({ second: 3, probability: .3, other: { second: 4, probability: .4 }, full: true, archive: true });
    const t = rig(FULL_HISTORY_RANGE, { full: unowned });
    try {
      await t.mount();
      await until(() => t.reads['page-full'].length === 1, 'page revalidation pending (never answers)');
      await t.invalidate();
      await t.resolve('fresh-full', 0, fresh);
      expect(t.shown()).toEqual(fresh);
    } finally { await t.cleanup(); }
  }, 10000);

  // CONTROL (#10745 on an old server, historyRange.ts's fallback): neither the
  // page read nor the fresh read carries `history_range`. The page's own All
  // request already showed a newer Buffalo observation; an older fresh All read
  // then finishes. The page body is request-owned through the real
  // fetchFuturesHistory boundary, so it parents the read and the newer value
  // stays; the accepted body carries only served metadata, none invented.
  test.each([
    ['page settles before the live frame', false],
    ['page settles while the fresh read is pending', true],
  ] as const)('legacy server: a newer page-accepted All observation survives an older fresh All read (%s)', async (_kind, pendingFirst) => {
    const page = body({ second: 5, probability: .5, full: true, legacy: true });
    // Buffalo is older than the page's; San Francisco is newer: the result is a merge.
    const fresh = body({ second: 3, probability: .3, other: { second: 4, probability: .4 }, full: true, legacy: true });
    const merged = { ...fresh, outcomes: [page.outcomes[0], fresh.outcomes[1]] };
    const t = rig(FULL_HISTORY_RANGE, {});
    try {
      await t.mount();
      if (pendingFirst) {
        await t.invalidate();
        await until(() => t.reads['fresh-full'].length === 1 && t.reads['page-full'].length === 1, 'both reads pending');
        await t.resolve('page-full', 0, page);
      } else {
        await t.resolve('page-full', 0, page);
        expect(t.shown()).toEqual(page);
        await t.invalidate();
      }
      await t.resolve('fresh-full', 0, fresh);
      expect(t.shown()).toEqual(merged);
      expect(t.cacheBody(FULL_HISTORY_RANGE)).toEqual(merged);
      expect(t.shown()!.outcomes[0].history.at(-1)).toEqual(page.outcomes[0].history.at(-1));
      expect(t.offered.map(offer => offer.range)).toEqual([FULL_HISTORY_RANGE]);
      expect(t.shown()).not.toHaveProperty('history_range');
    } finally { await t.cleanup(); }
  }, 10000);

  // CONTROL: a read abandoned by a range switch cannot write either key.
  test('control: a late 1M fresh read completing after the switch to All mutates nothing', async () => {
    const month = body({ second: 1, probability: .1 });
    const late = body({ second: 9, probability: .9 });
    const all = body({ second: 2, probability: .2, full: true, archive: true });
    const t = rig(undefined, { hours: month });
    try {
      await t.mount();
      await t.resolve('page-hours', 0, month);
      await t.invalidate();
      await until(() => t.reads['fresh-hours'].length === 1, '1M fresh read pending');
      await t.select(FULL_HISTORY_RANGE);
      await t.resolve('fresh-hours', 0, late);
      expect(t.offered).toHaveLength(0);
      await t.resolve('page-full', 0, all);
      expect(t.shown()).toEqual(all);
      expect(t.cacheBody(undefined)).toEqual(month);
    } finally { await t.cleanup(); }
  }, 10000);
});

// The stamp is taken at fetchFuturesHistory's resolved boundary and describes
// the request that produced the body; a body that answers something else is
// left unstamped and judged by its own served metadata.
describe('#11186 request provenance at the fetchFuturesHistory boundary', () => {
  const previousFetch = global.fetch;
  afterEach(() => { global.fetch = previousFetch; });
  const serve = (value: FuturesHistoryResponse) => {
    global.fetch = jest.fn(async () => ({ ok: true, status: 200, json: async () => value, headers: { get: (): null => null } })) as unknown as typeof fetch;
  };
  const id = marketSeed.id;

  test('a legacy answer is owned by the range its own request asked for', async () => {
    serve(body({ second: 2, probability: .2, full: true, legacy: true }));
    const all = await fetchFuturesHistory(id, HOURS, undefined, undefined, undefined, { range: FULL_HISTORY_RANGE });
    expect(all).not.toHaveProperty('history_range');
    expect(historyAnswersRequest(all, id, HOURS, FULL_HISTORY_RANGE)).toBe(true);
    expect(historyAnswersRequest(all, id, HOURS, undefined)).toBe(false);
    serve(body({ second: 2, probability: .2 }));
    const month = await fetchFuturesHistory(id, HOURS);
    expect(historyAnswersRequest(month, id, HOURS, undefined)).toBe(true);
    expect(historyAnswersRequest(month, id, HOURS, FULL_HISTORY_RANGE)).toBe(false);
  });

  test('a body whose served block names another range is not stamped as this request\'s', async () => {
    serve(body({ second: 2, probability: .2, full: true, archive: true }));
    const mislabeled = await fetchFuturesHistory(id, HOURS); // asked 1M, served a full answer
    expect(historyAnswersRequest(mislabeled, id, HOURS, undefined)).toBe(false);
    expect(historyAnswersRequest(mislabeled, id, HOURS, FULL_HISTORY_RANGE)).toBe(true);
  });

  test('a body for another market or window is not stamped', async () => {
    serve({ ...body({ second: 2, probability: .2, full: true, legacy: true }), hours: 168 });
    const otherWindow = await fetchFuturesHistory(id, HOURS, undefined, undefined, undefined, { range: FULL_HISTORY_RANGE });
    // Judged by served metadata alone: a metadata-less 168h body answers only 168h without range.
    expect(historyAnswersRequest(otherWindow, id, 168, FULL_HISTORY_RANGE)).toBe(false);
    expect(historyAnswersRequest(otherWindow, id, 168, undefined)).toBe(true);
  });
});
