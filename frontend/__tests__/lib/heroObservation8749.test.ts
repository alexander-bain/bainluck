import { appendHeroObservation, mergeLiveChartHistory, rememberLiveChartFrame, type LiveChartFrame } from '@/lib/liveChartHistory';
import { pinChartEdgeToHero } from '@/lib/chartEdgePin';
import type { LiveStreamFrame } from '@/lib/liveStreamController';

// Production, live/617, TB@PHI /events/15318356 (browser-watch.jsonl 686–692).
// The stream's last frame before the split, verbatim.
const lastFrame: LiveStreamFrame = {
  event_id: 15318356, p: 0.3632, source: 'kalshi', source_value: 0.34,
  updated_at: '2026-09-25T23:10:59.719327+00:00', status: 'live',
};
// History refetched at 23:11:09: its blend line ends on the backend's "now"
// edge at 36.3, which is what the page drew.
const served = {
  aggregate_line: [
    { timestamp: '2026-09-25T23:10:00+00:00', home_probability: 0.382 },
    { timestamp: '2026-09-25T23:11:09.400000+00:00', home_probability: 0.363 },
  ],
  blend_edge_pinned: true,
};
// The detail GET at 23:11:12.8 printed 35%–65%. Its body was not captured; the
// kalshi stamp here is the one the stream carried 1.24 s later for this same
// blend (0.3513, kalshi 0.35) — #8680 showed frames carry the source's stamp.
const detail = {
  status: 'live', hero_probability: 0.3513, hero_probability_source: 'blend',
  win_probability_sources: {
    kalshi: { updated_at: '2026-09-25T23:11:14.361196+00:00' },
    polymarket: { updated_at: '2026-09-25T23:10:37.393306+00:00' },
  },
};
const sameBlendFrame: LiveStreamFrame = {
  event_id: 15318356, p: 0.3513, source: 'kalshi', source_value: 0.35,
  updated_at: '2026-09-25T23:11:14.361196+00:00', status: 'live',
};

const last = (h: { aggregate_line?: { timestamp: string; home_probability: number }[] | null } | undefined) =>
  h!.aggregate_line![h!.aggregate_line!.length - 1];

// The page's composition before #8749: once any frame is held, no pin.
function beforeFix(points: LiveChartFrame[]) {
  const pushed = mergeLiveChartHistory(served, points);
  return pushed !== served ? pushed : pinChartEdgeToHero(served, detail);
}

test('the specimen: before the fix the detail refresh moved the headline and not the line', () => {
  const points = rememberLiveChartFrame([], lastFrame, 15318356);
  expect(last(beforeFix(points)).home_probability).toBe(0.363);
  expect(detail.hero_probability).toBe(0.3513);
});

test('the headline blend reaches the line at its own clock', () => {
  const points = rememberLiveChartFrame([], lastFrame, 15318356);
  const joined = appendHeroObservation(beforeFix(points), detail);
  expect(last(joined)).toEqual({ timestamp: '2026-09-25T23:11:14.361196+00:00', home_probability: 0.3513 });
});

test('the same publication arriving by stream afterwards adds no second point', () => {
  const points = [lastFrame, sameBlendFrame].reduce<LiveChartFrame[]>(
    (acc, f) => rememberLiveChartFrame(acc, f, 15318356), []);
  const merged = mergeLiveChartHistory(served, points);
  const joined = appendHeroObservation(merged, detail);
  expect(joined).toBe(merged);
  const instants = joined!.aggregate_line!.map(p => Date.parse(p.timestamp));
  expect(new Set(instants).size).toBe(instants.length);
  expect(last(joined).home_probability).toBe(0.3513);
});

test('an older headline never follows or overwrites a newer edge (PIT@DET 421 direction)', () => {
  const older = { ...detail, win_probability_sources: { kalshi: { updated_at: '2026-09-25T23:11:09.400000+00:00' } } };
  expect(appendHeroObservation(served, older)).toBe(served);
  const earlier = { ...detail, win_probability_sources: { kalshi: { updated_at: '2026-09-25T23:11:05Z' } } };
  expect(appendHeroObservation(served, earlier)).toBe(served);
});

test('the edge is the newest point even when the line is not in time order', () => {
  const shuffled = { ...served, aggregate_line: [served.aggregate_line[1], served.aggregate_line[0]] };
  const at = { ...detail, win_probability_sources: { kalshi: { updated_at: '2026-09-25T23:10:30Z' } } };
  expect(appendHeroObservation(shuffled, at)).toBe(shuffled);
});

test.each([
  ['no served blend line', { ...served, aggregate_line: [] }, detail],
  ['null blend line', { ...served, aggregate_line: null }, detail],
  ['settled headline', served, { ...detail, status: 'completed' }],
  ['non-blend headline', served, { ...detail, hero_probability_source: 'opening' }],
  ['no headline number', served, { ...detail, hero_probability: null }],
  ['out-of-range headline', served, { ...detail, hero_probability: 1.2 }],
  ['no source clocks', served, { ...detail, win_probability_sources: {} }],
  ['unparseable clock', served, { ...detail, win_probability_sources: { kalshi: { updated_at: 'soon' } } }],
  ['same value already on the edge', served, { ...detail, hero_probability: 0.363 }],
])('%s: nothing added, same object', (_label, history, hero) => {
  expect(appendHeroObservation(history as typeof served, hero as typeof detail)).toBe(history);
});

test('undefined history stays undefined', () => {
  expect(appendHeroObservation(undefined, detail)).toBeUndefined();
});

test('the page derives historyData through appendHeroObservation on the live arm', () => {
  const fs = require('fs');
  const path = require('path');
  const page: string = fs.readFileSync(path.join(__dirname, '../../app/events/[id]/page.tsx'), 'utf8');
  const memo = page.slice(page.indexOf('const historyData = useMemo('), page.indexOf('const backendBlendServed'));
  expect(memo).toContain('mergeLiveChartHistory(servedHistory, isLive ? chartPoints : [])');
  expect(memo).toContain('isLive ? appendHeroObservation(joined, event, servedHistory) : joined');
  expect(memo).toMatch(/\[servedHistory, event, isLive, chartPoints\]/);
});
