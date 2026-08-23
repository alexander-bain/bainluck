/**
 * UX-P118 item 5 — the two-ECEs disclosure.
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
 */

import {
  cohortPhrase,
  describeCategoryPopulation,
  describeCategoryTablePopulation,
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
    expect(d.sentence).toContain("pools the published categories");
    expect(d.sentence).toContain("icehockey_nhl");
    expect(d.sentence).toContain("traded outcomes only");
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
    expect(d.sentence).toContain("0.95pp");
    expect(d.sentence).toContain("35,416");
    // For a POOLED row the published twin differs on both axes, and saying only
    // "the whole population" would understate it.
    expect(d.sentence).toContain("only the “hockey” category");
  });

  it("names the cohort alone when a row pools nothing", () => {
    const d = describeCategoryPopulation(
      "politics",
      ["politics"],
      PUBLISHED,
      "excluding_never_moved"
    );

    expect(d.pools).toBe(false);
    expect(d.sentence).not.toContain("pools the published categories");
    expect(d.sentence).toContain("traded outcomes only");
    expect(d.sentence).toContain("the whole population, not this cohort");
  });

  it("claims no published twin when the displayed name is not a payload key", () => {
    // `football` is a DISPLAY name — the payload publishes
    // `americanfootball_nfl` and friends, never `football`. Inventing a
    // disagreement here would manufacture the exact confusion this fixes.
    const d = describeCategoryPopulation(
      "football",
      ["americanfootball_nfl", "americanfootball_cfl"],
      PUBLISHED,
      "excluding_never_moved"
    );

    expect(d.publishedEce).toBeNull();
    expect(d.publishedN).toBeNull();
    expect(d.sentence).not.toContain("The API publishes");
    // …but the pooling half still has to be stated.
    expect(d.sentence).toContain("pools the published categories");
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

  it("dedupes and sorts the pooled set so the tooltip is stable", () => {
    const d = describeCategoryPopulation(
      "hockey",
      ["icehockey_nhl", "hockey", "icehockey_nhl"],
      PUBLISHED,
      "excluding_never_moved"
    );

    expect(d.pooledFrom).toEqual(["hockey", "icehockey_nhl"]);
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
    const s = describeCategoryTablePopulation("all", 0, 128);

    expect(s).toContain("all resolved outcomes");
    expect(s).toContain("by_category");
    expect(s).not.toContain("also pool");
  });

  it("counts the pooled rows when there are any", () => {
    // 2 of 128 on the measured payload — rare enough that a per-row badge is
    // signal, common enough that omitting it loses the filed specimen.
    const s = describeCategoryTablePopulation("excluding_never_moved", 2, 128);

    expect(s).toContain("2 of 128 rows also pool");
  });
});
