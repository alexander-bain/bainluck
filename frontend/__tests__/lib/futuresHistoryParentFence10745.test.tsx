/** @jest-environment jsdom */
/** #10745: actual dual-SWR history parent authority reaches the private fence. */
import React from 'react';
import { act } from 'react-dom/test-utils';
import { createRoot } from 'react-dom/client';
import useSWR, { SWRConfig, unstable_serialize } from 'swr';
import SWRProvider from '@/components/SWRProvider';
import { useFuturesDetailStream } from '@/hooks/useFuturesDetailStream';
import { fetchFuturesMarket, fetchFuturesHistory } from '@/lib/api';
import { chartHistoryForSelection, visibleChartOutcomes } from '@/lib/futuresDetailDisplay';
import { VERIFIED_TITLE } from '@/lib/verifiedTitleDetail';
import type { FuturesMarketDetailResponse, FuturesHistoryResponse, FuturesOutcomeHistory } from '@/lib/types';
import canonical from '../fixtures/verifiedTitle10224/detail-kalshi-default.json';

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
const delay = (ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms));
async function until(predicate: () => boolean) {
  const deadline = Date.now() + 2000;
  while (!predicate()) {
    if (Date.now() > deadline) throw new Error('ordinary history control boundary did not arrive');
    await act(async () => { await delay(5); });
  }
}
function deferred<T>() {
  let finish!: (value: T) => void;
  let resolved = false;
  const promise = new Promise<T>(done => { finish = done; });
  return { promise, resolve: (value: T) => { resolved = true; finish(value); }, resolved: () => resolved };
}
const clock = (second: number) => '2030-01-01T00:00:0' + second + 'Z';
const tail = (row: FuturesOutcomeHistory) => row.history[row.history.length - 1];

class Wire {
  static all: Wire[] = [];
  readyState = 1;
  listeners = new Map<string, (event: unknown) => void>();
  constructor(readonly url: string) { Wire.all.push(this); }
  addEventListener(name: string, callback: (event: unknown) => void) { this.listeners.set(name, callback); }
  close() { this.readyState = 2; }
  emit(name: string) { this.listeners.get(name)?.({ data: '{}' }); }
}

test.each(['older_pending', 'reverse_order', 'newer_success', 'other_market_parent', 'other_range_parent', 'final_correction'] as const)(
  'one cached source history, actual dual-SWR/hook chart input: %s', async kind => {
    const marketSeed = JSON.parse(JSON.stringify(canonical)) as FuturesMarketDetailResponse;
    const chosen = marketSeed.outcomes.find(row => row.id === 643833)!;
    expect(marketSeed).toMatchObject({ id: 40533, source: 'kalshi', status: 'open' });
    expect(chosen.probability).not.toBeNull();
    const historyBody = (second: number, probability: number): FuturesHistoryResponse => ({
      market_id: marketSeed.id, market_name: marketSeed.name, hours: 168, actual_hours: 168,
      sparse: true, total_data_points: 2,
      outcomes: [{ outcome_id: chosen.id, name: chosen.name, history: [
        { timestamp: clock(0), probability: .1, american_odds: null, bookmaker: 'consensus' },
        { timestamp: clock(second), probability, american_odds: null, bookmaker: 'consensus' },
      ] }],
    });
    const seed = historyBody(1, .2), parentBody = historyBody(3, .6);
    const freshBody = historyBody(kind === 'newer_success' ? 4 : kind === 'final_correction' ? 3 : 2, kind === 'final_correction' ? 1 : .4);
    const freshMarket = JSON.parse(JSON.stringify(marketSeed)) as FuturesMarketDetailResponse;
    if (kind === 'final_correction') {
      freshMarket.status = 'resolved';
      freshMarket.outcomes.forEach(row => { row.is_winner = row.id === chosen.id; row.probability = row.is_winner ? 1 : 0; });
    }
    if (kind === 'older_pending') { parentBody.actual_hours = 720; parentBody.auto_extended = true; }
    if (kind === 'other_market_parent') parentBody.market_id += 1;
    if (kind === 'other_range_parent') parentBody.hours = 720;
    const parent = deferred<FuturesHistoryResponse>(), fresh = deferred<FuturesHistoryResponse>();
    const freshConsumed = deferred<FuturesHistoryResponse>();
    const marketKey = ['futures-market', marketSeed.id, VERIFIED_TITLE];
    const historyKey = ['futures-history', marketSeed.id, 168];
    // Cached bodies after their previous 5s FETCH records expired. Real initial
    // mount revalidation supplies C; no post-mount parent injection occurs.
    const cache = new Map<string, { data: unknown; _k: unknown }>([
      [unstable_serialize(marketKey), { data: marketSeed, _k: marketKey }],
      [unstable_serialize(historyKey), { data: seed, _k: historyKey }],
    ]);
    const seen: string[] = [], offered: FuturesHistoryResponse[] = [];
    const detailMutations: FuturesMarketDetailResponse[] = [], calls: string[] = [];
    const previousFetch = global.fetch, previousWire = global.EventSource;
    Wire.all = [];
    global.EventSource = Wire as unknown as typeof EventSource;
    global.fetch = jest.fn(async (input: unknown) => {
      const url = String(input); calls.push(url);
      const result = url.includes('/history?')
        ? await (url.includes('fresh=true') ? fresh.promise : parent.promise)
        : url.includes('fresh=true') ? freshMarket : marketSeed;
      return { ok: true, status: 200, json: async () => {
        if (url.includes('/history?') && url.includes('fresh=true')) freshConsumed.resolve(result as FuturesHistoryResponse);
        return result;
      }, headers: { get: () => null } };
    }) as unknown as typeof fetch;
    const selected = new Set([chosen.id]);

    function Caller() {
      const { data: market, mutate: refreshMarket } = useSWR(
        marketKey, () => fetchFuturesMarket(marketSeed.id, { representation: VERIFIED_TITLE }),
        { refreshInterval: 0, keepPreviousData: true, revalidateOnFocus: false, revalidateOnReconnect: false },
      );
      const { data: historyData, mutate: refreshHistory } = useSWR(
        market ? historyKey : null, () => fetchFuturesHistory(marketSeed.id, 168),
        { keepPreviousData: true, revalidateOnFocus: false, revalidateOnReconnect: false },
      );
      useFuturesDetailStream({
        marketId: marketSeed.id, market, history: historyData, historyHours: 168,
        setMarket: next => { detailMutations.push(next); return refreshMarket(next, { revalidate: false }); },
        setHistory: next => { offered.push(next); return refreshHistory(next, { revalidate: false }); },
        representation: VERIFIED_TITLE,
      });
      const pricedIds = new Set((market?.outcomes ?? []).filter(row => row.probability !== null).map(row => row.id));
      // Exact page selection helper and chart displayed-row helper: this is a
      // chart-input DOM witness, not a replacement chart or pixel acceptance.
      const chartRows = visibleChartOutcomes(chartHistoryForSelection(historyData?.outcomes ?? [], selected, pricedIds), selected);
      if (chartRows.length) seen.push(tail(chartRows[0]).timestamp);
      return <><output data-testid="history">{JSON.stringify(historyData)}</output>
        <output data-testid="chart-input">{JSON.stringify(chartRows)}</output></>;
    }
    const container = document.createElement('div'); document.body.appendChild(container);
    const root = createRoot(container);
    const shown = () => JSON.parse(container.querySelector('[data-testid="history"]')!.textContent!) as FuturesHistoryResponse;
    const chartRows = () => JSON.parse(container.querySelector('[data-testid="chart-input"]')!.textContent!) as FuturesOutcomeHistory[];
    const chartTail = () => tail(chartRows()[0]);
    const historyReads = () => calls.filter(url => url.includes('/history?'));
    try {
      await act(async () => {
        root.render(<SWRConfig value={{ provider: () => cache }}><SWRProvider><Caller /></SWRProvider></SWRConfig>);
      });
      await until(() => historyReads().some(url => !url.includes('fresh=true')) && Wire.all.length === 1);
      expect(shown()).toEqual(seed);
      expect(chartRows()).toHaveLength(1);
      expect(chartRows()[0].history.filter(point => point.probability !== null)).toHaveLength(2);
      await act(async () => { Wire.all[0].emit('open'); });
      await until(() => historyReads().some(url => url.includes('fresh=true')) && detailMutations.length === 1);
      expect(detailMutations[0]).toEqual(freshMarket);
      expect(historyReads()).toHaveLength(2);
      if (kind === 'reverse_order') {
        // The real API response body must be consumed and React's queued work
        // flushed even when a stale read correctly causes no setter invocation.
        await act(async () => { fresh.resolve(freshBody); await freshConsumed.promise; await delay(10); });
        expect(freshConsumed.resolved()).toBe(true);
        expect(offered).toHaveLength(1);
        expect(shown()).toEqual(freshBody);
        await act(async () => { parent.resolve(parentBody); await delay(25); });
        expect(shown()).toEqual(freshBody);
        expect(seen.includes(clock(3))).toBe(false);
      } else {
        await act(async () => { parent.resolve(parentBody); await delay(10); });
        await until(() => chartTail().timestamp === clock(3));
        expect(shown()).toEqual(parentBody);
        expect(chartRows()).toHaveLength(1);
        expect(chartRows()[0].history.filter(point => point.probability !== null)).toHaveLength(2);
        expect(chartTail().timestamp).toBe(clock(3));
        // The real API response body must be consumed and React's queued work
        // flushed even when a stale read correctly causes no setter invocation.
        await act(async () => { fresh.resolve(freshBody); await freshConsumed.promise; await delay(10); });
        expect(freshConsumed.resolved()).toBe(true);
        expect(offered).toHaveLength(kind === 'older_pending' ? 0 : 1);
        expect(shown()).toEqual(kind === 'older_pending' ? parentBody : freshBody);
        expect(chartTail().timestamp).toBe(kind === 'older_pending' || kind === 'final_correction' ? clock(3) : kind === 'newer_success' ? clock(4) : clock(2));
      }
      expect(historyReads()).toHaveLength(2);
    } finally {
      parent.resolve(parentBody); fresh.resolve(freshBody);
      await act(async () => {
        if (historyReads().some(url => url.includes('fresh=true'))) await freshConsumed.promise;
        root.unmount(); await delay(10);
      });
      container.remove(); global.fetch = previousFetch; global.EventSource = previousWire;
      const cleanup = { kind, fresh_body_consumed: freshConsumed.resolved(), parent_resolved: parent.resolved(), fresh_resolved: fresh.resolved(), root_unmounted: container.childNodes.length === 0,
        container_removed: !document.body.contains(container), wires_closed: Wire.all.every(wire => wire.readyState === 2),
        fetch_restored: global.fetch === previousFetch, eventsource_restored: global.EventSource === previousWire };
      expect(Object.values(cleanup).filter(value => typeof value === 'boolean').every(Boolean)).toBe(true);
    }
  }, 10000,
);
