// CAL-P117 — THE EXCLUSION AND ITS DISCLOSURE SHIP TOGETHER, OR NEITHER SHIPS.
//
// Alex ruled the `kalshi/economics` population fix on 2026-08-28 as option (b):
// the correlated intraday index-ladder rungs stop entering the published curve
// **AND** the removed rows are disclosed on the page as a named, counted
// exclusion — in his words, *"nobody later reads the smaller curve as a fixed
// one."*
//
// That is a conjunction, and the failure mode it guards against is specific and
// entirely plausible: the backend filter lands (it is 5.29 -> 2.61 pp on one
// cell and ~2.7% of the whole curve on another), the number on the page
// improves, and the sentence that explains WHY the denominator moved is trimmed
// in some later copy pass because it is long and reads like an apology. The
// ruling then survives in a commit message and nowhere a reader can see.
//
// So this suite pins three things, and each maps to a clause of the ruling:
//
//   1. the block exists and is gated on a NON-ZERO count — a filter that has
//      not been applied must render nothing, exactly like the four exclusions
//      above it, so the page never claims an exclusion it did not make;
//   2. the PER-CELL counts are rendered — the allowlist is keyed on
//      `(source, category)` (CAL-P114: category-only scoping takes
//      `polymarket/economics` from 3.91 to 17.75), so one total would hide
//      which cell actually shrank;
//   3. the closing clause survives — the sentence that says the curve got
//      SMALLER rather than BETTER.
//
// Asserted at the source level, following the precedent set and reasoned out in
// `calibrationAuditHooks.test.tsx` and `calibrationBannerCopy.test.tsx`: this
// page is a large client component behind SWR and rendering it here would prove
// less and break more. The compensating control for that choice — the thing
// that stops a source-level guard from staying green while the component quietly
// stops printing the feature — is assertion (1) below, which pins the JSX
// binding `data.nonexclusive_bundle_filter` inside the rendered `<li>` and not
// merely the string somewhere in the file.

import * as fs from "fs";
import * as path from "path";

const PAGE = path.join(__dirname, "..", "..", "app", "calibration", "page.tsx");
const API = path.join(__dirname, "..", "..", "lib", "api.ts");
const SOURCE: string = fs.readFileSync(PAGE, "utf8");
const API_SOURCE: string = fs.readFileSync(API, "utf8");

const TESTID = "calibration-nonexclusive-bundle-exclusion";
const TEMPORARY_TESTID = "calibration-nonexclusive-bundle-temporary";

/** The disclosure's JSX, from its test hook to the end of its list item. */
function disclosureRegion(source: string): string {
  const start = source.indexOf(`data-testid="${TESTID}"`);
  if (start < 0) {
    throw new Error(
      `the non-partition bundle disclosure is gone from the calibration page. ` +
        `Alex ruled the exclusion APPROVED WITH DISCLOSURE on 2026-08-28; if the ` +
        `exclusion is also gone this test should be deleted deliberately, and if ` +
        `it is not, this is the ruling being dropped. Re-anchor, do not delete.`,
    );
  }
  const end = source.indexOf("</li>", start);
  return source.slice(start, end);
}

/** Strip `{/* ... *\/}` JSX comments — prose about the copy is not the copy. */
function withoutJsxComments(region: string): string {
  return region.replace(/\{\/\*[\s\S]*?\*\/\}/g, " ");
}

/**
 * The copy as a READER meets it: comments gone, line wrapping collapsed.
 *
 * A sentence in JSX is broken across lines wherever the formatter chose, so a
 * phrase assertion against the raw source is really an assertion about where
 * the line breaks fell. That fails on a reflow that changed nothing a reader
 * can see, and — worse — it can be made to pass by re-wrapping copy whose
 * meaning was gutted. Collapse the whitespace and the test is about the words.
 */
function readerCopy(region: string): string {
  return withoutJsxComments(region).replace(/\s+/g, " ");
}

describe("CAL-P117 — the non-partition bundle exclusion is disclosed", () => {
  test("the page renders a list item bound to the payload's own filter", () => {
    const region = disclosureRegion(SOURCE);
    // The BINDING, not just the words: a block that stopped reading the payload
    // would keep every sentence below and print none of the numbers.
    expect(region).toContain("data.nonexclusive_bundle_filter.rule");
    expect(region).toContain("data.nonexclusive_bundle_filter.excluded.toLocaleString()");
  });

  test("it is gated on a non-zero count, like every exclusion above it", () => {
    // A filter that has not been applied renders nothing. The page must never
    // claim an exclusion it did not make — and on the day this lands, the
    // backend key does not exist yet, so this gate is what makes the change
    // safe to ship ahead of it.
    expect(SOURCE).toContain(
      "data.nonexclusive_bundle_filter && data.nonexclusive_bundle_filter.excluded > 0",
    );
  });

  test("the per-cell breakdown is rendered, not just the total", () => {
    const region = disclosureRegion(SOURCE);
    expect(region).toContain("excluded_by_cell");
    // Sorted, so the biggest removal is named first rather than whichever key
    // the serializer happened to emit first.
    expect(region).toMatch(/\.sort\(/);
  });

  test("the clause that stops a smaller curve reading as a fixed one survives", () => {
    const copy = withoutJsxComments(disclosureRegion(SOURCE));
    // Alex's ruling, in the page's own words. These are asserted as phrases
    // rather than one exact sentence so the copy can be edited for tone — what
    // may NOT happen is the meaning being dropped.
    expect(copy).toMatch(/shrank the curve rather than improving it/i);
    expect(copy).toMatch(/never read as a fixed one/i);
    // And it must say what actually caused the improvement.
    expect(copy).toMatch(/not because our prices got better/i);
  });

  test("the payload type carries the per-cell map", () => {
    expect(API_SOURCE).toContain("CalibrationNonexclusiveBundleFilter");
    expect(API_SOURCE).toContain("excluded_by_cell?: Record<string, number>");
    expect(API_SOURCE).toContain(
      "nonexclusive_bundle_filter?: CalibrationNonexclusiveBundleFilter | null",
    );
  });

  test("it sits inside the exclusions list, beside the filters it generalises", () => {
    // Placement is load-bearing: a reader reconciling the raw count with the
    // published total reads that list top to bottom. A disclosure filed
    // somewhere else on the page is a disclosure they will not meet.
    const start = SOURCE.indexOf(`data-testid="${TESTID}"`);
    const esports = SOURCE.indexOf("data.esports_multi_bundle_filter");
    const symmetry = SOURCE.indexOf("data.exclusion_symmetry &&");
    expect(esports).toBeGreaterThan(-1);
    expect(symmetry).toBeGreaterThan(-1);
    expect(start).toBeGreaterThan(esports);
    expect(start).toBeLessThan(symmetry);
  });
});

// CAL-P119 — THE SECOND CELL IS RULED, AND ITS EXCLUSION IS NOT THE SAME KIND.
//
// Alex ruled `polymarket/baseball` on 2026-08-28: **EXCLUDE NOW + FIX WRITER**.
// The rows leave the curve today with the same named, counted disclosure as
// `kalshi/economics` — and the writer that produced their prices is being
// repaired in parallel (lane1 queue 022), so *"when the writer is repaired the
// rows return and the exclusion empties itself."*
//
// That makes the two cells in this one filter leave for DIFFERENT reasons, and
// the difference is the reader's:
//
//   kalshi/economics    an intraday index ladder's rungs were never competing
//                       answers to one question. Structural. Permanent.
//   polymarket/baseball a Player-Props leg quoted 0.0355 was PUBLISHED at
//                       0.5005 by a writer. The question is real, the market's
//                       own quote is intact, and only our copy of the price is
//                       wrong. Temporary.
//
// The failure this suite guards is the page flattening the second into the
// first: ~2.7% of the published curve quietly written off as ineligible when it
// is merely mis-written, with nothing on the page that would ever bring it
// back. The disclosure of a temporary exclusion has to say that it is
// temporary, has to name the condition that ends it, and — because the block is
// rendered from the payload — has to disappear by itself when the backend stops
// emitting the cell. A hard-coded "baseball is temporary" sentence would still
// be on the page a year after the fix, which is the same lie in the other
// direction.
describe("CAL-P119 — a temporary exclusion is disclosed as temporary", () => {
  test("the temporary clause is rendered from the payload, not hard-coded", () => {
    const region = disclosureRegion(SOURCE);
    // The BINDING is the whole point. A hard-coded sentence naming baseball
    // would satisfy every copy assertion below and would still be on the page
    // after the writer is fixed.
    expect(region).toContain("data.nonexclusive_bundle_filter.temporary_by_cell");
    expect(region).toContain(`data-testid="${TEMPORARY_TESTID}"`);
  });

  test("it renders nothing when no cell is temporary", () => {
    // `kalshi/economics` alone is a PERMANENT exclusion. On that payload the
    // page must not print a word about rows coming back — the ruling that
    // approved it said no such thing.
    const region = disclosureRegion(SOURCE);
    expect(region).toContain(
      "Object.keys(data.nonexclusive_bundle_filter.temporary_by_cell).length > 0",
    );
  });

  test("each temporary cell is named with the condition that ends its exclusion", () => {
    const region = disclosureRegion(SOURCE);
    // Per cell, like `excluded_by_cell` above it: "which cell" and "until
    // when" are the two facts a reader needs to check the claim later.
    expect(region).toMatch(
      /Object\.entries\(data\.nonexclusive_bundle_filter\.temporary_by_cell\)/,
    );
    expect(region).toMatch(/returns when/i);
  });

  test("the promise that the rows come back survives", () => {
    const copy = readerCopy(disclosureRegion(SOURCE));
    // Alex's ruling, in the page's own words. Phrases rather than one exact
    // sentence so tone can be edited; what may NOT happen is the meaning being
    // dropped.
    expect(copy).toMatch(/temporary by design/i);
    expect(copy).toMatch(/re-enter the curve/i);
    // And the page must not let the removal read as a verdict on the rows.
    expect(copy).toMatch(/not claiming/i);
    expect(copy).toMatch(/gone for good/i);
  });

  // -------------------------------------------------------------------------
  // 🔴 CERT-647 — AND THE PROMISE MUST NOT COVER THE ROWS THAT NEVER COME BACK.
  //
  // This suite used to assert the copy said "this exclusion empties itself",
  // and the page said it — beside a count that was the whole R1+R2+R3+M1 union.
  // Only the M1/R3 arms end with the writer repair. R1/R2 are the same defect
  // already written into the back catalogue and a forward fix does not un-write
  // them; the backend's own constants block said so while the payload said the
  // opposite. So the assertion above was pinning a false sentence, and these
  // replace it: the temporary COUNT is rendered, and what stays is named.
  // -------------------------------------------------------------------------
  test("the temporary count is rendered, not left to the nearest number", () => {
    const region = disclosureRegion(SOURCE);
    // Without this the reader binds "part of this is temporary" to the per-cell
    // total printed immediately above it — which is exactly what CERT-647
    // caught. The count has to be in the sentence making the claim.
    expect(region).toContain("data.nonexclusive_bundle_filter.temporary_excluded");
    const copy = readerCopy(region);
    expect(copy).toMatch(/coming back/i);
  });

  test("the rows that are NOT coming back are named as such", () => {
    const region = disclosureRegion(SOURCE);
    expect(region).toContain("data.nonexclusive_bundle_filter.historical_excluded");
    const copy = readerCopy(region);
    // The page has to say the back catalogue stays, and say why. Dropping this
    // returns the page to a single undifferentiated temporary promise.
    expect(copy).toMatch(/are not/i);
    expect(copy).toMatch(/back catalogue/i);
    expect(copy).toMatch(/stay excluded/i);
  });

  test("the page never promises the whole exclusion empties itself", () => {
    // The exact sentence CERT-647 blocked. It is asserted ABSENT rather than
    // simply not-asserted-present, because "we removed the clause" is a fact a
    // later editor can undo by accident while every other test stays green.
    const copy = readerCopy(disclosureRegion(SOURCE));
    expect(copy).not.toMatch(/exclusion empties itself/i);
  });

  test("it says the price was wrong, not the question", () => {
    const copy = readerCopy(disclosureRegion(SOURCE));
    // The distinction IS the disclosure. Without it "temporary" is a schedule
    // note; with it, the reader knows we excluded our own defect and not a
    // class of market.
    expect(copy).toMatch(/real questions whose published price was written wrong/i);
    expect(copy).toMatch(/not\s+rows that were never forecasts/i);
  });

  test("the temporary clause sits after the permanent one, inside the same disclosure", () => {
    // One filter, one list item. A reader who meets "3.9% of the curve was
    // removed" must meet "and part of that is coming back" in the same breath,
    // not two bullets later.
    const start = SOURCE.indexOf(`data-testid="${TESTID}"`);
    const temporary = SOURCE.indexOf(`data-testid="${TEMPORARY_TESTID}"`);
    const closingClause = SOURCE.indexOf("never read as a fixed one");
    const endOfItem = SOURCE.indexOf("</li>", start);
    expect(temporary).toBeGreaterThan(closingClause);
    expect(temporary).toBeLessThan(endOfItem);
  });

  test("the payload type carries the per-cell revert condition", () => {
    expect(API_SOURCE).toContain("temporary_by_cell?: Record<string, string>");
  });

  test("the payload type carries both cohorts, so the bullet can add up", () => {
    // CERT-647: `temporary_excluded` is the M1/R3 cohort and
    // `historical_excluded` is its complement. A type carrying only the first
    // is one a later reader will assume covers the whole exclusion — the
    // original mistake, preserved in the contract.
    expect(API_SOURCE).toContain("temporary_excluded?: number;");
    expect(API_SOURCE).toContain("historical_excluded?: number;");
  });
});
