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
