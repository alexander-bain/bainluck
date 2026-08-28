"use client";

import React from "react";

import PlayerAvatar from "./PlayerAvatar";
import ShowMore, { COLLAPSED_LIST_COUNT } from "./ShowMore";
import {
  GRID_COLUMN_WIDTH_PX,
  GRID_NAME_WIDTH_PX,
  GRID_SECTION_LABEL,
  columnSumSentence,
  formatAge,
  formatGridCell,
  gridCellExplanation,
  gridCellGlyph,
  gridScrolls,
  gridWidthPx,
  type GridCell,
  type GridColumn,
  type PlayoffGrid as PlayoffGridModel,
} from "@/lib/playoffGrid";

/**
 * THE PLAYOFF GRID — players down, rounds across.
 *
 * UX-P139 rebuilt what this renders. The model now arrives whole from the
 * server, built from the register's `reaches` and nothing else, so this
 * component's entire job is to make five cell states legible on a 390px phone.
 *
 * ═══ THE FOUR RULINGS THAT SHAPE IT ═══
 *
 * **Ruling 3 (as amended) — no cell is ever blank.** Every cell prints
 * something, and the something says what it is. A priced cell prints its
 * number; a settled cell prints the result; a `no_market` cell says "no mkt"
 * because both sources were asked and neither carries the question; an
 * `unlinked` or `unregistered` cell prints an alarm and names the market that
 * did not resolve. The last two are OUR defect and are styled as one — Alex:
 * "the fix is linking the real markets".
 *
 * **Ruling 4 — the semifinal column is here.** It was missing because UX-P138
 * capped the grid at three reach columns and SF was the fourth. There is no
 * cap now.
 *
 * **Ruling 4 — the sum check is shown.** Under the grid, per column, with its
 * ratio and a sentence. It is a diagnostic and never a corrector: nothing here
 * rescales a column to make it add up.
 *
 * **Ruling 5 — wide rounds scroll.** `overflow-x-auto` with the header and the
 * rows inside the same scroller so they cannot drift apart. Today's grid is
 * 348px wide against a 358px content box, so it does not scroll; a draw with a
 * sixth column would, which is the point of the rule.
 *
 * ═══ WHAT THE READER SEES WHEN A ROW HAS NO MARKETS ═══
 *
 * 28 of 80 board contenders have no round-advancement market at either source
 * — Sinner among them. His row is four "no mkt" cells and a title price, which
 * looks alarming until you read it, so the row carries an explicit reason
 * rather than four bare cells.
 *
 * (Measured 2026-08-27 he is priced at 0.6% to win it, near the bottom of the
 * men's board rather than the top — the market pricing a withdrawal, not his
 * form. An earlier draft of this note said he led it, which was true of the
 * 2026-08-25 capture and stopped being true when the outright fields came back
 * live. Numbers in prose go stale; that is why the component states none.)
 */

const ALARM_STATES = new Set(["unlinked", "unregistered"]);

function Cell({
  cell,
  column,
}: {
  cell: GridCell | undefined;
  column: GridColumn;
}) {
  if (!cell) {
    // Structurally unreachable — the builder emits a cell for every column of
    // every row — and rendered as an alarm rather than as nothing, because a
    // grid that silently skips a cell is the exact defect this design exists
    // to end.
    return (
      <span
        className="text-[11px] font-bold text-accent-danger"
        data-testid="grid-cell"
        data-state="unregistered"
        data-column={column.key}
        title={`${column.long_label}. No cell built for this row.`}
      >
        !
      </span>
    );
  }

  const text = formatGridCell(cell);
  const explanation = gridCellExplanation(cell, column.long_label);
  const isAlarm = ALARM_STATES.has(cell.state);

  const shared = {
    "data-testid": "grid-cell",
    "data-state": cell.state,
    "data-column": column.key,
    "data-live": cell.probability_is_live ? "true" : "false",
    "data-alarm": isAlarm ? "true" : "false",
    "data-sources": cell.source_count,
    title: explanation,
  };

  if (text === null) {
    return (
      <span
        {...shared}
        className={`text-[9.5px] font-semibold uppercase tracking-tight ${
          isAlarm ? "text-accent-danger" : "text-text-muted/70"
        }`}
      >
        <span className="sr-only">{explanation}</span>
        <span aria-hidden="true">{gridCellGlyph(cell)}</span>
      </span>
    );
  }

  return (
    <span
      {...shared}
      className={`text-[13px] font-bold tabular-nums ${
        cell.probability_is_live ? "text-text-primary" : "text-text-secondary"
      }`}
    >
      <span className="sr-only">{explanation} </span>
      <span aria-hidden="true">{text}</span>
    </span>
  );
}

function SumCheck({ grid }: { grid: PlayoffGridModel }) {
  const failing = grid.columnSums.filter((check) => check.verdict !== "pass");
  return (
    <details
      className="mt-2 rounded-xl border border-surface-border bg-surface-card px-3 py-2"
      data-testid="grid-sum-check"
      data-failing={failing.length}
    >
      <summary className="cursor-pointer text-[11.5px] font-semibold text-text-secondary">
        Does each column add up?{" "}
        <span className="font-normal text-text-muted">
          {grid.columnSums.length - failing.length} of {grid.columnSums.length} columns
          within tolerance
        </span>
      </summary>
      {/* ALEX'S RULING 4, shown rather than claimed. Eight players reach the
          quarter-finals, four the semis, two the final, one wins it — so the
          column has to add to that, and when it does not the page says by how
          much instead of quietly scaling the numbers until it does. */}
      <ul className="mt-1.5 space-y-1" data-testid="grid-sum-rows">
        {grid.columnSums.map((check) => (
          <li
            key={check.key}
            className="flex items-baseline gap-2 text-[11px] leading-snug"
            data-testid="grid-sum-row"
            data-column={check.key}
            data-verdict={check.verdict}
          >
            <span
              aria-hidden="true"
              className={`mt-[3px] h-1.5 w-1.5 shrink-0 rounded-full ${
                check.verdict === "pass" ? "bg-accent-live" : "bg-accent-warning"
              }`}
            />
            <span className="text-text-secondary">{columnSumSentence(check)}</span>
          </li>
        ))}
      </ul>
      {grid.monotonicityViolations.length > 0 && (
        <p
          className="mt-2 border-t border-surface-border pt-1.5 text-[11px] leading-snug text-text-muted"
          data-testid="grid-monotonicity"
          data-count={grid.monotonicityViolations.length}
        >
          {/* The other eval. A player cannot be likelier to reach the final
              than the semis; where the market says otherwise we show the
              market and say that we noticed. */}
          {grid.monotonicityViolations.length} player
          {grid.monotonicityViolations.length === 1 ? " is" : "s are"} priced higher for a
          later round than an earlier one —{" "}
          {grid.monotonicityViolations
            .slice(0, 3)
            .map((v) => `${v.display_name} (${v.earlier} → ${v.later})`)
            .join(", ")}
          {grid.monotonicityViolations.length > 3 ? " and others" : ""}. That is the
          market disagreeing with itself in thin books, shown as quoted.
        </p>
      )}
    </details>
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
  const template = `${GRID_NAME_WIDTH_PX}px repeat(${grid.columns.length}, ${GRID_COLUMN_WIDTH_PX}px)`;
  const scrolls = gridScrolls(grid.columns.length);

  return (
    <section
      data-testid="playoff-grid"
      data-columns={grid.columns.length}
      data-rows={grid.rows.length}
      data-priced={grid.pricedCells}
      data-alarms={grid.alarmCells}
      data-scrolls={scrolls ? "true" : "false"}
    >
      <h2 className="mb-2 text-xs font-bold uppercase tracking-[0.07em] text-text-muted">
        {GRID_SECTION_LABEL}
        {drawLabel && (
          <span className="ml-1.5 font-normal normal-case tracking-normal">· {drawLabel}</span>
        )}
      </h2>

      {/* ALARM BANNER. Non-zero is red, and it is our defect, so it says so in
          the first person and gives the count rather than colouring some cells
          and hoping. */}
      {grid.alarmCells > 0 && (
        <div
          className="mb-2 rounded-xl border border-accent-danger/40 bg-accent-danger/5 px-3 py-2 text-[11.5px] leading-snug text-accent-danger"
          data-testid="grid-alarm-banner"
          data-count={grid.alarmCells}
        >
          <b className="font-semibold">
            {grid.alarmCells} cell{grid.alarmCells === 1 ? "" : "s"} could not be linked
            to their market.
          </b>{" "}
          Marked <span aria-hidden="true">!</span> below. This is a fault on our side, not
          an absence of markets, and it is being fixed.
        </div>
      )}

      {/* ONE SCROLLER around header AND rows (ruling 5). Two scrollers, or a
          scrolling body under a fixed header, is how a column header ends up
          over the wrong column. */}
      <div
        className={`overflow-hidden rounded-2xl border border-surface-border bg-surface-card ${
          scrolls ? "overflow-x-auto" : ""
        }`}
        data-testid="grid-scroller"
      >
        <div style={scrolls ? { minWidth: `${gridWidthPx(grid.columns.length)}px` } : undefined}>
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
                title={column.long_label}
                data-testid="grid-column"
                data-column={column.key}
                data-kind={column.kind}
                data-slots={column.slots ?? undefined}
              >
                {/* The header is short because 46px is short. The SENTENCE is
                    the `title` attribute and the sr-only span, because ruling
                    2 says a number names its own question and "SF" alone does
                    not. */}
                <span className="sr-only">{column.long_label}. </span>
                <span aria-hidden="true">{column.short_label}</span>
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
                data-rank={row.rank ?? undefined}
                data-on-board={row.onBoard ? "true" : "false"}
              >
                <span className="flex min-w-0 items-baseline">
                  {/* RULING 8, at 18px and NOT at the 26/28 the other two
                      surfaces use. The name box is GRID_NAME_WIDTH_PX = 118 by
                      measurement, and widening it by an avatar would push the
                      five-column grid from 348px to 376px inside a 358px
                      box — i.e. it would make ruling 5's horizontal scroll
                      start at FIVE columns instead of six, on today's grid,
                      and put the title column off-screen by default. A face is
                      worth three characters of a long surname; it is not worth
                      the last column. 18 + 4 leaves 96px, which fits "Carlos
                      Alcaraz" whole and truncates "Auger-Aliassime [11]"
                      slightly earlier than before. */}
                  <PlayerAvatar name={row.displayName} image={row.image} size={18} />
                  <span className="ml-1 self-center truncate text-[13.5px] font-semibold text-text-primary">
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
      </div>

      {/* THE LEGEND, AND THE COUNTERS. Every cell is in exactly one bucket and
          the buckets add to the total — a grid that cannot account for its own
          cells is not one anybody should trust. */}
      <p className="mt-2 text-[11px] leading-snug text-text-muted" data-testid="grid-legend">
        <b className="font-semibold text-text-secondary" data-testid="grid-coverage">
          {grid.pricedCells} of {grid.totalCells}
        </b>{" "}
        cells carry a market price.{" "}
        {grid.noMarketCells > 0 && (
          <span data-testid="grid-no-market">
            <b className="font-semibold text-text-secondary">{grid.noMarketCells}</b> say{" "}
            <span className="uppercase">no mkt</span> — we asked Kalshi and Polymarket and
            neither runs that market.{" "}
          </span>
        )}
        Nothing here is calculated from anything else: every number is a price somebody
        quoted for exactly the question in its column.
      </p>

      <SumCheck grid={grid} />
    </section>
  );
}
