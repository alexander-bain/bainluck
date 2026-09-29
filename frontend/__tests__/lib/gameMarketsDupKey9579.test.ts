jest.mock('../../lib/api', () => ({ API_URL: 'https://example.test' }));
import { createGameMarketsReconciler, type LiveGameMarkets } from '../../lib/gameMarketsStream';

// #9579: /events/14780549 (Bears 27–7 Eagles) serves four Kalshi rows that share every display
// field and differ only by market. The page rendered no props at all because the first read was refused.
const clock = (n: number) => `2026-09-29T03:11:39.${String(n).padStart(6, '0')}Z`;
const MARKETS = [62436318, 62436323, 62436317, 62436319];
function body(prices = [.99, .01, .01, .01], clocks = [1, 1, 1, 1], status = 'live'): LiveGameMarkets {
  const other = MARKETS.map((market, i) => ({ market_name: 'Both teams to score', outcome_name: 'Yes', probability: prices[i],
    source: 'kalshi', _market_id: market, contributor_outcome_ids: [100 + i] }));
  return { event_id: 14780549, status, home_team: 'Chicago Bears', away_team: 'Philadelphia Eagles', home_score: 27, away_score: 7,
    totals: [], player_props: [{ market_name: 'Makai Lemon: Receptions O/U 2.5', outcome_name: 'Over 2.5', over_probability: .6,
      source: 'polymarket', threshold: 2.5, _market_id: 9, contributor_outcome_ids: [9] }],
    team_totals: [], spreads: [], period_markets: [], matchups: [], pace: null, other,
    stream_market_ids: [...MARKETS, 9],
    outcome_market_ids: Object.fromEntries([...MARKETS.map((m, i) => [String(100 + i), m]), ['9', 9]]),
    outcome_revision_at: Object.fromEntries([...clocks.map((c, i) => [String(100 + i), clock(c)]), ['9', clock(1)]]),
  } as unknown as LiveGameMarkets;
}
const prices = (b: LiveGameMarkets | undefined) => b?.other.map(row => row.probability);

test('four same-named markets are adopted on the first read, so the page has a props body', () => {
  const r = createGameMarketsReconciler();
  const first = r.adopt(body());
  expect(first?.player_props).toHaveLength(1);
  expect(prices(first)).toEqual([.99, .01, .01, .01]);
});

test('a move on one of the four is accepted only for the market whose clock advanced', () => {
  const r = createGameMarketsReconciler(); r.adopt(body());
  expect(prices(r.adopt(body([.99, .2, .01, .01], [1, 2, 1, 1])))).toEqual([.99, .2, .01, .01]);
  expect(prices(r.adopt(body([.5, .2, .01, .01], [1, 2, 1, 1])))).toEqual([.99, .2, .01, .01]);
});

test('rows identical even in market still get distinct keys', () => {
  const twin = body(); twin.other = [twin.other[0], { ...twin.other[0] }];
  expect(createGameMarketsReconciler().adopt(twin)?.other).toHaveLength(2);
});
