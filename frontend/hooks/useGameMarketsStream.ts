'use client';

import { useEffect, useRef, useState } from 'react';
import { useMarketStream } from './useMarketStream';
import { createFuturesReadScheduler } from '@/lib/futuresDetailStream';
import { createGameMarketsReconciler, fetchFreshGameMarkets, type LiveGameMarkets } from '@/lib/gameMarketsStream';

/** The same held context serves scheduled, live and final contracts. */
export function useGameMarketsStream(eventId: number, canonicalId: number) {
  const key = `${eventId}:${canonicalId}`;
  const [state, setState] = useState<{ key: string; body: LiveGameMarkets }>();
  const scheduler = useRef<ReturnType<typeof createFuturesReadScheduler>>();
  useEffect(() => {
    if (!Number.isSafeInteger(eventId) || eventId <= 0) return;
    const reconcile = createGameMarketsReconciler();
    const worker = createFuturesReadScheduler({ now: () => Date.now(), read: async (signal, current) => {
      const next = await fetchFreshGameMarkets(eventId, signal);
      if (!current()) return;
      if (next.event_id !== canonicalId || !Array.isArray(next.totals) || !Array.isArray(next.player_props)) {
        throw new Error('Game markets identity or payload mismatch');
      }
      const body = reconcile.adopt(next);
      if (body && current()) setState({ key, body });
    } });
    scheduler.current = worker;
    const visibility = () => worker.setVisible(document.visibilityState !== 'hidden');
    visibility();
    worker.request();
    const timer = setInterval(() => worker.tick(), 250);
    document.addEventListener('visibilitychange', visibility);
    return () => {
      worker.stop(); clearInterval(timer); document.removeEventListener('visibilitychange', visibility);
      if (scheduler.current === worker) scheduler.current = undefined;
    };
  }, [eventId, canonicalId, key]);
  const body = state?.key === key ? state.body : undefined;
  useMarketStream({ marketIds: body?.stream_market_ids ?? [], enabled: !!body,
    onInvalidate: () => scheduler.current?.request() });
  return { data: body };
}
