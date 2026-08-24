/**
 * UX-P118 item 5 — the two-ECEs disclosure. #2108 — the false census.
 * UX-P125 — Option C as ruled.
 *
 * The values here are MEASURED, not invented: they come from
 * `GET /api/calibration` on 2026-08-21 (HTTP 200, 432 KB, 1,934 buckets),
 * recomputed with the page's own `ece` over the page's own bucket aggregation.
 *
 *   A) server key only, ALL rows       n=35416  ece=0.95   <- by_category
 *   B) server key only, cohort filter  n=15383  ece=1.94
 *   C) pooled keys,     ALL rows       n=47091  ece=1.38
 *   D) pooled keys,     cohort filter  n=27058  ece=2.25   <- the page
 *
 * B is the pair the class was filed on. D is what is actually on the screen.
 * The gap between them is the whole reason this module names two axes and not
 * one — a disclosure that stopped at the cohort would have labelled a number
 * nobody can see.
 *
 * ** Nothing here asserts a live census. ** These fixtures are hand-built sets
 * chosen to exercise each SHAPE (all-published, mixed, none-published, over the
 * cap). Asserting "soccer folds 55" would be #2108 reintroduced as a fixture —
 * a census restated as a constant, which is the defect the ruling exists to
 * correct. The live numbers are swept separately by
 * `tools/option-c-staging/run.sh`, against the payload, at run time.
 */

import {
  MEMBER_NAME_CAP,
  cohortPhrase,
  describeCategoryPopulation,
  describeCategoryTablePopulation,
  nameAll,
} from "@/lib/calibrationPopulation";

const PUBLISHED = [
  { category: "hockey", ece: 0.95, n: 35416 },
  { category: "icehockey_nhl", ece: 3.48, n: 10616 },
  { category: "politics", ece: 1.2, n: 4000 },
];

const HOCKEY_POOL = [
  "hockey",
  "icehockey_nhl",
  "icehockey_sweden_allsvenskan",
  "icehockey_sweden_hockey_league",
];

describe("describeCategoryPopulation", () => {
  it("names the pooling AND the cohort for a pooled row", () => {
    const d = describeCategoryPopulation(
      "hockey",
      HOCKEY_POOL,
      PUBLISHED,
      "excluding_never_moved"
    );

    expect(d.pools).toBe(true);
    expect(d.pooledFrom).toEqual([...HOCKEY_POOL].sort());
    // BOTH axes, or the sentence is a false account of the number beside it.
    expect(d.sentence).toContain("pools 2 published categories");
    expect(d.sentence).toContain("icehockey_nhl");
    expect(d.sentence).toContain("traded outcomes only");
  });

  it("splits published from unpublished instead of calling every member published", () => {
    // #2108 defect 3. "published" is what tells a reader they can go and verify
    // a member; two of hockey's four have no `by_category` row, and the shipped
    // sentence invited a reader to look up all four.
    const d = describeCategoryPopulation(
      "hockey",
      HOCKEY_POOL,
      PUBLISHED,
      "excluding_never_moved"
    );

    expect(d.publishedMembers).toEqual(["hockey", "icehockey_nhl"]);
    expect(d.unpublishedMembers).toEqual([
      "icehockey_sweden_allsvenskan",
      "icehockey_sweden_hockey_league",
    ]);
    expect(d.sentence).toContain("2 unpublished");
    expect(d.sentence).not.toContain("pools the published categories");
    // Both sets partition the fold — no member may be dropped by either label.
    expect(d.publishedMembers.length + d.unpublishedMembers.length).toBe(
      d.pooledFrom.length
    );
  });

  it("says so plainly when a fold publishes nothing at all", () => {
    const d = describeCategoryPopulation(
      "football",
      ["americanfootball_nfl", "americanfootball_cfl"],
      PUBLISHED,
      "excluding_never_moved"
    );

    expect(d.publishedMembers).toEqual([]);
    expect(d.sentence).toContain("2 payload categories, none of them published");
  });

  it("reconciles against the figure the API publishes under the same name", () => {
    const d = describeCategoryPopulation(
      "hockey",
      HOCKEY_POOL,
      PUBLISHED,
      "excluding_never_moved"
    );

    expect(d.publishedEce).toBe(0.95);
    expect(d.publishedN).toBe(35416);
    // Amendment 5 — the anchor, available on its own so the page can render it
    // as its own line rather than only as a sentence tail.
    expect(d.anchorSentence).toContain("The API publishes");
    expect(d.sentence).toContain("0.95pp");
    expect(d.sentence).toContain("35,416");
    // For a POOLED row the published twin differs on both axes, and saying only
    // "the whole population" would understate it.
    expect(d.sentence).toContain("the “hockey” category alone");
  });

  it("names the cohort alone when a row pools nothing", () => {
    const d = describeCategoryPopulation(
      "politics",
      ["politics"],
      PUBLISHED,
      "excluding_never_moved"
    );

    expect(d.pools).toBe(false);
    expect(d.sentence).not.toContain("pools");
    expect(d.sentence).toContain("traded outcomes only");
    expect(d.sentence).toContain("the whole population, not this cohort");
  });

  it("claims no published twin when the displayed name is not a payload key", () => {
    // `football` is a DISPLAY name — the payload publishes
    // `americanfootball_nfl` and friends, never `football`. Inventing a
    // disagreement here would manufacture the exact confusion this fixes.
    const d = describeCategoryPopulation(
      "football",
      ["americanfootball_nfl", "icehockey_nhl"],
      PUBLISHED,
      "excluding_never_moved"
    );

    expect(d.publishedEce).toBeNull();
    expect(d.publishedN).toBeNull();
    expect(d.anchorSentence).toBeNull();
    expect(d.sentence).not.toContain("The API publishes");
    // …but the pooling half still has to be stated.
    expect(d.sentence).toContain("pools 1 published category");
  });

  it("does not present a published category whose ece is null as a figure", () => {
    const d = describeCategoryPopulation(
      "hockey",
      ["hockey"],
      [{ category: "hockey", ece: null, n: 35416 }],
      "excluding_never_moved"
    );

    expect(d.publishedEce).toBeNull();
    expect(d.sentence).not.toContain("The API publishes");
  });

  it("dedupes and sorts the pooled set so the expansion is stable", () => {
    const d = describeCategoryPopulation(
      "hockey",
      ["icehockey_nhl", "hockey", "icehockey_nhl"],
      PUBLISHED,
      "excluding_never_moved"
    );

    expect(d.pooledFrom).toEqual(["hockey", "icehockey_nhl"]);
  });

  it("keeps the tooltip to counts — never the full member wall", () => {
    const d = describeCategoryPopulation(
      "hockey",
      HOCKEY_POOL,
      PUBLISHED,
      "excluding_never_moved"
    );

    expect(d.title).toContain("pools 2 published categories and 2 unpublished");
    expect(d.title).not.toContain("icehockey_sweden_allsvenskan");
  });
});

describe("the cap is legal only because the expansion is complete", () => {
  // Amendment 4, as ruled and as re-pointed by UX-P125. A cap in the COLLAPSED
  // sentence is fine — inlining 55 identifiers is the wall of text the ruling's
  // own tradeoff line warned about. A cap with nowhere to finish reading it is
  // #2108. So the guard is not "never cap": it is "cap ⇒ the member arrays are
  // complete", and it is asserted, not trusted.
  const MANY = Array.from({ length: MEMBER_NAME_CAP + 3 }, (_, i) => `pub_${i}`);
  const published = MANY.map(category => ({ category, ece: 1, n: 100 }));

  it("collapses the inline list past the cap", () => {
    const d = describeCategoryPopulation("x", MANY, published, "all");

    expect(d.capApplied).toBe(true);
    expect(d.sentence).toMatch(/and 3 more/);
  });

  it("carries every member in the expansion anyway", () => {
    const d = describeCategoryPopulation("x", MANY, published, "all");

    expect(d.publishedMembers).toEqual([...MANY].sort());
    expect(d.publishedMembers.length + d.unpublishedMembers.length).toBe(
      d.pooledFrom.length
    );
    // The expander renders `nameAll`, which is the uncapped enumeration.
    const expansion = nameAll(d.publishedMembers);
    for (const m of MANY) expect(expansion).toContain(m);
    expect(expansion).not.toMatch(/and \d+ more/);
  });

  it("does not collapse a list that fits", () => {
    const few = MANY.slice(0, MEMBER_NAME_CAP);
    const d = describeCategoryPopulation(
      "x",
      few,
      few.map(category => ({ category, ece: 1, n: 100 })),
      "all"
    );

    expect(d.capApplied).toBe(false);
    expect(d.sentence).not.toMatch(/and \d+ more/);
    for (const m of few) expect(d.sentence).toContain(m);
  });
});

describe("cohortPhrase", () => {
  it("reads as a noun phrase for every cohort, not as a heading", () => {
    // "measured over traded" is what dropping `shortLabel` into prose produces.
    // Both keys must yield something that survives the sentence around it.
    for (const key of ["all", "excluding_never_moved"] as const) {
      const phrase = cohortPhrase(key);
      expect(phrase).toBeTruthy();
      expect(phrase).toMatch(/outcomes/);
      expect(phrase).toBe(phrase.toLowerCase());
    }
  });

  it("distinguishes the two cohorts", () => {
    expect(cohortPhrase("all")).not.toBe(cohortPhrase("excluding_never_moved"));
  });
});

describe("describeCategoryTablePopulation", () => {
  it("always states the cohort and the by_category mismatch", () => {
    const s = describeCategoryTablePopulation("all", 0, 15);

    expect(s).toContain("all resolved outcomes");
    expect(s).toContain("by_category");
    expect(s).not.toContain("also pool");
  });

  it("counts the pooled rows, and points at the expander rather than a hover", () => {
    const s = describeCategoryTablePopulation("excluding_never_moved", 6, 15);

    expect(s).toContain("6 of 15 rows also pool");
    // Amendment 4 changed the affordance; the sentence has to change with it or
    // it sends a reader hovering for something that is now a click.
    expect(s).toContain("expand a row");
    // Amendment 3: the members are payload categories, not published ones.
    expect(s).toContain("payload");
  });

  it("never promises more pooled rows than the table renders", () => {
    // Amendment 6, as a relation rather than as a value. The shipped bug was a
    // numerator drawn from the normalized keys — a strictly larger population
    // than the rendered rows — so the fraction could exceed 1.
    const s = describeCategoryTablePopulation("all", 15, 15);
    expect(s).toContain("15 of 15 rows");
  });
});
