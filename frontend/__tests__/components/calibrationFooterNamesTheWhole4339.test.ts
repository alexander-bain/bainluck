// #4339 — THE FOOTER MUST NOT CALL A COHORT SUBTOTAL "RESOLVED OUTCOMES".
//
// ── WHAT A PHONE READER SAW, ON PRODUCTION, WITH NO INTERACTION ─────────────
//
// `https://www.bainluck.com/calibration` at 390px (D48 mystery-shop,
// calibration/1068). The same noun phrase, twice, 316,972 apart:
//
//   y ~9,500px   "What's included?"  755,817 resolved outcomes from Sep 2021…
//   y ~11,000px  page footer         438,845 resolved outcomes · 7 sources · …
//
// Nothing between them said they were different populations, and the footer is
// the page's last word — so 438,845 is the number a reader left with, under the
// word for the whole corpus.
//
// Confirmed against the live payload at build time (`GET /api/calibration`,
// HTTP 200, 489,105 bytes, 2,148 buckets): `total_outcomes` = 755,817, the sum
// of `n` over every bucket = 755,817, and the sum over the default cohort
// (`price_moved` true or null) = 438,845. So the card printed the corpus, the
// footer printed the traded cohort, and the two were reader-indistinguishable.
//
// ── WHY THE FOOTER'S EXISTING PARENTHETICAL DID NOT CATCH IT ────────────────
//
// It has one, keyed to `priceCohort` (closing line / opening price). The split
// that shrinks 755,817 → 438,845 is `cohortFilter`, traded vs untraded, which
// the footer never mentioned; and on the default view `priceCohort === "all"`,
// so the parenthetical is absent entirely. A guard that only asked "is there a
// qualifier" would grade the shipped defect a pass. That is why the reach test
// below asserts WHICH comparison the disclosure is keyed to.
//
// ── WHY THIS SUITE IS A PAIRING AND NOT ONE RENDER ──────────────────────────
//
// There is no jsdom in this suite (`testEnvironment: 'node'`) and `page.tsx` is
// a 2,000-line client component behind SWR — `calibrationAuditHooks.test.tsx`
// records why rendering it "would prove less and break more". So the sentence
// moved into `footerPopulationPhrase`, where the string a reader actually gets
// can be asserted directly, and the source scan is left with the one job it is
// good at: proving the footer still calls it. A pure function alone proves
// nothing about reach; a source scan alone proves nothing about the sentence.
// Neither half is sufficient, and an edit that defeats the fix has to defeat
// both.

import * as fs from "fs";
import * as path from "path";
import { footerPopulationPhrase } from "@/lib/calibrationPopulation";
import { partitionByActivity } from "@/lib/calibrationCohort";
import { PROD_BUCKETS, PROD_TOTAL_OUTCOMES } from "../lib/calibrationProdFixture";

const PAGE = path.join(__dirname, "..", "..", "app", "calibration", "page.tsx");
const SOURCE: string = fs.readFileSync(PAGE, "utf8");

/** The `<footer>` element, sliced out so nothing here can pass on a match
 *  somewhere else in a 2,000-line file — the "Population:" line at ~904 carries
 *  the same tokens and would satisfy every assertion below from three screens
 *  away. */
const FOOTER: string = (() => {
  const start = SOURCE.indexOf("<footer");
  const end = SOURCE.indexOf("</footer>", start);
  if (start === -1 || end === -1) throw new Error("no <footer> in page.tsx");
  return SOURCE.slice(start, end);
})();

describe("#4339 — the sentence a reader gets", () => {
  test("a cohort subtotal is named against the whole", () => {
    // The production numbers, as measured above.
    expect(footerPopulationPhrase(438_845, 755_817)).toBe(
      `${(438_845).toLocaleString()} resolved outcomes of ${(755_817).toLocaleString()} total`
    );
  });

  test("the whole, named as itself, carries no redundant qualifier", () => {
    // With the untraded toggle ON, cohortN IS fullN. "755,817 of 755,817 total"
    // is noise, and the disclosure exists to remove ambiguity, not to add text.
    expect(footerPopulationPhrase(755_817, 755_817)).toBe(
      `${(755_817).toLocaleString()} resolved outcomes`
    );
  });

  test("the qualifier names fullN and not some other number", () => {
    // A "fix" that qualifies against the cohort, or against a hardcoded corpus
    // size, reads as a disclosure and discloses nothing.
    const phrase = footerPopulationPhrase(438_845, 755_817);
    expect(phrase.startsWith((438_845).toLocaleString())).toBe(true);
    expect(phrase).toContain((755_817).toLocaleString());
    expect(phrase.indexOf((755_817).toLocaleString())).toBeGreaterThan(
      phrase.indexOf((438_845).toLocaleString())
    );
  });
});

describe("#4339 — the acceptance: the footer's number and the card's number", () => {
  // The acceptance is a claim about TWO elements: the footer's count and the
  // "What's included?" count cannot carry the same phrase with different
  // unqualified numbers. Two things make that true, and both are asserted.

  const partition = partitionByActivity(PROD_BUCKETS);
  const fullN = PROD_BUCKETS.reduce((s, b) => s + b.n, 0);
  const cohortN = partition.movedN + partition.notApplicableN;

  test("the card's number IS fullN — the qualifier reconciles the two elements", () => {
    // The card prints `data.total_outcomes`; the footer names `fullN`, the sum
    // over every bucket. If these ever stopped being the same number, "of N
    // total" would introduce a THIRD figure instead of reconciling two, and
    // this ship would be worse than the bug. Frozen production payload.
    expect(fullN).toBe(PROD_TOTAL_OUTCOMES);
  });

  test("on real data the two differ, so the disclosure is not dead code", () => {
    // 389,385 of 652,407 on the frozen fixture; 438,845 of 755,817 live. A
    // guard whose specimen has cohortN === fullN would pass against a footer
    // that never qualifies anything.
    expect(cohortN).not.toBe(fullN);
    expect(cohortN).toBeLessThan(fullN);
  });

  test("the phrase the footer builds from the real partition names both", () => {
    const phrase = footerPopulationPhrase(cohortN, fullN);
    expect(phrase).toContain(cohortN.toLocaleString());
    expect(phrase).toContain(PROD_TOTAL_OUTCOMES.toLocaleString());
    expect(phrase).toMatch(/resolved outcomes of .* total$/);
  });
});

describe("#4339 — reach: the footer is the element that calls it", () => {
  test("the footer calls footerPopulationPhrase with the cohort and the whole", () => {
    // Without this the sentence above is a library nobody uses.
    expect(FOOTER).toContain("footerPopulationPhrase(cohortN, fullN)");
  });

  test("page.tsx imports it — a call to a name it does not import is a build error, not a silent pass", () => {
    expect(SOURCE).toContain("footerPopulationPhrase,");
  });

  test("the footer no longer prints a bare cohortN", () => {
    // The shipped defect, exactly: `{cohortN.toLocaleString()} resolved
    // outcomes`. Re-inlining it — with or without a qualifier bolted on after —
    // takes the sentence back out of reach of every assertion above.
    expect(FOOTER).not.toContain("cohortN.toLocaleString()");
  });

  test("the disclosure is not keyed to priceCohort", () => {
    // The original bug's shape: the only conditional text in the footer was
    // `priceCohort !== "all" && …`, which is absent on the default view. The
    // population phrase must not be behind that condition — if it is, the
    // default view is unqualified again and the reader is back where they
    // started. The priceCohort parenthetical itself is fine and stays.
    const call = FOOTER.indexOf("footerPopulationPhrase(");
    const priceCond = FOOTER.indexOf('priceCohort !== "all"');
    expect(call).toBeGreaterThan(-1);
    expect(priceCond).toBeGreaterThan(-1);
    expect(call).toBeLessThan(priceCond);
  });

  test("the counts travel as data attributes, not only as prose", () => {
    // Notice 34's remedy shape: a probe reads the numbers off the element
    // rather than parsing the sentence, so tightening the copy later cannot
    // blind the measurement.
    expect(FOOTER).toContain("data-cohort-n={cohortN}");
    expect(FOOTER).toContain("data-full-n={fullN}");
    expect(FOOTER).toContain('data-testid="calibration-footer-population"');
  });

  test("no corpus size is hardcoded into the footer", () => {
    // 755817 moves every hour. A literal would be a census frozen into JSX —
    // right at apply time and quietly wrong by the next rebuild.
    expect(FOOTER).not.toMatch(/\b\d{6,}\b/);
  });
});
