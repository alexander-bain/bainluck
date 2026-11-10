/**
 * #10090 decision (b) (Fable, Nov 9): an open Search page shows FINAL when its
 * live game ends.
 *
 * Production, Nov 9: the Hawks vs Lakers card on /search?q=lakers froze on its
 * last live reading ("4th Quarter · Hawks 114 0% · Lakers 124 100%") for 18
 * minutes after the server stamped the game completed, while a fresh search
 * showed "FINAL 114 HAWKS — 124 LAKERS". The adopt rule refused any card whose
 * status differed from the served one. Now a live game whose card says it
 * finished takes status, final score and `completed_at` from that one read.
 */
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { adoptSearchEventCards, patchSearchEvent, type SearchEventBook } from '@/lib/searchEventsStream';
import type { DiscoverPriceCards } from '@/lib/discover/priceRefresh';
import type { Event, FeedItem } from '@/lib/types';

jest.mock('next/link', () => {
  const ReactLib = require('react');
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement('a', { href, ...props }, children),
  };
});
jest.mock('@/hooks', () => ({ useAnalytics: () => ({ trackEventCardClick: jest.fn() }) }));

import EventCard from '@/components/EventCard';

const ID = 15344868;
const ASKED = new Set([ID]);
const empty: SearchEventBook = new Map();

const live = (over: Partial<Event> = {}): Event => ({
  id: ID, external_id: 'x', sport: 'basketball_nba', home_team: 'Atlanta Hawks',
  away_team: 'Los Angeles Lakers', commence_time: '2025-03-04T00:00:00Z', status: 'live',
  home_score: 114, away_score: 124,
  current_odds: { home_probability: 0.0, away_probability: 1.0, spread: -2.5 } as Event['current_odds'],
  opening_odds: { home_probability: 0.56, away_probability: 0.44 } as Event['opening_odds'],
  hero_probability: 0.0, hero_probability_away: 1.0,
  espn: { period: '4th Quarter', game_clock: '0:14', broadcast: 'Spectrum Sports Net' },
  ...over,
}) as Event;

const card = (over: Record<string, unknown> = {}): FeedItem => ({
  type: 'event',
  data: {
    id: ID, status: 'completed', home_score: 114, away_score: 124, completed_at: '2025-03-04T02:23:08Z',
    current_odds: { home_probability: 0.56, away_probability: 0.44 },
    hero_probability: 0.56, hero_probability_away: 0.44, hero_probability_source: 'settled',
    blend_fold_revision: { [String(ID)]: 9001 }, hero_probability_observed_at: null, live_state: null,
    ...over,
  },
}) as unknown as FeedItem;

const answer = (items: FeedItem[], disposition = 'updated'): DiscoverPriceCards => ({
  built_at: 1, items,
  dispositions: Object.fromEntries(items.map((i) => [`event-${(i.data as { id: number }).id}`, disposition])) as DiscoverPriceCards['dispositions'],
});

beforeAll(() => { jest.useFakeTimers(); jest.setSystemTime(new Date('2025-03-04T02:40:00Z')); });
afterAll(() => jest.useRealTimers());

test('a live game whose card says completed takes status, final score and stamp from that read', () => {
  const e = live({ home_score: 111, away_score: 121 });
  const book = adoptSearchEventCards(empty, [e], answer([card()]), ASKED);
  const shown = patchSearchEvent(e, book);
  expect(shown.status).toBe('completed');
  expect([shown.home_score, shown.away_score]).toEqual([114, 124]);
  expect(shown.completed_at).toBe('2025-03-04T02:23:08Z');
  // The live clock goes; the broadcast stays; probabilities stay served.
  expect(shown.espn).toEqual({ broadcast: 'Spectrum Sports Net' });
  expect(shown.current_odds).toBe(e.current_odds);
  expect(shown.opening_odds).toBe(e.opening_odds);
});

test('the open card renders exactly what a fresh search shows', () => {
  const e = live();
  const shown = patchSearchEvent(e, adoptSearchEventCards(empty, [e], answer([card()]), ASKED));
  const fresh = live({ status: 'completed', completed_at: '2025-03-04T02:23:08Z', espn: { broadcast: 'Spectrum Sports Net' } });
  const html = renderToStaticMarkup(<EventCard event={shown} />);
  expect(html).toBe(renderToStaticMarkup(<EventCard event={fresh} />));
  expect(html).not.toContain('4th Quarter');
  expect(html).not.toBe(renderToStaticMarkup(<EventCard event={e} />));
});

test('a finish is terminal: a later live card never reopens the game', () => {
  const e = live();
  const done = adoptSearchEventCards(empty, [e], answer([card()]), ASKED);
  const after = adoptSearchEventCards(done, [e], answer([card({
    status: 'live', home_score: 116, away_score: 124, live_state: { period: '4th Quarter', game_clock: '0:05' },
    hero_probability_source: 'blend', blend_fold_revision: { [String(ID)]: 9002 },
  })]), ASKED);
  expect(after).toBe(done);
  expect(patchSearchEvent(e, after).status).toBe('completed');
});

test('a result the server has not resolved yet (withheld) is not adopted', () => {
  const e = live();
  expect(adoptSearchEventCards(empty, [e], answer([card()], 'withheld'), ASKED)).toBe(empty);
});

test('only a live game finishes this way; a scheduled one still refuses a status change', () => {
  const e = live({ status: 'scheduled', home_score: null, away_score: null, espn: undefined });
  const book = adoptSearchEventCards(empty, [e], answer([card()]), ASKED);
  expect(book).toBe(empty);
  expect(patchSearchEvent(e, book)).toBe(e);
});

test('closed counts as finished; an unknown status like "final" still does not', () => {
  const e = live();
  expect(patchSearchEvent(e, adoptSearchEventCards(empty, [e], answer([card({ status: 'closed' })]), ASKED)).status)
    .toBe('closed');
  expect(adoptSearchEventCards(empty, [e], answer([card({ status: 'final' })]), ASKED)).toBe(empty);
});
