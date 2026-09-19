// #7174 — the accuracy page's second statistic must not be named a MAXIMUM.
//
// WHAT PRODUCTION PRINTED (LOOK 2026-09-19 09:15Z, `artifacts-calibration-2611/`):
// the Source Comparison table headed a column "MCE" — over a tooltip that
// opened with the literal word "Max" — and put 2.6pp under it for Polymarket,
// on the row whose ECE cell read 2.7pp. Hockey and MMA did the same in the
// Category Breakdown. A maximum of a set of absolute bucket errors cannot fall
// below a weighted mean of that same set, so the header and the number beside
// it contradicted each other on the one page whose subject is whether our
// numbers can be trusted.
//
// The number was never wrong. `calibrationMath.mce()` is an equal-weighted MEAN
// over the ten buckets, and `app/utils/calibration_ece.py` has said so in its
// own docstring since CAL-P067 ("the latter name claims a maximum and this is a
// mean"). Only the name was wrong, so only the name changed.
//
// WHY TWO HALVES, AND WHY NEITHER IS A SUBSTRING BAN.
// `calibrationNotice34.test.ts` records the trap this suite is written around:
// *"a guard that ban[s] an assertion cannot be a substring test"* — a blanket
// `not.toMatch(/MCE/)` over the page would red-light the code comments that
// explain the rename, and would go green the day someone reintroduces the claim
// in a synonym. So:
//
//   1. ARITHMETIC. Drive the real `mce()` and `ece()` on a bucket set built so
//      the equal-weighted mean lands BELOW the n-weighted one, and assert both
//      that ordering and that `mce()` is not the per-bucket maximum. This is
//      what makes "it cannot be called a maximum" a measured fact rather than
//      an opinion about vocabulary. It also fails if someone ever "fixes" the
//      contradiction by quietly turning the function into a max — which would
//      move a published number on three surfaces (see #7174, out of scope).
//
//   2. STRUCTURAL. Assert WHICH header sits beside ECE, by position in the
//      header row, not by sweeping the file for a word. A rename back to "MCE",
//      or a tooltip that re-asserts a maximum, fails it; a comment mentioning
//      the history does not.
//
// The iOS twin prints the same pair under the same names and is NATIVE's
// (notice 41 / D127) — routed, not edited here, so this suite is web-only by
// construction.

import * as fs from "fs";
import * as path from "path";
import { mce, ece } from "../../lib/calibrationMath";
import type { CalibrationErrorBucket } from "../../lib/calibrationMath";

const PAGE = path.join(__dirname, "..", "..", "app", "calibration", "page.tsx");
const SOURCE: string = fs.readFileSync(PAGE, "utf8");

/**
 * Polymarket's shape, reduced to three buckets: the crowded bucket is the badly
 * calibrated one, so weighting by n pulls the mean UP and counting each bucket
 * once leaves it DOWN. Hand-picked rather than random, because the whole point
 * is a case where the two statistics order the "wrong" way round.
 *
 *   equal-weighted: (6.0 + 0.5 + 0.5) / 3               = 2.333…
 *   n-weighted:     (6.0*900 + 0.5*50 + 0.5*50) / 1000  = 5.45
 */
const CROWDED_BUCKET_IS_THE_BAD_ONE: CalibrationErrorBucket[] = [
  { n: 900, error: 6.0 },
  { n: 50, error: -0.5 },
  { n: 50, error: 0.5 },
];

describe("#7174 arithmetic — the second statistic is a mean, and can sit below ECE", () => {
  test("mce() lands BELOW ece() on a cohort whose crowded bucket is its worst", () => {
    const equalWeighted = mce(CROWDED_BUCKET_IS_THE_BAD_ONE);
    const nWeighted = ece(CROWDED_BUCKET_IS_THE_BAD_ONE);

    expect(equalWeighted).toBeCloseTo(2.3333, 3);
    expect(nWeighted).toBeCloseTo(5.45, 3);
    // The production symptom, reproduced in the pure function: the column the
    // page used to head "MCE" reads lower than the column headed "ECE".
    expect(equalWeighted).toBeLessThan(nWeighted);
  });

  test("mce() is not the maximum bucket error either, so no reading of the acronym fits", () => {
    const worstBucket = Math.max(
      ...CROWDED_BUCKET_IS_THE_BAD_ONE.map(b => Math.abs(b.error))
    );
    expect(worstBucket).toBeCloseTo(6.0, 6);
    expect(mce(CROWDED_BUCKET_IS_THE_BAD_ONE)).toBeLessThan(worstBucket);
  });
});

/** Every `<th …>…</th>` of the header row that follows `marker`, in order. */
function headerCells(marker: string): Array<{ attrs: string; text: string }> {
  const at = SOURCE.indexOf(marker);
  if (at === -1) throw new Error(`marker not found in page.tsx: ${marker}`);
  const theadOpen = SOURCE.indexOf("<thead>", at);
  const theadClose = SOURCE.indexOf("</thead>", theadOpen);
  if (theadOpen === -1 || theadClose === -1) {
    throw new Error(`no <thead> after marker: ${marker}`);
  }
  const row = SOURCE.slice(theadOpen, theadClose);

  const cells: Array<{ attrs: string; text: string }> = [];
  const re = /<th\b([^>]*)>([\s\S]*?)<\/th>/g;
  for (let m = re.exec(row); m !== null; m = re.exec(row)) {
    const text = m[2]
      .replace(/\{\/\*[\s\S]*?\*\/\}/g, " ") // JSX comments are not visible text
      .replace(/<[^>]*>/g, " ") // nested spans (the ⓘ mark)
      .replace(/&nbsp;/g, " ")
      .replace(/&#9432;/g, " ")
      .replace(/\s+/g, " ")
      .trim();
    cells.push({ attrs: m[1], text });
  }
  if (cells.length === 0) throw new Error(`no <th> parsed after marker: ${marker}`);
  return cells;
}

/**
 * Both accuracy tables. Named by a marker that is structural (the heading the
 * table belongs to), so the lookup does not depend on line numbers.
 */
const TABLES: Array<[string, string]> = [
  ["Source Comparison", ">Source Comparison<"],
  ["Category Breakdown", ">Category Breakdown<"],
];

describe.each(TABLES)("#7174 structural — %s header row", (_name, marker) => {
  test("parses a header row containing an ECE column", () => {
    const texts = headerCells(marker).map(c => c.text);
    expect(texts).toContain("ECE");
  });

  test("the column beside ECE is named for the mean it is, not a maximum", () => {
    const cells = headerCells(marker);
    const eceAt = cells.findIndex(c => c.text === "ECE");
    expect(eceAt).toBeGreaterThanOrEqual(0);

    const beside = cells[eceAt + 1];
    expect(beside).toBeDefined();

    // Positive: it says what it is.
    expect(beside.text).toBe("Per-bucket");

    // Negative, scoped to THIS cell — not a sweep of the file. "MCE" expands to
    // Maximum Calibration Error, and in a header cell that acronym IS the
    // claim, so banning it here is banning an assertion and not a word.
    expect(beside.text).not.toMatch(/\bMCE\b/i);
  });

  test("that column's tooltip disclaims the maximum and says it can read below ECE", () => {
    const cells = headerCells(marker);
    const beside = cells[cells.findIndex(c => c.text === "ECE") + 1];
    const title = /title="([^"]*)"/.exec(beside.attrs)?.[1] ?? "";

    // 🪤 The first draft of this test asserted `not.toMatch(/\bmaximum\b/i)` on
    // the tooltip and RED-LIT THE FIX — because the honest way to withhold a
    // claim in English is to negate it in front of the reader ("A mean, not a
    // maximum"). That is #4113's trap, reproduced here at 09:30Z by writing the
    // guard the obvious way. So the tooltip is graded on what it ASSERTS:
    expect(title).toMatch(/not a maximum/i);
    // …and on the clause that stops "2.6 under 2.7" reading as a broken number.
    // A tooltip on the mark is where notice 34 sends method notes.
    expect(title).toMatch(/below ECE/);
  });
});
