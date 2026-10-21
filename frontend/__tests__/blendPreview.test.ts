/**
 * #10090 — the reader half of display-before-persist. A provisional blend
 * overlays the hero only while no newer committed revision exists, is fenced
 * by a monotonic epoch floor, orders by seq within an epoch, is withdrawn by
 * revoke, expires, is cleared on reconnect, and never reaches `onFrame` (the
 * committed path).
 */

import {
  displayedPreview,
  displayedProbabilityObservedAt,
  overlayBlendPreview,
  parseBlendPreview,
  previewAfter,
  readerAfter,
  EMPTY_BLEND_PREVIEW_READER,
  type BlendPreviewFrame,
  type BlendPreviewReader,
  type BlendPreviewState,
} from '@/lib/blendPreview';
import { createLiveStreamController, type StreamHandle } from '@/lib/liveStreamController';

const EVENT = 1;

function blend(seq: number, p: number, opts: Partial<{ epoch: number; base: number; ttl: number; status: string }> = {}): BlendPreviewFrame {
  return {
    event_id: EVENT, p, status: opts.status ?? 'live', provisional: true,
    preview: { kind: 'blend', epoch: opts.epoch ?? 1, seq, base_rev: opts.base ?? 10, ttl_ms: opts.ttl ?? 60_000, pending: { kalshi: p } },
  };
}

function revoke(seq: number, through: number, epoch = 1): BlendPreviewFrame {
  return { event_id: EVENT, p: null, status: 'live', provisional: true, preview: { kind: 'revoke', epoch, seq, through_seq: through, reason: 'stale' } };
}

function held(rev: number | null, extra: Record<string, unknown> = {}) {
  return {
    id: EVENT, status: 'live', hero_probability_source: 'blend', hero_probability: 0.6,
    hero_probability_away: 0.4, blend_fold_revision: rev === null ? undefined : { [String(EVENT)]: rev },
    ...extra,
  };
}

const apply = (state: BlendPreviewState | null, frame: BlendPreviewFrame, now = 0) => previewAfter(state, frame, EVENT, now);

describe('parseBlendPreview refuses what is not a provisional frame', () => {
  test('a frame carrying a committed rev is refused', () => {
    expect(parseBlendPreview(JSON.stringify({ ...blend(1, 0.7), rev: { '1': 11 } }))).toBeNull();
  });
  test('missing base_rev, bad p, bad seq or a non-integer epoch are refused; a well-formed blend and revoke parse', () => {
    expect(parseBlendPreview({ ...blend(1, 0.7), preview: { ...blend(1, 0.7).preview, epoch: 'e1' } })).toBeNull();
    expect(parseBlendPreview({ ...blend(1, 0.7), preview: { ...blend(1, 0.7).preview, epoch: 1.5 } })).toBeNull();
    const noBase = blend(1, 0.7); delete noBase.preview.base_rev;
    expect(parseBlendPreview(noBase)).toBeNull();
    expect(parseBlendPreview({ ...blend(1, 0.7), p: 1.2 })).toBeNull();
    expect(parseBlendPreview(blend(-1, 0.7))).toBeNull();
    expect(parseBlendPreview(JSON.stringify(blend(1, 0.7)))).not.toBeNull();
    expect(parseBlendPreview(revoke(2, 1))).not.toBeNull();
  });
});

describe('ordering and correction', () => {
  test('a preview shows over the committed value while its base is current', () => {
    const state = apply(null, blend(1, 0.7));
    expect(displayedPreview(state, held(10), 0)).toBe(0.7);
    expect(overlayBlendPreview(held(10), state, 0)?.hero_probability).toBe(0.7);
    expect(overlayBlendPreview(held(10), state, 0)?.hero_probability_away).toBeCloseTo(0.3);
  });

  test('a newer committed revision wins, whoever wrote it; an older or equal one does not', () => {
    const state = apply(null, blend(1, 0.7, { base: 10 }));
    expect(displayedPreview(state, held(11), 0)).toBeNull();
    expect(displayedPreview(state, held(9), 0)).toBe(0.7);
    expect(displayedPreview(state, held(10), 0)).toBe(0.7);
  });

  test('a delayed lower seq never replaces a higher one in the same epoch', () => {
    let state = apply(null, blend(5, 0.72));
    state = apply(state, blend(4, 0.65));
    expect(displayedPreview(state, held(10), 0)).toBe(0.72);
  });

  test('a recomposed preview on the new base survives the commit that retired the old one', () => {
    // Kalshi preview on rev 10, PM commits rev 11, server recomposes Kalshi pending on 11.
    let state = apply(null, blend(1, 0.7, { base: 10 }));
    expect(displayedPreview(state, held(11), 0)).toBeNull();
    state = apply(state, blend(2, 0.71, { base: 11 }));
    expect(displayedPreview(state, held(11), 0)).toBe(0.71);
  });

  test('revoke withdraws previews up to through_seq only', () => {
    let state = apply(null, blend(3, 0.7));
    expect(apply(state, revoke(4, 2))).toBe(state);
    state = apply(state, revoke(4, 3));
    expect(state).toBeNull();
    expect(overlayBlendPreview(held(10), state, 0)?.hero_probability).toBe(0.6);
  });

});

describe('epoch fence: an earlier worker never regains the display', () => {
  const read = (reader: BlendPreviewReader, frame: BlendPreviewFrame, now = 0) => readerAfter(reader, frame, EVENT, now);

  test('a replacement (higher epoch) voids the old preview, whatever its seq', () => {
    let reader = read(EMPTY_BLEND_PREVIEW_READER, blend(90, 0.7, { epoch: 4 }));
    reader = read(reader, blend(1, 0.66, { epoch: 5 }));
    expect(reader.epoch).toBe(5);
    expect(displayedPreview(reader.held, held(10), 0)).toBe(0.66);
    const old = read(EMPTY_BLEND_PREVIEW_READER, blend(90, 0.7, { epoch: 4 }));
    expect(read(old, revoke(1, 0, 5))).toEqual({ held: null, epoch: 5 });
  });

  test('an old-epoch blend arriving after the replacement spoke is refused (no latest-arrival selection)', () => {
    let reader = read(EMPTY_BLEND_PREVIEW_READER, blend(1, 0.66, { epoch: 5 }));
    const after = read(reader, blend(91, 0.7, { epoch: 4 }));
    expect(after).toBe(reader);
    expect(displayedPreview(after.held, held(10), 0)).toBe(0.66);
    // Even with nothing held (the replacement revoked its own), the floor stays.
    reader = read(reader, revoke(2, 1, 5));
    expect(reader).toEqual({ held: null, epoch: 5 });
    expect(read(reader, blend(92, 0.71, { epoch: 4 }))).toBe(reader);
  });

  test("an old epoch's revoke cannot take down the replacement's preview", () => {
    const reader = read(EMPTY_BLEND_PREVIEW_READER, blend(1, 0.66, { epoch: 5 }));
    expect(read(reader, revoke(99, 98, 4))).toBe(reader);
  });

  test('another event\'s frame changes nothing', () => {
    const reader = read(EMPTY_BLEND_PREVIEW_READER, blend(1, 0.66, { epoch: 5 }));
    expect(readerAfter(reader, { ...blend(2, 0.1, { epoch: 9 }), event_id: 2 }, EVENT, 0)).toBe(reader);
  });
});

describe('committed truth', () => {

  test('expiry, a status change, a folded or unversioned hero, or a non-blend hero all show committed truth', () => {
    const state = apply(null, blend(1, 0.7, { ttl: 1000 }), 5000);
    expect(displayedPreview(state, held(10), 5999)).toBe(0.7);
    expect(displayedPreview(state, held(10), 6000)).toBeNull();
    expect(displayedPreview(state, held(10, { status: 'final' }), 5000)).toBeNull();
    expect(displayedPreview(state, held(10, { blend_fold_revision: { '1': 10, '2': 4 } }), 5000)).toBeNull();
    expect(displayedPreview(state, held(null), 5000)).toBeNull();
    expect(displayedPreview(state, held(10, { hero_probability_source: 'opening' }), 5000)).toBeNull();
    const terminal = apply(null, blend(1, 0.7, { status: 'final' }));
    expect(displayedPreview(terminal, held(10, { status: 'final' }), 0)).toBeNull();
  });

  test('without a preview the event object is returned untouched', () => {
    const event = held(10);
    expect(overlayBlendPreview(event, null, 0)).toBe(event);
  });
});

class FakeSource implements StreamHandle {
  readyState = 1;
  private listeners = new Map<string, ((event: unknown) => void)[]>();
  addEventListener(type: string, listener: (event: unknown) => void) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
  }
  close() { this.readyState = 2; }
  emit(type: string, data?: unknown) {
    for (const listener of this.listeners.get(type) ?? []) listener(data === undefined ? {} : { data });
  }
}

describe('stream controller seam', () => {
  test('accepted hub resync withdraws provisional authority before committed recovery', () => {
    const source = new FakeSource();
    let reader = EMPTY_BLEND_PREVIEW_READER;
    const atRecovery: (number | null)[] = [];
    const controller = createLiveStreamController({
      open: () => source,
      now: () => 0,
      onFrame: () => undefined,
      onDeliveringChange: () => undefined,
      onPreview: raw => {
        const parsed = parseBlendPreview(raw);
        if (parsed) reader = readerAfter(reader, parsed, EVENT, 0);
      },
      onPreviewReset: () => { reader = { ...reader, held: null }; },
      onRecovery: () => { atRecovery.push(displayedPreview(reader.held, held(10), 0)); },
    });
    controller.start();
    source.emit('open');
    source.emit('preview', JSON.stringify(blend(1, .7)));
    expect(displayedPreview(reader.held, held(10), 0)).toBe(.7);
    source.emit('resync', JSON.stringify({ generation: 1 }));
    expect(atRecovery).toEqual([null]);
    // Even before the same-revision recovery read returns, the old preview
    // no longer owns headline, clock or disposable chart state.
    expect(reader.held).toBeNull();
    source.emit('resync', JSON.stringify({ generation: 1 }));
    expect(atRecovery).toHaveLength(1);
    controller.stop();
  });
  test('a preview event reaches onPreview, never onFrame, and touches no delivery state; open and closed reset it', () => {
    const sources: FakeSource[] = [];
    const frames: unknown[] = [];
    const previews: unknown[] = [];
    const delivering: boolean[] = [];
    let resets = 0;
    const controller = createLiveStreamController({
      open: () => { const s = new FakeSource(); sources.push(s); return s; },
      now: () => 0,
      onFrame: (f) => frames.push(f),
      onDeliveringChange: (d) => delivering.push(d),
      onPreview: (raw) => previews.push(raw),
      onPreviewReset: () => { resets += 1; },
    });
    controller.start();
    sources[0].emit('open');
    expect(resets).toBe(1);
    const before = delivering.length;
    sources[0].emit('preview', JSON.stringify(blend(1, 0.7)));
    expect(previews).toHaveLength(1);
    expect(frames).toHaveLength(0);
    expect(delivering.length).toBe(before);
    sources[0].emit('closed');
    expect(resets).toBe(2);
  });
});


describe('the displayed probability owns its observation clock', () => {
  const committed = '2026-10-20T20:00:10Z';
  const observed = '2026-10-20T20:00:05Z';
  test.each([0, 1])('boundary probability %s uses its own observation, even if older than committed', p => {
    const state = apply(null, {...blend(1, p), display_observed_at: observed});
    expect(displayedProbabilityObservedAt(held(10), state, 0, committed)).toBe(observed);
    expect(displayedProbabilityObservedAt(held(11), state, 0, committed)).toBe(committed);
  });
  test('a retry attempt and receipt time cannot move the displayed observation', () => {
    const first = apply(null, {...blend(1, .7), display_observed_at: observed, observed_at: committed});
    const retry = apply(first, {...blend(2, .7), display_observed_at: observed, observed_at: '2026-10-20T20:00:30Z'}, 500);
    expect(displayedProbabilityObservedAt(held(10), retry, 500, committed)).toBe(observed);
    expect(displayedProbabilityObservedAt(held(10), null, 500, undefined)).toBeUndefined();
  });
});
