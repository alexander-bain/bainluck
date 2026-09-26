import { adoptNewerBlendEdge, servedBlendEdgeObservation } from '@/lib/blendObservationClock';
import { pinChartEdgeToHero } from '@/lib/chartEdgePin';
import { applyLiveFrame } from '@/lib/eventLivePush';
import { appendHeroObservation, mergeLiveChartHistory, rememberLiveChartFrame, type LiveChartFrame } from '@/lib/liveChartHistory';
import { createLiveStreamController, type LiveStreamFrame } from '@/lib/liveStreamController';
import { reconcileEventPoll } from '@/lib/reconcileEventPoll';

const detail = {
  id: 15318356, status: 'live', hero_probability: .5203, hero_probability_away: .4797,
  hero_probability_source: 'blend', hero_probability_observed_at: '2026-09-25T23:10:40Z' as string | null | undefined,
  home_score: 3, win_probability_sources: {
    kalshi: { value: .5203, updated_at: '2026-09-25T23:10:40Z', display_name: 'Kalshi', color: 'green' },
  },
};
const history = {
  aggregate_line: [
    { timestamp: '2026-09-25T23:10:00Z', home_probability: .382 },
    { timestamp: '2026-09-25T23:11:00Z', home_probability: .532 },
  ],
  blend_edge_pinned: true, blend_edge_observed_at: '2026-09-25T23:11:05Z',
};
const frame = (updated_at: string, p: number): LiveStreamFrame & { p: number } => ({
  event_id: detail.id, status: 'live', source: 'kalshi', source_value: p, updated_at, p,
});

// Actual controller -> transport callback -> cache mutation -> page chart join.
// The history effect fires only when history changes, not again on each frame.
function page(initial = detail) {
  let event = initial;
  let points: LiveChartFrame[] = [];
  const callbacks: Record<string, (event: unknown) => void> = {};
  const close = jest.fn();
  const delivering = jest.fn();
  const controller = createLiveStreamController({
    open: () => ({ readyState: 1, close, addEventListener: (name, callback) => { callbacks[name] = callback; } }),
    now: () => 0,
    onDeliveringChange: delivering,
    onFrame: next => {
      points = rememberLiveChartFrame(points, next, detail.id);
      if (next.event_id === detail.id && next.p !== null) {
        event = applyLiveFrame(event, { ...next, p: next.p })!;
      }
    },
  });
  controller.start();
  return {
    receive: (next: LiveStreamFrame) => callbacks.probability({ data: JSON.stringify(next) }),
    adopt: () => { event = adoptNewerBlendEdge(event, servedBlendEdgeObservation(history))!; },
    event: () => event,
    edge: () => {
      const pushed = mergeLiveChartHistory(history, points);
      const joined = pushed !== history ? pushed : pinChartEdgeToHero(history, event);
      return appendHeroObservation(joined, event, history)!.aggregate_line!.at(-1)!;
    },
    close: () => callbacks.closed({}),
    closeHandle: close,
    delivering,
  };
}

describe('live observation ordering across separate history and SSE transports', () => {
  test.each([
    ['history first', '2026-09-25T23:10:55Z'],
    ['frame first', '2026-09-25T23:10:55Z'],
    ['history first', '2026-09-25T23:11:02Z'],
    ['frame first', '2026-09-25T23:11:02Z'],
  ])('%s at %s converges without rolling a known newer hero back', (order, at) => {
    const held = page();
    const old = frame(at, .52);
    if (order === 'history first') { held.adopt(); held.receive(old); }
    else { held.receive(old); held.adopt(); }
    expect(held.event().hero_probability).toBe(.532);
    expect(held.event().hero_probability_observed_at).toBe(history.blend_edge_observed_at);
    expect(held.edge().home_probability).toBe(.532);
    expect(held.event().home_score).toBe(3);
  });

  test('newer detail also survives a delayed frame without changing source metadata', () => {
    const newer = { ...detail, hero_probability: .54, hero_probability_observed_at: '2026-09-25T23:11:10Z' };
    const held = page(newer);
    held.receive(frame('2026-09-25T23:10:55Z', .52));
    expect(held.event()).toBe(newer);
    expect(held.event().win_probability_sources).toBe(newer.win_probability_sources);
    expect(held.edge().home_probability).toBe(.54);
  });

  test('a newer frame still advances value/clock and retains source display metadata', () => {
    const held = page(); held.adopt();
    held.receive(frame('2026-09-25T23:11:20Z', .56));
    expect(held.event().hero_probability).toBe(.56);
    expect(held.event().hero_probability_observed_at).toBe('2026-09-25T23:11:20Z');
    expect(held.edge().home_probability).toBe(.56);
    expect(held.event().win_probability_sources.kalshi).toMatchObject({ value: .56, display_name: 'Kalshi', color: 'green' });
    held.close();
    expect(held.closeHandle).toHaveBeenCalled();
    expect(held.delivering).toHaveBeenLastCalledWith(false);
    held.receive(frame('2026-09-25T23:11:30Z', .57));
    expect(held.event().hero_probability).toBe(.56);
  });

  test.each([null, undefined, 'not-a-clock'])('unknown current clock %s preserves the existing frame path', clock => {
    const held = page({ ...detail, hero_probability_observed_at: clock });
    held.receive(frame('2026-09-25T23:10:55Z', .52));
    expect(held.event().hero_probability).toBe(.52);
  });

  test('equal clocks retain existing frame precedence', () => {
    const held = page();
    held.receive(frame(detail.hero_probability_observed_at!, .52));
    expect(held.event().hero_probability).toBe(.52);
  });
});

describe('poll provenance is unknown when the backend explicitly says so', () => {
  const mixed = {
    ...detail, hero_probability: .63,
    win_probability_sources: { ...detail.win_probability_sources, polymarket: { value: .74, updated_at: undefined } },
  };
  test.each([null, '', 'not-a-clock'])('explicit %s cannot borrow a partial source clock', clock => {
    const polled = { ...mixed, hero_probability_observed_at: clock };
    expect(reconcileEventPoll(polled, frame('2026-09-25T23:10:55Z', .55))).toBe(polled);
  });
  test('an absent legacy field retains source-clock compatibility', () => {
    const polled = { ...mixed, hero_probability_observed_at: undefined };
    expect(reconcileEventPoll(polled, frame('2026-09-25T23:10:55Z', .55)).hero_probability).toBe(.55);
  });
  test.each(['completed', 'closed', 'scheduled'])('%s keeps REST lifecycle authoritative', status => {
    const polled = { ...mixed, status, hero_probability_observed_at: null };
    expect(reconcileEventPoll(polled, frame('2026-09-25T23:10:55Z', .55))).toBe(polled);
  });
});
