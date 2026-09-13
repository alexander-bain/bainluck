// #5885 — A GAME THAT HAS NOT KICKED OFF CANNOT HAVE AN UNBACKED LIVE CLAIM.
//
// ═══ WHAT THE READER SAW ═══
//
// /events/14780147 (Chargers–Cardinals) on production, 2026-09-13 10:09:12Z:
// the hero header read `No result reported · CBS · Sep 13, 2026 · 1:25 PM PDT`
// — ten hours BEFORE kickoff. Twenty minutes earlier the same page had read
// "Starts in 10h 34m". The payload said `status "scheduled"`, `completed_at
// null`, no scores. `artifacts/ux-1232/PROD-5866-nfl-320.png`.
//
// ═══ THE MECHANISM, AND WHY THE OLD PREDICATE WAS NOT WRONG ═══
//
// `isSuspended = hasNoReportedResult(status, commence_time) || liveClaimUnbacked`.
// The first disjunct is correct and returned false. The second is an age rule:
// `liveClaimIsUnbacked` fires when the freshest `win_probability_sources` write
// is over `LIVE_CLAIM_MAX_BLEND_AGE_MS` (60 min), and on that page the sources
// were 08:52:40Z / 09:06:12Z / 09:08:03Z — a 61-minute blend, which is the
// ORDINARY state of a pregame page, because pregame markets are polled slowly
// by design. The bound reasons explicitly about a live game on a two-minute
// beat; it was being asked a question it was never written for.
//
// So the repair is a composition, not a new threshold, and that is what this
// file pins. `liveClaimIsUnbacked` must keep answering the age question alone
// (the table below asserts that too), and only `pageLiveClaimIsUnbacked` — the
// seam the page actually calls — carries `hasStarted`.

import {
  liveClaimIsUnbacked,
  pageLiveClaimIsUnbacked,
  LIVE_CLAIM_MAX_BLEND_AGE_MS,
} from "@/lib/eventLivePush";

const OVER_THE_HOUR = LIVE_CLAIM_MAX_BLEND_AGE_MS + 60_000; // the measured 61 min
const FRESH = 20_000;

describe("#5885 a pregame page does not wear the suspended badge", () => {
  test("the measured specimen: not started, 61-minute blend → NOT unbacked", () => {
    expect(
      pageLiveClaimIsUnbacked({
        hasStarted: false,
        pinned: undefined,
        blendAgeMs: OVER_THE_HOUR,
      }),
    ).toBe(false);
  });

  test("not started and the SERVER pinned it → still not unbacked", () => {
    // `pinned` is the server's own verdict and outranks the age rule inside
    // `liveClaimIsUnbacked`. It cannot outrank kickoff: a pin on a match that
    // has not begun is a statement about a live probability that does not exist
    // yet, and acting on it puts the badge back on the page this fixes.
    expect(
      pageLiveClaimIsUnbacked({
        hasStarted: false,
        pinned: true,
        blendAgeMs: FRESH,
      }),
    ).toBe(false);
  });

  test("CONTROL: the same blend age AFTER kickoff is still unbacked", () => {
    // Without this the fix reads as "the flag never fires", which would silently
    // undo #5459 — Jeanjean v Liu, a live page with a 146-minute blend, is the
    // case the flag exists for.
    expect(
      pageLiveClaimIsUnbacked({
        hasStarted: true,
        pinned: undefined,
        blendAgeMs: OVER_THE_HOUR,
      }),
    ).toBe(true);
    expect(
      pageLiveClaimIsUnbacked({
        hasStarted: true,
        pinned: true,
        blendAgeMs: FRESH,
      }),
    ).toBe(true);
  });

  test("a started page with a fresh blend is backed, as before", () => {
    expect(
      pageLiveClaimIsUnbacked({
        hasStarted: true,
        pinned: undefined,
        blendAgeMs: FRESH,
      }),
    ).toBe(false);
  });

  test("an unstamped page is not unbacked, started or not", () => {
    // "We cannot say how old this is" and "this is old" are different claims —
    // the rule `liveClaimIsUnbacked` was written to, unchanged here.
    expect(
      pageLiveClaimIsUnbacked({ hasStarted: true, pinned: undefined, blendAgeMs: null }),
    ).toBe(false);
    expect(
      pageLiveClaimIsUnbacked({ hasStarted: false, pinned: undefined, blendAgeMs: null }),
    ).toBe(false);
  });

  test("the age predicate itself did NOT move — it still knows nothing about kickoff", () => {
    // The composition is the fix. If `hasStarted` had been pushed down into
    // `liveClaimIsUnbacked`, every other caller of a blend-age question would
    // have silently acquired a kickoff opinion.
    expect(liveClaimIsUnbacked({ pinned: undefined, blendAgeMs: OVER_THE_HOUR })).toBe(true);
    expect(liveClaimIsUnbacked({ pinned: true, blendAgeMs: FRESH })).toBe(true);
    expect(liveClaimIsUnbacked({ pinned: undefined, blendAgeMs: FRESH })).toBe(false);
  });
});
