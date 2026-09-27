import { fetchEventWithLiveFrame } from '@/lib/reconcileEventPoll';
import { rememberLiveChartFrame, mergeLiveChartHistory, appendHeroObservation } from '@/lib/liveChartHistory';
import { pinChartEdgeToHero } from '@/lib/chartEdgePin';
import { servedBlendEdgeObservation } from '@/lib/blendObservationClock';
import { chartRevisionRefreshKey } from '@/lib/chartRevisionRefresh';
import { createFoldedRefetchScheduler } from '@/lib/foldedRefetchScheduler';
import fs from 'fs';
import path from 'path';

const quoteAt = '2026-09-27T05:00:00Z';
const frameAt = '2026-09-27T05:01:10Z';
const laterAt = '2026-09-27T05:01:30Z';
const oldFrame = {
  event_id: 123, status: 'live', source: 'kalshi', source_value: 0.8,
  p: 0.6, updated_at: frameAt, rev: { '123': 2 },
};
const points = rememberLiveChartFrame([], oldFrame, 123);
const initialHistory = {
  aggregate_line: [{ timestamp: quoteAt, home_probability: 0.45 }],
  blend_edge_pinned: true,
  blend_edge_observed_at: quoteAt,
  blend_edge_fold_revision: { '123': 1 },
};
function retired() {
  return {
    id: 123, status: 'live', hero_probability_source: 'blend',
    hero_probability: 0.4, hero_probability_away: 0.6,
    hero_probability_observed_at: quoteAt, blend_fold_revision: { '123': 3 },
    win_probability_sources: { polymarket: { value: 0.4, updated_at: quoteAt } },
  };
}
// Exact EventPage composition at e24de556a:743-750. A real pushed point is
// historical evidence; applying the ordinary pin must not overwrite it.
function pageChart(history: typeof initialHistory, event: ReturnType<typeof retired>, buffer = points) {
  const pushed = mergeLiveChartHistory(history, buffer);
  const joined = pushed !== history ? pushed : pinChartEdgeToHero(history, event);
  return appendHeroObservation(joined, event, history)!;
}
function retainsRealSixty(history: ReturnType<typeof pageChart>) {
  expect(history.aggregate_line).toContainEqual({ timestamp: frameAt, home_probability: 0.6 });
}

describe('#9051 current blend after source removal', () => {
  test('newer detail revision requests authoritative history without rewriting a real observation', async () => {
    const event = await fetchEventWithLiveFrame(async () => retired(), () => oldFrame,
      () => servedBlendEdgeObservation(initialHistory));
    const history = pageChart(initialHistory, event);
    expect(event.hero_probability).toBe(0.4);
    expect(event.blend_fold_revision).toEqual({ '123': 3 });
    retainsRealSixty(history);
    expect(history.aggregate_line.at(-1)?.home_probability).toBe(0.6);
    expect(chartRevisionRefreshKey(event, initialHistory, history)).not.toBeNull();
    // A current-state endpoint comes from the history response, never from a
    // client-invented clock on the surviving quote.
    const refreshed = { ...initialHistory,
      aggregate_line: [...initialHistory.aggregate_line,
        { timestamp: '2026-09-27T05:01:20Z', home_probability: 0.4 }],
      blend_edge_fold_revision: { '123': 3 },
    };
    const corrected = pageChart(refreshed, event);
    retainsRealSixty(corrected);
    expect(corrected.aggregate_line.at(-1)?.home_probability).toBe(0.4);
    expect(chartRevisionRefreshKey(event, refreshed, corrected)).toBeNull();
  });

  test('fresh paired history uses its exact current-state pin after a real frame in the same minute', async () => {
    // Backend _pin_blend_edge at actual now05:01:20 no longer floors to05:01:00.
    // The vector has ordering, but is not a new quote or removal timestamp.
    const refreshed = { ...initialHistory,
      aggregate_line: [...initialHistory.aggregate_line,
        { timestamp: '2026-09-27T05:01:20Z', home_probability: 0.4 }],
      blend_edge_fold_revision: { '123': 3 },
    };
    const event = await fetchEventWithLiveFrame(async () => retired(), () => oldFrame,
      () => servedBlendEdgeObservation(refreshed));
    const history = pageChart(refreshed, event);
    expect(event.hero_probability).toBe(0.4);
    retainsRealSixty(history);
    expect(history.aggregate_line.at(-1)?.home_probability).toBe(0.4);
  });

  test('control: a server pin in the next minute can end on40 without erasing prior60', async () => {
    const refreshed = { ...initialHistory,
      aggregate_line: [...initialHistory.aggregate_line,
        { timestamp: '2026-09-27T05:02:00Z', home_probability: 0.4 }],
      blend_edge_fold_revision: { '123': 3 },
    };
    const event = await fetchEventWithLiveFrame(async () => retired(), () => oldFrame,
      () => servedBlendEdgeObservation(refreshed));
    const history = pageChart(refreshed, event);
    retainsRealSixty(history);
    expect(history.aggregate_line.at(-1)?.home_probability).toBe(0.4);
  });

  test('control: a real surviving-source publication updates both headline and line', async () => {
    const fresh = { event_id: 123, status: 'live', source: 'polymarket',
      source_value: 0.5, p: 0.5, updated_at: laterAt, rev: { '123': 4 } };
    const event = await fetchEventWithLiveFrame(async () => retired(), () => fresh,
      () => servedBlendEdgeObservation(initialHistory));
    const history = pageChart(initialHistory, event, rememberLiveChartFrame(points, fresh, 123));
    expect(event.hero_probability).toBe(0.5);
    retainsRealSixty(history);
    expect(history.aggregate_line.at(-1)?.home_probability).toBe(0.5);
    expect(chartRevisionRefreshKey(event, initialHistory, history)).toBeNull();
  });

  test('changed cohort requests history, while older/equal/unknown revisions do not', () => {
    const event = retired();
    const history = pageChart(initialHistory, event);
    expect(chartRevisionRefreshKey({ ...event, blend_fold_revision: { '124': 1 } }, initialHistory, history)).not.toBeNull();
    for (const revision of [{ '123': 0 }, { '123': 1 }, undefined, { '123': NaN }]) {
      expect(chartRevisionRefreshKey({ ...event, blend_fold_revision: revision }, initialHistory, history)).toBeNull();
    }
    expect(chartRevisionRefreshKey(event, { ...initialHistory, blend_edge_fold_revision: undefined }, history)).toBeNull();
    expect(chartRevisionRefreshKey({ ...event, status: 'final' }, initialHistory, history)).toBeNull();
    expect(chartRevisionRefreshKey(event, { ...initialHistory, aggregate_line: [] }, history)).toBeNull();
  });

  test('revision keys are stable across object ordering and an already matching endpoint requests nothing', () => {
    const event = retired();
    const history = pageChart(initialHistory, event);
    const a = chartRevisionRefreshKey({ ...event, blend_fold_revision: { '123': 3, twin: 2 } }, initialHistory, history);
    const b = chartRevisionRefreshKey({ ...event, blend_fold_revision: { twin: 2, '123': 3 } }, initialHistory, history);
    expect(a).toBe(b);
    expect(chartRevisionRefreshKey(event, initialHistory, {
      aggregate_line: [{ timestamp: frameAt, home_probability: 0.4 }],
    })).toBeNull();
  });

  test('distinct removal revisions inside the floor get a trailing history request after silence', () => {
    jest.useFakeTimers();
    try {
      jest.setSystemTime(new Date(frameAt));
      const refresh = jest.fn();
      const scheduler = createFoldedRefetchScheduler(refresh, 5000);
      const requested = new Set<string>();
      const deliver = (revision: number) => {
        const event = { ...retired(), blend_fold_revision: { '123': revision } };
        const key = chartRevisionRefreshKey(event, initialHistory, pageChart(initialHistory, event));
        if (key && !requested.has(key)) { requested.add(key); scheduler.request(); }
      };
      deliver(3);
      deliver(3); // unchanged cached history/re-render must not spin
      expect(refresh).toHaveBeenCalledTimes(1);
      jest.advanceTimersByTime(1000);
      deliver(4);
      expect(refresh).toHaveBeenCalledTimes(1);
      jest.advanceTimersByTime(4000);
      expect(refresh).toHaveBeenCalledTimes(2);
      jest.advanceTimersByTime(10000);
      expect(refresh).toHaveBeenCalledTimes(2);
      scheduler.cancel();
    } finally {
      jest.useRealTimers();
    }
  });

  test('the page requests history through the bounded scheduler without mutating chart points', () => {
    const page = fs.readFileSync(path.join(__dirname, '../../app/events/[id]/page.tsx'), 'utf8');
    expect(page).toContain('chartRevisionRefreshKey(event, servedHistory, historyData)');
    expect(page).toMatch(/createFoldedRefetchScheduler\(\s*\(\) => \{ void refreshHistoryRef\.current\(\); \}, FOLDED_FRAME_REFETCH_MS,/);
    expect(page).toMatch(/if \(requestedChartRevisionRef\.current === key\) return;\s*requestedChartRevisionRef\.current = key;\s*foldedHistoryRefetch\.request\(\);/);
    expect(page).toContain('() => foldedHistoryRefetch.cancel()');
  });
});
