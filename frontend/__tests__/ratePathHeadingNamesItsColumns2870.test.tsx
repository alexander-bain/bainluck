/**
 * #2870 (heading half) — the rate-path card stops naming a year it is not showing.
 *
 * ═══ WHAT PRODUCTION SERVED ═══
 *
 * `https://bainluck.com/economics`, filed 2026-09-03 and re-measured verbatim
 * on 2026-09-14, eleven days later:
 *
 *     2026 rate path
 *     Market-implied probability of each Fed funds bracket
 *
 *               Jan                 Mar                 Apr
 *         Jan 2027 meeting    Mar 2027 meeting    Apr 2027 meeting
 *
 * The heading said 2026; every column said 2027. The card contradicted itself
 * on one screen and needed no external control to prove it, because
 * `app/economics/page.tsx` carried the literal string `2026 rate path` with
 * nothing binding it to the data underneath.
 *
 * ═══ WHY A RENAME WOULD NOT HAVE BEEN A FIX ═══
 *
 * Editing the literal to `2027` would have been correct for about a fortnight.
 * The backend half of #2870 restores the three hidden 2026 meetings, so the
 * set legitimately spans two calendar years now and will span different ones
 * next quarter. The only durable shape is the one #2674 used on this same
 * page: derive the label from the data that is rendered, so the two cannot
 * disagree by construction.
 *
 * ═══ WHY THESE ASSERTIONS ARE SPLIT IN TWO ═══
 *
 * The unit block below pins the derivation over inputs production does not
 * currently produce (an empty card, an unparseable title, a century straddle)
 * — cheap to state, impossible to LOOK at.
 *
 * `TestThePageUsesIt` is the one that stops the unit block being decoration.
 * A perfect pure function is worth nothing if the page still renders its own
 * literal, and that is exactly the defect being fixed — so the source of
 * `page.tsx` is read and asserted against, and the parser fails loudly if it
 * matches nothing rather than passing on a file it could not find.
 */

import fs from "fs";
import path from "path";

import { meetingYear, ratePathHeading } from "@/lib/fedRatePath";

const PAGE = path.join(process.cwd(), "app", "economics", "page.tsx");

// The three columns production served on 2026-09-14, plus the three the
// backend half restores. `sort_key` is YYYYMM, as `routes/economics.py` builds it.
const SERVED_2026_09_14 = [
  { sort_key: 202701, date: "Jan 2027 meeting" },
  { sort_key: 202703, date: "Mar 2027 meeting" },
  { sort_key: 202704, date: "Apr 2027 meeting" },
];

const RESTORED = [
  { sort_key: 202609, date: "Sep 2026 meeting" },
  { sort_key: 202610, date: "Oct 2026 meeting" },
  { sort_key: 202612, date: "Dec 2026 meeting" },
  ...SERVED_2026_09_14,
];

describe("#2870 the heading is derived from the columns", () => {
  it("does not reproduce the filed defect", () => {
    // The literal said 2026 over exactly this input.
    expect(ratePathHeading(SERVED_2026_09_14)).toBe("2027 rate path");
  });

  it("names both years once the 2026 meetings are restored", () => {
    expect(ratePathHeading(RESTORED)).toBe("2026–27 rate path");
  });

  it("uses an en dash, not a hyphen", () => {
    // Design system: ranges are en-dashed. Asserted because a hyphen is the
    // easy thing to type and reads as a compound word, not a span.
    expect(ratePathHeading(RESTORED)).toContain("–");
    expect(ratePathHeading(RESTORED)).not.toContain("-");
  });

  it("claims no year at all when there are no columns", () => {
    // The heading renders OUTSIDE the heatmap, so it is still on screen when
    // the card is empty. A year printed over nothing is this same defect.
    expect(ratePathHeading([])).toBe("Rate path");
    expect(ratePathHeading(null)).toBe("Rate path");
    expect(ratePathHeading(undefined)).toBe("Rate path");
  });
});

describe("#2870 the derivation survives the inputs the backend can actually emit", () => {
  it("treats sort_key 0 as an unknown year rather than year zero", () => {
    // `routes/economics.py` sets sort_key = 0 when the market title carried no
    // parseable month+year. 0/100 is 0 — a plausible-looking number that would
    // render "0–2027 rate path". This is the trap in the whole file.
    expect(meetingYear({ sort_key: 0, date: "meeting" })).toBeNull();
    expect(
      ratePathHeading([{ sort_key: 0, date: "meeting" }, ...SERVED_2026_09_14]),
    ).toBe("2027 rate path");
  });

  it("falls back to the date string when sort_key is unusable", () => {
    expect(meetingYear({ sort_key: 0, date: "Sep 2026 meeting" })).toBe(2026);
    expect(meetingYear({ sort_key: null, date: "Sep 2026 meeting" })).toBe(2026);
    expect(meetingYear({ date: "Sep 2026 meeting" })).toBe(2026);
  });

  it("reads a single column as a single year", () => {
    expect(ratePathHeading([{ sort_key: 202609, date: "Sep 2026 meeting" }])).toBe(
      "2026 rate path",
    );
  });

  it("is insensitive to the order the columns arrive in", () => {
    const reversed = [...RESTORED].reverse();
    expect(ratePathHeading(reversed)).toBe(ratePathHeading(RESTORED));
  });

  it("spells out a second year in a different century", () => {
    expect(
      ratePathHeading([
        { sort_key: 209911, date: "Nov 2099 meeting" },
        { sort_key: 210001, date: "Jan 2100 meeting" },
      ]),
    ).toBe("2099–2100 rate path");
  });

  it("returns a bare heading when no column carries a readable year", () => {
    expect(ratePathHeading([{ sort_key: 0, date: "" }])).toBe("Rate path");
  });
});

describe("#2870 the page actually uses it", () => {
  const source = fs.readFileSync(PAGE, "utf8");

  it("reads a page source that is really there", () => {
    // Non-vacuity: a source-scanning guard that silently matches nothing is
    // worse than no guard.
    expect(source.length).toBeGreaterThan(1000);
    expect(source).toContain("FedHeatmap");
  });

  it("no longer carries the hardcoded heading", () => {
    expect(source).not.toContain("2026 rate path");
  });

  it("carries no hardcoded `NNNN rate path` literal of any year", () => {
    // The regression this exists to catch is not "someone restores 2026" —
    // it is "someone edits it to 2027" and reintroduces the class.
    expect(source).not.toMatch(/["'`]\s*20\d{2}[^"'`]*rate path/i);
  });

  it("calls the derivation with the same array it renders", () => {
    // The binding. A heading derived from a DIFFERENT array than the heatmap
    // draws would be the original defect wearing a function call.
    expect(source).toMatch(/ratePathHeading\(\s*t\.fed\.fomc_meetings\s*\)/);
    expect(source).toMatch(/<FedHeatmap\s+meetings=\{t\.fed\.fomc_meetings\s*\|\|\s*\[\]\}/);
  });

  it("imports the derivation from the module these tests exercise", () => {
    expect(source).toMatch(/import\s*\{[^}]*ratePathHeading[^}]*\}\s*from\s*["']@\/lib\/fedRatePath["']/);
  });
});
