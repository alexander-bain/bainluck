// #6292 — SIX COLUMNS DO NOT FIT A PHONE, AND THE ONE THAT FELL OFF IS `ERROR`.
//
// ── WHAT A PHONE READER SAW, MEASURED ON PRODUCTION ─────────────────────────
//
// `https://bainluck.com/calibration` at 390px, read off the layout engine
// (`scrollWidth - clientWidth` on the `overflow-x-auto` wrapper, and the last
// `th`'s rect against the wrapper's right edge), 2026-09-18 00:2xZ:
//
//   table               cols  width  overflow  last col visible
//   Source Comparison     5    324       0     54 of 54  ✅
//   Traded vs Untraded    4    324       0     73 of 73  ✅
//   Calibration Table     6    370      46      2 of 49  ← this file
//   Category Breakdown    5    324       0     51 of 51  ✅
//
// CAL-P1263 (`60c43f913`) reclaimed the cell padding — `pr-1 sm:pr-4` — and
// that was enough for all three FIVE-column tables, which is why three of the
// four rows above are clean. It was not enough here, and the issue stayed open
// on exactly this remainder: the sixth column is `Error`, the number a reader
// comes to a calibration table for, and it renders 2 of its 49 pixels.
//
// ── WHY THE `95% CI` COLUMN IS THE ONE THAT MOVES ───────────────────────────
//
// Per-column widths at 390px, same read:
//
//   Bucket 55.3 · N 52.4 · Avg Predicted 74.8 · Actual Rate 54.9
//   · 95% CI 84.3 · Error 48.8                            = 370.5
//
// 46.5px has to go. `95% CI` is the widest column on the table by 10px, and it
// is the only specialist one — every other column is a headline number. It is
// also the only column whose width is driven by its CELLS rather than its
// header ("22.0-24.3%" at `text-sm tabular-nums`), so shrinking the header
// buys nothing. Removing it as a COLUMN sheds 84px and leaves 286px against a
// 324px wrapper, which is the whole 46px and 38px of margin besides.
//
// So at phone width the interval travels UNDERNEATH the rate it qualifies,
// inside the `Actual Rate` cell, in the same muted `text-xs` the column used.
// Nothing is dropped and nothing is shrunk — the issue's explicit bar was "do
// not fix this by shrinking type to the point the numbers stop being legible".
// At `sm` and up the column is back in its place and the table is byte-for-byte
// what it was; the `hidden`/`sm:hidden` pair is a `display:none` on one arm or
// the other, so exactly one copy of the interval is in the accessibility tree
// at any width.
//
// ── WHAT THIS FILE CAN AND CANNOT SEE ───────────────────────────────────────
//
// `testEnvironment: 'node'` — no layout engine, so no test in this repo can
// observe an overflow (the same limit `calibrationChartLegibleOnAPhone4394`
// documents). What a test CAN observe is the markup the browser is handed, and
// this table was extracted out of `app/calibration/page.tsx` so that it can be
// rendered on its own and asserted: see
// `__tests__/components/calibrationTableErrorColumn6292.test.tsx`. The
// production probe closes the reach half —
//
//   node artifacts-calibration-1263/measure-all-tables.mjs <url>
//   → every table `overflowPx: 0`, every `lastColVisiblePx` == `lastColW`
//
// and the same probe at desktop width is the no-change arm.

import React from "react";
import type { AggBucket } from "@/lib/calibrationParity";

/** The interval, formatted once, so the phone copy and the desktop column can
 *  never drift into disagreeing about the same bucket. */
export function formatBucketCI(b: Pick<AggBucket, "ciLower" | "ciUpper">): string {
  return `${b.ciLower.toFixed(1)}-${b.ciUpper.toFixed(1)}%`;
}

/** #7183. Every figure in this table is already rounded to exactly one decimal
 *  by `calibrationParity.aggregateBuckets` (`Math.round(x * 1000) / 10`), so the
 *  VALUES were never wrong. But a 1dp number that lands on a whole one loses its
 *  decimal when JS stringifies it — `1.0` becomes `"1"` — and production printed
 *  the 90-100% bucket as a bare "+1pp" in a `tabular-nums` column of "-0.5pp"
 *  and "+2.7pp". A column whose job is to line its decimal points up cannot have
 *  one cell at a coarser precision, least of all on the page about how precise
 *  our numbers are. `toFixed(1)` is the same thing `formatBucketCI` above has
 *  always done; these three cells were the ones that skipped it.
 *
 *  Note `(-0).toFixed(1)` is "0.0", not "-0.0": a difference that rounds to
 *  negative zero still prints unsigned, as it did before. */
function pp1(v: number): string {
  return v.toFixed(1);
}

/** #7596. `Error` is the only DERIVED figure in this table, and unlike every
 *  other derived figure on the page its two inputs are printed in the same row.
 *  `aggregateBuckets` rounds all three to 1dp INDEPENDENTLY — `avgProb` and
 *  `actual` from their own ratios, `error` from the raw gap — so double rounding
 *  can put 0.1pp between the error printed and the gap between the two numbers
 *  printed beside it. On the 2026-09-20 payload it did on FIVE of ten rows:
 *  74.6% / 77.2% / +2.7pp, 84.8% / 85.9% / +1.2pp, 4.2% / 3.8% / -0.5pp. A
 *  reader who subtracts the columns — the one check this table can be checked
 *  with by eye — got a different answer half the time, on the page about how
 *  precise our numbers are.
 *
 *  `lib/calibrationMath.ts` already draws this line and draws it the same way:
 *  `side().errorPp` is rounded from the raw ratio ("not from the two rounded
 *  values") because that table prints no inputs beside it, while `gapPp` is
 *  derived "at display precision" because both of ITS inputs are on screen. This
 *  is that rule, applied to the one cell on the page that had neither.
 *
 *  This is the RENDER, not the measurement. `AggBucket.error` keeps its full
 *  precision and is untouched: `ece()` and `mce()` read it to produce the
 *  headline pp figure and every Source Comparison row, and a 0.05pp-per-bucket
 *  shift there would move published numbers to fix a display. The cost here is
 *  bounded at 0.05pp on a column whose values run 0.3-2.7pp inside intervals
 *  ~0.7pp wide — below this table's own resolution, where the disagreement was
 *  not. */
function displayedErrorPp(b: Pick<AggBucket, "avgProb" | "actual">): number {
  return Math.round((b.actual - b.avgProb) * 10) / 10;
}

export default function CalibrationBucketTable({ buckets }: { buckets: AggBucket[] }) {
  return (
    <div className="overflow-x-auto scroll-shadow-x">
      <table className="w-full text-sm" data-testid="calibration-bucket-table">
        <thead>
          <tr className="text-left text-xs text-text-muted uppercase tracking-normal sm:tracking-wide">
            <th className="pb-2 pr-1 sm:pr-4">Bucket</th>
            <th className="pb-2 pr-1 sm:pr-4 text-right">N</th>
            <th className="pb-2 pr-1 sm:pr-4 text-right">Avg Predicted</th>
            <th className="pb-2 pr-1 sm:pr-4 text-right">Actual Rate</th>
            <th className="hidden sm:table-cell pb-2 pr-4 text-right">95% CI</th>
            <th className="pb-2 text-right">Error</th>
          </tr>
        </thead>
        <tbody>
          {buckets.map(b => {
          const shownError = displayedErrorPp(b);
          return (
            <tr key={b.bucket} className="border-t border-surface-border">
              {/* Same reason as the interval below: at 390px auto-layout gave
                  this column 58.7px and broke "30-40%" after the dash on four
                  of ten rows, while `Avg Predicted` sat on 84.6px to print
                  "4.2%". A bucket label split across two lines is the same
                  sliced-number look. */}
              <td className="py-2 pr-1 sm:pr-4 whitespace-nowrap">{b.bucket}</td>
              <td className="py-2 pr-1 sm:pr-4 text-right tabular-nums">{b.n.toLocaleString()}</td>
              <td className="py-2 pr-1 sm:pr-4 text-right tabular-nums">{pp1(b.avgProb)}%</td>
              <td className="py-2 pr-1 sm:pr-4 text-right tabular-nums">
                {pp1(b.actual)}%
                {/* `whitespace-nowrap` is load-bearing, not tidiness: measured
                    at 390px the interval needs 69.3px and auto table layout had
                    given this column a 68.8px content box, so nine of ten rows
                    broke "14.0-14.7%" across two lines and stood 69px tall. An
                    interval split over a line break is the sliced-number look
                    this issue is about. The half-pixel comes out of `Avg
                    Predicted`, which auto-layout had inflated to 89.5px to
                    print "4.2%". */}
                <span
                  className="sm:hidden block text-xs text-text-muted tabular-nums whitespace-nowrap"
                  data-testid="calibration-bucket-ci-inline"
                >
                  {formatBucketCI(b)}
                </span>
              </td>
              <td
                className="hidden sm:table-cell py-2 pr-4 text-right tabular-nums text-text-muted"
                data-testid="calibration-bucket-ci-column"
              >
                {formatBucketCI(b)}
              </td>
              {/* The colour reads the same number the cell prints, for the same
                  reason: keyed on `b.error` a cell showing exactly "3.0pp" could
                  be painted as though it were inside the 3pp bar. One quantity
                  per cell, in the type and in the colour. */}
              <td className={`py-2 text-right tabular-nums ${
                Math.abs(shownError) < 3 ? "text-text-muted" : shownError > 0 ? "text-green-600" : "text-red-600"
              }`}>
                {shownError > 0 ? "+" : ""}{pp1(shownError)}pp
              </td>
            </tr>
          );
          })}
        </tbody>
      </table>
    </div>
  );
}
