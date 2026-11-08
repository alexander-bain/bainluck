/**
 * #10090 — Search's game cards re-price live under Fable's decision A (Nov 8).
 *
 * 🔴 THE LOAD-BEARING RULE: "a card's probability must never be newer than its
 * score". A live game is patched only from a price card that carries
 * `live_state`, and then probability, score and clock move together.
 * `a_live_card_without_live_state_patches_nothing` and
 * `probability_score_and_clock_move_together` are the two halves.
 */
import { adoptSearchEventCards, patchSearchEvent, type SearchEventBook } from '@/lib/searchEventsStream';
import type { DiscoverPriceCards } from '@/lib/discover/priceRefresh';
import type { Event, FeedItem } from '@/lib/types';

const served = (over: Partial<Event> = {}): Event => ({
  id: 15343927, external_id: 'x', sport: 'basketball_nba', home_team: 'Detroit Pistons',
  away_team: 'Los Angeles Lakers', commence_time: '2026-11-09T00:00:00Z', status: 'scheduled',
  home_score: null, away_score: null,
  current_odds: { home_probability: 0.7039, away_probability: 0.2961, spread: -7.5 } as Event['current_odds'],
  hero_probability: 0.7039, hero_probability_away: 0.2961,
  ...over,
}) as Event;

const card = (over: Record<string, unknown> = {}): FeedItem => ({
  type: 'event',
  data: {
    id: 15343927, status: 'scheduled', home_score: null, away_score: null,
    current_odds: { home_probability: 0.71, away_probability: 0.29, home_rendered_percent: 71, away_rendered_percent: 29 },
    hero_probability: 0.71, hero_probability_away: 0.29, hero_probability_source: 'blend',
    blend_fold_revision: { '15343927': 2147 }, hero_probability_observed_at: '2026-11-08T22:44:51.215436+00:00',
    ...over,
  },
}) as unknown as FeedItem;

const answer = (items: FeedItem[], disposition = 'updated'): DiscoverPriceCards => ({
  built_at: 1, items,
  dispositions: Object.fromEntries(items.map((i) => [`event-${(i.data as { id: number }).id}`, disposition])) as DiscoverPriceCards['dispositions'],
});
const ASKED = new Set([15343927]);
const empty: SearchEventBook = new Map();

test('a scheduled game re-prices its probability fields and keeps everything else served', () => {
  const e = served();
  const book = adoptSearchEventCards(empty, [e], answer([card()]), ASKED);
  const shown = patchSearchEvent(e, book);
  expect(shown.current_odds).toEqual({ home_probability: 0.71, away_probability: 0.29, spread: -7.5 });
  expect([shown.hero_probability, shown.hero_probability_away]).toEqual([0.71, 0.29]);
  expect(shown.home_score).toBeNull();
  expect(shown.espn).toBeUndefined();
});

const live = (over: Partial<Event> = {}) => served({
  status: 'live', home_score: 54, away_score: 50,
  espn: { period: '3rd Quarter', game_clock: '7:30', broadcast: 'ESPN' }, ...over,
});

test('probability, score and clock move together on a live game', () => {
  const e = live();
  const book = adoptSearchEventCards(empty, [e], answer([card({
    status: 'live', home_score: 57, away_score: 50, live_state: { period: '3rd Quarter', game_clock: '6:58' },
    blend_fold_revision: { '15343927': 2150 },
  })]), ASKED);
  const shown = patchSearchEvent(e, book);
  expect([shown.home_score, shown.away_score]).toEqual([57, 50]);
  expect(shown.espn).toEqual({ period: '3rd Quarter', game_clock: '6:58', broadcast: 'ESPN' });
  expect(shown.current_odds?.home_probability).toBe(0.71);
});

test('a live card without live_state patches nothing', () => {
  const e = live();
  const book = adoptSearchEventCards(empty, [e], answer([card({ status: 'live', home_score: 57, away_score: 50 })]), ASKED);
  expect(book).toBe(empty);
  expect(patchSearchEvent(e, book)).toBe(e);
});

test('a cleared clock is cleared, never left stale beside a new score', () => {
  const e = live();
  const book = adoptSearchEventCards(empty, [e], answer([card({
    status: 'live', home_score: 57, away_score: 50, live_state: { period: 'Halftime', game_clock: null },
  })]), ASKED);
  expect(patchSearchEvent(e, book).espn).toEqual({ period: 'Halftime', broadcast: 'ESPN' });
});

test('a game that changed status stops updating', () => {
  const e = live();
  const book = adoptSearchEventCards(empty, [e], answer([card({
    status: 'final', home_score: 110, away_score: 102, live_state: { period: 'Final', game_clock: null },
  })]), ASKED);
  expect(book).toBe(empty);
  expect(patchSearchEvent(e, book)).toBe(e);
});

test('never backwards: an older fold revision or reading time is refused', () => {
  const e = served();
  const newer = adoptSearchEventCards(empty, [e], answer([card({ blend_fold_revision: { '15343927': 2150 } })]), ASKED);
  const older = adoptSearchEventCards(newer, [e], answer([card({
    blend_fold_revision: { '15343927': 2149 }, hero_probability: 0.6, current_odds: { home_probability: 0.6, away_probability: 0.4 },
  })]), ASKED);
  expect(older).toBe(newer);
  const staleClock = adoptSearchEventCards(newer, [e], answer([card({
    blend_fold_revision: { '15343927': 2150 }, hero_probability_observed_at: '2026-11-08T22:40:00Z', hero_probability: 0.6,
  })]), ASKED);
  expect(staleClock).toBe(newer);
});

test.each([
  ['a withheld disposition', answer([card()], 'withheld'), ASKED],
  ['a card with no fold revision', answer([card({ blend_fold_revision: null })]), ASKED],
  ['an id that was not asked for', answer([card()]), new Set<number>()],
])('nothing is adopted from %s', (_label, response, asked) => {
  expect(adoptSearchEventCards(empty, [served()], response as DiscoverPriceCards, asked as Set<number>)).toBe(empty);
});

test('a finished or postponed game on Search is never patched', () => {
  const finished = served({ status: 'final' as Event['status'] });
  const book = adoptSearchEventCards(empty, [served()], answer([card()]), ASKED);
  expect(patchSearchEvent(finished, book)).toBe(finished);
});

test('the same reading twice is a no-op, so nothing re-renders', () => {
  const e = served();
  const book = adoptSearchEventCards(empty, [e], answer([card()]), ASKED);
  expect(adoptSearchEventCards(book, [e], answer([card()]), ASKED)).toBe(book);
  const same = served({ current_odds: { home_probability: 0.71, away_probability: 0.29, spread: -7.5 } as Event['current_odds'],
    hero_probability: 0.71, hero_probability_away: 0.29 });
  expect(patchSearchEvent(same, book)).toBe(same);
});
