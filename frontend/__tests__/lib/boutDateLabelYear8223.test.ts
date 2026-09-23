/**
 * #8223 — a UFC fight card must not date a 2027 bout "Thu, Jul 1".
 *
 * WHAT A READER SAW. On the default landing page on 2026-09-23, three UFC
 * concept cards rendered `Wed, Jun 30` (/event/ufc/27jul01), `Thu, Jul 1`
 * (/event/ufc/27jul02) and `Sat, Jul 10` (/event/ufc/27jul11). The year is in
 * the slug; it was in no label. A reader in September 2026 reads those as dates
 * that passed three months ago, on cards selling fights nine months away.
 *
 * ⚠️ EVERY `now` IN THIS FILE IS PINNED, AND THAT IS THE POINT, NOT HYGIENE.
 * #1093 ("combat card-concept tests fail near UTC midnight, red-blocking
 * deploys") and #3458 ("a calendar-pinned test fixture took CI red on every
 * branch at once") are this exact module and this exact class. A test here that
 * reads the real clock is a future red on somebody else's branch.
 *
 * ⚠️ WHAT THIS SUITE CANNOT SEE, STATED RATHER THAN IMPLIED. The frontend jest
 * gate runs `TZ=UTC`, so local time and UTC are the same clock inside it and no
 * assertion written here can distinguish `getFullYear` from `getUTCFullYear` by
 * the value it returns. That distinction is real and load-bearing — it is why
 * this fix does not copy #8197's `getUTCFullYear` line. So it is pinned the only
 * way a TZ-blind suite honestly can: by SELF-CONSISTENCY — whatever year the
 * label prints must be the year the label's own month and day belong to, on one
 * clock, whichever clock the runner is on. That assertion is true in every
 * timezone and false for a mismatched pair.
 */

import {
  boutDateLabel,
  conceptHeadlineBout,
} from "@/lib/eventConceptDisplay";
import type { FeedConceptData } from "@/lib/types";

// 2026-09-23, the day the defect was photographed on production.
const READER_NOW = new Date("2026-09-23T11:41:00Z");

describe("#8223 boutDateLabel states the year when the bout is not in the reader's year", () => {
  // The three cards that were live on the landing page, by their real slugs.
  it.each([
    ["/event/ufc/27jul01", "2027-07-01T02:00:00Z"],
    ["/event/ufc/27jul02", "2027-07-02T02:00:00Z"],
    ["/event/ufc/27jul11", "2027-07-11T02:00:00Z"],
  ])("%s names 2027", (_slug, when) => {
    const label = boutDateLabel(when, "en-US", READER_NOW);
    expect(label).toContain("2027");
  });

  it("a bout in the reader's own year is byte-identical to what shipped before", () => {
    // These two were on the same page as the three defects and were already
    // correct. The fix must not move them: an over-claim fixed by printing MORE
    // has an under-claim as its failure mode, and only a same-year control sees
    // it.
    //
    // The expectation is the PRE-FIX GRAMMAR ITSELF rather than a literal like
    // "Fri, Oct 2". A literal encodes the runner's timezone — the first cut of
    // this test asserted the production (US-local) strings and went red under
    // the suite's `TZ=UTC`, which is #3458 being re-acquired inside the guard
    // written to prevent it. This form is exact and true on every runner.
    const preFix = (when: string) =>
      new Date(when).toLocaleDateString("en-US", {
        weekday: "short",
        month: "short",
        day: "numeric",
      });

    for (const when of ["2026-10-03T02:00:00Z", "2026-12-27T02:00:00Z"]) {
      expect(boutDateLabel(when, "en-US", READER_NOW)).toBe(preFix(when));
    }
  });

  it("a same-year label carries no year at all, not a year that happens to match", () => {
    const label = boutDateLabel("2026-10-03T02:00:00Z", "en-US", READER_NOW);
    expect(label).not.toMatch(/\d{4}/);
  });

  it("a bout in a PAST year is named too — 'last July' is as wrong as 'next July'", () => {
    const label = boutDateLabel("2025-07-02T02:00:00Z", "en-US", READER_NOW);
    expect(label).toContain("2025");
  });

  it("still returns null for the cases that had no date to print", () => {
    expect(boutDateLabel(null, "en-US", READER_NOW)).toBeNull();
    expect(boutDateLabel(undefined, "en-US", READER_NOW)).toBeNull();
    expect(boutDateLabel("", "en-US", READER_NOW)).toBeNull();
    expect(boutDateLabel("not a date", "en-US", READER_NOW)).toBeNull();
  });

  /**
   * THE INVARIANT THE TZ-BLIND SUITE CAN STILL PIN (see the file header).
   *
   * Read the year out of the label, then read the month/day out of the label,
   * and require they describe ONE instant on ONE clock. A fix that compared the
   * year in UTC while printing the day locally breaks this on any runner whose
   * offset moves the bout across a year boundary, and it is trivially true for
   * the correct fix on every runner.
   */
  it("the year the label prints belongs to the day the label prints", () => {
    const whens = [
      "2027-01-01T02:00:00Z", // the New Year specimen: UTC says 2027, most of
      "2026-12-31T23:30:00Z", // the Americas say Dec 31 / 2026.
      "2027-07-02T02:00:00Z",
      "2025-07-02T02:00:00Z",
    ];
    for (const when of whens) {
      const label = boutDateLabel(when, "en-US", READER_NOW);
      expect(label).not.toBeNull();
      const printedYear = label!.match(/\b(\d{4})\b/)?.[1];
      // The clock the label actually rendered on.
      const renderedYear = String(new Date(when).getFullYear());
      if (printedYear) {
        expect(printedYear).toBe(renderedYear);
      } else {
        // No year printed is itself a claim: "this is the reader's year".
        expect(renderedYear).toBe(String(READER_NOW.getFullYear()));
      }
    }
  });
});

/**
 * THE LOCAL-vs-UTC HAZARD, AND WHY THERE IS NO TEST FOR IT HERE.
 *
 * Reported rather than quietly omitted. The dangerous mistake in this branch is
 * comparing the year on a different clock than the label renders on — a UTC
 * comparison dates `2026-01-01T02:00:00Z` (which renders `Wed, Dec 31` across
 * the Americas, i.e. December 2025) as the reader's own year and prints no year
 * at all for a fight eleven months gone.
 *
 * It is NOT guarded, because in this gate it cannot be: the frontend jest suite
 * runs `TZ=UTC`, where local and UTC are one clock and the correct and incorrect
 * spellings return identical values for every input. The mutation run confirmed
 * it empirically — `getFullYear` → `getUTCFullYear` SURVIVED the whole suite.
 *
 * Pinning `process.env.TZ` in a `beforeAll` does not rescue it. Node does honour
 * a runtime TZ change (checked directly), but `Intl` has already resolved and
 * cached the zone by the time a hook runs inside jest, so the pin silently does
 * nothing and the test passes for the wrong reason — it was written, it reported
 * "Thu, Jan 1" where Los Angeles would say "Wed, Dec 31", and it was deleted
 * rather than shipped as a guard that only looks like one.
 *
 * So the hazard is handled where it can be: `boutDateLabel` asks the SAME
 * formatter for the year that prints the day, which makes the two clocks the
 * same object rather than two agreeing choices. The assertion below pins that
 * property — the one part of it this gate can see.
 */
describe("#8223 the year comes from the label's own formatter", () => {
  it("the decision matches a same-formatter oracle on every specimen", () => {
    // The oracle is spelled the way the fix is spelled — from the rendered year,
    // not from a getter. It agrees with the implementation in THIS timezone and
    // in every other one, which a getter-based oracle would not.
    const renderedYear = (d: Date) =>
      d.toLocaleDateString("en-US", { year: "numeric" });

    for (const when of [
      "2027-07-02T02:00:00Z",
      "2026-10-03T02:00:00Z",
      "2025-07-02T02:00:00Z",
      "2027-01-01T02:00:00Z",
      "2026-01-01T02:00:00Z",
      "2026-12-31T23:30:00Z",
    ]) {
      const label = boutDateLabel(when, "en-US", READER_NOW)!;
      const shouldName =
        renderedYear(new Date(when)) !== renderedYear(READER_NOW);
      expect(/\b\d{4}\b/.test(label)).toBe(shouldName);
    }
  });
});

describe("#8223 the card wrapper uses the same clock", () => {
  function conceptWith(commence: string): FeedConceptData {
    return {
      headline_bout: {
        commence_time: commence,
        competitors: [
          { name: "Manel Kape", probability: 0.5 },
          { name: "Joshua Van", probability: 0.5 },
        ],
      },
    } as unknown as FeedConceptData;
  }

  it("conceptHeadlineBout threads `now` through to the label", () => {
    const bout = conceptHeadlineBout(
      conceptWith("2027-07-02T02:00:00Z"),
      "en-US",
      READER_NOW,
    );
    expect(bout).not.toBeNull();
    // Asserted against the STRING, not against another call to boutDateLabel —
    // a self-referential expectation passes just as happily when both sides are
    // wrong, which is why it could not have caught this defect.
    expect(bout!.dateLabel).toContain("2027");
  });

  /**
   * THE SPECIMEN THAT CAN TELL THE TWO CLOCKS APART.
   *
   * The test above cannot: its bout is in 2027 and the ambient clock is 2026, so
   * a wrapper that DROPS `now` and falls back to `new Date()` still prints
   * "2027" and still passes. Measured — deleting `now,` from the call survived
   * the suite.
   *
   * Invert it. Put the bout on TODAY, whenever today is, and pin the reader's
   * clock three years out. Threading `now` then means "these years differ, print
   * one"; ignoring it means "the bout is in my own year, print nothing". The two
   * answers are opposite, so only the threaded one passes.
   *
   * Both dates are RELATIVE to the run, never literals: #3458 is a calendar-
   * pinned fixture that took CI red on every branch at once, and a hard-coded
   * year here would become that the moment the wall clock reached it.
   */
  it("the wrapper reads the `now` it is GIVEN, not the ambient clock", () => {
    const today = new Date();
    const readerThreeYearsOn = new Date(today);
    readerThreeYearsOn.setFullYear(today.getFullYear() + 3);

    const bout = conceptHeadlineBout(
      conceptWith(today.toISOString()),
      "en-US",
      readerThreeYearsOn,
    );
    expect(bout).not.toBeNull();
    // The bout is in the ambient year, so an unthreaded wrapper prints no year.
    expect(bout!.dateLabel).toContain(String(today.getFullYear()));
  });
});
