import type { FeedItem, FeedFuturesData } from '../../lib/types';
import type { DiscoverGroupedItem } from '../../components/discover/types';
import { adoptPriceCards, canAdoptPrice, groupedLeaves, marketResolved, projectPriceGroups, reconcilePriceBook, type PriceBook } from '../../lib/discover/priceRefresh';

const T1 = '2026-09-29T00:00:01.000001+00:00';
const T2 = '2026-09-29T00:00:02.000001+00:00';
const T3 = '2026-09-29T00:00:03.000001+00:00';
function market(id = 1, p = .4, clocks: Record<string, string | null> = { '10': T1, '20': T1 }, leader = 10): FeedItem {
  return { type: 'futures', score: 90, reason: 'Held reason', headline: 'Held headline', data: {
    id, name: 'Same question?', source: 'kalshi', group_id: 'g', canonical_market_key: 'k',
    status: 'open', outcome_observed_at: clocks, outcome_count: 2,
    top_outcomes: [{ id: leader, name: 'A', probability: p, price_observed_at: clocks[String(leader)] }],
  } } as unknown as FeedItem;
}
function event(rev: unknown = { '1': 3 }, stamp: string | null = T1, status = 'scheduled', quote: number | null = .5): FeedItem {
  return { type: 'event', score: 90, data: { id: 1, status, blend_fold_revision: rev,
    hero_probability_observed_at: stamp, current_odds: quote === null ? null : { home_probability: quote } } } as unknown as FeedItem;
}
function singles(...items: FeedItem[]): DiscoverGroupedItem[] { return items.map(item => ({ type: 'single', item })); }

test('one regressed outcome is not covered by a newer sibling, including microseconds', () => {
  expect(canAdoptPrice(market(1, .6, { '10': '2026-09-29T00:00:01.000000Z', '20': T3 }), market())).toBe(false);
  expect(canAdoptPrice(market(1, .6, { '10': T1, '20': T2 }), market())).toBe(true);
});
test('full raw vector permits top-N and normalization changes without borrowing a clock', () => {
  expect(canAdoptPrice(market(1, .7, { '10': T1, '20': T2 }, 20), market())).toBe(true);
  expect(canAdoptPrice(market(1, .7, { '10': T1, '20': T1 }), market())).toBe(false);
  expect(canAdoptPrice(market(1, .7, { '10': null, '20': T2 }), market())).toBe(false);
});
test('fold revisions precede observation clocks and unknown/incomparable revisions cannot win', () => {
  expect(canAdoptPrice(event({ '1': 4 }, T1), event({ '1': 3 }, T2))).toBe(true);
  expect(canAdoptPrice(event(null, T3), event())).toBe(false);
  expect(canAdoptPrice(event({ '1': 3, '2': 1 }, T3), event())).toBe(false);
});
test('same complete fold revision cannot rewrite its hero or resurrect a withdrawn quote', () => {
  expect(canAdoptPrice(event({ '1': 3 }, T1, 'scheduled', .7), event())).toBe(false);
  expect(canAdoptPrice(event({ '1': 3 }, T3, 'scheduled', .7), event())).toBe(false);
  expect(canAdoptPrice(event(), event({ '1': 3 }, null, 'scheduled', null))).toBe(false);
});
test('equal-vector terminal result can land without inventing an observation stamp', () => {
  expect(canAdoptPrice(event({ '1': 3 }, null, 'completed'), event())).toBe(true);
  expect(canAdoptPrice(event({ '1': 4 }, T3), event({ '1': 3 }, null, 'completed'))).toBe(false);
});
test('known final scores survive changed or missing scores, including a withheld response', () => {
  const held = event({ '1': 3 }, null, 'completed', null);
  Object.assign(held.data, { home_score: 3, away_score: 1 });
  for (const home of [2, null]) {
    const stale = event({ '1': 4 }, null, 'completed', null);
    Object.assign(stale.data, { home_score: home, away_score: 1 });
    expect(canAdoptPrice(stale, held, true)).toBe(false);
    expect(adoptPriceCards(new Map(), [held], { items: [stale], dispositions: { 'event-1': 'withheld' }, built_at: 101 }, new Set(['event-1'])).size).toBe(0);
  }
});
test('market terminal truth ignores elapsed resolution dates and preserves source identity', () => {
  const old = market();
  (old.data as FeedFuturesData).resolution_date = '2000-01-01T00:00:00Z';
  expect(marketResolved(old.data as FeedFuturesData)).toBe(false);
  const wrong = market(1, .8, { '10': T2, '20': T2 });
  (wrong.data as FeedFuturesData).source = 'polymarket';
  expect(canAdoptPrice(wrong, old)).toBe(false);
  (old.data as FeedFuturesData).status = 'closed';
  expect(canAdoptPrice(market(), old)).toBe(false);
});
test('a held settled winner cannot disappear or change inside another terminal body', () => {
  const held = market();
  Object.assign(held.data, { status: 'closed', resolved: true, winner: 'A' });
  for (const winner of [undefined, 'B']) {
    const next = market(1, .8, { '10': T3, '20': T3 });
    Object.assign(next.data, { status: 'settled', resolved: true, winner });
    expect(canAdoptPrice(next, held)).toBe(false);
  }
});
test.each([T1, null])('fresh withdrawal with clock %s keeps an independent fence against cached resurrection', stamp => {
  const held = market(), removed = market(1, .4, { '10': stamp, '20': T1 });
  (removed.data as FeedFuturesData).top_outcomes = [];
  const response = { items: [removed], dispositions: { 'futures-1': 'updated' as const }, built_at: 100 };
  let book = adoptPriceCards(new Map(), [held], response, new Set(['futures-1']));
  expect((book.get('futures-1')!.item.data as FeedFuturesData).top_outcomes).toEqual([]);
  // A newer sibling cannot republish the withdrawn leg at its old clock.
  const cached = market(1, .5, { '10': T1, '20': T2 });
  const reconciled = reconcilePriceBook(singles(cached), book);
  expect(reconciled).toBe(book);
  const projected = groupedLeaves(projectPriceGroups(singles(cached), book));
  expect(adoptPriceCards(book, projected, { ...response, items: [cached], built_at: 101 }, new Set(['futures-1']))).toBe(book);
  const genuinelyNew = market(1, .6, { '10': T2, '20': T2 });
  book = adoptPriceCards(book, projected, { ...response, items: [genuinelyNew], built_at: 102 }, new Set(['futures-1']));
  expect((book.get('futures-1')!.item.data as FeedFuturesData).top_outcomes[0].probability).toBe(.6);
});
test('an explicit null remains withdrawn when a different raw outcome advances', () => {
  const held = market(), removed = market(1, .4, { '10': T1, '20': T2 });
  (removed.data as FeedFuturesData).top_outcomes[0].probability = null;
  const response = { items: [removed], dispositions: { 'futures-1': 'updated' as const }, built_at: 100 };
  const book = adoptPriceCards(new Map(), [held], response, new Set(['futures-1']));
  expect((book.get('futures-1')!.item.data as FeedFuturesData).top_outcomes[0].probability).toBeNull();
  const cached = market(1, .5, { '10': T1, '20': T3 });
  expect(reconcilePriceBook(singles(cached), book)).toBe(book);
  const unknown = market(1, .4, { '10': null, '20': T1 });
  (unknown.data as FeedFuturesData).top_outcomes[0].probability = null;
  expect(canAdoptPrice(market(1, .6, { '10': null, '20': T2 }), unknown)).toBe(false);
});
test('fresh leaves update whole nested groups without editing membership, order or editorial copy', () => {
  const old = market(), sibling = market(2);
  const bundle = { type: 'bundle', headline: 'Held bundle', data: { id: 'bundle', title: 'Held title', items: [old, sibling], member_ids: [1, 2] } } as unknown as FeedItem;
  const groups = singles(bundle, market(3));
  const fresh = { ...market(1, .8, { '10': T2, '20': T2 }), headline: 'New editorial' };
  const book = adoptPriceCards(new Map(), groupedLeaves(groups), { items: [fresh, market(9)], dispositions: { 'futures-1': 'updated', 'futures-9': 'updated' }, built_at: 100 }, new Set(['futures-1']));
  const result = projectPriceGroups(groups, book);
  expect(groupedLeaves(result).map(item => (item.data as FeedFuturesData).id)).toEqual([1, 2, 3]);
  expect((groupedLeaves(result)[0].data as FeedFuturesData).top_outcomes[0].probability).toBe(.8);
  expect(groupedLeaves(result)[0].headline).toBe('Held headline');
  expect((result[0].item!.data as unknown as { title: string }).title).toBe('Held title');
});
test('ordinary t1 -> t3 -> t2 feed reads retain the newest accepted fence', () => {
  const t1 = market(), t3 = market(1, .8, { '10': T3, '20': T3 }), t2 = market(1, .6, { '10': T2, '20': T2 });
  let book: PriceBook = new Map([['futures-1', { item: t1, builtAt: 100 }]]);
  book = reconcilePriceBook(singles(t3), book);
  book = reconcilePriceBook(singles(t2), book);
  expect((projectPriceGroups(singles(t2), book)[0].item!.data as FeedFuturesData).top_outcomes[0].probability).toBe(.8);
});
test('explicit fresh withholding clears an expired event quote; cached same-vector feed cannot resurrect it', () => {
  const old = event(), withheld = event({ '1': 3 }, null, 'scheduled', null);
  let book = adoptPriceCards(new Map(), [old], { items: [withheld], dispositions: { 'event-1': 'withheld' }, built_at: 100 }, new Set(['event-1']));
  book = reconcilePriceBook(singles(old), book);
  expect((projectPriceGroups(singles(old), book)[0].item!.data as { current_odds: unknown }).current_odds).toBeNull();
});
test('unresolved, hidden, unsolicited and older response leaves cannot overwrite held state', () => {
  const old = market(), next = market(1, .8, { '10': T2, '20': T2 });
  const book: PriceBook = new Map([['futures-1', { item: old, builtAt: 100 }]]);
  expect(adoptPriceCards(book, [old], { items: [next], dispositions: { 'futures-1': 'unresolved' }, built_at: 101 }, new Set(['futures-1']))).toBe(book);
  expect(adoptPriceCards(book, [old], { items: [next], dispositions: { 'futures-1': 'updated' }, built_at: 99 }, new Set(['futures-1']))).toBe(book);
  expect(adoptPriceCards(book, [old], { items: [next], dispositions: { 'futures-1': 'updated' }, built_at: 101 }, new Set())).toBe(book);
});
