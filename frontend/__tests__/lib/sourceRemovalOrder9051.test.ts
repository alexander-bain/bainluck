import { fetchEventWithLiveFrame, reconcileEventPoll } from '@/lib/reconcileEventPoll';
import { applyLiveFrame, frameInvalidatesFoldedBlend, type LiveFrame } from '@/lib/eventLivePush';
import { adoptNewerBlendEdge, servedBlendEdgeObservation } from '@/lib/blendObservationClock';
import { compareFoldRevision, frameFoldOrder, parseFoldRevision } from '@/lib/foldRevision';
import type { LiveStreamFrame } from '@/lib/liveStreamController';

// #9051. Fixed clocks, all 2026-09-27T05:00:ssZ. The page held a Kalshi frame
// (Kalshi .8 + Polymarket .4 = .6) observed :10; Kalshi was then retired; the
// fresh response serves Polymarket .4 alone, dated by Polymarket's last quote at
// :00 — OLDER than the held frame, so no price clock can order them. The served
// fold revision (`lib/foldRevision.ts`) orders them by commit.
const at = (s: number) => `2026-09-27T05:00:${String(s).padStart(2, '0')}Z`;
const ROW = '123';
const TWIN = '456';

const kalshiFrame: LiveStreamFrame = {
  event_id: 123, status: 'live', source: 'kalshi', source_value: 0.8, p: 0.6, updated_at: at(10),
};

// The page applies a frame only once `p` is a number (`page.tsx`'s push effect).
const pushed = (frame: LiveStreamFrame): LiveFrame => ({ ...frame, p: frame.p as number });

function served(overrides: Record<string, unknown> = {}) {
  const base = {
    id: 123, status: 'live', hero_probability_source: 'blend',
    hero_probability: 0.4, hero_probability_away: 0.6, hero_probability_observed_at: at(0),
    home_score: 14, away_score: 10,
    win_probability_sources: {
      polymarket: { value: 0.4, display_name: 'Polymarket', updated_at: at(0) },
    } as Record<string, { value: number; display_name?: string; updated_at: string }>,
    blend_fold_revision: undefined as Record<string, number> | null | undefined,
  };
  return { ...base, ...overrides } as typeof base;
}

/** A held headline as the page's cache would carry it: value, price clock, revision. */
const held = (p: number, observed: number, rev: Record<string, number> | undefined) =>
  served({ hero_probability: p, hero_probability_away: 1 - p, hero_probability_observed_at: at(observed), blend_fold_revision: rev });
const edge = (p: number, observed: number, rev?: Record<string, number>) =>
  (rev ? { p, observedAt: at(observed), foldRevision: rev } : { p, observedAt: at(observed) });
const headline = (e: ReturnType<typeof served> | undefined) =>
  ({ p: e?.hero_probability, at: e?.hero_probability_observed_at, rev: e?.blend_fold_revision });

describe('the reported failure: a pre-removal frame on the post-removal response', () => {
  // The removal was a write to the row: its revision moved 1 → 2. The frame is rev 1.
  const postRemoval = served({ blend_fold_revision: { [ROW]: 2 } });
  const preRemovalFrame = { ...kalshiFrame, fold_revision: { [ROW]: 1 } };

  test('the fetch path keeps the survivors blend and does not recreate the removed source', async () => {
    const result = await fetchEventWithLiveFrame(async () => postRemoval, () => preRemovalFrame, () => null);
    expect(result).toBe(postRemoval);
    expect(result.win_probability_sources.kalshi).toBeUndefined();
  });

  test('the push path returns the cache untouched — even with the hero clock explicitly unknown', () => {
    expect(applyLiveFrame(postRemoval, pushed(preRemovalFrame))).toBe(postRemoval);
    const unclocked = { ...postRemoval, hero_probability_observed_at: null };
    expect(applyLiveFrame(unclocked, pushed(preRemovalFrame))).toBe(unclocked);
  });

  test('a SURVIVOR frame from before the removal is refused too — its p still folded Kalshi', () => {
    const survivor = { ...preRemovalFrame, source: 'polymarket', source_value: 0.4 };
    expect(applyLiveFrame(postRemoval, pushed(survivor))).toBe(postRemoval);
  });

  test('the frame of the removal write itself (same revision) is not re-applied', () => {
    expect(applyLiveFrame(postRemoval, pushed({ ...preRemovalFrame, fold_revision: { [ROW]: 2 } }))).toBe(postRemoval);
  });
});

describe('frames that must still land', () => {
  test('#8779: a stale response from before a source first appeared takes its first frame', () => {
    const stale = served({ blend_fold_revision: { [ROW]: 1 } });
    const firstFrame = { ...kalshiFrame, fold_revision: { [ROW]: 2 } };
    const result = applyLiveFrame(stale, pushed(firstFrame))!;
    expect(result.hero_probability).toBe(0.6);
    expect(result.win_probability_sources.kalshi).toEqual({ value: 0.8, updated_at: at(10) });
    expect(result.win_probability_sources.polymarket.display_name).toBe('Polymarket');
    expect(result.blend_fold_revision).toEqual({ [ROW]: 2 });
  });

  test('a source re-admitted after its removal is delivered by its newer write', () => {
    const postRemoval = served({ blend_fold_revision: { [ROW]: 2 } });
    const readmitted = { ...kalshiFrame, p: 0.62, source_value: 0.84, updated_at: at(20), fold_revision: { [ROW]: 3 } };
    expect(applyLiveFrame(postRemoval, pushed(readmitted))?.hero_probability).toBe(0.62);
    expect(reconcileEventPoll(postRemoval, readmitted).win_probability_sources.kalshi)
      .toEqual({ value: 0.84, updated_at: at(20) });
  });

  test('a newer write lands even when its clock reads older than the held price clock', () => {
    // Commit order is the claim; the frame's own clock is kept as its provenance.
    const cache = held(0.4, 30, { [ROW]: 2 });
    const result = applyLiveFrame(cache, pushed({ ...kalshiFrame, fold_revision: { [ROW]: 3 } }))!;
    expect(result.hero_probability).toBe(0.6);
    expect(result.hero_probability_observed_at).toBe(at(10));
  });
});

describe('a FOLDED hero (canonical + twins) never takes a raw-row frame', () => {
  const folded = served({ blend_fold_revision: { [ROW]: 4, [TWIN]: 7 } });

  test.each([
    ['a newer write to the canonical row', { [ROW]: 5 }],
    ['a newer write to the twin', { [TWIN]: 8 }],
    ['a frame with no revision', undefined],
  ])('%s is refused, and asks for a folded refetch', (_label, rev) => {
    const frame = pushed({ ...kalshiFrame, fold_revision: rev });
    expect(applyLiveFrame(folded, frame)).toBe(folded);
    expect(frameInvalidatesFoldedBlend(folded, frame)).toBe(true);
  });

  test('CONTROL — a single-row hero does not ask for a refetch on a frame it can order', () => {
    const single = served({ blend_fold_revision: { [ROW]: 4 } });
    expect(frameInvalidatesFoldedBlend(single, pushed({ ...kalshiFrame, fold_revision: { [ROW]: 5 } }))).toBe(false);
    expect(frameInvalidatesFoldedBlend(single, pushed({ ...kalshiFrame, fold_revision: { [ROW]: 3 } }))).toBe(false);
    expect(frameInvalidatesFoldedBlend(served(), pushed(kalshiFrame))).toBe(false);
    expect(frameInvalidatesFoldedBlend({ ...folded, status: 'completed' }, pushed(kalshiFrame))).toBe(false);
  });

  test('a single-row hero refuses a frame for a row it did not read, and refetches', () => {
    const single = served({ blend_fold_revision: { [ROW]: 4 } });
    const other = pushed({ ...kalshiFrame, fold_revision: { [TWIN]: 9 } });
    expect(applyLiveFrame(single, other)).toBe(single);
    expect(frameInvalidatesFoldedBlend(single, other)).toBe(true);
  });
});

// Codex, REVISED-SOURCE-REVIEW-0a44349954.md: a membership SCALAR there is one
// row's revision here; "membership 15 / 25" read as revisions 15 / 25.
describe('Codex consumer cases on the history edge', () => {
  test('observed 10 / removed 15 / committed 20: the post-removal edge is ADOPTED (.5)', () => {
    const result = adoptNewerBlendEdge(held(0.4, 0, { [ROW]: 15 }), edge(0.5, 10, { [ROW]: 20 }));
    expect(headline(result)).toEqual({ p: 0.5, at: at(10), rev: { [ROW]: 20 } });
  });

  test('the old blend that folded the removed source is REFUSED, however new its price', () => {
    const cache = held(0.4, 0, { [ROW]: 15 });
    expect(adoptNewerBlendEdge(cache, edge(0.6, 30, { [ROW]: 5 }))).toBe(cache);
  });

  test('SEQUENTIAL: an adopted newer revision is RETAINED, so a delayed older edge cannot undo it', () => {
    let cache = adoptNewerBlendEdge(held(0.4, 0, { [ROW]: 15 }), edge(0.5, 10, { [ROW]: 25 }));
    expect(headline(cache)).toEqual({ p: 0.5, at: at(10), rev: { [ROW]: 25 } });
    cache = adoptNewerBlendEdge(cache, edge(0.6, 12, { [ROW]: 15 }));
    expect(headline(cache)).toEqual({ p: 0.5, at: at(10), rev: { [ROW]: 25 } });
  });

  test.each([
    ['an EQUAL price clock', 12],
    ['an OLDER price clock (a removal can leave only an older survivor quote)', 10],
  ])('a newer revision with %s is adopted with its own clock', (_label, observed) => {
    const result = adoptNewerBlendEdge(held(0.4, 12, { [ROW]: 15 }), edge(0.5, observed, { [ROW]: 25 }));
    expect(headline(result)).toEqual({ p: 0.5, at: at(observed), rev: { [ROW]: 25 } });
  });

  test('an UNCHANGED value from a newer revision still moves the held revision', () => {
    const result = adoptNewerBlendEdge(held(0.4, 0, { [ROW]: 15 }), edge(0.4, 10, { [ROW]: 25 }));
    expect(headline(result)).toEqual({ p: 0.4, at: at(10), rev: { [ROW]: 25 } });
  });

  test('the same revision falls to strict price ordering', () => {
    const cache = held(0.4, 10, { [ROW]: 15 });
    expect(adoptNewerBlendEdge(cache, edge(0.5, 10, { [ROW]: 15 }))).toBe(cache);
    expect(headline(adoptNewerBlendEdge(cache, edge(0.5, 11, { [ROW]: 15 })))).toEqual({ p: 0.5, at: at(11), rev: { [ROW]: 15 } });
  });

  test('an absent or malformed edge revision never ERASES the held one', () => {
    const cache = held(0.4, 0, { [ROW]: 15 });
    for (const e of [edge(0.5, 10), { p: 0.5, observedAt: at(10), foldRevision: { [ROW]: -1 } }]) {
      const result = adoptNewerBlendEdge(cache, e);
      expect(result?.hero_probability).toBe(0.5); // no claim: the price rule, unchanged
      expect(result?.blend_fold_revision).toEqual({ [ROW]: 15 });
    }
  });

  test('a held headline with no revision takes the price rule, then keeps the edge revision', () => {
    const legacy = held(0.4, 0, undefined);
    expect(headline(adoptNewerBlendEdge(legacy, edge(0.5, 10, { [ROW]: 25 })))).toEqual({ p: 0.5, at: at(10), rev: { [ROW]: 25 } });
    expect(adoptNewerBlendEdge(held(0.4, 20, undefined), edge(0.5, 10, { [ROW]: 25 }))?.hero_probability).toBe(0.4);
  });
});

// Codex, twin-contract/CONTRACT-REVIEW.md: canonical PM .4 + twin Kalshi .8 = .6.
// The twin removal stamps 20 but commits 40; a canonical removal stamps 30 and
// commits 31. History read at 35 still folds twin Kalshi; detail read after 40
// does not. Max-removal-time was 30 on both, and the old .6 came back.
describe('Codex twin fold: two rows committing out of stamp order', () => {
  const detailAfter40 = held(0.4, 0, { [ROW]: 2, [TWIN]: 2 });
  const historyAt35 = edge(0.6, 10, { [ROW]: 2, [TWIN]: 1 });

  test('the history edge read at 35 is OLDER than the detail read after 40, and is refused', () => {
    expect(adoptNewerBlendEdge(detailAfter40, historyAt35)).toBe(detailAfter40);
  });

  test('CONTROL — the fold read after 40 adopted over the one read at 35', () => {
    const at35 = held(0.6, 10, { [ROW]: 2, [TWIN]: 1 });
    expect(headline(adoptNewerBlendEdge(at35, edge(0.4, 0, { [ROW]: 2, [TWIN]: 2 }))))
      .toEqual({ p: 0.4, at: at(0), rev: { [ROW]: 2, [TWIN]: 2 } });
  });

  test('a twin joining or leaving the fold is incomparable: the held headline stays', () => {
    expect(adoptNewerBlendEdge(detailAfter40, edge(0.7, 50, { [ROW]: 3 }))).toBe(detailAfter40);
    expect(adoptNewerBlendEdge(detailAfter40, edge(0.7, 50, { [ROW]: 3, [TWIN]: 3, '789': 1 }))).toBe(detailAfter40);
  });

  test('mixed directions are incomparable', () => {
    expect(adoptNewerBlendEdge(detailAfter40, edge(0.7, 50, { [ROW]: 3, [TWIN]: 1 }))).toBe(detailAfter40);
  });
});

describe('no revision on either side: every pre-contract rule applies unchanged', () => {
  test('the exact PR #9028 behaviour, kept on purpose', async () => {
    const legacy = served();
    expect(reconcileEventPoll(legacy, kalshiFrame).hero_probability).toBe(0.6);
    expect(applyLiveFrame(legacy, pushed(kalshiFrame))?.hero_probability).toBe(0.6);
    expect(adoptNewerBlendEdge(legacy, edge(0.6, 10))?.hero_probability).toBe(0.6);
    expect(applyLiveFrame(legacy, pushed(kalshiFrame))?.blend_fold_revision).toBeUndefined();
  });

  test('#8789: an older frame still loses to a newer cached price', () => {
    const cache = held(0.4, 20, undefined);
    expect(applyLiveFrame(cache, pushed(kalshiFrame))).toBe(cache);
  });

  test('a single-row held revision with a revisionless frame keeps the clock rule and the revision', () => {
    const cache = served({ blend_fold_revision: { [ROW]: 2 } });
    const result = applyLiveFrame(cache, pushed(kalshiFrame))!;
    expect(result.hero_probability).toBe(0.6);
    expect(result.blend_fold_revision).toEqual({ [ROW]: 2 });
    expect(applyLiveFrame(held(0.4, 20, { [ROW]: 2 }), pushed(kalshiFrame))?.hero_probability).toBe(0.4);
  });

  test('settled and non-live caches are outside the rule', () => {
    const final = served({ status: 'completed', blend_fold_revision: { [ROW]: 9 } });
    expect(reconcileEventPoll(final, { ...kalshiFrame, fold_revision: { [ROW]: 1 } })).toBe(final);
    // The push path keeps its old reach outside a held live blend.
    const opening = served({ hero_probability_source: 'opening', blend_fold_revision: { [ROW]: 9 } });
    expect(applyLiveFrame(opening, pushed({ ...kalshiFrame, fold_revision: { [ROW]: 1 } }))?.hero_probability).toBe(0.6);
  });
});

describe('servedBlendEdgeObservation', () => {
  const base = {
    blend_edge_pinned: true, blend_edge_observed_at: at(10),
    aggregate_line: [{ timestamp: at(20), home_probability: 0.5 }],
  };

  test('carries a well-formed revision and drops a malformed one (no claim)', () => {
    expect(servedBlendEdgeObservation(base)).toEqual({ p: 0.5, observedAt: at(10) });
    expect(servedBlendEdgeObservation({ ...base, blend_edge_fold_revision: { [ROW]: 3 } }))
      .toEqual({ p: 0.5, observedAt: at(10), foldRevision: { [ROW]: 3 } });
    for (const bad of [null, {}, [], { [ROW]: 1.5 }, { [ROW]: '3' }, { [ROW]: -1 }]) {
      expect(servedBlendEdgeObservation({ ...base, blend_edge_fold_revision: bad })).toEqual({ p: 0.5, observedAt: at(10) });
    }
  });
});

describe('the ordering primitives', () => {
  test('compareFoldRevision', () => {
    expect(compareFoldRevision({ a: 2, b: 1 }, { a: 1, b: 1 })).toBe('newer');
    expect(compareFoldRevision({ a: 1, b: 1 }, { a: 1, b: 1 })).toBe('same');
    expect(compareFoldRevision({ a: 1, b: 0 }, { a: 1, b: 1 })).toBe('older');
    expect(compareFoldRevision({ a: 2, b: 0 }, { a: 1, b: 1 })).toBe('incomparable');
    expect(compareFoldRevision({ a: 2 }, { a: 1, b: 1 })).toBe('incomparable');
    expect(compareFoldRevision({ a: 2, c: 1 }, { a: 1, b: 1 })).toBe('incomparable');
  });

  test('parseFoldRevision accepts only non-empty maps of non-negative integers', () => {
    expect(parseFoldRevision({ a: 0 })).toEqual({ a: 0 });
    for (const bad of [undefined, null, 3, 'x', [], {}, { a: NaN }, { a: 1.5 }, { a: -1 }, { a: '1' }]) {
      expect(parseFoldRevision(bad)).toBeNull();
    }
  });

  test('frameFoldOrder', () => {
    expect(frameFoldOrder(undefined, { a: 1 })).toBeNull();
    expect(frameFoldOrder({ a: 1 }, undefined)).toBeNull();
    expect(frameFoldOrder({ a: 1, b: 1 }, undefined)).toBe('incomparable');
    expect(frameFoldOrder({ a: 1 }, { a: 2 })).toBe('newer');
    expect(frameFoldOrder({ a: 1 }, { a: 1 })).toBe('same');
    expect(frameFoldOrder({ a: 1 }, { b: 2 })).toBe('incomparable');
    expect(frameFoldOrder({ a: 1 }, { a: 2, b: 2 })).toBe('incomparable');
  });
});
