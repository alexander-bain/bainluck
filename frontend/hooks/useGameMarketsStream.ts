'use client';

import { useEffect, useRef, useState } from 'react';
import { useMarketStream } from './useMarketStream';
import { createFuturesReadScheduler } from '@/lib/futuresDetailStream';
import { createGameMarketsReconciler, fetchFreshGameMarkets, type LiveGameMarkets } from '@/lib/gameMarketsStream';

/** #10285: the reconciler each game page last adopted with. Back to a game page used to render the
 * props and Additional Markets empty until a ~3s fresh read landed, while SWR served every other
 * section from its cache — so the browser restored the scroll against a page 1,125px short and the
 * reader landed far below the card they tapped. The remounted page renders the held reconciler's
 * body in its first frame and reconciles the fresh read with the SAME reconciler, so its revision
 * watermarks and withdrawal fences survive Back: a body alone cannot carry them (a null-clock
 * withdrawal leaves no clock to seed a new one from, and the unchanged quote it withdrew came back).
 * Plain data, a few games, most recently adopted last. */
type Reconciler = ReturnType<typeof createGameMarketsReconciler>;
const heldReconcilers = new Map<string, Reconciler>();
const HELD_GAMES = 8;

function hold(key: string, reconcile: Reconciler) {
  heldReconcilers.delete(key);
  heldReconcilers.set(key, reconcile);
  if (heldReconcilers.size > HELD_GAMES) heldReconcilers.delete(heldReconcilers.keys().next().value!);
}

/** The same held context serves scheduled, live and final contracts. */
export function useGameMarketsStream(eventId: number, canonicalId: number) {
  const key = `${eventId}:${canonicalId}`;
  const [state, setState] = useState<{ key: string; body: LiveGameMarkets }>();
  const scheduler = useRef<ReturnType<typeof createFuturesReadScheduler>>();
  useEffect(() => {
    if (!Number.isSafeInteger(eventId) || eventId <= 0) return;
    const reconcile = heldReconcilers.get(key) ?? createGameMarketsReconciler();
    const worker = createFuturesReadScheduler({ now: () => Date.now(), read: async (signal, current) => {
      const next = await fetchFreshGameMarkets(eventId, signal);
      if (!current()) return;
      if (next.event_id !== canonicalId || !Array.isArray(next.totals) || !Array.isArray(next.player_props)) {
        throw new Error('Game markets identity or payload mismatch');
      }
      const body = reconcile.adopt(next);
      if (body && current()) { hold(key, reconcile); setState({ key, body }); }
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
  const body = state?.key === key ? state.body : heldReconcilers.get(key)?.current();
  useMarketStream({ marketIds: body?.stream_market_ids ?? [], enabled: !!body,
    onInvalidate: () => scheduler.current?.request() });
  return { data: body };
}
