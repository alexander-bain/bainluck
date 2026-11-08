'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
 * Adoption and patching are `lib/searchFuturesStream`'s.
 *
 * `futures` is every market the page draws, families included; an id may
 * appear more than once (a family's headline can carry different rows than the
 * flat card). The stream subscribes each id once, and the returned `patch`
 * re-prices each OCCURRENCE by its own rows. `patch` returns its argument
 * itself until something is adopted for that market. Pass a memoised array:
 * a new array is a new search answer and resets the book.
 */
export function useSearchFuturesStream(futures: FuturesMarket[]): (market: FuturesMarket) => FuturesMarket {
  const [book, setBook] = useState<SearchPriceBook>(() => new Map());
  const streamed = useMemo(() => {
    const seen = new Set<number>();
    return futures.filter((m) => searchFuturesStreamable(m) && !seen.has(m.id) && seen.add(m.id));
  }, [futures]);
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

  return useCallback((market: FuturesMarket) => (book.size ? patchSearchFutures(market, book) : market), [book]);
}
