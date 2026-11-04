/**
 * #10090 — a Discover game card in view shows the venue's move at arrival.
 *
 * The real hook is mounted (minimalDom, as `discoverNavigationCleanup9722`)
 * over a fake EventSource, and the card's number is read from the hook's
 * `items` — the array the Discover page renders. The v3 frames are the
 * contract examples (`docs/contracts/dnpl-authority-v3.examples.json`).
 */
import '../helpers/minimalDom';
import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { useDiscoverPriceStream } from '../../hooks/useDiscoverPriceStream';
import { fetchDiscoverPriceCards } from '../../lib/api';
import { adoptPriceCards, groupedLeaves, projectPriceGroups } from '../../lib/discover/priceRefresh';
import type { DiscoverGroupedItem } from '../../components/discover/types';
import type { FeedEventData, FeedItem } from '../../lib/types';
import examples from '../../../docs/contracts/dnpl-authority-v3.examples.json';

jest.mock('../../lib/api', () => ({ API_URL: '', fetchDiscoverPriceCards: jest.fn() }));
jest.mock('../../hooks/useMarketStream', () => ({ useMarketStream: jest.fn() }));

const m = examples.messages;
const wire = JSON.stringify;

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  readyState = 1;
  closed = false;
  listeners: Record<string, ((event: unknown) => void)[]> = {};
  constructor(public url: string) { FakeEventSource.instances.push(this); }
  addEventListener(type: string, listener: (event: unknown) => void) { (this.listeners[type] ??= []).push(listener); }
  close() { this.closed = true; this.readyState = 2; }
  emit(type: string, data?: unknown) { act(() => (this.listeners[type] ?? []).forEach(listener => listener({ data }))); }
}

const committedOdds = { home_probability: 0.55, away_probability: 0.45, home_rendered_percent: 55, away_rendered_percent: 45 };
const event = {
  id: 42, external_id: 'x42', sport: 'tennis_atp', sport_name: 'ATP', home_team: 'Home', away_team: 'Away',
  commence_time: '2026-10-25T16:00:00Z', status: 'live', home_score: null, away_score: null, current_odds: committedOdds,
} as unknown as FeedEventData;
const groups: DiscoverGroupedItem[] = [{ type: 'single', item: { type: 'event', data: event } as FeedItem }];
const card = (revision: Record<string, number>, home = 0.55, extra: Record<string, unknown> = {}) => ({
  items: [{ type: 'event', data: {
    ...event, current_odds: home === 0.55 ? committedOdds : { home_probability: home, away_probability: 1 - home,
      home_rendered_percent: Math.round(home * 100), away_rendered_percent: 100 - Math.round(home * 100) },
    blend_fold_revision: revision, hero_probability_source: 'blend', hero_probability_observed_at: '2026-10-25T16:59:00Z',
    ...extra,
  } } as unknown as FeedItem],
  dispositions: { 'event-42': 'updated' as const }, built_at: 1,
});
const blend = (preview: Record<string, unknown> = {}, frame: Record<string, unknown> = {}) => wire({
  ...m.singleton_blend,
  frame: { ...m.singleton_blend.frame, ...frame, preview: { ...m.singleton_blend.frame.preview, ...preview } },
});
const committedFrame = (extra: Record<string, unknown> = {}) => wire({
  event_id: 42, p: 0.55, source: 'blend', source_value: null, updated_at: '2026-10-25T17:00:01Z', status: 'live', ...extra,
});

const fetcher = fetchDiscoverPriceCards as jest.Mock;
let root: Root | undefined;
let held: ReturnType<typeof useDiscoverPriceStream>;

function Harness() {
  held = useDiscoverPriceStream(groups, 'signed-out');
  return null;
}
const odds = () => (held.items[0].item!.data as FeedEventData).current_odds;
const stream = () => FakeEventSource.instances.filter(source => source.url.startsWith('/api/events/42/stream') && !source.closed).at(-1)!;
const flush = (ms = 0) => act(async () => { await jest.advanceTimersByTimeAsync(ms); });

/** A visible live card whose committed revision {42: 10} was read, its stream open on a v3 session. */
async function visibleCard(response = card({ '42': 10 })) {
  fetcher.mockResolvedValue(response);
  const container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root!.render(<Harness />));
  act(() => held.setPriceVisibility('card', ['event-42'], true));
  await flush();
  stream().emit('open');
  stream().emit('preview_open_v3', wire(m.singleton_open));
}

beforeEach(() => {
  jest.useFakeTimers();
  FakeEventSource.instances = [];
  (globalThis as Record<string, unknown>).EventSource = FakeEventSource;
  fetcher.mockReset();
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
  jest.spyOn(document, 'addEventListener').mockImplementation(() => {});
});
afterEach(() => {
  jest.restoreAllMocks();
  const current = root;
  root = undefined;
  act(() => current?.unmount());
  delete (globalThis as Record<string, unknown>).EventSource;
  jest.useRealTimers();
});

test('a preview frame moves a visible live game card before any refetch', async () => {
  await visibleCard();
  expect(odds()).toEqual(committedOdds);
  const reads = fetcher.mock.calls.length;
  stream().emit('preview_v3', blend());
  expect(odds()).toEqual({ home_probability: 0.6, away_probability: 1 - 0.6, home_rendered_percent: null, away_rendered_percent: null });
  expect(fetcher.mock.calls.length).toBe(reads);
  // The preview producer reaches authority-v3 subscribers only.
  expect(stream().url).toBe('/api/events/42/stream?preview_protocol=authority-v3');
});

test('a newer committed revision from the price-card read replaces it; an older one does not', async () => {
  await visibleCard();
  stream().emit('preview_v3', blend({ ttl_ms: 120_000 }));
  expect(odds()?.home_probability).toBe(0.6);
  // An older revision is refused by the price book, so the preview stays.
  fetcher.mockResolvedValue(card({ '42': 9 }, 0.5));
  stream().emit('probability', committedFrame());
  await flush(2_000);
  expect(fetcher).toHaveBeenCalledTimes(2);
  expect(odds()?.home_probability).toBe(0.6);
  // A newer one wins, whoever wrote it.
  fetcher.mockResolvedValue(card({ '42': 11 }, 0.58));
  stream().emit('probability', committedFrame());
  await flush(2_000);
  expect(fetcher).toHaveBeenCalledTimes(3);
  expect(odds()).toEqual({ home_probability: 0.58, away_probability: 1 - 0.58, home_rendered_percent: 58, away_rendered_percent: 42 });
});

test('a committed frame announcing a newer revision withdraws the preview before the read lands', async () => {
  await visibleCard();
  stream().emit('preview_v3', blend({ ttl_ms: 120_000 }));
  stream().emit('probability', committedFrame({ rev: { '42': 11 } }));
  expect(odds()).toEqual(committedOdds);
});

test('revoke and ttl expiry return the card to its committed number', async () => {
  await visibleCard();
  stream().emit('preview_v3', blend());
  expect(odds()?.home_probability).toBe(0.6);
  stream().emit('preview_v3', wire(m.singleton_revoke));
  expect(odds()).toEqual(committedOdds);

  stream().emit('preview_v3', blend({ seq: 3 }, { p: 0.62 }));
  expect(odds()?.home_probability).toBe(0.62);
  await flush(799);
  expect(odds()?.home_probability).toBe(0.62);
  await flush(2);
  expect(odds()).toEqual(committedOdds);
});

test('a lower epoch or a lower seq is refused', async () => {
  await visibleCard();
  stream().emit('preview_v3', blend({ seq: 3, ttl_ms: 120_000 }));
  expect(odds()?.home_probability).toBe(0.6);
  stream().emit('preview_v3', blend({ epoch: 1, seq: 9, ttl_ms: 120_000 }, { p: 0.7 }));
  expect(odds()?.home_probability).toBe(0.6);
  stream().emit('preview_v3', blend({ seq: 2, ttl_ms: 120_000 }, { p: 0.7 }));
  expect(odds()?.home_probability).toBe(0.6);
  stream().emit('preview_v3', blend({ seq: 4, ttl_ms: 120_000 }, { p: 0.65 }));
  expect(odds()?.home_probability).toBe(0.65);
});

test('a non-blend hero ignores the preview', async () => {
  await visibleCard(card({ '42': 10 }, 0.55, { hero_probability_source: 'sportsbook' }));
  stream().emit('preview_v3', blend({ ttl_ms: 120_000 }));
  expect(odds()).toEqual(committedOdds);
});

test('a preview in a different quote status is ignored', async () => {
  await visibleCard();
  stream().emit('preview_v3', blend({ ttl_ms: 120_000 }, { status: 'scheduled' }));
  expect(odds()).toEqual(committedOdds);
});

test('a card with no committed revision yet shows no preview', async () => {
  fetcher.mockResolvedValue({ items: [], dispositions: {}, built_at: 1 });
  const container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root!.render(<Harness />));
  act(() => held.setPriceVisibility('card', ['event-42'], true));
  await flush();
  stream().emit('open');
  stream().emit('preview_open_v3', wire(m.singleton_open));
  stream().emit('preview_v3', blend({ ttl_ms: 120_000 }));
  expect(odds()).toEqual(committedOdds);
});

test('scrolling the card out of view closes its stream and clears the overlay', async () => {
  await visibleCard();
  const source = stream();
  source.emit('preview_v3', blend({ ttl_ms: 120_000 }));
  expect(odds()?.home_probability).toBe(0.6);
  act(() => held.setPriceVisibility('card', [], false));
  expect(source.closed).toBe(true);
  expect(odds()).toEqual(committedOdds);
});

test('a reconnect clears the overlay', async () => {
  await visibleCard();
  const source = stream();
  source.emit('preview_v3', blend({ ttl_ms: 120_000 }));
  expect(odds()?.home_probability).toBe(0.6);
  source.emit('reconnect');
  expect(odds()).toEqual(committedOdds);
  // The retired socket can no longer reach the card.
  source.emit('preview_v3', blend({ seq: 5, ttl_ms: 120_000 }, { p: 0.7 }));
  expect(odds()).toEqual(committedOdds);
});

test('control: with no preview frames the items are exactly what the price book projects', async () => {
  const response = card({ '42': 10 });
  await visibleCard(response);
  stream().emit('probability', committedFrame());
  stream().emit('preview_v3', wire(m.singleton_revoke));
  const book = adoptPriceCards(new Map(), groupedLeaves(groups), response, new Set(['event-42']));
  expect(wire(held.items)).toBe(wire(projectPriceGroups(groups, book)));
});
