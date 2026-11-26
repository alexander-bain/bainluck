/**
 * #10090 — Set pages (`/collections/[slug]` machinery & paired-metric cards +
 * `/event/[domain]/[slug]` concept pages) project live `market_preview` /
 * `authority-v3` overlays and server-blended invalidation refreshes in <= 0.5 s
 * without reload, while honoring #13509 (3-way soccer guard), settled
 * immutability, and visualForms Rule #1 (no client-side multi-venue blending).
 */
import '../helpers/minimalDom';
import { quarantinedTimingTest } from '../helpers/timingQuarantine';
import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import CollectionHub from '@/components/collections/CollectionHub';
import EventConceptPage from '@/app/event/[domain]/[slug]/page';
import {
  fetchDiscoverPriceCards,
  fetchEventConcept,
  fetchPairedMetricsByCeremony,
} from '@/lib/api';
import {
  applyEventConceptLivePrices,
  patchConceptMatchupChild,
} from '@/lib/eventConceptStream';
import { patchMachineryVisualBlock } from '@/lib/machineryVisualBlockPatch';
import { pairedMetricSetMarketIds } from '@/lib/pairedMetricStream';
import type { CollectionHub as Hub, CollectionMember } from '@/lib/collections';
import type { BlendPreviewState } from '@/lib/blendPreview';
import type { PairedMetricSet } from '@/lib/discover/visualForms';
import type { EventConceptResponse, FeedFuturesData, FeedItem } from '@/lib/types';
import examples from '../../../docs/contracts/dnpl-authority-v3.examples.json';

let mockRouteParams: Record<string, string> = { domain: 'soccer', slug: 'wc-10090' };

jest.mock('next/navigation', () => ({
  useParams: () => mockRouteParams,
  useRouter: () => ({ replace: jest.fn(), push: jest.fn() }),
}));

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

jest.mock('@/components/event/WinnerEvolutionChart', () => () => null);
jest.mock('@/components/event/RaceToTitleChart', () => () => null);
jest.mock('@/components/event/SettledPathChart', () => () => null);

jest.mock('@/lib/api', () => {
  const actual = jest.requireActual('@/lib/api');
  return {
    ...actual,
    API_URL: '',
    fetchDiscoverPriceCards: jest.fn(),
    fetchPairedMetricsByCeremony: jest.fn(),
    fetchEventConcept: jest.fn(),
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

class FakeIntersectionObserver {
  constructor(private cb: (entries: { isIntersecting: boolean }[]) => void) {}
  observe = () => {
    this.cb([{ isIntersecting: true }]);
  };
  unobserve = () => {};
  disconnect = () => {};
}

const wire = JSON.stringify;
const realHrtimeNs = process.hrtime.bigint.bind(process.hrtime);
const m = examples.messages;
const priceCardsMock = fetchDiscoverPriceCards as jest.Mock;
const pairedMetricsMock = fetchPairedMetricsByCeremony as jest.Mock;
const conceptMock = fetchEventConcept as jest.Mock;

const T0 = '2026-11-23T17:00:00Z';
const T1 = '2026-11-23T17:00:05Z';

let root: Root | undefined;
const flush = (ms = 0) => act(async () => { await jest.advanceTimersByTimeAsync(ms); });

beforeEach(() => {
  jest.useFakeTimers();
  FakeEventSource.instances = [];
  (globalThis as Record<string, unknown>).EventSource = FakeEventSource;
  (globalThis as Record<string, unknown>).IntersectionObserver = FakeIntersectionObserver;
  const origCreate = document.createElement.bind(document);
  jest.spyOn(document, 'createElement').mockImplementation((tag: string, options?: ElementCreationOptions) => {
    const el = origCreate(tag, options);
    if (typeof (el as { getBoundingClientRect?: unknown }).getBoundingClientRect !== 'function') {
      (el as { getBoundingClientRect: () => DOMRect }).getBoundingClientRect = () =>
        ({ top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0, x: 0, y: 0, toJSON: () => ({}) }) as DOMRect;
    }
    return el;
  });
  window.scrollTo = jest.fn();
  if (typeof document.querySelector !== 'function') {
    (document as unknown as { querySelector: () => null }).querySelector = () => null;
  }
  if (!document.head) {
    Object.defineProperty(document, 'head', { configurable: true, value: document.createElement('head') });
  }
  priceCardsMock.mockReset();
  pairedMetricsMock.mockReset();
  conceptMock.mockReset();
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

const makePairedSet = (winProb: number): PairedMetricSet => ({
  set_id: 'oscars-best-picture',
  category: 'entertainment',
  kicker: 'Oscars',
  title: 'Best Picture',
  subtitle: 'Nominated % beside Wins %',
  stage_1_label: 'Nominated',
  stage_2_label: 'Wins',
  stage_1_settled_yes_label: 'Nominated',
  stage_1_settled_no_label: 'Not nominated',
  stage_1_settled: false,
  stage_2_settled: false,
  stage_1_market: {
    id: 601,
    source: 'kalshi',
    name: 'Best Picture Nominees',
    companion_polymarket_id: 602,
  },
  stage_2_market: {
    id: 603,
    source: 'kalshi',
    name: 'Best Picture Winner',
  },
  never_blend: true,
  blend_authority: 'server:futures_source_merge.blend_with_verdict',
  as_of: T0,
  entries: [
    {
      subject_key: 'film-a',
      subject: 'Hamnet',
      detail: 'Drama',
      stage_1_market_id: 601,
      stage_1_outcome: 'Hamnet',
      stage_1_probability: 0.8,
      stage_1_blend_authority: 'server:futures_source_merge.blend_with_verdict',
      stage_1_settled_state: null,
      stage_2_market_id: 603,
      stage_2_outcome: 'Hamnet',
      stage_2_probability: winProb,
      stage_2_blend_authority: 'single_venue',
      art: null,
    },
  ],
});

test('pairedMetricSetMarketIds, patchMachineryVisualBlock, and applyEventConceptLivePrices honor guards', () => {
  const ps = makePairedSet(0.31);
  expect(pairedMetricSetMarketIds([ps])).toEqual([601, 602, 603]);
  expect(
    pairedMetricSetMarketIds([{ ...ps, stage_1_settled: true, stage_2_settled: true }]),
  ).toEqual([]);

  const blockPatched = patchMachineryVisualBlock(
    {
      form_id: 'sibling_fields_grid',
      items: [
        {
          market_id: 501,
          title: 'Director',
          outcomes: [{ outcome_id: 70, name: 'Chloé Zhao', probability: 0.41, rendered_percent: 41, art: {} as never }],
        },
      ],
    },
    new Map([
      [
        'futures-501',
        {
          type: 'futures',
          data: {
            id: 501,
            status: 'open',
            top_outcomes: [{ id: 70, name: 'Chloé Zhao', probability: 0.58 }],
          },
        } as unknown as FeedItem,
      ],
    ]),
  );
  expect((blockPatched.items?.[0].outcomes as { rendered_percent: number }[])[0].rendered_percent).toBe(58);

  // #13601 (1): coin_flip_matchups prefers served rendered percents and otherwise uses
  // renderedDuelPercents so 0.505/0.495 prints 51% & 49% (sum 100), never 51% & 50%.
  for (const [homeProb, awayProb, expHome, expAway] of [
    [0.505, 0.495, 51, 49],
    [0.495, 0.505, 49, 51],
    [0.515, 0.485, 52, 48],
    [0.525, 0.475, 53, 47],
  ] as const) {
    const unservedMatchup = patchMachineryVisualBlock(
      {
        form_id: 'coin_flip_matchups',
        items: [{ event_id: 901, home_pct: 50, away_pct: 50 }],
      },
      new Map([
        [
          'event-901',
          {
            type: 'event',
            data: {
              id: 901,
              status: 'scheduled',
              sport: 'basketball_nba',
              current_odds: { home_probability: homeProb, away_probability: awayProb },
            },
          } as unknown as FeedItem,
        ],
      ]),
    );
    const row = unservedMatchup.items?.[0] as { home_pct: number; away_pct: number };
    expect(row.home_pct).toBe(expHome);
    expect(row.away_pct).toBe(expAway);
    expect(row.home_pct + row.away_pct).toBe(100);
  }

  const servedMatchup = patchMachineryVisualBlock(
    {
      form_id: 'coin_flip_matchups',
      items: [{ event_id: 902, home_pct: 50, away_pct: 50 }],
    },
    new Map([
      [
        'event-902',
        {
          type: 'event',
          data: {
            id: 902,
            status: 'scheduled',
            sport: 'basketball_nba',
            current_odds: {
              home_probability: 0.505,
              away_probability: 0.495,
              home_rendered_percent: 51,
              away_rendered_percent: 49,
            },
          },
        } as unknown as FeedItem,
      ],
    ]),
  );
  const servedRow = servedMatchup.items?.[0] as { home_pct: number; away_pct: number };
  expect(servedRow.home_pct).toBe(51);
  expect(servedRow.away_pct).toBe(49);

  // #13601 (2): patchVisualOutcomes and probability_history_chart use server
  // rendered_percent when present (#11995) and round locally only on provisional frames.
  const serverPercentOutcomes = patchMachineryVisualBlock(
    {
      form_id: 'sibling_fields_grid',
      items: [
        {
          market_id: 502,
          title: 'Confirmed vs Provisional',
          outcomes: [
            { outcome_id: 80, name: 'Candidate A', probability: 0.34, rendered_percent: 34, art: {} as never },
            { outcome_id: 81, name: 'Candidate B', probability: 0.4, rendered_percent: 40, art: {} as never },
          ],
        },
      ],
    },
    new Map([
      [
        'futures-502',
        {
          type: 'futures',
          data: {
            id: 502,
            status: 'open',
            top_outcomes: [
              { id: 80, name: 'Candidate A', probability: 0.34, rendered_percent: 33 },
              { id: 81, name: 'Candidate B', probability: 0.44, rendered_percent: null },
            ],
          },
        } as unknown as FeedItem,
      ],
    ]),
  );
  const patchedOuts = serverPercentOutcomes.items?.[0].outcomes as { rendered_percent: number }[];
  expect(patchedOuts[0].rendered_percent).toBe(33);
  expect(patchedOuts[1].rendered_percent).toBe(44);

  const chartPatched = patchMachineryVisualBlock(
    {
      form_id: 'probability_history_chart',
      items: [
        {
          market_id: 503,
          series: [
            { outcome_id: 90, current_pct: 34 },
            { outcome_id: 91, current_pct: 40 },
          ],
        },
      ],
    },
    new Map([
      [
        'futures-503',
        {
          type: 'futures',
          data: {
            id: 503,
            status: 'open',
            top_outcomes: [
              { id: 90, name: 'Confirmed', probability: 0.34, rendered_percent: 33 },
              { id: 91, name: 'Provisional', probability: 0.46, rendered_percent: null },
            ],
          },
        } as unknown as FeedItem,
      ],
    ]),
  );
  const patchedSeries = chartPatched.items?.[0].series as { current_pct: number }[];
  expect(patchedSeries[0].current_pct).toBe(33);
  expect(patchedSeries[1].current_pct).toBe(46);

  // #13509: soccer matchup rejects preview without p_away; adopts when p_away present
  const soccerChild = {
    kind: 'matchup' as const,
    event_id: 42,
    status: 'live',
    home: { name: 'Spain', probability: 0.45, score: 1 },
    away: { name: 'Brazil', probability: 0.25, score: 0 },
    blend_fold_revision: { '42': 10 },
    hero_probability_source: 'blend',
  };
  const noAwayPreview: BlendPreviewState = {
    eventId: 42,
    p: 0.58,
    pAway: null,
    sport: 'soccer',
    status: 'live',
    baseRev: 10,
    epoch: 2,
    seq: 1,
    expiresAt: 99_999,
    observedAt: T1,
  };
  expect(patchConceptMatchupChild(soccerChild, 'soccer', new Map(), noAwayPreview, 1_000)).toBe(soccerChild);
  const patchedChild = patchConceptMatchupChild(
    soccerChild,
    'soccer',
    new Map(),
    { ...noAwayPreview, pAway: 0.22 },
    1_000,
  );
  expect(patchedChild.home?.probability).toBe(0.58);
  expect(patchedChild.away?.probability).toBe(0.22);

  // Settled concept ignores overlays
  const settledConcept = {
    event: { key: 'event:soccer:wc-settled', domain: 'soccer', name: 'Final', status: 'settled' as const },
    primary: { kind: 'winner_field' as const, label: 'Winner', competitors: [], evolution_market_id: 701 },
    sections: [],
    children: [soccerChild],
    movers: [],
  } as unknown as EventConceptResponse;
  expect(
    applyEventConceptLivePrices(
      settledConcept,
      new Map(),
      { 42: { ...noAwayPreview, pAway: 0.22 } },
      1_000,
      {},
      1_000,
    ),
  ).toBe(settledConcept);
});

quarantinedTimingTest(
  'frontend/__tests__/lib/setPagesLiveReprice10090.test.tsx',
  'CollectionHub machinery section (market_preview) and AwardCategoryPairedCard (server invalidation) re-price in < 500 ms',
  async () => {
  const futuresItem: FeedItem = {
    type: 'futures',
    data: {
      id: 501,
      name: 'Best Director',
      source: 'kalshi',
      status: 'open',
      display_scale: 1,
      price_observed_at: T0,
      outcome_observed_at: { '70': T0 },
      top_outcomes: [{ id: 70, name: 'Chloé Zhao', probability: 0.41, rendered_percent: 41 }],
    } as unknown as FeedFuturesData,
  } as unknown as FeedItem;

  const member: CollectionMember = {
    key: 'market:501',
    id: 501,
    type: 'market',
    href: '/futures/501',
    item: futuresItem,
    questionIds: [],
    eventId: null,
  };

  const machineryHub: Hub = {
    slug: 'machinery-set-10090',
    title: 'Oscars Preview Set',
    edition: null,
    state: 'published',
    revision: 1,
    note: null,
    dek: null,
    family: null,
    theme: null,
    children: [],
    sections: [
      {
        key: 'sec-1',
        cls: 'unclassified',
        title: 'Directing',
        note: null,
        visualBlock: {
          form_id: 'sibling_fields_grid',
          items: [
            {
              market_id: 501,
              title: 'Best Director',
              href: '/futures/501',
              outcomes: [
                {
                  outcome_id: 70,
                  name: 'Chloé Zhao',
                  probability: 0.41,
                  rendered_percent: 41,
                  art: {} as never,
                },
              ],
            },
          ],
        },
        members: [member],
      },
    ],
    members: [member],
    related: {},
  };

  priceCardsMock.mockResolvedValue({
    items: [futuresItem],
    dispositions: { 'futures-501': 'updated' },
    built_at: 1,
  });

  const container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root!.render(<CollectionHub slug="machinery-set-10090" initialHub={machineryHub} />));
  await flush(10);

  expect(container.textContent).toContain('Chloé Zhao');
  expect(container.textContent).toContain('41%');

  const mktStream = FakeEventSource.instances
    .filter((s) => s.url.startsWith('/api/markets/stream') && s.url.includes('501') && !s.closed)
    .at(-1);
  expect(mktStream).toBeDefined();

  mktStream!.emit('open');
  const tMach0 = realHrtimeNs();
  mktStream!.emit(
    'market_preview',
    wire({
      type: 'market_preview',
      preview: true,
      market_id: 501,
      source: 'kalshi',
      outcomes: [{ outcome_id: 70, p: 0.58, observed_at: T1 }],
      seq: 5,
      ttl_ms: 10_000,
    }),
  );
  const dtMachMs = Number(realHrtimeNs() - tMach0) / 1e6;
  console.info(`[capture:collection-machinery] dt_ms=${dtMachMs.toFixed(2)}`);
  expect(dtMachMs).toBeLessThan(500);
  expect(container.textContent).toContain('58%');

  // Switch to Oscars paired-metrics hub (multi-venue companion_polymarket_id 602)
  act(() => root!.unmount());
  FakeEventSource.instances = [];
  pairedMetricsMock
    .mockResolvedValueOnce({ sets: [makePairedSet(0.31)] })
    .mockResolvedValueOnce({ sets: [makePairedSet(0.49)] });

  const oscarsHub: Hub = {
    slug: 'oscars-2027',
    title: '99th Oscars',
    edition: null,
    state: 'published',
    revision: 1,
    note: null,
    dek: null,
    family: null,
    theme: null,
    children: [],
    sections: [],
    members: [],
    related: {},
  };
  root = createRoot(container);
  act(() => root!.render(<CollectionHub slug="oscars-2027" initialHub={oscarsHub} />));
  await flush(10);

  expect(container.textContent).toContain('Hamnet');
  expect(container.textContent).toContain('31%');

  const pairedStream = FakeEventSource.instances
    .filter((s) => s.url.startsWith('/api/markets/stream') && s.url.includes('602') && !s.closed)
    .at(-1);
  expect(pairedStream).toBeDefined();
  const tPaired0 = realHrtimeNs();
  pairedStream!.emit('market', wire({ market_id: 602, terminal: false, invalidation: true }));
  await flush(0);
  const dtPairedMs = Number(realHrtimeNs() - tPaired0) / 1e6;
  console.info(`[capture:collection-paired-set] dt_ms=${dtPairedMs.toFixed(2)}`);
  expect(dtPairedMs).toBeLessThan(500);
  expect(pairedMetricsMock).toHaveBeenCalledTimes(2);
  expect(container.textContent).toContain('49%');

  // Burst protection: rapid follow-up invalidation at +2s stays debounced under the 10s floor until +10s.
  pairedMetricsMock.mockResolvedValueOnce({ sets: [makePairedSet(0.52)] });
  pairedStream!.emit('market', wire({ market_id: 602, terminal: false, invalidation: true }));
  await flush(2_000);
  expect(pairedMetricsMock).toHaveBeenCalledTimes(2);
  await flush(8_000);
  expect(pairedMetricsMock).toHaveBeenCalledTimes(3);
  expect(container.textContent).toContain('52%');
});

test('/event/[domain]/[slug] re-prices matchup children (authority-v3), evolution leaderboard (market_preview), and envelope refresh in < 500 ms', async () => {
  mockRouteParams = { domain: 'soccer', slug: 'wc-10090' };

  const makeConcept = (brazilWinProb: number, spainProb = 0.45): EventConceptResponse => ({
    event: {
      key: 'event:soccer:wc-10090',
      slug: 'wc-10090',
      domain: 'soccer',
      name: 'World Cup Test',
      status: 'live',
    },
    primary: {
      kind: 'winner_field',
      label: 'Winner',
      evolution_market_id: 701,
      competitors: [
        { name: 'Brazil', probability: brazilWinProb, outcome_id: 7001 },
        { name: 'Spain', probability: 0.2, outcome_id: 7002 },
      ],
    },
    sections: [],
    children: [
      {
        kind: 'matchup',
        event_id: 42,
        status: 'live',
        commence_time: T0,
        home: { name: 'Spain', probability: spainProb, score: 1 },
        away: { name: 'Brazil', probability: 0.25, score: 0 },
      },
    ],
    movers: [],
  });

  conceptMock
    .mockResolvedValueOnce(makeConcept(0.28))
    .mockResolvedValueOnce(makeConcept(0.39));

  priceCardsMock.mockResolvedValue({
    items: [
      {
        type: 'event',
        data: {
          id: 42,
          external_id: 'evt-42',
          sport: 'soccer',
          home_team: 'Spain',
          away_team: 'Brazil',
          commence_time: T0,
          status: 'live',
          home_score: 1,
          away_score: 0,
          current_odds: { home_probability: 0.45, away_probability: 0.25, draw_probability: 0.3 },
          blend_fold_revision: { '42': 10, '43': 20 },
          hero_probability_source: 'blend',
          hero_probability_observed_at: T0,
          live_state: { period: '2H', game_clock: '72:00' },
        },
      } as unknown as FeedItem,
    ],
    dispositions: { 'event-42': 'updated' },
    built_at: 1,
  });

  const container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root!.render(<EventConceptPage />));
  await flush(50);
  await flush(0);
  expect(priceCardsMock).toHaveBeenCalled();

  expect(container.textContent).toContain('28%');
  expect(container.textContent).toContain('45%');

  const evStream = FakeEventSource.instances
    .filter((s) => s.url.startsWith('/api/events/42/stream?preview_protocol=authority-v3') && !s.closed)
    .at(-1);
  expect(evStream).toBeDefined();

  evStream!.emit('open');
  evStream!.emit('preview_open_v3', wire(m.folded_open));
  // #13509: folded frame on soccer matchup with p_away: null must NOT fabricate 1 - p.
  evStream!.emit(
    'preview_v3',
    wire({
      ...m.folded_blend,
      frame: {
        ...m.folded_blend.frame,
        event_id: 42,
        sport: 'soccer',
        p: 0.58,
        p_away: null,
        preview: {
          ...m.folded_blend.frame.preview,
          fold_seq: 1,
          ttl_ms: 10_000,
          origin_authority: {
            '42': { epoch: 2, seq: 1, state: 'pending', ttl_ms: 10_000 },
            '43': { epoch: 3, seq: 1, state: 'pending', ttl_ms: 10_000 },
          },
        },
      },
    }),
  );
  expect(container.textContent).toContain('45%');
  expect(container.textContent).toContain('25%');

  const tMatch0 = realHrtimeNs();
  evStream!.emit(
    'preview_v3',
    wire({
      ...m.folded_blend,
      frame: {
        ...m.folded_blend.frame,
        event_id: 42,
        sport: 'soccer',
        p: 0.58,
        p_away: 0.22,
        preview: {
          ...m.folded_blend.frame.preview,
          fold_seq: 2,
          ttl_ms: 10_000,
          origin_authority: {
            '42': { epoch: 2, seq: 2, state: 'pending', ttl_ms: 10_000 },
            '43': { epoch: 3, seq: 1, state: 'pending', ttl_ms: 10_000 },
          },
        },
      },
    }),
  );
  const dtMatchMs = Number(realHrtimeNs() - tMatch0) / 1e6;
  console.info(`[capture:event-concept-matchup] dt_ms=${dtMatchMs.toFixed(2)}`);
  expect(dtMatchMs).toBeLessThan(500);
  expect(container.textContent).toContain('58%');
  expect(container.textContent).toContain('22%');

  const mktStream = FakeEventSource.instances
    .filter((s) => s.url.startsWith('/api/markets/stream') && s.url.includes('701') && !s.closed)
    .at(-1);
  expect(mktStream).toBeDefined();
  mktStream!.emit('open');
  const tEvo0 = realHrtimeNs();
  mktStream!.emit(
    'market_preview',
    wire({
      type: 'market_preview',
      preview: true,
      market_id: 701,
      source: 'kalshi',
      outcomes: [{ outcome_id: 7001, p: 0.36, observed_at: T1 }],
      seq: 5,
      ttl_ms: 10_000,
    }),
  );
  const dtEvoMs = Number(realHrtimeNs() - tEvo0) / 1e6;
  console.info(`[capture:event-concept-preview] dt_ms=${dtEvoMs.toFixed(2)}`);
  expect(dtEvoMs).toBeLessThan(500);
  expect(container.textContent).toContain('36%');

  const tRef0 = realHrtimeNs();
  mktStream!.emit('market', wire({ market_id: 701, terminal: false, invalidation: true }));
  await flush(0);
  const dtRefMs = Number(realHrtimeNs() - tRef0) / 1e6;
  console.info(`[capture:event-concept-refresh] dt_ms=${dtRefMs.toFixed(2)}`);
  expect(dtRefMs).toBeLessThan(500);
  expect(conceptMock).toHaveBeenCalledTimes(2);
  expect(container.textContent).toContain('39%');
});
