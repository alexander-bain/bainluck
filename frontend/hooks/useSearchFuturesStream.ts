'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { fetchDiscoverPriceCards } from '@/lib/api';
import { createPriceDelivery } from '@/lib/discover/priceDelivery';
import type { FeedItem, FuturesMarket } from '@/lib/types';
import {
  adoptSearchPriceCards, patchSearchFutures, searchFuturesStreamable,
  type SearchPriceBook,
} from '@/lib/searchFuturesStream';
import { useMarketStream } from './useMarketStream';

/**
 * #10090: Search's open Kalshi/Polymarket futures cards, re-priced live.
 *
 * The same dispatcher Discover uses (`createPriceDelivery`: one read in flight,
 * 50 ids a batch, a 2 s floor between reads, 429 back-off, a 60 s recovery read)
 * drives `/api/feed/price-cards`; `/api/markets/stream` tells it when to read.
 * Adoption and patching are `lib/searchFuturesStream`'s. Returns `futures`
 * itself until something is adopted.
 */
export function useSearchFuturesStream(futures: FuturesMarket[]): FuturesMarket[] {
  const [book, setBook] = useState<SearchPriceBook>(() => new Map());
  const streamed = useMemo(() => futures.filter(searchFuturesStreamable), [futures]);
  const streamedRef = useRef(streamed);
  streamedRef.current = streamed;
  const futuresRef = useRef(futures);
  futuresRef.current = futures;
  const key = streamed.map((m) => m.id).sort((a, b) => a - b).join(',');

  // A new search answer starts from its own served prices: a leg adopted for the
  // previous answer may be older than the price this one was served with.
  // A read already in flight for the previous answer is dropped on arrival.
  const answer = useRef(0);
  useEffect(() => {
    answer.current += 1;
    setBook((previous) => (previous.size ? new Map() : previous));
  }, [futures]);

  const delivery = useRef<ReturnType<typeof createPriceDelivery> | null>(null);
  useEffect(() => {
    if (!key) return;
    const worker = createPriceDelivery({
      visible: () => streamedRef.current.map((m) => ({ type: 'futures', data: { id: m.id } }) as unknown as FeedItem),
      fetch: (items, signal) => {
        const asked = answer.current;
        return fetchDiscoverPriceCards([], items.map((item) => (item.data as { id: number }).id), signal)
          .then((response) => ({ ...response, asked }));
      },
      accept: (response, requested) => {
        if ((response as { asked?: number }).asked !== answer.current) return;
        const ids = new Set([...requested].map((k) => Number(k.replace('futures-', ''))));
        setBook((previous) => adoptSearchPriceCards(previous, futuresRef.current, response, ids));
      },
      now: () => Date.now(),
      setTimer: (callback, ms) => setTimeout(callback, ms),
      clearTimer: (timer) => clearTimeout(timer),
    });
    delivery.current = worker;
    const sync = () => (document.visibilityState === 'hidden' ? worker.stop() : worker.start());
    sync();
    document.addEventListener('visibilitychange', sync);
    return () => {
      document.removeEventListener('visibilitychange', sync);
      worker.stop();
      if (delivery.current === worker) delivery.current = null;
    };
  }, [key]);

  useMarketStream({
    marketIds: streamed.map((m) => m.id),
    enabled: streamed.length > 0,
    onInvalidate: () => delivery.current?.invalidate(),
  });

  return useMemo(() => {
    if (!book.size) return futures;
    const next = futures.map((m) => patchSearchFutures(m, book));
    return next.every((m, i) => m === futures[i]) ? futures : next;
  }, [futures, book]);
}
