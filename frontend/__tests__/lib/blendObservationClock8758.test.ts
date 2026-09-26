import { adoptNewerBlendEdge, servedBlendEdgeObservation } from '@/lib/blendObservationClock';
import { pinChartEdgeToHero } from '@/lib/chartEdgePin';
import { applyLiveFrame } from '@/lib/eventLivePush';
import { appendHeroObservation, mergeLiveChartHistory, rememberLiveChartFrame, type LiveChartFrame } from '@/lib/liveChartHistory';
import type { LiveStreamFrame } from '@/lib/liveStreamController';
import { fetchEventWithLiveFrame, reconcileEventPoll } from '@/lib/reconcileEventPoll';

// #8749 / PR #8758. Every time is a fixed literal (gotcha #44). The history
// route pins its edge at the SERVE minute, floored (`_pin_blend_edge`), so the
// edge below is plotted at 23:11:00 while its price was observed at 23:10:37.
const EVENT_ID = 15318356;
const SERVE_MINUTE = '2026-09-25T23:11:00+00:00';
const served = {
  aggregate_line: [
    { timestamp: '2026-09-25T23:10:00+00:00', home_probability: 0.382 },
    { timestamp: SERVE_MINUTE, home_probability: 0.363 },
  ],
  blend_edge_pinned: true,
  blend_edge_observed_at: '2026-09-25T23:10:37.393306+00:00',
};
const detail = {
  id: EVENT_ID, status: 'live', hero_probability: 0.3513, hero_probability_away: 0.6487,
  hero_probability_source: 'blend' as const,
  hero_probability_observed_at: '2026-09-25T23:10:59.719327+00:00',
  win_probability_sources: {
    kalshi: { updated_at: '2026-09-25T23:10:59.719327+00:00' },
    polymarket: { updated_at: '2026-09-25T23:10:37.393306+00:00' },
  },
};
type Detail = typeof detail;
type Served = typeof served;

const last = (h: { aggregate_line?: { timestamp: string; home_probability: number }[] | null } | undefined) =>
  h!.aggregate_line![h!.aggregate_line!.length - 1];

// The page's `historyData` memo, verbatim in shape.
function chartOf(history: Served, event: Detail, points: LiveChartFrame[] = []) {
  const pushed = mergeLiveChartHistory(history, points);
  const joined = pushed !== history ? pushed : pinChartEdgeToHero(history, event);
  return appendHeroObservation(joined, event, history);
}
// The page's headline: the SWR cache after the history effect has run.
const headlineOf = (history: Served, event: Detail) =>
  adoptNewerBlendEdge(event, servedBlendEdgeObservation(history))!;

const frameAt = (updated_at: string, p: number): LiveStreamFrame & { p: number } => ({
  event_id: EVENT_ID, p, source: 'kalshi', source_value: p, updated_at, status: 'live',
});

describe('detail newer than the pinned edge', () => {
  const olderFrame = frameAt('2026-09-25T23:10:50Z', 0.358);
  const points = rememberLiveChartFrame([], olderFrame, EVENT_ID);

  test('the specimen: the original rule ordered the headline against the serve minute and refused it', () => {
    const legacy = { aggregate_line: served.aggregate_line, blend_edge_pinned: true };
    const pushed = mergeLiveChartHistory(legacy, points);
    expect(last(appendHeroObservation(pushed, detail, legacy)).home_probability).toBe(0.363);
    expect(detail.hero_probability).toBe(0.3513);
  });

  test('observed before the serve minute: the synthetic edge takes the newer price in place', () => {
    const chart = chartOf(served, detail, points);
    expect(last(chart)).toEqual({ timestamp: SERVE_MINUTE, home_probability: 0.3513 });
    expect(chart!.aggregate_line).toHaveLength(3);
    expect(headlineOf(served, detail).hero_probability).toBe(last(chart).home_probability);
  });

  test('observed after the serve minute: appended at its own clock', () => {
    const later = { ...detail, hero_probability_observed_at: '2026-09-25T23:11:14.361196+00:00' };
    const chart = chartOf(served, later, points);
    expect(last(chart)).toEqual({ timestamp: '2026-09-25T23:11:14.361196+00:00', home_probability: 0.3513 });
    expect(chart!.aggregate_line!.find(p => p.timestamp === SERVE_MINUTE)!.home_probability).toBe(0.363);
  });

  test('the detail clock is read, not a newer stamp on a source the blend did not fold', () => {
    const excluded = { ...detail, hero_probability_observed_at: '2026-09-25T23:10:30Z',
      win_probability_sources: { ...detail.win_probability_sources, espn: { updated_at: '2026-09-25T23:11:30Z' } } };
    const pushed = mergeLiveChartHistory(served, points);
    expect(appendHeroObservation(pushed, excluded, served)).toBe(pushed);
  });
});

describe('history newer than the headline (PIT@DET line 421 direction)', () => {
  const newer = { ...served, blend_edge_observed_at: '2026-09-25T23:11:05Z', aggregate_line: [
    served.aggregate_line[0], { timestamp: SERVE_MINUTE, home_probability: 0.532 }] };
  const stale = { ...detail, hero_probability: 0.5203, hero_probability_away: 0.4797,
    hero_probability_observed_at: '2026-09-25T23:10:40Z' };

  test('before: the edge pin wrote the older headline over the newer edge', () => {
    const legacy = { aggregate_line: newer.aggregate_line, blend_edge_pinned: true };
    expect(last(pinChartEdgeToHero(legacy, stale)).home_probability).toBe(0.5203);
  });

  test('the pin stands down and the headline adopts the edge price and clock', () => {
    expect(pinChartEdgeToHero(newer, stale)).toBe(newer);
    const headline = headlineOf(newer, stale);
    expect(headline.hero_probability).toBe(0.532);
    expect(headline.hero_probability_away).toBeCloseTo(0.468, 10);
    expect(headline.hero_probability_observed_at).toBe('2026-09-25T23:11:05Z');
    expect(last(chartOf(newer, headline)).home_probability).toBe(0.532);
    expect(chartOf(newer, headline)).toBe(newer);
    expect(adoptNewerBlendEdge(headline, servedBlendEdgeObservation(newer))).toBe(headline);
  });

  test('an older frame plotted after the serve minute is followed by the adopted edge at its observed clock', () => {
    const frame = frameAt('2026-09-25T23:11:02Z', 0.52);
    const withFrame = applyLiveFrame(stale, frame)!;
    const headline = headlineOf(newer, withFrame);
    expect(headline.hero_probability).toBe(0.532);
    const chart = chartOf(newer, headline, rememberLiveChartFrame([], frame, EVENT_ID));
    expect(last(chart)).toEqual({ timestamp: '2026-09-25T23:11:05Z', home_probability: 0.532 });
  });

  test('a withheld away side stays withheld', () => {
    const drawPriced = { ...stale, hero_probability_away: null as unknown as number };
    expect(headlineOf(newer, drawPriced).hero_probability_away).toBeNull();
  });

  test('a cached poll older than the drawn edge does not roll the headline back', async () => {
    const edge = servedBlendEdgeObservation(newer);
    const polled = await fetchEventWithLiveFrame(async () => stale, () => null, () => edge);
    expect(polled.hero_probability).toBe(0.532);
    const fresh = { ...stale, hero_probability: 0.54, hero_probability_observed_at: '2026-09-25T23:11:20Z' };
    expect(await fetchEventWithLiveFrame(async () => fresh, () => null, () => edge)).toBe(fresh);
  });
});

describe('SSE precedence', () => {
  test('a frame restamps the headline clock, so an older edge cannot take the headline back', () => {
    const frame = frameAt('2026-09-25T23:10:45Z', 0.349);
    const pushed = applyLiveFrame(detail, frame)!;
    expect(pushed.hero_probability_observed_at).toBe('2026-09-25T23:10:45Z');
    const edgeBetween = { ...served, blend_edge_observed_at: '2026-09-25T23:10:44Z' };
    expect(headlineOf(edgeBetween, pushed)).toBe(pushed);
  });

  test('a poll whose own clock predates a frame keeps the frame even when another source stamp is newer', () => {
    const frame = frameAt('2026-09-25T23:11:03Z', 0.349);
    const polled = { ...detail, win_probability_sources: { ...detail.win_probability_sources,
      espn: { updated_at: '2026-09-25T23:11:30Z' } } };
    const kept = reconcileEventPoll(polled, frame);
    expect(kept.hero_probability).toBe(0.349);
    expect(kept.hero_probability_observed_at).toBe(frame.updated_at);
  });

  test('a poll without the contract clock keeps the original any-source rule', () => {
    const frame = frameAt('2026-09-25T23:11:03Z', 0.349);
    const legacy = { ...detail, hero_probability_observed_at: undefined, win_probability_sources: {
      ...detail.win_probability_sources, espn: { updated_at: '2026-09-25T23:11:30Z' } } };
    expect(reconcileEventPoll(legacy, frame)).toBe(legacy);
  });
});

describe('equal and unknown clocks decide nothing', () => {
  const pushed = mergeLiveChartHistory(served, rememberLiveChartFrame([], frameAt('2026-09-25T23:10:50Z', 0.358), EVENT_ID));

  test.each([
    ['equal clocks', { ...detail, hero_probability_observed_at: served.blend_edge_observed_at }, served],
    ['headline older than the edge price', { ...detail, hero_probability_observed_at: '2026-09-25T23:10:30Z' }, served],
    ['unknown headline clock', { ...detail, hero_probability_observed_at: null as unknown as string }, served],
    ['unknown edge clock (legacy cache entry)', detail, { ...served, blend_edge_observed_at: null as unknown as string }],
    ['unparseable edge clock', detail, { ...served, blend_edge_observed_at: 'soon' }],
  ])('%s: the chart is left alone', (_label, hero, history) => {
    const merged = mergeLiveChartHistory(history, rememberLiveChartFrame([], frameAt('2026-09-25T23:10:50Z', 0.358), EVENT_ID));
    expect(appendHeroObservation(merged, hero, history)).toBe(merged);
  });

  test('equal clocks adopt nothing', () => {
    const equal = { ...detail, hero_probability_observed_at: '2026-09-25T23:11:05Z' };
    expect(adoptNewerBlendEdge(equal, { p: 0.532, observedAt: '2026-09-25T23:11:05.000Z' })).toBe(equal);
  });

  test('an unknown clock on either side keeps #3911 cross-worker pin', () => {
    expect(last(pinChartEdgeToHero({ ...served, blend_edge_observed_at: null as unknown as string }, detail)).home_probability).toBe(0.3513);
    expect(last(pinChartEdgeToHero(served, { ...detail, hero_probability_observed_at: null as unknown as string })).home_probability).toBe(0.3513);
  });

  test('the merged array is the same object when nothing lands', () => {
    expect(appendHeroObservation(pushed, { ...detail, hero_probability: 0.363 }, served)).toBe(pushed);
  });
});

describe('terminal and non-blend headlines are untouched', () => {
  const edge = { p: 0.99, observedAt: '2026-09-25T23:59:00Z' };
  test.each([
    ['completed', { ...detail, status: 'completed' }],
    ['settled hero', { ...detail, hero_probability_source: 'settled' as unknown as 'blend' }],
    ['opening fallback', { ...detail, hero_probability_source: 'opening' as unknown as 'blend' }],
    ['no headline number', { ...detail, hero_probability: null as unknown as number }],
  ])('%s: no adoption', (_label, event) => {
    expect(adoptNewerBlendEdge(event, edge)).toBe(event);
  });

  test.each([
    ['unpinned', { ...served, blend_edge_pinned: false }],
    ['no clock', { ...served, blend_edge_observed_at: null as unknown as string }],
    ['no line', { ...served, aggregate_line: [] }],
    ['out-of-range edge', { ...served, aggregate_line: [{ timestamp: SERVE_MINUTE, home_probability: 1.5 }] }],
  ])('%s history: no edge observation', (_label, history) => {
    expect(servedBlendEdgeObservation(history)).toBeNull();
  });
});

test('the page wires both directions', () => {
  const fs = require('fs');
  const path = require('path');
  const page: string = fs.readFileSync(path.join(__dirname, '../../app/events/[id]/page.tsx'), 'utf8');
  expect(page).toContain('isLive ? appendHeroObservation(joined, event, servedHistory) : joined');
  expect(page).toContain('() => latestBlendEdgeRef.current,');
  expect(page).toMatch(/const edge = servedBlendEdgeObservation\(servedHistory\);\s+latestBlendEdgeRef\.current = edge;/);
  expect(page).toContain('refreshEvent((prev) => adoptNewerBlendEdge(prev, edge), { revalidate: false });');
});
