// UX-P075 item (e) — the category label can never be a raw payload key.
//
// The staged item was one word ("label casing: Table Tennis"). The measured
// defect was a MECHANISM: every call site was `DISPLAY_NAMES[c] || c`, whose
// fallback is the database identifier, so a category renders correctly until it
// grows past the page's 1,000-outcome floor without a map entry and then prints
// `table_tennis` at a reader. Nothing on our side changes when that fires.
//
// So this suite asserts the mechanism is gone, not just that one label is right.
// The named case is pinned first because Alex asked for it by name; the class
// assertion below it is the part that stops the next one.

import {
  DISPLAY_NAMES,
  categoryLabel,
  normalizeCat,
} from "@/lib/calibrationCategories";

// The fifteen categories `/api/calibration` would render, measured on the LIVE
// payload 2026-08-14, after `normalizeCat` and after the page's 1,000-outcome
// floor, in the order the page sorts them.
//
// NOT read from `calibrationProdFixture`, and that is deliberate: that fixture
// pre-sums the category dimension away and says so in its own header — *"this
// fixture CANNOT prove anything about the per-category rollup"*. Grading a
// category test on it would have produced fifteen passes over a single row
// labelled `agg`, which is exactly the vacuous-guard shape this lane keeps
// finding. (It did, on the first run of this file.)
//
// A dated snapshot, not a live read. If the real category set drifts this list
// goes stale — but the class assertion below it ("an unknown key is prettified")
// holds for anything, so a stale list costs coverage of the named rows, never
// the guarantee.
const RENDERED_CATEGORIES_2026_08_14 = [
  "baseball", "basketball", "soccer", "tennis", "hockey",
  "economics", "weather", "esports", "golf", "table_tennis",
  "politics", "entertainment", "football", "motorsports", "mma",
] as const;

describe("the named case — Alex, 2026-08-13", () => {
  test("table_tennis renders as Table Tennis", () => {
    expect(categoryLabel("table_tennis")).toBe("Table Tennis");
  });

  test("and it reaches the reader as a category key at all — the anchor", () => {
    // If `normalizeCat` ever folds table_tennis into something else, the label
    // above becomes dead code and this suite would keep passing while the page
    // showed something different. `table` is not a sport, so the whole key
    // survives normalisation and IS what the page labels.
    expect(normalizeCat("table_tennis")).toBe("table_tennis");
  });
});

describe("no category label is ever a raw payload key — the class", () => {
  test("the census carries categories to grade, and they survive normalisation", () => {
    // The anchor. Also proves the list is of RENDERED keys: a row that
    // `normalizeCat` folds elsewhere is never labelled, so listing it here would
    // grade a string the page does not show.
    expect(RENDERED_CATEGORIES_2026_08_14.length).toBe(15);
    for (const cat of RENDERED_CATEGORIES_2026_08_14) {
      expect(normalizeCat(cat)).toBe(cat);
    }
  });

  test("every category the page would render has a human label", () => {
    for (const cat of RENDERED_CATEGORIES_2026_08_14) {
      const label = categoryLabel(cat);
      expect(label).not.toBe(cat);
      expect(label).not.toMatch(/_/);
      expect(label).not.toBe("");
    }
  });

  test("an UNKNOWN multi-word key is prettified, not passed through", () => {
    // The actual guarantee. A category nobody has mapped — the state
    // `table_tennis` was in until today — must still render as words.
    for (const unmapped of ["water_polo", "beach_volleyball", "some_new_sport"]) {
      expect(DISPLAY_NAMES[unmapped]).toBeUndefined();
      const label = categoryLabel(unmapped);
      expect(label).not.toBe(unmapped);
      expect(label).not.toMatch(/_/);
      expect(label[0]).toBe(label[0].toUpperCase());
    }
  });

  test("an unknown single-word key loses nothing and gains no underscore", () => {
    expect(DISPLAY_NAMES["chess"]).toBeUndefined();
    expect(categoryLabel("chess")).toBe("chess");
  });

  test("short all-caps acronyms survive the prettifier", () => {
    // Regression cover for `nicheCatLabel`'s acronym rule, which the fallback
    // now inherits: "MMA" must not become "Mma".
    expect(categoryLabel("mma")).toBe("MMA");
  });

  test("the explicit map still wins over the generated label", () => {
    // Alex asked for "Table Tennis"; a generated label is not an opinion, and
    // the map is where opinions live.
    expect(DISPLAY_NAMES["table_tennis"]).toBe("Table Tennis");
    expect(categoryLabel("table_tennis")).toBe(DISPLAY_NAMES["table_tennis"]);
  });
});
