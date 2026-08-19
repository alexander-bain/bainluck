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

import { useMemo, useState } from "react";
import {
  selectDivergenceRows,
  type PropDropReason,
} from "@/lib/propDivergence";
import type { PlayerPropRow } from "@/lib/playerPropsGrouping";
import PropTravelBar from "./PropTravelBar";
import PropDivergenceDetail from "./PropDivergenceDetail";

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

export default function PropDivergenceRail({ playerProps, status }: Props) {
  const [expanded, setExpanded] = useState(false);
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
            <PropTravelBar row={row} />
          </div>
        ))}

        {/* V1: ONE expand, and only when it leads somewhere. `notSelected` is
            the rail's own accounting of what it could not fit — never a
            taxonomy loss, which is why it is safe to offer as a destination. */}
        {result.notSelected > 0 && (
          <div className="pt-1">
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              aria-expanded={expanded}
              className="text-[12px] font-medium text-accent-brand hover:underline"
            >
              {expanded
                ? "Show fewer"
                : `See all ${result.eligible} questions`}
            </button>
            {expanded && (
              <PropDivergenceDetail playerProps={playerProps} status={status} />
            )}
          </div>
        )}

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
