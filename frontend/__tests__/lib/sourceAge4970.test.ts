/**
 * #4970 / D132 — THE AGE VOCABULARY, PINNED AT A FIXED INSTANT.
 *
 * Gotcha #44: a test anchor must not branch on the clock. Every case here
 * passes `NOW` explicitly, so "97 minutes reads as 1h ago" is asserted about
 * the arithmetic rather than about whenever the suite happened to run.
 *
 * The three cases that are the point of the module, rather than of the
 * formatting:
 *
 *   • an ABSENT stamp is `null`, never a word — the whole reason the models
 *     page can tell "we have never read this source" from "we read it a moment
 *     ago", which is the defect latency/339 refused to build into the card half;
 *   • an UNPARSEABLE stamp is `null` too — the private copy this replaced fell
 *     out of the bottom of its own comparisons as the literal "NaN d ago";
 *   • `sourceIsStale` is FALSE for an absent stamp, because an undatable source
 *     is not a stale one and the page must not claim it is.
 */
import {
  SOURCE_STALE_AFTER_MS,
  formatSourceAge,
  formatSourceStamp,
  sourceAgeMs,
  sourceIsStale,
} from "@/lib/sourceAge";

/** 2026-09-11T20:14:00Z — the instant the production specimen was read. */
const NOW = Date.parse("2026-09-11T20:14:00.000Z");
const ago = (ms: number) => new Date(NOW - ms).toISOString();

const MIN = 60 * 1000;
const HOUR = 60 * MIN;
const DAY = 24 * HOUR;

describe("formatSourceAge — the words BookmakerTable has always used", () => {
  it.each([
    [0, "just now"],
    [59 * 1000, "just now"],
    [1 * MIN, "1m ago"],
    [3 * MIN, "3m ago"],
    [59 * MIN, "59m ago"],
    [60 * MIN, "1h ago"],
    [23 * HOUR, "23h ago"],
    [24 * HOUR, "yesterday"],
    [47 * HOUR, "yesterday"],
    [2 * DAY, "2d ago"],
    [30 * DAY, "30d ago"],
  ])("%i ms ago reads %s", (ms, expected) => {
    expect(formatSourceAge(ago(ms), NOW)).toBe(expected);
  });

  it("prints the production specimen's two ends as different sentences", () => {
    // The whole ship in one assertion: on `/events/15310077/models` at 20:14Z,
    // Kalshi's number was 6 seconds old and ESPN's was 97 minutes old, and the
    // page said the same nothing about both.
    expect(formatSourceAge(ago(6 * 1000), NOW)).toBe("just now");
    expect(formatSourceAge(ago(97 * MIN), NOW)).toBe("1h ago");
  });

  it("rounds DOWN, so an age never flatters itself", () => {
    expect(formatSourceAge(ago(119 * MIN), NOW)).toBe("1h ago");
    expect(formatSourceAge(ago(2 * DAY + 23 * HOUR), NOW)).toBe("2d ago");
  });
});

describe("an absence is never a word", () => {
  it.each([null, undefined, "", "not a date", "yesterday"])(
    "%p yields null, not a relative age",
    (bad) => {
      expect(formatSourceAge(bad as string | null | undefined, NOW)).toBeNull();
      expect(sourceAgeMs(bad as string | null | undefined, NOW)).toBeNull();
      expect(formatSourceStamp(bad as string | null | undefined)).toBeNull();
    },
  );

  it("does not print 'NaN d ago' for an unparseable stamp", () => {
    // The literal regression in the private copy this module replaced: every
    // comparison against NaN is false, so it fell out of the bottom as
    // `${NaN}d ago`. `null` is the only value that is not a sentence about
    // recency, so assert that rather than the absence of a substring — a
    // `not.toContain` on `null` errors out and would never have caught this.
    const out = formatSourceAge("2026-13-45T99:99:99Z", NOW);
    expect(out).toBeNull();
    expect(String(out)).not.toContain("NaN");
  });

  it("treats an undatable source as NOT stale — the claim we cannot support", () => {
    expect(sourceIsStale(null, NOW)).toBe(false);
    expect(sourceIsStale(undefined, NOW)).toBe(false);
    expect(sourceIsStale("not a date", NOW)).toBe(false);
  });
});

describe("sourceIsStale — one threshold for both halves of the page", () => {
  it("is 30 minutes, the number BookmakerTable already averages on", () => {
    expect(SOURCE_STALE_AFTER_MS).toBe(30 * 60 * 1000);
  });

  it("is false at the threshold and true past it", () => {
    expect(sourceIsStale(ago(SOURCE_STALE_AFTER_MS), NOW)).toBe(false);
    expect(sourceIsStale(ago(SOURCE_STALE_AFTER_MS + 1), NOW)).toBe(true);
  });

  it("calls the specimen's ESPN stale and its Kalshi fresh", () => {
    expect(sourceIsStale(ago(97 * MIN), NOW)).toBe(true);
    expect(sourceIsStale(ago(39 * MIN), NOW)).toBe(true);
    expect(sourceIsStale(ago(6 * 1000), NOW)).toBe(false);
    expect(sourceIsStale(ago(2 * MIN), NOW)).toBe(false);
  });
});

describe("a future stamp cannot read as a negative age", () => {
  it("clamps to zero rather than printing '-3m ago'", () => {
    // A clock skew between the dyno and the reader's browser is the ordinary
    // cause, and "just now" is the honest reading of it.
    expect(formatSourceAge(new Date(NOW + 3 * MIN).toISOString(), NOW)).toBe(
      "just now",
    );
    expect(sourceAgeMs(new Date(NOW + 3 * MIN).toISOString(), NOW)).toBe(0);
  });
});
