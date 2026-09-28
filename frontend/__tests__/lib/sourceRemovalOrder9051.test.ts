import { readFileSync } from 'fs';
import { fetchEventWithLiveFrame, keepNewerHeldHeadline, reconcileEventPoll } from '@/lib/reconcileEventPoll';
import { applyLiveFrame, frameInvalidatesFoldedBlend, type LiveFrame } from '@/lib/eventLivePush';
import { adoptNewerBlendEdge, edgeInvalidatesHeldBlend, servedBlendEdgeObservation } from '@/lib/blendObservationClock';
import { createFoldedRefetchScheduler } from '@/lib/foldedRefetchScheduler';
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
  const preRemovalFrame = { ...kalshiFrame, rev: { [ROW]: 1 } };

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
    expect(applyLiveFrame(postRemoval, pushed({ ...preRemovalFrame, rev: { [ROW]: 2 } }))).toBe(postRemoval);
  });
});

describe('frames that must still land', () => {
  test('#8779: a stale response from before a source first appeared takes its first frame', () => {
    const stale = served({ blend_fold_revision: { [ROW]: 1 } });
    const firstFrame = { ...kalshiFrame, rev: { [ROW]: 2 } };
    const result = applyLiveFrame(stale, pushed(firstFrame))!;
    expect(result.hero_probability).toBe(0.6);
    expect(result.win_probability_sources.kalshi).toEqual({ value: 0.8, updated_at: at(10) });
    expect(result.win_probability_sources.polymarket.display_name).toBe('Polymarket');
    expect(result.blend_fold_revision).toEqual({ [ROW]: 2 });
  });

  test('a source re-admitted after its removal is delivered by its newer write', () => {
    const postRemoval = served({ blend_fold_revision: { [ROW]: 2 } });
    const readmitted = { ...kalshiFrame, p: 0.62, source_value: 0.84, updated_at: at(20), rev: { [ROW]: 3 } };
    expect(applyLiveFrame(postRemoval, pushed(readmitted))?.hero_probability).toBe(0.62);
    expect(reconcileEventPoll(postRemoval, readmitted).win_probability_sources.kalshi)
      .toEqual({ value: 0.84, updated_at: at(20) });
  });

  test('a newer write lands even when its clock reads older than the held price clock', () => {
    // Commit order is the claim; the frame's own clock is kept as its provenance.
    const cache = held(0.4, 30, { [ROW]: 2 });
    const result = applyLiveFrame(cache, pushed({ ...kalshiFrame, rev: { [ROW]: 3 } }))!;
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
    const frame = pushed({ ...kalshiFrame, rev: rev });
    expect(applyLiveFrame(folded, frame)).toBe(folded);
    expect(frameInvalidatesFoldedBlend(folded, frame)).toBe(true);
  });

  test('CONTROL — a single-row hero does not ask for a refetch on a frame it can order', () => {
    const single = served({ blend_fold_revision: { [ROW]: 4 } });
    expect(frameInvalidatesFoldedBlend(single, pushed({ ...kalshiFrame, rev: { [ROW]: 5 } }))).toBe(false);
    expect(frameInvalidatesFoldedBlend(single, pushed({ ...kalshiFrame, rev: { [ROW]: 3 } }))).toBe(false);
    expect(frameInvalidatesFoldedBlend(served(), pushed(kalshiFrame))).toBe(false);
    expect(frameInvalidatesFoldedBlend({ ...folded, status: 'completed' }, pushed(kalshiFrame))).toBe(false);
  });

  test('a single-row hero refuses a frame for a row it did not read, and refetches', () => {
    const single = served({ blend_fold_revision: { [ROW]: 4 } });
    const other = pushed({ ...kalshiFrame, rev: { [TWIN]: 9 } });
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

  test('an absent or malformed edge revision is refused by a versioned headline — it cannot borrow rev15', () => {
    const cache = held(0.4, 0, { [ROW]: 15 });
    for (const e of [edge(0.5, 10), { p: 0.5, observedAt: at(10), foldRevision: { [ROW]: -1 } }]) {
      expect(adoptNewerBlendEdge(cache, e)).toBe(cache);
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

  test('a single-row held revision refuses a revisionless frame and asks for the paired read', () => {
    const cache = served({ blend_fold_revision: { [ROW]: 2 } });
    expect(applyLiveFrame(cache, pushed(kalshiFrame))).toBe(cache);
    expect(reconcileEventPoll(cache, kalshiFrame)).toBe(cache);
    expect(frameInvalidatesFoldedBlend(cache, pushed(kalshiFrame))).toBe(true);
  });

  test('settled and non-live caches are outside the rule', () => {
    const final = served({ status: 'completed', blend_fold_revision: { [ROW]: 9 } });
    expect(reconcileEventPoll(final, { ...kalshiFrame, rev: { [ROW]: 1 } })).toBe(final);
    // The push path keeps its old reach outside a held live blend.
    const opening = served({ hero_probability_source: 'opening', blend_fold_revision: { [ROW]: 9 } });
    expect(applyLiveFrame(opening, pushed({ ...kalshiFrame, rev: { [ROW]: 1 } }))?.hero_probability).toBe(0.6);
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
    for (const bad of [undefined, null, 3, 'x', [], {}, { a: NaN }, { a: 1.5 }, { a: -1 }, { a: '1' }, { a: 2 ** 53 }]) {
      expect(parseFoldRevision(bad)).toBeNull();
    }
  });

  test('frameFoldOrder', () => {
    expect(frameFoldOrder(undefined, { a: 1 })).toBeNull();
    expect(frameFoldOrder({ a: 1 }, undefined)).toBe('incomparable');
    expect(frameFoldOrder({ a: 1 }, { a: -1 })).toBe('incomparable');
    expect(frameFoldOrder({ a: 1, b: 1 }, undefined)).toBe('incomparable');
    expect(frameFoldOrder({ a: 1 }, { a: 2 })).toBe('newer');
    expect(frameFoldOrder({ a: 1 }, { a: 1 })).toBe('same');
    expect(frameFoldOrder({ a: 1 }, { b: 2 })).toBe('incomparable');
    expect(frameFoldOrder({ a: 1 }, { a: 2, b: 2 })).toBe('incomparable');
  });
});

// Codex, revision-95bcc174/SOURCE-REVIEW.md: four delivery gaps on the actual
// call paths — the helpers were right, the page's fetch/push/history flow was not.
describe('Codex 95bcc174 (1): the poll path orders by revision BEFORE its clock gates', () => {
  test('a hero with an explicitly unknown clock takes a strictly newer write through the fetch chain', async () => {
    const polled = served({ hero_probability: 0.6, hero_probability_away: 0.4, hero_probability_observed_at: null, blend_fold_revision: { [ROW]: 2 } });
    const frame = { ...kalshiFrame, p: 0.4, updated_at: at(40), rev: { [ROW]: 3 } };
    const result = await fetchEventWithLiveFrame(async () => polled, () => frame, () => null);
    expect(headline(result)).toEqual({ p: 0.4, at: at(40), rev: { [ROW]: 3 } });
  });

  test('CONTROL — with no revision claim the unknown-clock protection still holds', async () => {
    const polled = served({ hero_probability: 0.6, hero_probability_away: 0.4, hero_probability_observed_at: null });
    const frame = { ...kalshiFrame, p: 0.4, updated_at: at(40) };
    expect(await fetchEventWithLiveFrame(async () => polled, () => frame, () => null)).toBe(polled);
  });

  test('an older or same revision is refused by the poll path too', () => {
    const polled = served({ blend_fold_revision: { [ROW]: 3 } });
    for (const rev of [2, 3]) {
      expect(reconcileEventPoll(polled, { ...kalshiFrame, updated_at: at(59), rev: { [ROW]: rev } })).toBe(polled);
    }
  });
});

describe('Codex 95bcc174 (2): a first frame keeps its revision', () => {
  test('accepted under the legacy rule with no held revision, its vector stays with its value', () => {
    const result = applyLiveFrame(served(), pushed({ ...kalshiFrame, rev: { [ROW]: 3 } }))!;
    expect(headline(result)).toEqual({ p: 0.6, at: at(10), rev: { [ROW]: 3 } });
    // …so a later stale frame is now orderable, and refused.
    expect(applyLiveFrame(result, pushed({ ...kalshiFrame, p: 0.7, updated_at: at(20), rev: { [ROW]: 2 } }))).toBe(result);
  });

  test('a malformed frame vector is not retained', () => {
    expect(applyLiveFrame(served(), pushed({ ...kalshiFrame, rev: { [ROW]: -3 } }))?.blend_fold_revision).toBeUndefined();
  });
});

describe('Codex 95bcc174 (3): a later poll cannot forget an accepted revision', () => {
  // The page adopted .5 @10 rev25 from history; a delayed history .6 @12 rev15
  // was refused but is now the fetcher's latest edge; a stale detail at rev15 lands.
  const accepted = adoptNewerBlendEdge(held(0.4, 0, { [ROW]: 15 }), edge(0.5, 10, { [ROW]: 25 }))!;
  const oldEdge = edge(0.6, 12, { [ROW]: 15 });
  const stalePoll = served({
    hero_probability: 0.6, hero_probability_away: 0.4, hero_probability_observed_at: at(12), blend_fold_revision: { [ROW]: 15 }, home_score: 21,
    // The pre-removal membership: the retired source is still in its rail.
    win_probability_sources: { polymarket: { value: 0.4, updated_at: at(0) }, kalshi: { value: 0.8, updated_at: at(12) } },
  });

  test('the stale poll keeps the accepted headline and revision, and takes its REST fields', async () => {
    const result = await fetchEventWithLiveFrame(async () => stalePoll, () => null, () => oldEdge, () => accepted);
    expect(headline(result)).toEqual({ p: 0.5, at: at(10), rev: { [ROW]: 25 } });
    expect(result.home_score).toBe(21);
    // The rail stays with the number it explains: no retired source comes back.
    expect(result.win_probability_sources).toBe(accepted.win_probability_sources);
    expect(result.win_probability_sources.kalshi).toBeUndefined();
  });

  test('CONTROL — without the held headline (the old fetch chain) the stale poll wins: this is the defect', async () => {
    const result = await fetchEventWithLiveFrame(async () => stalePoll, () => null, () => oldEdge);
    expect(result.hero_probability).toBe(0.6);
  });

  test('a newer or incomparable poll is the authoritative read and wins whole', () => {
    const newer = served({ hero_probability: 0.45, blend_fold_revision: { [ROW]: 30 } });
    expect(keepNewerHeldHeadline(newer, accepted)).toBe(newer);
    const refolded = served({ hero_probability: 0.45, blend_fold_revision: { [ROW]: 25, [TWIN]: 1 } });
    expect(keepNewerHeldHeadline(refolded, accepted)).toBe(refolded);
  });

  test('a live-blend poll with no revision keeps the held blend with its own revision, and takes its REST fields', () => {
    const legacy = served({ hero_probability: 0.45, home_score: 28 });
    const result = keepNewerHeldHeadline(legacy, accepted);
    expect(headline(result)).toEqual({ p: 0.5, at: at(10), rev: { [ROW]: 25 } });
    expect(result.win_probability_sources).toBe(accepted.win_probability_sources);
    expect(result.home_score).toBe(28);
  });

  test('a poll that ends the game is never held back by an older revision', () => {
    const final = served({ status: 'completed', hero_probability_source: 'final', hero_probability: 1, blend_fold_revision: { [ROW]: 15 } });
    expect(keepNewerHeldHeadline(final, accepted)).toBe(final);
  });
});

describe('Codex 95bcc174 (4): an incomparable history edge asks for the authoritative read', () => {
  const heldFold = held(0.4, 0, { [ROW]: 2, [TWIN]: 2 });

  test.each([
    ['a twin left the fold', { [ROW]: 3 }],
    ['a row joined the fold', { [ROW]: 3, [TWIN]: 3, '789': 1 }],
    ['the components disagree', { [ROW]: 3, [TWIN]: 1 }],
  ])('%s: refused, and a refetch is requested', (_label, rev) => {
    expect(adoptNewerBlendEdge(heldFold, edge(0.7, 50, rev))).toBe(heldFold);
    expect(edgeInvalidatesHeldBlend(heldFold, edge(0.7, 50, rev))).toBe(true);
  });

  test('CONTROL — orderable, absent or non-live edges request nothing', () => {
    expect(edgeInvalidatesHeldBlend(heldFold, edge(0.7, 50, { [ROW]: 3, [TWIN]: 2 }))).toBe(false);
    expect(edgeInvalidatesHeldBlend(heldFold, edge(0.7, 50, { [ROW]: 1, [TWIN]: 2 }))).toBe(false);
    expect(edgeInvalidatesHeldBlend(heldFold, edge(0.7, 50))).toBe(false);
    expect(edgeInvalidatesHeldBlend(held(0.4, 0, undefined), edge(0.7, 50, { [ROW]: 3 }))).toBe(false);
    expect(edgeInvalidatesHeldBlend({ ...heldFold, status: 'completed' }, edge(0.7, 50, { [ROW]: 3 }))).toBe(false);
  });

  test('the refetched detail is adopted over the old fold, so the refusal does not loop', () => {
    const refetched = served({ hero_probability: 0.7, blend_fold_revision: { [ROW]: 3 } });
    const result = keepNewerHeldHeadline(refetched, heldFold);
    expect(result).toBe(refetched);
    expect(edgeInvalidatesHeldBlend(result, edge(0.72, 55, { [ROW]: 4 }))).toBe(false);
  });
});

describe('the refetch scheduler: rate-limited, and the last request of a burst is never lost', () => {
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => jest.useRealTimers());

  test('a burst refetches once now and once at the window end, then stays quiet', () => {
    const refetch = jest.fn();
    const scheduler = createFoldedRefetchScheduler(refetch, 5000, () => Date.now());
    scheduler.request();
    expect(refetch).toHaveBeenCalledTimes(1);
    for (let i = 0; i < 4; i += 1) { jest.advanceTimersByTime(1000); scheduler.request(); }
    expect(refetch).toHaveBeenCalledTimes(1);
    jest.advanceTimersByTime(1000);
    expect(refetch).toHaveBeenCalledTimes(2); // the trailing one: the stream then went quiet
    jest.advanceTimersByTime(60_000);
    expect(refetch).toHaveBeenCalledTimes(2);
  });

  test('requests spaced beyond the window each refetch immediately', () => {
    const refetch = jest.fn();
    const scheduler = createFoldedRefetchScheduler(refetch, 5000, () => Date.now());
    scheduler.request();
    jest.advanceTimersByTime(6000);
    scheduler.request();
    expect(refetch).toHaveBeenCalledTimes(2);
  });

  test('cancel drops a pending trailing refetch (unmount)', () => {
    const refetch = jest.fn();
    const scheduler = createFoldedRefetchScheduler(refetch, 5000, () => Date.now());
    scheduler.request();
    scheduler.request();
    scheduler.cancel();
    jest.advanceTimersByTime(10_000);
    expect(refetch).toHaveBeenCalledTimes(1);
  });
});

describe('the page: a refuse-and-refetch branch writes nothing in the same tick', () => {
  // swr drops a fetch that any later mutation post-dates — even a no-op one —
  // so a refetch followed by `refreshEvent(prev => prev)` cancels itself. jsdom
  // is not installed here, so the page's two branches are pinned in source.
  const page = readFileSync('app/events/[id]/page.tsx', 'utf8');

  test('the push effect returns right after requesting the refetch', () => {
    expect(page).toMatch(/if \(frameInvalidatesFoldedBlend\(heldEventRef\.current, liveFrame\)\) \{\s*foldedRefetch\.request\(\);\s*return;\s*\}/);
  });

  test('the history effect returns right after requesting the refetch', () => {
    expect(page).toMatch(/if \(edgeInvalidatesHeldBlend\(heldEventRef\.current, edge\)\) \{\s*foldedRefetch\.request\(\);\s*return;\s*\}/);
  });

  test('the poll fetcher reconciles against the held headline', () => {
    expect(page).toMatch(/\(\) => latestBlendEdgeRef\.current,\s*\(\) => heldEventRef\.current,/);
    expect(page).toMatch(/heldEventRef\.current = event;/);
  });
});

describe("the producer's wire shapes (PR #9078, backend/tests/test_fold_revision_9051.py)", () => {
  // Verbatim `json.dumps(build_frame(...))`: the frame's revision key is `rev`,
  // `{"<event_id>": rev}`, or null when the writer had none (no claim).
  const wire = (rev: string, updatedAt = at(10)) => JSON.parse(
    `{"event_id": 15, "p": 0.6, "source": "kalshi", "source_value": 0.8, "updated_at": "${updatedAt}", "status": "live", "rev": ${rev}}`,
  ) as LiveStreamFrame;
  const single = () => held(0.4, 0, { '15': 11 });

  test('a newer `rev` lands and its vector travels with the value', () => {
    const result = applyLiveFrame(single(), pushed(wire('{"15": 12}')))!;
    expect(headline(result)).toEqual({ p: 0.6, at: at(10), rev: { '15': 12 } });
  });

  test('an older `rev` is refused even though its clock is newer — the key is read', () => {
    const cache = single();
    expect(applyLiveFrame(cache, pushed(wire('{"15": 10}', at(30))))).toBe(cache);
    expect(reconcileEventPoll(cache, wire('{"15": 10}', at(30)))).toBe(cache);
  });

  test('`rev: null` cannot be ordered against a held vector: refused, and the page asks for the paired read', () => {
    const cache = single();
    expect(applyLiveFrame(cache, pushed(wire('null')))).toBe(cache);
    expect(frameInvalidatesFoldedBlend(cache, pushed(wire('null')))).toBe(true);
    // With no held vector it claims nothing: the clock rule decides, no vector is minted.
    const legacy = held(0.4, 0, undefined);
    expect(headline(applyLiveFrame(legacy, pushed(wire('null'))))).toEqual({ p: 0.6, at: at(10), rev: undefined });
  });

  test("a folded detail vector with a twin at the migration's default 0 still invalidates on any frame", () => {
    const folded = served({ blend_fold_revision: { '15': 4, '16': 0 } });
    expect(parseFoldRevision(folded.blend_fold_revision)).toEqual({ '15': 4, '16': 0 });
    expect(frameInvalidatesFoldedBlend(folded, pushed(wire('{"15": 5}')))).toBe(true);
    expect(applyLiveFrame(folded, pushed(wire('{"15": 5}')))).toBe(folded);
  });

  test('a history payload whose edge revision is null (no pin, or a pre-#9051 cache) makes no claim', () => {
    const history = { blend_edge_pinned: true, blend_edge_observed_at: at(10), blend_edge_fold_revision: null,
      aggregate_line: [{ timestamp: at(20), home_probability: 0.5 }] };
    expect(servedBlendEdgeObservation(history)).toEqual({ p: 0.5, observedAt: at(10) });
  });
});

// Codex on 64a14a3d8d: held .5 @10 rev25; a legacy (or malformed-vector) REST
// .6 @20 still folding the removed source; the current history .5 @10 rev25.
// keepNewerHeldHeadline took the REST .6 and copied rev25 onto it, so the next
// edge saw equal vectors and an older clock and could never repair it.
// The invariant: a value and its revision stay paired, on every entry point.
describe('Codex 64a14a3d8d: a value never borrows a revision from another value', () => {
  const accepted = held(0.5, 10, { [ROW]: 25 });
  const currentHistory = edge(0.5, 10, { [ROW]: 25 });
  const restWithRemoved = (rev: unknown) => served({
    hero_probability: 0.6, hero_probability_away: 0.4, hero_probability_observed_at: at(20), home_score: 21,
    win_probability_sources: { polymarket: { value: 0.4, updated_at: at(0) }, kalshi: { value: 0.8, updated_at: at(20) } },
    blend_fold_revision: rev as Record<string, number> | undefined,
  });

  test.each([
    ['legacy (absent)', undefined],
    ['malformed', { [ROW]: -1 }],
  ])('%s REST vector: the fetch chain keeps .5/rev25, takes the score, and the next edge leaves it right', async (_, rev) => {
    const polled = await fetchEventWithLiveFrame(async () => restWithRemoved(rev), () => null, () => currentHistory, () => accepted);
    expect(headline(polled)).toEqual({ p: 0.5, at: at(10), rev: { [ROW]: 25 } });
    expect(polled.win_probability_sources.kalshi).toBeUndefined();
    expect(polled.home_score).toBe(21);
    expect(headline(adoptNewerBlendEdge(polled, currentHistory))).toEqual({ p: 0.5, at: at(10), rev: { [ROW]: 25 } });
  });

  test('CONTROL — the 64a14a3d8d pairing (.6 tagged rev25) is the one the next edge cannot repair', () => {
    const fabricated = { ...restWithRemoved(undefined), blend_fold_revision: { [ROW]: 25 } };
    expect(adoptNewerBlendEdge(fabricated, currentHistory)).toBe(fabricated);
  });

  test('a versioned REST read is still the authoritative one: newer wins whole, with its own vector', async () => {
    const newer = served({ hero_probability: 0.45, blend_fold_revision: { [ROW]: 30 } });
    const polled = await fetchEventWithLiveFrame(async () => newer, () => null, () => currentHistory, () => accepted);
    expect(headline(polled)).toEqual({ p: 0.45, at: at(0), rev: { [ROW]: 30 } });
  });

  test('terminal transitions are never held back by a revision, and carry none of the held one', () => {
    const final = served({ status: 'completed', hero_probability_source: 'final', hero_probability: 1 });
    expect(keepNewerHeldHeadline(final, accepted)).toBe(final);
    const opening = served({ hero_probability_source: 'opening', hero_probability: 0.55 });
    expect(keepNewerHeldHeadline(opening, accepted)).toBe(opening);
  });

  test('true revisionless bootstrap is unchanged: with nothing held, every response and frame lands as before', async () => {
    const legacyHeld = held(0.4, 0, undefined);
    expect(keepNewerHeldHeadline(restWithRemoved(undefined), legacyHeld)).toEqual(restWithRemoved(undefined));
    expect(applyLiveFrame(legacyHeld, pushed(kalshiFrame))?.hero_probability).toBe(0.6);
  });

  test('push path: an applied frame carries its own vector or none, never the held one', () => {
    // Outside a held live blend the frame lands (its old reach) — without the held rev9.
    const opening = served({ hero_probability_source: 'opening', blend_fold_revision: { [ROW]: 9 } });
    const bare = applyLiveFrame(opening, pushed(kalshiFrame))!;
    expect(bare.hero_probability).toBe(0.6);
    expect(bare.blend_fold_revision).toBeUndefined();
    expect(applyLiveFrame(opening, pushed({ ...kalshiFrame, rev: { [ROW]: 1 } }))?.blend_fold_revision).toEqual({ [ROW]: 1 });
  });

  test('history path: a revisionless edge adopted by a revisionless headline mints no vector', () => {
    const result = adoptNewerBlendEdge(held(0.4, 0, undefined), edge(0.5, 10));
    expect(headline(result)).toEqual({ p: 0.5, at: at(10), rev: undefined });
  });
});
