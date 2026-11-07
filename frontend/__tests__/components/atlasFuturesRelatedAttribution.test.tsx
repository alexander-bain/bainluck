/** @jest-environment jsdom */

import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import RelatedByTag from '@/components/RelatedByTag';
import { formatAtlasAttribution } from '@/components/atlas/atlasStateCopy';

(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;

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

let swrPayload: unknown;
let searchParamsStr = '';
let futuresMarketPayload: unknown;

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
        data: undefined,
        error: undefined,
        isLoading: false,
        mutate: () => {},
      };
    }
    return { data: swrPayload, error: undefined, isLoading: false, mutate: () => {} };
  },
}));

import FuturesDetailPage from '../../app/futures/[id]/page';

const SAMPLE_PAYLOAD = {
  items: [
    {
      type: 'futures',
      data: {
        id: 109085,
        name: 'Will Republicans win the Kansas Senate seat?',
        outcome_count: 2,
        top_outcomes: [
          { name: 'Republican', probability: 0.97, rendered_percent: 97 },
          { name: 'Democrat', probability: 0.02, rendered_percent: 2 },
        ],
      },
    },
    {
      type: 'futures',
      data: {
        id: 108629,
        name: 'Which state will have the closest Governor race?',
        outcome_count: 24,
        discover_card: {
          distribution_outcomes: [
            { label: 'Kansas', probability: 0.21 },
            { label: 'Wisconsin', probability: 0.14 },
            { label: 'Nevada', probability: 0.12 },
            { label: 'Ohio', probability: 0.08 },
          ],
          remaining_outcome_count: 20,
        },
        top_outcomes: [
          { name: 'Kansas', probability: 0.21, rendered_percent: 21 },
          { name: 'Wisconsin', probability: 0.14, rendered_percent: 14 },
          { name: 'Nevada', probability: 0.12, rendered_percent: 12 },
        ],
      },
    },
    {
      type: 'concept',
      data: {
        key: 'event:ufc:320',
        domain: 'ufc',
        name: 'Who headlines UFC 320?',
        leader: { name: 'Khamzat Chimaev', probability: 0.62 },
      },
    },
  ],
};

describe('Step F4 — RelatedByTag and attribution restyle (#883)', () => {
  beforeEach(() => {
    swrPayload = SAMPLE_PAYLOAD;
  });

  it('keeps default (atlas=false) markup byte-identical when atlas is omitted', () => {
    const defaultHtml = renderHtml(
      <RelatedByTag
        tags={['sport:politics']}
        excludeId={999}
        excludeType="futures"
        limit={4}
        title="More Politics"
      />,
    );
    const explicitFalseHtml = renderHtml(
      <RelatedByTag
        tags={['sport:politics']}
        excludeId={999}
        excludeType="futures"
        limit={4}
        title="More Politics"
        atlas={false}
      />,
    );

    expect(defaultHtml).toBe(explicitFalseHtml);
    expect(defaultHtml).not.toContain('atlas-related-eyebrow');
    expect(defaultHtml).toContain('Will Republicans win the Kansas Senate seat?');
  });

  it('renders Keep exploring eyebrow and predicate headings when atlas=true while preserving card fields', () => {
    const html = renderHtml(
      <RelatedByTag
        tags={['sport:politics']}
        excludeId={999}
        excludeType="futures"
        limit={4}
        title="More Politics"
        atlas
      />,
    );

    expect(html).toContain('data-testid="atlas-related-eyebrow"');
    expect(html).toContain('Keep exploring');
    expect(html).toContain('data-testid="related-by-tag-heading"');
    expect(html).toContain('More Politics');
    // Trailing question marks are stripped on Atlas related cards
    expect(html).toContain('Will Republicans win the Kansas Senate seat</span>');
    expect(html).toContain('Which state will have the closest Governor race</span>');
    expect(html).toContain('Who headlines UFC 320</span>');
    expect(html).toContain('data-testid="related-card-more"');
    expect(html).toContain('+21 more');
  });

  it('formats attribution source labels without venue prices or comparison prose and uses a neutral fallback when sourceLabels is empty', () => {
    expect(formatAtlasAttribution('kalshi')).toBe('Kalshi');
    expect(formatAtlasAttribution('polymarket')).toBe('Polymarket');
    expect(formatAtlasAttribution('kalshi', { sourceCount: 2 })).toBe(
      '2 sources',
    );
    expect(
      formatAtlasAttribution('datagolf', { sourceCount: 2, sourceLabels: [] }),
    ).toBe('2 sources');
    expect(
      formatAtlasAttribution('odds_api', { sourceCount: 3, sourceLabels: [] }),
    ).toBe('3 sources');
    expect(
      formatAtlasAttribution('kalshi', {
        sourceLabels: ['Kalshi', 'Polymarket'],
      }),
    ).toBe('Kalshi · Polymarket');
  });

  it('renders the attribution footer under ?atlas=1 and opens AtlasDetailsSheet when Market details is clicked', async () => {
    searchParamsStr = 'atlas=1';
    futuresMarketPayload = {
      id: 108629,
      name: 'Which state will have the closest Governor race?',
      status: 'open',
      mutually_exclusive: true,
      source: 'kalshi',
      source_count: 1,
      external_id: 'KXGOVCLOSEST-26-FL',
      created_at: '2026-10-01T00:00:00Z',
      updated_at: '2026-11-03T18:00:00Z',
      outcomes: [
        {
          id: 1,
          name: 'Florida',
          probability: 0.29,
          rendered_percent: 29,
          rank: 1,
          is_winner: false,
          last_updated: '2026-11-03T18:00:00Z',
        },
        {
          id: 2,
          name: 'Wisconsin',
          probability: 0.21,
          rendered_percent: 21,
          rank: 2,
          is_winner: false,
          last_updated: '2026-11-03T18:00:00Z',
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

      const footer = container.querySelector(
        '[data-testid="atlas-attribution-footer"]',
      );
      expect(footer).not.toBeNull();
      expect(
        container.querySelector('[data-testid="atlas-attribution-source"]')?.textContent,
      ).toBe('Kalshi');
      expect(container.querySelector('[data-testid="atlas-details-sheet"]')).toBeNull();

      const detailsButton = container.querySelector(
        '[data-testid="atlas-attribution-details-button"]',
      ) as HTMLButtonElement;
      expect(detailsButton).not.toBeNull();
      expect(detailsButton.textContent).toBe('Market details');

      await act(async () => {
        detailsButton.click();
      });

      expect(container.querySelector('[data-testid="atlas-details-sheet"]')).not.toBeNull();
    } finally {
      await act(async () => {
        root.unmount();
      });
      container.remove();
      searchParamsStr = '';
    }
  });

  it('places the body slot (two-sided dial) above Keep exploring and removes the duplicate Final Results table under ?atlas=1 per Decide 47: E', async () => {
    searchParamsStr = 'atlas=1';
    futuresMarketPayload = {
      id: 109085,
      name: 'Kansas Senate winner?',
      status: 'resolved',
      mutually_exclusive: true,
      llm_sport_category: 'politics',
      source: 'kalshi',
      source_count: 1,
      external_id: 'SENATEKS-26',
      created_at: '2026-06-01T00:00:00Z',
      updated_at: '2026-11-04T06:00:00Z',
      outcomes: [
        {
          id: 10,
          name: 'Adam Hamilton',
          probability: null,
          opening_probability: 0.12,
          rank: 1,
          is_winner: true,
          resolution_source: 'api_settlement',
          last_updated: '2026-11-04T06:00:00Z',
        },
        {
          id: 11,
          name: 'Roger Marshall',
          probability: null,
          opening_probability: 0.86,
          rank: 2,
          is_winner: false,
          resolution_source: 'api_settlement',
          last_updated: '2026-11-04T06:00:00Z',
        },
      ],
    };

    const html = renderHtml(<FuturesDetailPage params={{ id: '109085' }} />);
    searchParamsStr = '';

    const heroIdx = html.indexOf('data-testid="atlas-futures-hero"');
    const dialBodyIdx = html.indexOf('data-testid="atlas-duel-body"');
    const keepExploringIdx = html.indexOf('Keep exploring');
    const attributionIdx = html.indexOf('data-testid="atlas-attribution-footer"');

    expect(heroIdx).toBeGreaterThan(-1);
    expect(dialBodyIdx).toBeGreaterThan(heroIdx);
    expect(keepExploringIdx).toBeGreaterThan(dialBodyIdx);
    expect(attributionIdx).toBeGreaterThan(keepExploringIdx);
    expect(html).not.toContain('Final Results');
  });
});
