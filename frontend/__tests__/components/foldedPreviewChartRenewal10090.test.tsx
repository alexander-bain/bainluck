import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { readFileSync } from 'fs';
import { join } from 'path';
import type { EventHistoryResponse } from '@/lib/types';
import { displayedProbabilityObservedAt, overlayBlendPreview, overlayBlendPreviewLine,
  previewAfter, type BlendPreviewFrame } from '@/lib/blendPreview';

jest.mock('@/components/Analytics/AnalyticsProvider', () => ({useAnalyticsContext: () => ({track: () => {}})}));
jest.mock('recharts', () => ({
  ...jest.requireActual('recharts'),
  ResponsiveContainer: ({children}: {children: React.ReactElement}) => React.cloneElement(children, {width: 390, height: 300}),
}));
import OddsChart from '@/components/OddsChart';

const served: EventHistoryResponse = JSON.parse(readFileSync(join(__dirname, '../fixtures/event-15322164-history-10093.json'), 'utf8'));
const event = {id: 15322164, sport: 'tennis', status: 'live', hero_probability_source: 'blend',
  hero_probability: .25, blend_fold_revision: {'15322164': 221, '2': 0}};
const observed = '2026-10-01T17:43:25Z';
const frame: BlendPreviewFrame = {event_id: event.id, p: .75, p_away: .25, sport: 'tennis',
  display_observed_at: observed, status: 'live', preview: {
    kind: 'blend', epoch: 4, seq: 1, base_rev: 221, ttl_ms: 10000,
    folded_version: 1, origin_event_id: event.id, base_fold_revision: event.blend_fold_revision,
  }};

// Render the real chart across a same-revision paired read and renewal.
// This tests generated SVG, not browser mount timing or physical paint.
test('same-observation renewal survives committed history rerenders in the folded chart', () => {
  let state = previewAfter(null, frame, event.id, 0);
  const historical = served.aggregate_line!.filter(p => Date.parse(p.timestamp) < Date.parse(observed));
  const refresh = {...served, event_id: event.id, aggregate_line: [...historical,
    {timestamp: '2026-10-01T17:43:25.400Z', home_probability: .25}],
    blend_edge_pinned: true, blend_edge_observed_at: '2026-10-01T17:43:20Z',
    blend_edge_fold_revision: event.blend_fold_revision};
  const draw = (history: EventHistoryResponse, now: number) => {
    const line = overlayBlendPreviewLine({...event}, state, now, history.aggregate_line ?? undefined, history);
    return renderToStaticMarkup(<><output>{overlayBlendPreview({...event}, state, now).hero_probability}</output>
      <time dateTime={displayedProbabilityObservedAt(event, state, now, '2026-10-01T17:43:20Z') ?? undefined}/>
      <OddsChart history={history.history} bookmakerHistory={history.bookmaker_history}
        winProbHistory={history.win_prob_history} winProbSources={history.win_prob_sources}
        aggregateLine={line} backendBlendServed homeTeam="Home" awayTeam="Away"
        isLive eventStatus="live" commenceTime="2026-10-01T15:00:00Z"/></>).replace(/recharts-line-\d+|recharts\d+-clip/g, 'RECHARTS_ID');
  };
  const first = draw({...served, aggregate_line: historical}, 100);
  expect(first).toContain('data-callout-label="75%"');
  expect(draw(refresh, 400)).toBe(first);
  expect(first).toContain('<output>0.75</output>');
  expect(first).toContain(`dateTime="${observed}"`);
  state = previewAfter(state, {...frame, observed_at: '2026-10-01T17:43:26Z',
    preview: {...frame.preview, seq: 2}}, event.id, 500);
  expect(draw({...refresh, aggregate_line: [...refresh.aggregate_line]}, 600)).toBe(first);
  expect(refresh.aggregate_line.at(-1)?.home_probability).toBe(.25);
  state = null;
  expect(draw(refresh, 700)).not.toBe(first);
  expect(draw(refresh, 700)).toContain('data-callout-label="25%"');
});
