/** @jest-environment jsdom */
/** #10743: actual ReactDOM/SWR caller retains same-ID parent authority. */
import React from 'react';
import { act } from 'react-dom/test-utils';
import { createRoot } from 'react-dom/client';
import useSWR, { SWRConfig, unstable_serialize } from 'swr';
import SWRProvider from '@/components/SWRProvider';
import { useFuturesDetailStream } from '@/hooks/useFuturesDetailStream';
import { fetchFuturesMarket } from '@/lib/api';
import { VERIFIED_TITLE } from '@/lib/verifiedTitleDetail';
import type { FuturesMarketDetailResponse } from '@/lib/types';
import canonical from '../fixtures/verifiedTitle10224/detail-kalshi-default.json';
import verified from '../fixtures/verifiedTitle10224/detail-kalshi-verified.json';

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const delay = (ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms));
async function until(predicate: () => boolean) {
  const deadline = Date.now() + 2000;
  while (!predicate()) {
    if (Date.now() > deadline) throw new Error('ordinary control boundary did not arrive');
    await act(async () => { await delay(5); });
  }
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}
function body(second: number, firstProbability: number, terminal = false) {
  const value = JSON.parse(JSON.stringify(canonical)) as FuturesMarketDetailResponse;
  value.status = terminal ? 'resolved' : 'open';
  const total = value.outcomes.slice(1).reduce((sum, row) => sum + (row.probability ?? 0), 0);
  value.outcomes.forEach((row, index) => {
    row.last_updated = `2030-01-01T00:00:0${second}Z`;
    row.probability = terminal ? (index === 0 ? 1 : 0)
      : index === 0 ? firstProbability : (row.probability ?? 0) * (1 - firstProbability) / total;
    row.is_winner = terminal ? index === 0 : null;
  });
  return value;
}

class Wire {
  static all: Wire[] = [];
  readyState = 1;
  listeners = new Map<string, (event: unknown) => void>();
  constructor(readonly url: string) { Wire.all.push(this); }
  addEventListener(name: string, callback: (event: unknown) => void) { this.listeners.set(name, callback); }
  close() { this.readyState = 2; }
  emit(name: string) { this.listeners.get(name)?.({ data: '{}' }); }
}

test.each(['terminal_race', 'quote_race', 'reverse_order', 'newer_success', 'verified_move', 'source_fallback'] as const)(
  'one cached market, actual caller/SWR/hook: %s', async kind => {
    const seed = body(1, .2);
    const parentBody = body(3, .6, kind === 'terminal_race' || kind === 'reverse_order');
    const freshBody = body(kind === 'newer_success' ? 4 : 2, .4);
    if (kind === 'verified_move' || kind === 'source_fallback') {
      // A composite's row clocks are not a revision. Preserve whole-body
      // dispatch adoption and transitions to source, without inventing ordering.
      Object.assign(parentBody, JSON.parse(JSON.stringify(verified)));
      if (kind === 'verified_move') {
        Object.assign(freshBody, JSON.parse(JSON.stringify(verified)));
        freshBody.outcomes[0].probability = .135;
        expect(freshBody.outcomes[0].last_updated).toBe(parentBody.outcomes[0].last_updated);
      } else {
        freshBody.outcomes.forEach(row => { row.last_updated = '2020-01-01T00:00:00Z'; });
      }
    }
    const parent = deferred<FuturesMarketDetailResponse>();
    const fresh = deferred<FuturesMarketDetailResponse>();
    const key = ['futures-market', seed.id, VERIFIED_TITLE];
    // A real cached same-key body with no outstanding FETCH record represents
    // a previous visit after its 5-second dedupe request has expired.
    const cache = new Map([[unstable_serialize(key), { data: seed, _k: key }]]);
    const seen: FuturesMarketDetailResponse[] = [];
    const mutations: FuturesMarketDetailResponse[] = [];
    const calls: string[] = [];
    const previousFetch = global.fetch;
    const previousWire = global.EventSource;
    Wire.all = [];
    global.EventSource = Wire as unknown as typeof EventSource;
    global.fetch = jest.fn(async (input: unknown) => {
      const url = String(input); calls.push(url);
      const history = url.includes('/history?');
      const result = history ? {
        market_id: seed.id, market_name: seed.name, hours: 168, outcomes: [],
      } : await (url.includes('fresh=true') ? fresh.promise : parent.promise);
      return { ok: true, status: 200, json: async () => result, headers: { get: () => null } };
    }) as unknown as typeof fetch;

    function Caller() {
      const { data: market, mutate: refreshMarket } = useSWR(
        key, () => fetchFuturesMarket(seed.id, { representation: VERIFIED_TITLE }),
        { refreshInterval: 0, keepPreviousData: true, revalidateOnFocus: false, revalidateOnReconnect: false },
      );
      useFuturesDetailStream({
        marketId: seed.id, market, history: undefined, historyHours: 168,
        setMarket: next => { mutations.push(next); return refreshMarket(next, { revalidate: false }); },
        setHistory: async () => undefined, representation: VERIFIED_TITLE,
      });
      if (market) seen.push(market);
      return <output>{market ? JSON.stringify(market) : 'missing'}</output>;
    }
    const container = document.createElement('div'); document.body.appendChild(container);
    const root = createRoot(container);
    const shown = () => JSON.parse(container.textContent!) as FuturesMarketDetailResponse;
    try {
      // Outer provider isolates test caches only; actual application provider
      // supplies its real cache/config behavior to the exact caller below.
      await act(async () => {
        root.render(<SWRConfig value={{ provider: () => cache }}><SWRProvider><Caller /></SWRProvider></SWRConfig>);
      });
      await until(() => calls.some(url => !url.includes('fresh=true')) && Wire.all.length === 1);
      expect(shown()).toEqual(seed);
      await act(async () => { Wire.all[0].emit('open'); });
      await until(() => calls.some(url => url.includes('fresh=true') && !url.includes('/history?')));
      expect(calls.filter(url => !url.includes('/history?'))).toHaveLength(2);
      if (kind === 'reverse_order') {
        await act(async () => { fresh.resolve(freshBody); await delay(10); });
        await until(() => mutations.length === 1);
        expect(shown()).toEqual(freshBody);
        await act(async () => { parent.resolve(parentBody); await delay(25); });
        expect(shown()).toEqual(freshBody);
        expect(seen.some(value => value.status === 'resolved')).toBe(false);
      } else {
        await act(async () => { parent.resolve(parentBody); await delay(10); });
        await until(() => shown().outcomes[0].last_updated === parentBody.outcomes[0].last_updated);
        expect(shown()).toEqual(parentBody);
        await act(async () => { fresh.resolve(freshBody); await delay(10); });
        await until(() => mutations.length === 1);
        expect(shown()).toEqual(['newer_success', 'verified_move', 'source_fallback'].includes(kind) ? freshBody : parentBody);
      }
    } finally {
      // Resolve retained boundaries so every real API/React/SWR task can end.
      parent.resolve(parentBody); fresh.resolve(freshBody);
      await act(async () => { root.unmount(); await delay(10); });
      container.remove(); global.fetch = previousFetch; global.EventSource = previousWire;
      expect(Wire.all.every(wire => wire.readyState === 2)).toBe(true);
    }
  }, 10000,
);
