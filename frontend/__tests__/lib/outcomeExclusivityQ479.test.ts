// lane1-Q479 — the predicate contract for TOP-PRODUCT-DEFECTS item 13.
//
// The page-level proof lives in
// `__tests__/components/futuresDetailIndependentOutcomesQ479.test.tsx`; this file
// pins the rule itself, and in particular the ASYMMETRY that makes it safe:
// `futures_markets.mutually_exclusive` has ORM `default=True`, so `true` is what
// an unwritten row says and `false` is what a source had to write.

import {
  INDEPENDENT_OUTCOMES_NOTE_OPEN,
  INDEPENDENT_OUTCOMES_NOTE_SETTLED,
  MIN_OUTCOMES_FOR_INDEPENDENCE_NOTE,
  independentOutcomesNote,
  outcomesArePricedIndependently,
} from "@/lib/outcomeExclusivity";

describe("only a POSITIVE denial counts as evidence", () => {
  test("false — the source overwrote the default, so we have a fact", () => {
    expect(outcomesArePricedIndependently(false, 8)).toBe(true);
  });

  test("true is NOT evidence — it is the column default", () => {
    // This is the whole reason the predicate is `=== false` and not `!== true`.
    // precompute_calibration.py's Rung 4 (Queue 299) stopped accepting the same
    // flag as proof of a partition for the same reason; nothing here reinstates
    // it in the other direction either.
    expect(outcomesArePricedIndependently(true, 8)).toBe(false);
  });

  test("absent is silence, not the opposite claim", () => {
    expect(outcomesArePricedIndependently(undefined, 8)).toBe(false);
    expect(outcomesArePricedIndependently(null, 8)).toBe(false);
  });

  test("a truthy/falsy near-miss does not slip through", () => {
    // Guards against a future refactor to `!mutuallyExclusive`, which would
    // print the note on every payload that simply omits the field.
    expect(outcomesArePricedIndependently(0 as unknown as boolean, 8)).toBe(false);
    expect(outcomesArePricedIndependently("" as unknown as boolean, 8)).toBe(false);
  });
});

describe("the outcome-count floor", () => {
  test("a two-sided market is a duel whatever the flag says", () => {
    expect(outcomesArePricedIndependently(false, 2)).toBe(false);
    expect(outcomesArePricedIndependently(false, 1)).toBe(false);
    expect(outcomesArePricedIndependently(false, 0)).toBe(false);
  });

  test("the floor is exactly three, inclusive", () => {
    expect(MIN_OUTCOMES_FOR_INDEPENDENCE_NOTE).toBe(3);
    expect(outcomesArePricedIndependently(false, 3)).toBe(true);
  });
});

describe("both renderings are enumerated, because the copy changes with state", () => {
  test("an open bundle speaks in the present", () => {
    expect(independentOutcomesNote(false, 8, false)).toBe(
      INDEPENDENT_OUTCOMES_NOTE_OPEN
    );
    expect(INDEPENDENT_OUTCOMES_NOTE_OPEN).toContain("can happen");
  });

  test("a settled bundle speaks in the past", () => {
    expect(independentOutcomesNote(false, 8, true)).toBe(
      INDEPENDENT_OUTCOMES_NOTE_SETTLED
    );
    expect(INDEPENDENT_OUTCOMES_NOTE_SETTLED).toContain("could happen");
    expect(INDEPENDENT_OUTCOMES_NOTE_SETTLED).not.toContain("is priced");
  });

  test("the two are actually different strings", () => {
    // A settled card claiming the present tense is the HISTORY_CLAIM class this
    // board has blocked on repeatedly; a copy-paste that made these identical
    // would sail past both tests above.
    expect(INDEPENDENT_OUTCOMES_NOTE_OPEN).not.toBe(INDEPENDENT_OUTCOMES_NOTE_SETTLED);
  });

  test("no note is null, never an empty string", () => {
    expect(independentOutcomesNote(true, 8, false)).toBeNull();
    expect(independentOutcomesNote(undefined, 8, false)).toBeNull();
    expect(independentOutcomesNote(false, 2, false)).toBeNull();
  });
});

describe("the note never asserts a number it cannot support", () => {
  for (const note of [
    INDEPENDENT_OUTCOMES_NOTE_OPEN,
    INDEPENDENT_OUTCOMES_NOTE_SETTLED,
  ]) {
    test(`"${note.slice(0, 24)}…" states the shape, not a corrected total`, () => {
      // The fix is emphatically not a renormalisation, so the copy must not
      // imply one ("should add up to", "adjusted", "normalised").
      expect(note).toMatch(/don't add up to 100%/);
      expect(note.toLowerCase()).not.toContain("normal");
      expect(note.toLowerCase()).not.toContain("adjust");
      expect(note.toLowerCase()).not.toContain("should add");
    });
  }
});
