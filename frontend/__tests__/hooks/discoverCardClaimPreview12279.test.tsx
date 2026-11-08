/**
 * #12279 — a live Discover game card never prints two numbers for one team.
 *
 * Served on production, Sat Nov 7 ~8:22 AM PT (Atlas's 390 px capture for #12255):
 * the Hull City @ Arsenal card read "Arsenal 67%" over its own sentence "Arsenal
 * chance fell from 83% to 66%". The number is #10090's preview, repainted at a
 * venue's move; the sentence is the producer's claim about the COMMITTED price,
 * and it stayed until the next price-card read brought one for the new number.
 *
 * The rule: while the preview prints a different percent for the side the
 * sentence states (`live_claim_percent`, served by the feed), the sentence is
 * withdrawn; the read that commits the move brings its own. A sentence that
 * states no current percent (an underdog lead), or a preview that prints the
 * same percent, is left alone.
 *
 * Harness as `discoverCardPreview10090`: the real hook over a fake EventSource,
 * frames from `docs/contracts/dnpl-authority-v3.examples.json`.
 */
import '../helpers/minimalDom';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { useDiscoverPriceStream } from '../../hooks/useDiscoverPriceStream';
import { fetchDiscoverPriceCards } from '../../lib/api';
import { adoptPriceCards, groupedLeaves, projectPriceGroups } from '../../lib/discover/priceRefresh';
import { servedDuelPercents } from '../../lib/servedDuelPercents';
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

const FELL_TO_66 = 'Arsenal chance fell from 83% to 66%';
const event = {
  id: 42, external_id: 'x42', sport: 'soccer_epl', sport_name: 'EPL', home_team: 'Arsenal', away_team: 'Hull City',
  commence_time: '2026-11-07T15:00:00Z', status: 'live', home_score: 1, away_score: 0,
  current_odds: { home_probability: 0.655, away_probability: 0.345, home_rendered_percent: 66, away_rendered_percent: 34 },
} as unknown as FeedEventData;
const groups: DiscoverGroupedItem[] = [{ type: 'single', item: { type: 'event', data: event, headline: null, reason: '', score: 1 } as FeedItem }];

/** A price-card read: the committed price at `home`, with the copy the feed composed for it. */
const card = (revision: Record<string, number>, home: number, copy: Record<string, unknown>,
  data: Record<string, unknown> = {}) => {
  const homePct = Math.round(home * 100);
  return {
    items: [{
      type: 'event', score: 1, ...copy,
      data: {
        ...event, ...data, current_odds: { home_probability: home, away_probability: 1 - home,
          home_rendered_percent: homePct, away_rendered_percent: 100 - homePct },
        blend_fold_revision: revision, hero_probability_source: 'blend', hero_probability_observed_at: '2026-11-07T16:21:00Z',
      },
    } as unknown as FeedItem],
    dispositions: { 'event-42': 'updated' as const }, built_at: 1,
  };
};
const claim66 = { headline: FELL_TO_66, reason: FELL_TO_66, live_claim_percent: { side: 'home', percent: 66 } };
const preview = (p: number, preview: Record<string, unknown> = {}) => wire({
  ...m.singleton_blend,
  frame: { ...m.singleton_blend.frame, p, p_away: null, sport: 'soccer_epl',
    preview: { ...m.singleton_blend.frame.preview, ttl_ms: 120_000, ...preview } },
});
const committedFrame = () => wire({
  event_id: 42, p: 0.67, source: 'blend', source_value: null, updated_at: '2026-11-07T16:22:01Z', status: 'live',
});

const fetcher = fetchDiscoverPriceCards as jest.Mock;
let root: Root | undefined;
let held: ReturnType<typeof useDiscoverPriceStream>;

function Harness() {
  held = useDiscoverPriceStream(groups, 'signed-out');
  return null;
}
const shown = () => held.items[0].item!;
const odds = () => (shown().data as FeedEventData).current_odds!;
const stream = () => FakeEventSource.instances.filter(source => source.url.startsWith('/api/events/42/stream') && !source.closed).at(-1)!;
const flush = (ms = 0) => act(async () => { await jest.advanceTimersByTimeAsync(ms); });

/** The percent the card prints for `side`, by the card's own call (`components/discover/EventCard`). */
function printed(side: 'home' | 'away'): number | null {
  const o = odds();
  const [away, home] = servedDuelPercents(o.away_probability, o.home_probability,
    o.away_rendered_percent, o.home_rendered_percent);
  return side === 'home' ? home : away;
}

async function visibleCard(response: ReturnType<typeof card>) {
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

test('the committed card states the number it prints', async () => {
  await visibleCard(card({ '42': 10 }, 0.655, claim66));
  expect(printed('home')).toBe(66);
  expect(shown().headline).toBe(FELL_TO_66);
});

test('🔴 the specimen: a preview that prints 67 withdraws the sentence that says 66', async () => {
  await visibleCard(card({ '42': 10 }, 0.655, claim66));
  stream().emit('preview_v3', preview(0.67));
  expect(odds().home_probability).toBe(0.67);
  expect(printed('home')).toBe(67);
  // Nothing left on the card says 66% beside the 67%.
  expect(shown().headline).toBeNull();
  expect(shown().reason).toBe('');
  expect(shown().live_claim_percent ?? null).toBeNull();
});

test('the read that commits the move brings the sentence for the new number', async () => {
  await visibleCard(card({ '42': 10 }, 0.655, claim66));
  stream().emit('preview_v3', preview(0.67));
  expect(shown().headline).toBeNull();
  const fellTo67 = 'Arsenal chance fell from 83% to 67%';
  fetcher.mockResolvedValue(card({ '42': 11 }, 0.67,
    { headline: fellTo67, reason: fellTo67, live_claim_percent: { side: 'home', percent: 67 } }));
  stream().emit('probability', committedFrame());
  await flush(2_000);
  expect(printed('home')).toBe(67);
  expect(shown().headline).toBe(fellTo67);
});

test('a preview that prints the same percent keeps the sentence', async () => {
  await visibleCard(card({ '42': 10 }, 0.655, claim66));
  stream().emit('preview_v3', preview(0.6575));
  expect(odds().home_probability).toBe(0.6575);
  expect(printed('home')).toBe(66);
  expect(shown().headline).toBe(FELL_TO_66);
});

test('a sentence that states no current percent is left alone', async () => {
  const lead = 'Hull City leading after starting at 5%';
  await visibleCard(card({ '42': 10 }, 0.655, { headline: lead, reason: lead }));
  stream().emit('preview_v3', preview(0.67));
  expect(printed('home')).toBe(67);
  expect(shown().headline).toBe(lead);
});

test('an away-side sentence is judged on the away number', async () => {
  // Two-way board: the sentence names the away side, so the home number is not its number.
  const rose = 'Hull City chance rose from 40% to 70%';
  await visibleCard(card({ '42': 10 }, 0.3, { headline: rose, reason: rose, live_claim_percent: { side: 'away', percent: 70 } },
    { sport: 'americanfootball_nfl' }));
  stream().emit('preview_v3', preview(0.302, { seq: 2 }));
  expect([printed('away'), printed('home')]).toEqual([70, 30]);
  expect(shown().headline).toBe(rose);
  stream().emit('preview_v3', preview(0.29, { seq: 3 }));
  expect(printed('away')).toBe(71);
  expect(shown().headline).toBeNull();
});

test('copy that is not the stale sentence survives its withdrawal', async () => {
  await visibleCard(card({ '42': 10 }, 0.655, { ...claim66, reason: 'Tight game' }));
  stream().emit('preview_v3', preview(0.67));
  expect(shown().headline).toBeNull();
  expect(shown().reason).toBe('Tight game');
});

test('the stated percent travels with the sentence in the price book', () => {
  const held = { ...groups[0].item!, ...claim66 } as FeedItem;
  const start = [{ type: 'single', item: held }] as DiscoverGroupedItem[];
  // A fresh read whose sentence states no current percent clears the held one.
  const fresh = card({ '42': 11 }, 0.67, { headline: 'Tight game', reason: 'Tight game' });
  const book = adoptPriceCards(new Map(), groupedLeaves(start), fresh, new Set(['event-42']));
  const [projected] = projectPriceGroups(start, book);
  expect(projected.item!.headline).toBe('Tight game');
  expect('live_claim_percent' in projected.item!).toBe(false);
});
