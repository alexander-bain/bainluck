/**
 * #3650 — no calibration ranking orders rows by a metric it did not measure.
 *
 * THE BUG. iPad Calibration ranked **DataGolf first at `0.0`** in a table whose
 * own subhead reads *"sorted by ECE … Lower is better"*
 * (`artifacts-native-042/ipad-calibration.png`). Measured against
 * `/api/calibration` on 2026-09-06, `datagolf` publishes 36 outcomes, all
 * `price_moved: false`, so the default cohort holds **zero** of them — every
 * metric on that row was an empty reduction's identity element. Its real ECE is
 * **36.49pp**, 13× the worst measured source. The rule that produced it was one
 * line: `.sorted { $0.ece < $1.ece }`.
 *
 * WHAT THIS GUARDS, AND WHY IT IS A SCAN RATHER THAN AN ASSERTION ABOUT ONE FILE.
 * The defect is not "CalibrationViewModel got it wrong" — it is a SHAPE that
 * reads naturally and is wrong every time: ordering calibration rows by a raw
 * metric comparison, with no gate on the count behind it. An allowlist of known
 * call sites cannot catch the file nobody thought to add, so this DISCOVERS the
 * shape across every Swift file in the iOS tree — iPhone, Watch and Widget
 * targets alike — and requires it to route through `CalibrationRowOrdering`.
 *
 * IT DELIBERATELY DOES NOT RESTATE THE ORDERING. A text guard can only check
 * that identifiers appear, and "both `measured` and `unmeasured` are mentioned"
 * is satisfied by a comparator with its two arms exchanged — the exact mutant
 * that would restore the bug. That permutation is killed in Swift, by
 * `CalibrationRowOrderingTests.testASwappedComparatorIsCaught`. This file's job
 * is the half CI can actually reach: that no new site bypasses the orderer, and
 * that the metrics stay optional so the compiler keeps enforcing the rest.
 *
 * It lives in jest because jest is a deploy gate here and the Swift test target
 * is not reachable from CI.
 */

import { readFileSync, readdirSync } from "fs";
import { join } from "path";

/** The whole iOS tree, not just the app target — a copy in Watch or Widget is a copy. */
const IOS_ROOT = join(__dirname, "../../../ios/Bain Luck");
const CANONICAL = join(IOS_ROOT, "Bain Luck/Utilities/CalibrationRowOrdering.swift");
const VIEW_MODEL = join(IOS_ROOT, "Bain Luck/ViewModels/CalibrationViewModel.swift");

function swiftFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return swiftFiles(path);
    return entry.isFile() && entry.name.endsWith(".swift") ? [path] : [];
  });
}

/**
 * Comments are stripped first: the canonical file and the view model both quote
 * the old expression in their headers to record what went wrong, and a raw
 * substring scan would call that documentation a reimplementation.
 */
function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^[ \t]*\/\/.*$/gm, "")
    .replace(/(?<!:)\/\/.*$/gm, "");
}

/**
 * An ordering/selection closure whose body compares a calibration metric.
 *
 * `sorted`, `min` and `max` all publish a row's POSITION or pick a row to put
 * on a card, which is the same claim in different clothing — "Best calibrated"
 * naming an unmeasured category is the headline version of the table bug.
 */
const RAW_METRIC_ORDERING =
  /\.(sorted|min|max)\s*(?:\(\s*by:)?\s*\{[^{}]*\b(ece|mce|brier)\b[^{}]*\}/g;

describe("#3650 calibration row ordering has one implementation", () => {
  const files = swiftFiles(IOS_ROOT);

  it("finds the iOS tree and the canonical orderer", () => {
    expect(files.length).toBeGreaterThan(100);
    expect(files).toContain(CANONICAL);
    expect(files).toContain(VIEW_MODEL);
  });

  it("orders calibration rows nowhere but in CalibrationRowOrdering", () => {
    const offenders: string[] = [];
    for (const file of files) {
      // The canonical orderer is the one place the comparison is allowed to live.
      if (file === CANONICAL) continue;
      const body = stripComments(readFileSync(file, "utf8"));
      for (const hit of body.match(RAW_METRIC_ORDERING) ?? []) {
        offenders.push(`${file.slice(IOS_ROOT.length + 1)}: ${hit.replace(/\s+/g, " ").trim()}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it("keeps the withheld metrics optional so the compiler enforces the render side", () => {
    const vm = readFileSync(VIEW_MODEL, "utf8");
    // A withheld metric is `nil`, never `0`. If these go back to plain `Double`
    // the empty reduction's zero can reach a formatter again and every other
    // guard here is decoration.
    for (const row of ["CalSourceRow", "CalCategoryRow"]) {
      const decl = vm.slice(vm.indexOf(`struct ${row}`));
      const fields = decl.slice(0, decl.indexOf("\n}"));
      for (const metric of ["ece", "mce", "brier"]) {
        expect(fields).toMatch(new RegExp(`let ${metric}: Double\\?`));
      }
    }
  });

  it("routes every row build through the metric-withholding helper", () => {
    const vm = stripComments(readFileSync(VIEW_MODEL, "utf8"));
    // One call per metric on each of the two row builders.
    const calls = vm.match(/CalibrationRowOrdering\.metric\(/g) ?? [];
    expect(calls.length).toBe(6);
    expect(vm).toContain("CalibrationRowOrdering.orderedByECE(rows)");
  });
});
