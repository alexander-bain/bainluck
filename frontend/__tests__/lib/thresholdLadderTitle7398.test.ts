// #7398 — A SCOPE KEY IS NEVER A HEADING.
//
// `threshold_groups` is keyed by a grouping identifier. Production 2026-09-20
// served exactly these keys for the three markets in the filing:
//
//     /futures/60653756  '# or below'  (20 rungs)  Treasury 30Y yield
//     /futures/60775290  'above #'     ( 6 rungs)  Strait of Hormuz
//     /futures/59699795  'above #k'    ( 8 rungs)  album equivalent units
//
// and the page printed the key. This pins the rule that replaced it, one test
// per clause, so a mutant that deletes any single clause reddens something.

import {
  isThresholdScopeKey,
  thresholdLadderTitle,
} from "@/lib/futuresLadder";

const TREASURY = "How low will the 30Y US Treasury yield get by Sep 30, 2026?";

describe("isThresholdScopeKey", () => {
  test.each(["# or below", "above #", "above #k", "group:kalshi:KX30YRDIRLM-26SEP30L", "GROUP:x"])(
    "%s is a scope key",
    (key) => {
      expect(isThresholdScopeKey(key)).toBe(true);
    },
  );

  test.each(["", "   ", null, undefined])("%s (empty) is treated as a scope key", (key) => {
    // Nothing to print is the same answer as a key: no heading.
    expect(isThresholdScopeKey(key)).toBe(true);
  });

  test.each([TREASURY, "Peak traffic through the Strait of Hormuz? (9/14 - 9/20)", "Grouped rounds"])(
    "%s is prose, not a key",
    (title) => {
      // "Grouped rounds" guards the prefix test against matching mid-word or on
      // the bare word "group": only the `group:` scope prefix counts.
      expect(isThresholdScopeKey(title)).toBe(false);
    },
  );
});

describe("thresholdLadderTitle", () => {
  test("🔴 the live defect: the Treasury ladder no longer prints '# or below'", () => {
    expect(thresholdLadderTitle("# or below", TREASURY, TREASURY)).toBeUndefined();
  });

  test("🔴 the H1 echo is dropped even when the key itself is prose", () => {
    // Without this clause a readable stem equal to the page's own question
    // would be repeated in small caps directly above its own rungs.
    expect(thresholdLadderTitle(TREASURY, "something else", ` ${TREASURY.toUpperCase()} `))
      .toBeUndefined();
  });

  test("a group_title that says something the H1 does not IS the heading", () => {
    // The cross-market case: several markets under one event. Dropping this
    // clause would leave every multi-market ladder unlabelled.
    expect(
      thresholdLadderTitle("above #", "US Open 2026 — total aces", "Will Alcaraz hit 30+ aces?"),
    ).toBe("US Open 2026 — total aces");
  });

  test("a readable stem is kept when there is no group_title to prefer", () => {
    expect(thresholdLadderTitle("Jayson Tatum: points", "", "Celtics vs Knicks")).toBe(
      "Jayson Tatum: points",
    );
  });

  test("🔴 a group_title that is itself a scope key is refused too", () => {
    // The rule is about what we PRINT, not about which field it came from.
    expect(thresholdLadderTitle("group:kalshi:KXABC", "above #", "Some question?")).toBeUndefined();
  });

  test("no group_title and a scope key leaves the ladder titleless", () => {
    expect(thresholdLadderTitle("above #", null, "Some question?")).toBeUndefined();
    expect(thresholdLadderTitle("above #", undefined, undefined)).toBeUndefined();
  });

  test("a surviving heading is served verbatim, trimmed — never re-cased or re-worded", () => {
    expect(thresholdLadderTitle("above #", "  Peak traffic (9/14 - 9/20)  ", "Other")).toBe(
      "Peak traffic (9/14 - 9/20)",
    );
  });
});
