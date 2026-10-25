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
const first = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const second = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const authority = {incarnation: '1', namespace: '11111111-1111-4111-8111-111111111111'};
const wrap = (frame: unknown, stream_session = first) => ({protocol: 3, event_id: 1, authority, stream_session, frame});
const opening = (members = [1,2], stream_session = first) => ({protocol: 3, event_id: 1, authority, stream_session, members});
const vector = { '1': 11, '2': 22 };
const committed = { id: 1, status: 'live', sport: 'soccer_epl', hero_probability_source: 'blend',
  hero_probability: .4, blend_fold_revision: vector };
const observed = '2026-10-21T00:00:05Z';
const preview = { event_id: 1, p: .48, p_away: null, status: 'live', sport: 'soccer_epl',
  display_observed_at: observed,
  preview: { kind: 'blend', folded_version: 2, fold_session: first, fold_seq: 1, ttl_ms: 5000,
    origin_authority: {'1': {epoch: 900, seq: 1, state: 'pending', ttl_ms: 5000},
      '2': {epoch: 12, seq: 80, state: 'pending', ttl_ms: 5000}}, base_fold_revision: vector } };
function Page({ membership }: { membership?: Record<string, number> }) {
  const { blendPreview, blendPreviewNow } = useLiveEventStream(1, true, undefined, undefined, membership ?? vector);
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
    expect(Source.current.url).toMatch(/\/api\/events\/1\/stream\?preview_protocol=authority-v3$/);
    await act(async () => { Source.current.emit('open', {}); Source.current.emit('preview_open_v3', opening()); Source.current.emit('preview_v3', wrap(preview)); });
    expect(JSON.parse(host.textContent!)).toEqual({ headline: .48, observed,
      chart: [{ timestamp: observed, home_probability: .48 }] });
    await act(async () => { Source.current.emit('resync', { generation: 1 }); });
    expect(JSON.parse(host.textContent!)).toEqual({ headline: null, observed: 'stored', chart: [] });
    // Same committed floor and reordered old preview cannot revive it.
    await act(async () => {
      Source.current.emit('fold_preview_floor', { event_id: 1, floor: vector });
      Source.current.emit('preview_v3', wrap(preview));
    });
    expect(JSON.parse(host.textContent!)).toEqual({ headline: null, observed: 'stored', chart: [] });
  } finally {
    await act(async () => { root.unmount(); });
    globalThis.EventSource = original;
    jest.useRealTimers();
  }
});

test('v3 session negotiation reaches all surfaces and recovery keeps origin fences', async () => {
  const original = globalThis.EventSource;
  globalThis.EventSource = Source as unknown as typeof EventSource;
  jest.useFakeTimers();
  const host = document.createElement('div'); const root = createRoot(host);
  const v2 = { ...preview, preview: { kind: 'blend', folded_version: 2,
    fold_session: first, fold_seq: 1, base_fold_revision: vector, ttl_ms: 1000,
    origin_authority: {'1': {epoch: 900, seq: 1, state: 'pending', ttl_ms: 1000},
      '2': {epoch: 12, seq: 80, state: 'pending', ttl_ms: 1000}} } };
  try {
    await act(async () => { root.render(<Page />); });
    await act(async () => { Source.current.emit('open', {}); Source.current.emit('preview_open_v3', opening()); Source.current.emit('preview_v3', wrap(v2)); });
    expect(JSON.parse(host.textContent!)).toEqual({headline: .48, observed,
      chart: [{timestamp: observed, home_probability: .48}]});
    await act(async () => { Source.current.emit('resync', {generation: 1}); });
    expect(JSON.parse(host.textContent!)).toEqual({headline: null, observed: 'stored', chart: []});
    await act(async () => { Source.current.emit('preview_v3', wrap({...v2, preview: {...v2.preview, fold_seq: 2}})); });
    expect(JSON.parse(host.textContent!)).toEqual({headline: null, observed: 'stored', chart: []});
    const fresh = {...v2, preview: {...v2.preview, fold_seq: 3, origin_authority: {
      '1': {epoch: 900, seq: 2, state: 'pending', ttl_ms: 1000},
      '2': {epoch: 12, seq: 81, state: 'pending', ttl_ms: 1000}}}};
    await act(async () => { Source.current.emit('preview_v3', wrap(fresh)); });
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
    await act(async () => {old.emit('open', {}); old.emit('preview_open_v3', opening()); old.emit('preview_v3', wrap(frame(first, vector, 1)));});
    expect(JSON.parse(host.textContent!).headline).toBe(.48);
    const replacement = {'1': 11, '3': 33};
    await act(async () => { root.render(<Page membership={replacement} />); });
    expect(old.readyState).toBe(2);
    expect(Source.current).not.toBe(old);
    expect(JSON.parse(host.textContent!).headline).toBeNull();
    await act(async () => {
      Source.current.emit('open', {});
      Source.current.emit('preview_open_v3', opening([1,3], second));
      Source.current.emit('preview_v3', wrap(frame(first, vector, 2)));
      old.emit('preview_open_v3', {...opening(), authority:{...authority,incarnation:'999'}});
      old.emit('preview_v3', wrap(frame(first, vector, 999)));
      Source.current.emit('preview_v3', wrap(frame(second, replacement, 1), second));
    });
    expect(JSON.parse(host.textContent!).headline).toBeNull();
    await act(async () => {Source.current.emit('preview_v3', wrap(frame(second, replacement, 2), second));});
    expect(JSON.parse(host.textContent!).headline).toBe(.48);
  } finally {
    await act(async () => {root.unmount();});
    globalThis.EventSource = original; jest.useRealTimers();
  }
});

test('new authority restores low-epoch updates on headline and chart, retains committed floors, and rejects legacy delivery', async () => {
  const original=globalThis.EventSource;
  globalThis.EventSource=Source as unknown as typeof EventSource;
  jest.useFakeTimers();
  const host=document.createElement('div'), root=createRoot(host);
  const nextAuthority={...authority,incarnation:'2',namespace:'22222222-2222-4222-8222-222222222222'};
  const fresh={...preview,preview:{...preview.preview,fold_seq:1,
    origin_authority:{'1':{epoch:1,seq:1,state:'pending',ttl_ms:5000},'2':{epoch:1,seq:1,state:'pending',ttl_ms:5000}}}};
  try {
    await act(async()=>{root.render(<Page />);});
    await act(async()=>{Source.current.emit('open',{});Source.current.emit('preview_open_v3',opening());Source.current.emit('preview_v3',wrap(preview));});
    expect(JSON.parse(host.textContent!).headline).toBe(.48);
    await act(async()=>{Source.current.emit('open',{});});
    expect(JSON.parse(host.textContent!)).toEqual({headline:null,observed:'stored',chart:[]});
    await act(async()=>{Source.current.emit('preview_v3',wrap(fresh));Source.current.emit('preview',preview);});
    expect(JSON.parse(host.textContent!).headline).toBeNull();
    await act(async()=>{Source.current.emit('preview_open_v3',{...opening(),authority:nextAuthority});Source.current.emit('preview_v3',{...wrap(fresh),authority:nextAuthority});});
    expect(JSON.parse(host.textContent!)).toEqual({headline:.48,observed,chart:[{timestamp:observed,home_probability:.48}]});
    await act(async()=>{Source.current.emit('preview_v3',wrap({...preview,p:.99}));Source.current.emit('preview',{...preview,p:.99});});
    expect(JSON.parse(host.textContent!).headline).toBe(.48);
    await act(async()=>{Source.current.emit('probability',{event_id:1,rev:{'1':12,'2':22},p:.45,status:'live'});});
    expect(JSON.parse(host.textContent!)).toEqual({headline:null,observed:'stored',chart:[]});
    await act(async()=>{Source.current.emit('preview_v3',{...wrap({...fresh,preview:{...fresh.preview,fold_seq:2}}),authority:nextAuthority});});
    expect(JSON.parse(host.textContent!).headline).toBeNull();
  } finally {
    await act(async()=>{root.unmount();});globalThis.EventSource=original;jest.useRealTimers();
  }
});
