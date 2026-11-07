/**
 * #10090 — a Discover futures card in view shows the venue's move at arrival.
 *
 * The real hook and the real market stream (`useMarketStream` →
 * `createMarketStreamController`) are mounted (minimalDom, as
 * `discoverNavigationCleanup9722`) over a fake EventSource, and the card's
 * numbers are read from the hook's `items` — the array the Discover page
 * renders. Frames are the backend's `market_preview` shape
 * (`backend/app/utils/market_preview.py`).
 */
import '../helpers/minimalDom';
import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { useDiscoverPriceStream } from '../../hooks/useDiscoverPriceStream';
import { fetchDiscoverPriceCards } from '../../lib/api';
import { adoptPriceCards, groupedLeaves, projectPriceGroups } from '../../lib/discover/priceRefresh';
import type { DiscoverGroupedItem } from '../../components/discover/types';
import type { FeedFuturesData, FeedItem } from '../../lib/types';

jest.mock('../../lib/api', () => ({ API_URL: '', fetchDiscoverPriceCards: jest.fn() }));

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

const T0 = '2026-11-03T17:00:00.000000+00:00';
const T1 = '2026-11-03T17:00:05.250000+00:00';
const T_MID = '2026-11-03T17:00:03.000000+00:00';
const MARKET = 501;

const leg = (id: number, name: string, probability: number, clock: string, rank: number) => (
  { id, name, probability, rank, movement: null, rendered_percent: Math.round(probability * 100), price_observed_at: clock });

/** A three-way field (not a complement pair): each previewed leg moves on its own. */
function market(yes = 0.4, clock = T0, extra: Record<string, unknown> = {}) {
  return {
    id: MARKET, name: 'Who wins?', source: 'kalshi', status: 'open', group_id: null, group_type: null,
    canonical_market_key: null, external_id: 'KXTEST', display_scale: 1, price_observed_at: clock,
    outcome_observed_at: { '70': clock, '71': clock, '72': clock },
    top_outcomes: [leg(70, 'Alpha', yes, clock, 1), leg(71, 'Beta', 0.5, clock, 2), leg(72, 'Gamma', 0.1, clock, 3)],
    ...extra,
  } as unknown as FeedFuturesData;
}

/** A Yes/No complement pair (#2060: it prints a total of 100). */
function pairMarket(yes = 0.425, no = 0.575, clock = T0) {
  return {
    ...market(yes, clock), name: 'Will it happen?', outcome_observed_at: { '70': clock, '71': clock },
    top_outcomes: [
      { ...leg(70, 'Yes', yes, clock, 1), rendered_percent: 43 }, { ...leg(71, 'No', no, clock, 2), rendered_percent: 57 },
    ],
  } as unknown as FeedFuturesData;
}
const card = (data: FeedFuturesData) => ({
  items: [{ type: 'futures', data } as FeedItem], dispositions: { [`futures-${MARKET}`]: 'updated' as const }, built_at: Date.now(),
});
const preview = (extra: Record<string, unknown> = {}, outcomes = [{ outcome_id: 70, p: 0.47, observed_at: T1 }]) => wire({
  type: 'market_preview', preview: true, market_id: MARKET, source: 'kalshi', outcomes, seq: 5, ttl_ms: 10_000,
  published_at: '2026-11-03T17:00:05.300000+00:00', ...extra,
});
const invalidation = () => wire({
  market_id: MARKET, source: 'kalshi', outcome_ids: [70], outcome_observed_at: { '70': T1 }, updated_at: T1,
  terminal: false, invalidation: true,
});

const fetcher = fetchDiscoverPriceCards as jest.Mock;
let root: Root | undefined;
let held: ReturnType<typeof useDiscoverPriceStream>;
let groups: DiscoverGroupedItem[];

function Harness() {
  held = useDiscoverPriceStream(groups, 'signed-out');
  return null;
}
const rows = () => (held.items[0].item!.data as FeedFuturesData).top_outcomes;
const yes = () => rows()[0];
const stream = () => FakeEventSource.instances.filter(source => source.url.startsWith('/api/markets/stream') && !source.closed).at(-1)!;
const flush = (ms = 0) => act(async () => { await jest.advanceTimersByTimeAsync(ms); });

/** A visible open futures card whose committed price was read, its market stream open. */
async function visibleCard(data = market()) {
  groups = [{ type: 'single', item: { type: 'futures', data } as FeedItem }];
  fetcher.mockResolvedValue(card(data));
  const container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root!.render(<Harness />));
  act(() => held.setPriceVisibility('card', [`futures-${MARKET}`], true));
  await flush();
  stream().emit('open', wire({ market_ids: [MARKET], unavailable_market_ids: [] }));
}

beforeEach(() => {
  jest.useFakeTimers();
  jest.setSystemTime(new Date('2026-11-03T17:00:06Z'));
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

test('a preview frame moves a visible futures card before any refetch', async () => {
  await visibleCard();
  expect(stream().url).toBe(`/api/markets/stream?ids=${MARKET}`);
  expect(yes().probability).toBe(0.4);
  const reads = fetcher.mock.calls.length;
  stream().emit('market_preview', preview());
  expect(yes()).toEqual(expect.objectContaining({ id: 70, probability: 0.47, rendered_percent: null }));
  // Only the previewed leg moves; its sibling keeps its committed number.
  expect(rows()[1]).toEqual(expect.objectContaining({ id: 71, probability: 0.5, rendered_percent: 50 }));
  expect(rows()[2]).toEqual(expect.objectContaining({ id: 72, probability: 0.1, rendered_percent: 10 }));
  expect(fetcher.mock.calls.length).toBe(reads);
});

test('a committed read with an equal or newer observation replaces it; an older one does not', async () => {
  await visibleCard();
  stream().emit('market_preview', preview());
  expect(yes().probability).toBe(0.47);
  // Committed, newer than the card's but older than the preview: the book
  // adopts it, the preview stays on top.
  const reads = fetcher.mock.calls.length;
  fetcher.mockResolvedValue(card(market(0.44, T_MID)));
  stream().emit('market', invalidation());
  await flush(2_000);
  expect(fetcher.mock.calls.length).toBeGreaterThan(reads);
  expect(yes().probability).toBe(0.47);
  // (It was adopted: its sibling's newer committed clock is on the card.)
  expect((held.items[0].item!.data as unknown as { outcome_observed_at: Record<string, string> }).outcome_observed_at['71']).toBe(T_MID);
  // Committed at the preview's own observation: it wins.
  fetcher.mockResolvedValue(card(market(0.46, T1)));
  stream().emit('market', invalidation());
  await flush(2_000);
  expect(yes()).toEqual(expect.objectContaining({ probability: 0.46, rendered_percent: 46 }));
});

test('ttl expiry returns the card to its committed number', async () => {
  await visibleCard();
  stream().emit('market_preview', preview({ ttl_ms: 800 }));
  expect(yes().probability).toBe(0.47);
  await flush(799);
  expect(yes().probability).toBe(0.47);
  await flush(2);
  expect(yes()).toEqual(expect.objectContaining({ probability: 0.4, rendered_percent: 40 }));
});

test('a lower or repeated seq is refused; a higher one moves the card', async () => {
  await visibleCard();
  stream().emit('market_preview', preview({ seq: 5 }));
  stream().emit('market_preview', preview({ seq: 4 }, [{ outcome_id: 70, p: 0.3, observed_at: T1 }]));
  stream().emit('market_preview', preview({ seq: 5 }, [{ outcome_id: 70, p: 0.3, observed_at: T1 }]));
  expect(yes().probability).toBe(0.47);
  stream().emit('market_preview', preview({ seq: 6 }, [{ outcome_id: 71, p: 0.52, observed_at: T1 }]));
  // A later frame for the sibling keeps the earlier leg's unexpired preview.
  expect(yes().probability).toBe(0.47);
  expect(rows()[1].probability).toBe(0.52);
});

test('a reconnect clears the overlay and the retired connection cannot reach the card', async () => {
  await visibleCard();
  const source = stream();
  source.emit('market_preview', preview());
  expect(yes().probability).toBe(0.47);
  source.emit('reconnect');
  expect(yes().probability).toBe(0.4);
  source.emit('market_preview', preview({ seq: 9 }));
  expect(yes().probability).toBe(0.4);
});

test('scrolling the card out of view closes its stream and clears the overlay', async () => {
  await visibleCard();
  const source = stream();
  source.emit('market_preview', preview());
  expect(yes().probability).toBe(0.47);
  act(() => held.setPriceVisibility('card', [], false));
  expect(source.closed).toBe(true);
  expect(yes().probability).toBe(0.4);
});

test('a card printed on a scaled basis, another source, or a withheld leg ignores the preview', async () => {
  await visibleCard(market(0.4, T0, { display_scale: 1.05 }));
  stream().emit('market_preview', preview());
  expect(yes().probability).toBe(0.4);
  act(() => root!.unmount());
  root = undefined;

  FakeEventSource.instances = [];
  await visibleCard(market(0.4, T0, { source: 'polymarket' }));
  stream().emit('market_preview', preview());
  expect(yes().probability).toBe(0.4);
  act(() => root!.unmount());
  root = undefined;

  FakeEventSource.instances = [];
  const withheld = market(0.4, T0);
  withheld.top_outcomes[0] = { ...withheld.top_outcomes[0], probability: null };
  await visibleCard(withheld);
  stream().emit('market_preview', preview());
  expect(yes().probability).toBe(null);
});

// ── a complement pair prints a total of 100 ─────────────────────────────────

const percents = () => rows().map(row => row.rendered_percent);

test('a one-sided Kalshi move on a complement pair carries its complement to the other side', async () => {
  await visibleCard(pairMarket());
  // 0.445 / 0.555 rounded on their own read 45 / 56 = 101 (the #2060 picture).
  stream().emit('market_preview', preview({}, [{ outcome_id: 70, p: 0.445, observed_at: T1 }]));
  expect(rows().map(row => row.probability)).toEqual([0.445, 0.555]);
  expect(percents()[0]! + percents()[1]!).toBe(100);
  expect(percents()).toEqual([45, 55]);
});

test('the No side previewed alone sets Yes to its complement', async () => {
  await visibleCard(pairMarket());
  stream().emit('market_preview', preview({}, [{ outcome_id: 71, p: 0.615, observed_at: T1 }]));
  expect(rows().map(row => row.probability)).toEqual([0.385, 0.615]);
  expect(percents()[0]! + percents()[1]!).toBe(100);
});

test('both sides previewed consistently are shown', async () => {
  await visibleCard(pairMarket());
  stream().emit('market_preview', preview({}, [
    { outcome_id: 70, p: 0.47, observed_at: T1 }, { outcome_id: 71, p: 0.535, observed_at: T1 },
  ]));
  expect(rows().map(row => row.probability)).toEqual([0.47, 0.535]);
  expect(percents()[0]! + percents()[1]!).toBe(100);
});

test('both sides previewed inconsistently keep the committed pair', async () => {
  await visibleCard(pairMarket());
  stream().emit('market_preview', preview({}, [
    { outcome_id: 70, p: 0.47, observed_at: T1 }, { outcome_id: 71, p: 0.6, observed_at: T1 },
  ]));
  expect(rows().map(row => row.probability)).toEqual([0.425, 0.575]);
  expect(percents()).toEqual([43, 57]);
});

test('a multi-outcome field that is not a pair is untouched by the pair rule', async () => {
  await visibleCard(market());
  stream().emit('market_preview', preview({}, [{ outcome_id: 70, p: 0.445, observed_at: T1 }]));
  expect(rows().map(row => row.probability)).toEqual([0.445, 0.5, 0.1]);
  expect(percents()).toEqual([null, 50, 10]);
});

test('control: with no preview frames the items are exactly what the price book projects', async () => {
  const data = market();
  await visibleCard(data);
  stream().emit('market', invalidation());
  await flush(2_000);
  const response = card(data);
  const book = adoptPriceCards(new Map(), groupedLeaves(groups), response, new Set([`futures-${MARKET}`]));
  expect(wire(held.items)).toBe(wire(projectPriceGroups(groups, book)));
});


test('a server-allocated field keeps its shared numbers until the committed API refresh', async () => {
  const allocated = (p: number, clock: string) => {
    const data = market(p, clock);
    data.top_outcomes = [leg(70, 'Alpha', p, clock, 1), leg(71, 'Beta', 0.9 - p, clock, 2), leg(72, 'Gamma', 0.1, clock, 3)];
    return { ...data, full_field_rendered: true, discover_card: { distribution_outcomes: data.top_outcomes.map(row => ({
      label: row.name, probability: row.probability, rendered_percent: row.rendered_percent,
    })) } } as FeedFuturesData;
  };
  await visibleCard(allocated(0.4, T0));
  stream().emit('market_preview', preview());
  expect(yes()).toEqual(expect.objectContaining({ probability: 0.4, rendered_percent: 40 }));
  fetcher.mockResolvedValue(card(allocated(0.45, T1)));
  stream().emit('market', invalidation());
  await flush(2_000);
  expect(yes()).toEqual(expect.objectContaining({ probability: 0.45, rendered_percent: 45 }));
  expect(rows().map(row => row.rendered_percent).reduce<number>((sum, p) => sum + (p ?? 0), 0)).toBe(100);
});
