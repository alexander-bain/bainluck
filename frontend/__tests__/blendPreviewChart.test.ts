import { overlayBlendPreviewLine, previewAfter, readerAfter, EMPTY_BLEND_PREVIEW_READER, type BlendPreviewFrame } from '@/lib/blendPreview';

const event = {id: 1, status: 'live', hero_probability_source: 'blend', blend_fold_revision: {'1': 10}};
const at = '2026-10-20T21:14:10.000Z';
const frame = (seq = 1): BlendPreviewFrame => ({event_id: 1, p: .75, status: 'live', display_observed_at: at, preview: {kind: 'blend', epoch: 4, seq, base_rev: 10, ttl_ms: 1000}});
const line = [{timestamp: '2026-10-20T21:14:09.000Z', home_probability: .6}];
const held = () => previewAfter(null, frame(), 1, 0);

test('extends only a render copy with the supplied observation, never receipt time or cached history', () => {
  Object.freeze(line[0]); Object.freeze(line);
  const copy = overlayBlendPreviewLine(event, held(), 500, line);
  expect(copy).toEqual([...line, {timestamp: at, home_probability: .75}]);
  expect(copy).not.toBe(line);
  expect(line).toHaveLength(1);
  expect(copy![0]).toBe(line[0]);
});

test.each([undefined, '', 'not-a-date'])('missing or malformed observation %s never invents a chart time', display_observed_at => {
  const state = previewAfter(null, {...frame(), display_observed_at}, 1, 0);
  expect(overlayBlendPreviewLine(event, state, 500, line)).toBe(line);
});

test.each(['2026-10-20T21:14:09.000Z', '2026-10-20T21:14:08.000Z'])('a preview observed at %s cannot rewrite a committed point', display_observed_at => {
  const state = previewAfter(null, {...frame(), display_observed_at}, 1, 0);
  expect(overlayBlendPreviewLine(event, state, 500, line)).toBe(line);
});

test('newer commit, expiry, terminal and another event restore the identical committed line', () => {
  expect(overlayBlendPreviewLine({...event, blend_fold_revision: {'1': 11}}, held(), 500, line)).toBe(line);
  expect(overlayBlendPreviewLine(event, held(), 1000, line)).toBe(line);
  expect(overlayBlendPreviewLine({...event, status: 'final'}, held(), 500, line)).toBe(line);
  expect(overlayBlendPreviewLine({...event, id: 2}, held(), 500, line)).toBe(line);
});

test('revoke and reconnect remove the temporary point without leaving history behind', () => {
  const revoke: BlendPreviewFrame = {event_id: 1, p: null, preview: {kind: 'revoke', epoch: 4, seq: 2, through_seq: 1}};
  const state = previewAfter(held(), revoke, 1, 500);
  expect(overlayBlendPreviewLine(event, state, 500, line)).toBe(line);
  expect(overlayBlendPreviewLine(event, null, 500, line)).toBe(line);
});

test('an old epoch cannot bring its chart point back after takeover', () => {
  let reader = readerAfter(EMPTY_BLEND_PREVIEW_READER, frame(), 1, 0);
  reader = readerAfter(reader, {event_id: 1, p: null, preview: {kind: 'revoke', epoch: 5, seq: 1, through_seq: 0}}, 1, 100);
  reader = readerAfter(reader, frame(99), 1, 200);
  expect(overlayBlendPreviewLine(event, reader.held, 500, line)).toBe(line);
});

test('legacy attempt clock never dates a chart, even when it is well-formed', () => {
  const state = previewAfter(null, {...frame(), display_observed_at: undefined, observed_at: at}, 1, 0);
  expect(overlayBlendPreviewLine(event, state, 500, line)).toBe(line);
});

test('newer retry sequence with identical observation leaves endpoint time unchanged', () => {
  const first = previewAfter(null, frame(1), 1, 0);
  const retry = previewAfter(first, {...frame(2), observed_at: '2026-10-20T21:14:20Z'}, 1, 400);
  expect(overlayBlendPreviewLine(event, retry, 500, line))
    .toEqual(overlayBlendPreviewLine(event, first, 500, line));
});


test('a same-revision history refresh cannot erase a newer preview with its synthetic read-time edge', () => {
  const committed = {timestamp: '2026-10-20T21:14:08Z', home_probability: .6};
  const before = {event_id: 1, aggregate_line: [committed, ...line],
    blend_edge_pinned: true, blend_edge_observed_at: committed.timestamp,
    blend_edge_fold_revision: {'1': 10}};
  const refreshed = {...before, aggregate_line: [committed,
    {timestamp: '2026-10-20T21:14:10.400Z', home_probability: .6}]};
  const snapshot = JSON.stringify(refreshed);
  const first = held();
  expect(overlayBlendPreviewLine(event, first, 100, before.aggregate_line, before)?.at(-1))
    .toEqual({timestamp: at, home_probability: .75});
  const projected = overlayBlendPreviewLine({...event}, first, 400, refreshed.aggregate_line, refreshed);
  expect(projected).toEqual([committed, {timestamp: at, home_probability: .75}]);
  const renewal = previewAfter(first, {...frame(2), observed_at: '2026-10-20T21:14:11Z'}, 1, 500);
  expect(overlayBlendPreviewLine({...event}, renewal, 600, refreshed.aggregate_line, refreshed)).toEqual(projected);
  expect(JSON.stringify(refreshed)).toBe(snapshot);
  expect(overlayBlendPreviewLine(event, null, 600, refreshed.aggregate_line, refreshed)).toBe(refreshed.aggregate_line);
});

test.each([
  {blend_edge_pinned: false}, {event_id: 2}, {blend_edge_observed_at: null},
  {blend_edge_observed_at: at}, {blend_edge_fold_revision: undefined},
  {blend_edge_fold_revision: {'1': 11}}, {blend_edge_fold_revision: {'2': 10}},
])('a synthetic-edge claim without current authority cannot replace history: %j', delta => {
  const served = {event_id: 1, aggregate_line: [
    {timestamp: '2026-10-20T21:14:10.400Z', home_probability: .6}],
    blend_edge_pinned: true, blend_edge_observed_at: '2026-10-20T21:14:08Z',
    blend_edge_fold_revision: {'1': 10}, ...delta};
  expect(overlayBlendPreviewLine(event, held(), 500, served.aggregate_line, served)).toBe(served.aggregate_line);
});

test('a real later observation before a synthetic edge still prevents an older preview', () => {
  const served = {event_id: 1, aggregate_line: [
    {timestamp: '2026-10-20T21:14:10.200Z', home_probability: .8},
    {timestamp: '2026-10-20T21:14:10.400Z', home_probability: .6}],
    blend_edge_pinned: true, blend_edge_observed_at: '2026-10-20T21:14:08Z',
    blend_edge_fold_revision: {'1': 10}};
  expect(overlayBlendPreviewLine(event, held(), 500, served.aggregate_line, served)).toBe(served.aggregate_line);
});
