/** @jest-environment jsdom */

import React, { useState } from 'react';
import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { FuturesHero } from '../../components/FuturesHero';
import AtlasDetailsSheet from '../../components/atlas/AtlasDetailsSheet';
import {
  ATLAS_STATE_COPY,
  formatAtlasAttribution,
  formatAtlasDatePT,
  formatAtlasMarketHeading,
  formatAtlasTimestampPT,
  resolveAtlasOptIn,
  resolveOriginalMarketUrl,
} from '../../components/atlas/atlasStateCopy';

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

describe('Step F1 — Atlas futures headline, result, and shared details sheet (#883)', () => {
  describe('atlasStateCopy shared helpers', () => {
    it('exports the canonical shared state wording including "No recent probability"', () => {
      expect(ATLAS_STATE_COPY.loading).toBe('Loading');
      expect(ATLAS_STATE_COPY.updateInterrupted).toBe('Update interrupted');
      expect(ATLAS_STATE_COPY.postponed).toBe('Postponed');
      expect(ATLAS_STATE_COPY.voided).toBe('Void');
      expect(ATLAS_STATE_COPY.noRecentPrice).toBe('No recent probability');
      expect(ATLAS_STATE_COPY.wonWithCheck).toBe('✓ Won');
      expect(ATLAS_STATE_COPY.lostWithCross).toBe('✗ Lost');
    });

    it('resolves ?atlas=1 opt-in from query strings and URLSearchParams', () => {
      expect(resolveAtlasOptIn('?atlas=1')).toBe(true);
      expect(resolveAtlasOptIn('atlas=true')).toBe(true);
      expect(resolveAtlasOptIn('?atlas=0')).toBe(false);
      expect(resolveAtlasOptIn('')).toBe(false);
      expect(resolveAtlasOptIn(new URLSearchParams('atlas=1'))).toBe(true);
      expect(resolveAtlasOptIn(null)).toBe(false);
    });

    it('formats dates and timestamps in Pacific Time with PT suffix', () => {
      expect(
        formatAtlasTimestampPT('2026-11-03T08:55:57Z', { includeSeconds: true }),
      ).toBe('Nov 3, 2026, 12:55:57 AM PT');
      expect(
        formatAtlasTimestampPT('2027-01-19T15:00:00Z', { includeSeconds: false }),
      ).toBe('Jan 19, 2027, 7:00 AM PT');
      expect(formatAtlasDatePT('2027-01-19')).toBe('Jan 19, 2027');
      expect(formatAtlasMarketHeading('Will Democrats sweep all swing state Governor races?')).toBe(
        'Will Democrats sweep all swing state Governor races',
      );
    });

    it('formats source attribution and builds original market links', () => {
      expect(formatAtlasAttribution('kalshi')).toBe('Kalshi');
      expect(formatAtlasAttribution('polymarket')).toBe('Polymarket');
      expect(formatAtlasAttribution('kalshi', { sourceCount: 2 })).toBe(
        '2 sources',
      );
      expect(
        formatAtlasAttribution('datagolf', {
          sourceCount: 2,
          sourceLabels: [],
        }),
      ).toBe('2 sources');
      expect(
        formatAtlasAttribution('odds_api', {
          sourceCount: 3,
          sourceLabels: ['  '],
        }),
      ).toBe('3 sources');
      expect(
        formatAtlasAttribution('kalshi', {
          sourceLabels: ['Kalshi', 'Polymarket'],
        }),
      ).toEqual('Kalshi · Polymarket');

      const kalshiLink = resolveOriginalMarketUrl({
        source: 'kalshi',
        externalId: 'KXDEMSWINGSTATEGOVSWEEP-26NOV03',
      });
      expect(kalshiLink).toEqual({
        url: 'https://kalshi.com/markets/kxdemswingstategovsweep',
        label: 'Original market',
        venueName: 'Kalshi',
      });
      expect(resolveOriginalMarketUrl({ source: 'kalshi', externalId: '' })).toBeNull();
      expect(resolveOriginalMarketUrl({ source: 'polymarket', externalId: '65536371' })).toBeNull();
      expect(
        resolveOriginalMarketUrl({
          source: 'polymarket',
          externalId: 'denver-december-snowfall-2026',
        }),
      ).toEqual({
        url: 'https://polymarket.com/event/denver-december-snowfall-2026',
        label: 'Original market',
        venueName: 'Polymarket',
      });
    });
  });

  describe('FuturesHero behind ?atlas=1', () => {
    it('names the leader, its chance, and the scheduled resolution on an open market', () => {
      const html = renderHtml(
        <FuturesHero
          atlas
          name="Closest Governor race in 2026?"
          probability={0.29}
          rendered={29}
          outcomeName="Florida"
          categoryLabel="Politics"
          lastObservedLabel="Nov 3, 2026, 6:33 PM PT"
          scheduledResolutionLabel="Scheduled resolution Jan 19, 2027, 8:59 PM PT"
          onOpenDetails={() => {}}
        />,
      );

      expect(html).toContain('data-testid="atlas-futures-hero"');
      expect(html).toContain('data-testid="hero-percent"');
      expect(html).toContain('>29<');
      expect(html).toContain('>Florida<');
      expect(html).toContain('>Closest Governor race in 2026<');
      expect(html).toContain('Recorded Nov 3, 2026, 6:33 PM PT');
      expect(html).toContain('Scheduled resolution Jan 19, 2027, 8:59 PM PT');
      expect(html).toContain('data-testid="atlas-details-trigger"');
    });

    it('prints "No recent probability" when an open market has no current probability', () => {
      const html = renderHtml(
        <FuturesHero
          atlas
          name="Kansas Senate winner"
          probability={null}
          outcomeName="Adam Hamilton"
          categoryLabel="Politics"
        />,
      );

      expect(html).toContain('data-testid="atlas-no-recent-price"');
      expect(html).toContain('>No recent probability<');
      expect(html).toContain('>Adam Hamilton<');
    });

    it('leads with "✓ Won" and opening chance on a settled single-venue market', () => {
      const html = renderHtml(
        <FuturesHero
          atlas
          resolved
          resolvedWon
          name="Georgia Governor winner"
          probability={0.96}
          outcomeName="Keisha Lance Bottoms"
          openingProbability={0.56}
          renderedOpening={56}
          sourceCount={1}
          categoryLabel="Politics"
        />,
      );

      expect(html).toContain('>✓ Won<');
      expect(html).toContain('>Keisha Lance Bottoms<');
      expect(html).toContain('data-testid="atlas-opening-chance"');
      expect(html).toContain('>56%<');
    });

    it('holds back opening chance silently on a settled multi-venue market (#12043)', () => {
      const html = renderHtml(
        <FuturesHero
          atlas
          resolved
          resolvedWon
          name="Kansas Senate winner"
          probability={0.97}
          outcomeName="Adam Hamilton"
          openingProbability={0.52}
          sourceCount={2}
          categoryLabel="Politics"
        />,
      );

      expect(html).toContain('>✓ Won<');
      expect(html).not.toContain('data-testid="atlas-opening-chance"');
    });

    it('leads with "✗ Lost" on a settled single-leg market where the leg lost', () => {
      const html = renderHtml(
        <FuturesHero
          atlas
          resolved
          resolvedWon={false}
          resolvedLost
          name="Will Democrats sweep all swing state Governor races?"
          probability={0}
          outcomeName="Yes"
          openingProbability={0.38}
          sourceCount={1}
          categoryLabel="Politics"
        />,
      );

      expect(html).toContain('>✗ Lost<');
      expect(html).toContain('>Yes<');
      expect(html).toContain('data-testid="atlas-opening-chance"');
      expect(html).toContain('>38%<');
    });
  });

  describe('AtlasDetailsSheet shared component', () => {
    it('renders exact PT observation times, attribution, original market link, and settlement rules', () => {
      const html = renderHtml(
        <AtlasDetailsSheet
          open
          onClose={() => {}}
          subjectName="Yes"
          marketTitle="Will Democrats sweep all swing state Governor races"
          isSettled
          settledResult="won"
          openingProbability={0.38}
          renderedOpening={38}
          lastProbability={0.58}
          renderedLast={58}
          lastObservedAt="2026-11-03T08:55:57Z"
          selectedObservation={{
            probability: 0.58,
            observedAt: '2026-11-03T08:55:57Z',
          }}
          resolutionDate="2026-11-03T15:00:00Z"
          source="kalshi"
          sourceCount={1}
          externalId="KXDEMSWINGSTATEGOVSWEEP-26NOV03"
          rulesText="If Democrats win the governorships of ALL of the following states, the market resolves to Yes."
        />,
      );

      expect(html).toContain('role="dialog"');
      expect(html).toContain('aria-modal="true"');
      expect(html).toContain('>✓ Won<');
      expect(html).toContain('data-testid="atlas-details-opening"');
      expect(html).toContain('>38%<');
      expect(html).toContain('Nov 3, 2026, 12:55:57 AM PT');
      expect(html).toContain('>58%<');
      expect(html).toContain('Nov 3, 2026, 7:00 AM PT');
      expect(html).toContain('>Kalshi<');
      expect(html).toContain('href="https://kalshi.com/markets/kxdemswingstategovsweep"');
      expect(html).toContain('If Democrats win the governorships');
      expect(html).not.toContain('data-testid="atlas-details-settled-at"');
      expect(html).not.toContain('data-testid="atlas-details-last-observation"');
    });

    it('withholds opening chance silently when the market is multi-venue and omits original-market row for numeric external IDs', () => {
      const html = renderHtml(
        <AtlasDetailsSheet
          open
          onClose={() => {}}
          subjectName="Adam Hamilton"
          marketTitle="Kansas Senate winner"
          openingProbability={0.52}
          lastProbability={0.97}
          source="polymarket"
          sourceCount={2}
          externalId="65536371"
        />,
      );

      expect(html).not.toContain('data-testid="atlas-details-opening"');
      expect(html).toContain('2 sources');
      expect(html).not.toContain('Both Kalshi and Polymarket');
      expect(html).toContain('data-testid="atlas-details-last-observation"');
      expect(html).toContain('>97%<');
      expect(html).not.toContain('data-testid="atlas-details-original-market"');
      expect(html).not.toContain('65536371');
    });

    it('opens on one tap from FuturesHero, locks body scroll while open, and closes on Close button click', async () => {
      function Harness() {
        const [open, setOpen] = useState(false);
        return (
          <div>
            <FuturesHero
              atlas
              name="Closest Governor race in 2026?"
              probability={0.29}
              rendered={29}
              outcomeName="Florida"
              categoryLabel="Politics"
              onOpenDetails={() => setOpen(true)}
            />
            <AtlasDetailsSheet
              open={open}
              onClose={() => setOpen(false)}
              subjectName="Florida"
              marketTitle="Closest Governor race in 2026"
              lastProbability={0.29}
              renderedLast={29}
              lastObservedAt="2026-11-03T08:55:57Z"
              source="kalshi"
              externalId="KXGOVCLOSEST-26-FL"
            />
          </div>
        );
      }

      const container = document.createElement('div');
      document.body.appendChild(container);
      const root = createRoot(container);
      try {
        await act(async () => {
          root.render(<Harness />);
        });
        expect(container.querySelector('[data-testid="atlas-details-sheet"]')).toBeNull();
        expect(document.body.style.overflow).toBe('');

        const trigger = container.querySelector(
          '[data-testid="atlas-details-trigger"]',
        ) as HTMLButtonElement;
        expect(trigger).not.toBeNull();

        await act(async () => {
          trigger.click();
        });
        expect(container.querySelector('[data-testid="atlas-details-sheet"]')).not.toBeNull();
        expect(document.body.style.overflow).toBe('hidden');

        const closeBtn = container.querySelector(
          '[data-testid="atlas-details-close"]',
        ) as HTMLButtonElement;
        expect(closeBtn).not.toBeNull();

        await act(async () => {
          closeBtn.click();
        });
        expect(container.querySelector('[data-testid="atlas-details-sheet"]')).toBeNull();
        expect(document.body.style.overflow).toBe('');
      } finally {
        await act(async () => {
          root.unmount();
        });
        container.remove();
      }
    });
  });
});
