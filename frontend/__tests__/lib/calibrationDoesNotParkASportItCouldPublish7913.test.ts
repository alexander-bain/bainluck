/**
 * #7913 — the accuracy page must not park a sport it has already earned a curve for.
 *
 * ## The defect this pins
 *
 * The niche card tells the reader that 42 categories "don't have enough resolved
 * outcomes yet for a curve we'd stand behind", and promises "the moment one
 * crosses the bar it appears above automatically". Measured on production
 * 2026-09-22 01:17Z, four of those chips were not waiting for anything:
 *
 *     NCAA Lacrosse  829  |  PLL  530  |  Lacrosse  268   = 1,627, over the bar
 *     MLB              3                                  baseball, published at 129,771
 *
 * `normalizeCat` rolls a compound key up only when its BASE segment is a key in
 * `DISPLAY_NAMES`. Every comparable sport is in that map, which is why none of
 * them fragments — seven basketball keys become one Basketball row. Lacrosse was
 * not, so its three keys were each measured against the 1,000 bar alone.
 *
 * ## Why this is a class guard and not four pinned strings
 *
 * The pinned labels below would pass if someone hard-coded four exceptions. The
 * load-bearing test is `no sport is parked in fragments that clear the bar`,
 * which is computed from the payload's OWN key structure and knows nothing about
 * which sports we happen to have mapped. It fails on any future sport that
 * fragments the same way, which is the actual failure mode: the map is edited by
 * hand and the payload grows on its own.
 *
 * ## The fixture is a dated snapshot, and drift is safe
 *
 * Counts are the live payload of 2026-09-22 (bank `generated_at` 2026-09-15).
 * Same discipline as `calibrationCategories.test.ts`: drift costs coverage of the
 * named rows, never the property, which is asserted over whatever is here.
 */

import {
  normalizeCat,
  categoryLabel,
  DISPLAY_NAMES,
} from "@/lib/calibrationCategories";

/** The publish bar the payload states (`min_category_outcomes`). */
const PUBLISH_BAR = 1000;

/**
 * Resolved-outcome counts per RAW payload category, live 2026-09-22 01:17Z.
 *
 * Only the rows this test reasons about: the fragmented sport, the bare league
 * acronym, their published parents, and the three near-misses that must NOT be
 * folded (see the scope note in #7913).
 */
const OUTCOMES_20260922: Readonly<Record<string, number>> = {
  // the fragmented sport — three keys, one game
  lacrosse: 268,
  lacrosse_ncaa: 829,
  lacrosse_pll: 530,
  // the bare league acronym and the prefixed spelling that already folded
  mlb: 3,
  baseball_mlb: 33011,
  baseball: 140893,
  // deliberately left fragmented — folding these would be wrong (see below)
  aussierules: 109,
  aussierules_afl: 1211,
  rugby: 344,
  rugbyleague_nrl: 1219,
  uncategorized: 113,
  other: 2591,
};

describe("#7913 — a sport is measured against the publish bar once, not once per league", () => {
  it("folds every spelling of the fragmented sport onto one published key", () => {
    const keys = ["lacrosse", "lacrosse_ncaa", "lacrosse_pll"];
    const folded = new Set(keys.map(normalizeCat));

    // One destination, not three. This is the whole defect.
    expect(folded.size).toBe(1);

    const [dest] = [...folded];
    const total = keys.reduce((s, k) => s + OUTCOMES_20260922[k], 0);
    expect(total).toBe(1627);
    // The fold is only worth anything if it actually crosses the bar.
    expect(total).toBeGreaterThanOrEqual(PUBLISH_BAR);
    // ...and every fragment alone does not, which is why it was parked.
    for (const k of keys) {
      expect(OUTCOMES_20260922[k]).toBeLessThan(PUBLISH_BAR);
    }
    // The published row needs a name a reader would write.
    expect(categoryLabel(dest)).toBe("Lacrosse");
  });

  it("folds a bare league acronym onto the sport its prefixed spelling already uses", () => {
    // The prefixed spelling has folded since before this issue; the bare one is
    // the straggler, and both must land in the same place or the 3 outcomes stay
    // parked beside a parent carrying six figures.
    expect(normalizeCat("mlb")).toBe(normalizeCat("baseball_mlb"));
    expect(normalizeCat("mlb")).toBe("baseball");
    expect(OUTCOMES_20260922["baseball"]).toBeGreaterThanOrEqual(PUBLISH_BAR);
  });

  /**
   * THE CLASS. Group the parked keys by the sport base they would fold onto if
   * the base were mapped, and assert no such group clears the bar while still
   * being parked. Derived from key structure and the dated counts — it does not
   * consult the map it is guarding, so it cannot pass by agreeing with itself.
   */
  it("parks no group of same-sport fragments that together clear the bar", () => {
    const parkedTotals = new Map<string, number>();
    for (const [key, n] of Object.entries(OUTCOMES_20260922)) {
      const normalized = normalizeCat(key);
      // A key that folds onto a destination already over the bar is published,
      // not parked — those are exactly the chips #7325 removed.
      const destTotal = Object.entries(OUTCOMES_20260922)
        .filter(([k]) => normalizeCat(k) === normalized)
        .reduce((s, [, v]) => s + v, 0);
      if (destTotal >= PUBLISH_BAR) continue;
      // Still parked. Attribute it to its sport base.
      const base = key.split("_")[0];
      parkedTotals.set(base, (parkedTotals.get(base) ?? 0) + n);
    }

    const offenders = [...parkedTotals.entries()].filter(
      ([, n]) => n >= PUBLISH_BAR
    );
    expect(offenders).toEqual([]);
  });

  /**
   * The scope note, pinned so a later edit does not quietly widen the fix.
   *
   * These three look like the same defect and are not. Folding the bare Aussie
   * rules key onto its league row is the #7532 trap recorded in
   * `__tests__/ios/calibrationCategoryLabelParity7722.test.ts`: a parent key in
   * that map re-groups the buckets the table counts and collapses AFLW onto
   * AFL's label. Lacrosse was safe because its fold target is the SPORT.
   */
  it("leaves the three near-misses alone, each for its own reason", () => {
    // Rugby union and rugby league are different sports.
    expect(normalizeCat("rugby")).not.toBe(normalizeCat("rugbyleague_nrl"));
    // The league keeps its own published row; the bare sport key stays parked.
    expect(normalizeCat("aussierules_afl")).toBe("aussierules_afl");
    expect(normalizeCat("aussierules")).not.toBe("aussierules_afl");
    // "Classified as other" and "never classified" are different facts.
    expect(normalizeCat("uncategorized")).not.toBe(normalizeCat("other"));

    // The #7532 trap itself: a base entry here would collapse AFLW onto AFL.
    expect(DISPLAY_NAMES["aussierules"]).toBeUndefined();
    expect(DISPLAY_NAMES["rugbyleague"]).toBeUndefined();
  });
});
