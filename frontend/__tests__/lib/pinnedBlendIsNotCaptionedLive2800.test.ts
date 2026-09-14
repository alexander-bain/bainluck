// ux/1251 (#2800) — A PRICE FROZEN FOR 87 MINUTES IS NOT CAPTIONED "Live".
//
// ═══ WHAT WAS ON THE SCREEN ═══
//
// `/events/15312054` (Peliwo v Ziegann, ATP), production 2026-09-14 07:26Z,
// phone width 390px (`artifacts/ux-1251/live-tennis-15312054-390px.png`):
//
//     ● 1m ago                      <- header badge, fresh, and honest about the WRITE
//     No result reported            <- phase badge, already withdrawn
//        99 % – 1 %
//        Live · Bain Luck blend     <- one line under the withdrawal
//
// over a Win Probability chart flat at 99% across the entire match. The payload
// says why, in a field the backend already computes:
//
//     live_probability_pinned = { pinned: true, probability: 0.99,
//                                 observations: 84, span_seconds: 5247 }
//
// 84 reads over 87 minutes, every one of them 0.99.
//
// ═══ WHY #5069's GUARD CANNOT CATCH IT ═══
//
// #5069 removed "Live" from a blend past its freshness boundary, and that
// boundary is an AGE (`heroStampIsStale(stamp, "price")`, 120s). It is the
// right test for a source that went dark — Sabalenka–Pegula's `189m ago`. It is
// structurally blind to this one: a PINNED price is rewritten punctually with
// an identical value, so the stamp reads `1m ago` forever while the number has
// not moved in an hour and a half. New and unchanging at the same time.
//
// So the two defects are disjoint, and neither guard covers the other:
//
//     #5069  stale stamp, live claim intact     -> caption must drop "Live"
//     #2800  fresh stamp, live claim withdrawn  -> caption must drop "Live"
//
// ═══ WHY THE NUMBER STAYS ═══
//
// Standing notice 34 and #5069 both say the repair is removing a word, not
// adding a sentence — and a pinned match is NOT a `suspended` one. The venue
// still lists it and the book is still quoted at 0.99, so blanking the hero
// would assert less than we know. `status='suspended'` keeps its own `No price`
// answer, which it reaches through `isLive === false`, and the last describe
// block below pins that it is untouched by this change.

import { resolveProbability } from "../../lib/eventKeyStats";
import { blendCaptionIsStale } from "../../lib/eventState";
import type {
  EventHistoryResponse,
  EventDetailResponse,
} from "../../lib/types";

function hist(partial: Partial<EventHistoryResponse>): EventHistoryResponse {
  return { event_id: 1, history: [], ...partial } as unknown as EventHistoryResponse;
}

function evt(partial: Partial<EventDetailResponse>): EventDetailResponse {
  return {
    id: 1,
    home_team: "Peliwo",
    away_team: "Ziegann",
    status: "live",
    commence_time: "2026-09-14T06:00:00Z",
    ...partial,
  } as unknown as EventDetailResponse;
}

/** The specimen: a live event whose hero number is a genuine blend. */
const PINNED_BLEND = evt({
  status: "live",
  hero_probability: 0.99,
  hero_probability_away: 0.01,
  hero_probability_source: "blend",
} as Partial<EventDetailResponse>);

/**
 * The caption, resolved the way `app/events/[id]/page.tsx` now resolves it.
 *
 * The two booleans are passed SEPARATELY rather than pre-OR'd so each test
 * states which of the two real-world conditions it is standing up. This mirrors
 * the call site exactly: `blendCaptionIsStale(heroStampIsStale(...), unbacked)`.
 */
function caption(stampIsStale: boolean, liveClaimUnbacked: boolean): string | null {
  return resolveProbability(
    PINNED_BLEND,
    hist({}),
    null,
    true, // isLive — `status='live'`, which is the whole difficulty: this row
    false, //          never reaches the `noReportedResult` branch at all.
    false,
    blendCaptionIsStale(stampIsStale, liveClaimUnbacked),
  ).probSourceLabel;
}

describe("#2800 the hero caption does not call a withdrawn claim live", () => {
  test("THE BUG: a fresh stamp over a withdrawn claim is not captioned 'Live'", () => {
    // Fails before the fix. `stampIsStale=false` is the point — the page's own
    // badge said `1m ago`, so every age-based guard in the codebase passes this
    // row, and the caption still must not say "Live".
    expect(caption(false, true)).not.toMatch(/Live/);
    expect(caption(false, true)).toBe("Bain Luck blend");
  });

  test("the number itself still shows — only the claim about its currency goes", () => {
    // Notice 34. An empty hero would be a worse answer than a frozen one, and
    // the reader still has "No result reported" above it.
    const r = resolveProbability(
      PINNED_BLEND,
      hist({}),
      null,
      true,
      false,
      false,
      blendCaptionIsStale(false, true),
    );
    expect(r.homeProb).toBeCloseTo(0.99);
    expect(r.awayProb).toBeCloseTo(0.01);
  });

  test("A BACKED, FRESH BLEND KEEPS ITS WORD — the direction this must not cost", () => {
    // gotcha #43. The overwhelming majority of live events are neither stale
    // nor unbacked; if this arm ever goes red the fix has eaten the live case.
    expect(caption(false, false)).toBe("Live · Bain Luck blend");
  });

  test("#5069 is not regressed: a stale stamp alone still drops the word", () => {
    // The pre-existing defect must keep being caught with the claim intact.
    expect(caption(true, false)).toBe("Bain Luck blend");
  });

  test("both conditions at once is still just the one caption", () => {
    expect(caption(true, true)).toBe("Bain Luck blend");
  });
});

describe("#2800 blendCaptionIsStale — the whole truth table", () => {
  // Four rows, stated explicitly rather than generated, so a reader can see
  // that the only cell returning false is the one where BOTH signals are clear.
  test("only a fresh stamp AND a backed claim earns the word", () => {
    expect(blendCaptionIsStale(false, false)).toBe(false);
    expect(blendCaptionIsStale(true, false)).toBe(true);
    expect(blendCaptionIsStale(false, true)).toBe(true);
    expect(blendCaptionIsStale(true, true)).toBe(true);
  });

  test("it is an OR, not a replacement — neither input can mask the other", () => {
    // The mutant this kills: returning `liveClaimUnbacked` alone (which passes
    // every #2800 test above) silently un-fixes #5069, and vice versa.
    expect(blendCaptionIsStale(true, false)).toBe(blendCaptionIsStale(false, true));
    expect(blendCaptionIsStale(true, false)).toBe(true);
  });
});

describe("#2800 the suspended arm is reached another way and is untouched", () => {
  // `status='suspended'` renders `No price` today and must keep doing so. It
  // gets there through `isLive === false`, so it never passes through the
  // caption branch this file changes — pinned here to prove the change did not
  // reach across into it.
  const SUSPENDED = evt({
    status: "suspended",
    hero_probability: 0.97,
    hero_probability_away: 0.03,
    hero_probability_source: "blend",
  } as Partial<EventDetailResponse>);

  test("a suspended event with no chart point asserts no caption at all", () => {
    const r = resolveProbability(
      SUSPENDED,
      hist({}),
      null,
      false, // isLive — false for `suspended`, which is why its own branch runs
      false,
      true, // noReportedResult
      blendCaptionIsStale(false, true),
    );
    // Stronger than "does not say Live": this branch asserts NOTHING about the
    // number's source, which is what the `No price` hero renders from. Written
    // as an explicit null rather than a regex because a regex matcher silently
    // errors on null and would have read as a pass shape.
    expect(r.probSourceLabel).toBeNull();
  });
});
