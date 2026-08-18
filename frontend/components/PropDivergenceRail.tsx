"use client";

/**
 * THE DIVERGENCE — the pregame mark vs where a prop is now.
 *
 * UX-P098 (UX-AMBITION-1, slice 1). Alex's ruled verdicts, via Fable:
 *   V1  lead with five live questions; the full prop set sits behind one expand
 *   V2  every row is a travelled bar; surprising rows ADDITIONALLY get a sentence
 *   V3  a prop lost to no trading may vanish silently; anything else must surface
 *
 * All selection logic lives in `lib/propDivergence.ts` and is unit-tested
 * against a real production payload. This file is rendering only.
 */

import { useMemo } from "react";
import {
  selectDivergenceRows,
  type DivergenceRow,
  type PropDropReason,
} from "@/lib/propDivergence";
import type { PlayerPropRow } from "@/lib/playerPropsGrouping";

interface Props {
  playerProps?: readonly PlayerPropRow[] | null;
  status?: string | null;
}

const REASON_LABEL: Record<PropDropReason, string> = {
  no_real_price: "no trading",
  outside_band: "already decided",
  misclassified: "couldn't be read",
  wrong_game: "linked to another game",
  ungraded: "settled but never graded",
  unknown: "unknown",
};

function pct(p: number): string {
  return `${Math.round(p * 100)}%`;
}

/**
 * One row's bar. Domain is fixed 0-100% so rows are comparable to each other
 * and to the native chart's single-axis convention.
 */
function TravelBar({ row }: { row: DivergenceRow }) {
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

export default function PropDivergenceRail({ playerProps, status }: Props) {
  const result = useMemo(
    () => selectDivergenceRows({ playerProps, status }),
    [playerProps, status],
  );

  // Nothing eligible AND nothing went wrong: the page says nothing rather than
  // announcing an absence. A poisoned empty is handled below, not here.
  if (result.rows.length === 0 && result.nonBenignCount === 0) return null;

  const nonBenign = result.dropped.filter((d) => !d.benign);

  return (
    <div className="bg-surface-card rounded-card shadow-card overflow-hidden">
      <div className="px-4 sm:px-5 py-3 border-b border-surface-border/30 flex items-baseline justify-between gap-3">
        <h3 className="text-[13px] font-semibold text-text-primary">
          {result.rows.some((r) => r.settled) ? "How the props moved" : "What's moving"}
        </h3>
        {result.eligible > result.rows.length && (
          <span className="text-[11px] text-text-muted">
            {result.rows.length} of {result.eligible}
          </span>
        )}
      </div>

      <div className="px-4 sm:px-5 py-3 space-y-3.5">
        {result.rows.map((row) => (
          <div key={row.key}>
            {/* V2: the sentence is an ESCALATION above its bar, never a
                replacement for it. Surprising rows get both. */}
            {row.sentence && (
              <p className="text-[13px] leading-snug text-text-primary">
                {row.sentence}
              </p>
            )}
            <p
              className={`text-[12px] text-text-secondary ${row.sentence ? "mt-0.5" : ""}`}
            >
              {row.label}
            </p>
            <TravelBar row={row} />
          </div>
        ))}

        {/* V3: a non-benign loss must reach the screen. We do not claim "no
            trading" for something we could not read — that is the invention
            gotcha #53 forbids. */}
        {nonBenign.length > 0 && (
          <p className="text-[11px] text-text-muted border-t border-surface-border/30 pt-2.5">
            {result.rows.length === 0
              ? "These props couldn't be shown: "
              : "Also not shown: "}
            {nonBenign
              .map((d) => `${d.count} ${REASON_LABEL[d.reason]}`)
              .join(", ")}
            .
          </p>
        )}
      </div>
    </div>
  );
}
