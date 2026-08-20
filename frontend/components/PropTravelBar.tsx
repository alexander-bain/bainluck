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
 *
 * ── POST-GAME IS A DIFFERENT ELEMENT, NOT A DIFFERENT COLOUR (UX-P105, #2011) ──
 *
 * Alex, on the expand captures: *"shouldn't it always finish at 0% or 100%? …
 * post-game it doesn't make any sense."* It didn't: the head was drawn at
 * `row.current`, which after settlement is the LAST TRADED PRICE, and the label
 * read `final 58%` — a price wearing the grammar of a result. So a settled row
 * renders the mark and the outcome, and no travel bar at all.
 *
 * The dispatch lives HERE, in the one shared component, for the same reason the
 * component was extracted: both surfaces get the post-game treatment, or the
 * two halves of one screen disagree about whether a game is over.
 */

import type { DivergenceRow } from "@/lib/propDivergence";
import { SETTLED_NO_GRADE_LABEL } from "@/lib/propGrade";

export function pct(p: number): string {
  return `${Math.round(p * 100)}%`;
}

/** Signed travel in points, the mock's "−40" pill. In-game only. */
export function signedTravelPoints(row: DivergenceRow): string {
  const pts = Math.round((row.current - row.pregameMark) * 100);
  if (pts === 0) return "0";
  return pts > 0 ? `+${pts}` : `${pts}`;
}

/**
 * Distance from the pregame mark to the outcome, in points. Post-game only, and
 * unsigned on purpose — the direction is already stated in words next to it,
 * and a "+93" reads as a price move, which is the thing this replaces.
 */
export function surprisePoints(row: DivergenceRow): string | null {
  if (row.surprise == null) return null;
  return `${Math.round(row.surprise * 100)} pts`;
}

/** The outcome, in the settled vocabulary. `null` when nothing may be stated. */
export function resolutionLabel(row: DivergenceRow): string | null {
  if (row.resolution == null) return null;
  return row.resolution === 1 ? "HAPPENED" : "DIDN'T HAPPEN";
}

/**
 * A settled row: what the market marked it at, and what actually happened.
 *
 * No bar, per #2011's scope. The mark is still shown — it is the whole point of
 * THE SCRIPT, and dropping it would leave the outcome with nothing to be
 * surprising against.
 */
function ResolvedMark({ row }: { row: DivergenceRow }) {
  const label = resolutionLabel(row);

  // Settled, but the backend published no verdict we may state. `propGrade` is
  // the one authority for that sentence; restating it here is how #1650 got one
  // backend state wearing three vocabularies on one screen.
  if (label == null) {
    return (
      <div className="mt-1.5 flex items-baseline justify-between gap-3 text-[11px]">
        <span className="text-text-muted">marked {pct(row.pregameMark)}</span>
        <span className="text-text-muted">{SETTLED_NO_GRADE_LABEL}</span>
      </div>
    );
  }

  const tone = row.resolution === 1 ? "text-accent-live" : "text-accent-danger";

  return (
    <div
      className="mt-1.5 flex items-baseline justify-between gap-3 text-[11px] tabular-nums"
      role="img"
      aria-label={`${row.label}: marked ${pct(row.pregameMark)}, it ${
        row.resolution === 1 ? "happened" : "did not happen"
      }`}
    >
      <span className="text-text-muted">
        marked {pct(row.pregameMark)} <span aria-hidden="true">&rarr;</span>{" "}
        <span className={`font-semibold ${tone}`}>{label}</span>
      </span>
      <span className="text-text-secondary">{surprisePoints(row)}</span>
    </div>
  );
}

export default function PropTravelBar({ row }: { row: DivergenceRow }) {
  if (row.settled) return <ResolvedMark row={row} />;

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
        aria-label={`${row.label}: opened at ${pct(row.pregameMark)}, now ${pct(row.current)}`}
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
        <span className="text-text-secondary font-medium">now {pct(row.current)}</span>
      </div>
    </div>
  );
}
