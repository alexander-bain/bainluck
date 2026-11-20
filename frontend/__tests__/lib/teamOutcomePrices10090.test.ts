/**
 * #10090 — the team page's season-futures rows re-price live by outcome id.
 *
 * `/api/feed/price-cards` returns a market's top outcomes only, so a team's leg
 * of a 30-way field never re-priced, and the team page is a 2.7-5.8 s read. The
 * page re-reads its rows through `/api/feed/outcome-prices` when their market
 * moves. These are the patch rules: never backwards, a refusal clears the number,
 * unknown changes nothing, row fields only.
 */
import { adoptOutcomePrices, patchTeamFuture, type OutcomePriceItem, type OutcomePricesResponse, type TeamOutcomeBook } from '@/lib/teamOutcomePrices';
import type { TeamFutureItem } from '@/lib/api';

const row = (over: Partial<TeamFutureItem> = {}): TeamFutureItem => ({
  outcome_id: 261567710, outcome_name: 'Los Angeles Lakers', market_id: 65677957,
  market_name: 'NBA: Teams to Win 40+ Games', market_tier: 5, category: 'basketball', source: 'polymarket',
  probability: 0.905, probability_change_24h: null, rank: 2, total_outcomes: 30,
  resolution_date: '2027-04-26T03:59:00+00:00', is_winner: false,
  matched_team: { id: 49, name: 'Los Angeles Lakers' },
  ...over,
}) as TeamFutureItem;

const price = (over: Partial<OutcomePriceItem> = {}): OutcomePriceItem => ({
  outcome_id: 261567710, market_id: 65677957, probability: 0.88, probability_change_24h: -0.025,
  rank: 3, total_outcomes: 30, is_winner: false, price_revision_at: '2025-06-15T18:30:12.345678+00:00',
  ...over,
});

const answer = (items: OutcomePriceItem[], dispositions?: Record<string, string>): OutcomePricesResponse => ({
  items, built_at: 1,
  dispositions: dispositions ?? Object.fromEntries(items.map((i) => [`outcome-${i.outcome_id}`, 'updated'])),
});
const ASKED = new Set([261567710]);
const empty: TeamOutcomeBook = new Map();

test('a fresh reading moves probability, 24h move, rank and field size together', () => {
  const book = adoptOutcomePrices(empty, answer([price()]), ASKED);
  const shown = patchTeamFuture(row(), book);
  expect([shown.probability, shown.probability_change_24h, shown.rank, shown.total_outcomes])
    .toEqual([0.88, -0.025, 3, 30]);
  // Everything else stays served.
  expect(shown.outcome_name).toBe('Los Angeles Lakers');
  expect(shown.market_tier).toBe(5);
});

test('never backwards: an older reading is ignored', () => {
  const held = adoptOutcomePrices(empty, answer([price()]), ASKED);
  const older = adoptOutcomePrices(held, answer([price({ probability: 0.5, price_revision_at: '2025-06-15T18:29:00Z' })]), ASKED);
  expect(older).toBe(held);
  const unstamped = adoptOutcomePrices(held, answer([price({ probability: 0.5, price_revision_at: null })]), ASKED);
  expect(unstamped).toBe(held);
  const newer = adoptOutcomePrices(held, answer([price({ probability: 0.86, price_revision_at: '2025-06-15T18:31:00Z' })]), ASKED);
  expect(patchTeamFuture(row(), newer).probability).toBe(0.86);
});

test('a withheld or closed leg clears the number instead of keeping a stale one', () => {
  for (const disposition of ['withheld', 'closed']) {
    const held = adoptOutcomePrices(empty, answer([price()]), ASKED);
    const refused = adoptOutcomePrices(held, answer([], { 'outcome-261567710': disposition }), ASKED);
    const shown = patchTeamFuture(row(), refused);
    expect([shown.probability, shown.probability_change_24h]).toEqual([null, null]);
  }
});

test('missing or unresolved changes nothing', () => {
  for (const disposition of ['missing', 'unresolved']) {
    const held = adoptOutcomePrices(empty, answer([price()]), ASKED);
    expect(adoptOutcomePrices(held, answer([], { 'outcome-261567710': disposition }), ASKED)).toBe(held);
  }
});

test('only requested outcomes are adopted, and a reading for another market never patches the row', () => {
  const other = price({ outcome_id: 999 });
  expect(adoptOutcomePrices(empty, answer([other]), ASKED)).toBe(empty);
  const crossed = adoptOutcomePrices(empty, answer([price({ market_id: 1 })]), ASKED);
  const served = row();
  expect(patchTeamFuture(served, crossed)).toBe(served);
});

test('the same reading twice is a no-op, so nothing re-renders', () => {
  const once = adoptOutcomePrices(empty, answer([price()]), ASKED);
  expect(adoptOutcomePrices(once, answer([price()]), ASKED)).toBe(once);
  const unchanged = row({ probability: 0.88, probability_change_24h: -0.025, rank: 3 });
  expect(patchTeamFuture(unchanged, once)).toBe(unchanged);
});

test('a graded winner arrives with its reading', () => {
  const book = adoptOutcomePrices(empty, answer([price({ is_winner: true, probability: 1 })]), ASKED);
  expect(patchTeamFuture(row(), book).is_winner).toBe(true);
});
