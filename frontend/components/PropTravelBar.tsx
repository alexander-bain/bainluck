"use client";

/**
 * The travelled bar — ONE implementation, shared by THE DIVERGENCE rail and its
 * detail view.
 *
 * Extracted from `PropDivergenceRail` in UX-P101 rather than copied. The rail
 * and the detail view are allowed to disagree about which rows they show and
 * about nothing else; two bar implementations would drift on exactly the thing
 * the reader compares across the fold — the position of the tick and the head.
 *
 * Domain is fixed 0-100% so rows are comparable to each other and to the native
 * chart's single-axis convention (`project_native_chart_single_axis`).
 */

import type { DivergenceRow } from "@/lib/propDivergence";

export function pct(p: number): string {
  return `${Math.round(p * 100)}%`;
}

/** Signed travel in points, the mock's "−40" pill. */
export function signedTravelPoints(row: DivergenceRow): string {
  const pts = Math.round((row.current - row.pregameMark) * 100);
  if (pts === 0) return "0";
  return pts > 0 ? `+${pts}` : `${pts}`;
}

export default function PropTravelBar({ row }: { row: DivergenceRow }) {
  const from = Math.min(row.pregameMark, row.current);
  const to = Math.max(row.pregameMark, row.current);
  const left = `${from * 100}%`;
  const width = `${Math.max(to - from, 0) * 100}%`;

  // Direction by colour, design-system tokens only (the site is light-mode
  // only; raw Tailwind dark classes are banned).
  const spanTone =
    row.direction === "over"
      ? "bg-accent-live"
      : row.direction === "under"
        ? "bg-accent-danger"
        : "bg-surface-border";
  const headTone =
    row.direction === "over"
      ? "bg-accent-live"
      : row.direction === "under"
        ? "bg-accent-danger"
        : "bg-text-muted";

  return (
    <div className="mt-1.5">
      <div
        className="relative h-2 rounded-full bg-surface-border/40"
        role="img"
        aria-label={`${row.label}: opened at ${pct(row.pregameMark)}, ${
          row.settled ? "finished at" : "now"
        } ${pct(row.current)}`}
      >
        {/* the travel */}
        <div
          className={`absolute top-0 h-2 rounded-full ${spanTone}`}
          style={{ left, width }}
        />
        {/* where the market opened the question */}
        <div
          className="absolute -top-0.5 h-3 w-px bg-text-muted"
          style={{ left: `${row.pregameMark * 100}%` }}
        />
        {/* where it is now */}
        <div
          className={`absolute -top-0.5 h-3 w-[3px] rounded-sm ${headTone}`}
          style={{ left: `${row.current * 100}%` }}
        />
      </div>
      <div className="mt-1 flex items-center justify-between text-[11px] text-text-muted tabular-nums">
        <span>opened {pct(row.pregameMark)}</span>
        <span className="text-text-secondary font-medium">
          {row.settled ? "final" : "now"} {pct(row.current)}
        </span>
      </div>
    </div>
  );
}
