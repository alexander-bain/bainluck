import { fetchEventWithLiveFrame, reconcileEventPoll } from '@/lib/reconcileEventPoll';
import { applyLiveFrame, type LiveFrame } from '@/lib/eventLivePush';
import { adoptNewerBlendEdge } from '@/lib/blendObservationClock';
import { servedBlendEdgeObservation } from '@/lib/blendObservationClock';
import { edgePredatesServedSourceRemoval, predatesServedSourceRemoval } from '@/lib/sourceRemovalClock';
import type { LiveStreamFrame } from '@/lib/liveStreamController';

// #9051, the exact-source counterexample (PR #9028 head c4318426): the page held
// a Kalshi frame (Kalshi .8 + Polymarket .4 = .6) observed 05:00:10; Kalshi was
// then retired; the fresh response serves Polymarket .4 alone, dated by
// Polymarket's last quote at 05:00:00 — older than the held frame. Fixed clocks.
const OLD_AT = '2026-09-27T05:00:00Z';
const FRAME_AT = '2026-09-27T05:00:10Z';
const REMOVED_AT = '2026-09-27T05:00:15Z';
const NEWER_AT = '2026-09-27T05:00:20Z';
const EARLIER_REMOVAL = '2026-09-27T04:00:00Z';

const kalshiFrame: LiveStreamFrame = {
  event_id: 123, status: 'live', source: 'kalshi', source_value: 0.8, p: 0.6, updated_at: FRAME_AT,
};

// The page applies a frame only once `p` is a number (`page.tsx`'s push effect).
const pushed = (frame: LiveStreamFrame): LiveFrame => ({ ...frame, p: frame.p as number });

function served(overrides: Record<string, unknown> = {}) {
  return {
    id: 123, status: 'live', hero_probability_source: 'blend',
    hero_probability: 0.4, hero_probability_away: 0.6, hero_probability_observed_at: OLD_AT,
    home_score: 14, away_score: 10,
    win_probability_sources: {
      polymarket: { value: 0.4, display_name: 'Polymarket', updated_at: OLD_AT },
    } as Record<string, { value: number; display_name?: string; updated_at: string }>,
    ...overrides,
  };
}

describe('the reported failure: a fresh post-removal response', () => {
  const postRemoval = served({ blend_source_removed_at: REMOVED_AT });

  test('keeps the survivors blend and does not recreate the removed source', async () => {
    const result = await fetchEventWithLiveFrame(async () => postRemoval, () => kalshiFrame, () => null);
    expect(result).toBe(postRemoval);
    expect(result.hero_probability).toBe(0.4);
    expect(result.win_probability_sources.kalshi).toBeUndefined();
  });

  test('refuses a held frame for a SURVIVOR too — its blend still folded the removed source', () => {
    const survivorFrame = { ...kalshiFrame, source: 'polymarket', source_value: 0.4 };
    expect(reconcileEventPoll(postRemoval, survivorFrame)).toBe(postRemoval);
  });

  test('refuses a frame observed at exactly the removal clock (the removal is the later write)', () => {
    expect(reconcileEventPoll(postRemoval, { ...kalshiFrame, updated_at: REMOVED_AT })).toBe(postRemoval);
  });

  test('refuses a pre-removal history edge, however much newer than the survivors quote', async () => {
    // Computed from the membership before the removal: that membership had none.
    const edge = { p: 0.6, observedAt: FRAME_AT, membershipRemovedAt: null };
    expect(adoptNewerBlendEdge(postRemoval, edge)).toBe(postRemoval);
    const result = await fetchEventWithLiveFrame(async () => postRemoval, () => null, () => edge);
    expect(result.hero_probability).toBe(0.4);
  });
});

describe('the push path: a delayed old frame landing on the post-removal cache', () => {
  test('returns the cache untouched', () => {
    const cache = served({ blend_source_removed_at: REMOVED_AT });
    expect(applyLiveFrame(cache, pushed(kalshiFrame))).toBe(cache);
  });

  test('is refused even when the cached hero clock is explicitly unknown', () => {
    // Price ordering abstains on a null hero clock and used to let this through.
    const cache = served({ blend_source_removed_at: REMOVED_AT, hero_probability_observed_at: null });
    expect(applyLiveFrame(cache, pushed(kalshiFrame))).toBe(cache);
  });
});

describe('healthy controls', () => {
  test('#8779: a stale response from BEFORE a source first appeared still takes its first frame', async () => {
    // Byte-identical sources to the failure; only the removal clock differs, and
    // an older (or no) removal cannot date a source that did not exist yet.
    for (const removal of [EARLIER_REMOVAL, null, undefined]) {
      const stale = served({ blend_source_removed_at: removal });
      const result = await fetchEventWithLiveFrame(async () => stale, () => kalshiFrame, () => null);
      expect(result.hero_probability).toBe(0.6);
      expect(result.win_probability_sources.kalshi).toEqual({ value: 0.8, updated_at: FRAME_AT });
      expect(result.win_probability_sources.polymarket.display_name).toBe('Polymarket');
    }
  });

  test('a source re-admitted AFTER its removal is delivered by its new frame', () => {
    const postRemoval = served({ blend_source_removed_at: REMOVED_AT });
    const readmitted = { ...kalshiFrame, p: 0.62, source_value: 0.84, updated_at: NEWER_AT };
    const result = reconcileEventPoll(postRemoval, readmitted);
    expect(result.hero_probability).toBe(0.62);
    expect(result.win_probability_sources.kalshi).toEqual({ value: 0.84, updated_at: NEWER_AT });
    expect(applyLiveFrame(postRemoval, pushed(readmitted))?.hero_probability).toBe(0.62);
  });

  test('a newer surviving response wins and keeps the removed source absent', () => {
    const newer = served({
      blend_source_removed_at: REMOVED_AT, hero_probability_observed_at: NEWER_AT,
      win_probability_sources: { polymarket: { value: 0.4, updated_at: NEWER_AT } },
    });
    expect(reconcileEventPoll(newer, kalshiFrame)).toBe(newer);
  });

  test('an ordinary newer frame for a still-admitted source advances the blend', () => {
    const admitted = served({
      blend_source_removed_at: EARLIER_REMOVAL, hero_probability: 0.45, hero_probability_away: 0.55,
      win_probability_sources: {
        polymarket: { value: 0.4, updated_at: OLD_AT }, kalshi: { value: 0.5, updated_at: OLD_AT },
      },
    });
    const result = reconcileEventPoll(admitted, kalshiFrame);
    expect(result.hero_probability).toBe(0.6);
    expect(result.win_probability_sources.kalshi.value).toBe(0.8);
  });

  test('#8789: an older frame still loses to a newer cached price, removal clock or not', () => {
    const cache = served({ blend_source_removed_at: EARLIER_REMOVAL, hero_probability_observed_at: NEWER_AT });
    expect(applyLiveFrame(cache, pushed(kalshiFrame))).toBe(cache);
  });

  test('a post-removal history edge observed after the removal is adopted', () => {
    const postRemoval = served({ blend_source_removed_at: REMOVED_AT });
    const result = adoptNewerBlendEdge(postRemoval, { p: 0.42, observedAt: NEWER_AT, membershipRemovedAt: REMOVED_AT });
    expect(result?.hero_probability).toBe(0.42);
    expect(result?.hero_probability_observed_at).toBe(NEWER_AT);
  });
});

describe('no removal claim decides nothing — every existing rule applies unchanged', () => {
  test.each([undefined, null, '', 'not-a-time'])('removal clock %p: the old behaviour stands', removal => {
    const legacy = served({ blend_source_removed_at: removal });
    // Without the producer this is the exact PR #9028 behaviour, kept on purpose:
    // the client cannot tell a removal from a pre-addition response on its own.
    expect(reconcileEventPoll(legacy, kalshiFrame).hero_probability).toBe(0.6);
    expect(adoptNewerBlendEdge(legacy, { p: 0.6, observedAt: FRAME_AT, membershipRemovedAt: null })?.hero_probability).toBe(0.6);
  });

  test('an unparseable frame clock keeps its existing semantics on both paths', () => {
    const cache = served({ blend_source_removed_at: REMOVED_AT });
    const undated = { ...kalshiFrame, updated_at: 'invalid' };
    expect(reconcileEventPoll(cache, undated)).toBe(cache);
    expect(applyLiveFrame(cache, pushed(undated))?.hero_probability).toBe(0.6);
  });

  test('settled and non-live caches are outside this rule', () => {
    const final = served({ status: 'completed', blend_source_removed_at: REMOVED_AT });
    expect(reconcileEventPoll(final, kalshiFrame)).toBe(final);
    // The push path keeps its old reach outside a held live blend: an opening
    // hero is not a blend the removal clock dates.
    const opening = served({ hero_probability_source: 'opening', blend_source_removed_at: REMOVED_AT });
    expect(applyLiveFrame(opening, pushed(kalshiFrame))?.hero_probability).toBe(0.6);
  });

  test('the predicate itself', () => {
    expect(predatesServedSourceRemoval({ blend_source_removed_at: REMOVED_AT }, FRAME_AT)).toBe(true);
    expect(predatesServedSourceRemoval({ blend_source_removed_at: REMOVED_AT }, REMOVED_AT)).toBe(true);
    expect(predatesServedSourceRemoval({ blend_source_removed_at: REMOVED_AT }, NEWER_AT)).toBe(false);
    expect(predatesServedSourceRemoval({ blend_source_removed_at: REMOVED_AT }, null)).toBe(false);
    expect(predatesServedSourceRemoval({}, FRAME_AT)).toBe(false);
    expect(predatesServedSourceRemoval(null, FRAME_AT)).toBe(false);
  });
});

// Codex source review of PR #9061 head 8472caecee (SOURCE-REVIEW.md): the edge's
// PRICE clock cannot tell which membership it came from. All 05:00:ssZ: Polymarket
// .4 at 00; Polymarket .5 observed 10; Kalshi removed 15; the matcher commits .5
// at 20 into the post-removal row, stamping the observation (10), not its commit.
describe('Codex timeline: a history edge is ordered by its MEMBERSHIP, not its price clock', () => {
  const postRemoval = served({ blend_source_removed_at: REMOVED_AT });

  test('post-removal commit of a price observed before the removal is ADOPTED (.5)', () => {
    const edge = { p: 0.5, observedAt: FRAME_AT, membershipRemovedAt: REMOVED_AT };
    const result = adoptNewerBlendEdge(postRemoval, edge);
    expect(result?.hero_probability).toBe(0.5);
    expect(result?.hero_probability_observed_at).toBe(FRAME_AT);
  });

  test('the old blend that folded the removed source is REFUSED (.4), same price clock', () => {
    for (const membership of [null, EARLIER_REMOVAL]) {
      const edge = { p: 0.6, observedAt: FRAME_AT, membershipRemovedAt: membership };
      expect(adoptNewerBlendEdge(postRemoval, edge)).toBe(postRemoval);
    }
  });

  test('an observation after the removal is adopted (.5)', () => {
    const edge = { p: 0.5, observedAt: NEWER_AT, membershipRemovedAt: REMOVED_AT };
    expect(adoptNewerBlendEdge(postRemoval, edge)?.hero_probability).toBe(0.5);
  });

  test('an edge with no membership claim decides nothing: price ordering stands', () => {
    // The producer half is not shipped; the client cannot infer membership order.
    expect(adoptNewerBlendEdge(postRemoval, { p: 0.5, observedAt: FRAME_AT })?.hero_probability).toBe(0.5);
    expect(adoptNewerBlendEdge(postRemoval, { p: 0.5, observedAt: FRAME_AT, membershipRemovedAt: 'x' })?.hero_probability).toBe(0.5);
  });

  test('servedBlendEdgeObservation: key absent is no claim; served null IS a claim', () => {
    const base = {
      blend_edge_pinned: true, blend_edge_observed_at: FRAME_AT,
      aggregate_line: [{ timestamp: NEWER_AT, home_probability: 0.5 }],
    };
    expect(servedBlendEdgeObservation(base)).toEqual({ p: 0.5, observedAt: FRAME_AT });
    expect(servedBlendEdgeObservation({ ...base, blend_edge_source_removed_at: null }))
      .toEqual({ p: 0.5, observedAt: FRAME_AT, membershipRemovedAt: null });
    expect(servedBlendEdgeObservation({ ...base, blend_edge_source_removed_at: REMOVED_AT }))
      .toEqual({ p: 0.5, observedAt: FRAME_AT, membershipRemovedAt: REMOVED_AT });
  });

  test('the edge predicate itself', () => {
    const hero = { blend_source_removed_at: REMOVED_AT };
    expect(edgePredatesServedSourceRemoval(hero, null)).toBe(true);
    expect(edgePredatesServedSourceRemoval(hero, EARLIER_REMOVAL)).toBe(true);
    expect(edgePredatesServedSourceRemoval(hero, REMOVED_AT)).toBe(false);
    expect(edgePredatesServedSourceRemoval(hero, NEWER_AT)).toBe(false);
    expect(edgePredatesServedSourceRemoval(hero, undefined)).toBe(false);
    expect(edgePredatesServedSourceRemoval(hero, 'x')).toBe(false);
    expect(edgePredatesServedSourceRemoval({}, null)).toBe(false);
    expect(edgePredatesServedSourceRemoval(null, null)).toBe(false);
  });
});
