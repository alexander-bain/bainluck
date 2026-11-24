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
import { isFinishedStatus } from '@/lib/eventState';
import { createLiveStreamController } from '@/lib/liveStreamController';
import type { EventConceptResponse, FeedItem } from '@/lib/types';
import {
  adoptConceptMatchupCards,
  applyEventConceptLivePrices,
  eventConceptMarketIds,
  eventConceptMatchups,
  type ConceptMatchupBook,
} from '@/lib/eventConceptStream';
import { useMarketStream } from './useMarketStream';

export const MAX_CONCEPT_MATCHUP_STREAMS = 10;
const CONCEPT_REFRESH_FLOOR_MS = 2_000;

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
 * #10090: Live committed + provisional SSE price delivery for
 * `/event/[domain]/[slug]` (matchup `authority-v3` + `/api/markets/stream`
 * invalidations & `market_preview` overlays).
 */
export function useEventConceptPriceStream(
  data: EventConceptResponse | undefined,
  onConceptInvalidate: () => void,
): EventConceptResponse | undefined {
  const [matchupBook, setMatchupBook] = useState<ConceptMatchupBook>(() => new Map());
  const [marketPreviewsState, setMarketPreviewsState] = useState<{
    states: MarketPreviews;
    now: number;
  }>({ states: {}, now: 0 });
  const readers = useRef<Record<number, EventPreviewView>>({});
  const [eventPreviews, setEventPreviews] = useState<EventPreviewsState>({ states: {}, now: 0 });

  const conceptKey = data?.event?.key ?? '';
  const marketIds = useMemo(() => eventConceptMarketIds(data), [data]);
  const marketIdSet = useMemo(() => new Set(marketIds), [marketIds]);
  const matchups = useMemo(() => eventConceptMatchups(data), [data]);

  const visibleRef = useRef<FeedItem[]>([]);
  visibleRef.current = matchups.map(
    (m) => ({ type: 'event', data: { id: m.event_id! } }) as unknown as FeedItem,
  );
  const matchupsRef = useRef(matchups);
  matchupsRef.current = matchups;
  const matchupKey = visibleRef.current
    .map((item) => `event-${(item.data as { id: number }).id}`)
    .sort()
    .join(',');

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

  // Reset books & preview states only when switching concept slug/key.
  const keySeq = useRef(0);
  useEffect(() => {
    keySeq.current += 1;
    readers.current = {};
    setMatchupBook((previous) => (previous.size ? new Map() : previous));
    setEventPreviews((previous) =>
      Object.keys(previous.states).length || previous.now !== 0 ? { states: {}, now: 0 } : previous,
    );
    setMarketPreviewsState((previous) =>
      Object.keys(previous.states).length || previous.now !== 0 ? { states: {}, now: 0 } : previous,
    );
  }, [conceptKey]);

  const onRefreshRef = useRef(onConceptInvalidate);
  onRefreshRef.current = onConceptInvalidate;
  const lastRefreshAt = useRef(0);
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (refreshTimer.current) {
        clearTimeout(refreshTimer.current);
        refreshTimer.current = null;
      }
    },
    [],
  );
  const scheduleConceptRefresh = useCallback(() => {
    const now = Date.now();
    const wait = CONCEPT_REFRESH_FLOOR_MS - (now - lastRefreshAt.current);
    if (wait <= 0) {
      if (refreshTimer.current) {
        clearTimeout(refreshTimer.current);
        refreshTimer.current = null;
      }
      lastRefreshAt.current = now;
      onRefreshRef.current();
      return;
    }
    if (refreshTimer.current) return;
    refreshTimer.current = setTimeout(() => {
      refreshTimer.current = null;
      lastRefreshAt.current = Date.now();
      onRefreshRef.current();
    }, wait);
  }, []);

  const delivery = useRef<ReturnType<typeof createPriceDelivery> | null>(null);
  const invalidateMatchups = useCallback(() => delivery.current?.invalidate(), []);
  useEffect(() => {
    if (!matchupKey) return;
    const worker = createPriceDelivery({
      visible: () => visibleRef.current,
      fetch: (items, signal) => {
        const seq = keySeq.current;
        const ids = items.map((item) => (item.data as { id: number }).id);
        return fetchDiscoverPriceCards(ids, [], signal).then((response) => ({
          ...response,
          seq,
        }));
      },
      accept: (response, requested) => {
        if ((response as { seq?: number }).seq !== keySeq.current) return;
        const asked = new Set(
          [...requested]
            .filter((k) => k.startsWith('event-'))
            .map((k) => Number(k.slice('event-'.length))),
        );
        setMatchupBook((previous) =>
          adoptConceptMatchupCards(previous, matchupsRef.current, response, asked),
        );
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
  }, [matchupKey]);

  const handleMarketInvalidate = useCallback(
    (batch: number[]) => {
      if (batch.some((id) => marketIdSet.has(id))) {
        setMarketPreviewsState((previous) => {
          const states = dropMarketPreviews(previous.states, batch);
          return states === previous.states ? previous : { states, now: performance.now() };
        });
        scheduleConceptRefresh();
      }
    },
    [marketIdSet, scheduleConceptRefresh],
  );

  const evoId = data?.primary?.evolution_market_id ?? null;
  const handleMarketPreview = useCallback(
    (frame: MarketPreviewFrame) => {
      if (evoId !== frame.market_id) return;
      const at = performance.now();
      setMarketPreviewsState((previous) => {
        const states = applyMarketPreview(previous.states, frame, at);
        return states === previous.states ? previous : { states, now: at };
      });
    },
    [evoId],
  );

  const handleMarketPreviewReset = useCallback((ids: number[]) => {
    setMarketPreviewsState((previous) => {
      const states = dropMarketPreviews(previous.states, ids);
      return states === previous.states ? previous : { states, now: performance.now() };
    });
  }, []);

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
    marketIds,
    enabled: marketIds.length > 0 && data?.event?.status !== 'settled',
    onInvalidate: handleMarketInvalidate,
    onPreview: handleMarketPreview,
    onPreviewReset: handleMarketPreviewReset,
  });

  const prioritizedMatchups = useMemo(() => {
    const active = matchups.filter((m) => {
      const held = matchupBook.get(m.event_id!);
      return !held || !isFinishedStatus(held.status);
    });
    const ordered = [
      ...active.filter((m) => m.status === 'live'),
      ...active.filter((m) => m.status !== 'live'),
    ];
    return ordered.slice(0, MAX_CONCEPT_MATCHUP_STREAMS);
  }, [matchups, matchupBook]);

  const revisionEntries = useMemo(
    () =>
      prioritizedMatchups.flatMap((m) => {
        const eid = m.event_id!;
        const rev =
          matchupBook.get(eid)?.revision ??
          (m as { blend_fold_revision?: unknown }).blend_fold_revision ??
          null;
        return rev != null ? [[eid, rev] as [number, unknown]] : [];
      }),
    [prioritizedMatchups, matchupBook],
  );
  const revisionKey = JSON.stringify(revisionEntries);
  useEffect(() => {
    for (const [id, revision] of JSON.parse(revisionKey) as [number, unknown][]) {
      updateEventPreview(id, (view, at) =>
        afterFloor(view, authorityPreviewMembership(view.reader, revision, id), revision, at),
      );
    }
  }, [revisionKey, updateEventPreview]);

  const matchupStreamKey = useMemo(
    () =>
      prioritizedMatchups
        .map((m) => {
          const eid = m.event_id!;
          const rev =
            matchupBook.get(eid)?.revision ??
            (m as { blend_fold_revision?: unknown }).blend_fold_revision ??
            {};
          return `${eid}:${Object.keys(rev).sort().join('.')}`;
        })
        .sort()
        .join(','),
    [prioritizedMatchups, matchupBook],
  );

  useEffect(() => {
    const ids = matchupStreamKey
      ? matchupStreamKey.split(',').map((entry) => parseInt(entry, 10))
      : [];
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
        onDeliveringChange: invalidateMatchups,
        onFrame: (next) => {
          invalidateMatchups();
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
          invalidateMatchups();
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
  }, [matchupStreamKey, invalidateMatchups, updateEventPreview]);

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

  return useMemo(
    () =>
      applyEventConceptLivePrices(
        data,
        matchupBook,
        eventPreviews.states,
        eventPreviews.now,
        marketPreviewsState.states,
        marketPreviewsState.now,
      ),
    [data, matchupBook, eventPreviews, marketPreviewsState],
  );
}
