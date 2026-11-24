/**
 * #10090 — Category pages (`/categories/[slug]`) project live committed and
 * provisional SSE prices (`authority-v3` events, `market_preview` single &
 * combined futures cards) onto visible cards within <= 0.5 s without reload.
 */
import '../helpers/minimalDom';
import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import CategoryPage from '@/app/categories/[slug]/page';
import { fetchDiscoverPriceCards, fetchFeed } from '@/lib/api';
import type { FeedEventData, FeedFuturesData, FeedItem, FeedResponse } from '@/lib/types';
import examples from '../../../docs/contracts/dnpl-authority-v3.examples.json';

jest.mock('next/link', () => {
  const ReactLib = require('react');
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement('a', { href, ...props }, children),
  };
});

jest.mock('next/image', () => {
  const ReactLib = require('react');
  return {
    __esModule: true,
    default: ({ alt, src, ...props }: Record<string, unknown>) =>
      ReactLib.createElement('img', { alt, src, ...props }),
  };
});

jest.mock('@/components/motion', () => {
  const ReactLib = require('react');
  const stripMotionProps = ({
    initial: _i,
    animate: _a,
    exit: _e,
    transition: _t,
    whileHover: _wh,
    whileTap: _wt,
    layout: _l,
    layoutId: _lid,
    variants: _v,
    ...domProps
  }: Record<string, unknown>) => domProps;
  const tag = (el: string) =>
    ReactLib.forwardRef(({ children, ...props }: Record<string, unknown>, ref: unknown) =>
      ReactLib.createElement(el, { ...stripMotionProps(props), ref }, children as React.ReactNode),
    );
  return {
    MotionProvider: ({ children }: { children: React.ReactNode }) => children,
    motion: { div: tag('div'), span: tag('span'), button: tag('button') },
  };
});

jest.mock('@/components/AuthProvider', () => ({
  useAuthContext: () => ({ user: null, isLoading: false }),
}));

jest.mock('@/components/Analytics', () => ({
  useAnalyticsContext: () => ({ track: jest.fn() }),
}));

jest.mock('@/hooks', () => ({
  usePageTracking: jest.fn(),
  useScrollDepth: jest.fn(),
  useEngagementTime: jest.fn(),
}));

jest.mock('@/lib/api', () => {
  const actual = jest.requireActual('@/lib/api');
  return {
    ...actual,
    API_URL: '',
    fetchFeed: jest.fn(),
    fetchDiscoverPriceCards: jest.fn(),
  };
});

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  readyState = 1;
  closed = false;
  listeners: Record<string, ((event: unknown) => void)[]> = {};
  constructor(public url: string) {
    FakeEventSource.instances.push(this);
  }
  addEventListener(type: string, listener: (event: unknown) => void) {
    (this.listeners[type] ??= []).push(listener);
  }
  close() {
    this.closed = true;
    this.readyState = 2;
  }
  emit(type: string, data?: unknown) {
    act(() => (this.listeners[type] ?? []).forEach((listener) => listener({ data })));
  }
}

const wire = JSON.stringify;
const realHrtimeNs = process.hrtime.bigint.bind(process.hrtime);
const m = examples.messages;
const fetchFeedMock = fetchFeed as jest.Mock;
const fetchPriceCardsMock = fetchDiscoverPriceCards as jest.Mock;

const T0 = '2026-11-23T17:00:00Z';
const T1 = '2026-11-23T17:00:05Z';

const makeOutcome = (id: number, name: string, probability: number, rendered_percent?: number) => ({
  id,
  name,
  probability,
  ...(rendered_percent !== undefined ? { rendered_percent } : {}),
  american_odds: null,
  rank: id,
  rank_change_24h: null,
  probability_change_24h: null,
  price_observed_at: T0,
});

const liveEvent: FeedEventData = {
  id: 42,
  external_id: 'evt-42',
  sport: 'tennis_atp',
  sport_name: 'ATP',
  home_team: 'Carlos Alcaraz',
  away_team: 'Jannik Sinner',
  commence_time: '2026-11-23T16:00:00Z',
  status: 'live',
  home_score: 1,
  away_score: 0,
  current_odds: {
    home_probability: 0.55,
    away_probability: 0.45,
    home_rendered_percent: 55,
    away_rendered_percent: 45,
  },
  blend_fold_revision: { '42': 10 },
  hero_probability_source: 'blend',
  hero_probability_observed_at: T0,
} as unknown as FeedEventData;

const singleMarket: FeedFuturesData = {
  id: 111,
  name: 'Single Politics Approval Market',
  category: 'politics',
  llm_sport_category: 'politics',
  status: 'open',
  source: 'kalshi',
  external_id: 'KX-111',
  display_scale: 1,
  price_observed_at: T0,
  outcome_observed_at: { '70': T0, '71': T0 },
  top_outcomes: [
    makeOutcome(70, 'Above 50%', 0.43, 43),
    makeOutcome(71, 'Below 50%', 0.57, 57),
  ],
} as unknown as FeedFuturesData;

const combinedKalshi: FeedFuturesData = {
  id: 221,
  name: 'Fed Rate Cut Next Meeting',
  category: 'politics',
  llm_sport_category: 'politics',
  canonical_market_key: 'politics::fed-cut-2026',
  status: 'open',
  source: 'kalshi',
  external_id: 'KX-221',
  display_scale: 1,
  price_observed_at: T0,
  outcome_observed_at: { '80': T0, '81': T0 },
  top_outcomes: [
    makeOutcome(80, 'Yes', 0.42),
    makeOutcome(81, 'No', 0.58),
  ],
} as unknown as FeedFuturesData;

const combinedPoly: FeedFuturesData = {
  id: 222,
  name: 'Fed Rate Cut Next Meeting',
  category: 'politics',
  llm_sport_category: 'politics',
  canonical_market_key: 'politics::fed-cut-2026',
  status: 'open',
  source: 'polymarket',
  external_id: 'PM-222',
  display_scale: 1,
  price_observed_at: T0,
  outcome_observed_at: { '90': T0, '91': T0 },
  top_outcomes: [
    makeOutcome(90, 'Yes', 0.44),
    makeOutcome(91, 'No', 0.56),
  ],
} as unknown as FeedFuturesData;

const initialItems: FeedItem[] = [
  { type: 'event', id: 42, score: 100, data: liveEvent } as unknown as FeedItem,
  { type: 'futures', id: 111, score: 90, data: singleMarket } as unknown as FeedItem,
  { type: 'futures', id: 221, score: 85, data: combinedKalshi } as unknown as FeedItem,
  { type: 'futures', id: 222, score: 80, data: combinedPoly } as unknown as FeedItem,
];

let root: Root | undefined;
const flush = (ms = 0) => act(async () => { await jest.advanceTimersByTimeAsync(ms); });

class FakeIntersectionObserver {
  constructor(private cb: (entries: { isIntersecting: boolean }[]) => void) {}
  observe = () => {
    this.cb([{ isIntersecting: true }]);
  };
  unobserve = () => {};
  disconnect = () => {};
}

beforeEach(() => {
  jest.useFakeTimers();
  FakeEventSource.instances = [];
  (globalThis as Record<string, unknown>).EventSource = FakeEventSource;
  (globalThis as Record<string, unknown>).IntersectionObserver = FakeIntersectionObserver;
  fetchFeedMock.mockReset();
  fetchPriceCardsMock.mockReset();
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
});

afterEach(() => {
  if (root) {
    act(() => root!.unmount());
    root = undefined;
  }
  document.body.innerHTML = '';
  jest.useRealTimers();
});

test('/categories/[slug] re-prices live event cards, FeedCard, and CombinedFeedCard within <= 0.5 s without reload', async () => {
  const feedResponse: FeedResponse = {
    items: initialItems,
    total: 4,
    limit: 50,
    offset: 0,
    has_more: false,
  };
  fetchFeedMock.mockResolvedValue(feedResponse);
  fetchPriceCardsMock.mockResolvedValue({
    items: initialItems,
    dispositions: {
      'event-42': 'updated',
      'futures-111': 'updated',
      'futures-221': 'updated',
      'futures-222': 'updated',
    },
    built_at: 1,
  });

  const container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root!.render(<CategoryPage params={{ slug: 'politics' }} />));
  await flush(50);

  expect(container.textContent).toContain('Alcaraz');
  expect(container.textContent).toContain('55.0%');
  expect(container.textContent).toContain('Single Politics Approval Market');
  expect(container.textContent).toContain('43%');
  expect(container.textContent).toContain('Fed Rate Cut Next Meeting');
  expect(container.textContent).toContain('2 sources');
  expect(container.textContent).toContain('42%');

  const eventStream = FakeEventSource.instances
    .filter((s) => s.url.startsWith('/api/events/42/stream') && !s.closed)
    .at(-1);
  expect(eventStream).toBeDefined();
  expect(eventStream!.url).toContain('preview_protocol=authority-v3');

  const marketStream = FakeEventSource.instances
    .filter((s) => s.url.startsWith('/api/markets/stream') && !s.closed)
    .at(-1);
  expect(marketStream).toBeDefined();
  expect(marketStream!.url).toContain('111');
  expect(marketStream!.url).toContain('221');
  expect(marketStream!.url).toContain('222');

  // 1. Live event authority-v3 preview
  eventStream!.emit('open');
  eventStream!.emit('preview_open_v3', wire(m.singleton_open));
  const tEvent0 = realHrtimeNs();
  eventStream!.emit(
    'preview_v3',
    wire({
      ...m.singleton_blend,
      frame: {
        ...m.singleton_blend.frame,
        event_id: 42,
        p: 0.62,
        p_away: 0.38,
        preview: { ...m.singleton_blend.frame.preview, seq: 1, base_rev: 10, ttl_ms: 10_000 },
      },
    }),
  );
  const dtEventMs = Number(realHrtimeNs() - tEvent0) / 1e6;
  console.info(`[capture:category-event-card] dt_ms=${dtEventMs.toFixed(2)}`);
  expect(dtEventMs).toBeLessThan(500);
  expect(container.textContent).toContain('62.0%');

  // 2. Single futures FeedCard market_preview
  marketStream!.emit('open');
  const tFeed0 = realHrtimeNs();
  marketStream!.emit(
    'market_preview',
    wire({
      type: 'market_preview',
      preview: true,
      market_id: 111,
      source: 'kalshi',
      outcomes: [
        { outcome_id: 70, p: 0.51, observed_at: T1 },
        { outcome_id: 71, p: 0.49, observed_at: T1 },
      ],
      seq: 5,
      ttl_ms: 10_000,
    }),
  );
  const dtFeedMs = Number(realHrtimeNs() - tFeed0) / 1e6;
  console.info(`[capture:category-feed-card] dt_ms=${dtFeedMs.toFixed(2)}`);
  expect(dtFeedMs).toBeLessThan(500);
  expect(container.textContent).toContain('51%');

  // 3. Multi-source CombinedFeedCard market_preview
  const tComb0 = realHrtimeNs();
  marketStream!.emit(
    'market_preview',
    wire({
      type: 'market_preview',
      preview: true,
      market_id: 221,
      source: 'kalshi',
      outcomes: [
        { outcome_id: 80, p: 0.68, observed_at: T1 },
        { outcome_id: 81, p: 0.32, observed_at: T1 },
      ],
      seq: 6,
      ttl_ms: 10_000,
    }),
  );
  const dtCombMs = Number(realHrtimeNs() - tComb0) / 1e6;
  console.info(`[capture:category-combined-card] dt_ms=${dtCombMs.toFixed(2)}`);
  expect(dtCombMs).toBeLessThan(500);
  expect(container.textContent).toContain('68%');
});
