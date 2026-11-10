'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { API_URL, fetchDiscoverPriceCards } from '@/lib/api';
import { createPriceDelivery } from '@/lib/discover/priceDelivery';
import { createLiveStreamController } from '@/lib/liveStreamController';
import type { Event, FeedItem, FuturesMarket } from '@/lib/types';
import {
  adoptSearchPriceCards, patchSearchFutures, searchFuturesStreamable,
  type SearchPriceBook,
} from '@/lib/searchFuturesStream';
import {
  adoptSearchEventCards, patchSearchEvent, searchEventStreamable,
  type SearchEventBook,
} from '@/lib/searchEventsStream';
import { useMarketStream } from './useMarketStream';

/** Fable's decision A (#10090, Nov 8): live game streams per Search answer. */
export const MAX_SEARCH_EVENT_STREAMS = 10;

/**
 * #10090: Search's open Kalshi/Polymarket futures cards and its scheduled and
 * live game cards, re-priced live.
 *
 * One dispatcher (`createPriceDelivery`, Discover's: one read in flight, 50 ids
 * a batch, a 2 s floor between reads, 429 back-off, a 60 s recovery read) reads
 * `/api/feed/price-cards` for both. What tells it to read:
 *
 * * futures — `/api/markets/stream`, one connection per 50 markets;
 * * live games — their `/api/events/{id}/stream`, the first
 *   {@link MAX_SEARCH_EVENT_STREAMS} on the page;
 * * scheduled games — the 60 s recovery read only.
 *
 * Adoption and patching are `lib/searchFuturesStream` and
 * `lib/searchEventsStream`. `futures` may carry one id more than once (a family
 * headline and a flat card); each id is read once and the returned
 * `patchMarket` re-prices each occurrence by its own rows. Pass memoised arrays:
 * a new array is a new search answer and resets both books.
 */
export function useSearchPriceStream(futures: FuturesMarket[], events: Event[]): {
  patchMarket: (market: FuturesMarket) => FuturesMarket;
  patchEvent: (event: Event) => Event;
} {
  const [marketBook, setMarketBook] = useState<SearchPriceBook>(() => new Map());
  const [eventBook, setEventBook] = useState<SearchEventBook>(() => new Map());
  const streamedMarkets = useMemo(() => {
    const seen = new Set<number>();
    return futures.filter((m) => searchFuturesStreamable(m) && !seen.has(m.id) && seen.add(m.id));
  }, [futures]);
  const streamedEvents = useMemo(() => {
    const seen = new Set<number>();
    return events.filter((e) => searchEventStreamable(e) && !seen.has(e.id) && seen.add(e.id));
  }, [events]);
  const visibleRef = useRef<FeedItem[]>([]);
  visibleRef.current = [
    ...streamedMarkets.map((m) => ({ type: 'futures', data: { id: m.id } }) as unknown as FeedItem),
    ...streamedEvents.map((e) => ({ type: 'event', data: { id: e.id } }) as unknown as FeedItem),
  ];
  const futuresRef = useRef(futures);
  futuresRef.current = futures;
  const eventsRef = useRef(events);
  eventsRef.current = events;
  const key = visibleRef.current.map((item) => `${item.type}-${(item.data as { id: number }).id}`).sort().join(',');

  // A new search answer starts from its own served prices: a reading adopted
  // for the previous answer may be older than the one this answer was served
  // with. A read already in flight for the previous answer is dropped on arrival.
  const answer = useRef(0);
  useEffect(() => {
    answer.current += 1;
    setMarketBook((previous) => (previous.size ? new Map() : previous));
    setEventBook((previous) => (previous.size ? new Map() : previous));
  }, [futures, events]);

  const delivery = useRef<ReturnType<typeof createPriceDelivery> | null>(null);
  useEffect(() => {
    if (!key) return;
    const worker = createPriceDelivery({
      visible: () => visibleRef.current,
      fetch: (items, signal) => {
        const asked = answer.current;
        const ids = (type: string) => items.filter((item) => item.type === type).map((item) => (item.data as { id: number }).id);
        return fetchDiscoverPriceCards(ids('event'), ids('futures'), signal).then((response) => ({ ...response, asked }));
      },
      accept: (response, requested) => {
        if ((response as { asked?: number }).asked !== answer.current) return;
        const asked = (prefix: string) => new Set([...requested].filter((k) => k.startsWith(prefix)).map((k) => Number(k.slice(prefix.length))));
        setMarketBook((previous) => adoptSearchPriceCards(previous, futuresRef.current, response, asked('futures-')));
        setEventBook((previous) => adoptSearchEventCards(previous, eventsRef.current, response, asked('event-')));
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
    marketIds: streamedMarkets.map((m) => m.id),
    enabled: streamedMarkets.length > 0,
    onInvalidate: () => delivery.current?.invalidate(),
  });

  // Live games: each frame is a "read now"; the price card, not the frame, is
  // what gets painted, so probability, score and clock arrive from one reading.
  const liveKey = streamedEvents.filter((e) => e.status === 'live').slice(0, MAX_SEARCH_EVENT_STREAMS)
    .map((e) => e.id).join(',');
  useEffect(() => {
    const ids = liveKey ? liveKey.split(',').map(Number) : [];
    if (!ids.length || typeof EventSource === 'undefined') return;
    const invalidate = () => delivery.current?.invalidate();
    let streams: { id: number; retryAt: number | null; controller: ReturnType<typeof createLiveStreamController> }[] = [];
    const open = (id: number) => {
      const controller = createLiveStreamController({
        open: () => {
          const wire = new EventSource(`${API_URL}/api/events/${id}/stream`);
          // Status is opaque to EventSource; stop its private retry on any error.
          wire.addEventListener('error', () => wire.close());
          return wire;
        },
        now: () => Date.now(),
        onFrame: invalidate,
        onDeliveringChange: invalidate,
        onReconcile: invalidate,
      });
      controller.start();
      return { id, retryAt: null as number | null, controller };
    };
    const close = () => { streams.forEach((stream) => stream.controller.stop()); streams = []; };
    const sync = () => { close(); if (document.visibilityState !== 'hidden') streams = ids.map(open); };
    sync();
    const timer = setInterval(() => {
      streams = streams.map((stream) => {
        stream.controller.tick();
        if (stream.controller.state.stopped) {
          if (stream.retryAt === null) stream.retryAt = Date.now() + 60_000;
          if (Date.now() >= stream.retryAt) return open(stream.id);
        }
        return stream;
      });
    }, 5_000);
    document.addEventListener('visibilitychange', sync);
    return () => { clearInterval(timer); document.removeEventListener('visibilitychange', sync); close(); };
  }, [liveKey]);

  const patchMarket = useCallback(
    (market: FuturesMarket) => (marketBook.size ? patchSearchFutures(market, marketBook) : market), [marketBook]);
  const patchEvent = useCallback(
    (event: Event) => (eventBook.size ? patchSearchEvent(event, eventBook) : event), [eventBook]);
  return useMemo(() => ({ patchMarket, patchEvent }), [patchMarket, patchEvent]);
}
