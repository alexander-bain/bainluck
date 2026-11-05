/** @jest-environment jsdom */

import React from 'react';
import { act } from 'react';
import { createRoot } from 'react-dom/client';
import FuturesShapeBody, {
  resolveAtlasBodyKind,
} from '../../components/futures/FuturesShapeBody';
import QuantityGroup, { buildThresholdRungs } from '../../components/QuantityGroup';
import {
  SHAPE_CLAIM,
  SHAPE_DUEL,
  SHAPE_FIELD,
  SHAPE_PARTICIPATION,
  SHAPE_QUANTITY,
} from '../../lib/marketShape';
import type { FuturesOutcome } from '../../lib/types';

function renderHtml(element: React.ReactElement): string {
  const container = document.createElement('div');
  const root = createRoot(container);
  act(() => {
    root.render(element);
  });
  const html = container.innerHTML;
  act(() => {
    root.unmount();
  });
  return html;
}

function makeOutcome(overrides: Partial<FuturesOutcome> & { id: number; name: string }): FuturesOutcome {
  return {
    probability: 0.5,
    opening_probability: 0.4,
    opening_american_odds: null,
    american_odds: null,
    probability_change_24h: null,
    movement: null,
    rank: 1,
    rank_change_24h: null,
    is_winner: null,
    last_updated: null,
    ...overrides,
  };
}

describe('Step F2 — Atlas futures bodies by stored shape (#883)', () => {
  describe('resolveAtlasBodyKind', () => {
    it('classifies one-leg, duel, qualifier, field, and quantity shapes', () => {
      expect(
        resolveAtlasBodyKind({
          marketShape: SHAPE_CLAIM,
          outcomeCount: 1,
          mutuallyExclusive: true,
        }),
      ).toBe('one-leg');

      expect(
        resolveAtlasBodyKind({
          marketShape: SHAPE_DUEL,
          outcomeCount: 2,
          mutuallyExclusive: true,
        }),
      ).toBe('duel');

      expect(
        resolveAtlasBodyKind({
          marketShape: SHAPE_PARTICIPATION,
          outcomeCount: 8,
          mutuallyExclusive: true,
        }),
      ).toBe('qualifier');

      expect(
        resolveAtlasBodyKind({
          marketShape: SHAPE_FIELD,
          outcomeCount: 8,
          mutuallyExclusive: false,
        }),
      ).toBe('qualifier');

      expect(
        resolveAtlasBodyKind({
          marketShape: SHAPE_FIELD,
          outcomeCount: 8,
          mutuallyExclusive: true,
        }),
      ).toBe('field');

      expect(
        resolveAtlasBodyKind({
          marketShape: SHAPE_QUANTITY,
          outcomeCount: 5,
          mutuallyExclusive: true,
        }),
      ).toBe('quantity');
    });
  });

  describe('Two-sided market (duel)', () => {
    it('renders a semicircle dial driven by the server number and withholds multi-venue opening (#12043)', () => {
      const outcomes: FuturesOutcome[] = [
        makeOutcome({
          id: 101,
          name: 'Adam Hamilton',
          probability: 0.62,
          opening_probability: 0.48,
          rank: 1,
        }),
        makeOutcome({
          id: 102,
          name: 'Roger Marshall',
          probability: 0.38,
          opening_probability: 0.52,
          rank: 2,
        }),
      ];
      const renderedById = new Map([
        [101, { current: 62, opening: 48 }],
        [102, { current: 38, opening: 52 }],
      ]);

      const singleVenueHtml = renderHtml(
        <FuturesShapeBody
          outcomes={outcomes}
          sortedOutcomes={outcomes}
          pricedOutcomes={outcomes}
          renderedById={renderedById}
          marketName="Kansas Senate winner"
          marketShape={SHAPE_DUEL}
          mutuallyExclusive
          isResolved={false}
          sourceCount={1}
          selectedOutcomeId={101}
          onSelectOutcome={() => {}}
        />,
      );

      expect(singleVenueHtml).toContain('data-testid="atlas-duel-body"');
      expect(singleVenueHtml).toContain('data-testid="atlas-binary-dial"');
      expect(singleVenueHtml).toContain('>Adam Hamilton<');
      expect(singleVenueHtml).toContain('>Roger Marshall<');
      expect(singleVenueHtml).toContain('>62%<');
      expect(singleVenueHtml).toContain('>48%<');
      expect(singleVenueHtml).toContain('+14 pp');
      expect(singleVenueHtml).toContain('since opening');

      const multiVenueHtml = renderHtml(
        <FuturesShapeBody
          outcomes={outcomes}
          sortedOutcomes={outcomes}
          pricedOutcomes={outcomes}
          renderedById={renderedById}
          marketName="Kansas Senate winner"
          marketShape={SHAPE_DUEL}
          mutuallyExclusive
          isResolved={false}
          sourceCount={2}
          selectedOutcomeId={101}
          onSelectOutcome={() => {}}
        />,
      );

      expect(multiVenueHtml).toContain('data-testid="atlas-duel-body"');
      expect(multiVenueHtml).not.toContain('since opening');
      expect(multiVenueHtml).toContain('Unavailable');
      expect(multiVenueHtml).toContain('data-testid="atlas-dial-multivenue-note"');
    });
  });

  describe('One-leg market', () => {
    it('shows the single supplied outcome on a dial and never invents a "No" side', () => {
      const outcomes: FuturesOutcome[] = [
        makeOutcome({
          id: 201,
          name: 'Yes',
          probability: 0.58,
          opening_probability: 0.38,
          is_winner: true,
          resolution_source: 'kalshi',
          rank: 1,
        }),
      ];
      const renderedById = new Map([[201, { current: 58, opening: 38 }]]);

      const html = renderHtml(
        <FuturesShapeBody
          outcomes={outcomes}
          sortedOutcomes={outcomes}
          pricedOutcomes={outcomes}
          renderedById={renderedById}
          marketName="Will Democrats sweep all swing state Governor races?"
          marketShape={SHAPE_CLAIM}
          mutuallyExclusive
          isResolved
          sourceCount={1}
          selectedOutcomeId={201}
          onSelectOutcome={() => {}}
        />,
      );

      expect(html).toContain('data-testid="atlas-one-leg-body"');
      expect(html).toContain('One market, one supplied side');
      expect(html).toContain('>Yes<');
      expect(html).toContain('>✓ Won<');
      expect(html).toContain('>38%<');
      expect(html).not.toContain('>No<');
    });
  });

  describe('Mutually exclusive field', () => {
    it('shows the top 3 contenders with server-fed numbers and opens a searchable full-field sheet', async () => {
      const outcomes: FuturesOutcome[] = [
        makeOutcome({ id: 1, name: 'Florida', probability: 0.29, opening_probability: 0.22, rank: 1 }),
        makeOutcome({ id: 2, name: 'Georgia', probability: 0.24, opening_probability: 0.27, rank: 2 }),
        makeOutcome({ id: 3, name: 'Arizona', probability: 0.19, opening_probability: 0.18, rank: 3 }),
        makeOutcome({ id: 4, name: 'Wisconsin', probability: 0.15, opening_probability: 0.16, rank: 4 }),
        makeOutcome({ id: 5, name: 'Nevada', probability: 0.13, opening_probability: 0.17, rank: 5 }),
      ];
      const renderedById = new Map([
        [1, { current: 29, opening: 22 }],
        [2, { current: 24, opening: 27 }],
        [3, { current: 19, opening: 18 }],
        [4, { current: 15, opening: 16 }],
        [5, { current: 13, opening: 17 }],
      ]);

      const container = document.createElement('div');
      document.body.appendChild(container);
      const root = createRoot(container);
      try {
        await act(async () => {
          root.render(
            <FuturesShapeBody
              outcomes={outcomes}
              sortedOutcomes={outcomes}
              pricedOutcomes={outcomes}
              renderedById={renderedById}
              marketName="Closest Governor race in 2026?"
              marketShape={SHAPE_FIELD}
              mutuallyExclusive
              isResolved={false}
              sourceCount={1}
              selectedOutcomeId={1}
              onSelectOutcome={() => {}}
            />,
          );
        });

        expect(container.querySelector('[data-testid="atlas-field-body"]')).not.toBeNull();
        expect(container.querySelectorAll('[data-testid="atlas-field-leader-row"]').length).toBe(3);
        expect(container.innerHTML).toContain('2 more');
        expect(container.innerHTML).toContain('Search all 5 outcomes');
        expect(document.querySelector('[data-testid="atlas-field-sheet"]')).toBeNull();

        const openBtn = container.querySelector(
          '[data-testid="atlas-field-more-button"]',
        ) as HTMLButtonElement;
        expect(openBtn).not.toBeNull();

        await act(async () => {
          openBtn.click();
        });

        const sheet = document.querySelector('[data-testid="atlas-field-sheet"]');
        expect(sheet).not.toBeNull();
        expect(document.querySelectorAll('[data-testid="atlas-field-sheet-row"]').length).toBe(5);
      } finally {
        await act(async () => {
          root.unmount();
        });
        container.remove();
      }
    });
  });

  describe('Qualifier set (independent chances)', () => {
    it('labels independent chances "do not add to 100" and prints unnormalized server numbers', () => {
      const outcomes: FuturesOutcome[] = [
        makeOutcome({ id: 11, name: 'Detroit Lions', probability: 0.84, opening_probability: 0.65, rank: 1 }),
        makeOutcome({ id: 12, name: 'Green Bay Packers', probability: 0.72, opening_probability: 0.61, rank: 2 }),
        makeOutcome({ id: 13, name: 'Minnesota Vikings', probability: 0.68, opening_probability: 0.45, rank: 3 }),
      ];
      const renderedById = new Map([
        [11, { current: 84, opening: 65 }],
        [12, { current: 72, opening: 61 }],
        [13, { current: 68, opening: 45 }],
      ]);

      const html = renderHtml(
        <FuturesShapeBody
          outcomes={outcomes}
          sortedOutcomes={outcomes}
          pricedOutcomes={outcomes}
          renderedById={renderedById}
          marketName="NFC North teams to make the playoffs"
          marketShape={SHAPE_PARTICIPATION}
          mutuallyExclusive={false}
          isResolved={false}
          sourceCount={1}
          selectedOutcomeId={11}
          onSelectOutcome={() => {}}
        />,
      );

      expect(html).toContain('data-testid="atlas-qualifier-body"');
      expect(html).toContain('data-testid="atlas-qualifier-do-not-add"');
      expect(html).toContain('do not add to 100');
      expect(html).toContain('>84%<');
      expect(html).toContain('>72%<');
      expect(html).toContain('>68%<');
    });
  });

  describe('Thresholds on production rungs (QuantityGroup / buildThresholdRungs)', () => {
    it('renders thresholds at their true numeric positions on QuantityGroup when atlas is enabled', () => {
      const rungs = buildThresholdRungs([
        { outcome_id: 1, name: 'Above 20°', label: 'Above 20°', threshold_value: 20, probability: 0.92 },
        { outcome_id: 2, name: 'Above 24°', label: 'Above 24°', threshold_value: 24, probability: 0.64 },
        { outcome_id: 3, name: 'Above 32°', label: 'Above 32°', threshold_value: 32, probability: 0.18 },
      ]);

      const html = renderHtml(<QuantityGroup title="All Outcomes" rungs={rungs} atlas />);

      expect(html).toContain('data-testid="atlas-threshold-true-positions"');
      const xs = Array.from(
        html.matchAll(/<circle cx="([0-9.]+)" cy="([0-9.]+)"/g),
      ).map((m) => Number(m[1]));
      expect(xs.length).toBe(3);
      // 38 + ratio * 270: for 20 -> 38, for 24 (ratio 1/3) -> 128, for 32 (ratio 1) -> 308.
      expect(xs[0]).toBeCloseTo(38, 1);
      expect(xs[1]).toBeCloseTo(128, 1);
      expect(xs[2]).toBeCloseTo(308, 1);
    });
  });
});
