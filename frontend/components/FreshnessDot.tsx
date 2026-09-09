"use client";

import React from "react";

/**
 * THE FRESHNESS MARK, AND THERE IS ONE OF IT (#4283, notice 34, notice 35).
 *
 * ═══ WHY THIS FILE EXISTS ═══
 *
 * Standing notice 34: method notes about our pipeline — "last number is when we
 * last saw…" — may not appear in a page body. `TournamentProps` answered that
 * for the props cards in #4278 by switching to the `dot` variant UX-P154 had
 * already built: a mark you can see, with the whole sentence in a tooltip and
 * an `sr-only` label, which is exactly where notice 34 says a method note goes.
 *
 * The match slate and the contender boards print the SAME sentence
 * (`slateRowFreshnessLabel`, `rowFreshnessLabel`) and had no such treatment.
 * #4283 is that gap. The one thing it must not do is invent a fourth glyph:
 * `LiquidityMark`'s own header puts it plainly — *"a fifth surface-specific
 * glyph is how a signal stops being a signal"*. So the props `dot` moved here
 * and all three surfaces render this component. It is a move, not a copy.
 *
 * ═══ WHY IT IS A SOLID DOT AND NOT A RING ═══
 *
 * `LiquidityMark` is a HOLLOW ring in muted grey and this is a SOLID dot in
 * amber, and that pair is deliberate — the two facts are different (a number
 * can be minutes old and still come off a market nobody will trade at) and
 * they sit on the same honesty line. Painting them alike would teach a reader
 * that they mean one thing. That reasoning is `LiquidityMark`'s, recorded at
 * the top of that file; this is the other half of the same decision.
 *
 * ═══ THE PREFIX IS THE WHOLE POINT OF `label` BEING A PROP ═══
 *
 * 🔴 The caller passes the COMPLETE admission, prefix included. #4278 shipped
 * within an inch of the CERT-411 round-2 falsehood by building the tooltip out
 * of the bare age and dropping "which leg is old" on the floor: a two-leg row
 * whose other half refreshed an hour ago would have claimed the whole row was
 * 35 days stale. The visible mark has no room for a name — a fixed-width mark
 * is the point — so the tooltip and the `sr-only` copy are the ONLY places
 * that fact can live, and they carry it in full or the mark is a lie.
 */

export type FreshnessTone = "quiet" | "muted";

/** "32h" / "20d" / "—". The mark labels itself in the tooltip, not here. */
export function compactAge(ageHours: number | null): string {
  if (ageHours === null || !Number.isFinite(ageHours)) return "—";
  if (ageHours < 48) return `${Math.floor(ageHours)}h`;
  return `${Math.floor(ageHours / 24)}d`;
}

export function FreshnessDot({
  label,
  ageHours,
  tone = "quiet",
  testId,
  state,
  className,
}: {
  /** The complete admission, prefix and all. Tooltip + screen reader only. */
  label: string;
  ageHours: number | null;
  tone?: FreshnessTone;
  testId?: string;
  /** Passed through for the guards that already read it on the props chip. */
  state?: string;
  className?: string;
}) {
  const toneClass = tone === "quiet" ? "text-accent-warning" : "text-text-muted";
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1 text-[10.5px] tabular-nums ${toneClass} ${
        className ?? ""
      }`}
      data-testid={testId}
      data-variant="dot"
      data-state={state}
      title={label}
    >
      <span
        aria-hidden="true"
        className={`h-1.5 w-1.5 rounded-full ${
          tone === "quiet" ? "bg-accent-warning" : "bg-text-muted"
        }`}
      />
      <span className="sr-only">{label}. </span>
      <span aria-hidden="true">{compactAge(ageHours)}</span>
    </span>
  );
}
