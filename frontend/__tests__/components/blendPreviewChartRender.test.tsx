import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { readFileSync } from 'fs';
import { join } from 'path';
import type { EventHistoryResponse } from '@/lib/types';
import { overlayBlendPreviewLine, previewAfter, type BlendPreviewFrame } from '@/lib/blendPreview';

jest.mock('@/components/Analytics/AnalyticsProvider', () => ({useAnalyticsContext: () => ({track: () => {}})}));
jest.mock('recharts', () => ({
  ...jest.requireActual('recharts'),
  ResponsiveContainer: ({children}: {children: React.ReactElement}) => React.cloneElement(children, {width: 390, height: 300}),
}));
import OddsChart from '@/components/OddsChart';
import { computeSharedChartDomain } from '@/lib/eventKeyStats';

const served: EventHistoryResponse = JSON.parse(readFileSync(join(__dirname, '../fixtures/event-15322164-history-10093.json'), 'utf8'));
const event = {id: 15322164, status: 'live', hero_probability_source: 'blend', blend_fold_revision: {'15322164': 221}};
const frame: BlendPreviewFrame = {event_id: event.id, p: .75, observed_at: '2026-10-01T17:43:25Z', status: 'live', preview: {kind: 'blend', epoch: 4, seq: 1, base_rev: 221, ttl_ms: 1000}};
const held = previewAfter(null, frame, event.id, 0);
const domain = computeSharedChartDomain(served, 'live', 'live', '2026-10-01T15:00:00Z', 'tennis');
const render = (line: EventHistoryResponse['aggregate_line']) => renderToStaticMarkup(<OddsChart
  history={served.history} bookmakerHistory={served.bookmaker_history}
  winProbHistory={served.win_prob_history} winProbSources={served.win_prob_sources}
  aggregateLine={line ?? undefined} backendBlendServed homeTeam="Harris/Hsieh" awayTeam="Lammons/Withrow"
  isLive eventStatus="live" commenceTime="2026-10-01T15:00:00Z"
  chartStartTime={domain?.start} chartEndTime={domain?.end}
  sharedTicks={domain?.ticks} chartLabelFormat={domain?.labelFormat}
/>).replace(/recharts-line-\d+|recharts\d+-clip/g, "RECHARTS_GENERATED_ID");

test('the real chart draws the admitted preview before any commit, and expiry restores the original rendering', () => {
  const before = JSON.stringify(served);
  const parent = render(served.aggregate_line);
  const candidate = render(overlayBlendPreviewLine(event, held, 500, served.aggregate_line ?? undefined));
  expect(parent).toContain('data-callout-label="25%"');
  expect(candidate).toContain('data-callout-label="75%"');
  expect(candidate).toMatch(/recharts-line-curve/);
  expect(render(overlayBlendPreviewLine(event, held, 1000, served.aggregate_line ?? undefined))).toBe(parent);
  expect(JSON.stringify(served)).toBe(before);
});

test('a newer committed revision cannot be covered by an older provisional chart point', () => {
  expect(render(overlayBlendPreviewLine({...event, blend_fold_revision: {'15322164': 222}}, held, 500, served.aggregate_line ?? undefined))).toBe(render(served.aggregate_line));
});
