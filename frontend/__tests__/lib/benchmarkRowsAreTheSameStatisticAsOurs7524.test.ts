// #7524 — a row in "How We Compare" must be the same STATISTIC as the one it is
// drawn beside.
//
// The section plots our per-bucket calibration error against published
// benchmarks on one 0-10pp axis. A fourth row, "Iowa Electronic Markets (Berg
// et al. 2008) — 1.5pp", sat at 15% of that axis beside our blue 10.2%. It is
// not a calibration figure: Further Reading, 5,500px down the same page, is
// where the 1.5pp comes from and says in our own words that IEM "predicted
// presidential outcomes within 1.5pp" — an absolute error on vote SHARE.
//
// CAL-P1261 (#6278) made four assertions about this section and every one is
// about how a row is DRAWN — the cohort tag, the colour grading, the invented
// midpoint, the footnote. Whether a row measures the same thing as ours is the
// prior question and nothing asked it. This file asks it.
//
// Source-level, following this page's stated convention
// (`calibrationCensoredWiringReachesThePage6211.test.ts`): a 3,000-line client
// component behind SWR, where "rendering it would prove less and break more".

import * as fs from "fs";
import * as path from "path";

const PAGE = path.join(__dirname, "..", "..", "app", "calibration", "page.tsx");
const source = fs.readFileSync(PAGE, "utf8");

/**
 * The file with comments stripped.
 *
 * Load-bearing here, not hygiene. The fix's own comment quotes the deleted row
 * label and the Further Reading sentence verbatim, to record why the row went.
 * Every assertion below would read that explanation as the code it forbids —
 * the negative ones would fail on it, and the obvious "fix" is to delete the
 * reasoning. (`calibrationIntervalReachesOneFigure7374.test.ts` hit the same
 * wall and solved it the same way.)
 */
const code = source
  .replace(/\/\*[\s\S]*?\*\//g, "")
  .split("\n")
  .filter(line => !line.trim().startsWith("//"))
  .join("\n");

/**
 * The benchmark list only — from the rendered heading to the footnote that
 * closes the section. Sliced so that Berg surviving in Further Reading, 1,100
 * lines below, can neither satisfy nor falsify anything about this list.
 *
 * Anchored on `>How We Compare</h2>` rather than the bare phrase for the reason
 * CAL-P1261's own guard carries a note about: its first run sliced from a doc
 * comment several hundred lines earlier that happens to name the section.
 */
function benchmarkList(): string {
  const start = code.indexOf(">How We Compare</h2>");
  expect(start).toBeGreaterThan(-1);
  const end = code.indexOf("reference points, not a ranking", start);
  expect(end).toBeGreaterThan(start);
  return code.slice(start, end);
}

/** The Further Reading list only. */
function furtherReading(): string {
  const start = code.indexOf(">Further Reading</h2>");
  expect(start).toBeGreaterThan(-1);
  const end = code.indexOf("</section>", start);
  expect(end).toBeGreaterThan(start);
  return code.slice(start, end);
}

describe("#7524 control — the two sections this guard slices are both real", () => {
  // Anti-vacuity. Every assertion in this file passes against an empty slice,
  // and the comment-stripping above is exactly the kind of step that can
  // silently empty one.
  it("the benchmark list is present, substantial, and still ours", () => {
    const list = benchmarkList();
    expect(list.length).toBeGreaterThan(400);
    // Our own measured row, the thing the benchmarks are drawn against.
    expect(list).toContain("cohortMCE");
    expect(list).toContain("highlight: true");
    // A surviving benchmark, so "no IEM row" is not satisfied by "no rows".
    expect(list).toContain("Metaculus (self-reported)");
  });

  it("the Further Reading list is present and substantial", () => {
    const fr = furtherReading();
    expect(fr.length).toBeGreaterThan(400);
    expect(fr).toContain("Superforecasting");
  });

  it("the two slices are disjoint", () => {
    // If the anchors ever collapse onto one another, the cross-section
    // assertions below become self-referential and stop meaning anything.
    const list = benchmarkList();
    expect(list).not.toContain(">Further Reading</h2>");
    expect(furtherReading()).not.toContain("cohortMCE");
  });
});

describe("#7524 the benchmark list plots no vote-share forecast error", () => {
  it("carries no Iowa Electronic Markets row", () => {
    expect(benchmarkList()).not.toContain("Iowa Electronic Markets");
  });

  it("carries no 1.5pp figure", () => {
    // The label could be reworded; the number is the defect. Distinct from
    // every other literal in the list (#7531 made Metaculus a 2-3 range, so the
    // list now holds 2, 3, 2 and 5), so this cannot pass or fail for a
    // neighbouring row's reasons.
    expect(benchmarkList()).not.toMatch(/mce:\s*1\.5\b/);
  });

  it("holds exactly three rows — ours and two benchmarks", () => {
    // A tripwire, not a style rule. The row that went was added in good faith;
    // what was missing was anyone asking whether it measured what our row
    // measures. A fourth row reddens this and sends its author to the comment
    // above the list, which is the whole point.
    const list = benchmarkList();
    expect(list.split("highlight:").length - 1).toBe(3);
    expect(list.split("label:").length - 1).toBe(3);
  });
});

describe("#7524 Berg survives where the page describes it correctly", () => {
  // The reference was never the problem — plotting its figure as a calibration
  // error was. Deleting the citation outright would be a different regression,
  // and one that a "no Iowa Electronic Markets anywhere" guard would cause.
  it("Further Reading still cites Berg, with its DOI", () => {
    const fr = furtherReading();
    expect(fr).toContain("Berg, Nelson");
    expect(fr).toContain("Iowa Electronic Markets");
    expect(fr).toContain("10.1016/j.ijforecast.2008.03.007");
  });

  it("Further Reading still says what the 1.5pp actually measures", () => {
    // This sentence is the page's own attribution and the entire evidence for
    // the fix: it is what makes the figure a vote-share error rather than a
    // calibration one. If it is ever reworded into "calibration error", the
    // removed row stops being wrong and this guard should be revisited — so it
    // is pinned rather than left implicit.
    const fr = furtherReading();
    expect(fr).toContain("predicted presidential outcomes within 1.5pp");
  });
});
