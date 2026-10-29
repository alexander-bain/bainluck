/**
 * #10090 — the held chart's endpoint follows the headline's preview for the
 * preview's whole lifetime.
 *
 * Specimen: calibration's matched lab pair, 2026-10-29 20:20Z, base arm
 * (`artifacts/calibration-10090-11742-pair-20261029`, PAIR-TIMELINE `changes`).
 * The headline showed the 71% preview from +0.12 s to its 60 s lifetime; the
 * chart's drawn endpoint fell back to the committed 63% at +20.4 s (basis
 * preview → hero-edge) and stayed there through the next poll at +52.4 s
 * (basis history). Both falls are the 32 s history poll:
 *
 *   +20.4 s  the backend pins its read-time edge with the cached detail hero
 *            (0.42, fold 1=0) and the page's #8749 repair rewrites that edge in
 *            place to the committed headline (0.63). The overlay matched the
 *            synthetic edge by VALUE, so the rewritten copy read as a committed
 *            point newer than the preview.
 *   +52.4 s  the sources have been quiet 30 s, so the backend carries each one
 *            forward to the read time (`live_edge`) and the minute bucket of
 *            that read lands on the blend line after the preview's observation.
 *
 * The page pipeline below is `page.tsx`'s `historyData` memo (merge, pin, #8749)
 * with no source-observation bank.
 */
import { displayedPreview, overlayBlendPreviewLine, previewAfter, type BlendPreviewFrame } from '@/lib/blendPreview';
import { pinChartEdgeToHero } from '@/lib/chartEdgePin';
import { appendHeroObservation, mergeLiveChartHistory, type LiveChartFrame, type ServedEdgeClock } from '@/lib/liveChartHistory';

type Point = {timestamp: string; home_probability: number};
type Served = {
  event_id: number;
  aggregate_line: Point[];
  blend_edge_pinned: boolean;
  blend_edge_observed_at: string | null;
  blend_edge_fold_revision: Record<string, number> | null;
  win_prob_history: Record<string, Array<Point & {live_edge?: boolean}>>;
  history: Array<{timestamp: string; home_probability: number}>;
};

const PREVIEW_AT = '2026-10-29T20:02:43.715334+00:00';
const committedEvent = {
  id: 1, status: 'live', sport: 'tennis_atp', hero_probability: 0.63, hero_probability_source: 'blend',
  hero_probability_observed_at: '2026-10-29T13:02:37.742159-07:00', blend_fold_revision: {'1': 2},
};
// The two primes the stream pushed before the target (rev 1, rev 2).
const primes: LiveChartFrame[] = [
  {timestamp: '2026-10-29T13:02:37.727545-07:00', home_probability: 0.48875, rev: {'1': 1}},
  {timestamp: '2026-10-29T13:02:37.742159-07:00', home_probability: 0.63, rev: {'1': 2}},
];
const sources = {
  kalshi: [{timestamp: '2026-10-29T20:01:10+00:00', home_probability: 0.465},
    {timestamp: '2026-10-29T20:02:37.727545+00:00', home_probability: 0.6}],
  polymarket: [{timestamp: '2026-10-29T20:01:10+00:00', home_probability: 0.3775},
    {timestamp: '2026-10-29T20:02:37.742159+00:00', home_probability: 0.66}],
};

/** The 20:03:04 read (+20.4 s): edge pinned from the cached detail hero, no carry yet (26 s quiet). */
const pollAt20 = (): Served => ({
  event_id: 1,
  aggregate_line: [
    {timestamp: '2026-10-29T20:01:00+00:00', home_probability: 0.42125},
    {timestamp: '2026-10-29T20:02:00+00:00', home_probability: 0.63},
    {timestamp: '2026-10-29T20:03:04.064256+00:00', home_probability: 0.42125},
  ],
  blend_edge_pinned: true,
  blend_edge_observed_at: '2026-10-29T20:02:23.834954+00:00',
  blend_edge_fold_revision: {'1': 0},
  win_prob_history: {kalshi: [...sources.kalshi], polymarket: [...sources.polymarket]},
  history: [],
});

/** The 20:03:36 read (+52.4 s): fresh edge, and both sources carried to the read time. */
const pollAt52 = (): Served => ({
  event_id: 1,
  aggregate_line: [
    {timestamp: '2026-10-29T20:01:00+00:00', home_probability: 0.42125},
    {timestamp: '2026-10-29T20:02:00+00:00', home_probability: 0.63},
    {timestamp: '2026-10-29T20:03:00+00:00', home_probability: 0.63},
    {timestamp: '2026-10-29T20:03:36.081995+00:00', home_probability: 0.63},
  ],
  blend_edge_pinned: true,
  blend_edge_observed_at: '2026-10-29T20:02:37.742159+00:00',
  blend_edge_fold_revision: {'1': 2},
  win_prob_history: {
    kalshi: [...sources.kalshi, {timestamp: '2026-10-29T20:03:36+00:00', home_probability: 0.6, live_edge: true}],
    polymarket: [...sources.polymarket, {timestamp: '2026-10-29T20:03:36+00:00', home_probability: 0.66, live_edge: true}],
  },
  history: [],
});

/** The boot read at 20:02:36 (before the primes and the target). */
const bootRead = (): Served => ({
  event_id: 1,
  aggregate_line: [
    {timestamp: '2026-10-29T20:01:00+00:00', home_probability: 0.42125},
    {timestamp: '2026-10-29T20:02:36.425768+00:00', home_probability: 0.42125},
  ],
  blend_edge_pinned: true,
  blend_edge_observed_at: '2026-10-29T20:02:23.834954+00:00',
  blend_edge_fold_revision: {'1': 0},
  win_prob_history: {kalshi: [sources.kalshi[0]], polymarket: [sources.polymarket[0]]},
  history: [],
});

type HeldEvent = typeof committedEvent & {blend_fold_revision: Record<string, number>};

/** `page.tsx`'s `historyData` for a live, quote-eligible page. */
function pageLine(served: Served, event: HeldEvent, frames: LiveChartFrame[]): Point[] {
  const history = served as unknown as ServedEdgeClock;
  const pushed = mergeLiveChartHistory(history, frames);
  const joined = pushed !== history ? pushed : pinChartEdgeToHero(history, event);
  return appendHeroObservation(joined, event, history)!.aggregate_line as Point[];
}

const foldedFrame = (p: number, seq: number, observed = PREVIEW_AT): BlendPreviewFrame => ({
  event_id: 1, p, p_away: 1 - p, sport: 'tennis_atp', status: 'live', display_observed_at: observed,
  preview: {kind: 'blend', epoch: 3, seq, base_rev: 2, ttl_ms: 60_000,
    base_fold_revision: {'1': 2}, origin_event_id: 1},
});
const singletonFrame = (p: number, seq: number, observed = PREVIEW_AT): BlendPreviewFrame => ({
  event_id: 1, p, status: 'live', display_observed_at: observed,
  preview: {kind: 'blend', epoch: 3, seq, base_rev: 2, ttl_ms: 60_000},
});
const SHAPES = [['folded (v3, the specimen)', foldedFrame], ['singleton', singletonFrame]] as const;

const endpoint = (line: Point[] | undefined) => line?.[line.length - 1];

describe.each(SHAPES)('%s preview', (_name, frame) => {
  // Received at +116 ms like the specimen; it expires at its 60 s lifetime.
  const held = previewAfter(null, frame(0.71, 5), 1, 116);

  test('the +20.4 s poll: a synthetic edge the page rewrote to the headline does not end the preview early', () => {
    const served = pollAt20();
    const line = pageLine(served, committedEvent, primes);
    // The specimen's page state: the served read-time edge carries the headline's committed 63%.
    expect(endpoint(line)).toEqual({timestamp: '2026-10-29T20:03:04.064256+00:00', home_probability: 0.63});
    expect(displayedPreview(held, committedEvent, 20_416)).toBe(0.71);
    expect(endpoint(overlayBlendPreviewLine(committedEvent, held, 20_416, line, served)))
      .toEqual({timestamp: PREVIEW_AT, home_probability: 0.71});
  });

  test('the +52.4 s poll: the carry-forward minute after the preview does not end it early', () => {
    const served = pollAt52();
    const line = pageLine(served, committedEvent, primes);
    expect(line.map(point => point.timestamp)).toContain('2026-10-29T20:03:00+00:00');
    expect(endpoint(overlayBlendPreviewLine(committedEvent, held, 52_415, line, served)))
      .toEqual({timestamp: PREVIEW_AT, home_probability: 0.71});
  });

  test('the projection removes only those two presentation points; every reading and the cache stay', () => {
    const served = pollAt52();
    const snapshot = JSON.stringify(served);
    const line = pageLine(served, committedEvent, primes);
    const projected = overlayBlendPreviewLine(committedEvent, held, 52_415, line, served)!;
    expect(projected.slice(0, -1)).toEqual(line.filter(point => Date.parse(point.timestamp) < Date.parse(PREVIEW_AT)));
    expect(projected.slice(0, -1).every((point, i) => point === line[i])).toBe(true);
    expect(JSON.stringify(served)).toBe(snapshot);
  });

  /**
   * The page over 0–70 s with no commit: each history poll arrives at its
   * specimen time, and every 100 ms the chart's drawn endpoint must be the
   * number the headline shows.
   */
  test('headline and chart agree at every 100 ms from 0 to 70 s with no commit', () => {
    const polls: Array<[number, Served]> = [[-6_000, bootRead()], [20_416, pollAt20()], [52_415, pollAt52()]];
    for (let now = 0; now <= 70_000; now += 100) {
      const served = polls.filter(([at]) => at <= now).at(-1)![1];
      const state = now >= 116 ? held : null;
      const headline = displayedPreview(state, committedEvent, now) ?? committedEvent.hero_probability;
      const line = pageLine(served, committedEvent, primes);
      const chart = endpoint(overlayBlendPreviewLine(committedEvent, state, now, line, served))!.home_probability;
      expect({now, chart}).toEqual({now, chart: headline});
    }
    // The lifetime still ends both together: 60 s after receipt, committed truth.
    expect(displayedPreview(held, committedEvent, 60_116)).toBeNull();
  });

  test('a commit landing at 30 s replaces the preview on both, with the committed value at its own time', () => {
    const commit: LiveChartFrame = {timestamp: '2026-10-29T13:03:13.700000-07:00', home_probability: 0.71, rev: {'1': 3}};
    const committed: HeldEvent = {...committedEvent, hero_probability: 0.71, blend_fold_revision: {'1': 3},
      hero_probability_observed_at: commit.timestamp};
    for (const [now, served] of [[30_000, pollAt20()], [52_415, pollAt52()]] as const) {
      const line = pageLine(served, committed, [...primes, commit]);
      expect(displayedPreview(held, committed, now)).toBeNull();
      const projected = overlayBlendPreviewLine(committed, held, now, line, served);
      expect(projected).toBe(line);
      expect(endpoint(projected)!.home_probability).toBe(0.71);
    }
    // A later fresh read that already holds the commit ends on it too.
    const fresh = {...pollAt52(), blend_edge_fold_revision: {'1': 3},
      aggregate_line: [...pollAt52().aggregate_line.slice(0, -1), {timestamp: '2026-10-29T20:03:36.081995+00:00', home_probability: 0.71}]};
    const line = pageLine(fresh, committed, [...primes, commit]);
    expect(endpoint(overlayBlendPreviewLine(committed, held, 52_415, line, fresh))!.home_probability).toBe(0.71);
  });

  test('a newer preview moves both to its value at its own observation', () => {
    const newer = previewAfter(held, frame(0.75, 6, '2026-10-29T20:03:20+00:00'), 1, 36_000);
    for (const [now, served] of [[36_100, pollAt20()], [52_415, pollAt52()]] as const) {
      const line = pageLine(served, committedEvent, primes);
      expect(displayedPreview(newer, committedEvent, now)).toBe(0.75);
      expect(endpoint(overlayBlendPreviewLine(committedEvent, newer, now, line, served)))
        .toEqual({timestamp: '2026-10-29T20:03:20+00:00', home_probability: 0.75});
    }
  });

  test('settle returns the identical committed line on both', () => {
    const settled = {...committedEvent, status: 'final'};
    for (const served of [pollAt20(), pollAt52()]) {
      const line = pageLine(served, committedEvent, primes);
      expect(displayedPreview(held, settled, 30_000)).toBeNull();
      expect(overlayBlendPreviewLine(settled, held, 30_000, line, served)).toBe(line);
    }
  });

  describe('every other guard still returns the committed line', () => {
    test('a history whose edge revision is newer than the preview base', () => {
      const served = {...pollAt52(), blend_edge_fold_revision: {'1': 3}};
      const line = pageLine(served, committedEvent, primes);
      expect(overlayBlendPreviewLine(committedEvent, held, 52_415, line, served)).toBe(line);
    });

    test('a rewritten edge that is not the headline’s value, or whose headline clock is not before the preview', () => {
      const served = pollAt20();
      const line = pageLine(served, committedEvent, primes);
      const foreign = [...line.slice(0, -1), {...line[line.length - 1], home_probability: 0.5}];
      expect(overlayBlendPreviewLine(committedEvent, held, 20_416, foreign, served)).toBe(foreign);
      for (const hero_probability_observed_at of [PREVIEW_AT, '2026-10-29T20:02:50Z', null, undefined]) {
        const later = {...committedEvent, hero_probability_observed_at} as unknown as HeldEvent;
        expect(overlayBlendPreviewLine(later, held, 20_416, line, served)).toBe(line);
      }
    });

    test('a real source reading or a sportsbook reading in the carried minute', () => {
      const reading = pollAt52();
      reading.win_prob_history.kalshi.push({timestamp: '2026-10-29T20:03:20+00:00', home_probability: 0.6});
      const book = {...pollAt52(), history: [{timestamp: '2026-10-29T20:03:00+00:00', home_probability: 0.63}]};
      for (const served of [reading, book]) {
        const line = pageLine(served, committedEvent, primes);
        expect(overlayBlendPreviewLine(committedEvent, held, 52_415, line, served)).toBe(line);
      }
    });

    test('a carried minute is never removed while the read-time edge stays, or with no pinned edge to vouch for it', () => {
      const kept = {...pollAt52(), blend_edge_observed_at: '2026-10-29T20:02:50Z'};
      const unpinned = {...pollAt52(), aggregate_line: pollAt52().aggregate_line.slice(0, -1),
        blend_edge_pinned: false, blend_edge_observed_at: null, blend_edge_fold_revision: null};
      for (const served of [kept, unpinned]) {
        const line = pageLine(served, committedEvent, primes);
        expect(overlayBlendPreviewLine(committedEvent, held, 52_415, line, served)).toBe(line);
      }
    });

    test('a pushed frame after the preview’s observation', () => {
      const later: LiveChartFrame = {timestamp: '2026-10-29T20:02:50+00:00', home_probability: 0.63, rev: {'1': 2}};
      const served = pollAt20();
      const line = pageLine(served, committedEvent, [...primes, later]);
      expect(overlayBlendPreviewLine(committedEvent, held, 20_416, line, served)).toBe(line);
    });

    test('expiry, another event’s history and a missing observation clock', () => {
      const served = pollAt52();
      const line = pageLine(served, committedEvent, primes);
      expect(overlayBlendPreviewLine(committedEvent, held, 60_116, line, served)).toBe(line);
      expect(overlayBlendPreviewLine(committedEvent, held, 52_415, line, {...served, event_id: 2})).toBe(line);
      const unclocked = previewAfter(null, {...frame(0.71, 5), display_observed_at: undefined}, 1, 116);
      expect(overlayBlendPreviewLine(committedEvent, unclocked, 52_415, line, served)).toBe(line);
    });
  });
});
