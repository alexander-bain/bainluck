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
 *   3. one block per team of labelled metric pairs (`matrix.groups`), each pair
 *      side by side when it fits and one value per line when it does not.
 *
 * An accessibility text size goes straight to 3 (native
 * `arrangements(accessibilitySize:)`). The lead column — the current chance
 * during play, else the first (`matrix.lead`) — is the largest figure, in the
 * team's colour. Figures never shrink or wrap; absence words wrap as words.
 *
 * "Fits" is measured, not assumed: after each render the frame's scroll width is
 * compared with its own width before paint, and a grid that overflows steps to
 * the next arrangement. A width change starts again from 1. Web has no Dynamic
 * Type category, so an accessibility size is read the way `usePlotBox`
 * (NFLEventCards.tsx) reads enlarged text — the root font size — at or above
 * `ACCESSIBILITY_ROOT_FONT_PX` (150% of the 16 px default).
 *
 * Each column's source and clock is printed here only when `inlineProvenance`
 * is set; the page leaves them to About once it has verified About carries
 * every one (`provenanceInAbout`).
 */

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type {
  HockeyJourneyHeadline,
  HockeyJourneySlot,
  HockeyJourneyTeam,
} from "@/lib/eventPage10868/hockeyJourneyTypes";

export type HockeyJourneyMatrixArrangement = "grid" | "shortGrid" | "pairs";

/** Root font size, in CSS px, from which text counts as an accessibility size (150% of 16 px). */
export const ACCESSIBILITY_ROOT_FONT_PX = 24;

/** The arrangements to try, in order (native `arrangements(accessibilitySize:)`). */
export function matrixArrangements(accessibilitySize: boolean): HockeyJourneyMatrixArrangement[] {
  return accessibilitySize ? ["pairs"] : ["grid", "shortGrid", "pairs"];
}

const useIsomorphicLayoutEffect = typeof window === "undefined" ? useEffect : useLayoutEffect;

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
}: {
  headline: HockeyJourneyHeadline;
  /** Print each column's source and clock under the matrix (false once About holds them all). */
  inlineProvenance?: boolean;
}) {
  const { matrix } = headline;
  const teams: Record<"home" | "away", HockeyJourneyTeam> = { home: headline.home, away: headline.away };
  const provenance = inlineProvenance ? matrix.columns.filter((c) => c.provenance) : [];

  const frame = useRef<HTMLDivElement>(null);
  const measured = useRef({ width: -1, accessibilitySize: false });
  const [width, setWidth] = useState(0);
  const [accessibilitySize, setAccessibilitySize] = useState(false);
  const [step, setStep] = useState(0);
  // A short grid identical to the full one is not a different arrangement.
  const order = matrixArrangements(accessibilitySize).filter(
    (a) => a !== "shortGrid" || !!(headline.home.short || headline.away.short),
  );
  const arrangement = order[Math.min(step, order.length - 1)];

  // Width and text size: read now and on every resize; a new width or text size starts over at the first arrangement.
  useEffect(() => {
    const el = frame.current;
    if (!el) return;
    const read = () => {
      const root = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
      const large = root >= ACCESSIBILITY_ROOT_FONT_PX;
      const w = el.clientWidth;
      if (w === measured.current.width && large === measured.current.accessibilitySize) return;
      measured.current = { width: w, accessibilitySize: large };
      setStep(0);
      setWidth(w);
      setAccessibilitySize(large);
    };
    read();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(read);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Fit: a grid wider than its frame steps to the next arrangement before paint.
  useIsomorphicLayoutEffect(() => {
    const el = frame.current;
    if (!el || arrangement === "pairs") return;
    if (el.scrollWidth > el.clientWidth + 1) setStep((s) => s + 1);
  }, [arrangement, width, accessibilitySize]);

  const short = arrangement === "shortGrid";

  return (
    <div className="space-y-3" data-hockey-matrix={matrix.phase}>
      <div ref={frame} className="w-full overflow-x-auto" data-arrangement={arrangement}>
        {arrangement === "pairs" ? (
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
                  {matrix.groups.map((group) => (
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
                {matrix.columns.map((column) => (
                  <th key={column.title} scope="col" className="px-1 py-2 text-center align-bottom text-sm font-semibold text-text-secondary">
                    <span className="mx-auto block min-w-16 max-w-[7.5rem]">{column.title}</span>
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
                    {row.values.map((slot, i) => (
                      <td key={matrix.columns[i]?.title ?? i} className="px-1 py-3 text-center align-middle">
                        <span className="mx-auto block min-w-16 max-w-[7.5rem]">
                          <SlotValue slot={slot} lead={i === matrix.lead} tint={team.tint} />
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
