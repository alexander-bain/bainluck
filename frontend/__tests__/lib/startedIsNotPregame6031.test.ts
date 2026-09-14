/**
 * A MATCH THAT HAS KICKED OFF IS NOT "PREGAME" — #6031, from live/217.
 *
 * ═══ WHAT THE READER SAW ═══
 *
 * /events/15308588 (Barcelona v Delfin) on production, 2026-09-14 00:10Z:
 * **77 minutes** past its own served kickoff, `status "scheduled"`, and the
 * hero's phase badge read the literal word `Pregame` — directly above a chart
 * headed "Since Start". Screenshot:
 * `artifacts/live-216/barcelona-delfin-pregame-0010Z.png`.
 *
 * ═══ THE MECHANISM, AND WHY NEITHER EXISTING GUARD CAUGHT IT ═══
 *
 * The badge's last branch is reached when an event is not live, not final and
 * not `hasNoReportedResult`. Two fixes already live on it and each closed its
 * own half of the lie:
 *
 *   - #3211 suppressed the COUNTDOWN once `hasStarted`, so the page stopped
 *     counting down to a moment in the past;
 *   - live/048 gave `suspended` its own branch, so a stopped match stopped
 *     falling through to this one.
 *
 * What neither covers is the window BETWEEN them. `startedWithoutResult` only
 * fires past `UPCOMING_GRACE_MS` (2h), so for two hours after kickoff a
 * `scheduled` row is `hasStarted && !isSuspended` — and #3211's suppression
 * turned the ternary's live arm off without changing the word its dead arm
 * prints. The page contradicted its own `hasStarted` in the one place a reader
 * looks first.
 *
 * THIS IS NOT A TAIL STATE. Every match passes through this window, because a
 * row is `scheduled` until a source flips it to `live`: seconds where ESPN
 * anchors the fixture, up to the full two hours where nothing does (tennis,
 * #2700). It is the badge a reader sees when they tap a card at kickoff.
 *
 * ═══ WHAT THIS FILE REFUSES, AS MUCH AS WHAT IT ASSERTS ═══
 *
 * The tempting repair is to widen the grace (or `hasNoReportedResult`) so the
 * window closes. That would print "No result reported" over a match twenty
 * minutes in — false, and the precise claim the grace exists to refuse. So the
 * last describe below pins the grace UNMOVED from both sides: this fix is the
 * word and only the word, and a future session that closes the hole by moving
 * the floor turns those arms red.
 *
 * ═══ EVERY ARM PINS ITS OWN CLOCK ═══
 *
 * `startedWithoutResult` takes a time, so gotcha #44 applies: every assertion
 * offsets from `KICKOFF` rather than reading the real clock, and the boundary
 * is stated from both sides.
 */

import {
  UPCOMING_GRACE_MS,
  hasNoReportedResult,
  startBadgeLabel,
  startedWithoutResult,
} from "@/lib/eventState";

/** Fixed anchor. Offset FIRST, then compare — never branch on the real clock. */
const KICKOFF = Date.parse("2026-09-14T22:53:00.000Z");
const MINUTE = 60_000;

/** The measured specimen: 77 minutes past kickoff, inside the two-hour grace. */
const SPECIMEN_NOW = KICKOFF + 77 * MINUTE;

const ISO = new Date(KICKOFF).toISOString();

describe("#6031 the phase badge stops calling a kicked-off match Pregame", () => {
  test("THE MEASURED SPECIMEN: started, no countdown → 'Started', never 'Pregame'", () => {
    // The old ternary was `countdown && !hasStarted ? … : "Pregame"`, so with
    // `hasStarted` true it printed "Pregame" whatever the countdown held. Both
    // arms below are RED against that expression — this is the fix.
    expect(startBadgeLabel(true, "")).toBe("Started");
    expect(startBadgeLabel(true, "")).not.toBe("Pregame");
  });

  test("started with a STALE countdown still in state → 'Started'", () => {
    // `gameCountdown` is React state on a once-a-second timer; it does not
    // necessarily empty itself the instant kickoff passes. The label must not
    // depend on whether that tick has landed yet.
    expect(startBadgeLabel(true, "0h 0m")).toBe("Started");
    expect(startBadgeLabel(true, "2h 14m")).toBe("Started");
  });

  test("the word never asserts play — 'Started' only says kickoff passed", () => {
    // `hasStarted` is `commence_time <= now` and nothing more. A source saying
    // the match is being played sends the badge to the LIVE branch (emerald,
    // pulsing) and never reaches this function at all, so anything stronger
    // here would claim what no source has reported.
    const label = startBadgeLabel(true, "");
    expect(label).not.toMatch(/underway|in progress|live|playing/i);
    // ...and it is a word, not a sentence — notice 34, no diagnostic prose.
    expect(label.split(/\s+/)).toHaveLength(1);
  });

  describe("the pregame arms are PRESERVED, not collateral", () => {
    test("not started, countdown running → the countdown, unchanged", () => {
      expect(startBadgeLabel(false, "2h 14m")).toBe("Starts in 2h 14m");
    });

    test("not started, countdown not yet computed → 'Pregame', unchanged", () => {
      // The word keeps its one honest use: before kickoff, with no countdown
      // string to print. Deleting it outright would blank the badge here.
      expect(startBadgeLabel(false, "")).toBe("Pregame");
      expect(startBadgeLabel(false, null)).toBe("Pregame");
      expect(startBadgeLabel(false, undefined)).toBe("Pregame");
    });
  });

  describe("the badge and the suspended branch hand off with no gap", () => {
    test("specimen at +77m: NOT suspended, so the badge is what speaks", () => {
      // Both halves of the contract in one arm — if this row were suspended the
      // page would never call `startBadgeLabel`, and the assertion above would
      // be grading an unreachable branch.
      expect(hasNoReportedResult("scheduled", ISO, SPECIMEN_NOW)).toBe(false);
      expect(startBadgeLabel(true, "")).toBe("Started");
    });

    test("past the grace the OTHER branch takes it — 'Started' does not linger", () => {
      const wellPast = KICKOFF + UPCOMING_GRACE_MS + MINUTE;
      expect(hasNoReportedResult("scheduled", ISO, wellPast)).toBe(true);
    });

    test("every minute of the window is covered by exactly one of the two", () => {
      // The real guarantee: no minute after kickoff is both, and none is
      // neither. A gap here is #6031; an overlap is the widening it refuses.
      for (let m = 0; m <= 180; m += 5) {
        const now = KICKOFF + m * MINUTE;
        const suspended = hasNoReportedResult("scheduled", ISO, now);
        const badge = startBadgeLabel(true, "");
        expect(badge).toBe("Started");
        expect(suspended).toBe(m * MINUTE > UPCOMING_GRACE_MS);
      }
    });
  });

  describe("THE GRACE IS UNMOVED — this fix is the word only", () => {
    test("one minute inside the grace is still not 'no result reported'", () => {
      const inside = KICKOFF + UPCOMING_GRACE_MS - MINUTE;
      expect(startedWithoutResult("scheduled", ISO, inside)).toBe(false);
    });

    test("EXACTLY at the grace is still inside it (the predicate is strict `<`)", () => {
      // Stated because a boundary-inclusive rewrite is the quiet way to widen.
      const exact = KICKOFF + UPCOMING_GRACE_MS;
      expect(startedWithoutResult("scheduled", ISO, exact)).toBe(false);
    });

    test("a match twenty minutes in is NOT told its result is missing", () => {
      // The lie this fix was explicitly forbidden to trade for.
      expect(startedWithoutResult("scheduled", ISO, KICKOFF + 20 * MINUTE)).toBe(
        false,
      );
    });

    test("the grace is still two hours", () => {
      expect(UPCOMING_GRACE_MS).toBe(2 * 60 * 60 * 1000);
    });
  });
});
