/**
 * #10090 — League page (`/sport/[sport]/[league]`) projects live `authority-v3`
 * previews, `market_preview` updates (`LeagueMarketSection` & `LeagueBinaryBoard`),
 * and server-blended `fetchChampionshipGrid` invalidation refreshes in <= 0.5 s
 * without reload, while honoring #13509 (3-way draw guard) and #12506/#3868
 * settled immutability.
 */
import '../helpers/minimalDom';
import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import LeagueShowcasePage from '@/app/sport/[sport]/[league]/page';
import {
  fetchChampionshipGrid,
  fetchDiscoverPriceCards,
  fetchLeagueMarkets,
  fetchSportHierarchyDetail,
  type LeagueFuturesResponse,
  type LeagueGameBrief,
  type LeagueMarket,
} from '@/lib/api';
import { overlayLeagueGamePreview, overlayLeagueMarketPreview } from '@/lib/leaguePriceStream';
import type { BlendPreviewState } from '@/lib/blendPreview';
import type { ChampionshipGridResponse, FeedItem } from '@/lib/types';
import examples from '../../../docs/contracts/dnpl-authority-v3.examples.json';

jest.mock('next/navigation', () => ({
  useParams: () => ({ sport: 'basketball', league: 'nba' }),
}));

jest.mock('next/dynamic', () => () => function MockDynamic() {
  return null;
});

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

jest.mock('@/components/Analytics', () => ({
  useAnalyticsContext: () => ({ track: jest.fn() }),
}));

jest.mock('@/hooks', () => ({
  usePageTracking: jest.fn(),
  useScrollDepth: jest.fn(),
  useEngagementTime: jest.fn(),
  useAnalytics: () => ({ trackEventCardClick: jest.fn(), trackFuturesCardClick: jest.fn() }),
}));

jest.mock('@/lib/api', () => {
  const actual = jest.requireActual('@/lib/api');
  return {
    ...actual,
    API_URL: '',
    fetchSportHierarchyDetail: jest.fn(),
    fetchChampionshipGrid: jest.fn(),
    fetchLeagueMarkets: jest.fn(),
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

const hierarchyMock = fetchSportHierarchyDetail as jest.Mock;
const gridMock = fetchChampionshipGrid as jest.Mock;
const leagueMarketsMock = fetchLeagueMarkets as jest.Mock;
const priceCardsMock = fetchDiscoverPriceCards as jest.Mock;

const T0 = '2026-11-23T17:00:00Z';
const T1 = '2026-11-23T17:00:05Z';

const baseGame: LeagueGameBrief = {
  id: 42,
  home_team: 'Boston Celtics',
  away_team: 'Miami Heat',
  commence_time: '2026-11-23T16:00:00Z',
  status: 'live',
  sport: 'basketball_nba',
  home_score: 52,
  away_score: 48,
  home_win_probability: 0.55,
  current_odds: {
    home_probability: 0.55,
    away_probability: 0.45,
  },
};

const awardMarket: LeagueMarket = {
  id: 501,
  name: 'NBA MVP 2027',
  source: 'kalshi',
  market_tier: 1,
  category: 'nba',
  resolution_date: null,
  outcome_count: 3,
  canonical_market_key: null,
  section: 'awards',
  top_outcomes: [
    {
      id: 70,
      name: 'Nikola Jokic',
      probability: 0.41,
      opening_probability: 0.4,
      rank: 1,
      movement_24h: 0.01,
      team_id: null,
    },
    {
      id: 71,
      name: 'Shai Gilgeous-Alexander',
      probability: 0.35,
      opening_probability: 0.35,
      rank: 2,
      movement_24h: 0,
      team_id: null,
    },
    {
      id: 72,
      name: 'Luka Doncic',
      probability: 0.24,
      opening_probability: 0.25,
      rank: 3,
      movement_24h: -0.01,
      team_id: null,
    },
  ],
};

const binaryMarket: LeagueMarket = {
  id: 502,
  name: 'Will Boston win 60+ games?',
  source: 'kalshi',
  market_tier: 2,
  category: 'nba',
  resolution_date: null,
  outcome_count: 2,
  canonical_market_key: null,
  section: 'props',
  top_outcomes: [
    {
      id: 80,
      name: 'Yes',
      probability: 0.62,
      opening_probability: 0.6,
      rank: 1,
      movement_24h: 0.02,
      team_id: null,
    },
    {
      id: 81,
      name: 'No',
      probability: 0.38,
      opening_probability: 0.4,
      rank: 2,
      movement_24h: -0.02,
      team_id: null,
    },
  ],
};

const makeGrid = (prob: number): ChampionshipGridResponse => ({
  league: 'nba',
  name: 'NBA',
  season: '2026-27',
  championship_market_id: 901,
  columns: [
    {
      key: 'win_championship',
      label: 'Win Finals',
      order: 1,
      sequential: false,
      market_id: 901,
      market_ids: [901],
      resolved: false,
    },
  ],
  teams: [
    {
      name: 'Boston Celtics',
      short_name: 'BOS',
      team_id: 1,
      logo_url: null,
      primary_color: null,
      secondary_color: null,
      record: '14-2',
      conference: 'East',
      division: null,
      region: null,
      seed: 1,
      cells: {
        win_championship: {
          merged_probability: prob,
          sources: [{ source: 'kalshi', probability: prob }],
          trend_24h: null,
          state: 'live',
        },
      },
    },
  ],
  movers: [],
  trend_chart: { column: 'win_championship', top: 5, timeline: [] },
  grouped_teams: null,
  last_updated: T0,
  team_count: 1,
  sources_available: ['kalshi'],
});

let root: Root | undefined;
const flush = (ms = 0) => act(async () => { await jest.advanceTimersByTimeAsync(ms); });

beforeEach(() => {
  jest.useFakeTimers();
  FakeEventSource.instances = [];
  (globalThis as Record<string, unknown>).EventSource = FakeEventSource;
  const origCreate = document.createElement.bind(document);
  jest.spyOn(document, 'createElement').mockImplementation((tag: string, options?: ElementCreationOptions) => {
    const el = origCreate(tag, options);
    if (typeof (el as { getBoundingClientRect?: unknown }).getBoundingClientRect !== 'function') {
      (el as { getBoundingClientRect: () => DOMRect }).getBoundingClientRect = () =>
        ({ top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0, x: 0, y: 0, toJSON: () => ({}) }) as DOMRect;
    }
    return el;
  });
  hierarchyMock.mockReset();
  gridMock.mockReset();
  leagueMarketsMock.mockReset();
  priceCardsMock.mockReset();
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
});

afterEach(() => {
  if (root) {
    act(() => root!.unmount());
    root = undefined;
  }
  document.body.innerHTML = '';
  jest.restoreAllMocks();
  jest.useRealTimers();
});

test('#13509 & #12506/#3868: three-way soccer game refuses preview without p_away; finished game & settled outcome stay immutable', () => {
  const soccerGame: LeagueGameBrief & { blend_fold_revision: Record<string, number>; hero_probability_source: string } = {
    id: 42,
    home_team: 'Arsenal',
    away_team: 'Chelsea',
    commence_time: T0,
    status: 'live',
    sport: 'soccer_epl',
    home_score: 1,
    away_score: 1,
    home_win_probability: 0.44,
    current_odds: {
      home_probability: 0.44,
      away_probability: 0.28,
      draw_probability: 0.28,
    } as LeagueGameBrief['current_odds'],
    blend_fold_revision: { '42': 10 },
    hero_probability_source: 'blend',
  };
  const previewNoAway: BlendPreviewState = {
    eventId: 42,
    p: 0.51,
    pAway: null,
    sport: 'soccer_epl',
    status: 'live',
    baseRev: 10,
    epoch: 2,
    seq: 1,
    expiresAt: 99_999,
    observedAt: T1,
  };
  expect(overlayLeagueGamePreview(soccerGame, previewNoAway, 1_000)).toBe(soccerGame);

  const previewWithAway: BlendPreviewState = { ...previewNoAway, pAway: 0.24 };
  const patchedSoccer = overlayLeagueGamePreview(soccerGame, previewWithAway, 1_000);
  expect(patchedSoccer.home_win_probability).toBe(0.51);
  expect(patchedSoccer.current_odds?.away_probability).toBe(0.24);

  const finishedGame: LeagueGameBrief & { blend_fold_revision: Record<string, number>; hero_probability_source: string } = {
    ...baseGame,
    status: 'completed',
    blend_fold_revision: { '42': 10 },
    hero_probability_source: 'blend',
  };
  expect(overlayLeagueGamePreview(finishedGame, { ...previewWithAway, sport: 'basketball_nba' }, 1_000)).toBe(finishedGame);

  const settledMarket: LeagueMarket = {
    ...awardMarket,
    top_outcomes: awardMarket.top_outcomes.map((o, idx) =>
      idx === 0 ? { ...o, settled: true, is_winner: true } : o,
    ),
  };
  expect(
    overlayLeagueMarketPreview(
      settledMarket,
      {
        501: {
          source: 'kalshi',
          seq: 1,
          legs: { '70': { p: 0.99, observedAt: T1, expiresAt: 99_999 } },
        },
      },
      1_000,
    ),
  ).toBe(settledMarket);
});

test('/sport/[sport]/[league] re-prices LeagueGameRail, LeagueMarketSection, LeagueBinaryBoard, and championship grid in < 500 ms without reload', async () => {
  hierarchyMock.mockResolvedValue({
    slug: 'basketball',
    name: 'Basketball',
    leagues: [{ slug: 'nba', name: 'NBA', sport_keys: ['basketball_nba'], grid_slug: 'nba' }],
  });
  gridMock
    .mockResolvedValueOnce(makeGrid(0.25))
    .mockResolvedValueOnce(makeGrid(0.31));

  const envelope: LeagueFuturesResponse = {
    sport_key: 'basketball_nba',
    total_markets: 2,
    tier: 'full',
    sections: {
      awards: [awardMarket],
      props: [binaryMarket],
    },
    upcoming_games: [baseGame],
    recent_results: [],
    unreported_games: [],
  };
  leagueMarketsMock.mockResolvedValue(envelope);

  priceCardsMock.mockResolvedValue({
    items: [
      {
        type: 'event',
        data: {
          id: 42,
          external_id: 'evt-42',
          sport: 'basketball_nba',
          sport_name: 'NBA',
          home_team: 'Boston Celtics',
          away_team: 'Miami Heat',
          commence_time: baseGame.commence_time,
          status: 'live',
          home_score: 52,
          away_score: 48,
          current_odds: { home_probability: 0.55, away_probability: 0.45 },
          blend_fold_revision: { '42': 10 },
          hero_probability_source: 'blend',
          hero_probability_observed_at: T0,
          live_state: { period: 'Q3', game_clock: '06:12' },
        },
      } as unknown as FeedItem,
    ],
    dispositions: { 'event-42': 'updated' },
    built_at: 1,
  });

  const container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root!.render(<LeagueShowcasePage />));
  await flush(50);
  await flush(0);
  expect(priceCardsMock).toHaveBeenCalled();

  expect(container.textContent).toContain('Celtics');
  expect(container.textContent).toContain('55.0%');
  expect(container.textContent).toContain('MVP 2027');
  expect(container.textContent).toContain('41%');
  expect(container.textContent).toContain('Will Boston win 60+ games?');
  expect(container.textContent).toContain('62%');
  expect(container.textContent).toContain('Boston Celtics14-225%');

  const gameStream = FakeEventSource.instances
    .filter((s) => s.url.startsWith('/api/events/42/stream') && !s.closed)
    .at(-1);
  expect(gameStream).toBeDefined();
  expect(gameStream!.url).toContain('preview_protocol=authority-v3');

  const marketStream = FakeEventSource.instances
    .filter((s) => s.url.startsWith('/api/markets/stream') && !s.closed)
    .at(-1);
  expect(marketStream).toBeDefined();
  expect(marketStream!.url).toContain('501');
  expect(marketStream!.url).toContain('502');
  expect(marketStream!.url).toContain('901');

  // 1. Live game authority-v3 preview
  gameStream!.emit('open');
  gameStream!.emit('preview_open_v3', wire(m.singleton_open));
  const tGame0 = realHrtimeNs();
  gameStream!.emit(
    'preview_v3',
    wire({
      ...m.singleton_blend,
      frame: {
        ...m.singleton_blend.frame,
        event_id: 42,
        sport: 'basketball_nba',
        p: 0.67,
        p_away: 0.33,
        preview: { ...m.singleton_blend.frame.preview, seq: 1, base_rev: 10, ttl_ms: 10_000 },
      },
    }),
  );
  const dtGameMs = Number(realHrtimeNs() - tGame0) / 1e6;
  console.info(`[capture:league-game-rail] dt_ms=${dtGameMs.toFixed(2)}`);
  expect(dtGameMs).toBeLessThan(500);
  expect(container.textContent).toContain('67.0%');

  // 2. Section market_preview (AwardCard)
  marketStream!.emit('open');
  const tSec0 = realHrtimeNs();
  marketStream!.emit(
    'market_preview',
    wire({
      type: 'market_preview',
      preview: true,
      market_id: 501,
      source: 'kalshi',
      outcomes: [{ outcome_id: 70, p: 0.54, observed_at: T1 }],
      seq: 5,
      ttl_ms: 10_000,
    }),
  );
  const dtSecMs = Number(realHrtimeNs() - tSec0) / 1e6;
  console.info(`[capture:league-market-section] dt_ms=${dtSecMs.toFixed(2)}`);
  expect(dtSecMs).toBeLessThan(500);
  expect(container.textContent).toContain('54%');

  // 3. Binary board market_preview (LeagueBinaryBoard)
  const tBin0 = realHrtimeNs();
  marketStream!.emit(
    'market_preview',
    wire({
      type: 'market_preview',
      preview: true,
      market_id: 502,
      source: 'kalshi',
      outcomes: [{ outcome_id: 80, p: 0.74, observed_at: T1 }],
      seq: 6,
      ttl_ms: 10_000,
    }),
  );
  const dtBinMs = Number(realHrtimeNs() - tBin0) / 1e6;
  console.info(`[capture:league-binary-board] dt_ms=${dtBinMs.toFixed(2)}`);
  expect(dtBinMs).toBeLessThan(500);
  expect(container.textContent).toContain('74%');

  // 4. Championship grid market invalidation triggers server-blended grid refresh
  const tGrid0 = realHrtimeNs();
  marketStream!.emit(
    'market',
    wire({ market_id: 901, terminal: false, invalidation: true }),
  );
  await flush(10);
  const dtGridMs = Number(realHrtimeNs() - tGrid0) / 1e6;
  console.info(`[capture:league-championship-grid] dt_ms=${dtGridMs.toFixed(2)}`);
  expect(dtGridMs).toBeLessThan(500);
  expect(gridMock).toHaveBeenCalledTimes(2);
  expect(container.textContent).toContain('Boston Celtics14-231%');
});
