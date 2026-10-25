import {
  EMPTY_BLEND_PREVIEW_READER, parseBlendPreview, readerAfter,
  readerAfterCommitFloor, readerAfterPreviewOpen, readerAfterPreviewReset, readerAfterPreviewMembership,
  displayedPreview, displayedProbabilityObservedAt, overlayBlendPreviewLine,
  type BlendPreviewReader,
} from '@/lib/blendPreview';
const vector = {'1': 10, '2': 20};
const event = {id: 1, status: 'live', sport: 'tennis', hero_probability_source: 'blend', blend_fold_revision: vector};
const pending = (epoch: number, seq: number, ttl_ms = 1000) => ({epoch, seq, state: 'pending', ttl_ms});
const retired = (epoch: number, seq: number, state = 'revoked') => ({epoch, seq, state});
const packet = (fold_seq: number, origin_authority: Record<string, unknown> = {'1': pending(900, 2), '2': pending(12, 80)}, extra: Record<string, unknown> = {}) => ({
  event_id: 1, p: .7, p_away: .3, sport: 'tennis', status: 'live', display_observed_at: '2026-10-21T20:00:04Z',
  preview: {kind: 'blend', folded_version: 2, fold_session: 'session_one', fold_seq,
    base_fold_revision: vector, origin_authority, ttl_ms: 1000, ...extra},
});
const open = (r = EMPTY_BLEND_PREVIEW_READER, session = 'session_one') => readerAfterPreviewOpen(r, {event_id: 1, fold_session: session}, 1);
const accept = (r: BlendPreviewReader, value: unknown, now = 0) => {
  const frame = parseBlendPreview(value); expect(frame).not.toBeNull();
  return readerAfter(r, frame!, 1, now);
};
test('membership replacement prunes removed floors and preserves surviving origin fences', () => {
  let r = readerAfterPreviewMembership(EMPTY_BLEND_PREVIEW_READER, vector, 1);
  r = accept(open(r), packet(1));
  r = readerAfterCommitFloor(r, {'2': 99});
  r = readerAfterPreviewMembership(readerAfterPreviewReset(r), {'1': 10, '3': 30}, 1);
  expect(r.floors).toEqual({'1': 10, '3': 30});
  expect(Object.keys(r.multiOrigin!.authorities)).toEqual(['1']);
  const next = packet(1, {'1': pending(900, 3), '3': pending(2, 1)}, {
    fold_session: 'session_two', base_fold_revision: {'1': 10, '3': 30}});
  expect(accept(r, next)).toBe(r);
  r = open(r, 'session_two');
  expect(accept(r, packet(2))).toBe(r);
  expect(accept(r, {...next, preview: {...next.preview, origin_authority: {
    '1': pending(900, 2), '3': pending(2, 1)}}})).toBe(r);
  const adopted = accept(r, next);
  expect(adopted.held).not.toBeNull();
  expect(Object.keys(adopted.multiOrigin!.authorities)).toEqual(['1', '3']);
});
test('singleton to folded upgrade preserves the accepted origin identity across reset', () => {
  let r = readerAfterPreviewMembership(EMPTY_BLEND_PREVIEW_READER, {'1': 10}, 1);
  r = accept(r, {event_id: 1, p: .7, preview: {kind: 'blend', epoch: 900, seq: 2, base_rev: 10, ttl_ms: 1000}});
  r = readerAfterPreviewMembership(readerAfterPreviewReset(r), vector, 1);
  r = open(r);
  expect(accept(r, packet(1))).toBe(r);
  expect(accept(r, packet(1, {'1': pending(900, 3), '2': pending(12, 80)})).held).not.toBeNull();
});
test('folded to singleton drops removed origin scalar clocks but retains a known survivor', () => {
  const legacy = {event_id: 1, p: .7, p_away: .3, sport: 'tennis', status: 'live',
    preview: {kind: 'blend', folded_version: 1, origin_event_id: 2, base_fold_revision: vector,
      epoch: 900, seq: 80, base_rev: 20, ttl_ms: 1000}};
  let r = accept(readerAfterPreviewMembership(EMPTY_BLEND_PREVIEW_READER, vector, 1), legacy);
  r = readerAfterPreviewMembership(readerAfterPreviewReset(r), {'1': 10}, 1);
  expect(r.epoch).toBe(-1);
  expect(r.foldedSequence).toBeUndefined();
  const singleton = {event_id: 1, p: .6, preview: {kind: 'blend', epoch: 12, seq: 2, base_rev: 10, ttl_ms: 1000}};
  expect(accept(r, singleton).held!.p).toBe(.6);
  let known = accept(open(), packet(1));
  known = readerAfterPreviewMembership(readerAfterPreviewReset(known), {'1': 10}, 1);
  expect(known.epoch).toBe(900);
  expect(accept(known, singleton)).toBe(known);
});
test('base warming after withdrawal preserves pending sibling original deadline', () => {
  const r = accept(open(), packet(1));
  const withdrawal = packet(2, {'1': retired(900, 2, 'committed'), '2': pending(12, 80)}, {kind: 'revoke', ttl_ms: 0});
  const raw: Record<string, unknown> = {...withdrawal, p: null};
  delete raw.p_away; delete raw.sport;
  const held = accept(r, raw, 200);
  expect(held.held).toBeNull();
  expect(held.multiOrigin!.authorities['2'].state).toBe('pending');
  const warmed = accept(held, packet(3, {'1': retired(900, 2, 'committed'), '2': pending(12, 80)}), 800);
  expect(warmed.held!.expiresAt).toBe(1000);
});
test('independent origin clocks reach all three surfaces without scalar wire clocks', () => {
  const raw = packet(1); expect(raw.preview).not.toHaveProperty('epoch');
  const r = accept(open(), raw);
  expect(displayedPreview(r.held, event, 100)).toBe(.7);
  expect(displayedProbabilityObservedAt(event, r.held, 100, 'stored')).toBe(raw.display_observed_at);
  expect(overlayBlendPreviewLine(event, r.held, 100, [])).toEqual([{timestamp: raw.display_observed_at, home_probability: .7}]);
  const next = accept(r, packet(2, {'1': pending(900, 2), '2': pending(12, 81)}), 100);
  expect(next.multiOrigin!.authorities['1'].seq).toBe(2);
  expect(next.multiOrigin!.authorities['2'].seq).toBe(81);
});
test('only the current open can establish a session', () => {
  expect(accept(EMPTY_BLEND_PREVIEW_READER, packet(1))).toBe(EMPTY_BLEND_PREVIEW_READER);
  const r = open(); expect(accept(r, packet(1, undefined, {fold_session: 'other'}))).toBe(r);
  expect(readerAfterPreviewOpen(r, {event_id: 2, fold_session: 'other'}, 1)).toBe(r);
});
test('component regression or missing sibling is refused atomically', () => {
  const r = accept(open(), packet(1));
  expect(accept(r, packet(2, {'1': pending(900, 1), '2': pending(12, 81)}))).toBe(r);
  expect(accept(r, packet(2, {'2': pending(12, 81)}))).toBe(r);
  expect(r.multiOrigin!.authorities['2'].seq).toBe(80);
});
test('duplicate snapshots and sibling activity never renew an unchanged constituent', () => {
  const r = accept(open(), packet(4));
  expect(accept(r, packet(4), 800)).toBe(r); expect(accept(r, packet(3), 800)).toBe(r);
  const next = accept(r, packet(5, {'1': pending(900, 2), '2': pending(12, 81)}), 800);
  expect(next.held!.expiresAt).toBe(1000); expect(displayedPreview(next.held, event, 1000)).toBeNull();
  expect(accept(next, packet(6, {'1': pending(900, 2), '2': pending(12, 82)}), 1001)).toBe(next);
});
test.each(['revoked', 'expired', 'committed'])('%s A preserves B and fences same-tuple resurrection', state => {
  const r = accept(open(), packet(1));
  const next = accept(r, packet(2, {'1': retired(900, 2, state), '2': pending(12, 80)}), 100);
  expect(next.held!.expiresAt).toBe(1000); expect(accept(next, packet(3), 200)).toBe(next);
  const fresh = accept(next, packet(3, {'1': pending(901, 1), '2': pending(12, 80)}), 200);
  expect(fresh.multiOrigin!.authorities['1'].epoch).toBe(901);
});
test('all-retired withdrawal invents no committed probability', () => {
  const r = accept(open(), packet(1));
  const raw = {...packet(2, {'1': retired(900, 2), '2': retired(12, 80)}, {kind: 'revoke', ttl_ms: 0}), p: null};
  const next = accept(r, raw, 100); expect(next.held).toBeNull(); expect(accept(next, packet(3), 200)).toBe(next);
});
test('committed floors beat newer transport snapshots with uncovered bases', () => {
  const r = readerAfterCommitFloor(accept(open(), packet(1)), {'2': 21}); expect(r.held).toBeNull();
  expect(accept(r, packet(2, {'1': pending(900, 3), '2': pending(12, 81)})).held).toBeNull();
});
test('reset keeps fences and deadlines; new session may omit previously withdrawn origins', () => {
  const r = accept(open(), packet(1)); const reset = readerAfterPreviewReset(r);
  expect(reset.held).toBeNull(); expect(accept(reset, packet(2))).toBe(reset);
  const reopened = open(reset, 'session_two');
  const next = accept(reopened, packet(1, {'2': pending(12, 81)}, {fold_session: 'session_two'}), 900);
  expect(next.held).not.toBeNull();
  expect(accept(next, packet(2, {'1': pending(899, 100), '2': pending(12, 82)}, {fold_session: 'session_two'}), 901)).toBe(next);
  expect(accept(next, packet(2, {'1': pending(900, 2), '2': pending(12, 82)}, {fold_session: 'session_two'}), 1001)).toBe(next);
});
test('legacy packets cannot downgrade established v2 authority', () => {
  const r = accept(open(), packet(1));
  const legacy = {event_id: 1, p: .2, preview: {kind: 'blend', epoch: 9999, seq: 99, base_rev: 10, ttl_ms: 1000}};
  expect(accept(r, legacy)).toBe(r); expect(accept(readerAfterPreviewReset(r), legacy).held).toBeNull();
});
test.each([
  {fold_seq: -1}, {fold_session: ''}, {folded_version: 3}, {base_fold_revision: {'1': 10}},
  {base_fold_revision: {'1': 10, wrong: 20}}, {origin_authority: {'1': pending(900, 2, 999)}},
  {origin_authority: {'1': {...retired(900, 2), ttl_ms: 1}}},
  {origin_authority: {'1': pending(900, 2), '2': pending(12, 80), '3': pending(2, 3)}},
])('malformed packet is refused without singleton fallback: %j', extra => {
  expect(parseBlendPreview(packet(1, undefined, extra))).toBeNull();
});


test('same-connection resync permits fresh origin sequences without resurrecting old ones', () => {
  const before = accept(open(), packet(1));
  const reset = readerAfterPreviewReset(before);
  const fresh = accept(reset, packet(2, {'1': pending(900, 3), '2': pending(12, 81)}), 100);
  expect(fresh.held).not.toBeNull();
  expect(fresh.multiOrigin!.session).toBe('session_one');
});
