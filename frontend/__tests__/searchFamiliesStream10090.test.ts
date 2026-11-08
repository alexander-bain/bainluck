/**
 * #10090 — Search's futures FAMILIES re-price live, like its flat cards (#12401).
 *
 * A family draws a headline and member markets, each a `FuturesMarket` with
 * its own rows. One id can appear both as a family row and as a flat card, with
 * different rows; each occurrence is re-priced by its OWN rows, never swapped
 * for the other's.
 */
import {
  adoptSearchPriceCards, patchSearchFamilies, patchSearchFutures, searchAnswerMarkets, type SearchPriceBook,
} from '@/lib/searchFuturesStream';
import type { DiscoverPriceCards } from '@/lib/discover/priceRefresh';
import type { FeedItem, FuturesFamily, FuturesMarket, FuturesOutcome } from '@/lib/types';

const row = (id: number, probability: number | null): FuturesOutcome =>
  ({ id, name: String(id), probability, american_odds: null, rank: null, rank_change_24h: null,
     probability_change_24h: null, movement: null, opening_probability: null,
     opening_american_odds: null, is_winner: null }) as FuturesOutcome;

const market = (id: number, rows: FuturesOutcome[], over: Partial<FuturesMarket> = {}): FuturesMarket => ({
  id, name: `m${id}`, description: null, sport: null, sport_name: null, category: null,
  llm_sport_category: null, status: 'open', source: 'kalshi', external_id: null,
  mutually_exclusive: true, commence_time: null, resolution_date: null, outcome_count: rows.length,
  created_at: null, updated_at: null, top_outcomes: rows, ...over,
}) as FuturesMarket;

const family = (headline: FuturesMarket, members: FuturesMarket[]): FuturesFamily =>
  ({ family_key: `f${headline.id}`, label: 'Fed', headline, members, more_count: 0, member_count: members.length });

const answer = (id: number, rows: { id: number; p: number }[]): DiscoverPriceCards => ({
  built_at: 1,
  dispositions: { [`futures-${id}`]: 'updated' },
  items: [{ type: 'futures', data: { id, source: 'kalshi', status: 'open',
    top_outcomes: rows.map((r) => ({ id: r.id, name: String(r.id), probability: r.p, rank: null, movement: null,
      price_revision_at: '2026-11-08T22:40:00Z' })) } } as unknown as FeedItem],
});

const patcher = (book: SearchPriceBook) => (m: FuturesMarket) => patchSearchFutures(m, book);

test('the stream covers every market the answer draws, families included', () => {
  const flat = market(1, [row(11, 0.5)]);
  const head = market(2, [row(21, 0.6)]);
  const member = market(3, [row(31, 0.2)]);
  expect(searchAnswerMarkets([flat], [family(head, [member])]).map((m) => m.id)).toEqual([1, 2, 3]);
});

test('a family headline and its members re-price by their own rows', () => {
  const head = market(2, [row(21, 0.6), row(22, 0.4)]);
  const member = market(3, [row(31, 0.2)]);
  const fams = [family(head, [member])];
  let book: SearchPriceBook = new Map();
  book = adoptSearchPriceCards(book, [head, member], answer(2, [{ id: 21, p: 0.65 }, { id: 22, p: 0.35 }]), new Set([2]));
  book = adoptSearchPriceCards(book, [head, member], answer(3, [{ id: 31, p: 0.25 }]), new Set([3]));
  const [live] = patchSearchFamilies(fams, patcher(book));
  expect(live.headline.top_outcomes!.map((o) => o.probability)).toEqual([0.65, 0.35]);
  expect(live.members[0].top_outcomes![0].probability).toBe(0.25);
  expect(live.label).toBe('Fed');
});

test('one id drawn twice keeps each occurrence\'s own rows', () => {
  // The family shows two legs of market 2; the flat card shows a different one.
  const inFamily = market(2, [row(21, 0.6), row(22, 0.3)]);
  const flat = market(2, [row(23, 0.1)]);
  const book = adoptSearchPriceCards(new Map(), [inFamily, flat], answer(2, [{ id: 21, p: 0.62 }, { id: 23, p: 0.12 }]), new Set([2]));
  const patch = patcher(book);
  expect(patch(inFamily).top_outcomes!.map((o) => [o.id, o.probability])).toEqual([[21, 0.62], [22, 0.3]]);
  expect(patch(flat).top_outcomes!.map((o) => [o.id, o.probability])).toEqual([[23, 0.12]]);
});

test('nothing moved returns the same families array and objects', () => {
  const fams = [family(market(2, [row(21, 0.6)]), [market(3, [row(31, 0.2)])])];
  const empty: SearchPriceBook = new Map();
  expect(patchSearchFamilies(fams, patcher(empty))).toBe(fams);
  const book = adoptSearchPriceCards(empty, [fams[0].headline], answer(2, [{ id: 21, p: 0.6 }]), new Set([2]));
  expect(patchSearchFamilies(fams, patcher(book))).toBe(fams);
});

test('a settled family row keeps its served price', () => {
  const settled = market(3, [row(31, 1)], { status: 'resolved' });
  const fams = [family(market(2, [row(21, 0.6)]), [settled])];
  const book = adoptSearchPriceCards(new Map(), [settled], answer(3, [{ id: 31, p: 0.5 }]), new Set([3]));
  expect(patchSearchFamilies(fams, patcher(book))[0].members[0]).toBe(settled);
});
