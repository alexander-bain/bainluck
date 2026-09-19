// #6292 — THE `ERROR` COLUMN SURVIVES A 390px SCREEN.
//
// The measurement, the per-column arithmetic and the reason `95% CI` is the
// column that moves are in `components/CalibrationBucketTable.tsx`'s header.
// This file pins what a node environment can actually see: the markup.
//
// The claim under test is NOT "the table fits" — no test here can observe a
// layout (`testEnvironment: 'node'`). It is the narrower, checkable one the fix
// rests on: at phone width exactly one column is withdrawn, it is the widest
// and most specialist one, its number is still on the screen underneath the
// rate it qualifies, and `Error` — the column that fell off — is withdrawn at
// no width at all. If a later change re-adds a seventh column or hides `Error`
// to make room, these go red before a reader sees it.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import CalibrationBucketTable, { formatBucketCI } from "../../components/CalibrationBucketTable";
import type { AggBucket } from "../../lib/calibrationParity";

/** Two real rows off production (`/calibration`, 2026-09-18): the first bucket,
 *  whose interval is the SHORT one, and a mid bucket carrying the LONGEST
 *  interval string the table can print — "22.0-24.3%" is what actually set the
 *  84.3px column width that had to go. A fixture with only short intervals
 *  would under-state the column and grade a non-fix a pass. */
const BUCKETS: AggBucket[] = [
  { midpoint: 5, n: 66556, winners: 2529, avgProb: 4.2, actual: 3.8, error: -0.5,
    bucket: "0-10%", ciLower: 3.6, ciUpper: 3.9 },
  { midpoint: 25, n: 8134, winners: 1879, avgProb: 24.4, actual: 23.1, error: -1.3,
    bucket: "20-30%", ciLower: 22.0, ciUpper: 24.3 },
];

/** The row cells of the rendered table, in document order, as raw markup.
 *
 *  The `(?=[\s>])` is not decoration: `<th[^>]*>` — the obvious spelling, and
 *  the one this file shipped first — also matches `<thead>`, so element 0 came
 *  back as `<thead><tr …><th …>Bucket</th>` and every index after it was off by
 *  nothing only because the count happened to stay 6. A tag-stripping
 *  `.replace()` hid that for one round by reducing the wrong fragment to the
 *  right word. Match the tag NAME, not its prefix. */
function cellsOf(markup: string): string[] {
  const body = markup.slice(markup.indexOf("<tbody"));
  return body.match(/<td(?=[\s>])[^>]*>[\s\S]*?<\/td>/g) ?? [];
}

function headersOf(markup: string): string[] {
  return markup.match(/<th(?=[\s>])[^>]*>[\s\S]*?<\/th>/g) ?? [];
}

/** The text between a one-element fragment's own tags. Sliced rather than
 *  tag-stripped with `replace(/<[^>]+>/g, "")`, which is what the first draft
 *  did and which CodeQL correctly refused as incomplete sanitization — a
 *  single-pass strip is not a way to get text out of markup, even markup this
 *  file generated itself. These headers hold plain words, so the span between
 *  the first `>` and the last `<` IS the text. */
function textOf(fragment: string): string {
  return fragment.slice(fragment.indexOf(">") + 1, fragment.lastIndexOf("<")).trim();
}

/** The classes on the fragment's OWN opening tag. Split rather than regexed
 *  because `/\bhidden\b/` also matches `sm:hidden` — the two say opposite
 *  things about a phone, and the first draft of this file got it wrong. */
function ownClasses(fragment: string): string[] {
  const open = fragment.slice(0, fragment.indexOf(">") + 1);
  return (open.match(/class="([^"]*)"/)?.[1] ?? "").split(/\s+/).filter(Boolean);
}

/** Withdrawn from a phone: `display:none` until the `sm` breakpoint. */
const hiddenOnPhone = (fragment: string) => ownClasses(fragment).includes("hidden");

const MARKUP = renderToStaticMarkup(<CalibrationBucketTable buckets={BUCKETS} />);

describe("#6292 — six columns on a phone", () => {
  test("the table still has all six columns; nothing was deleted to make room", () => {
    const heads = headersOf(MARKUP);
    expect(heads).toHaveLength(6);
    expect(heads.map(textOf)).toEqual([
      "Bucket", "N", "Avg Predicted", "Actual Rate", "95% CI", "Error",
    ]);
  });

  test("`95% CI` is the ONLY column withdrawn at phone width — header and cells", () => {
    const heads = headersOf(MARKUP);
    const hiddenHeads = heads.filter(hiddenOnPhone).map(textOf);
    expect(hiddenHeads).toEqual(["95% CI"]);

    // Per row: six cells, exactly one of them phone-hidden, and it is the CI one.
    const cells = cellsOf(MARKUP);
    expect(cells).toHaveLength(6 * BUCKETS.length);
    for (let r = 0; r < BUCKETS.length; r++) {
      const row = cells.slice(r * 6, r * 6 + 6);
      const hidden = row.filter(hiddenOnPhone);
      expect(hidden).toHaveLength(1);
      expect(hidden[0]).toContain('data-testid="calibration-bucket-ci-column"');
    }
  });

  test("a withdrawn column comes BACK at `sm`, so desktop is untouched", () => {
    // `hidden` without `sm:table-cell` would delete the column from every width
    // — the fix would then be data loss wearing a layout fix's clothes.
    const withdrawn = [...headersOf(MARKUP), ...cellsOf(MARKUP)].filter(hiddenOnPhone);
    expect(withdrawn.length).toBeGreaterThan(0); // never vacuous
    for (const frag of withdrawn) {
      expect(ownClasses(frag)).toContain("sm:table-cell");
    }
  });

  test("`Error` is hidden at no width — it is the column the defect ate", () => {
    const heads = headersOf(MARKUP);
    expect(heads[5]).toContain("Error");
    expect(hiddenOnPhone(heads[5])).toBe(false);
    for (let r = 0; r < BUCKETS.length; r++) {
      const errorCell = cellsOf(MARKUP)[r * 6 + 5];
      expect(hiddenOnPhone(errorCell)).toBe(false);
      expect(errorCell).toContain(`${BUCKETS[r].error}pp`);
    }
  });

  test("the interval a phone loses as a column is on the screen as a line", () => {
    // Withdrawing the column is only honest because the number stays. The
    // inline copy is `sm:hidden`, so the two are never both visible.
    for (const b of BUCKETS) {
      const inline = MARKUP.match(
        new RegExp(`<span[^>]*calibration-bucket-ci-inline[^>]*>${formatBucketCI(b).replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}</span>`)
      );
      expect(inline).not.toBeNull();
      expect(inline![0]).toMatch(/\bsm:hidden\b/);
    }
    // ...and it sits INSIDE the rate it qualifies, not in a row of its own.
    for (let r = 0; r < BUCKETS.length; r++) {
      const actualCell = cellsOf(MARKUP)[r * 6 + 3];
      expect(actualCell).toContain(`${BUCKETS[r].actual}%`);
      expect(actualCell).toContain("calibration-bucket-ci-inline");
    }
  });

  test("both copies of an interval are the same string, always", () => {
    // One formatter, so a later change to the precision cannot leave a phone
    // reader and a desktop reader looking at different numbers for one bucket.
    for (const b of BUCKETS) {
      const occurrences = MARKUP.split(formatBucketCI(b)).length - 1;
      expect(occurrences).toBe(2);
    }
    expect(formatBucketCI({ ciLower: 3.6, ciUpper: 3.9 })).toBe("3.6-3.9%");
    expect(formatBucketCI({ ciLower: 22, ciUpper: 24.25 })).toBe("22.0-24.3%");
  });

  test("the horizontal-scroll affordance stays on the wrapper", () => {
    // CAL-P1263 shipped `scroll-shadow-x` so a cut edge reads as "more this
    // way". This table should no longer overflow at all, but the class is what
    // makes the OTHER widths honest and removing it is a silent regression.
    expect(MARKUP).toMatch(/class="overflow-x-auto scroll-shadow-x"/);
  });

  test("an empty cohort renders a head and no rows, not a crash", () => {
    const empty = renderToStaticMarkup(<CalibrationBucketTable buckets={[]} />);
    expect(headersOf(empty)).toHaveLength(6);
    expect(cellsOf(empty)).toHaveLength(0);
  });
});

// #7183 — EVERY FIGURE IN THE COLUMN IS AT THE SAME PRECISION.
//
// Production (2026-09-19 10:13Z, 390px) printed the 90-100% bucket's error as a
// bare "+1pp" in a `tabular-nums` column of "-0.5pp" and "+2.7pp", because the
// cells stringified the raw number and JS drops a trailing ".0".
//
// Why the suite above could not see it: its assertions interpolate the fixture's
// own number — ``toContain(`${BUCKETS[r].error}pp`)`` — which RESTATES the
// rendering rule instead of pinning a format, and both of its fixtures are
// non-integer, so they render identically either way. The bug is only reachable
// through a whole-numbered row, which is what this fixture is. It is not a
// second copy of the rows above; it exists to be the case they cannot be.
const WHOLE: AggBucket[] = [
  // `aggregateBuckets` rounds to 1dp (`Math.round(x * 1000) / 10`), so each of
  // these is a value that function can really produce — 96.0 - 95.0 = 1.0.
  { midpoint: 95, n: 15114, winners: 14512, avgProb: 95, actual: 96, error: 1,
    bucket: "90-100%", ciLower: 95.8, ciUpper: 96.4 },
  // ...and the negative and exact-zero arms, which sign handling can get wrong
  // independently: `(-0).toFixed(1)` is "0.0", never "-0.0".
  { midpoint: 45, n: 68953, winners: 30000, avgProb: 46, actual: 44, error: -2,
    bucket: "40-50%", ciLower: 43.8, ciUpper: 44.5 },
  { midpoint: 55, n: 1000, winners: 550, avgProb: 55, actual: 55, error: 0,
    bucket: "50-60%", ciLower: 52, ciUpper: 58 },
];

describe("#7183 — a whole-numbered figure keeps its decimal", () => {
  const MARKUP_W = renderToStaticMarkup(<CalibrationBucketTable buckets={WHOLE} />);
  const cellText = (r: number, c: number) => textOf(cellsOf(MARKUP_W)[r * 6 + c]);

  test("the ERROR column prints 1dp on every row, signed, never a bare integer", () => {
    expect(cellText(0, 5)).toBe("+1.0pp");
    expect(cellText(1, 5)).toBe("-2.0pp");
    expect(cellText(2, 5)).toBe("0.0pp"); // no "+" at exactly zero, and no "-0.0"
  });

  test("`Avg Predicted` and `Actual Rate` keep theirs too — same line, same class", () => {
    expect(cellText(0, 2)).toBe("95.0%");
    expect(cellText(1, 2)).toBe("46.0%");
    // The actual-rate cell carries the inline CI span, so assert its leading
    // figure rather than the whole cell's text.
    expect(cellsOf(MARKUP_W)[0 * 6 + 3]).toContain(">96.0%");
    expect(cellsOf(MARKUP_W)[1 * 6 + 3]).toContain(">44.0%");
  });

  test("no cell in a tabular-nums figure column is at a different precision", () => {
    // The column-level claim, so a later change that fixes one cell and leaves
    // another cannot pass. Every figure this table prints carries exactly one
    // decimal place.
    const cells = cellsOf(MARKUP_W);
    expect(cells).toHaveLength(6 * WHOLE.length);
    for (let r = 0; r < WHOLE.length; r++) {
      for (const c of [2, 5]) {
        expect(cellText(r, c)).toMatch(/^[+-]?\d+\.\d(%|pp)$/);
      }
    }
  });
});
