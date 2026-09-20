// #7374 — the module is only as real as where the page reads the pair.
//
// `calibrationIntervalScope.test.ts` holds the decision. This holds the WIRING,
// which no unit test can see: the defect was not a wrong function, it was two
// render sites reaching past any function and formatting `data.mce_ci_lower` /
// `data.mce_ci_upper` themselves. Re-adding either line restores the defect with
// every unit test green and `npm run typecheck` clean.
//
// Source-level, deliberately — the convention this page already sets, and its
// stated reason (`calibrationCensoredWiringReachesThePage6211.test.ts`): it is a
// 3,000-line client component behind SWR, and "rendering it would prove less and
// break more".
//
// The assertions pin PAYLOAD FIELD NAMES, not local identifiers. `mce_ci_lower`
// and `mce_ci_upper` are the API contract; a rename of them is a contract change
// that should redden a guard, whereas pinning `mceInterval` would redden on an
// honest rename and get the guard deleted by the next reader.

import * as fs from "fs";
import * as path from "path";

const PAGE = path.join(__dirname, "..", "..", "app", "calibration", "page.tsx");
const source = fs.readFileSync(PAGE, "utf8");

/**
 * The file with comments stripped.
 *
 * Both fixes in this area left long comments quoting the old code and the old
 * numbers — including the literal `data.mce_ci_lower.toFixed(1)` this guard
 * exists to forbid. An assertion over the raw file would fail on its own
 * explanation, and the obvious "fix" is to delete the explanation.
 */
const code = source
  .replace(/\/\*[\s\S]*?\*\//g, "")
  .split("\n")
  .filter(line => !line.trim().startsWith("//"))
  .join("\n");

function occurrences(needle: string): number {
  return code.split(needle).length - 1;
}

describe("#7374 the page reads the published pair in exactly one place", () => {
  it("control — the field names are still in this file at all", () => {
    // Without this, every count-based assertion below passes on a page that
    // stopped mentioning the interval entirely, which is a different bug.
    expect(occurrences("mce_ci_lower")).toBeGreaterThan(0);
    expect(occurrences("mce_ci_upper")).toBeGreaterThan(0);
  });

  it("names each bound once, and only as an argument to the scope helper", () => {
    expect(occurrences("mce_ci_lower")).toBe(1);
    expect(occurrences("mce_ci_upper")).toBe(1);

    const call = code.indexOf("mceIntervalForCohort({");
    expect(call).toBeGreaterThan(-1);
    const end = code.indexOf("})", call);
    expect(end).toBeGreaterThan(call);
    const args = code.slice(call, end);

    expect(args).toContain("mce_ci_lower");
    expect(args).toContain("mce_ci_upper");
    // The population the interval claims to describe travels with it, from the
    // same two values the page prints.
    expect(args).toContain("cohortN");
    expect(args).toContain("fullN");
  });

  it("never formats a bound itself", () => {
    // The exact shape both render sites used: `data.mce_ci_lower.toFixed(1)`.
    expect(code).not.toMatch(/mce_ci_(lower|upper)\s*\.\s*toFixed/);
  });
});

describe("#7374 the How We Compare row carries no interval", () => {
  /**
   * The benchmark list, sliced so a `95% CI` elsewhere on the page cannot
   * satisfy — or falsify — this.
   */
  function benchmarkSection(): string {
    const start = code.indexOf("How We Compare");
    expect(start).toBeGreaterThan(-1);
    const end = code.indexOf("reference points, not a ranking", start);
    expect(end).toBeGreaterThan(start);
    return code.slice(start, end);
  }

  it("control — the section is the one that prints our own per-bucket figure", () => {
    const section = benchmarkSection();
    expect(section).toContain("cohortMCE");
    expect(section).toContain("per-bucket");
    expect(section).toContain("Metaculus");
  });

  it("prints no confidence interval beside the equal-weighted figure", () => {
    const section = benchmarkSection();
    expect(section).not.toContain("95% CI");
    expect(section).not.toContain("mce_ci");
  });

  it("the row type has no slot to put one back into", () => {
    const start = code.indexOf("type BenchmarkRow = {");
    expect(start).toBeGreaterThan(-1);
    const end = code.indexOf("};", start);
    const rowType = code.slice(start, end);
    expect(rowType).toContain("highlight");
    expect(rowType).not.toMatch(/\bci\??\s*:/);
  });
});

describe("#7374 the interval sits with the figure it is an interval for", () => {
  /** The "Show the math" fold. */
  function showTheMath(): string {
    const start = code.indexOf('data-testid="calibration-show-the-math"');
    expect(start).toBeGreaterThan(-1);
    const end = code.indexOf("How we measure this", start);
    expect(end).toBeGreaterThan(start);
    return code.slice(start, end);
  }

  it("is rendered in the ECE sentence, gated on the derived interval", () => {
    const fold = showTheMath();
    // `_bootstrap_mce_ci` is n-weighted; ECE is the n-weighted figure and this
    // fold is the sentence about it.
    expect(fold).toContain("ECE");
    expect(fold).toContain("n-weighted");
    expect(fold).toContain("{mceInterval &&");
    expect(fold).toContain("formatMceInterval(mceInterval)");
  });

  it("no longer claims to be an interval on the per-bucket figure", () => {
    expect(showTheMath()).not.toContain("interval on the per-bucket figure");
  });

  it("is not gated on the constant that could never be false", () => {
    // `priceCohort` is declared `const priceCohort: ... = "all"`, so the old
    // guard `priceCohort === "all"` was true on every render. Neither render
    // site may rely on it again.
    expect(showTheMath()).not.toContain('priceCohort === "all"');
  });
});
