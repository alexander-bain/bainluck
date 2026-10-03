jest.mock('../../lib/api', () => ({ API_URL: 'https://example.test' }));
import { createGameMarketsReconciler, fetchFreshGameMarkets, type LiveGameMarkets } from '../../lib/gameMarketsStream';
const clock = (n: number) => `2030-01-01T00:00:00.${String(n).padStart(6, '0')}Z`;
function body(a: number | null = .4, b: number | null = .6, ca: string | null = clock(1), cb: string | null = clock(1)): LiveGameMarkets {
  return { event_id: 7, status: 'live', home_team: 'Home', away_team: 'Away', home_score: 2, away_score: 1,
    totals: [], player_props: [], team_totals: [], spreads: [], period_markets: [], matchups: [], pace: null,
    other: [{ market_name: 'Winner', outcome_name: 'Home', probability: a, source: 'kalshi', _market_id: 11, contributor_outcome_ids: [1] },
      { market_name: 'Winner', outcome_name: 'Away', probability: b, source: 'kalshi', _market_id: 11, contributor_outcome_ids: [2] }],
    stream_market_ids: [11], outcome_market_ids: { '1': 11, '2': 11 }, outcome_revision_at: { '1': ca, '2': cb },
    outcome_observed_at: { '1': null, '2': null } } as unknown as LiveGameMarkets;
}
const prices = (b: LiveGameMarkets | undefined) => b?.other.map(row => row.probability);

test('one raw sibling revision adopts the normalized vector, never a mixed body', () => {
  const r = createGameMarketsReconciler(); r.adopt(body());
  expect(prices(r.adopt(body(.5, .5, clock(2))))).toEqual([.5, .5]);
  expect(prices(r.adopt(body(.6, .4, clock(3), clock(0))))).toEqual([.5, .5]);
  expect(prices(r.adopt(body(.8, .2, clock(2))))).toEqual([.5, .5]);
});
test.each([clock(1), null])('withdrawal at %s clears but an unchanged or unrelated sibling cannot revive it', ca => {
  const r = createGameMarketsReconciler(); r.adopt(body());
  expect(prices(r.adopt(body(null, .6, ca)))).toEqual([null, .6]);
  expect(prices(r.adopt(body(.8, .2, clock(1), clock(2))))).toEqual([null, .6]);
  expect(prices(r.adopt(body(.5, .5, clock(2), clock(2))))).toEqual([.5, .5]);
});
test('missing row is a withdrawal and a removed book stays subscribed', () => {
  const r = createGameMarketsReconciler(); r.adopt(body());
  const absent = body(); absent.other = [];
  expect(r.adopt(absent)?.other).toEqual([]);
  expect(r.current()?.stream_market_ids).toEqual([11]);
  expect(r.adopt(body())?.other).toEqual([]);
  expect(prices(r.adopt(body(.7, .3, clock(2), clock(2))))).toEqual([.7, .3]);
});
test('known clocks cannot disappear behind a displayed quote; precise ordering preserves microseconds', () => {
  const r = createGameMarketsReconciler(); r.adopt(body());
  expect(prices(r.adopt(body(.5, .5, null, clock(2))))).toEqual([.4, .6]);
  expect(prices(r.adopt(body(.5, .5, clock(2), clock(2))))).toEqual([.5, .5]);
  expect(r.current()?.outcome_observed_at).toEqual({ '1': null, '2': null });
});
test('same instant with offset spelling does not authorize another value', () => {
  const r = createGameMarketsReconciler(); r.adopt(body());
  expect(prices(r.adopt(body(.8, .2, '2030-01-01T01:00:00.000001+01:00')))).toEqual([.4, .6]);
});
test('matchup nested quotes participate in withdrawal and own-contributor restoration', () => {
  const matchup = (p: number | null, ca: string | null = clock(1), cb: string | null = clock(1)) => {
    const v = body(.4, .6, ca, cb); v.other = [];
    v.matchups = [{ market_name: 'Home vs Away', type: 'h2h', source: 'kalshi', _market_id: 11,
      outcomes: [{ name: 'Home', probability: p, contributor_outcome_ids: [1] },
        { name: 'Away', probability: .6, contributor_outcome_ids: [2] }] }] as unknown as LiveGameMarkets['matchups']; return v;
  };
  const r = createGameMarketsReconciler(); r.adopt(matchup(.4)); r.adopt(matchup(null, null));
  expect(r.adopt(matchup(.8, clock(1), clock(2)))?.matchups[0].outcomes[0].probability).toBeNull();
  expect(r.adopt(matchup(.5, clock(2), clock(2)))?.matchups[0].outcomes[0].probability).toBe(.5);
});
test('a provisional actual may advance, but it does not authorize a missing quote clock', () => {
  const prop = (actual: number, ca: string | null) => {
    const v = body(.4, .6, ca); v.other = [];
    v.player_props = [{ market_name: 'Points', outcome_name: 'Player', over_probability: .4, source: 'kalshi',
      threshold: 3, movement: 0, actual, hit: null, _market_id: 11, contributor_outcome_ids: [1] }] as unknown as LiveGameMarkets['player_props']; return v;
  };
  const r = createGameMarketsReconciler(); r.adopt(prop(1, clock(1)));
  expect(r.adopt(prop(2, clock(2)))?.player_props[0].actual).toBe(2);
  expect(r.adopt(prop(3, null))?.player_props[0].actual).toBe(2);
});
test('real grades accept unknown clocks but cannot reverse or change a final score', () => {
  const r = createGameMarketsReconciler(); r.adopt(body());
  const final = body(1, 0, null, null); final.status = 'completed';
  final.other[0].is_winner = true; final.other[1].is_winner = false;
  expect(prices(r.adopt(final))).toEqual([1, 0]);
  expect(prices(r.adopt(body()))).toEqual([1, 0]);
  expect(r.adopt({ ...final, home_score: 3 })?.home_score).toBe(2);
});
test('closed winner contract fences even when unrelated fields reject the response', () => {
  const r = createGameMarketsReconciler(); const initial = body(); initial.status = 'completed';
  initial.open_winner_quote = { event_id: 7, market_id: 11, market_name: 'Winner', status: 'open', source: 'kalshi', observed_at: null,
    outcomes: [{ outcome_id: 1, side: 'home', name: 'Home', probability: .4, observed_at: null },
      { outcome_id: 2, side: 'away', name: 'Away', probability: .6, observed_at: null }] };
  r.adopt(initial);
  expect(r.adopt({ ...initial, home_score: 9, closed_winner_market_ids: [11] })?.open_winner_quote).toBeNull();
  expect(r.adopt(initial)?.open_winner_quote).toBeNull();
  expect(r.current()?.home_score).toBe(2);
});
test('identity and duplicate row keys fail closed', () => {
  const r = createGameMarketsReconciler(); r.adopt(body());
  expect(r.adopt({ ...body(), event_id: 8 })?.event_id).toBe(7);
  const invalid = body(); invalid.other.push(invalid.other[0]);
  expect(r.adopt(invalid)?.other).toHaveLength(2);
});
test('fresh fetch avoids boot/shared cache and carries server 429 cooldown', async () => {
  const fetcher = jest.fn().mockResolvedValueOnce({ ok: true, json: async () => body() })
    .mockResolvedValueOnce({ ok: false, status: 429, headers: { get: () => null }, json: async () => ({ retry_after: 70 }) });
  global.fetch = fetcher;
  await fetchFreshGameMarkets(7, new AbortController().signal);
  expect(fetcher).toHaveBeenCalledWith('https://example.test/api/events/7/game-markets?fresh=true', expect.objectContaining({ cache: 'no-store' }));
  await expect(fetchFreshGameMarkets(7, new AbortController().signal)).rejects.toMatchObject({ status: 429, retryAfterMs: 70000 });
});

function winnerBody(market = 11, status = 'completed'): LiveGameMarkets {
  const value = body(); value.other = []; value.status = status;
  value.stream_market_ids = [11, 12];
  value.outcome_market_ids = { '1': 11, '2': 11, '3': 12, '4': 12 };
  value.outcome_revision_at = Object.fromEntries([1,2,3,4].map(id => [id, clock(1)]));
  const first = market === 11 ? 1 : 3;
  value.open_winner_quote = { event_id: 7, market_id: market, market_name: 'Winner', status: 'open', source: 'kalshi', observed_at: null,
    outcomes: [{ outcome_id: first, side: 'home', name: 'Home', probability: .4, observed_at: null },
      { outcome_id: first + 1, side: 'away', name: 'Away', probability: .6, observed_at: null }] };
  return value;
}
test('first final quote uses already-known quiet raw rows without blocking final state', () => {
  const r = createGameMarketsReconciler(); const live = winnerBody(11, 'live'); live.open_winner_quote = null;
  r.adopt(live);
  expect(r.adopt(winnerBody())?.status).toBe('completed');
  expect(r.current()?.open_winner_quote?.market_id).toBe(11);
});
test('whole-book representative may switch A to B and back without inventing withdrawal', () => {
  const r = createGameMarketsReconciler(); r.adopt(winnerBody());
  expect(r.adopt(winnerBody(12))?.open_winner_quote?.market_id).toBe(12);
  expect(r.adopt(winnerBody())?.open_winner_quote?.market_id).toBe(11);
});
test('real whole-book withdrawal requires own advance, and one changed leg restores coherent pair', () => {
  const r = createGameMarketsReconciler(); r.adopt(winnerBody());
  const absent = winnerBody(); absent.open_winner_quote = null; r.adopt(absent);
  const unrelated = winnerBody(); unrelated.outcome_revision_at!['3'] = clock(2);
  expect(r.adopt(unrelated)?.open_winner_quote).toBeNull();
  const restored = winnerBody(); restored.outcome_revision_at!['1'] = clock(2);
  restored.open_winner_quote!.outcomes[0].probability = .5; restored.open_winner_quote!.outcomes[1].probability = .5;
  expect(r.adopt(restored)?.open_winner_quote?.outcomes.map(row => row.probability)).toEqual([.5,.5]);
});
test.each(['subscription', 'binding'])('unbound winner quote cannot render (%s)', missing => {
  const value = winnerBody();
  if (missing === 'subscription') value.stream_market_ids = [12];
  else value.outcome_market_ids!['1'] = 12;
  expect(createGameMarketsReconciler().adopt(value)?.open_winner_quote).toBeNull();
});

test('delayed unbound response cannot erase a valid held quote, but explicit closure still clears', () => {
  const r = createGameMarketsReconciler(); r.adopt(winnerBody());
  const invalid = winnerBody(); invalid.home_score = 9; invalid.outcome_market_ids!['1'] = 12;
  expect(r.adopt(invalid)?.open_winner_quote?.market_id).toBe(11);
  expect(r.adopt({ ...invalid, closed_winner_market_ids: [11] })?.open_winner_quote).toBeNull();
});

// #10358: the During matrix renders only what adopt() accepted, so its cells must ride the same
// publication/revision/withdrawal fences as every other row on the game-markets body.
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
function duringBody(clocks: Record<number, number | null> = {}, cells: object[] | null = null, status = 'live'): LiveGameMarkets {
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
const duringCells = (b: LiveGameMarkets | undefined) =>
  Object.fromEntries((b?.during_player_props?.rows ?? []).map(row => [row.question_key as string, (row.current as { probability: unknown }).probability]));

test('the section published when the game turns live is adopted with no quote tick', () => {
  const r = createGameMarketsReconciler(); r.adopt(duringBody({}, null, 'scheduled'));
  const live = r.adopt(duringBody({}, [judge2(), judge3(), soto2()]));
  expect(live?.status).toBe('live');
  expect(duringCells(live)).toEqual({ [question('judge', 2)]: .4, [question('judge', 3)]: .2, [question('soto', 2)]: .5 });
});

test('a same-value newer observation is adopted with its own clock', () => {
  const r = createGameMarketsReconciler(); r.adopt(duringBody({}, [judge2()]));
  const later = r.adopt(duringBody({ 31: 5 }, [judge2(.4, clock(5))]));
  expect((later?.during_player_props?.rows?.[0].current as { observed_at: string }).observed_at).toBe(clock(5));
  expect((later?.during_player_props?.rows?.[0].contributors as { observed_at: string }[])[0].observed_at).toBe(clock(5));
});

test('an older or conflicting cell cannot replace the accepted one', () => {
  const r = createGameMarketsReconciler(); r.adopt(duringBody({}, [judge2(), soto2()]));
  r.adopt(duringBody({ 31: 3 }, [judge2(.45, clock(3)), soto2()]));
  expect(duringCells(r.adopt(duringBody({ 31: 2 }, [judge2(.41, clock(2)), soto2()])))[question('judge', 2)]).toBe(.45);
  expect(duringCells(r.adopt(duringBody({ 31: 3 }, [judge2(.6, clock(3)), soto2()])))[question('judge', 2)]).toBe(.45);
  // A contributor quote moving under an unchanged blend is still a changed value.
  const hidden = judge2(.45, clock(3)); hidden.contributors[0].probability = .9;
  expect(r.adopt(duringBody({ 31: 3 }, [hidden, soto2()]))?.during_player_props?.rows?.[0].contributors).toEqual(judge2(.45, clock(3)).contributors);
});

test('withdrawal clears the cell and only its own newer evidence restores it', () => {
  const r = createGameMarketsReconciler(); r.adopt(duringBody({}, [judge2(), soto2()]));
  expect(duringCells(r.adopt(duringBody({}, [judge2(null, clock(1), 'unavailable'), soto2()])))[question('judge', 2)]).toBeNull();
  expect(duringCells(r.adopt(duringBody({}, [judge2(), soto2()])))[question('judge', 2)]).toBeNull();
  expect(duringCells(r.adopt(duringBody({ 33: 2 }, [judge2(), soto2(.55)])))[question('judge', 2)]).toBeNull();
  expect(duringCells(r.adopt(duringBody({ 31: 3, 33: 2 }, [judge2(.4, clock(3)), soto2(.55)])))[question('judge', 2)]).toBe(.4);
});

test('a rung the ladder rule dropped returns on its neighbour\'s newer quote, never on another ladder', () => {
  const r = createGameMarketsReconciler(); r.adopt(duringBody({}, [judge2(), judge3(), soto2()]));
  expect(Object.keys(duringCells(r.adopt(duringBody({}, [judge2(), soto2()]))))).toEqual([question('judge', 2), question('soto', 2)]);
  expect(duringCells(r.adopt(duringBody({ 33: 2 }, [judge2(), judge3(), soto2(.55)])))[question('judge', 3)]).toBeUndefined();
  expect(duringCells(r.adopt(duringBody({ 31: 3, 33: 2 }, [judge2(.35, clock(3)), judge3(), soto2(.55)])))[question('judge', 3)]).toBe(.2);
});

test('a new cell over already-known quiet quotes needs a newer clock once the section is live', () => {
  const r = createGameMarketsReconciler(); r.adopt(duringBody({}, [soto2()]));
  expect(duringCells(r.adopt(duringBody({}, [judge2(), soto2()])))[question('judge', 2)]).toBeUndefined();
  expect(duringCells(r.adopt(duringBody({ 31: 2 }, [judge2(.4, clock(2)), soto2()])))[question('judge', 2)]).toBe(.4);
});

test.each([
  ['source', { source: 'polymarket' }], ['side', { side: 'under' }], ['period', { period: 'first_half' }], ['outcome', { outcome: 33 }],
])('a contributor %s change with no market evidence keeps the accepted identity', (_, change) => {
  const r = createGameMarketsReconciler(); r.adopt(duringBody({}, [judge2()]));
  const moved = cell('judge', 2, [{ market: 21, outcome: 31, p: .4, seen: clock(1), ...change }]);
  expect(r.adopt(duringBody({}, [moved]))?.during_player_props?.rows?.[0].contributors).toEqual(judge2().contributors);
});

test('a graded cell cannot fall back to a live quote', () => {
  const r = createGameMarketsReconciler(); r.adopt(duringBody({}, [judge2()]));
  const graded = { ...judge2(null, clock(1), 'actual_only'), result: { actual: 2, hit: true, resolution_source: 'box_score' } };
  r.adopt(duringBody({}, [graded]));
  expect(r.adopt(duringBody({ 31: 4 }, [judge2(.4, clock(4))]))?.during_player_props?.rows?.[0].result).toEqual(graded.result);
});

test('a final body with no During section withdraws every cell', () => {
  const r = createGameMarketsReconciler(); r.adopt(duringBody({}, [judge2(), soto2()]));
  const final = r.adopt(duringBody({}, null, 'completed'));
  expect(final?.status).toBe('completed');
  expect(final?.during_player_props).toBeNull();
  expect(r.adopt(duringBody({}, [judge2(), soto2()]))?.status).toBe('completed');
});

test('a finite zero is a quote, and a number on a non-quoted cell is not', () => {
  const r = createGameMarketsReconciler(); r.adopt(duringBody({}, [judge2(0), soto2()]));
  // Zero is held as a quote, so an unexplained move off it is refused like any other value.
  expect(duringCells(r.adopt(duringBody({}, [judge2(.3), soto2()])))[question('judge', 2)]).toBe(0);
  const stray = judge2(); stray.current = { ...stray.current, state: 'unavailable', probability: .4 };
  r.adopt(duringBody({}, [stray, soto2()]));
  // The stray-number cell was a withdrawal: the same quote cannot return without newer evidence.
  expect(r.adopt(duringBody({}, [judge2(0), soto2()]))?.during_player_props?.rows?.[0].current).toEqual(stray.current);
});
