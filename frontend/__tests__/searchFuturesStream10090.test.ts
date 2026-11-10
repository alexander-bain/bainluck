/**
 * #10090 — Search's futures cards re-price from `/api/feed/price-cards`.
 *
 * The specimen is real: `/api/events/search?q=chiefs` on Nov 8 served
 * "NFL: 2027 Champion" (129037) with five rows, and `price-cards` for the same
 * id answered with three of them (the feed scorer's own top outcomes) and a
 * Kansas City row at 0.135 against Search's 0.13. The card must re-price the
 * three shared rows and keep its other two.
 */
import {
  adoptSearchPriceCards, patchSearchFutures, searchFuturesStreamable, type SearchPriceBook,
} from '@/lib/searchFuturesStream';
import type { DiscoverPriceCards } from '@/lib/discover/priceRefresh';
import type { FeedItem, FuturesMarket, FuturesOutcome } from '@/lib/types';

const row = (id: number, name: string, probability: number | null): FuturesOutcome =>
  ({ id, name, probability, american_odds: null, rank: null, rank_change_24h: null,
     probability_change_24h: null, movement: null, opening_probability: null,
     opening_american_odds: null, is_winner: null }) as FuturesOutcome;

const market = (over: Partial<FuturesMarket> = {}): FuturesMarket => ({
  id: 129037, name: 'NFL: 2027 Champion', description: null, sport: null, sport_name: null,
  category: null, llm_sport_category: 'football', status: 'open', source: 'polymarket',
  external_id: null, mutually_exclusive: true, commence_time: null, resolution_date: null,
  outcome_count: 32, created_at: null, updated_at: null,
  top_outcomes: [
    row(1709101, 'Kansas City', 0.13), row(1709109, 'Buffalo', 0.132), row(1709102, 'Baltimore', 0.075),
    row(1709110, 'Detroit', 0.07), row(1709111, 'Philadelphia', 0.065),
  ],
  ...over,
}) as FuturesMarket;

const card = (rows: { id: number; p: number | null; rev?: string | null }[], over: Record<string, unknown> = {}): FeedItem =>
  ({ type: 'futures', data: {
    id: 129037, name: 'NFL: 2027 Champion', source: 'polymarket', status: 'open',
    top_outcomes: rows.map((r) => ({ id: r.id, name: String(r.id), probability: r.p, rank: null, movement: null,
      price_revision_at: r.rev === undefined ? '2026-11-08T21:40:00.000000+00:00' : r.rev })),
    ...over,
  } }) as unknown as FeedItem;

const answer = (items: FeedItem[], disposition = 'updated'): DiscoverPriceCards => ({
  items, built_at: 1, dispositions: Object.fromEntries(items.map((i) => [`futures-${(i.data as { id: number }).id}`, disposition])) as DiscoverPriceCards['dispositions'],
});

const empty: SearchPriceBook = new Map();
const ASKED = new Set([129037]);

test('the shared rows re-price and the card keeps the rows the fresh body does not carry', () => {
  const m = market();
  const book = adoptSearchPriceCards(empty, [m], answer([card([
    { id: 1709101, p: 0.135 }, { id: 1709109, p: 0.132 }, { id: 1709780, p: 0.4 },
  ])]), ASKED);
  const shown = patchSearchFutures(m, book);
  expect(shown.top_outcomes!.map((o) => [o.id, o.probability])).toEqual([
    [1709101, 0.135], [1709109, 0.132], [1709102, 0.075], [1709110, 0.07], [1709111, 0.065],
  ]);
  // The fresh body's own row that Search does not show is never added.
  expect(shown.top_outcomes!.some((o) => o.id === 1709780)).toBe(false);
  expect(shown.prices_updated_at).toBe(m.prices_updated_at);
});

test('a leg never goes backwards in revision', () => {
  const m = market();
  const newer = adoptSearchPriceCards(empty, [m], answer([card([{ id: 1709101, p: 0.14, rev: '2026-11-08T21:41:00Z' }])]), ASKED);
  const older = adoptSearchPriceCards(newer, [m], answer([card([{ id: 1709101, p: 0.12, rev: '2026-11-08T21:39:00Z' }])]), ASKED);
  expect(older).toBe(newer);
  expect(patchSearchFutures(m, older).top_outcomes![0].probability).toBe(0.14);
  // An undated leg cannot replace a dated one either.
  const undated = adoptSearchPriceCards(newer, [m], answer([card([{ id: 1709101, p: 0.11, rev: null }])]), ASKED);
  expect(undated).toBe(newer);
});

test('a withheld price (null) is adopted: the server withdrew it', () => {
  const m = market();
  const book = adoptSearchPriceCards(empty, [m], answer([card([{ id: 1709101, p: null }])]), ASKED);
  expect(patchSearchFutures(m, book).top_outcomes![0].probability).toBeNull();
});

test.each([
  ['a disposition other than updated', answer([card([{ id: 1709101, p: 0.2 }])], 'withheld'), ASKED],
  ['a different source', answer([card([{ id: 1709101, p: 0.2 }], { source: 'kalshi' })]), ASKED],
  ['a settled card', answer([card([{ id: 1709101, p: 1 }], { status: 'resolved', winner: 'Kansas City' })]), ASKED],
  ['an id that was not asked for', answer([card([{ id: 1709101, p: 0.2 }])]), new Set<number>()],
])('nothing is adopted from %s', (_label, response, asked) => {
  expect(adoptSearchPriceCards(empty, [market()], response as DiscoverPriceCards, asked as Set<number>)).toBe(empty);
});

test('only open Kalshi/Polymarket cards stream, and never a related-game listing', () => {
  expect(searchFuturesStreamable(market())).toBe(true);
  expect(searchFuturesStreamable(market({ status: 'resolved' }))).toBe(false);
  expect(searchFuturesStreamable(market({ source: 'draftkings' }))).toBe(false);
  expect(searchFuturesStreamable(market({ related_game_listing: { event_id: 1 } as FuturesMarket['related_game_listing'] }))).toBe(false);
  // A settled search card ignores whatever the book holds for it.
  const book = adoptSearchPriceCards(empty, [market()], answer([card([{ id: 1709101, p: 0.2 }])]), ASKED);
  const settled = market({ status: 'resolved' });
  expect(patchSearchFutures(settled, book)).toBe(settled);
});

test('an unchanged answer returns the same objects, so nothing re-renders', () => {
  const m = market();
  const book = adoptSearchPriceCards(empty, [m], answer([card([{ id: 1709101, p: 0.13 }])]), ASKED);
  expect(patchSearchFutures(m, book)).toBe(m);
  const again = adoptSearchPriceCards(book, [m], answer([card([{ id: 1709101, p: 0.13 }])]), ASKED);
  expect(again).toBe(book);
  expect(patchSearchFutures(m, empty)).toBe(m);
});

test('a card that carries only `outcomes` is patched there', () => {
  const m = market({ top_outcomes: undefined, outcomes: [row(1709101, 'Kansas City', 0.13)] });
  const book = adoptSearchPriceCards(empty, [m], answer([card([{ id: 1709101, p: 0.15 }])]), ASKED);
  const shown = patchSearchFutures(m, book);
  expect(shown.outcomes![0].probability).toBe(0.15);
  expect(shown.top_outcomes).toBeUndefined();
});
