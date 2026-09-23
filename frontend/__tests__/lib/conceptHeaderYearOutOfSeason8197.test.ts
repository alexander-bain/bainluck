// #8197 — A 2027 EVENT DATED "Sep 17 – Sep 19" READS AS THIS WEEK.
//
// Not a regression of #8139: #8139 is correct and live. Its producer half
// filled `/event/event:golf:ryder-cup`'s own window, which production served as
//
//     event.start_date = 2027-09-17T00:00:00+00:00
//     event.end_date   = 2027-09-19T00:00:00+00:00
//     next_edition     = null
//
// so `conceptHeaderDate` stopped taking its year-bearing fallback and started
// taking the own-window short-circuit, which prints through `eventDateRange` —
// no year. At 390px the header read `Sep 17 – Sep 19 · 3 markets tracked`
// directly beneath a `STARTS IN 359 DAYS` badge.
//
// The clock is ALWAYS passed explicitly here. A date test that reads the real
// clock passes in September and fails in January (gotcha #44); where the
// default-argument path is what is under test, the anchor is BUILT from the
// current year rather than compared against a literal.

import { conceptHeaderDate } from "@/lib/eventConceptDisplay";

/** The reader's clock in the filing: the day the frame was photographed. */
const SEP_2026 = new Date("2026-09-23T00:00:00Z");

const RYDER_START = "2027-09-17T00:00:00+00:00";
const RYDER_END = "2027-09-19T00:00:00+00:00";
const EDITION = { start: "2027-04-08", end: "2027-04-11" };

describe("#8197 — an out-of-year window states its year", () => {
  test("the filing's own specimen: the Ryder Cup header names 2027", () => {
    expect(conceptHeaderDate("upcoming", RYDER_START, RYDER_END, null, SEP_2026)).toBe(
      "September 17–19, 2027",
    );
  });

  test("the defect string itself is gone", () => {
    // The literal bytes lane1b photographed. Asserting the positive above and
    // the negative here means a future formatter change cannot quietly restore
    // the exact rendering this issue is about.
    const line = conceptHeaderDate("upcoming", RYDER_START, RYDER_END, null, SEP_2026);
    expect(line).not.toBe("Sep 17 – Sep 19");
    expect(line).toContain("2027");
  });

  test("a window in a PAST year names its year too", () => {
    // The hazard is symmetric: "Apr 9 – Apr 12" on a 2025 event reads as this
    // season just as wrongly as a 2027 one does.
    expect(
      conceptHeaderDate("settled", "2025-04-09", "2025-04-12", null, SEP_2026),
    ).toBe("April 9–12, 2025");
  });

  test("a window straddling New Year names both years", () => {
    // Half of it IS the current year, so an `every`-shaped test would call this
    // in-season and print "Dec 30 – Jan 2" — which names neither year on the
    // one window that most needs both.
    expect(
      conceptHeaderDate("upcoming", "2026-12-30", "2027-01-02", null, SEP_2026),
    ).toBe("December 30, 2026 – January 2, 2027");
  });
});

describe("#8197 — nothing that reads correctly today moves", () => {
  test("an in-season window keeps the compact grammar, unchanged", () => {
    expect(
      conceptHeaderDate("upcoming", "2026-09-17", "2026-09-19", null, SEP_2026),
    ).toBe("Sep 17 – Sep 19");
  });

  test("the settled Masters control is byte-identical", () => {
    // ux/1455's control page: settled, has its own window, AND declares a next
    // edition — it exercises the own-window short-circuit and the settled gate
    // in one shot. It is in-season, so it must not move.
    expect(
      conceptHeaderDate("settled", "2026-04-09", "2026-04-12", EDITION, SEP_2026),
    ).toBe("Apr 9 – Apr 12");
  });

  test("the fallback branch is untouched: no own window ⇒ the declared edition", () => {
    expect(conceptHeaderDate("upcoming", null, null, EDITION, SEP_2026)).toBe(
      "April 8–11, 2027",
    );
  });

  test("live and settled with no own window still print nothing", () => {
    expect(conceptHeaderDate("live", null, null, EDITION, SEP_2026)).toBeNull();
    expect(conceptHeaderDate("settled", null, null, EDITION, SEP_2026)).toBeNull();
  });

  test("no window and no edition is still honest-empty", () => {
    expect(conceptHeaderDate("upcoming", null, null, null, SEP_2026)).toBeNull();
  });
});

describe("#8197 — the edges the year rule must not break", () => {
  test("an end-only window still renders, and says Ends", () => {
    // `formatEditionWindow` needs a start and returns null without one, so the
    // year-bearing branch cannot express this window. The `?? own` fallback
    // keeps the header rendering rather than blanking it. KNOWN GAP, recorded
    // deliberately: an end-only out-of-year window still prints no year. It is
    // preferred to blanking the line, and no served concept has one today.
    expect(conceptHeaderDate("upcoming", null, RYDER_END, null, SEP_2026)).toBe(
      "Ends Sep 19",
    );
  });

  test("a start-only out-of-year window names its year", () => {
    expect(conceptHeaderDate("upcoming", RYDER_START, null, null, SEP_2026)).toBe(
      "September 17, 2027",
    );
  });

  test("the year comes from the WINDOW, not from the status", () => {
    // Every status takes the same branch — the rule is a property of the dates.
    for (const status of ["upcoming", "live", "settled"]) {
      expect(conceptHeaderDate(status, RYDER_START, RYDER_END, null, SEP_2026)).toBe(
        "September 17–19, 2027",
      );
    }
  });

  test("the default clock argument is the real one", () => {
    // Anchor BUILT from the current year, never compared to a literal, so this
    // asserts the default-parameter path in any month of any year.
    const y = new Date().getUTCFullYear();
    expect(conceptHeaderDate("upcoming", `${y}-06-01`, `${y}-06-03`, null)).toBe(
      "Jun 1 – Jun 3",
    );
    expect(conceptHeaderDate("upcoming", `${y + 1}-06-01`, `${y + 1}-06-03`, null)).toBe(
      `June 1–3, ${y + 1}`,
    );
  });
});
