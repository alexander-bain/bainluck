jest.mock('../../lib/api', () => ({ API_URL: 'https://example.test' }));
import { createGameMarketsReconciler, type LiveGameMarkets } from '../../lib/gameMarketsStream';

// #10358: the During matrix renders only what adopt() accepted, so its cells must ride the same
// publication/revision/withdrawal fences as every other row on the game-markets body.
const clock = (n: number) => `2030-01-01T00:00:00.${String(n).padStart(6, '0')}Z`;
type Leg = { market: number; outcome: number; source?: string; side?: string; period?: string; p?: number | null; seen?: string | null };
const question = (subject: string, count: number) => `s:${subject}|hits|full_game|ge:${count}|over`;

function cell(subject: string, count: number, legs: Leg[], state = 'quoted', current: number | null = legs[0].p ?? null) {
  return {
    question_key: question(subject, count), stat_key: 'hits', period_key: 'full_game',
    subject: { key: subject, label: subject, kind: 'player' },
    predicate: { kind: 'count_at_least', count, side: 'over', label: `${count}+` },
    current: { state, probability: state === 'quoted' ? current : null, basis: 'single_source', observed_at: legs[0].seen ?? null },
    contributors: legs.map(l => ({ source: l.source ?? 'kalshi', market_id: l.market, outcome_id: l.outcome, outcome_name: 'Yes',
      side: l.side ?? 'over', period_key: l.period ?? 'full_game', probability: l.p ?? null, observed_at: l.seen ?? null })),
    result: null, comparison: { state: 'unavailable', reason: 'no_pregame_pin' },
    _market_id: legs[0].market, _market_ids: legs.map(l => l.market), contributor_outcome_ids: legs.map(l => l.outcome),
  };
}

// Judge 2+ / 3+ are one ladder (outcomes 31, 32); Soto 2+ is another (33).
function body(clocks: Record<number, number | null> = {}, cells: object[] | null = null, status = 'live'): LiveGameMarkets {
  const at = { 31: 1, 32: 1, 33: 1, ...clocks };
  return { event_id: 7, status, home_team: 'Home', away_team: 'Away', home_score: 1, away_score: 0,
    totals: [], player_props: [], team_totals: [], spreads: [], period_markets: [], matchups: [], other: [], pace: null,
    stream_market_ids: [21, 22, 23], outcome_market_ids: { '31': 21, '32': 22, '33': 23 },
    outcome_revision_at: Object.fromEntries(Object.entries(at).map(([id, n]) => [id, n === null ? null : clock(n)])),
    during_player_props: cells && { contract: '10236.v1', stats: [], rows: cells, coverage: {} },
  } as unknown as LiveGameMarkets;
}
const judge2 = (p: number | null = .4, seen = clock(1), state = 'quoted') => cell('judge', 2, [{ market: 21, outcome: 31, p, seen }], state);
const judge3 = (p: number | null = .2) => cell('judge', 3, [{ market: 22, outcome: 32, p, seen: clock(1) }]);
const soto2 = (p: number | null = .5) => cell('soto', 2, [{ market: 23, outcome: 33, p, seen: clock(1) }]);
const cells = (b: LiveGameMarkets | undefined) =>
  Object.fromEntries((b?.during_player_props?.rows ?? []).map(row => [row.question_key as string, (row.current as { probability: unknown }).probability]));

test('the section published when the game turns live is adopted with no quote tick', () => {
  const r = createGameMarketsReconciler(); r.adopt(body({}, null, 'scheduled'));
  const live = r.adopt(body({}, [judge2(), judge3(), soto2()]));
  expect(live?.status).toBe('live');
  expect(cells(live)).toEqual({ [question('judge', 2)]: .4, [question('judge', 3)]: .2, [question('soto', 2)]: .5 });
});

test('a same-value newer observation is adopted with its own clock', () => {
  const r = createGameMarketsReconciler(); r.adopt(body({}, [judge2()]));
  const later = r.adopt(body({ 31: 5 }, [judge2(.4, clock(5))]));
  expect((later?.during_player_props?.rows?.[0].current as { observed_at: string }).observed_at).toBe(clock(5));
  expect((later?.during_player_props?.rows?.[0].contributors as { observed_at: string }[])[0].observed_at).toBe(clock(5));
});

test('an older or conflicting cell cannot replace the accepted one', () => {
  const r = createGameMarketsReconciler(); r.adopt(body({}, [judge2(), soto2()]));
  r.adopt(body({ 31: 3 }, [judge2(.45, clock(3)), soto2()]));
  expect(cells(r.adopt(body({ 31: 2 }, [judge2(.41, clock(2)), soto2()])))[question('judge', 2)]).toBe(.45);
  expect(cells(r.adopt(body({ 31: 3 }, [judge2(.6, clock(3)), soto2()])))[question('judge', 2)]).toBe(.45);
  // A contributor quote moving under an unchanged blend is still a changed value.
  const hidden = judge2(.45, clock(3)); hidden.contributors[0].probability = .9;
  expect(r.adopt(body({ 31: 3 }, [hidden, soto2()]))?.during_player_props?.rows?.[0].contributors).toEqual(judge2(.45, clock(3)).contributors);
});

test('withdrawal clears the cell and only its own newer evidence restores it', () => {
  const r = createGameMarketsReconciler(); r.adopt(body({}, [judge2(), soto2()]));
  expect(cells(r.adopt(body({}, [judge2(null, clock(1), 'unavailable'), soto2()])))[question('judge', 2)]).toBeNull();
  expect(cells(r.adopt(body({}, [judge2(), soto2()])))[question('judge', 2)]).toBeNull();
  expect(cells(r.adopt(body({ 33: 2 }, [judge2(), soto2(.55)])))[question('judge', 2)]).toBeNull();
  expect(cells(r.adopt(body({ 31: 3, 33: 2 }, [judge2(.4, clock(3)), soto2(.55)])))[question('judge', 2)]).toBe(.4);
});

test('a rung the ladder rule dropped returns on its neighbour\'s newer quote, never on another ladder', () => {
  const r = createGameMarketsReconciler(); r.adopt(body({}, [judge2(), judge3(), soto2()]));
  expect(Object.keys(cells(r.adopt(body({}, [judge2(), soto2()]))))).toEqual([question('judge', 2), question('soto', 2)]);
  expect(cells(r.adopt(body({ 33: 2 }, [judge2(), judge3(), soto2(.55)])))[question('judge', 3)]).toBeUndefined();
  expect(cells(r.adopt(body({ 31: 3, 33: 2 }, [judge2(.35, clock(3)), judge3(), soto2(.55)])))[question('judge', 3)]).toBe(.2);
});

test('a new cell over already-known quiet quotes needs a newer clock once the section is live', () => {
  const r = createGameMarketsReconciler(); r.adopt(body({}, [soto2()]));
  expect(cells(r.adopt(body({}, [judge2(), soto2()])))[question('judge', 2)]).toBeUndefined();
  expect(cells(r.adopt(body({ 31: 2 }, [judge2(.4, clock(2)), soto2()])))[question('judge', 2)]).toBe(.4);
});

test.each([
  ['source', { source: 'polymarket' }], ['side', { side: 'under' }], ['period', { period: 'first_half' }], ['outcome', { outcome: 33 }],
])('a contributor %s change with no market evidence keeps the accepted identity', (_, change) => {
  const r = createGameMarketsReconciler(); r.adopt(body({}, [judge2()]));
  const moved = cell('judge', 2, [{ market: 21, outcome: 31, p: .4, seen: clock(1), ...change }]);
  expect(r.adopt(body({}, [moved]))?.during_player_props?.rows?.[0].contributors).toEqual(judge2().contributors);
});

test('a graded cell cannot fall back to a live quote', () => {
  const r = createGameMarketsReconciler(); r.adopt(body({}, [judge2()]));
  const graded = { ...judge2(null, clock(1), 'actual_only'), result: { actual: 2, hit: true, resolution_source: 'box_score' } };
  r.adopt(body({}, [graded]));
  expect(r.adopt(body({ 31: 4 }, [judge2(.4, clock(4))]))?.during_player_props?.rows?.[0].result).toEqual(graded.result);
});

test('a final body with no During section withdraws every cell', () => {
  const r = createGameMarketsReconciler(); r.adopt(body({}, [judge2(), soto2()]));
  const final = r.adopt(body({}, null, 'completed'));
  expect(final?.status).toBe('completed');
  expect(final?.during_player_props).toBeNull();
  expect(r.adopt(body({}, [judge2(), soto2()]))?.status).toBe('completed');
});

test('a finite zero is a quote, and a number on a non-quoted cell is not', () => {
  const r = createGameMarketsReconciler(); r.adopt(body({}, [judge2(0), soto2()]));
  // Zero is held as a quote, so an unexplained move off it is refused like any other value.
  expect(cells(r.adopt(body({}, [judge2(.3), soto2()])))[question('judge', 2)]).toBe(0);
  const stray = judge2(); stray.current = { ...stray.current, state: 'unavailable', probability: .4 };
  r.adopt(body({}, [stray, soto2()]));
  // The stray-number cell was a withdrawal: the same quote cannot return without newer evidence.
  expect(r.adopt(body({}, [judge2(0), soto2()]))?.during_player_props?.rows?.[0].current).toEqual(stray.current);
});
