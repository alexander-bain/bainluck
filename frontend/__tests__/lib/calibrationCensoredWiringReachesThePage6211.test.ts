// #6211 — the censoring gate is only as real as the array the page hands it.
//
// WHY THIS FILE EXISTS, measured rather than imagined.
//
// `lib/calibrationSourceRows.ts` decides whether a source's population has two
// sides in it, and 58 tests hold that decision. Every one of them constructs
// its own `buckets`. So a mutation at the CALL SITE —
//
//     buckets: groupBuckets,   ->   buckets: [],
//
// leaves all 58 green, passes `npm run typecheck` with the repo's exact
// baseline (2 pre-existing errors in this file, unchanged), and silently
// restores the defect: `censoringVerdict([])` is `censored: false`, so every
// row is `measured` again and DataGolf publishes 36.5pp exactly as before.
// That mutation was run; that is what it did.
//
// The REQUIRED `buckets` field on `SourceRowInput` makes the compiler catch an
// OMISSION (`TS2741: Property 'buckets' is missing`), which is worth having and
// is not this. Omission is the accident; a wrong value is the regression.
//
// So this asserts the wiring itself, at source level — the convention
// `calibrationAuditHooks.test.tsx` sets for this page and states the reason
// for: it is a 2,000-line client component behind SWR, and "rendering it would
// prove less and break more".
//
// The assertion is deliberately not `toContain("buckets: groupBuckets")`. That
// pins a NAME, so an honest rename reddens it and the next reader deletes the
// guard. What is actually load-bearing is the IDENTITY: the buckets the verdict
// judges must be the same array the three published metrics were computed from.
// If they can differ, the row can be judged on one population and printed from
// another — a defect with no symptom until a reader sees a number no gate
// looked at. So the identifier is discovered from the source and then required
// to appear in all four places.

import * as fs from "fs";
import * as path from "path";

const PAGE = path.join(__dirname, "..", "..", "app", "calibration", "page.tsx");
const source = fs.readFileSync(PAGE, "utf8");

/**
 * The `providerMetrics` memo — the block that builds one row per provider.
 *
 * Sliced rather than regexed over the whole 2,700-line file so a coincidental
 * `buckets:` somewhere else in the page cannot satisfy these assertions.
 */
function providerMetricsBlock(): string {
  const start = source.indexOf("const providerMetrics = useMemo(");
  expect(start).toBeGreaterThan(-1);
  const end = source.indexOf("}, [normalized, sources, cohortFilter]);", start);
  expect(end).toBeGreaterThan(start);
  return source.slice(start, end);
}

describe("#6211 — the page hands the gate the buckets its metrics came from", () => {
  const block = providerMetricsBlock();

  /** The name the block gives its pooled-bucket array. Discovered, not assumed. */
  const bucketsIdent = (() => {
    const m = block.match(/const\s+(\w+)\s*=\s*aggregateBuckets\(/);
    expect(m).not.toBeNull();
    return m![1];
  })();

  it("pools the provider's buckets once, with aggregateBuckets", () => {
    // The row's own population, not a re-derivation and not the page-wide one.
    expect(bucketsIdent).toBeTruthy();
    expect(block).toMatch(
      new RegExp(`const\\s+${bucketsIdent}\\s*=\\s*aggregateBuckets\\(normalized,\\s*match\\)`)
    );
  });

  it("computes the published ECE and MCE from that same array", () => {
    // Half of the identity claim. If the metrics came from somewhere else, the
    // verdict below would be about a different population than the numbers.
    expect(block).toMatch(new RegExp(`ece\\(\\s*${bucketsIdent}\\s*\\)`));
    expect(block).toMatch(new RegExp(`mce\\(\\s*${bucketsIdent}\\s*\\)`));
  });

  it("passes that same array to the gate as `buckets`", () => {
    // THE MUTATION, pinned: `buckets: []` satisfies the type, the 58 unit
    // tests and the typecheck baseline, and restores the defect in full.
    expect(block).toMatch(new RegExp(`buckets:\\s*${bucketsIdent}\\s*,`));

    // Stated as a ban too, so the specific regression that was measured is
    // named and cannot come back wearing a comment.
    expect(block).not.toMatch(/buckets:\s*\[\s*\]/);
  });

  it("renders the censored set from the rows the table renders", () => {
    // Same pairing discipline `data-withheld-sources` already keeps: the
    // attribute is derived from `sourceRows`, never from a second condition
    // that has to be kept in step with them.
    expect(source).toMatch(/data-censored-sources=\{[\s\S]{0,120}censoredSourceRows\(sourceRows\)/);
    expect(source).toContain("censoredSourceRows");
  });

  it("keeps the withheld sentence keyed on the OTHER absence", () => {
    // `withheldSourcesNote` must not start speaking for censored rows: with
    // the cohort toggle already on, "no outcomes in this cohort — use the
    // toggle" is false twice over for a 36-outcome row.
    expect(source).toMatch(/withheldSourcesNote\(sourceRows,\s*cohort\.toggleLabel\)/);
    expect(source).toMatch(/sourceRowsExcludedFromRollup\(sourceRows\)/);
  });
});
