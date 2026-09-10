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
    // CAL-P1078: the grouping count is now the WHOLE pool (4), not the
    // published half of it (2) — the sentence names the list it is actually
    // enumerating, which is what made "2 published categories (hockey,
    // icehockey_nhl)" beside a four-member fold misleading in the first place.
    expect(d.sentence).toContain("4 categories grouped under one name");
    expect(d.sentence).toContain("icehockey_nhl");
    expect(d.sentence).toContain("traded outcomes only");
  });

  it("still splits published from unpublished as DATA, off the sentence", () => {
    // #2108 defect 3 was that the sentence called all four members "published"
    // when two have no `by_category` row. CAL-P1078 does not un-fix that: it
    // takes the whole distinction OFF the reader's screen, because "published"
    // here means "our serialiser emits a row under this name" and no reader can
    // do anything with that. The split is still computed, still complete, and
    // still reaches every probe — the row hangs both lists on
    // `data-published-members` / `data-unpublished-members`.
    //
    // #2108 STAYS OPEN. This ship hides our accounting of the gap; it does not
    // close it, and standing notice 34's amended clause is what requires the
    // numbers to survive as data when the sentence goes.
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
    // Both sets partition the fold — no member may be dropped by either label.
    expect(d.publishedMembers.length + d.unpublishedMembers.length).toBe(
      d.pooledFrom.length
    );
    // …and neither label reaches the reader.
    expect(d.sentence).not.toContain("unpublished");
    expect(d.sentence).not.toContain("published");
  });

  it("says so plainly when a fold publishes nothing at all", () => {
    const d = describeCategoryPopulation(
      "football",
      ["americanfootball_nfl", "americanfootball_cfl"],
      PUBLISHED,
      "excluding_never_moved"
    );

    expect(d.publishedMembers).toEqual([]);
    // CAL-P1078: the SPLIT is still computed and still complete — it is the
    // sentence that stopped naming it. See the "no payload vocabulary" block
    // at the foot of this file for why.
    expect(d.unpublishedMembers).toEqual([
      "americanfootball_cfl",
      "americanfootball_nfl",
    ]);
    expect(d.sentence).toContain("2 categories grouped under one name");
  });

  it("anchors against the whole-population figure without naming the API", () => {
    const d = describeCategoryPopulation(
      "hockey",
      HOCKEY_POOL,
      PUBLISHED,
      "excluding_never_moved"
    );

    expect(d.publishedEce).toBe(0.95);
    expect(d.publishedN).toBe(35416);
    // Amendment 5 — the anchor, available on its own so the page can render it
    // as its own line rather than only as a sentence tail. CAL-P1078 kept the
    // anchor and both its figures; what left is "The API publishes", which is a
    // sentence about our serialiser rather than about the reader's question.
    expect(d.anchorSentence).toContain("Across all");
    expect(d.anchorSentence).not.toContain("The API publishes");
    expect(d.sentence).toContain("0.95pp");
    expect(d.sentence).toContain("35,416");
    // For a POOLED row the whole-population twin differs on both axes, and
    // saying only "not just this slice" would understate it.
    expect(d.sentence).toContain("for “hockey” on its own");
  });

  it("names the cohort alone when a row pools nothing", () => {
    const d = describeCategoryPopulation(
      "politics",
      ["politics"],
      PUBLISHED,
      "excluding_never_moved"
    );

    expect(d.pools).toBe(false);
    expect(d.sentence).not.toContain("grouped under one name");
    expect(d.sentence).toContain("traded outcomes only");
    expect(d.sentence).toContain("not just this slice");
  });

  it("claims no whole-population twin when the displayed name is not a payload key", () => {
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
    expect(d.sentence).not.toContain("Across all");
    // …but the grouping half still has to be stated.
    expect(d.sentence).toContain("2 categories grouped under one name");
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

    expect(d.title).toContain("covers 4 categories grouped under one name");
    expect(d.title).not.toContain("icehockey_sweden_allsvenskan");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// CAL-P1078 — NO PAYLOAD VOCABULARY REACHES A READER (standing notice 34 as
// amended by D102: the target is jargon, not grey type).
//
// Alex, on the live page: a bare "56 CATEGORIES" badge under Soccer, opening
// onto "Published in `by_category` (1)" and "Not published (55)". Every string
// this module hands the page is a reader's string, so the ban is asserted over
// the module's OUTPUT across a population rather than by reading the source —
// a source-scan would pass the moment someone builds the same words by
// concatenation.
// ─────────────────────────────────────────────────────────────────────────────
describe("no payload vocabulary in anything a reader sees", () => {
  const BANNED = [
    "by_category",
    "payload",
    "the API",
    "unpublished",
    "published",
  ];

  const SPECIMENS: ReadonlyArray<readonly [string, string[]]> = [
    ["a pooled row with a published twin", HOCKEY_POOL],
    ["a pooled row with no published member", ["americanfootball_nfl", "americanfootball_cfl"]],
    ["a row that pools nothing", ["politics"]],
    ["a row past the naming cap", Array.from({ length: MEMBER_NAME_CAP + 3 }, (_, i) => `p_${i}`)],
  ];

  it.each(SPECIMENS)("%s: sentence and tooltip are clean", (_what, pool) => {
    for (const cohort of ["all", "excluding_never_moved"] as const) {
      const d = describeCategoryPopulation(pool[0], pool, PUBLISHED, cohort);
      for (const word of BANNED) {
        expect(d.sentence.toLowerCase()).not.toContain(word.toLowerCase());
        expect(d.title.toLowerCase()).not.toContain(word.toLowerCase());
      }
    }
  });

  it("the table-level note is clean on every cohort and both pooling states", () => {
    for (const cohort of ["all", "excluding_never_moved"] as const) {
      for (const pooled of [0, 6, 15]) {
        const s = describeCategoryTablePopulation(cohort, pooled, 15);
        for (const word of BANNED) {
          expect(s.toLowerCase()).not.toContain(word.toLowerCase());
        }
        // A coverage count is notice 34's named shape; it must not come back
        // as a fraction of rows either.
        expect(s).not.toMatch(/\d+ of \d+ rows/);
      }
    }
  });

  it("the ban is a real ban — the shipped strings would have failed it", () => {
    // NEGATIVE CONTROL. Every assertion above passes vacuously if `BANNED` is
    // empty or the lowercasing is wrong, so the words that were live on
    // production are run through the same predicate and must be caught.
    const WAS_LIVE = [
      "This row pools 1 published category (soccer) and 54 unpublished.",
      "The API publishes 0.95pp for “hockey” over 35,416 outcomes",
      "it will not match the whole-population number the API publishes in `by_category`",
      "6 of 15 rows also pool several payload categories under one label",
    ];
    for (const line of WAS_LIVE) {
      const hit =
        BANNED.some(w => line.toLowerCase().includes(w.toLowerCase())) ||
        /\d+ of \d+ rows/.test(line);
      expect(hit).toBe(true);
    }
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
  it("always states the cohort, which is the one fact only it can give", () => {
    const s = describeCategoryTablePopulation("all", 0, 15);

    expect(s).toContain("all resolved outcomes");
    // No pooled rows ⇒ no grouping clause. A note that mentions grouping on a
    // table with none is furniture.
    expect(s).not.toContain("group");
  });

  it("says a row can be a group, without counting how many are", () => {
    const s = describeCategoryTablePopulation("excluding_never_moved", 6, 15);

    expect(s).toContain("traded outcomes only");
    expect(s).toContain("group several closely related categories");
    // CAL-P1078 / notice 34: the coverage count is exactly the shape the notice
    // names. It travels on `data-pooled-rows` / `data-total-rows` instead — see
    // calibrationNotice34.test.ts, which asserts both attributes are still on
    // the page.
    expect(s).not.toMatch(/\d+ of \d+ rows/);
  });

  it("the grouping clause is driven by the pooled count, not always on", () => {
    // The two branches must be distinguishable, or the parameter is dead and a
    // future edit can silently make the note constant.
    const none = describeCategoryTablePopulation("all", 0, 15);
    const some = describeCategoryTablePopulation("all", 15, 15);
    expect(none).not.toEqual(some);
    expect(some.startsWith(none)).toBe(true);
  });
});
