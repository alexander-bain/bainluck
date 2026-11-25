'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  API_URL,
  fetchDiscoverPriceCards,
  type LeagueFuturesResponse,
  type LeagueGameBrief,
  type LeagueMarket,
} from '@/lib/api';
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
import type { FeedItem } from '@/lib/types';
import {
  adoptLeagueGameCards,
  adoptLeagueMarketCards,
  leagueGameStreamable,
  leagueMarketStreamable,
  leagueSectionMarkets,
  overlayLeagueGamePreview,
  overlayLeagueMarketPreview,
  patchLeagueGameFromBook,
  patchLeagueMarketFromBook,
  type LeagueGameBook,
  type LeagueMarketBook,
} from '@/lib/leaguePriceStream';
import { useMarketStream } from './useMarketStream';

export const MAX_LEAGUE_EVENT_STREAMS = 10;

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
 * #10090: Live committed + provisional SSE prices (`authority-v3` for games,
 * `market_preview` for futures/binaries) for `/sport/[sport]/[league]`.
 */
export function useLeaguePriceStream(
  leagueMarkets: LeagueFuturesResponse | null,
): {
  upcomingGames: LeagueGameBrief[];
  sections: Record<string, LeagueMarket[]>;
} {
  const [marketBook, setMarketBook] = useState<LeagueMarketBook>(() => new Map());
  const [gameBook, setGameBook] = useState<LeagueGameBook>(() => new Map());
  const [marketPreviewsState, setMarketPreviewsState] = useState<{
    states: MarketPreviews;
    now: number;
  }>({ states: {}, now: 0 });
  const readers = useRef<Record<number, EventPreviewView>>({});
  const [eventPreviews, setEventPreviews] = useState<EventPreviewsState>({ states: {}, now: 0 });

  const baseGames = useMemo(
    () => leagueMarkets?.upcoming_games ?? [],
    [leagueMarkets],
  );
  const baseSections = useMemo(
    () => leagueMarkets?.sections ?? {},
    [leagueMarkets],
  );
  const sectionMarkets = useMemo(
    () => leagueSectionMarkets(leagueMarkets?.sections).filter(leagueMarketStreamable),
    [leagueMarkets],
  );

  const streamedGames = useMemo(() => {
    const seen = new Set<number>();
    return baseGames.filter((g) => leagueGameStreamable(g) && !seen.has(g.id) && seen.add(g.id));
  }, [baseGames]);

  const visibleRef = useRef<FeedItem[]>([]);
  visibleRef.current = [
    ...sectionMarkets.map((m) => ({ type: 'futures', data: { id: m.id } }) as unknown as FeedItem),
    ...streamedGames.map((g) => ({ type: 'event', data: { id: g.id } }) as unknown as FeedItem),
  ];
  const gamesRef = useRef(baseGames);
  gamesRef.current = baseGames;
  const marketsRef = useRef(sectionMarkets);
  marketsRef.current = sectionMarkets;

  const deliveryKey = visibleRef.current
    .map((item) => `${item.type}-${(item.data as { id: number }).id}`)
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

  // Reset only when a new leagueMarkets envelope arrives (never when grid invalidation refreshes grid).
  const envelopeSeq = useRef(0);
  useEffect(() => {
    envelopeSeq.current += 1;
    readers.current = {};
    setMarketBook((previous) => (previous.size ? new Map() : previous));
    setGameBook((previous) => (previous.size ? new Map() : previous));
    setEventPreviews((previous) =>
      Object.keys(previous.states).length || previous.now !== 0 ? { states: {}, now: 0 } : previous,
    );
    setMarketPreviewsState((previous) =>
      Object.keys(previous.states).length || previous.now !== 0 ? { states: {}, now: 0 } : previous,
    );
  }, [leagueMarkets]);

  const delivery = useRef<ReturnType<typeof createPriceDelivery> | null>(null);
  const invalidateCards = useCallback(() => delivery.current?.invalidate(), []);
  useEffect(() => {
    if (!deliveryKey) return;
    const worker = createPriceDelivery({
      visible: () => visibleRef.current,
      fetch: (items, signal) => {
        const seq = envelopeSeq.current;
        const ids = (type: string) =>
          items.filter((i) => i.type === type).map((i) => (i.data as { id: number }).id);
        return fetchDiscoverPriceCards(ids('event'), ids('futures'), signal).then((response) => ({
          ...response,
          seq,
        }));
      },
      accept: (response, requested) => {
        if ((response as { seq?: number }).seq !== envelopeSeq.current) return;
        const asked = (prefix: string) =>
          new Set(
            [...requested].filter((k) => k.startsWith(prefix)).map((k) => Number(k.slice(prefix.length))),
          );
        setMarketBook((previous) =>
          adoptLeagueMarketCards(previous, marketsRef.current, response, asked('futures-')),
        );
        setGameBook((previous) =>
          adoptLeagueGameCards(previous, gamesRef.current, response, asked('event-')),
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
  }, [deliveryKey]);

  const streamedMarketIds = useMemo(() => sectionMarkets.map((m) => m.id), [sectionMarkets]);

  const sectionMarketIdSet = useMemo(() => new Set(sectionMarkets.map((m) => m.id)), [sectionMarkets]);
  const handleMarketInvalidate = useCallback(
    (batch: number[]) => {
      if (batch.some((id) => sectionMarketIdSet.has(id))) invalidateCards();
    },
    [sectionMarketIdSet, invalidateCards],
  );

  const handleMarketPreview = useCallback((frame: MarketPreviewFrame) => {
    if (!sectionMarketIdSet.has(frame.market_id)) return;
    const at = performance.now();
    setMarketPreviewsState((previous) => {
      const states = applyMarketPreview(previous.states, frame, at);
      return states === previous.states ? previous : { states, now: at };
    });
  }, [sectionMarketIdSet]);

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
    marketIds: streamedMarketIds,
    enabled: streamedMarketIds.length > 0,
    onInvalidate: handleMarketInvalidate,
    onPreview: handleMarketPreview,
    onPreviewReset: handleMarketPreviewReset,
  });

  // Prioritize live games first, then scheduled games, capped at MAX_LEAGUE_EVENT_STREAMS.
  const prioritizedGames = useMemo(() => {
    const active = streamedGames.filter((g) => !gameBook.get(g.id)?.final);
    const ordered = [
      ...active.filter((g) => g.status === 'live'),
      ...active.filter((g) => g.status !== 'live'),
    ];
    return ordered.slice(0, MAX_LEAGUE_EVENT_STREAMS);
  }, [streamedGames, gameBook]);

  const revisionEntries = useMemo(
    () =>
      prioritizedGames.flatMap((game) => {
        const rev =
          gameBook.get(game.id)?.revision ??
          (game as LeagueGameBrief & { blend_fold_revision?: unknown }).blend_fold_revision ??
          null;
        return rev != null ? [[game.id, rev] as [number, unknown]] : [];
      }),
    [prioritizedGames, gameBook],
  );
  const revisionKey = JSON.stringify(revisionEntries);
  useEffect(() => {
    for (const [id, revision] of JSON.parse(revisionKey) as [number, unknown][]) {
      updateEventPreview(id, (view, at) =>
        afterFloor(view, authorityPreviewMembership(view.reader, revision, id), revision, at),
      );
    }
  }, [revisionKey, updateEventPreview]);

  const gameStreamKey = useMemo(
    () =>
      prioritizedGames
        .map((g) => {
          const rev =
            gameBook.get(g.id)?.revision ??
            (g as LeagueGameBrief & { blend_fold_revision?: unknown }).blend_fold_revision ??
            {};
          return `${g.id}:${Object.keys(rev).sort().join('.')}`;
        })
        .sort()
        .join(','),
    [prioritizedGames, gameBook],
  );

  useEffect(() => {
    const ids = gameStreamKey ? gameStreamKey.split(',').map((entry) => parseInt(entry, 10)) : [];
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
        onDeliveringChange: invalidateCards,
        onFrame: (next) => {
          invalidateCards();
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
          invalidateCards();
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
  }, [gameStreamKey, invalidateCards, updateEventPreview]);

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

  const upcomingGames = useMemo(
    () =>
      baseGames.map((game) => {
        const committed = gameBook.size ? patchLeagueGameFromBook(game, gameBook) : game;
        return overlayLeagueGamePreview(
          committed,
          eventPreviews.states[game.id],
          eventPreviews.now,
          gameBook.get(game.id) ?? null,
        );
      }),
    [baseGames, gameBook, eventPreviews],
  );

  const sections = useMemo(() => {
    const out: Record<string, LeagueMarket[]> = {};
    for (const [sectionKey, markets] of Object.entries(baseSections)) {
      out[sectionKey] = markets.map((market) => {
        const committed = marketBook.size ? patchLeagueMarketFromBook(market, marketBook) : market;
        return overlayLeagueMarketPreview(
          committed,
          marketPreviewsState.states,
          marketPreviewsState.now,
          marketBook,
        );
      });
    }
    return out;
  }, [baseSections, marketBook, marketPreviewsState]);

  return useMemo(() => ({ upcomingGames, sections }), [upcomingGames, sections]);
}
