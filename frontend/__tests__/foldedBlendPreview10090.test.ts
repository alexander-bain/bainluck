import {
  displayedPreview, overlayBlendPreview, displayedProbabilityObservedAt,
  overlayBlendPreviewLine, parseBlendPreview, readerAfter, readerAfterCommitFloor,
  EMPTY_BLEND_PREVIEW_READER, type BlendPreviewFrame,
} from '@/lib/blendPreview';

const vector = { '1': 11, '2': 22, '3': 7 };
const held = { id: 1, status: 'live', sport: 'soccer_epl', hero_probability_source: 'blend',
  hero_probability: .4, hero_probability_away: null, blend_fold_revision: vector };
function packet(): BlendPreviewFrame {
  return { event_id: 1, p: .48, p_away: null, sport: 'soccer_epl', status: 'live',
    display_observed_at: '2026-10-21T00:00:05Z',
    preview: { kind: 'blend', epoch: 8, seq: 12, base_rev: 22, ttl_ms: 5000,
      folded_version: 1, origin_event_id: 2, base_fold_revision: vector } };
}

test('one admitted full fold drives headline, observation and chart without an invented away', () => {
  const p = packet();
  expect(parseBlendPreview(JSON.stringify(p))).not.toBeNull();
  const reader = readerAfter(EMPTY_BLEND_PREVIEW_READER, p, 1, 100);
  expect(displayedPreview(reader.held, held, 101)).toBe(.48);
  expect(overlayBlendPreview(held, reader.held, 101)).toMatchObject({
    hero_probability: .48, hero_probability_away: null,
  });
  expect(displayedProbabilityObservedAt(held, reader.held, 101, 'old')).toBe(p.display_observed_at);
  expect(overlayBlendPreviewLine(held, reader.held, 101, [])).toEqual([
    { timestamp: p.display_observed_at, home_probability: .48 },
  ]);
  expect(displayedPreview(reader.held, held, 5100)).toBeNull();
  expect(held.hero_probability).toBe(.4);
});

test.each([{ '1': 12 }, { '2': 23 }, { '3': 8 }])('a raw member commit removes authority before detail finishes: %s', floor => {
  let reader = readerAfter(EMPTY_BLEND_PREVIEW_READER, packet(), 1, 0);
  reader = readerAfterCommitFloor(reader, floor);
  expect(reader.held).toBeNull();
  reader = readerAfter(reader, packet(), 1, 1);
  expect(reader.held).toBeNull();
});

test('old floors do not erase the warm preview; mixed or missing held vectors refuse', () => {
  const reader = readerAfterCommitFloor(readerAfter(EMPTY_BLEND_PREVIEW_READER, packet(), 1, 0), { '2': 21 });
  expect(reader.held).not.toBeNull();
  expect(displayedPreview(reader.held, { ...held, blend_fold_revision: { '1': 10, '2': 23, '3': 7 } }, 1)).toBeNull();
  expect(displayedPreview(reader.held, { ...held, blend_fold_revision: { '1': 11, '2': 22 } }, 1)).toBeNull();
  expect(displayedPreview(reader.held, { ...held, sport: 'basketball_nba' }, 1)).toBeNull();
  expect(displayedPreview(reader.held, { ...held, status: 'completed' }, 1)).toBeNull();
});

test('a source-origin revoke cannot withdraw another source origin', () => {
  const reader = readerAfter(EMPTY_BLEND_PREVIEW_READER, packet(), 1, 0);
  const revoke: BlendPreviewFrame = { event_id: 1, p: null,
    preview: { kind: 'revoke', epoch: 8, seq: 13, through_seq: 12, origin_event_id: 3 } };
  expect(readerAfter(reader, revoke, 1, 1).held).toBe(reader.held);
  revoke.preview.origin_event_id = 2;
  expect(readerAfter(reader, revoke, 1, 1).held).toBeNull();
});

test('a reordered preview cannot return after revoke or reconnect cleared the display', () => {
  let reader = readerAfter(EMPTY_BLEND_PREVIEW_READER, packet(), 1, 0);
  reader = readerAfter(reader, { event_id: 1, p: null,
    preview: { kind: 'revoke', epoch: 8, seq: 13, through_seq: 12, origin_event_id: 2 } }, 1, 1);
  expect(readerAfter(reader, packet(), 1, 2).held).toBeNull();
  const newer = packet(); newer.preview.seq = 14;
  reader = readerAfter(reader, newer, 1, 3);
  expect(reader.held).not.toBeNull();
  reader = { ...reader, held: null };
  expect(readerAfter(reader, newer, 1, 4).held).toBeNull();
});

test.each(['base', 'origin', 'away', 'version'])('malformed folded authority is rejected: %s', kind => {
  const p = packet();
  if (kind === 'base') p.preview.base_fold_revision = { '1': 11 };
  if (kind === 'origin') p.preview.origin_event_id = 4;
  if (kind === 'away') delete p.p_away;
  if (kind === 'version') p.preview.folded_version = 2;
  expect(parseBlendPreview(p)).toBeNull();
});
