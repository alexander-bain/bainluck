"use client";

/**
 * PlacementGrid — one tournament, players down, placement questions across.
 *
 * UX-1052 item 3. Alex, shopping /sports on 2026-09-03: five near-identical
 * cards for the Omega European Masters (Winner / Top 5 / Top 10 / Top 20 /
 * Make the Cut), each listing the same handful of golfers. "Group them into a
 * beautiful grid … the way the US Open bracket grid works."
 *
 * That grid already existed — on the concept page, as `FinishPositionLadder`.
 * This is its presentational core, lifted out so the feed's version and the
 * event page's version are ONE design rather than two that drift. The event
 * page keeps its own data derivation (`renderedFinishColumns` /
 * `finishPositionRows` read a competitor envelope); the feed's rows are built
 * by the backend from the placement markets themselves. Only the drawing is
 * shared, which is the part a reader can tell apart.
 *
 * Values are fractions (0–1) or null. NULL RENDERS AS "—" AND IS NEVER
 * FABRICATED: a golfer with no Top 5 book has no Top 5 number, and inventing
 * one from an adjacent column would be a worse lie than an empty cell.
 */

export interface PlacementGridColumn {
  key: string;
  label: string;
}

export interface PlacementGridRow {
  name: string;
  /** column key → probability as a fraction (0–1), or null when unpriced. */
  values: Record<string, number | null>;
}

interface PlacementGridProps {
  columns: PlacementGridColumn[];
  rows: PlacementGridRow[];
  /** Header for the name column ("Player", "Team", "Driver"). */
  entityLabel?: string;
  /** A plain line under the grid, e.g. "8 of 156 players". */
  footnote?: string;
  /** Tighter type/spacing for a feed card. */
  compact?: boolean;
}

/** Whole-percent, "—" when absent. */
export function formatPlacementCell(v: number | null | undefined): string {
  if (typeof v !== "number" || !Number.isFinite(v)) return "—";
  return `${Math.round(v * 100)}%`;
}

/** A light heat gradient without raw palette — same steps as the concept
 *  page's ladder, so the two grids read identically. */
export function placementCellClass(v: number | null | undefined): string {
  if (typeof v !== "number" || !Number.isFinite(v)) return "text-text-muted";
  if (v >= 0.5) return "text-text-primary font-semibold";
  if (v >= 0.15) return "text-text-primary";
  return "text-text-secondary";
}

export default function PlacementGrid({
  columns,
  rows,
  entityLabel = "Player",
  footnote,
  compact = false,
}: PlacementGridProps) {
  if (columns.length === 0 || rows.length === 0) return null;

  const cell = compact ? "w-12" : "w-16";

  return (
    // A 5-column table does not fit a phone, so it scrolls horizontally while
    // the name column stays the flexible one — the same treatment the concept
    // page's ladder uses.
    <div className="overflow-x-auto -mx-1 px-1">
      <div className={compact ? "min-w-[18rem]" : "min-w-[22rem]"}>
        <div className="flex items-center gap-2 px-1 pb-1.5 text-[10px] uppercase tracking-wide text-text-muted">
          <span className="flex-1 min-w-0">{entityLabel}</span>
          {columns.map((col) => (
            <span key={col.key} className={`${cell} text-right shrink-0`}>
              {col.label}
            </span>
          ))}
        </div>
        <div className="divide-y divide-surface-border/40">
          {rows.map((row, i) => (
            <div
              key={`${row.name}-${i}`}
              className={`flex items-center gap-2 ${compact ? "py-1.5 text-[13px]" : "py-2 text-sm"}`}
            >
              <span className="flex-1 min-w-0 truncate text-text-primary">
                {row.name}
              </span>
              {columns.map((col) => (
                <span
                  key={col.key}
                  className={`${cell} text-right shrink-0 font-mono tabular-nums ${placementCellClass(
                    row.values[col.key],
                  )}`}
                >
                  {formatPlacementCell(row.values[col.key])}
                </span>
              ))}
            </div>
          ))}
        </div>
        {footnote && (
          <div className="pt-2 mt-1.5 border-t border-surface-elevated">
            <span className="text-[11px] text-text-muted">{footnote}</span>
          </div>
        )}
      </div>
    </div>
  );
}
