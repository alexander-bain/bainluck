// #8581 — THE ACCURACY PAGE'S THREE STATS TABLES FIT A 375px PHONE.
//
// #6292 made them fit at 390px and was measured only there. At 375px (iPhone
// SE, 12/13 mini) all three ran past their card again: Source Comparison 8px,
// the Calibration Table 7px ("-0.3p"), Category Breakdown 18px ("0.22"). Every
// wide column was wide because of its uppercase HEADER ("OUTCOMES" 71px over
// numbers that need 57-59), and Category Breakdown's widest cell is
// "Uncategorized" itself. The fix is two classes per table, both phone-only:
// mixed-case headers and 13px body type, back to uppercase / 14px from `sm` up.
//
// No test here can observe a layout (`testEnvironment: 'node'`); the measured
// widths are in the issue. This pins the markup the fix rests on, so a later
// edit that restores the bare `uppercase` or `text-sm` goes red before a reader
// sees the sliced digit again.

import { readFileSync } from "fs";
import { join } from "path";
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import CalibrationBucketTable from "../../components/CalibrationBucketTable";
import type { AggBucket } from "../../lib/calibrationParity";

const BUCKETS: AggBucket[] = [
  { midpoint: 5, n: 79088, winners: 3243, avgProb: 4.4, actual: 4.1, error: -0.3,
    bucket: "0-10%", ciLower: 3.9, ciUpper: 4.2 },
];

/** The classes on the first opening tag of `tag` at or after `from`. Split, not
 *  regexed: `/\buppercase\b/` also matches `sm:uppercase`, and the two say
 *  opposite things about a phone. */
function classesOf(markup: string, tag: string, from = 0): string[] {
  const at = markup.indexOf(`<${tag} `, from);
  if (at < 0) throw new Error(`no <${tag}> after ${from}`);
  const open = markup.slice(at, markup.indexOf(">", at) + 1);
  return (open.match(/className="([^"]*)"|class="([^"]*)"/)?.slice(1).find(Boolean) ?? "")
    .split(/\s+/)
    .filter(Boolean);
}

function expectPhoneSizing(table: string[], headerRow: string[]) {
  expect(table).toEqual(expect.arrayContaining(["text-[13px]", "sm:text-sm"]));
  expect(table).not.toContain("text-sm");
  expect(headerRow).toEqual(expect.arrayContaining(["normal-case", "sm:uppercase"]));
  expect(headerRow).not.toContain("uppercase");
}

describe("#8581 — stats tables at 375px", () => {
  test("Calibration Table: 13px body and mixed-case headers below sm, 14px/uppercase from sm", () => {
    const markup = renderToStaticMarkup(<CalibrationBucketTable buckets={BUCKETS} />);
    expectPhoneSizing(classesOf(markup, "table"), classesOf(markup, "tr"));
  });

  const PAGE = readFileSync(join(__dirname, "../../app/calibration/page.tsx"), "utf8");

  test.each([
    ["Source Comparison", 'data-testid="calibration-source-comparison-section"'],
    ["Category Breakdown", 'data-testid="calibration-category-breakdown"'],
  ])("%s: 13px body and mixed-case headers below sm, 14px/uppercase from sm", (_name, anchor) => {
    const section = PAGE.indexOf(anchor);
    expect(section).toBeGreaterThan(0);
    const table = PAGE.indexOf("<table ", section);
    expectPhoneSizing(classesOf(PAGE, "table", section), classesOf(PAGE, "tr", table));
  });
});
