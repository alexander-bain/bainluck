'use client';

import { useEffect, useRef } from 'react';
import { fetchFuturesMarket, fetchFuturesHistory, type ApiError } from '@/lib/api';
import type {
  FuturesMarketDetailResponse, FuturesHistoryResponse, FuturesRepresentation,
} from '@/lib/types';
import { useMarketStream } from './useMarketStream';
import {
  createFuturesDetailReconciler, createFuturesReadScheduler,
  futuresDetailSettled, historyAnswersRequest, reconcileFuturesHistory, stampHistoryRequest,
} from '@/lib/futuresDetailStream';
import type { HistoryRangeRequest } from '@/lib/historyRange';

/** Invalidations re-read real detail and real history; neither the transport nor
 * this hook manufactures chart points, observation times, or a sports LIVE state. */
export function useFuturesDetailStream(options: {
  marketId: number;
  market: FuturesMarketDetailResponse | undefined;
  history: FuturesHistoryResponse | undefined;
  historyHours: number;
  /** #683: the chart's `range=full` read. The re-read asks for the same range,
   *  or a fresh `hours`-only body would replace the whole-history chart. */
  historyRange?: HistoryRangeRequest;
  setMarket: (market: FuturesMarketDetailResponse) => Promise<unknown>;
  setHistory: (history: FuturesHistoryResponse) => Promise<unknown>;
  /** #10224: the representation this page asks for. Absent ⇒ the default
   *  request, unchanged. The chart re-read is `/history` in either mode
   *  (#10244): a verified page draws its source's own consensus history. */
  representation?: FuturesRepresentation;
}): void {
  const callbacks = useRef(options); callbacks.current = options;
  const reconciler = useRef<ReturnType<typeof createFuturesDetailReconciler>>();
  const parentSeed = useRef<FuturesMarketDetailResponse>();
  const history = useRef<FuturesHistoryResponse>();
  const historyParent = useRef<FuturesHistoryResponse>();
  const scheduler = useRef<ReturnType<typeof createFuturesReadScheduler>>();
  const ready = options.market?.id === options.marketId && Array.isArray(options.market?.outcomes);
  const enabled = ready && !!options.market && !futuresDetailSettled(options.market) &&
    ['kalshi', 'polymarket'].includes(options.market.source ?? '');

  // A same-ID SWR revalidation can advance the parent while our read is pending.
  // Adopt through the existing fences; resetting would lose private withdrawals.
  useEffect(() => {
    const parent = options.market;
    if (!ready || !parent) return;
    if (reconciler.current?.current().id !== parent.id) reconciler.current = createFuturesDetailReconciler(parent);
    else if (parentSeed.current !== parent) reconciler.current.adopt(parent);
    parentSeed.current = parent;
  }, [ready, options.market]);

  // Chart history has its own SWR key and can advance independently of detail.
  // #11186: `keepPreviousData` hands us the previous rung's body while the next
  // loads, so a parent must answer the requested RANGE too, not just the hours.
  useEffect(() => {
    const parent = options.history;
    if (!ready || !historyAnswersRequest(parent, options.marketId, options.historyHours, options.historyRange)) return;
    if (historyParent.current !== parent) history.current = reconcileFuturesHistory(history.current, parent, reconciler.current?.current());
    historyParent.current = parent;
  }, [ready, options.history, options.marketId, options.historyHours, options.historyRange]);

  useEffect(() => {
    if (!ready || !callbacks.current.market) return;
    const initial = callbacks.current.market;
    if (reconciler.current?.current().id !== initial.id) reconciler.current = createFuturesDetailReconciler(initial);
    const marketId = options.marketId, hours = options.historyHours, range = options.historyRange;
    history.current = historyAnswersRequest(callbacks.current.history, initial.id, hours, range) ? callbacks.current.history : undefined;
    const worker = createFuturesReadScheduler({
      now: () => Date.now(),
      read: async (signal, current) => {
        // Independent resolution: a slow chart cannot hold back a current hero.
        // One bounded pair consumes the dedicated fresh-market budget (#9526).
        const representation = callbacks.current.representation;
        const detailRead = fetchFuturesMarket(marketId, { fresh: true, signal, representation }).then(async next => {
          if (!current() || callbacks.current.marketId !== marketId || next.id !== marketId) return;
          // Cover a parent render whose passive effect has not run yet. Consume
          // each parent object once, without restarting the worker or its debt.
          const parent = callbacks.current.market;
          if (parent?.id === marketId && Array.isArray(parent.outcomes) && parentSeed.current !== parent) {
            reconciler.current!.adopt(parent);
            parentSeed.current = parent;
          }
          const accepted = reconciler.current!.adopt(next);
          await callbacks.current.setMarket(accepted);
        });
        const historyRead = fetchFuturesHistory(marketId, hours, undefined, undefined, undefined, { fresh: true, signal, range }).then(async next => {
          // Let an authoritative final verdict authorize its final chart value,
          // while the headline itself never waits for history to download.
          await detailRead.catch(() => undefined);
          if (!current() || callbacks.current.marketId !== marketId || callbacks.current.historyHours !== hours || callbacks.current.historyRange !== range || next.market_id !== marketId || next.hours !== hours) return;
          stampHistoryRequest(next, range);
          const parent = callbacks.current.history;
          if (historyAnswersRequest(parent, marketId, hours, range) && historyParent.current !== parent) {
            history.current = reconcileFuturesHistory(history.current, parent, reconciler.current?.current());
            historyParent.current = parent;
          }
          const held = history.current;
          const accepted = reconcileFuturesHistory(held, next, reconciler.current?.current());
          const heldRows = new Set(held?.outcomes);
          // Every incoming series was rejected: retain the canonical parent's
          // whole body and metadata instead of mutating its key with stale data.
          if (held && accepted.outcomes.length > 0 && accepted.outcomes.length === held.outcomes.length &&
            accepted.outcomes.every(row => heldRows.has(row))) return;
          history.current = stampHistoryRequest(accepted, range);
          await callbacks.current.setHistory(accepted);
        });
        const results = await Promise.allSettled([detailRead, historyRead]);
        // Preserve failed final-read debt even while healthy heartbeats continue.
        const errors = results.filter((result): result is PromiseRejectedResult => result.status === 'rejected');
        if (errors.length) {
          const rateError = errors.map(result => result.reason as ApiError).filter(error => error.status === 429)
            .sort((a, b) => (b.retryAfterMs ?? 60_000) - (a.retryAfterMs ?? 60_000))[0];
          throw rateError ?? errors[0].reason;
        }
      },
    });
    scheduler.current = worker;
    const visibility = () => worker.setVisible(document.visibilityState !== 'hidden');
    visibility();
    const timer = setInterval(() => worker.tick(), 250);
    document.addEventListener('visibilitychange', visibility);
    return () => {
      worker.stop(); clearInterval(timer); document.removeEventListener('visibilitychange', visibility);
      if (scheduler.current === worker) scheduler.current = undefined;
    };
  }, [ready, options.marketId, options.historyHours, options.historyRange]);

  useMarketStream({
    marketIds: [options.marketId], enabled,
    onInvalidate: ids => { if (ids.includes(options.marketId)) scheduler.current?.request(); },
  });
}
