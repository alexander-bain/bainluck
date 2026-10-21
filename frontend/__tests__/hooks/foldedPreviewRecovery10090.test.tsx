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
  constructor() { Source.current = this; }
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
function Page() {
  const { blendPreview, blendPreviewNow } = useLiveEventStream(1, true);
  return <output>{JSON.stringify({
    headline: displayedPreview(blendPreview, committed, blendPreviewNow),
    observed: displayedProbabilityObservedAt(committed, blendPreview, blendPreviewNow, 'stored'),
    chart: overlayBlendPreviewLine(committed, blendPreview, blendPreviewNow, []),
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
