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
 *
 * ═══ WHAT A RUNG PRINTS (#7687) ═══
 *
 * The probability went through a bare `renderedPercent`, so a rung strictly
 * inside (0, 1) could print `0%` or `100%` — UX-P046's boundary rule, which
 * every other percentage on the site already obeys, had never been applied
 * here. It is live at both ends on this block: one Red Sox event page served
 * `make_playoffs` at 0.9972 in the same list as rungs at 0.001. It now prints
 * through `formatProbabilityPercent`, so a rung that is merely close to an
 * absolute says `>99%` or `<1%` and only a genuine 0 or 1 prints as one.
 */

import { motion } from "@/components/motion";
import { fadeIn } from "@/lib/animations";
import { formatProbabilityPercent } from "@/lib/probabilityDisplay";
import { ADVERSE_COLUMN_KEYS, risingIsGood } from "@/lib/gridColumnPolarity";

/** One stage on the path. */
export interface AdvancementStage {
  /** The destination, in words — "Quarter-finals", "Win division". */
  label: string;
  /** 0–1. */
  prob: number;
  /** Move over the last 24h, 0–1, or `null` when nothing was measured twice. */
  change: number | null;
  /**
   * Already secured — printed as `✓ clinched` rather than as 100%.
   *
   * #7687: this must come from something that REPORTS a settlement. Both
   * callers now pass a constant `false` for want of one, because neither
   * payload carries the state: `TournamentExtensions` refused a price
   * threshold from the start, and `RelatedFutures` derived one at `>= 0.995`
   * until production showed it could only fire on rungs that were not settled
   * (its call site carries the measurement). The prop stays because the block
   * genuinely has a clinched state to draw once a payload reports one; what it
   * may not be is inferred from how big the number is.
   */
  resolved: boolean;
  /**
   * The grid column this rung came from — `relegation`, `top_4`, `championship`
   * — when the caller has one. Structured, from `league_configs.py` by way of
   * `league_context.columns[].key`, NOT parsed back out of `label`: the label
   * is a display string that translates and re-words, and a classifier keyed on
   * it would misfile every rung whose wording moved. Absent where the caller
   * has no structured key (the raw-futures fallback, the tennis register), and
   * absence is read as "unknown", never as "fine".
   */
  columnKey?: string;
}

/**
 * Grid columns that are NOT a rung on the way to a title (#7206).
 *
 * This is the same set, held once, that says which way is up for a column's
 * 24h move (#7745) — see `lib/gridColumnPolarity`, which carries the vocabulary
 * survey behind it and the note on when the two questions would have to split.
 * Two sets of one string each, in two files, both meaning "relegation is the
 * odd one out", is how they stop agreeing.
 */
export const NON_ADVANCEMENT_STAGE_KEYS: ReadonlySet<string> = ADVERSE_COLUMN_KEYS;

/** The heading a ladder of rungs toward a title gets. */
export const CHAMPIONSHIP_PATH_HEADING = "CHAMPIONSHIP PATH";

/**
 * The heading a ladder gets once it holds a rung that is not one.
 *
 * "Relegated 78.5% / Top 4 4% / Champion 1%" is a true and useful list. What it
 * is not is a *path to a championship*, and a heading that says so is reading
 * the reader a different block from the one under it.
 */
export const SEASON_OUTCOMES_HEADING = "SEASON OUTCOMES";

/**
 * The heading these rungs can honestly carry.
 *
 * ═══ WHY THIS LIVES IN THE COMPONENT AND NOT AT THE CALL SITE (#7206) ═══
 *
 * The defect was one caller passing a ladder whose first and largest rung was
 * `Relegated` under the default heading `CHAMPIONSHIP PATH` — on production,
 * `/events/15305209` at 390px, Coventry City's card read **CHAMPIONSHIP PATH /
 * Relegated 78.5%**. Fixing it where that caller builds its rows would have
 * worked and would have been undefended: the relationship "this heading is only
 * true of these rungs" would have lived in the distance between two files, and
 * the next caller to pass a season-outcomes ladder would print the same
 * sentence again with nothing going red.
 *
 * So the component refuses to print the claim instead. A block holding a
 * non-advancement rung IS a season-outcomes block whatever its caller wanted to
 * call it, so the downgrade is unconditional rather than a rewrite of headings
 * that happen to contain the word "championship" — there is no string test here
 * and nothing to keep in step with a re-wording.
 *
 * Callers with no structured key are untouched: `TournamentExtensions`' tennis
 * rounds carry no `columnKey`, so `CHANCE OF REACHING` survives, and so does
 * every league whose columns are all rungs.
 */
export function advancementHeading(
  stages: AdvancementStage[],
  requested: string,
): string {
  const holdsNonAdvancement = stages.some(
    (s) => s.columnKey != null && NON_ADVANCEMENT_STAGE_KEYS.has(s.columnKey),
  );
  return holdsNonAdvancement ? SEASON_OUTCOMES_HEADING : requested;
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
  heading = CHAMPIONSHIP_PATH_HEADING,
  testId,
}: {
  stages: AdvancementStage[];
  /** The block's own label. Tennis says what it means; a league says its own. */
  heading?: string;
  testId?: string;
}) {
  if (stages.length === 0) return null;

  // #7206. The rungs get the last word on what the block may call itself.
  const effectiveHeading = advancementHeading(stages, heading);

  return (
    <>
      <div
        className="text-[10px] font-semibold uppercase tracking-wide text-text-muted mb-2"
        data-testid={testId ? `${testId}-heading` : undefined}
      >
        {effectiveHeading}
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
                    // The ARROW says which way the number moved; the COLOUR says
                    // whether that is good news for this rung, and on a
                    // `Relegated` rung those are opposite answers (#7745).
                    (p.change > 0) === risingIsGood(p.columnKey)
                      ? "text-accent-brand"
                      : "text-accent-danger"
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
                {p.resolved ? "✓ clinched" : formatProbabilityPercent(p.prob)}
              </span>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
