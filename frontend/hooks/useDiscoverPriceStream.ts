'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { DiscoverGroupedItem } from '@/components/discover/types';
import type { FeedBundleData, FeedEventData, FeedFuturesData, FeedItem } from '@/lib/types';
import { API_URL, fetchDiscoverPriceCards } from '@/lib/api';
import { createLiveStreamController } from '@/lib/liveStreamController';
import { createPriceDelivery } from '@/lib/discover/priceDelivery';
import {
  adoptPriceCards, groupedLeaves, marketResolved, priceKey, projectPriceGroups,
  reconcilePriceBook, type PriceBook,
} from '@/lib/discover/priceRefresh';
import {
  EMPTY_AUTHORITY_PREVIEW, authorityPreviewFloor, authorityPreviewFrame, authorityPreviewHandover,
  authorityPreviewMembership, authorityPreviewOpen, authorityPreviewReset, type AuthorityPreviewReader,
} from '@/lib/authorityPreview';
import { overlayBlendPreview, type BlendPreviewState } from '@/lib/blendPreview';
import { parseFoldRevision } from '@/lib/foldRevision';
import { useMarketStream } from './useMarketStream';

/**
 * #10090: one event card's v3 preview reader, wired exactly as the event page
 * wires it (`useLiveEventStream`), and the folded preview a commit floor hands
 * over (`authorityPreviewHandover`). Never written into the price book.
 */
type PreviewView = { reader: AuthorityPreviewReader; handover?: BlendPreviewState | null };
/** The previews on screen, per event, and the monotonic time they are judged at. */
type Previews = { states: Record<number, BlendPreviewState>; now: number };
const EMPTY_VIEW: PreviewView = { reader: EMPTY_AUTHORITY_PREVIEW };
const shownPreview = (view: PreviewView | undefined) => view ? view.reader.preview.held ?? view.handover ?? null : null;

function afterFloor(previous: PreviewView, reader: AuthorityPreviewReader, raw: unknown, at: number): PreviewView {
  return { reader, handover: authorityPreviewHandover(previous.reader, reader, raw, previous.handover ?? null, at) };
}

/**
 * #10090: the card's number with its event's admitted preview overlaid — the
 * same `displayedPreview` gate as the event page hero (blend hero, same status,
 * no newer committed revision, unexpired). The card prints `current_odds`, so
 * the overlay lands there; the served whole percents describe the committed
 * value, so they are dropped and the card's own rounding rule decides.
 * Returns `groups` itself when nothing is overlaid.
 */
function overlayPreviews(groups: DiscoverGroupedItem[], previews: Previews): DiscoverGroupedItem[] {
  let changed = false;
  const project = (item: FeedItem): FeedItem => {
    if (item.type === 'bundle') {
      const bundle = item.data as FeedBundleData;
      const items = bundle.items.map(project);
      return items.every((leaf, i) => leaf === bundle.items[i]) ? item : { ...item, data: { ...bundle, items } };
    }
    if (item.type !== 'event') return item;
    const data = item.data as FeedEventData;
    const state = previews.states[data.id];
    if (!state || !data.current_odds) return item;
    const overlaid = overlayBlendPreview(data as Parameters<typeof overlayBlendPreview>[0], state, previews.now);
    if (overlaid === data) return item;
    changed = true;
    const p = state.p;
    return { ...item, data: { ...data, current_odds: { ...data.current_odds, home_probability: p, away_probability: 1 - p,
      home_rendered_percent: null, away_rendered_percent: null } } };
  };
  const next = groups.map(group => group.type === 'single' ? { ...group, item: group.item && project(group.item) }
    : { ...group, items: group.items?.map(project) });
  return changed ? next : groups;
}

/** Price bodies are projected AFTER editorial ranking/filtering/grouping. */
export function useDiscoverPriceStream(groups: DiscoverGroupedItem[], principal: string) {
  const [stored, setStored] = useState<{ principal: string; book: PriceBook }>(() => ({ principal, book: new Map() }));
  const [owners, setOwners] = useState<Record<string, string[]>>({});
  let book = stored.principal === principal ? stored.book : new Map();
  book = reconcilePriceBook(groups, book);
  // Derive before rendering children, so even a t1 -> newer t3 -> cached t2
  // feed sequence cannot briefly paint t2 or forget its accepted fence.
  if (stored.principal !== principal || book !== stored.book) setStored({ principal, book });
  // Stable while neither the groups nor the book moved, so consumers can memo on it.
  const projected = useMemo(() => projectPriceGroups(groups, book), [groups, book]);
  const visibleKeys = useMemo(() => new Set(Object.values(owners).flat()), [owners]);
  const leaves = groupedLeaves(projected).filter(item => visibleKeys.has(priceKey(item)!));
  const leavesRef = useRef(leaves);
  leavesRef.current = leaves;
  const groupsRef = useRef(projected);
  groupsRef.current = projected;
  const dispatcher = useRef<ReturnType<typeof createPriceDelivery> | null>(null);
  const invalidate = useCallback(() => dispatcher.current?.invalidate(), []);
  // #10090: readers live in a ref so a committed frame that changes nothing on
  // screen renders nothing; only a change to the shown preview sets state.
  const readers = useRef<Record<number, PreviewView>>({});
  const [previews, setPreviews] = useState<Previews>({ states: {}, now: 0 });
  const updatePreview = useCallback((id: number, change: (view: PreviewView, at: number) => PreviewView | null) => {
    const at = performance.now();
    const before = readers.current[id];
    const view = change(before ?? EMPTY_VIEW, at);
    if (view) readers.current[id] = view; else delete readers.current[id];
    const shown = shownPreview(view ?? undefined);
    if (shown === shownPreview(before)) return;
    setPreviews(previous => {
      const states = { ...previous.states };
      if (shown) states[id] = shown; else delete states[id];
      return { states, now: at };
    });
  }, []);
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

  const liveEvents = leaves.filter(item => item.type === 'event' && ['live', 'scheduled', 'suspended'].includes((item.data as FeedEventData).status))
    .map(item => item.data as FeedEventData & { blend_fold_revision?: unknown }).sort((a, b) => a.id - b.id);
  // #10090: the committed revision (price-card read) is the reader's sole fold
  // membership authority; a changed membership reopens the stream, as on the
  // event page, so the v3 session is opened against the adopted rows.
  const eventKey = liveEvents.map(data => `${data.id}:${Object.keys(parseFoldRevision(data.blend_fold_revision) ?? {}).sort().join('.')}`).join(',');
  const revisionKey = JSON.stringify(liveEvents.flatMap(data => data.blend_fold_revision == null ? [] : [[data.id, data.blend_fold_revision]]));
  useEffect(() => {
    // #10090: every committed revision is also a commit floor (`authorityPreviewMembership`).
    for (const [id, revision] of JSON.parse(revisionKey) as [number, unknown][]) {
      updatePreview(id, (view, at) => afterFloor(view, authorityPreviewMembership(view.reader, revision, id), revision, at));
    }
  }, [revisionKey, updatePreview]);
  useEffect(() => {
    const ids = eventKey ? eventKey.split(',').map(entry => parseInt(entry, 10)) : [];
    // #10090: a card out of view drops its reader, and its overlay, with its stream.
    Object.keys(readers.current).map(Number).filter(id => !ids.includes(id)).forEach(id => updatePreview(id, () => null));
    if (!ids.length || typeof EventSource === 'undefined') return;
    let streams: { id: number; retryAt: number | null; controller: ReturnType<typeof createLiveStreamController> }[] = [];
    const open = (id: number) => {
      const controller = createLiveStreamController({
        open: () => {
          // #10090: authority-v3 is the only protocol the preview producer
          // reaches (its frames are DNPL3 envelopes); the event page uses it too.
          const wire = new EventSource(`${API_URL}/api/events/${id}/stream?preview_protocol=authority-v3`);
          // Status is opaque to EventSource; stop its private retry on any error.
          wire.addEventListener('error', () => wire.close());
          return wire;
        },
        now: () => Date.now(), onDeliveringChange: invalidate,
        // #10090: the same reader calls, in the same order, as `useLiveEventStream`.
        onFrame: (next) => {
          invalidate();
          const promise = next.folded_quote_pending === true && !('folded_quote' in next);
          if (next.event_id === id && next.rev) updatePreview(id, (view, at) => {
            const floored = authorityPreviewFloor(view.reader, next.rev);
            const shown = shownPreview(view);
            return promise && (next.status === undefined || next.status === shown?.status)
              ? afterFloor(view, floored, next.rev, at) : { reader: floored };
          });
          else if (next.event_id === id && !promise) updatePreview(id, view => view.handover ? { reader: view.reader } : view);
        },
        onReconcile: (control) => {
          updatePreview(id, view => ({ reader: authorityPreviewFloor(view.reader, control.floor) }));
          invalidate();
        },
        previewNow: () => performance.now(),
        onAuthorityPreview: (raw, receivedAt) => updatePreview(id, (view, at) => ({
          reader: authorityPreviewFrame(view.reader, raw, id, receivedAt, at),
        })),
        onPreviewFloor: (raw) => {
          try {
            const packet = typeof raw === 'string' ? JSON.parse(raw) : raw;
            if (!packet || packet.event_id !== id) return;
            updatePreview(id, (view, at) => afterFloor(view, authorityPreviewFloor(view.reader, packet.floor), packet.floor, at));
          } catch {
            updatePreview(id, view => ({ reader: authorityPreviewReset(view.reader) }));
          }
        },
        onAuthorityPreviewOpen: (raw) => updatePreview(id, view => ({ reader: authorityPreviewOpen(view.reader, raw, id) })),
        onPreviewReset: (endSession = true) => updatePreview(id, view => ({ reader: authorityPreviewReset(view.reader, endSession) })),
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
  }, [eventKey, invalidate, principal, updatePreview]);

  // #10090: re-render when the next shown preview's lifetime ends, so an
  // expired provisional value gives way to the committed one without a frame.
  const nextExpiry = Math.min(...Object.values(previews.states).map(state => state.expiresAt).filter(at => at > previews.now));
  useEffect(() => {
    if (!Number.isFinite(nextExpiry)) return;
    const timer = setTimeout(() => setPreviews(previous => ({ ...previous, now: performance.now() })),
      Math.max(0, nextExpiry - performance.now()) + 1);
    return () => clearTimeout(timer);
  }, [nextExpiry]);

  // The price book, the dispatcher and adoption all keep reading `projected`:
  // a preview is never a committed price.
  const items = useMemo(() => overlayPreviews(projected, previews), [projected, previews]);
  return { items, setPriceVisibility };
}
