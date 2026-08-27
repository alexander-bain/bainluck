"use client";

import React from "react";

import ShowMore, { COLLAPSED_LIST_COUNT } from "./ShowMore";
import {
  GRID_SECTION_LABEL,
  formatGridCell,
  type GridCell,
  type GridColumn,
  type PlayoffGrid as PlayoffGridModel,
} from "@/lib/playoffGrid";

/**
 * THE PLAYOFF GRID — players down, rounds across (UX-P138, Alex's ruling 4).
 *
 * "Bracket tab = the PLAYOFF GRID — players × rounds with the probability of
 * reaching each, exactly like the league playoff tables."
 *
 * The row grammar is `ProgressionLadder`'s, the MLB/NBA playoff table — name,
 * then a percentage per stage. Not the component: it pulls framer-motion and
 * fires Wikipedia image lookups for team logos, and it is one card PER TEAM
 * with stages as rows, which at 44 tennis players is 44 cards. Transposed, the
 * same information is one table you can read down.
 *
 * ═══ WHAT THIS GRID WILL NOT DO ═══
 *
 * It will not fill a cell it does not have a price for. Every number here is a
 * market's answer to exactly the question in its column header — see
 * `lib/playoffGrid.ts` for the three sources and for why chaining match odds
 * into P(reach the semis) is forbidden even though it would look better.
 *
 * The consequence is visible and deliberate: **the middle of this grid is
 * mostly holes today.** We price the next round densely (it is just today's
 * match), the title densely (it is the board), and eight curated
 * advance-to-round questions in between. A hole prints as a hole with a legend
 * saying what a hole is, because the alternative — a plausible number — is the
 * one thing the charter's reliability doctrine forbids by name.
 *
 * ═══ ON THE TAB'S NAME ═══
 *
 * This tab is still called "Bracket" and contains no bracket. UX-P136 measured
 * why the tree cannot be the answer on a phone; the grid is the tree's
 * information without its geometry. If the word grates, `TABS` in
 * `app/tournaments/[slug]/page.tsx` is a one-line change and the report
 * proposes "Path" — same posture as ruling 7's section name, which Alex
 * already holds the pick on.
 */

function Cell({ cell, column }: { cell: GridCell; column: GridColumn }) {
  const text = formatGridCell(cell);

  if (text === null) {
    // A HOLE, SAID OUT LOUD. Not an em-dash and not a zero: a zero is a
    // forecast ("the market thinks this is impossible") and an em-dash is
    // indistinguishable from the "out" state one column over.
    return (
      <span
        className="text-[12px] text-text-muted/50"
        data-testid="grid-cell"
        data-state="unpriced"
        data-column={column.key}
      >
        <span className="sr-only">Not priced</span>
        <span aria-hidden="true">·</span>
      </span>
    );
  }

  return (
    <span
      className={`text-[13px] font-bold tabular-nums ${
        cell.state === "reached"
          ? "text-accent-live"
          : cell.state === "out"
            ? "text-text-muted/60"
            : cell.isLive
              ? "text-text-primary"
              : "text-text-secondary"
      }`}
      data-testid="grid-cell"
      data-state={cell.state}
      data-origin={cell.origin ?? undefined}
      data-column={column.key}
      data-live={cell.isLive ? "true" : "false"}
    >
      {text}
    </span>
  );
}

export default function PlayoffGrid({
  grid,
  drawLabel,
  initialExpanded = false,
}: {
  grid: PlayoffGridModel;
  drawLabel?: string;
  /** Capture seam: render the full field rather than the collapsed five. */
  initialExpanded?: boolean;
}) {
  const [expanded, setExpanded] = React.useState(initialExpanded);

  if (grid.rows.length === 0 || grid.columns.length === 0) {
    return (
      <div
        className="rounded-2xl border border-dashed border-surface-border bg-surface-card px-4 py-5 text-center"
        data-testid="grid-empty"
      >
        <div className="text-[15px] font-semibold text-text-primary">Nothing to chart yet</div>
        <p className="mt-1 text-[13px] text-text-secondary">
          Nobody in this draw has a priced round to reach.
        </p>
      </div>
    );
  }

  const visible = expanded ? grid.rows : grid.rows.slice(0, COLLAPSED_LIST_COUNT);
  // The grid template is computed rather than hard-coded so a three-column and
  // a four-column grid line up under the same header without a second class.
  const template = `minmax(0,1fr) repeat(${grid.columns.length}, 46px)`;

  return (
    <section
      data-testid="playoff-grid"
      data-columns={grid.columns.length}
      data-rows={grid.rows.length}
      data-priced={grid.pricedCells}
    >
      <h2 className="mb-2 text-xs font-bold uppercase tracking-[0.07em] text-text-muted">
        {GRID_SECTION_LABEL}
        {drawLabel && (
          <span className="ml-1.5 font-normal normal-case tracking-normal">· {drawLabel}</span>
        )}
      </h2>

      <div className="overflow-hidden rounded-2xl border border-surface-border bg-surface-card">
        <div
          className="grid items-center gap-1.5 border-b border-surface-border px-3.5 py-2 text-[9.5px] font-bold uppercase tracking-[0.05em] text-text-muted"
          style={{ gridTemplateColumns: template }}
          data-testid="grid-header"
        >
          <span>Player</span>
          {grid.columns.map((column) => (
            <span
              key={column.key}
              className={`text-right ${column.kind === "title" ? "text-text-secondary" : ""}`}
              title={column.longLabel}
              data-testid="grid-column"
              data-column={column.key}
              data-kind={column.kind}
            >
              {/* The header is short because 46px is short. The SENTENCE is
                  the `title` attribute and the sr-only span, because ruling 2
                  says a number names its own question and "SF" alone does
                  not. */}
              <span className="sr-only">{column.longLabel}. </span>
              <span aria-hidden="true">{column.shortLabel}</span>
            </span>
          ))}
        </div>

        <ol>
          {visible.map((row) => (
            <li
              key={row.entityKey}
              className="grid items-center gap-1.5 border-t border-surface-border px-3.5 py-2 first:border-t-0"
              style={{ gridTemplateColumns: template }}
              data-testid="grid-row"
              data-entity={row.entityKey}
              data-rank={row.rank}
            >
              <span className="flex min-w-0 items-baseline">
                <span className="truncate text-[13.5px] font-semibold text-text-primary">
                  {row.displayName}
                </span>
                {row.seed !== null && (
                  <span className="ml-1.5 shrink-0 text-[11px] font-normal text-text-muted">
                    [{row.seed}]
                  </span>
                )}
              </span>
              {grid.columns.map((column) => (
                <span key={column.key} className="text-right">
                  <Cell cell={row.cells[column.key]} column={column} />
                </span>
              ))}
            </li>
          ))}
        </ol>

        {grid.rows.length > COLLAPSED_LIST_COUNT && (
          <ShowMore
            expanded={expanded}
            total={grid.rows.length}
            onToggle={() => setExpanded((value) => !value)}
          />
        )}
      </div>

      {/* THE LEGEND, AND THE COUNTER. A grid this sparse has to say it is
          sparse, or the reader reads the holes as a rendering fault. */}
      <p className="mt-2 text-[11px] leading-snug text-text-muted" data-testid="grid-legend">
        <span aria-hidden="true">·</span> means nobody prices that question yet —{" "}
        <b className="font-semibold text-text-secondary" data-testid="grid-coverage">
          {grid.pricedCells} of {grid.totalCells}
        </b>{" "}
        cells have a market behind them. Nothing here is calculated from anything else.
        {grid.droppedColumns.length > 0 && (
          <>
            {" "}
            <span data-testid="grid-dropped-columns">
              {grid.droppedColumns.length} later round
              {grid.droppedColumns.length === 1 ? "" : "s"} (
              {grid.droppedColumns.map((column) => column.shortLabel).join(", ")}) do not fit this
              width.
            </span>
          </>
        )}
      </p>
    </section>
  );
}
