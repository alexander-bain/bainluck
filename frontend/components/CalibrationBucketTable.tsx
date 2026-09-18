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
          {buckets.map(b => (
            <tr key={b.bucket} className="border-t border-surface-border">
              {/* Same reason as the interval below: at 390px auto-layout gave
                  this column 58.7px and broke "30-40%" after the dash on four
                  of ten rows, while `Avg Predicted` sat on 84.6px to print
                  "4.2%". A bucket label split across two lines is the same
                  sliced-number look. */}
              <td className="py-2 pr-1 sm:pr-4 whitespace-nowrap">{b.bucket}</td>
              <td className="py-2 pr-1 sm:pr-4 text-right tabular-nums">{b.n.toLocaleString()}</td>
              <td className="py-2 pr-1 sm:pr-4 text-right tabular-nums">{b.avgProb}%</td>
              <td className="py-2 pr-1 sm:pr-4 text-right tabular-nums">
                {b.actual}%
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
              <td className={`py-2 text-right tabular-nums ${
                Math.abs(b.error) < 3 ? "text-text-muted" : b.error > 0 ? "text-green-600" : "text-red-600"
              }`}>
                {b.error > 0 ? "+" : ""}{b.error}pp
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
