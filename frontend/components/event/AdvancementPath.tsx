"use client";

/**
 * ADVANCEMENT PATH — one competitor's chance of reaching each later stage.
 *
 * ═══ WHAT THIS IS AND WHY IT IS ITS OWN FILE (UX-P152) ═══
 *
 * Alex, 2026-08-28: *"During an MLB game, don't we show the odds of each team
 * advancing to each stage of the playoff grid?"*
 *
 * Yes — this block.  It is the `CHAMPIONSHIP PATH` list inside each team's card
 * in the Related Futures section of an event page: one row per stage, a label,
 * a bar, the probability, the 24h move, and `✓ clinched` once a stage is
 * secured.  Until now it existed **twice**, copied verbatim for the home card
 * and the away card in `RelatedFutures.tsx`, and it had a decoy: a
 * `GridPlayoffPathPair` component written for `/api/events/{id}/team-progression`,
 * fully plumbed from the event page down, and **never mounted**.  That decoy
 * is why "what does the MLB page show?" has two plausible answers in the code
 * and only one on screen.
 *
 * So this is the one that ships, lifted out once, and now rendered by both
 * callers:
 *
 *   * `RelatedFutures` — a team's playoff stages, from the related-futures
 *     markets (unchanged behaviour; two copies became two calls).
 *   * `TournamentExtensions` — a tennis player's chance of reaching each round
 *     of the draw, from the tournament register's pinned reach cells.
 *
 * Alex asked for the tournament match to *"mirror that treatment ... same
 * component family if one exists, so the pattern stays consistent app-wide"*.
 * One component with two callers is the strongest available form of that: the
 * two surfaces cannot drift, because there is nothing to drift.
 */

import { motion } from "@/components/motion";
import { fadeIn } from "@/lib/animations";

/** One stage on the path. */
export interface AdvancementStage {
  /** The destination, in words — "Quarter-finals", "Win division". */
  label: string;
  /** 0–1. */
  prob: number;
  /** Move over the last 24h, 0–1, or `null` when nothing was measured twice. */
  change: number | null;
  /** Already secured — printed as `✓ clinched` rather than as 100%. */
  resolved: boolean;
}

/**
 * A move smaller than this is noise, not a story.
 *
 * Lifted with the markup from `RelatedFutures`, where it was an inline
 * `0.005`. Named here because the same dead band now governs two surfaces and
 * an unnamed constant duplicated across files is how they stop agreeing.
 */
export const MOVE_DEAD_BAND = 0.005;

export default function AdvancementPath({
  stages,
  heading = "CHAMPIONSHIP PATH",
  testId,
}: {
  stages: AdvancementStage[];
  /** The block's own label. Tennis says what it means; a league says its own. */
  heading?: string;
  testId?: string;
}) {
  if (stages.length === 0) return null;

  return (
    <>
      <div className="text-[10px] font-semibold uppercase tracking-wide text-text-muted mb-2">
        {heading}
      </div>
      <div className="space-y-0.5 mb-5" data-testid={testId}>
        {stages.map((p) => (
          <div
            key={p.label}
            className="flex items-center gap-3 py-1.5"
            data-testid="advancement-stage"
            data-stage={p.label}
            data-probability={p.prob}
          >
            <div className="text-sm w-36 shrink-0 text-text-secondary">{p.label}</div>
            <div className="flex-1 h-2 rounded-full bg-surface-border overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  p.resolved ? "bg-accent-live" : "bg-violet-400"
                }`}
                style={{ width: `${p.resolved ? 100 : p.prob * 100}%` }}
              />
            </div>
            <div className="w-28 text-right flex items-center justify-end gap-2">
              {p.change != null && Math.abs(p.change) >= MOVE_DEAD_BAND && (
                <span
                  className={`text-xs font-mono tabular-nums ${
                    p.change > 0 ? "text-accent-brand" : "text-accent-danger"
                  }`}
                >
                  {p.change > 0 ? "↑" : "↓"}{" "}
                  {(Math.abs(p.change) * 100).toFixed(1)}%
                </span>
              )}
              <span
                className={`font-mono tabular-nums text-sm font-bold ${
                  p.resolved ? "text-accent-live" : ""
                }`}
              >
                {p.resolved ? "✓ clinched" : `${Math.round(p.prob * 100)}%`}
              </span>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
