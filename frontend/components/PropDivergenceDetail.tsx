"use client";

/**
 * THE DIVERGENCE — detail view (UX-AMBITION-1, slice 2).
 *
 * V1's other half: "the full prop set sits behind a single expand". The rail
 * answers *what should I look at*; this answers *what else is there*. On the
 * ratified mock's own game that is 95 questions the rail cannot reach.
 *
 * Transcribed from Mock 2 in `docs/mockups/event-props-script-divergence-mock.html`
 * (Cardinals @ Reds, event 14788546 — the same payload now fixtured):
 *
 *   - a count badge, "34 off script"
 *   - rows ordered by distance from the pregame mark
 *   - the grey tick is what the script said, the head is where it is now
 *   - "props still on script are below the fold"
 *
 * V2's escalation is unchanged across the fold: every row is a bar, and a row
 * clearing the measured surprise threshold ADDITIONALLY carries a sentence.
 * Selection lives in `lib/propDivergence.ts`; this file is rendering only.
 */

import { useMemo } from "react";
import {
  selectDivergenceDetail,
  type DivergenceRow,
  type PropDropReason,
} from "@/lib/propDivergence";
import type { PlayerPropRow } from "@/lib/playerPropsGrouping";
import { SETTLED_NO_GRADE_LABEL } from "@/lib/propGrade";
import PropTravelBar, {
  pct,
  resolutionLabel,
  signedTravelPoints,
  surprisePoints,
} from "./PropTravelBar";

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

function Row({ row, settled }: { row: DivergenceRow; settled: boolean }) {
  // The right-hand pill answers "how far from the script": in-game that is the
  // signed price move, post-game it is the distance from the mark to the
  // OUTCOME (#2011). `PropTravelBar` already carries the resolution and its
  // points, so the pill is suppressed post-game rather than duplicated.
  const pill = settled ? null : signedTravelPoints(row);
  const moveTone =
    row.direction === "over"
      ? "text-accent-live"
      : row.direction === "under"
        ? "text-accent-danger"
        : "text-text-muted";

  const outcome = resolutionLabel(row);
  const points = surprisePoints(row);

  return (
    <div>
      {/* V2: the sentence is an ESCALATION above its bar, never a replacement. */}
      {row.sentence && (
        <p className="text-[13px] leading-snug text-text-primary">{row.sentence}</p>
      )}
      <div
        className={`flex items-baseline justify-between gap-3 ${row.sentence ? "mt-0.5" : ""}`}
      >
        <p className="text-[12px] text-text-secondary">{row.label}</p>
        {pill && (
          <span className={`text-[12px] font-medium tabular-nums shrink-0 ${moveTone}`}>
            {pill}
          </span>
        )}
      </div>
      <PropTravelBar row={row} />
      <p className="sr-only">
        {settled && outcome
          ? `Script said ${pct(row.pregameMark)}; it ${
              row.resolution === 1 ? "happened" : "did not happen"
            }${points ? ` — ${points} from the mark` : ""}.`
          : `Script said ${pct(row.pregameMark)}, now ${pct(row.current)}.`}
      </p>
    </div>
  );
}

export default function PropDivergenceDetail({ playerProps, status }: Props) {
  const result = useMemo(
    () => selectDivergenceDetail({ playerProps, status }),
    [playerProps, status],
  );

  const nonBenign = result.dropped.filter((d) => !d.benign);

  // Nothing eligible AND nothing went wrong: say nothing rather than announce
  // an absence. A non-benign loss still has to reach the screen (V3).
  if (result.eligible === 0 && nonBenign.length === 0) return null;

  return (
    <div className="pt-1">
      {result.offScript.length > 0 && (
        <>
          <div className="flex items-baseline justify-between gap-3 pb-1">
            <h4 className="text-[12px] font-semibold text-text-primary">
              Off script
            </h4>
            <span className="text-[11px] text-text-muted tabular-nums">
              {result.offScriptCount} of {result.eligible}
            </span>
          </div>
          <div className="space-y-3.5">
            {result.offScript.map((row) => (
              <Row key={row.key} row={row} settled={result.settled} />
            ))}
          </div>
        </>
      )}

      {result.onScript.length > 0 && (
        <>
          <div className="flex items-baseline justify-between gap-3 pb-1 pt-4 mt-4 border-t border-surface-border/30">
            <h4 className="text-[12px] font-semibold text-text-primary">
              {result.settled ? "Went to script" : "Still on script"}
            </h4>
            <span className="text-[11px] text-text-muted tabular-nums">
              {result.onScript.length}
            </span>
          </div>
          <div className="space-y-3.5">
            {result.onScript.map((row) => (
              <Row key={row.key} row={row} settled={result.settled} />
            ))}
          </div>
        </>
      )}

      {/* #2011's named residual: a settled question with no readable verdict is
          its own group. Folding it into "Went to script" would assert how it
          landed — the claim we just established we cannot make. */}
      {result.ungraded.length > 0 && (
        <>
          <div className="flex items-baseline justify-between gap-3 pb-1 pt-4 mt-4 border-t border-surface-border/30">
            <h4 className="text-[12px] font-semibold text-text-primary">
              Not graded
            </h4>
            <span className="text-[11px] text-text-muted tabular-nums">
              {result.ungraded.length}
            </span>
          </div>
          {/* SAID ONCE, not once per row. `SETTLED_NO_GRADE_LABEL` on a hundred
              consecutive lines is the vocabulary drift #1650 punished, in its
              other direction: technically consistent, unreadable in practice.
              The questions themselves still all appear — completeness is this
              view's contract (V3). */}
          <p className="text-[11px] text-text-muted pb-1.5">
            {SETTLED_NO_GRADE_LABEL} — these questions settled without a published
            outcome, so there is no result to show against their mark.
          </p>
          <ul className="space-y-1">
            {result.ungraded.map((row) => (
              <li
                key={row.key}
                className="flex items-baseline justify-between gap-3 text-[12px] text-text-muted"
              >
                <span>{row.label}</span>
                <span className="tabular-nums shrink-0">
                  marked {pct(row.pregameMark)}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}

      <p className="text-[11px] text-text-muted pt-3 mt-3 border-t border-surface-border/30">
        {result.settled
          ? "Ordered by how far the outcome landed from the pregame mark."
          : "Ordered by distance from the pregame mark — the grey tick is what the script said, the marker is where it is now."}
      </p>

      {/* V3: a non-benign loss must reach the screen. We do not claim "no
          trading" for something we could not read — gotcha #53. */}
      {nonBenign.length > 0 && (
        <p className="text-[11px] text-text-muted pt-2">
          {result.eligible === 0
            ? "These props couldn't be shown: "
            : "Also not shown: "}
          {nonBenign.map((d) => `${d.count} ${REASON_LABEL[d.reason]}`).join(", ")}.
        </p>
      )}
    </div>
  );
}
