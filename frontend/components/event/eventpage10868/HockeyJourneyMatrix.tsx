"use client";

/**
 * #10868 — the hockey journey's paired comparison matrix (web).
 *
 * Draws `HockeyJourneyHeadline.matrix` and nothing else: every value, column
 * title and provenance line is the view model's (lib/eventPage10868). The
 * RESPONSIVE HIERARCHY is native `HockeyJourneyHeadline10868`'s
 * (HockeyJourneyEventPagePresentation10868.swift `matrix` / `grid` /
 * `labelledPairs`), tried in order, the first that fits whole being drawn:
 *
 *   1. aligned columns with full team names;
 *   2. aligned columns with the owner's short names (`teamShortNames`, the
 *      headline's `short`; a team without one keeps its full name);
 *   2b. OPT-IN ONLY (`compactColumns`, default off): the same aligned columns
 *      with short names and each column sized by its own content — no 4rem
 *      per-column floor and 2px rather than 4px side padding. Type sizes are
 *      unchanged. A caller that does not pass `compactColumns` never reaches
 *      it: its arrangements, classes and fit key are exactly as before;
 *   2c. OPT-IN ONLY, next (`compactNamesAbove`): the same content-sized
 *      aligned columns with NO team column — each team's FULL name (and its
 *      Won/Lost) sits on its own row above that team's values, spanning the
 *      columns and wrapping as words. Each team is its own `<tbody>`: the name
 *      is a `scope="rowgroup"` header and every value cell also names its
 *      column and its team through `headers`. Same values, labels, order and
 *      type sizes; nothing is elided, hidden or scrolled. It exists for a
 *      final whose single-word team names leave no room for a name column
 *      (Bucs–Steelers at a 375px phone);
 *   3. one block per team of labelled metric pairs (`matrix.groups`), each pair
 *      side by side when it fits and one value per line when it does not.
 *
 * An accessibility text size goes straight to 3 (native
 * `arrangements(accessibilitySize:)`). The lead column — the current chance
 * during play, else the first (`matrix.lead`) — is the largest figure, in the
 * team's colour. Figures never shrink or wrap; absence words wrap as words.
 *
 * "Fits" is measured, not assumed: the frame's scroll width is compared with
 * its own width before paint, and a grid that overflows steps to the next
 * arrangement. The search starts again from 1 whenever what it is fitting
 * changes — the frame's width, the text size, OR THE MATRIX'S OWN CONTENT
 * (`matrixFitContent`: phase, columns, printed values, names, results) — so a
 * before → live change at the same viewport that widens the grid falls back,
 * and a later, narrower final climbs back to full names, with no remount and no
 * resize. The step is derived per fit key during render, so a stale fallback is
 * never drawn for new content. Web has no Dynamic
 * Type category, so an accessibility size is read the way `usePlotBox`
 * (NFLEventCards.tsx) reads enlarged text — the root font size — at or above
 * `ACCESSIBILITY_ROOT_FONT_PX` (150% of the 16 px default).
 *
 * A column with NO value for either team, whose two absence words are the same
 * (`matrixSharedAbsences` — a channel missing for the whole game, not for one
 * side), leaves the grid and the team blocks and is stated once beneath them,
 * under "Both teams", in column order with its own title and words. Nothing is
 * dropped, only not repeated per team: a degraded live read keeps its chance
 * rows compact, so the history starts on a phone's first screen. A column with
 * a value for either team, or different words per team, stays in the grid. No
 * metric column left and no result: no grid at all, only the shared lines.
 *
 * Each column's source and clock is printed here only when `inlineProvenance`
 * is set; the page leaves them to About once it has verified About carries
 * every one (`provenanceInAbout`).
 */

import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import type {
  HockeyJourneyHeadline,
  HockeyJourneySlot,
  HockeyJourneyTeam,
} from "@/lib/eventPage10868/hockeyJourneyTypes";
import { ACCESSIBILITY_ROOT_FONT_PX } from "./useFrameMeasure";

export type HockeyJourneyMatrixArrangement = "grid" | "shortGrid" | "compactGrid" | "compactNamesAbove" | "pairs";

/** The label over the columns stated once for both teams. */
export const BOTH_TEAMS_LABEL = "Both teams";

// One threshold for the whole screen (the card's rail and chooser, the chart's axis use it too).
export { ACCESSIBILITY_ROOT_FONT_PX };

/**
 * The arrangements to try, in order (native `arrangements(accessibilitySize:)`).
 * `compactColumns` (opt-in, default off) inserts the content-sized grid before
 * the labelled pairs; an accessibility text size still goes straight to pairs.
 */
export function matrixArrangements(accessibilitySize: boolean, compactColumns = false): HockeyJourneyMatrixArrangement[] {
  if (accessibilitySize) return ["pairs"];
  return compactColumns
    ? ["grid", "shortGrid", "compactGrid", "compactNamesAbove", "pairs"]
    : ["grid", "shortGrid", "pairs"];
}

const useIsomorphicLayoutEffect = typeof window === "undefined" ? useEffect : useLayoutEffect;

/**
 * Everything in the headline that can change the matrix's width: the phase,
 * the lead and groups, each column title, each printed value or absence, the
 * team names (full and short) and the result words. Two headlines with the same
 * signature lay out alike; any change re-runs the fit from full names.
 */
export function matrixFitContent(headline: HockeyJourneyHeadline): string {
  const { matrix } = headline;
  return JSON.stringify([
    matrix.phase,
    matrix.lead,
    matrix.groups,
    matrix.columns.map((c) => c.title),
    matrix.rows.map((r) => [r.side, r.values.map((v) => v.text), r.result]),
    [headline.home.name, headline.home.short, headline.away.name, headline.away.short],
  ]);
}

/**
 * The columns absent for BOTH teams in the same words, in column order: stated
 * once under the grid instead of in every team's row or block.
 */
export function matrixSharedAbsences(matrix: HockeyJourneyHeadline["matrix"]): number[] {
  return matrix.columns.flatMap((_, i) => {
    const [home, away] = matrix.rows.map((row) => row.values[i]);
    return home?.kind === "absent" && away?.kind === "absent" && home.text === away.text ? [i] : [];
  });
}

function SlotValue({ slot, lead, tint }: { slot: HockeyJourneySlot; lead: boolean; tint: string | null }) {
  if (slot.kind === "absent") {
    return <span className="text-sm font-medium text-text-secondary break-words">{slot.text}</span>;
  }
  return (
    <>
      <span
        aria-hidden="true"
        className={`${lead ? "text-3xl" : "text-xl"} whitespace-nowrap font-bold tabular-nums leading-tight ${
          lead && tint ? "" : "text-text-primary"
        }`}
        style={lead && tint ? { color: tint } : undefined}
      >
        {slot.text}
      </span>
      <span className="sr-only">{slot.spoken}</span>
    </>
  );
}

function ResultChip({ result }: { result: string | null }) {
  if (!result) return null;
  return (
    <span
      className={`whitespace-nowrap rounded-full border border-surface-border px-2 py-0.5 text-sm ${
        result === "Won" ? "bg-surface-elevated font-semibold text-text-primary" : "text-text-secondary"
      }`}
    >
      {result}
    </span>
  );
}

export default function HockeyJourneyMatrix({
  headline,
  inlineProvenance = true,
  compactColumns = false,
}: {
  headline: HockeyJourneyHeadline;
  /** Print each column's source and clock under the matrix (false once About holds them all). */
  inlineProvenance?: boolean;
  /**
   * Opt-in: try the content-sized grids (`compactGrid`, then `compactNamesAbove`)
   * before falling back to labelled pairs.
   */
  compactColumns?: boolean;
}) {
  const { matrix } = headline;
  const teams: Record<"home" | "away", HockeyJourneyTeam> = { home: headline.home, away: headline.away };
  const provenance = inlineProvenance ? matrix.columns.filter((c) => c.provenance) : [];
  const shared = matrixSharedAbsences(matrix);
  const kept = matrix.columns.map((_, i) => i).filter((i) => !shared.includes(i));
  const groups = matrix.groups.map((group) => group.filter((i) => kept.includes(i))).filter((group) => group.length > 0);
  const drawGrid = kept.length > 0 || matrix.rows.some((row) => row.result);
  const sharedLabelId = useId();
  const tableId = useId();

  const frame = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  const [accessibilitySize, setAccessibilitySize] = useState(false);
  // What the fit search is for: this content, at this width, at this text size.
  // A step found for another key is never reused — the search restarts at full
  // names in the same render that brings the new content (expansion OR contraction).
  const fitKey = `${matrixFitContent(headline)}|${width}|${accessibilitySize ? "large" : "standard"}${
    compactColumns ? "|compact" : ""
  }`;
  const [fit, setFit] = useState({ key: fitKey, step: 0 });
  const step = fit.key === fitKey ? fit.step : 0;
  // A short grid identical to the full one is not a different arrangement.
  const order = matrixArrangements(accessibilitySize, compactColumns).filter(
    (a) => a !== "shortGrid" || !!(headline.home.short || headline.away.short),
  );
  const arrangement = order[Math.min(step, order.length - 1)];

  // Width and text size: read now and on every resize. Unchanged values bail out.
  useEffect(() => {
    const el = frame.current;
    if (!el) return;
    const read = () => {
      const root = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
      setWidth(el.clientWidth);
      setAccessibilitySize(root >= ACCESSIBILITY_ROOT_FONT_PX);
    };
    read();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(read);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Fit, before paint: measure what this render drew for this key; a grid wider
  // than its frame steps to the next arrangement. Runs whenever the key or the
  // drawn arrangement changes, so new headline content is always measured.
  useIsomorphicLayoutEffect(() => {
    const el = frame.current;
    if (!el || arrangement === "pairs" || !drawGrid) return;
    if (el.scrollWidth > el.clientWidth + 1) setFit({ key: fitKey, step: step + 1 });
  }, [arrangement, drawGrid, fitKey, step]);

  const short = arrangement === "shortGrid" || arrangement === "compactGrid";
  // Only the opt-in compact grid changes a class; every other arrangement keeps today's exact strings.
  const namesAbove = arrangement === "compactNamesAbove";
  const compact = arrangement === "compactGrid" || namesAbove;
  const cell = compact ? "mx-auto block min-w-0 max-w-[7.5rem]" : "mx-auto block min-w-16 max-w-[7.5rem]";
  const pad = compact ? "px-0.5" : "px-1";

  return (
    <div className="space-y-3" data-hockey-matrix={matrix.phase}>
      <div ref={frame} hidden={!drawGrid} className="w-full overflow-x-auto" data-arrangement={arrangement}>
        {!drawGrid ? null : namesAbove ? (
          <table className="w-full border-collapse" data-names-above="">
            <caption className="sr-only">{headline.spokenLabel}</caption>
            <thead>
              <tr className="border-b border-surface-border">
                {kept.map((i) => (
                  <th
                    key={matrix.columns[i].title}
                    id={`${tableId}-c${i}`}
                    scope="col"
                    className={`${pad} py-2 text-center align-bottom text-sm font-semibold text-text-secondary`}
                  >
                    <span className={cell}>{matrix.columns[i].title}</span>
                  </th>
                ))}
              </tr>
            </thead>
            {matrix.rows.map((row) => {
              const team = teams[row.side];
              const nameId = `${tableId}-${row.side}`;
              return (
                <tbody key={row.side} data-side={row.side} className="border-b border-surface-border last:border-b-0">
                  <tr>
                    <th id={nameId} scope="rowgroup" colSpan={Math.max(1, kept.length)} className="pt-3 text-left align-middle text-base">
                      <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                        <span className="break-words font-semibold" style={team.tint ? { color: team.tint } : undefined}>
                          {team.name}
                        </span>
                        <ResultChip result={row.result} />
                      </span>
                    </th>
                  </tr>
                  {kept.length > 0 && (
                    <tr>
                      {kept.map((i) => (
                        <td
                          key={matrix.columns[i].title}
                          headers={`${tableId}-c${i} ${nameId}`}
                          className={`${pad} pb-3 pt-1 text-center align-middle`}
                        >
                          <span className={cell}>
                            <SlotValue slot={row.values[i]} lead={i === matrix.lead} tint={team.tint} />
                          </span>
                        </td>
                      ))}
                    </tr>
                  )}
                </tbody>
              );
            })}
          </table>
        ) : arrangement === "pairs" ? (
          <div className="space-y-4">
            {matrix.rows.map((row) => {
              const team = teams[row.side];
              return (
                <div key={row.side} role="group" aria-label={team.name} className="rounded-lg bg-surface-deep p-3">
                  <p className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                    <span className="break-words text-lg font-bold" style={team.tint ? { color: team.tint } : undefined}>
                      {team.name}
                    </span>
                    <ResultChip result={row.result} />
                  </p>
                  {groups.map((group) => (
                    // One comparison pair: side by side when it fits, one value per line when not.
                    <dl key={group.join(":")} className="mt-2 flex flex-wrap gap-x-6 gap-y-2">
                      {group.map((column) => (
                        <div key={matrix.columns[column]?.title ?? column} className="min-w-0">
                          <dt className="text-sm font-medium text-text-secondary">{matrix.columns[column]?.title}</dt>
                          <dd className="mt-0.5">
                            <SlotValue slot={row.values[column]} lead={column === matrix.lead} tint={team.tint} />
                          </dd>
                        </div>
                      ))}
                    </dl>
                  ))}
                </div>
              );
            })}
          </div>
        ) : (
          <table className="w-full border-collapse">
            <caption className="sr-only">{headline.spokenLabel}</caption>
            <thead>
              <tr className="border-b border-surface-border">
                <th scope="col" className="py-2 pr-2 text-left">
                  <span className="sr-only">Team</span>
                </th>
                {kept.map((i) => (
                  <th key={matrix.columns[i].title} scope="col" className={`${pad} py-2 text-center align-bottom text-sm font-semibold text-text-secondary`}>
                    <span className={cell}>{matrix.columns[i].title}</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {matrix.rows.map((row) => {
                const team = teams[row.side];
                const label = short && team.short ? team.short : team.name;
                return (
                  <tr key={row.side} className="border-b border-surface-border last:border-b-0">
                    <th scope="row" className="py-3 pr-2 text-left align-middle text-base">
                      <span className="flex flex-col items-start gap-1">
                        <span className="whitespace-nowrap font-semibold" style={team.tint ? { color: team.tint } : undefined}>
                          <span aria-hidden={label !== team.name ? true : undefined}>{label}</span>
                          {label !== team.name && <span className="sr-only">{team.name}</span>}
                        </span>
                        <ResultChip result={row.result} />
                      </span>
                    </th>
                    {kept.map((i) => (
                      <td key={matrix.columns[i].title} className={`${pad} py-3 text-center align-middle`}>
                        <span className={cell}>
                          <SlotValue slot={row.values[i]} lead={i === matrix.lead} tint={team.tint} />
                        </span>
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {shared.length > 0 && (
        <div role="group" aria-labelledby={sharedLabelId} data-matrix-shared-absences="" className="text-sm">
          <p id={sharedLabelId} className="font-semibold text-text-primary">
            {BOTH_TEAMS_LABEL}
          </p>
          <dl className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-text-secondary">
            {shared.map((i) => (
              <div key={matrix.columns[i].title} className="flex min-w-0 flex-wrap gap-x-1">
                <dt className="font-medium">{matrix.columns[i].title}:</dt>
                <dd className="min-w-0 break-words">{matrix.rows[0].values[i].text}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      {provenance.length > 0 && (
        <dl className="space-y-1 text-sm text-text-secondary">
          {provenance.map((column) => (
            <div key={column.title} className="flex flex-wrap gap-x-1">
              <dt className="font-medium text-text-primary">{column.title}:</dt>
              <dd className="min-w-0 break-words">{column.provenance}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}
