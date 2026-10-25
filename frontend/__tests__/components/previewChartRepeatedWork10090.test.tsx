/** @jest-environment jsdom */
// Retained production fixture; work-count regression, not a wall-clock benchmark.
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { readFileSync } from 'fs';
import { join } from 'path';
import * as gameState from '@/lib/chartGameState';
import * as support from '@/lib/chartObservationSupport';
import OddsChart from '@/components/OddsChart';

jest.mock('@/components/Analytics/AnalyticsProvider', () => ({
  useAnalyticsContext: () => ({ track() {} }),
}));
jest.mock('recharts', () => ({
  ...jest.requireActual('recharts'),
  ResponsiveContainer: ({ children }: { children: React.ReactElement }) =>
    React.cloneElement(children, { width: 390, height: 300 }),
}));
const body = JSON.parse(readFileSync(join(__dirname, '../fixtures/periodLabelRightRule.15314713.mlb-live-t10.json'), 'utf8'));
const props = {
  history: body.history, bookmakerHistory: body.bookmaker_history,
  winProbHistory: body.win_prob_history, winProbSources: body.win_prob_sources,
  espnHistory: body.espn_history, scoreHistory: body.score_history,
  scoringPlays: body.scoring_plays,
  backendBlendServed: true, homeTeam: body.home_team, awayTeam: body.away_team,
  sportKey: 'baseball_mlb', isLive: true, eventStatus: 'live', commenceTime: body.commence_time,
  chartStartTime: body.commence_time, chartEndTime: '2026-09-20T04:47:00Z',
};

test('a changed preview retains source filtering and classification when cutoffs do not move', async () => {
  const previous = (globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT;
  (globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;
  jest.useFakeTimers().setSystemTime(Date.parse('2026-09-20T04:47:00Z'));
  const stamp = jest.spyOn(gameState, 'stampObservedGameState');
  const classify = jest.spyOn(support, 'classifySeriesSupport');
  const host = document.createElement('div');
  document.body.appendChild(host);
  const root = createRoot(host);
  const render = async (line: typeof body.aggregate_line, overrides: Partial<React.ComponentProps<typeof OddsChart>> = {}) => {
    await act(async () => root.render(<OddsChart {...props} {...overrides} aggregateLine={line} />));
  };
  try {
    await render(body.aggregate_line);
    const mounted = stamp.mock.calls.length;
    const classified = classify.mock.calls.length;
    expect(mounted).toBeGreaterThan(0);
    const initialHtml = host.innerHTML;
    await render(body.aggregate_line);
    expect(stamp).toHaveBeenCalledTimes(mounted);
    expect(classify).toHaveBeenCalledTimes(classified);
    expect(host.innerHTML).toBe(initialHtml);
    const line = [...body.aggregate_line, { timestamp: '2026-09-20T04:46:30Z', home_probability: .55 }];
    await render(line);
    expect(stamp).toHaveBeenCalledTimes(mounted + 1);
    expect(classify).toHaveBeenCalledTimes(classified);
    // The unchanged game-state arrays are processed again solely because the
    // disposable aggregate edge changed. Values are not timed as user latency.
    const before = stamp.mock.calls[mounted - 1];
    const after = stamp.mock.calls[mounted];
    expect(after[1]).toBe(before[1]);
    expect(after[2]).toEqual(before[2]);
    expect(host.querySelector('[data-callout-label]')?.getAttribute('data-callout-label')).toBe('55%');
    expect(body.aggregate_line).toHaveLength(614);
    const previewHtml = host.innerHTML;
    // New source data must invalidate even with the identical numeric cutoff.
    let priorCount = classify.mock.calls.length;
    await render(line, { espnHistory: [...body.espn_history] });
    expect(classify.mock.calls.length).toBeGreaterThan(priorCount);
    expect(host.innerHTML).toBe(previewHtml);
    // Restore source identity before independently testing a moved cutoff.
    await render(line);
    // A genuinely moved start changes filtering, not just its Date identity.
    priorCount = classify.mock.calls.length;
    await render(line, { chartStartTime: '2026-09-20T03:00:00Z' });
    expect(classify.mock.calls.length).toBeGreaterThan(priorCount);
    const moved = stamp.mock.calls[stamp.mock.calls.length - 1][1]!;
    expect(moved.length).toBeLessThan(after[1]!.length);
    expect(moved.every(row => Date.parse(row.timestamp) >= Date.parse('2026-09-20T03:00:00Z'))).toBe(true);
    // A start beyond all observations fails the original survival guard and
    // becomes null. The uncut source array must be restored, not cached away.
    priorCount = classify.mock.calls.length;
    await render(line, { chartStartTime: '2099-01-01T00:00:00Z' });
    expect(classify.mock.calls.length).toBeGreaterThan(priorCount);
    expect(stamp.mock.calls[stamp.mock.calls.length - 1][1]).toBe(body.espn_history);
    // Restoring the original window restores the identical complete DOM.
    await render(line);
    expect(host.innerHTML).toBe(previewHtml);
    // A genuine right-edge move still reclassifies trailing source support.
    priorCount = classify.mock.calls.length;
    await render(line, { chartEndTime: '2026-09-20T04:48:00Z' });
    expect(classify.mock.calls.length).toBeGreaterThan(priorCount);
  } finally {
    await act(async () => root.unmount());
    host.remove(); stamp.mockRestore(); classify.mockRestore(); jest.useRealTimers();
    (globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = previous;
  }
});

test('a completed-game end cutoff refilters stable sources and preserves the survival floor', async () => {
  const previous = (globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT;
  (globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;
  jest.useFakeTimers().setSystemTime(Date.parse('2026-10-21T20:03:00Z'));
  const stamp = jest.spyOn(gameState, 'stampObservedGameState');
  const classify = jest.spyOn(support, 'classifySeriesSupport');
  const source = [
    { timestamp: '2026-10-21T20:00:00Z', home_probability: .5, away_probability: .5 },
    { timestamp: '2026-10-21T20:01:00Z', home_probability: .6, away_probability: .4 },
    { timestamp: '2026-10-21T20:02:00Z', home_probability: .7, away_probability: .3 },
  ];
  const closedProps: React.ComponentProps<typeof OddsChart> = {
    history: [], winProbHistory: { kalshi: source }, aggregateLine: source,
    homeTeam: 'Home', awayTeam: 'Away', backendBlendServed: true,
    isLive: false, eventStatus: 'completed', externalTimeRange: 'all',
    chartStartTime: source[0].timestamp, commenceTime: source[0].timestamp,
  };
  // With no game-end source or sportsbook rows, completedAt determines the
  // real end cutoff. Keep every source array and the start fixed throughout.
  const host = document.createElement('div');
  document.body.appendChild(host);
  const root = createRoot(host);
  const render = async (completedAt: string) => {
    await act(async () => root.render(<OddsChart {...closedProps} completedAt={completedAt} />));
  };
  const classifiedTimes = () => classify.mock.calls[classify.mock.calls.length - 1][0].map(row => row.atMs);
  const stampedSource = () => stamp.mock.calls[stamp.mock.calls.length - 1][2]![0];
  try {
    await render(source[1].timestamp);
    expect(classifiedTimes()).toEqual(source.slice(0, 2).map(row => Date.parse(row.timestamp)));
    expect(stampedSource()).toEqual(source.slice(0, 2));
    expect(host.querySelector('[data-callout-label]')?.getAttribute('data-callout-label')).toBe('60%');
    const clippedHtml = host.innerHTML;
    let classified = classify.mock.calls.length;
    await render(source[1].timestamp);
    expect(classify).toHaveBeenCalledTimes(classified);

    await render(source[2].timestamp);
    expect(classify.mock.calls.length).toBeGreaterThan(classified);
    expect(classifiedTimes()).toEqual(source.map(row => Date.parse(row.timestamp)));
    expect(stampedSource()).toEqual(source);
    expect(host.querySelector('[data-callout-label]')?.getAttribute('data-callout-label')).toBe('70%');

    // A cutoff before every observation must become null, preserving the
    // journey rather than memoizing an empty filtered series.
    classified = classify.mock.calls.length;
    await render('2026-10-21T19:59:00Z');
    expect(classify.mock.calls.length).toBeGreaterThan(classified);
    expect(stampedSource()).toEqual(source);
    expect(host.querySelector('[data-callout-label]')?.getAttribute('data-callout-label')).toBe('70%');

    await render(source[1].timestamp);
    expect(stampedSource()).toEqual(source.slice(0, 2));
    expect(host.innerHTML).toBe(clippedHtml);
    expect(source).toHaveLength(3);
  } finally {
    await act(async () => root.unmount());
    host.remove(); stamp.mockRestore(); classify.mockRestore(); jest.useRealTimers();
    (globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = previous;
  }
});
