/** Mounted hook/controller recovery; minimal DOM is not browser paint. */
import '../helpers/minimalDom';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { useLiveEventStream } from '@/hooks/useLiveEventStream';
import { displayedPreview, displayedProbabilityObservedAt, overlayBlendPreviewLine } from '@/lib/blendPreview';

class Source {
  static current: Source;
  readyState = 1;
  listeners = new Map<string, (event: unknown) => void>();
  constructor(readonly url: string) { Source.current = this; }
  close() { this.readyState = 2; }
  addEventListener(name: string, fn: (event: unknown) => void) { this.listeners.set(name, fn); }
  emit(name: string, payload: unknown) { this.listeners.get(name)?.({ data: JSON.stringify(payload) }); }
}
const vector = { '1': 11, '2': 22 };
const committed = { id: 1, status: 'live', sport: 'soccer_epl', hero_probability_source: 'blend',
  hero_probability: .4, blend_fold_revision: vector };
const observed = '2026-10-21T00:00:05Z';
const preview = { event_id: 1, p: .48, p_away: null, status: 'live', sport: 'soccer_epl',
  display_observed_at: observed,
  preview: { kind: 'blend', epoch: 8, seq: 12, base_rev: 22, ttl_ms: 5000,
    folded_version: 1, origin_event_id: 2, base_fold_revision: vector } };
function Page({ membership }: { membership?: Record<string, number> }) {
  const { blendPreview, blendPreviewNow } = useLiveEventStream(1, true, undefined, undefined, membership);
  const current = membership ? {...committed, blend_fold_revision: membership} : committed;
  return <output>{JSON.stringify({
    headline: displayedPreview(blendPreview, current, blendPreviewNow),
    observed: displayedProbabilityObservedAt(current, blendPreview, blendPreviewNow, 'stored'),
    chart: overlayBlendPreviewLine(current, blendPreview, blendPreviewNow, []),
  })}</output>;
}
test('resync clears all three provisional surfaces through the actual hook before recovery reads', async () => {
  const original = globalThis.EventSource;
  globalThis.EventSource = Source as unknown as typeof EventSource;
  jest.useFakeTimers();
  const host = document.createElement('div');
  const root = createRoot(host);
  try {
    await act(async () => { root.render(<Page />); });
    expect(Source.current.url).toMatch(/\/api\/events\/1\/stream\?preview_protocol=folded-v1$/);
    await act(async () => { Source.current.emit('open', {}); Source.current.emit('preview', preview); });
    expect(JSON.parse(host.textContent!)).toEqual({ headline: .48, observed,
      chart: [{ timestamp: observed, home_probability: .48 }] });
    await act(async () => { Source.current.emit('resync', { generation: 1 }); });
    expect(JSON.parse(host.textContent!)).toEqual({ headline: null, observed: 'stored', chart: [] });
    // Same committed floor and reordered old preview cannot revive it.
    await act(async () => {
      Source.current.emit('fold_preview_floor', { event_id: 1, floor: vector });
      Source.current.emit('preview', preview);
    });
    expect(JSON.parse(host.textContent!)).toEqual({ headline: null, observed: 'stored', chart: [] });
  } finally {
    await act(async () => { root.unmount(); });
    globalThis.EventSource = original;
    jest.useRealTimers();
  }
});

test('v2 session negotiation reaches all surfaces and recovery keeps origin fences', async () => {
  const original = globalThis.EventSource;
  globalThis.EventSource = Source as unknown as typeof EventSource;
  jest.useFakeTimers();
  const host = document.createElement('div'); const root = createRoot(host);
  const v2 = { ...preview, preview: { kind: 'blend', folded_version: 2,
    fold_session: 'mounted_session', fold_seq: 1, base_fold_revision: vector, ttl_ms: 1000,
    origin_authority: {'1': {epoch: 900, seq: 1, state: 'pending', ttl_ms: 1000},
      '2': {epoch: 12, seq: 80, state: 'pending', ttl_ms: 1000}} } };
  try {
    await act(async () => { root.render(<Page />); });
    await act(async () => { Source.current.emit('open', {event_id: 1, fold_session: 'mounted_session'}); Source.current.emit('preview', v2); });
    expect(JSON.parse(host.textContent!)).toEqual({headline: .48, observed,
      chart: [{timestamp: observed, home_probability: .48}]});
    await act(async () => { Source.current.emit('resync', {generation: 1}); });
    expect(JSON.parse(host.textContent!)).toEqual({headline: null, observed: 'stored', chart: []});
    await act(async () => { Source.current.emit('preview', {...v2, preview: {...v2.preview, fold_seq: 2}}); });
    expect(JSON.parse(host.textContent!)).toEqual({headline: null, observed: 'stored', chart: []});
    const fresh = {...v2, preview: {...v2.preview, fold_seq: 3, origin_authority: {
      '1': {epoch: 900, seq: 2, state: 'pending', ttl_ms: 1000},
      '2': {epoch: 12, seq: 81, state: 'pending', ttl_ms: 1000}}}};
    await act(async () => { Source.current.emit('preview', fresh); });
    expect(JSON.parse(host.textContent!).headline).toBe(.48);
    await act(async () => { jest.advanceTimersByTime(1001); });
    expect(JSON.parse(host.textContent!)).toEqual({headline: null, observed: 'stored', chart: []});
  } finally {
    await act(async () => { root.unmount(); });
    globalThis.EventSource = original; jest.useRealTimers();
  }
});

test('membership change reopens held page and accepts replacement source', async () => {
  const original = globalThis.EventSource;
  globalThis.EventSource = Source as unknown as typeof EventSource;
  jest.useFakeTimers();
  const host = document.createElement('div'); const root = createRoot(host);
  const frame = (session: string, members: Record<string, number>, seq: number) => ({...preview,
    preview: {kind: 'blend', folded_version: 2, fold_session: session, fold_seq: seq,
      base_fold_revision: members, ttl_ms: 1000,
      origin_authority: Object.fromEntries(Object.keys(members).map(key => [key,
        {epoch: Number(key), seq, state: 'pending', ttl_ms: 1000}]))}});
  try {
    await act(async () => { root.render(<Page membership={vector} />); });
    const old = Source.current;
    await act(async () => {old.emit('open', {event_id: 1, fold_session: 'first'}); old.emit('preview', frame('first', vector, 1));});
    expect(JSON.parse(host.textContent!).headline).toBe(.48);
    const replacement = {'1': 11, '3': 33};
    await act(async () => { root.render(<Page membership={replacement} />); });
    expect(old.readyState).toBe(2);
    expect(Source.current).not.toBe(old);
    expect(JSON.parse(host.textContent!).headline).toBeNull();
    await act(async () => {
      Source.current.emit('open', {event_id: 1, fold_session: 'second'});
      Source.current.emit('preview', frame('first', vector, 2));
      Source.current.emit('preview', frame('second', replacement, 1));
    });
    expect(JSON.parse(host.textContent!).headline).toBeNull();
    await act(async () => {Source.current.emit('preview', frame('second', replacement, 2));});
    expect(JSON.parse(host.textContent!).headline).toBe(.48);
  } finally {
    await act(async () => {root.unmount();});
    globalThis.EventSource = original; jest.useRealTimers();
  }
});
