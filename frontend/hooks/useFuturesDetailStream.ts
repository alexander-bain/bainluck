'use client';

import { useEffect, useRef } from 'react';
import { fetchFuturesMarket, fetchFuturesHistory, type ApiError } from '@/lib/api';
import type { FuturesMarketDetailResponse, FuturesHistoryResponse } from '@/lib/types';
import { useMarketStream } from './useMarketStream';
import {
  createFuturesDetailReconciler, createFuturesReadScheduler,
  futuresDetailSettled, reconcileFuturesHistory,
} from '@/lib/futuresDetailStream';

/** Invalidations re-read real detail and real history; neither the transport nor
 * this hook manufactures chart points, observation times, or a sports LIVE state. */
export function useFuturesDetailStream(options: {
  marketId: number;
  market: FuturesMarketDetailResponse | undefined;
  history: FuturesHistoryResponse | undefined;
  historyHours: number;
  setMarket: (market: FuturesMarketDetailResponse) => Promise<unknown>;
  setHistory: (history: FuturesHistoryResponse) => Promise<unknown>;
}): void {
  const callbacks = useRef(options); callbacks.current = options;
  const reconciler = useRef<ReturnType<typeof createFuturesDetailReconciler>>();
  const history = useRef<FuturesHistoryResponse>();
  const scheduler = useRef<ReturnType<typeof createFuturesReadScheduler>>();
  const ready = options.market?.id === options.marketId && Array.isArray(options.market?.outcomes);
  const enabled = ready && !!options.market && !futuresDetailSettled(options.market) &&
    ['kalshi', 'polymarket'].includes(options.market.source ?? '');

  useEffect(() => {
    if (!ready || !callbacks.current.market) return;
    const initial = callbacks.current.market;
    if (reconciler.current?.current().id !== initial.id) reconciler.current = createFuturesDetailReconciler(initial);
    history.current = callbacks.current.history?.market_id === initial.id ? callbacks.current.history : undefined;
    const marketId = options.marketId, hours = options.historyHours;
    const worker = createFuturesReadScheduler({
      now: () => Date.now(),
      read: async (signal, current) => {
        // Independent resolution: a slow chart cannot hold back a current hero.
        // One bounded pair consumes the dedicated fresh-market budget (#9526).
        const detailRead = fetchFuturesMarket(marketId, { fresh: true, signal }).then(async next => {
          if (!current() || callbacks.current.marketId !== marketId || next.id !== marketId) return;
          const accepted = reconciler.current!.adopt(next);
          await callbacks.current.setMarket(accepted);
        });
        const historyRead = fetchFuturesHistory(marketId, hours, undefined, undefined, undefined, { fresh: true, signal }).then(async next => {
          // Let an authoritative final verdict authorize its final chart value,
          // while the headline itself never waits for history to download.
          await detailRead.catch(() => undefined);
          if (!current() || callbacks.current.marketId !== marketId || callbacks.current.historyHours !== hours || next.market_id !== marketId) return;
          history.current = reconcileFuturesHistory(history.current, next, reconciler.current?.current());
          await callbacks.current.setHistory(history.current);
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
  }, [ready, options.marketId, options.historyHours]);

  useMarketStream({
    marketIds: [options.marketId], enabled,
    onInvalidate: ids => { if (ids.includes(options.marketId)) scheduler.current?.request(); },
  });
}
