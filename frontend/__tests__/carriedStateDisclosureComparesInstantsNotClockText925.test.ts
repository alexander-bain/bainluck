/**
 * #925 — THE CARRIED-STATE DISCLOSURE COMPARES INSTANTS, NOT THE TEXT IT PRINTS.
 *
 * Codex found this against the delivered candidate and supplied the correction
 * (`CODEX-0007-tooltip-date-correction.patch`, 2026-09-23). The candidate decided
 * "is this carried state old?" by formatting both instants as `h:mm a` and
 * comparing the STRINGS, so **yesterday 8:00 PM and today 8:00 PM compared equal**
 * and the tooltip disclosed nothing at all — silently, on the one case the
 * disclosure exists for. A formatted clock is a lossy projection of an instant;
 * using it as an identity is the same defect #8135 fixed on the futures axis the
 * same morning, in a different file.
 *
 * The correction compares actual minute buckets and prints the DATE when the
 * observation falls on another calendar day.
 *
 * ── WHY THIS DOES NOT ASSERT A LITERAL DATE STRING ──
 *
 * `jest.config.js:13` pins `process.env.TZ = 'UTC'`, and `carriedStateDisclosure`
 * formats in whatever zone it runs in — the READER's, in production. So an
 * assertion like `toContain("Sep 22")` is true only under the pin and says
 * nothing about the rule a reader meets. Asserting the SHAPE instead — a date
 * token is present / absent — with instants chosen so the underlying fact holds
 * in EVERY zone makes the timezone irrelevant rather than merely pinned:
 *
 *  - two instants exactly 24h apart are on different calendar days in every
 *    fixed-offset zone, so the cross-day arm cannot become a same-day arm;
 *  - two instants ten minutes apart around 08:00Z are on the SAME calendar day
 *    in every zone from UTC−11 to UTC+14 (local 21:00 the previous day through
 *    22:00), so the same-day arm cannot become a cross-day one.
 */

import { carriedStateDisclosure } from "@/lib/chartGameState";

/** `Sep 22, 8:00 PM` — a month-and-day prefix, whatever the month happens to be. */
const DATE_TOKEN = /\b[A-Z][a-z]{2} \d{1,2}, \d{1,2}:\d{2} [AP]M\b/;
/** `8:00 PM` with nothing before it. */
const BARE_CLOCK = /^\w+(?: and \w+)? as of \d{1,2}:\d{2} [AP]M$/;

const POINT = "2026-09-23T08:00:00Z";
/** Exactly 24h earlier: another calendar day in every zone. */
const A_DAY_EARLIER = "2026-09-22T08:00:00Z";
/** Ten minutes earlier: the same calendar day in every zone. */
const TEN_MIN_EARLIER = "2026-09-23T07:50:00Z";

function carriedClock(observedAt: string, timestamp = POINT) {
  return carriedStateDisclosure({
    timestamp,
    period: "1",
    clock: "7:41",
    hasScore: false,
    clockApprox: true,
    clockObservedAt: observedAt,
  });
}

describe("#925 — a clock carried from another day says so", () => {
  it("discloses the DAY when the observation is 24h behind the point", () => {
    // RED on the delivered candidate: `format(…, "h:mm a")` made these two
    // instants the same string, the function returned null, and the tooltip
    // printed nothing.
    const d = carriedClock(A_DAY_EARLIER);
    expect(d).not.toBeNull();
    expect(d?.text).toMatch(DATE_TOKEN);
    expect(d?.carried).toBe("clock");
  });

  it("CONTROL — ten minutes behind, same day, keeps the bare clock", () => {
    // Without this, "print the date every time" passes the arm above and puts a
    // date on every in-game tooltip in the app.
    const d = carriedClock(TEN_MIN_EARLIER);
    expect(d).not.toBeNull();
    expect(d?.text).toMatch(BARE_CLOCK);
    expect(d?.text).not.toMatch(DATE_TOKEN);
  });

  it("CONTROL — the same actual minute is not a carry, and still discloses nothing", () => {
    // The disclosure's whole point is age. Two readings inside one minute are
    // the same reading; this is the arm that stops the fix becoming "always
    // disclose".
    expect(carriedClock("2026-09-23T08:00:10Z", "2026-09-23T08:00:50Z")).toBeNull();
  });

  it("is decided by the INSTANT, so the same wall clock is not the same reading", () => {
    // States the defect as a property rather than as a case: two observations
    // that print identically must not be treated as one. If this ever passes
    // with a string comparison restored, the two arms above are the reason why.
    const sameWallClock = carriedClock(A_DAY_EARLIER);
    const sameMinute = carriedClock("2026-09-23T08:00:30Z");
    expect(sameWallClock).not.toBeNull();
    expect(sameMinute).toBeNull();
  });
});
