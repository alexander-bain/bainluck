import { reconcileEventPoll, fetchEventWithLiveFrame } from '@/lib/reconcileEventPoll';
import type { LiveStreamFrame } from '@/lib/liveStreamController';

// Production15317723: stream50/50, then ordinary REST replaced only the hero
// with52/48 while the chart retained50. Times stay fixed; no clock branches.
const frame: LiveStreamFrame = {
  event_id: 15317723, p: 0.5, source: 'polymarket', source_value: 0.495,
  updated_at: '2026-09-25T05:29:37.840Z', status: 'live',
};
const response = {
  id: 15317723, status: 'live', hero_probability: 0.515,
  hero_probability_away: 0.485, hero_probability_source: 'blend',
  home_score: 1, away_score: 0,
  linescore: { home_games: 3, away_games: 2, observed_at: '2026-09-25T05:29:44Z' },
  win_probability_sources: {
    polymarket: { value: 0.515, display_name: 'Polymarket', updated_at: '2026-09-25T05:29:18Z' },
    kalshi: { value: 0.52, display_name: 'Kalshi', updated_at: '2026-09-25T05:29:17Z' },
  },
};

test('an older probability response cannot undo the received stream price', () => {
  const result = reconcileEventPoll(response, frame);
  expect(result.hero_probability).toBe(0.5);
  expect(result.hero_probability_away).toBe(0.5);
  expect(result.win_probability_sources.polymarket.value).toBe(0.495);
  expect(result.win_probability_sources.polymarket.updated_at).toBe(frame.updated_at);
  expect(result.win_probability_sources.polymarket.display_name).toBe('Polymarket');
  expect(result.home_score).toBe(1);
  expect(result.linescore).toBe(response.linescore);
  expect(result.win_probability_sources.kalshi).toBe(response.win_probability_sources.kalshi);
  expect(response.hero_probability).toBe(0.515);
});

test.each(['2026-09-25T05:29:37.840Z', '2026-09-25T05:29:40Z'])(
  'equal/newer REST probability wins (%s), including another source', stamp => {
    const newer = { ...response, hero_probability: 0.6, win_probability_sources: {
      ...response.win_probability_sources, kalshi: { ...response.win_probability_sources.kalshi, updated_at: stamp },
    } };
    expect(reconcileEventPoll(newer, frame)).toBe(newer);
  },
);

test.each(['completed', 'closed', 'cancelled', 'scheduled', 'postponed'])(
  'REST %s and its score/result are never replaced by a retained live frame', status => {
    const final = { ...response, status, hero_probability: 1, home_score: 2 };
    expect(reconcileEventPoll(final, frame)).toBe(final);
  },
);

test.each(['settled', 'final_unresolved', 'opening'])(
  'a REST %s probability is not reinterpreted as a live blend', hero_probability_source => {
    const result = { ...response, hero_probability_source };
    expect(reconcileEventPoll(result, frame)).toBe(result);
  },
);

test('cold-load, navigation, absent probabilities and unknown clocks keep REST authoritative', () => {
  expect(reconcileEventPoll(response, null)).toBe(response);
  expect(reconcileEventPoll(response, { ...frame, event_id: 7 })).toBe(response);
  const empty = { ...response, hero_probability: null };
  expect(reconcileEventPoll(empty, frame)).toBe(empty);
  const undated = { ...response, win_probability_sources: {} };
  expect(reconcileEventPoll(undated, frame)).toBe(undated);
  expect(reconcileEventPoll(response, { ...frame, updated_at: 'invalid' })).toBe(response);
});

test.each([null, NaN, -0.1, 1.1])('an invalid frame probability %s cannot erase REST', p => {
  expect(reconcileEventPoll(response, { ...frame, p })).toBe(response);
});

test.each([0, 1])('real boundary probability %s is preserved, never treated as missing', p => {
  expect(reconcileEventPoll(response, { ...frame, p }).hero_probability).toBe(p);
});

test('the retained original timestamp cannot make an old price look newly observed', () => {
  const first = reconcileEventPoll(response, frame);
  const nextPoll = reconcileEventPoll({ ...response, home_score: 2 }, frame);
  expect(nextPoll.win_probability_sources.polymarket.updated_at).toBe(first.win_probability_sources.polymarket.updated_at);
  expect(nextPoll.win_probability_sources.polymarket.updated_at).toBe(frame.updated_at);
  expect(nextPoll.home_score).toBe(2);
});


test('a push arriving DURING the REST request also survives the response', async () => {
  let latest: LiveStreamFrame | null = null;
  let resolve!: (value: typeof response) => void;
  const request = new Promise<typeof response>(done => { resolve = done; });
  const result = fetchEventWithLiveFrame(() => request, () => latest);
  latest = frame;
  resolve(response);
  expect((await result).hero_probability).toBe(0.5);
  expect((await result).linescore).toBe(response.linescore);
});

test('transport failures stay failures so SWR keeps its normal retry behavior', async () => {
  const error = new Error('offline');
  await expect(fetchEventWithLiveFrame(() => Promise.reject(error), () => frame)).rejects.toBe(error);
});
