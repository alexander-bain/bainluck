import '../helpers/minimalDom';
import React, { act } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createRoot } from 'react-dom/client';
import { FuturesCard, FuturesCompactRow } from '@/components/discover/FuturesCard';
import type { FeedFuturesData, FeedItem } from '@/lib/types';

jest.mock('next/link', () => ({
  __esModule: true,
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
    <a href={href} {...props}>{children}</a>,
}));

function card(delta: Partial<FeedFuturesData> = {}): FeedFuturesData {
  return {
    id: 712, name: 'Who wins the award?', source: 'kalshi', status: 'open',
    llm_sport_category: 'entertainment', resolution_date: '2035-01-01T00:00:00Z',
    top_outcomes: [{ id: 11, name: 'Alice', probability: 0.99, movement: 0.2 }],
    outcome_count: 2, ...delta,
  } as FeedFuturesData;
}
function item(data: FeedFuturesData): FeedItem {
  return { type: 'futures', score: 88, headline: 'Alice leads at 99%', data } as FeedItem;
}
function full(data: FeedFuturesData) {
  return <FuturesCard data={data} item={item(data)} liked={false} setLiked={() => {}} trending />;
}
function text(markup: string) { return markup.replace(/<[^>]*>/g, ' '); }

describe('held Discover futures cards consume assigned results', () => {
  it('replaces the mounted forecast with the assigned winner without a stale caption', () => {
    const host = document.createElement('div');
    document.body.appendChild(host);
    const root = createRoot(host);
    try {
      act(() => root.render(full(card())));
      expect(host.textContent).toContain('99%');
      act(() => root.render(full(card({ resolved: true, winner: 'Bob', top_outcomes: [] }))));
      expect(host.textContent).toContain('Bob');
      expect(host.textContent).toContain('Resolved');
      expect(host.textContent).not.toMatch(/99%|Alice/);
      const markup = renderToStaticMarkup(full(card({ resolved: true, winner: 'Bob', top_outcomes: [] })));
      expect(markup).toContain('href="/futures/712"');
    } finally { act(() => root.unmount()); document.body.removeChild(host); }
  });

  it('assigned winner outranks a carried stale leader or chart archetype', () => {
    const data = card({ winner: ' Bob ', discover_card: { format: 'threshold_heatmap' } } as Partial<FeedFuturesData>);
    const html = renderToStaticMarkup(full(data));
    expect(html).toContain('data-card-format="resolved"');
    expect(text(html)).toContain('Bob');
    expect(text(html)).not.toContain('Alice');
    expect(html).not.toContain('futures-hero-probability');
  });

  it.each(['resolved', 'closed', 'settled', 'finalized', 'final', 'CLOSED'])('unknown winner under assigned %s is honestly Resolved', status => {
    const html = renderToStaticMarkup(full(card({ status, top_outcomes: [], winner: undefined })));
    expect(text(html)).toContain('Resolved');
    expect(html).not.toContain('futures-assigned-result');
    expect(html).not.toContain('futures-hero-probability');
    expect(text(html)).not.toMatch(/Alice|won|99%/);
  });

  it('resolved flag handles all-loss or unnamed results without inventing a winner', () => {
    const html = renderToStaticMarkup(full(card({ resolved: true, status: 'open', winner: ' ', top_outcomes: [] })));
    expect(text(html)).toContain('Resolved');
    expect(text(html)).not.toContain('Alice');
    expect(html).not.toContain('futures-assigned-result');
  });

  it('old date and certain-looking open price cannot fabricate an assigned result', () => {
    const html = renderToStaticMarkup(full(card({ resolution_date: '2020-01-01T00:00:00Z',
      top_outcomes: [{ id: 11, name: 'Alice', probability: 1, movement: null, rank: 1 }] })));
    expect(html).not.toContain('data-card-format="resolved"');
    expect(html).toContain('futures-hero-probability');
  });

  it.each([['Bob', 'Resolved · Bob'], [undefined, 'Resolved']])('grouped compact row presents assigned %s without an obsolete percent', (winner, result) => {
    const data = card({ resolved: true, winner, top_outcomes: [] });
    const html = renderToStaticMarkup(<FuturesCompactRow data={data} item={item(data)} />);
    expect(text(html)).toContain(result);
    expect(html).toContain('compact-row-assigned-result');
    expect(text(html)).not.toMatch(/Alice|99%/);
    expect(html).toContain('/futures/712');
  });
});
