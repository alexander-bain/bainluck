// CAL-P1217 — the coverage accounting obeys notice 34 on the page itself.
//
// The selector suite (`__tests__/lib/calibrationCoverage.test.ts`) grades what
// may be shown. This grades the shape it is shown IN, which is a separate
// promise and the one that is easy to lose in a later edit:
//
//   * folded, so a reader who does not care sees one line (D102: "untraded or
//     vanished props go behind a collapsed toggle — present, openable, taking
//     no real estate when closed");
//   * the numbers on data-attributes, so a probe reads them without opening the
//     fold (notice 34's failing-self-audit clause, and the reason the
//     population arithmetic beside it moved to attributes in #4340);
//   * this file's own words, never the payload's `rule` strings — the finding
//     #4067 made about the filter bullets directly below it.
//
// A SOURCE SCAN, like its neighbours here and for their reason: `page.tsx` is a
// ~2,600-line SWR client component and this suite runs under `node` with no
// jsdom. What is graded is the source of the region, with comments stripped —
// the comments in that region quote the rule they enforce, and a raw scan would
// red on the explanation for the fix.

import * as fs from "fs";
import * as path from "path";

import { RUNG_LABELS } from "@/lib/calibrationCoverage";
import { COMPLETE_CENSUS } from "../lib/calibrationCensusFixture";

const PAGE_PATH = path.join(__dirname, "..", "..", "app", "calibration", "page.tsx");
const RAW: string = fs.readFileSync(PAGE_PATH, "utf8");

const RENDERED: string = RAW
  .replace(/\{\s*\/\*[\s\S]*?\*\/\s*\}/g, " ")
  .replace(/\/\*[\s\S]*?\*\//g, " ")
  .replace(/^[ \t]*\/\/.*$/gm, " ");

const collapse = (s: string): string => s.replace(/\s+/g, " ");

/** The accounting's own JSX, from its test id to the bullet that follows it. */
function region(): string {
  const start = RENDERED.indexOf('data-testid="calibration-coverage-accounting"');
  expect(start).toBeGreaterThan(-1);
  const end = RENDERED.indexOf("data.liquidity_filter &&", start);
  expect(end).toBeGreaterThan(start);
  return RENDERED.slice(start, end);
}

describe("the coverage accounting is folded and still measurable", () => {
  it("is behind a collapsed toggle", () => {
    expect(region()).toContain("<details");
    expect(region()).toContain("<summary");
  });

  it("puts every number it fold away onto the element as an attribute", () => {
    for (const attr of ["data-covered", "data-plotted", "data-excluded", "data-empty-rules"]) {
      expect(region()).toContain(attr);
    }
  });

  it("keys each row so a probe can read one rule's count", () => {
    expect(region()).toContain("data-rung=");
  });

  it("renders only when the selector returns an accounting", () => {
    // `coverage &&` is the whole of the render gate: no fallback branch, no
    // "0 excluded", no empty fold. The page carries one bullet fewer.
    expect(collapse(region())).not.toContain("coverage ?");
    expect(collapse(RENDERED)).toContain("{coverage && (");
  });

  it("states the scope, because the headline total is a different unit", () => {
    // The bridge counts futures outcomes; the page's headline total also
    // contains sportsbook curve observations. A reader who subtracts one from
    // the other must not be invited to.
    expect(collapse(region())).toContain("Sportsbook rows are counted separately");
  });
});

describe("the labels are ours, not the payload's", () => {
  it("prints no rule string the server wrote", () => {
    for (const rung of COMPLETE_CENSUS.coverage_bridge.rungs as ReadonlyArray<{ rule: string }>) {
      // The first clause of each rule is enough to catch a paste: the whole
      // string is a hard-wrapped multi-line sentence in the payload and would
      // never appear contiguously even if it were printed.
      const head = rung.rule.split(" ").slice(0, 6).join(" ");
      expect(collapse(RENDERED)).not.toContain(head);
    }
  });

  it("takes its wording from the label map rather than restating it", () => {
    // One string is allowed to be literal in the page — none. The terminal
    // rung's label comes from RUNG_LABELS too, so a wording change lands in one
    // place and the table cannot disagree with itself.
    for (const label of Object.values(RUNG_LABELS)) {
      expect(collapse(RENDERED)).not.toContain(label);
    }
    expect(region()).toContain("RUNG_LABELS[PLOTTED_RUNG]");
    expect(region()).toContain("row.label");
  });
});

describe("the scan can fail", () => {
  // Controls. Both of these would have passed silently if the region were
  // empty or the stripper ate the prose — the two ways a source scan lies.
  it("found a region with the render in it", () => {
    expect(region().length).toBeGreaterThan(400);
    expect(region()).toContain("toLocaleString()");
  });

  it("still sees rendered prose after stripping comments", () => {
    expect(collapse(RENDERED)).toContain("Where the prediction-market outcomes went");
  });
});
