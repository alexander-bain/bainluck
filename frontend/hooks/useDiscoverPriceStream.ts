'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { DiscoverGroupedItem } from '@/components/discover/types';
import type { FeedEventData, FeedFuturesData } from '@/lib/types';
import { API_URL, fetchDiscoverPriceCards } from '@/lib/api';
import { createLiveStreamController } from '@/lib/liveStreamController';
import { createPriceDelivery } from '@/lib/discover/priceDelivery';
import {
  adoptPriceCards, groupedLeaves, marketResolved, priceKey, projectPriceGroups,
  reconcilePriceBook, type PriceBook,
} from '@/lib/discover/priceRefresh';
import { useMarketStream } from './useMarketStream';

/** Price bodies are projected AFTER editorial ranking/filtering/grouping. */
export function useDiscoverPriceStream(groups: DiscoverGroupedItem[], principal: string) {
  const [stored, setStored] = useState<{ principal: string; book: PriceBook }>(() => ({ principal, book: new Map() }));
  const [owners, setOwners] = useState<Record<string, string[]>>({});
  let book = stored.principal === principal ? stored.book : new Map();
  book = reconcilePriceBook(groups, book);
  // Derive before rendering children, so even a t1 -> newer t3 -> cached t2
  // feed sequence cannot briefly paint t2 or forget its accepted fence.
  if (stored.principal !== principal || book !== stored.book) setStored({ principal, book });
  const projected = projectPriceGroups(groups, book);
  const visibleKeys = useMemo(() => new Set(Object.values(owners).flat()), [owners]);
  const leaves = groupedLeaves(projected).filter(item => visibleKeys.has(priceKey(item)!));
  const leavesRef = useRef(leaves);
  leavesRef.current = leaves;
  const groupsRef = useRef(projected);
  groupsRef.current = projected;
  const dispatcher = useRef<ReturnType<typeof createPriceDelivery> | null>(null);
  const invalidate = useCallback(() => dispatcher.current?.invalidate(), []);
  const setPriceVisibility = useCallback((owner: string, keys: string[], visible: boolean) => {
    setOwners(previous => {
      if (!visible && !(owner in previous)) return previous;
      if (visible && previous[owner]?.join('|') === keys.join('|')) return previous;
      const next = { ...previous };
      if (visible) next[owner] = keys; else delete next[owner];
      return next;
    });
  }, []);

  useEffect(() => {
    const delivery = createPriceDelivery({
      visible: () => leavesRef.current,
      fetch: (items, signal) => fetchDiscoverPriceCards(
        items.filter(item => item.type === 'event').map(item => (item.data as FeedEventData).id),
        items.filter(item => item.type === 'futures').map(item => (item.data as FeedFuturesData).id), signal,
      ),
      accept: (response, requested) => setStored(previous => {
        if (previous.principal !== principal) return previous;
        const next = adoptPriceCards(previous.book, groupedLeaves(groupsRef.current), response, requested);
        return next === previous.book ? previous : { principal, book: next };
      }),
      now: () => Date.now(), setTimer: (callback, ms) => setTimeout(callback, ms), clearTimer: timer => clearTimeout(timer),
    });
    dispatcher.current = delivery;
    const sync = () => document.visibilityState === 'hidden' ? delivery.stop() : delivery.start();
    sync();
    document.addEventListener('visibilitychange', sync);
    return () => {
      document.removeEventListener('visibilitychange', sync);
      delivery.stop();
      if (dispatcher.current === delivery) dispatcher.current = null;
    };
  }, [principal]);

  const visibleSignature = leaves.map(priceKey).sort().join(',');
  useEffect(() => { invalidate(); }, [visibleSignature, invalidate, principal]);
  useMarketStream({
    marketIds: leaves.filter(item => item.type === 'futures' && !marketResolved(item.data as FeedFuturesData))
      .map(item => (item.data as FeedFuturesData).id),
    enabled: true, onInvalidate: invalidate,
  });

  const eventKey = leaves.filter(item => item.type === 'event' && ['live', 'scheduled', 'suspended'].includes((item.data as FeedEventData).status))
    .map(item => (item.data as FeedEventData).id).sort((a, b) => a - b).join(',');
  useEffect(() => {
    if (!eventKey || typeof EventSource === 'undefined') return;
    const ids = eventKey.split(',').map(Number);
    let streams: { id: number; retryAt: number | null; controller: ReturnType<typeof createLiveStreamController> }[] = [];
    const open = (id: number) => {
      const controller = createLiveStreamController({
        open: () => {
          const wire = new EventSource(`${API_URL}/api/events/${id}/stream`);
          // Status is opaque to EventSource; stop its private retry on any error.
          wire.addEventListener('error', () => wire.close());
          return wire;
        },
        now: () => Date.now(), onFrame: invalidate, onDeliveringChange: invalidate,
      });
      controller.start();
      return { id, retryAt: null as number | null, controller };
    };
    const close = () => { streams.forEach(stream => stream.controller.stop()); streams = []; };
    const sync = () => { close(); if (document.visibilityState !== 'hidden') streams = ids.map(open); };
    sync();
    const timer = setInterval(() => {
      streams = streams.map(stream => {
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
  }, [eventKey, invalidate, principal]);

  return { items: projected, setPriceVisibility };
}
