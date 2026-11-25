'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { API_URL, fetchDiscoverPriceCards } from '@/lib/api';
import {
  EMPTY_AUTHORITY_PREVIEW,
  authorityPreviewFloor,
  authorityPreviewFrame,
  authorityPreviewHandover,
  authorityPreviewMembership,
  authorityPreviewOpen,
  authorityPreviewReset,
  type AuthorityPreviewReader,
} from '@/lib/authorityPreview';
import type { BlendPreviewState } from '@/lib/blendPreview';
import {
  applyMarketPreview,
  dropMarketPreviews,
  nextMarketPreviewExpiry,
  type MarketPreviewFrame,
  type MarketPreviews,
} from '@/lib/discover/marketPreview';
import { createPriceDelivery } from '@/lib/discover/priceDelivery';
import { createLiveStreamController } from '@/lib/liveStreamController';
import type { Event, FeedItem, FuturesMarket } from '@/lib/types';
import {
  adoptSearchPriceCards,
  overlaySearchMarketPreview,
  patchSearchFutures,
  searchFuturesStreamable,
  type SearchPriceBook,
} from '@/lib/searchFuturesStream';
import {
  adoptSearchEventCards,
  overlaySearchEventPreview,
  patchSearchEvent,
  searchEventStreamable,
  type SearchEventBook,
} from '@/lib/searchEventsStream';
import { useMarketStream } from './useMarketStream';

/** Fable's decision A (#10090, Nov 8): live game streams per Search answer. */
export const MAX_SEARCH_EVENT_STREAMS = 10;

type EventPreviewView = {
  reader: AuthorityPreviewReader;
  handover?: BlendPreviewState | null;
};
type EventPreviewsState = { states: Record<number, BlendPreviewState>; now: number };
const EMPTY_EVENT_VIEW: EventPreviewView = { reader: EMPTY_AUTHORITY_PREVIEW };
const shownEventPreview = (view: EventPreviewView | undefined) =>
  view ? (view.reader.preview.held ?? view.handover ?? null) : null;

function afterFloor(
  previous: EventPreviewView,
  reader: AuthorityPreviewReader,
  raw: unknown,
  at: number,
): EventPreviewView {
  return {
    reader,
    handover: authorityPreviewHandover(previous.reader, reader, raw, previous.handover ?? null, at),
  };
}

/**
 * #10090: Search's open Kalshi/Polymarket futures cards (and family rows) and its
 * scheduled/live game cards, re-priced live with `< 0.5 s` provisional SSE overlays
 * (`authority-v3` for games, `market_preview` for futures) plus `/api/feed/price-cards`
 * reconciliation through the shared `createPriceDelivery` dispatcher.
 */
export function useSearchPriceStream(
  futures: FuturesMarket[],
  events: Event[],
): {
  patchMarket: (market: FuturesMarket) => FuturesMarket;
  patchEvent: (event: Event) => Event;
} {
  const [marketBook, setMarketBook] = useState<SearchPriceBook>(() => new Map());
  const [eventBook, setEventBook] = useState<SearchEventBook>(() => new Map());
  const [marketPreviewsState, setMarketPreviewsState] = useState<{
    states: MarketPreviews;
    now: number;
  }>({ states: {}, now: 0 });

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
  const key = visibleRef.current
    .map((item) => `${item.type}-${(item.data as { id: number }).id}`)
    .sort()
    .join(',');

  const readers = useRef<Record<number, EventPreviewView>>({});
  const [eventPreviews, setEventPreviews] = useState<EventPreviewsState>({ states: {}, now: 0 });
  const updateEventPreview = useCallback(
    (id: number, change: (view: EventPreviewView, at: number) => EventPreviewView | null) => {
      const at = performance.now();
      const before = readers.current[id];
      const view = change(before ?? EMPTY_EVENT_VIEW, at);
      if (view) readers.current[id] = view;
      else delete readers.current[id];
      const shown = shownEventPreview(view ?? undefined);
      if (shown === shownEventPreview(before)) return;
      setEventPreviews((previous) => {
        const states = { ...previous.states };
        if (shown) states[id] = shown;
        else delete states[id];
        return { states, now: at };
      });
    },
    [],
  );

  // A new search answer starts from its own served prices.
  const answer = useRef(0);
  useEffect(() => {
    answer.current += 1;
    readers.current = {};
    setMarketBook((previous) => (previous.size ? new Map() : previous));
    setEventBook((previous) => (previous.size ? new Map() : previous));
    setEventPreviews((previous) =>
      Object.keys(previous.states).length || previous.now !== 0 ? { states: {}, now: 0 } : previous,
    );
    setMarketPreviewsState((previous) =>
      Object.keys(previous.states).length || previous.now !== 0 ? { states: {}, now: 0 } : previous,
    );
  }, [futures, events]);

  const delivery = useRef<ReturnType<typeof createPriceDelivery> | null>(null);
  const invalidate = useCallback(() => delivery.current?.invalidate(), []);
  useEffect(() => {
    if (!key) return;
    const worker = createPriceDelivery({
      visible: () => visibleRef.current,
      fetch: (items, signal) => {
        const asked = answer.current;
        const ids = (type: string) =>
          items.filter((item) => item.type === type).map((item) => (item.data as { id: number }).id);
        return fetchDiscoverPriceCards(ids('event'), ids('futures'), signal).then((response) => ({
          ...response,
          asked,
        }));
      },
      accept: (response, requested) => {
        if ((response as { asked?: number }).asked !== answer.current) return;
        const asked = (prefix: string) =>
          new Set(
            [...requested].filter((k) => k.startsWith(prefix)).map((k) => Number(k.slice(prefix.length))),
          );
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

  const streamedMarketIds = useMemo(() => streamedMarkets.map((m) => m.id), [streamedMarkets]);
  const handleMarketPreview = useCallback((frame: MarketPreviewFrame) => {
    const at = performance.now();
    setMarketPreviewsState((previous) => {
      const states = applyMarketPreview(previous.states, frame, at);
      return states === previous.states ? previous : { states, now: at };
    });
  }, []);
  const handleMarketPreviewReset = useCallback((ids: number[]) => {
    setMarketPreviewsState((previous) => {
      const states = dropMarketPreviews(previous.states, ids);
      return states === previous.states ? previous : { states, now: performance.now() };
    });
  }, []);

  // Market preview state resets alongside [futures, events] in the effect above.

  // Re-render when next market preview expires
  const nextMarketExpiry = nextMarketPreviewExpiry(
    marketPreviewsState.states,
    marketPreviewsState.now,
  );
  useEffect(() => {
    if (!Number.isFinite(nextMarketExpiry)) return;
    const timer = setTimeout(
      () => setMarketPreviewsState((previous) => ({ ...previous, now: performance.now() })),
      Math.max(0, nextMarketExpiry - performance.now()) + 1,
    );
    return () => clearTimeout(timer);
  }, [nextMarketExpiry]);

  useMarketStream({
    marketIds: streamedMarketIds,
    enabled: streamedMarkets.length > 0,
    onInvalidate: invalidate,
    onPreview: handleMarketPreview,
    onPreviewReset: handleMarketPreviewReset,
  });

  // Prioritize live games first, then scheduled games (capped at MAX_SEARCH_EVENT_STREAMS).
  const prioritizedStreamEvents = useMemo(() => {
    const active = streamedEvents.filter((e) => !eventBook.get(e.id)?.final);
    const ordered = [
      ...active.filter((e) => e.status === 'live'),
      ...active.filter((e) => e.status !== 'live'),
    ];
    return ordered.slice(0, MAX_SEARCH_EVENT_STREAMS);
  }, [streamedEvents, eventBook]);

  // Seed/advance authority-v3 reader membership whenever a committed fold revision arrives
  const revisionEntries = useMemo(
    () =>
      prioritizedStreamEvents.flatMap((event) => {
        const rev =
          eventBook.get(event.id)?.revision ??
          (event as Event & { blend_fold_revision?: unknown }).blend_fold_revision ??
          null;
        return rev != null ? [[event.id, rev] as [number, unknown]] : [];
      }),
    [prioritizedStreamEvents, eventBook],
  );
  const revisionKey = JSON.stringify(revisionEntries);
  useEffect(() => {
    for (const [id, revision] of JSON.parse(revisionKey) as [number, unknown][]) {
      updateEventPreview(id, (view, at) =>
        afterFloor(view, authorityPreviewMembership(view.reader, revision, id), revision, at),
      );
    }
  }, [revisionKey, updateEventPreview]);

  const eventStreamKey = useMemo(
    () =>
      prioritizedStreamEvents
        .map((e) => {
          const rev =
            eventBook.get(e.id)?.revision ??
            (e as Event & { blend_fold_revision?: unknown }).blend_fold_revision ??
            {};
          return `${e.id}:${Object.keys(rev).sort().join('.')}`;
        })
        .sort()
        .join(','),
    [prioritizedStreamEvents, eventBook],
  );

  useEffect(() => {
    const ids = eventStreamKey ? eventStreamKey.split(',').map((entry) => parseInt(entry, 10)) : [];
    Object.keys(readers.current)
      .map(Number)
      .filter((id) => !ids.includes(id))
      .forEach((id) => updateEventPreview(id, () => null));
    if (!ids.length || typeof EventSource === 'undefined') return;

    let streams: {
      id: number;
      retryAt: number | null;
      controller: ReturnType<typeof createLiveStreamController>;
    }[] = [];
    const open = (id: number) => {
      const controller = createLiveStreamController({
        open: () => {
          const wire = new EventSource(`${API_URL}/api/events/${id}/stream?preview_protocol=authority-v3`);
          wire.addEventListener('error', () => wire.close());
          return wire;
        },
        now: () => Date.now(),
        onDeliveringChange: invalidate,
        onFrame: (next) => {
          invalidate();
          const promise = next.folded_quote_pending === true && !('folded_quote' in next);
          if (next.event_id === id && next.rev) {
            updateEventPreview(id, (view, at) => {
              const floored = authorityPreviewFloor(view.reader, next.rev);
              const shown = shownEventPreview(view);
              return promise && (next.status === undefined || next.status === shown?.status)
                ? afterFloor(view, floored, next.rev, at)
                : { reader: floored };
            });
          } else if (next.event_id === id && !promise) {
            updateEventPreview(id, (view) => (view.handover ? { reader: view.reader } : view));
          }
        },
        onReconcile: (control) => {
          updateEventPreview(id, (view) => ({
            reader: authorityPreviewFloor(view.reader, control.floor),
          }));
          invalidate();
        },
        previewNow: () => performance.now(),
        onAuthorityPreview: (raw, receivedAt) =>
          updateEventPreview(id, (view, at) => ({
            reader: authorityPreviewFrame(view.reader, raw, id, receivedAt, at),
          })),
        onPreviewFloor: (raw) => {
          try {
            const packet = typeof raw === 'string' ? JSON.parse(raw) : raw;
            if (!packet || packet.event_id !== id) return;
            updateEventPreview(id, (view, at) =>
              afterFloor(view, authorityPreviewFloor(view.reader, packet.floor), packet.floor, at),
            );
          } catch {
            updateEventPreview(id, (view) => ({ reader: authorityPreviewReset(view.reader) }));
          }
        },
        onAuthorityPreviewOpen: (raw) =>
          updateEventPreview(id, (view) => ({
            reader: authorityPreviewOpen(view.reader, raw, id),
          })),
        onPreviewReset: (endSession = true) =>
          updateEventPreview(id, (view) => ({
            reader: authorityPreviewReset(view.reader, endSession),
          })),
      });
      controller.start();
      return { id, retryAt: null as number | null, controller };
    };
    const close = () => {
      streams.forEach((stream) => stream.controller.stop());
      streams = [];
    };
    const sync = () => {
      close();
      if (document.visibilityState !== 'hidden') streams = ids.map(open);
    };
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
    return () => {
      clearInterval(timer);
      document.removeEventListener('visibilitychange', sync);
      close();
    };
  }, [eventStreamKey, invalidate, updateEventPreview]);

  // Re-render when next game preview expires
  const nextEventExpiry = Math.min(
    ...Object.values(eventPreviews.states)
      .map((state) => state.expiresAt)
      .filter((at) => at > eventPreviews.now),
  );
  useEffect(() => {
    if (!Number.isFinite(nextEventExpiry)) return;
    const timer = setTimeout(
      () => setEventPreviews((previous) => ({ ...previous, now: performance.now() })),
      Math.max(0, nextEventExpiry - performance.now()) + 1,
    );
    return () => clearTimeout(timer);
  }, [nextEventExpiry]);

  const patchMarket = useCallback(
    (market: FuturesMarket) => {
      const committed = marketBook.size ? patchSearchFutures(market, marketBook) : market;
      return overlaySearchMarketPreview(
        committed,
        marketPreviewsState.states,
        marketPreviewsState.now,
        marketBook,
      );
    },
    [marketBook, marketPreviewsState],
  );

  const patchEvent = useCallback(
    (event: Event) => {
      const committed = eventBook.size ? patchSearchEvent(event, eventBook) : event;
      return overlaySearchEventPreview(
        committed,
        eventPreviews.states[event.id],
        eventPreviews.now,
        eventBook.get(event.id) ?? null,
      );
    },
    [eventBook, eventPreviews],
  );

  return useMemo(() => ({ patchMarket, patchEvent }), [patchMarket, patchEvent]);
}
