/** @jest-environment jsdom */

import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import {
  buildAtlasFieldCohort,
  retainContenderColors,
} from '@/components/futures/FuturesShapeBody';
import { FuturesChart, spreadAtlasEndLabels } from '@/components/FuturesChart';

(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;

let searchParamsStr = '';
let futuresMarketPayload: unknown;
let futuresHistoryPayload: unknown;

jest.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(searchParamsStr),
  useRouter: () => ({ replace: () => {}, push: () => {} }),
}));

jest.mock('@/hooks', () => ({
  usePageTracking: () => {},
  useScrollDepth: () => {},
  useEngagementTime: () => {},
  usePinnedFutures: () => ({
    isPinned: () => false,
    togglePin: () => {},
    isMaxReached: false,
  }),
}));

jest.mock('@/components/Analytics', () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));

jest.mock('@/hooks/useMarketStream', () => ({
  useMarketStream: () => {},
}));

jest.mock('@/hooks/useFuturesDetailStream', () => ({
  useFuturesDetailStream: () => {},
}));

jest.mock('swr', () => ({
  __esModule: true,
  default: (key: unknown) => {
    if (Array.isArray(key) && key[0] === 'futures-market') {
      return {
        data: futuresMarketPayload,
        error: undefined,
        isLoading: false,
        mutate: () => {},
      };
    }
    if (Array.isArray(key) && key[0] === 'futures-history') {
      return {
        data: futuresHistoryPayload,
        error: undefined,
        isLoading: false,
        mutate: () => {},
      };
    }
    return {
      data: { items: [] },
      error: undefined,
      isLoading: false,
      mutate: () => {},
    };
  },
}));

import FuturesDetailPage from '../../app/futures/[id]/page';

describe('Step F5 — Futures chart adopts event-page prototype chart grammar (#883, Decide 47: E)', () => {
  afterEach(() => {
    searchParamsStr = '';
    futuresMarketPayload = undefined;
    futuresHistoryPayload = undefined;
  });

  describe('Pure helpers: retainContenderColors, buildAtlasFieldCohort, spreadAtlasEndLabels', () => {
    it('retains continuing contender color slots when a chosen contender replaces one slot', () => {
      const initial = retainContenderColors({}, ['kansas', 'alaska', 'oklahoma'], 3);
      expect(initial).toEqual({
        kansas: 0,
        alaska: 1,
        oklahoma: 2,
      });

      // Choosing Vermont replaces Oklahoma, while Kansas (0) and Alaska (1) keep their colors
      const afterPin = retainContenderColors(initial, ['vermont', 'kansas', 'alaska'], 3);
      expect(afterPin.kansas).toBe(0);
      expect(afterPin.alaska).toBe(1);
      expect(afterPin.vermont).toBe(2);
    });

    it('builds the 3-leader cohort and pins a non-top-3 selection alongside the top 2 other leaders', () => {
      const pool = [
        { id: 1, name: 'Kansas' },
        { id: 2, name: 'Alaska' },
        { id: 3, name: 'Oklahoma' },
        { id: 4, name: 'Colorado' },
        { id: 5, name: 'Vermont' },
      ];

      expect(buildAtlasFieldCohort(pool, null, 3).map((r) => r.id)).toEqual([1, 2, 3]);
      expect(buildAtlasFieldCohort(pool, 2, 3).map((r) => r.id)).toEqual([1, 2, 3]);
      expect(buildAtlasFieldCohort(pool, 5, 3).map((r) => r.id)).toEqual([5, 1, 2]);
    });

    it('spreads overlapping end labels vertically without exceeding plot bounds', () => {
      const placed = spreadAtlasEndLabels(
        [
          { outcomeId: 1, text: 'Kansas 95%', y: 26, pointX: 652, color: '#0EA5E9', opacity: 1 },
          { outcomeId: 2, text: 'Alaska 3%', y: 155, pointX: 652, color: '#F59E0B', opacity: 1 },
          { outcomeId: 3, text: 'Oklahoma 1%', y: 158, pointX: 652, color: '#10B981', opacity: 1 },
        ],
        28,
        156,
        16,
      );
      expect(placed).toHaveLength(3);
      expect(placed[2].labelY - placed[1].labelY).toBeGreaterThanOrEqual(16);
      expect(placed[2].labelY).toBeLessThanOrEqual(156);
    });
  });

  describe('Two-outcome market (109085): dial controls the journey and Final Results table is removed', () => {
    it('draws the selected side on the journey with its end label, switches sides on dial tap, and omits the standalone Final Results table under ?atlas=1', async () => {
      searchParamsStr = 'atlas=1';
      futuresMarketPayload = {
        id: 109085,
        name: 'Kansas Senate winner?',
        status: 'resolved',
        market_type: 'duel',
        mutually_exclusive: true,
        llm_sport_category: 'politics',
        source: 'kalshi',
        source_count: 1,
        external_id: 'SENATEKS-26',
        created_at: '2026-06-01T00:00:00Z',
        updated_at: '2026-11-04T06:00:00Z',
        outcomes: [
          {
            id: 1595212,
            name: 'Adam Hamilton',
            probability: 1.0,
            opening_probability: 0.12,
            rank: 1,
            is_winner: true,
            resolution_source: 'api_settlement',
            last_updated: '2026-11-04T06:00:00Z',
          },
          {
            id: 1595211,
            name: 'Roger Marshall',
            probability: 0.0,
            opening_probability: 0.855,
            rank: 2,
            is_winner: false,
            resolution_source: 'api_settlement',
            last_updated: '2026-11-04T06:00:00Z',
          },
        ],
      };
      futuresHistoryPayload = {
        sparse: false,
        actual_hours: 168,
        outcomes: [
          {
            outcome_id: 1595212,
            name: 'Adam Hamilton',
            history: [
              { timestamp: '2026-10-01T00:00:00Z', probability: 0.12, american_odds: null, bookmaker: 'kalshi' },
              { timestamp: '2026-11-04T05:00:00Z', probability: 0.999, american_odds: null, bookmaker: 'kalshi' },
              { timestamp: '2026-11-04T05:00:01Z', probability: 1.0, american_odds: null, bookmaker: 'settlement' },
            ],
          },
          {
            outcome_id: 1595211,
            name: 'Roger Marshall',
            history: [
              { timestamp: '2026-10-01T00:00:00Z', probability: 0.855, american_odds: null, bookmaker: 'kalshi' },
              { timestamp: '2026-11-04T05:00:00Z', probability: 0.001, american_odds: null, bookmaker: 'kalshi' },
              { timestamp: '2026-11-04T05:00:01Z', probability: 0.0, american_odds: null, bookmaker: 'settlement' },
            ],
          },
        ],
      };

      const container = document.createElement('div');
      document.body.appendChild(container);
      const root = createRoot(container);
      try {
        await act(async () => {
          root.render(<FuturesDetailPage params={{ id: '109085' }} />);
        });

        // 1. Standalone Final Results / All Outcomes section is removed under ?atlas=1
        expect(container.textContent).not.toContain('Final Results');
        expect(container.querySelector('[data-testid="futures-sort-controls"]')).toBeNull();

        // 2. Journey carries only the active side (Adam Hamilton) with its end label, and no bottom legend
        const endLabelsInitial = container.querySelectorAll('[data-testid="atlas-chart-end-label"]');
        expect(endLabelsInitial).toHaveLength(1);
        expect(endLabelsInitial[0].textContent).toContain('Adam Hamilton ✓ Won');
        expect(container.querySelector('[aria-label="Chart legend"]')).toBeNull();

        // 3. Tapping the second side on the dial switches the journey to Roger Marshall
        const sideButtons = container.querySelectorAll('[data-testid="atlas-dial-side-button"]');
        expect(sideButtons).toHaveLength(2);
        await act(async () => {
          (sideButtons[1] as HTMLButtonElement).click();
        });

        const endLabelsAfterTap = container.querySelectorAll('[data-testid="atlas-chart-end-label"]');
        expect(endLabelsAfterTap).toHaveLength(1);
        expect(endLabelsAfterTap[0].textContent).toContain('Roger Marshall ✗ Lost');
      } finally {
        await act(async () => {
          root.unmount();
        });
        container.remove();
      }
    });
  });

  describe('Field market (108629): 3 leaders in the chart with retained colors and "N more" sheet', () => {
    it('draws the 3 leaders with end labels in their series colors, retains continuing colors when a contender from "N more" is chosen, and removes the standalone All Outcomes table', async () => {
      searchParamsStr = 'atlas=1';
      futuresMarketPayload = {
        id: 108629,
        name: 'Closest Governor race in 2026?',
        status: 'open',
        market_type: 'field',
        mutually_exclusive: true,
        llm_sport_category: 'politics',
        source: 'kalshi',
        source_count: 1,
        external_id: 'KXGOVCLOSEST-26',
        created_at: '2026-09-01T00:00:00Z',
        updated_at: '2026-11-06T14:00:00Z',
        outcomes: [
          { id: 1594085, name: 'Kansas', probability: 0.95, rendered_percent: 95, opening_probability: 0.035, rank: 1, is_winner: null, last_updated: '2026-11-06T14:00:00Z' },
          { id: 235955685, name: 'Alaska', probability: 0.03, rendered_percent: 3, opening_probability: 0.065, rank: 2, is_winner: null, last_updated: '2026-11-06T14:00:00Z' },
          { id: 254416045, name: 'Oklahoma', probability: 0.01, rendered_percent: 1, opening_probability: 0.015, rank: 3, is_winner: null, last_updated: '2026-11-06T14:00:00Z' },
          { id: 235955690, name: 'Colorado', probability: 0.01, rendered_percent: 1, opening_probability: 0.055, rank: 4, is_winner: null, last_updated: '2026-11-06T14:00:00Z' },
          { id: 254416041, name: 'Vermont', probability: 0.01, rendered_percent: 1, opening_probability: 0.035, rank: 5, is_winner: null, last_updated: '2026-11-06T14:00:00Z' },
        ],
      };
      futuresHistoryPayload = {
        sparse: false,
        actual_hours: 168,
        outcomes: [
          {
            outcome_id: 1594085,
            name: 'Kansas',
            history: [
              { timestamp: '2026-10-01T00:00:00Z', probability: 0.035, american_odds: null, bookmaker: 'kalshi' },
              { timestamp: '2026-11-06T14:00:00Z', probability: 0.95, american_odds: null, bookmaker: 'kalshi' },
            ],
          },
          {
            outcome_id: 235955685,
            name: 'Alaska',
            history: [
              { timestamp: '2026-10-01T00:00:00Z', probability: 0.065, american_odds: null, bookmaker: 'kalshi' },
              { timestamp: '2026-11-06T14:00:00Z', probability: 0.03, american_odds: null, bookmaker: 'kalshi' },
            ],
          },
          {
            outcome_id: 254416045,
            name: 'Oklahoma',
            history: [
              { timestamp: '2026-10-01T00:00:00Z', probability: 0.015, american_odds: null, bookmaker: 'kalshi' },
              { timestamp: '2026-11-06T14:00:00Z', probability: 0.01, american_odds: null, bookmaker: 'kalshi' },
            ],
          },
          {
            outcome_id: 254416041,
            name: 'Vermont',
            history: [
              { timestamp: '2026-10-01T00:00:00Z', probability: 0.035, american_odds: null, bookmaker: 'kalshi' },
              { timestamp: '2026-11-06T14:00:00Z', probability: 0.01, american_odds: null, bookmaker: 'kalshi' },
            ],
          },
        ],
      };

      const container = document.createElement('div');
      document.body.appendChild(container);
      const root = createRoot(container);
      try {
        await act(async () => {
          root.render(<FuturesDetailPage params={{ id: '108629' }} />);
        });

        // Standalone All Outcomes table is absent; the "N more" reach lives in FuturesShapeBody
        expect(container.querySelector('[data-testid="futures-sort-controls"]')).toBeNull();
        expect(container.querySelector('[data-testid="atlas-field-more-button"]')).not.toBeNull();

        // 3 leaders drawn in the chart with end labels in their series colors
        const initialLabels = Array.from(
          container.querySelectorAll('[data-testid="atlas-chart-end-label"]'),
        );
        expect(initialLabels).toHaveLength(3);
        const labelTexts = initialLabels.map((el) => el.textContent);
        expect(labelTexts).toEqual(
          expect.arrayContaining(['Kansas 95%', 'Alaska 3%', 'Oklahoma 1%']),
        );

        const kansasColorBefore = container
          .querySelector('[data-testid="atlas-field-leader-row"][data-outcome-id="1594085"]')
          ?.getAttribute('data-series-color');
        const alaskaColorBefore = container
          .querySelector('[data-testid="atlas-field-leader-row"][data-outcome-id="235955685"]')
          ?.getAttribute('data-series-color');
        const oklahomaColorBefore = container
          .querySelector('[data-testid="atlas-field-leader-row"][data-outcome-id="254416045"]')
          ?.getAttribute('data-series-color');
        expect(kansasColorBefore).toBeTruthy();
        expect(alaskaColorBefore).toBeTruthy();
        expect(oklahomaColorBefore).toBeTruthy();

        // Open the "2 more" searchable sheet and choose Vermont (254416041)
        const moreBtn = container.querySelector(
          '[data-testid="atlas-field-more-button"]',
        ) as HTMLButtonElement;
        await act(async () => {
          moreBtn.click();
        });

        const sheetRows = Array.from(
          document.querySelectorAll('[data-testid="atlas-field-sheet-row"]'),
        );
        const vermontBtn = sheetRows.find((el) =>
          el.textContent?.includes('Vermont'),
        ) as HTMLButtonElement;
        expect(vermontBtn).toBeDefined();

        await act(async () => {
          vermontBtn.click();
        });

        // Cohort is now [Vermont, Kansas, Alaska]; Kansas and Alaska keep their colors, Vermont takes the freed color
        const leaderRowsAfter = Array.from(
          container.querySelectorAll('[data-testid="atlas-field-leader-row"]'),
        );
        expect(leaderRowsAfter.map((el) => el.getAttribute('data-outcome-id'))).toEqual([
          '254416041',
          '1594085',
          '235955685',
        ]);
        expect(leaderRowsAfter[0].getAttribute('data-series-color')).toBe(oklahomaColorBefore);
        expect(leaderRowsAfter[1].getAttribute('data-series-color')).toBe(kansasColorBefore);
        expect(leaderRowsAfter[2].getAttribute('data-series-color')).toBe(alaskaColorBefore);
        expect(
          leaderRowsAfter[0].querySelector('[data-testid="atlas-field-pinned-badge"]')?.textContent,
        ).toBe('Pinned');

        // Chart end labels also update to Vermont, Kansas, Alaska in those exact colors
        const afterLabels = Array.from(
          container.querySelectorAll('[data-testid="atlas-chart-end-label"]'),
        );
        expect(afterLabels.map((el) => el.textContent)).toEqual(
          expect.arrayContaining(['Vermont 1%', 'Kansas 95%', 'Alaska 3%']),
        );
        const vermontEndLabel = afterLabels.find((el) =>
          el.textContent?.includes('Vermont'),
        );
        expect(vermontEndLabel?.getAttribute('data-color')).toBe(oklahomaColorBefore);
      } finally {
        await act(async () => {
          root.unmount();
        });
        container.remove();
      }
    });
  });

  describe('Standalone FuturesChart end labels', () => {
    it('renders end labels with name + % and suppresses the bottom toggle legend when atlas is true', () => {
      const container = document.createElement('div');
      const root = createRoot(container);
      act(() => {
        root.render(
          <FuturesChart
            historyData={[
              {
                outcome_id: 1,
                name: 'Kansas',
                history: [
                  { timestamp: '2026-10-01T00:00:00Z', probability: 0.21, american_odds: null, bookmaker: 'kalshi' },
                  { timestamp: '2026-11-01T00:00:00Z', probability: 0.95, american_odds: null, bookmaker: 'kalshi' },
                ],
              },
            ]}
            selectedOutcomes={new Set([1])}
            onToggleOutcome={() => {}}
            fixedYAxis
            fieldCeiling
            atlas
          />,
        );
      });

      const endLabels = container.querySelectorAll('[data-testid="atlas-chart-end-label"]');
      expect(endLabels).toHaveLength(1);
      expect(endLabels[0].textContent).toBe('Kansas 95%');
      expect(container.textContent).not.toContain('Showing top 5 outcomes');

      act(() => {
        root.unmount();
      });
    });
  });
});
