import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import RelatedByTag from '@/components/RelatedByTag';
import { formatAtlasAttribution } from '@/components/atlas/atlasStateCopy';

let swrPayload: unknown;

jest.mock('swr', () => ({
  __esModule: true,
  default: () => ({ data: swrPayload, error: undefined, isLoading: false }),
}));

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
    const defaultHtml = renderToStaticMarkup(
      <RelatedByTag
        tags={['sport:politics']}
        excludeId={999}
        excludeType="futures"
        limit={4}
        title="More Politics"
      />,
    );
    const explicitFalseHtml = renderToStaticMarkup(
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
    const html = renderToStaticMarkup(
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

  it('formats attribution source labels without venue prices or comparison prose', () => {
    expect(formatAtlasAttribution('kalshi')).toBe('Kalshi');
    expect(formatAtlasAttribution('polymarket')).toBe('Polymarket');
    expect(formatAtlasAttribution('kalshi', { sourceCount: 2 })).toBe(
      'Both Kalshi and Polymarket',
    );
    expect(
      formatAtlasAttribution('kalshi', {
        sourceLabels: ['Kalshi', 'Polymarket'],
      }),
    ).toBe('Kalshi · Polymarket');
  });
});
