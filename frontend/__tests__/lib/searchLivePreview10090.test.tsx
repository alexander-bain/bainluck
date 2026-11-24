/**
 * #10090 — Search game cards, flat market cards, and family cards re-price
 * within <= 0.5 s of receipt without a reload (authority-v3 + market_preview).
 */
import '../helpers/minimalDom';
import React, { act, useMemo } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import {
  overlaySearchEventPreview,
  searchEventStreamable,
} from '@/lib/searchEventsStream';
import {
  overlaySearchMarketPreview,
  patchSearchFamilies,
  searchAnswerMarkets,
} from '@/lib/searchFuturesStream';
import { useSearchPriceStream } from '@/hooks/useSearchPriceStream';
import { fetchDiscoverPriceCards } from '@/lib/api';
import { overlayBlendPreview, type BlendPreviewState } from '@/lib/blendPreview';
import { applyMarketPreview } from '@/lib/discover/marketPreview';
import type { Event, FeedItem, FuturesFamily, FuturesMarket, FuturesOutcome } from '@/lib/types';
import examples from '../../../docs/contracts/dnpl-authority-v3.examples.json';

jest.mock('next/link', () => {
  const ReactLib = require('react');
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement('a', { href, ...props }, children),
  };
});

jest.mock('@/hooks', () => ({
  useAnalytics: () => ({ trackEventCardClick: jest.fn(), trackFuturesCardClick: jest.fn() }),
}));

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

jest.mock('@/lib/api', () => {
  const actual = jest.requireActual('@/lib/api');
  return {
    ...actual,
    API_URL: '',
    fetchDiscoverPriceCards: jest.fn(),
  };
});

import EventCard from '@/components/EventCard';
import FuturesCard from '@/components/FuturesCard';
import SearchFamilyCard from '@/components/SearchFamilyCard';

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
const fetchCardsMock = fetchDiscoverPriceCards as jest.Mock;
const realHrtimeNs = process.hrtime.bigint.bind(process.hrtime);
const m = examples.messages;

const makeOutcome = (id: number, name: string, probability: number | null): FuturesOutcome =>
  ({
    id,
    name,
    probability,
    american_odds: null,
    rank: 1,
    rank_change_24h: null,
    probability_change_24h: null,
    movement: null,
    opening_probability: null,
    opening_american_odds: null,
    is_winner: null,
  }) as FuturesOutcome;

const makeMarket = (
  id: number,
  name: string,
  rows: FuturesOutcome[],
  over: Partial<FuturesMarket> = {},
): FuturesMarket =>
  ({
    id,
    name,
    description: null,
    sport: null,
    sport_name: null,
    category: 'politics',
    llm_sport_category: 'politics',
    status: 'open',
    source: 'kalshi',
    external_id: `KX-${id}`,
    mutually_exclusive: true,
    commence_time: null,
    resolution_date: null,
    outcome_count: rows.length,
    created_at: null,
    updated_at: null,
    top_outcomes: rows,
    ...over,
  }) as FuturesMarket;

const makeEvent = (over: Partial<Event> = {}): Event =>
  ({
    id: 42,
    external_id: 'x42',
    sport: 'tennis_atp',
    home_team: 'Carlos Alcaraz',
    away_team: 'Jannik Sinner',
    commence_time: '2026-10-25T16:00:00Z',
    status: 'live',
    home_score: 1,
    away_score: 1,
    current_odds: {
      home_probability: 0.55,
      away_probability: 0.45,
      home_rendered_percent: 55,
      away_rendered_percent: 45,
    } as Event['current_odds'],
    hero_probability: 0.55,
    hero_probability_away: 0.45,
    espn: { period: '2nd Set', game_clock: '4-4' },
    ...over,
  }) as Event;

test('#13509: three-way soccer game refuses preview without p_away; two-way adopts 1 - p', () => {
  const blendState: BlendPreviewState = {
    eventId: 42,
    epoch: 1,
    seq: 2,
    baseRev: 10,
    p: 0.68,
    status: 'live',
    expiresAt: 5000,
    sport: 'basketball_nba',
  };
  const nbaEvent = makeEvent({
    sport: 'basketball_nba',
    hero_probability_source: 'blend',
    blend_fold_revision: { '42': 10 },
  } as Partial<Event>);
  const patchedNba = overlaySearchEventPreview(nbaEvent, blendState, 100);
  expect(patchedNba.hero_probability).toBe(0.68);
  expect(patchedNba.hero_probability_away).toBeCloseTo(0.32, 6);

  const soccerEvent = makeEvent({
    sport: 'soccer_epl',
    hero_probability_source: 'blend',
    blend_fold_revision: { '42': 10 },
  } as Partial<Event>);
  const soccerState: BlendPreviewState = { ...blendState, sport: 'soccer_epl', pAway: null };
  // Never fabricate 1 - p when draw-priced game lacks pAway
  expect(overlaySearchEventPreview(soccerEvent, soccerState, 100)).toBe(soccerEvent);

  const completed = makeEvent({ status: 'completed' });
  expect(overlaySearchEventPreview(completed, blendState, 100)).toBe(completed);
  expect(overlayBlendPreview).toBeDefined();
});

test('overlaySearchMarketPreview overlays newer previews and ignores older/null/settled rows', () => {
  const mkt = makeMarket(501, 'Next Fed Chair?', [makeOutcome(70, 'Kevin Warsh', 0.4)]);
  const previews = applyMarketPreview(
    {},
    {
      market_id: 501,
      source: 'kalshi',
      outcomes: [{ outcome_id: 70, p: 0.52, observed_at: '2026-11-24T08:00:05Z' }],
      seq: 1,
      ttl_ms: 10_000,
    },
    100,
  );
  expect(overlaySearchMarketPreview(mkt, previews, 200).top_outcomes![0].probability).toBe(0.52);

  const settled = makeMarket(501, 'Next Fed Chair?', [makeOutcome(70, 'Kevin Warsh', 1.0)], {
    status: 'resolved',
  });
  expect(overlaySearchMarketPreview(settled, previews, 200)).toBe(settled);
});

describe('timed DOM captures for Search cards (< 0.5 s from SSE receipt)', () => {
  const origEventSource = global.EventSource;
  let root: Root | undefined;
  let container: HTMLElement | undefined;

  beforeEach(() => {
    FakeEventSource.instances = [];
    fetchCardsMock.mockReset();
    (global as unknown as { EventSource: typeof EventSource }).EventSource =
      FakeEventSource as unknown as typeof EventSource;
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2026-10-25T17:00:00Z'));
  });

  afterEach(() => {
    if (root) act(() => root!.unmount());
    root = undefined;
    if (container && container.parentNode) container.parentNode.removeChild(container);
    container = undefined;
    (global as unknown as { EventSource: typeof EventSource }).EventSource = origEventSource;
    jest.useRealTimers();
  });

  function Harness({
    futures,
    families,
    events,
  }: {
    futures: FuturesMarket[];
    families: FuturesFamily[];
    events: Event[];
  }) {
    const answerMarkets = useMemo(
      () => searchAnswerMarkets(futures, families),
      [futures, families],
    );
    const { patchMarket, patchEvent } = useSearchPriceStream(answerMarkets, events);
    const liveEvents = events.map(patchEvent);
    const liveFutures = futures.map(patchMarket);
    const liveFamilies = patchSearchFamilies(families, patchMarket);
    return (
      <div>
        <div data-area="events">
          {liveEvents.map((e) => (
            <EventCard key={e.id} event={e} sourceSection="search_results" />
          ))}
        </div>
        <div data-area="futures">
          {liveFutures.map((mkt) => (
            <FuturesCard key={mkt.id} market={mkt} />
          ))}
        </div>
        <div data-area="families">
          {liveFamilies.map((fam) => (
            <SearchFamilyCard key={fam.family_key} family={fam} />
          ))}
        </div>
      </div>
    );
  }

  test('Search game card (authority-v3), flat futures card, and family card re-price in < 500 ms', async () => {
    const game = makeEvent();
    const flat = makeMarket(501, 'Who wins the flat market?', [
      makeOutcome(70, 'Alpha', 0.4),
      makeOutcome(71, 'Beta', 0.6),
    ]);
    const head = makeMarket(502, 'Fed Rate Cut 2027?', [
      makeOutcome(80, 'Yes', 0.35),
      makeOutcome(81, 'No', 0.65),
    ]);
    const member = makeMarket(503, 'Fed Chair Nominee?', [
      makeOutcome(90, 'Kevin Warsh', 0.25),
    ]);
    const fam: FuturesFamily = {
      family_key: 'fed-2027',
      label: 'Federal Reserve',
      headline: head,
      members: [member],
      more_count: 0,
      member_count: 2,
    };

    const initialPriceCards = {
      built_at: 1,
      dispositions: {
        'event-42': 'updated',
        'futures-501': 'updated',
        'futures-502': 'updated',
        'futures-503': 'updated',
      },
      items: [
        {
          type: 'event',
          data: {
            id: 42,
            status: 'live',
            home_score: 1,
            away_score: 1,
            current_odds: {
              home_probability: 0.55,
              away_probability: 0.45,
              home_rendered_percent: 55,
              away_rendered_percent: 45,
            },
            hero_probability: 0.55,
            hero_probability_away: 0.45,
            hero_probability_source: 'blend',
            blend_fold_revision: { '42': 10 },
            hero_probability_observed_at: '2026-10-25T16:59:00Z',
            live_state: { period: '2nd Set', game_clock: '4-4' },
          },
        } as unknown as FeedItem,
        {
          type: 'futures',
          data: {
            id: 501,
            source: 'kalshi',
            status: 'open',
            top_outcomes: [
              { id: 70, name: 'Alpha', probability: 0.4, rank: 1, movement: null, price_revision_at: '2026-10-25T16:59:00Z' },
              { id: 71, name: 'Beta', probability: 0.6, rank: 2, movement: null, price_revision_at: '2026-10-25T16:59:00Z' },
            ],
          },
        } as unknown as FeedItem,
        {
          type: 'futures',
          data: {
            id: 502,
            source: 'kalshi',
            status: 'open',
            top_outcomes: [
              { id: 80, name: 'Yes', probability: 0.35, rank: 1, movement: null, price_revision_at: '2026-10-25T16:59:00Z' },
            ],
          },
        } as unknown as FeedItem,
        {
          type: 'futures',
          data: {
            id: 503,
            source: 'kalshi',
            status: 'open',
            top_outcomes: [
              { id: 90, name: 'Kevin Warsh', probability: 0.25, rank: 1, movement: null, price_revision_at: '2026-10-25T16:59:00Z' },
            ],
          },
        } as unknown as FeedItem,
      ],
    };

    fetchCardsMock.mockResolvedValue(initialPriceCards);
    expect(searchEventStreamable(game)).toBe(true);

    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);

    act(() => {
      root!.render(<Harness futures={[flat]} families={[fam]} events={[game]} />);
    });
    await act(async () => {
      await jest.advanceTimersByTimeAsync(0);
    });

    // Event stream opened with ?preview_protocol=authority-v3
    const eventSse = FakeEventSource.instances
      .filter((s) => s.url.startsWith('/api/events/42/stream?preview_protocol=authority-v3') && !s.closed)
      .at(-1)!;
    expect(eventSse).toBeDefined();
    eventSse.emit('open');
    eventSse.emit('preview_open_v3', wire(m.singleton_open));

    const previewP = m.singleton_blend.frame.p;
    const expectedGamePct = `${Math.round(previewP * 100)}%`;

    const tGameRecvNs = realHrtimeNs();
    eventSse.emit(
      'preview_v3',
      wire({
        ...m.singleton_blend,
        frame: {
          ...m.singleton_blend.frame,
          preview: { ...m.singleton_blend.frame.preview },
        },
      }),
    );
    const dtGameMs = Number(realHrtimeNs() - tGameRecvNs) / 1e6;
    expect(dtGameMs).toBeGreaterThan(0);
    expect(dtGameMs).toBeLessThan(500);
    console.info(`[capture:search-game-card] dt_ms=${dtGameMs.toFixed(2)}`);
    expect(container.textContent).toContain(expectedGamePct);

    // Market stream opened for 501,502,503 -> emit market_preview on flat & family
    const mktSse = FakeEventSource.instances
      .filter((s) => s.url.startsWith('/api/markets/stream') && !s.closed)
      .at(-1)!;
    expect(mktSse).toBeDefined();
    mktSse.emit('open', wire({ market_ids: [501, 502, 503], unavailable_market_ids: [] }));

    const tFlatRecvNs = realHrtimeNs();
    mktSse.emit(
      'market_preview',
      wire({
        type: 'market_preview',
        preview: true,
        market_id: 501,
        source: 'kalshi',
        outcomes: [{ outcome_id: 70, p: 0.77, observed_at: '2026-10-25T17:00:05Z' }],
        seq: 1,
        ttl_ms: 10_000,
      }),
    );
    const dtFlatMs = Number(realHrtimeNs() - tFlatRecvNs) / 1e6;
    expect(dtFlatMs).toBeGreaterThan(0);
    expect(dtFlatMs).toBeLessThan(500);
    console.info(`[capture:search-futures-card] dt_ms=${dtFlatMs.toFixed(2)}`);
    expect(container.textContent).toContain('77%');

    const tFamRecvNs = realHrtimeNs();
    mktSse.emit(
      'market_preview',
      wire({
        type: 'market_preview',
        preview: true,
        market_id: 502,
        source: 'kalshi',
        outcomes: [{ outcome_id: 80, p: 0.64, observed_at: '2026-10-25T17:00:06Z' }],
        seq: 1,
        ttl_ms: 10_000,
      }),
    );
    const dtFamMs = Number(realHrtimeNs() - tFamRecvNs) / 1e6;
    expect(dtFamMs).toBeGreaterThan(0);
    expect(dtFamMs).toBeLessThan(500);
    console.info(`[capture:search-family-card] dt_ms=${dtFamMs.toFixed(2)}`);
    expect(container.textContent).toContain('64%');
  });
});
