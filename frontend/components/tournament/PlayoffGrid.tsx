"use client";

import React from "react";

import LiquidityMark from "../LiquidityMark";
import { LIQUIDITY_DEFINITION } from "@/lib/liquidity";
import PlayerAvatar from "./PlayerAvatar";
import ShowMore, { COLLAPSED_LIST_COUNT } from "./ShowMore";
import {
  GRID_SECTION_LABEL,
  columnSumSentence,
  formatAge,
  formatGridCell,
  gridCellExplanation,
  gridCellGlyph,
  gridScrollFloorPx,
  gridScrolls,
  markedCellCount,
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
 * rows inside the same scroller so they cannot drift apart. Since #3072 the
 * arithmetic behind that verdict counts a row's padding and gaps as well as its
 * tracks, so the men's five-column draw scrolls (406px against a measured 332px
 * card) where it used to be clipped; a three-column first-week grid still does
 * not. Since #3087 the name track sticks while it scrolls — see
 * `GRID_STICKY_NAME`, because a number without the name beside it is half a
 * sentence.
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

/**
 * The grid's two column widths, as CSS variables with a `lg` override.
 *
 * Tailwind arbitrary properties, so the desktop measurements answer to the same
 * breakpoint as everything else on the page and no JS ever has to know how wide
 * the window is.
 *
 * ⚠️ WRITTEN OUT AS A LITERAL ON PURPOSE, and it must stay one. Tailwind's JIT
 * finds classes by scanning source text for candidates; it does not execute the
 * file. Composing this out of `GRID_NAME_WIDTH_PX` and friends — which is what
 * the first draft of this did, to avoid typing a number twice — means the
 * string `[--grid-name-w:118px]` never literally appears anywhere, so Tailwind
 * emits no rule for it, `var(--grid-name-w)` resolves to nothing, and every
 * grid track collapses. It fails at RUNTIME with a green build and a green
 * typecheck, which is the worst way for a layout to break.
 *
 * The duplication that buys is real, so it is guarded rather than tolerated:
 * `playoffGridDesktop.test.tsx` parses these four values back out of the string
 * and asserts they equal the exported constants.
 */
export const GRID_SIZING =
  "[--grid-name-w:118px] [--grid-col-w:46px] lg:[--grid-name-w:236px] lg:[--grid-col-w:84px]";

/**
 * ═══ THE NAME TRACK STAYS WHEN THE GRID SCROLLS (#3087) ═══
 *
 * #3072 made the Title column REACHABLE — 74px of scroll where there had been
 * none. Reaching it cost the reader the other half of the sentence. Measured on
 * production the morning after that shipped, phone viewport 390px, the men's
 * grid pushed to `scrollLeft = 74`: the header reads `R16 QF SF FINAL TITLE`
 * and the rows read **`s Alcaraz`**, **`nder Z…`**, **`Medve…`**. The number
 * arrives exactly as the name it belongs to leaves, and a table where those two
 * facts are never on screen together does not answer the question it was built
 * for ("who wins the title, and how likely is it").
 *
 * So the name track is `position: sticky` at the scrollport's left edge. Three
 * things this has to get right, none of them optional:
 *
 * - **It must not move anything at rest.** `-ml-3.5 pl-3.5 -mr-1.5 pr-1.5`
 *   extends the sticky box's PAINT over the row's own `px-3.5` padding and into
 *   the `gap-1.5` beside it while leaving its content box exactly where it was.
 *   The margins cancel the paddings, so the track's `max-content` contribution
 *   is unchanged and no name truncates one character earlier than yesterday.
 * - **It must be opaque.** `bg-surface-card` is the card's own background — a
 *   transparent sticky cell lets the percentages slide UNDER the name, which
 *   reads as a rendering fault rather than as a frozen column.
 * - **It expires where ruling 5 expires.** Applied only when `scrolls`, and
 *   retired at `lg` (`lg:static`), where the tracks are `1fr`, the grid fills
 *   its card, and there is nothing to scroll or to stick to.
 */
export const GRID_STICKY_NAME =
  "sticky left-0 z-10 bg-surface-card -ml-3.5 pl-3.5 -mr-1.5 pr-1.5 " +
  "lg:static lg:z-auto lg:ml-0 lg:mr-0 lg:pl-0 lg:pr-0";

/**
 * ═══ AND IT COMES TO REST ON WHOLE COLUMNS (#3087, second half) ═══
 *
 * A frozen name column and a free scroll produce a number that is WRONG on
 * screen. Photographed on production at `scrollLeft = 74` with the sticky cell
 * live and nothing else: the QF column sits half under the name box and Alcaraz's
 * row reads `Carlos Alcaraz  5%  67%  62%  43%` — his real QF number is **75%**.
 * A reader has no way to know the 7 is behind the name. "One number per
 * question" cannot survive a resting position that eats a digit.
 *
 * So the scroller snaps, and the snap line is the sticky cell's right edge
 * rather than the scrollport's: `scroll-padding-left` = the row's own padding
 * plus the name track plus the gap = `14 + 118 + 6 = 138px`, which is exactly the
 * measured width of the sticky box on production. Each value cell is a
 * `snap-start` target, so the rest positions are `0` and `52`
 * (`GRID_COLUMN_WIDTH_PX + GRID_GAP_PX`) — at 0 the grid reads R16→FINAL, at 52
 * it reads QF→**TITLE**, and at neither is any column half-hidden.
 *
 * ⚠️ `138` IS WRITTEN OUT because Tailwind's JIT scans source text and cannot
 * execute an expression — the same trap `GRID_SIZING` documents above. It is
 * transcription, not judgement, and `playoffGrid.test.tsx` parses the number
 * back out and asserts it equals the three constants added together, so the day
 * one of them changes the guard fails instead of the layout.
 *
 * `lg:snap-none` because above the breakpoint the grid does not scroll at all.
 */
export const GRID_SCROLL_SNAP = "snap-x snap-mandatory scroll-pl-[138px] lg:snap-none";

/**
 * ═══ THE SPARK BARS — RULED IN (UX-P147) ═══
 *
 * UX-P146 built these behind a prop defaulting to OFF and rendered both
 * options for Alex's eye (`reach-table-with-bars.html` / `reach-table-plain.html`).
 * He ruled: **"Option A is great"** — the bars. So the default is ON and the
 * prop stays only as the seam the plain mock is still rendered through, because
 * a comparison artifact that cannot draw the rejected option stops being a
 * comparison the moment somebody asks the question again.
 *
 * What a bar is: a single faint rule under the number, filled from the right to
 * the cell's own probability. One colour for every column and every row — a bar
 * is a length, and colour-coding it would add a second variable to a table
 * whose whole claim is that each cell answers exactly its own column. No
 * labels, no axis, no gridline: the number IS the label and it is already
 * there. `aria-hidden`, because it says nothing the cell's own screen-reader
 * sentence does not.
 *
 * ═══ AND THE TRUNCATION HE NAMED WITH IT ═══
 *
 * *"Player names truncate too early when the window is **not super wide**."*
 * The emphasis is his and it is the diagnosis. The name track was a FIXED
 * `var(--grid-name-w)` while every value column was `minmax(var(--grid-col-w),
 * 1fr)`, so every pixel a window gained went to the numbers and none of it to
 * the names — and `--grid-name-w` only steps up to 236px at `lg`.
 *
 * Between 560px and 1024px of viewport, therefore, the grid was drawing the
 * PHONE's 118px name box inside up to 830px of available width: "Tomas Martin
 * Etcheverry" cut to about "Tomas Marti", five value columns at ~140px each
 * holding a three-character percentage, and — now the bars are on — a bar
 * stretched across the whitespace that was paid for with his surname. Above
 * `lg` nothing truncates and nothing changes, which is exactly why the
 * complaint is scoped to windows that are not super wide.
 *
 * Alex's rule for the fix is the fix: **names get priority over bar width; bars
 * compress first.** See `gridTemplate` below.
 */
function SparkBar({ probability }: { probability: number }) {
  const pct = Math.max(0, Math.min(1, probability)) * 100;
  return (
    <span
      aria-hidden="true"
      className="mt-1 block h-[3px] w-full overflow-hidden rounded-full bg-surface-elevated"
      data-testid="grid-spark-bar"
      data-fill={pct.toFixed(1)}
    >
      <span
        className="ml-auto block h-full rounded-full bg-text-muted/45"
        style={{ width: `${pct}%` }}
      />
    </span>
  );
}

function Cell({
  cell,
  column,
  sparkBars = true,
}: {
  cell: GridCell | undefined;
  column: GridColumn;
  /** On since UX-P147 — see `SparkBar`. `false` renders the plain mock. */
  sparkBars?: boolean;
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
        className={`text-[9.5px] font-semibold uppercase tracking-tight lg:text-[11px] ${
          isAlarm ? "text-accent-danger" : "text-text-muted/70"
        }`}
      >
        <span className="sr-only">{explanation}</span>
        <span aria-hidden="true">{gridCellGlyph(cell)}</span>
      </span>
    );
  }

  const barred = sparkBars && typeof cell.probability === "number";

  return (
    <span
      {...shared}
      className={`text-[13px] font-bold tabular-nums lg:text-[15px] ${
        cell.probability_is_live ? "text-text-primary" : "text-text-secondary"
      } ${barred ? "block w-full" : ""}`}
    >
      <span className="sr-only">{explanation} </span>
      <span
        aria-hidden="true"
        className={barred ? "flex items-center justify-end gap-1" : undefined}
      >
        {text}
        {/* UX-P157. Inside the number's own line so it cannot be mistaken for
            a mark on the row or on the column — it belongs to THIS cell.
            No `onReveal`: a 46px value track has nowhere to put a panel, and
            the cell's `title` already carries the same sentence (see
            `gridCellExplanation`). The sr-only text above carries it too, so
            the mark is `aria-hidden` chrome here rather than a second,
            duplicate announcement on every thin cell in a 336-cell grid. */}
        <LiquidityMark facts={cell} observedAt={cell.observed_at} size="sm" decorative />
      </span>
      {barred && <SparkBar probability={cell.probability as number} />}
    </span>
  );
}

/**
 * ONE template, two sets of measurements — and, since UX-P147, an ORDER OF
 * PRIORITY between the two kinds of track.
 *
 * The widths are CSS variables set by `GRID_SIZING`, so the phone keeps the
 * 118/46 every prior ruling was verdicted against and a `lg` window gets
 * 236/84.
 *
 * ═══ WHAT CHANGED, AND WHY IT IS `max-content` ═══
 *
 * It was `var(--grid-name-w) repeat(n, minmax(var(--grid-col-w), 1fr))` — the
 * name track FIXED, the value tracks flexible. Every pixel of extra window
 * therefore went to the numbers, so a 900px window truncated a name at exactly
 * the character a 600px one did. Alex, item 1: *"names get priority over bar
 * width; bars compress first."*
 *
 * So the name track is `minmax(var(--grid-name-w), max-content)`. Read it as
 * the sentence it is: *never narrower than the measured minimum, never wider
 * than the longest name in this table.* The CSS grid algorithm then does
 * exactly what Alex asked, in this order:
 *
 *   1. every track starts at its minimum — the name at 118/236, each value
 *      column at 46/84, which is the phone's layout unchanged;
 *   2. **"maximize tracks"** hands out free space to non-flexible tracks up to
 *      their growth limits. `max-content` is a growth limit; `1fr` is not
 *      (a flexible track's growth limit is frozen at its base size for this
 *      step). So the NAME grows first, and stops the moment the longest name
 *      fits whole;
 *   3. **"expand flexible tracks"** gives whatever is left to the `1fr` value
 *      columns, which is where the bars live.
 *
 * Bars compress first because they are last in that order, and they can only
 * compress to `var(--grid-col-w)` — a floor wide enough for `100%` — after
 * which the grid scrolls rather than crushing them, exactly as ruling 5 says.
 *
 * ⚠️ THE PHONE IS UNTOUCHED, and this is the property to keep. At 390px there
 * is no free space, step 2 distributes nothing, and the name track sits at its
 * 118px minimum truncating precisely as before. `max-content` cannot widen a
 * track past the space available — it is a *growth limit*, not a minimum — so
 * it cannot overflow a narrow window either.
 *
 * ⚠️ AND `lg` AND ABOVE IS UNTOUCHED TOO, for the mirror reason. There the
 * minimum is already 236px, which was measured as "the widest real name plus a
 * seed badge with nothing clipped"; the longest name on the men's grid is
 * "Tomas Martin Etcheverry" and it fits. A `max-content` growth limit BELOW the
 * base size is clamped up to it by the spec, so the track does not grow, the
 * free space still goes to the bars, and the desktop layout every prior ruling
 * was verdicted against is byte-identical. The change bites in exactly the
 * range Alex named — 560px to 1024px — and nowhere else.
 *
 * A NOTE ON WHAT `max-content` MEASURES. It is the longest name in the WHOLE
 * table, not per row, because grid tracks are shared. That is the correct
 * reading of "names get priority": a column sized to its longest entry is a
 * column where no name is cut while another row has slack.
 */
export function gridTemplate(columnCount: number): string {
  return `minmax(var(--grid-name-w), max-content) repeat(${columnCount}, minmax(var(--grid-col-w), 1fr))`;
}

function SumCheck({ grid }: { grid: PlayoffGridModel }) {
  const failing = grid.columnSums.filter((check) => check.verdict !== "pass");
  return (
    <details
      className="mt-2 max-w-[80ch] rounded-xl border border-surface-border bg-surface-card px-3 py-2"
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
          className="mt-2 max-w-[80ch] border-t border-surface-border pt-1.5 text-[11px] leading-snug text-text-muted"
          data-testid="grid-monotonicity"
          data-count={grid.monotonicityViolations.length}
        >
          {/* The other eval. A player cannot be likelier to reach the final
              than the semis; where the market says otherwise we show the
              market and say that we noticed. */}
          {grid.monotonicityViolations.length} player
          {grid.monotonicityViolations.length === 1 ? " has" : "s have"} a higher chance for a
          later round than an earlier one —{" "}
          {grid.monotonicityViolations
            .slice(0, 3)
            .map((v) => `${v.display_name} (${v.earlier} → ${v.later})`)
            .join(", ")}
          {grid.monotonicityViolations.length > 3 ? " and others" : ""}. That is the
          market disagreeing with itself where trading is thin, shown exactly as quoted.
        </p>
      )}
    </details>
  );
}

export default function PlayoffGrid({
  grid,
  drawLabel,
  initialExpanded = false,
  sparkBars = true,
}: {
  grid: PlayoffGridModel;
  drawLabel?: string;
  /** Capture seam: render the full field rather than the collapsed five. */
  initialExpanded?: boolean;
  /**
   * Draw a faint bar under each numeric cell. **ON since UX-P147** — Alex saw
   * `reach-table-with-bars.html` beside `reach-table-plain.html` and ruled
   * "Option A is great". The prop survives so the plain artifact can still be
   * re-rendered from the shipped component. See `SparkBar` above.
   */
  sparkBars?: boolean;
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
          {/* UX-P145: "a priced round to reach" — *priced* as a verb. */}
          No market has a number yet for how far anyone in this draw gets.
        </p>
      </div>
    );
  }

  const visible = expanded ? grid.rows : grid.rows.slice(0, COLLAPSED_LIST_COUNT);
  const template = gridTemplate(grid.columns.length);
  const scrolls = gridScrolls(grid.columns.length);
  // Over the WHOLE grid, not the five visible rows: the key explains a symbol
  // that is one "show more" away, and a key that appears on expand would look
  // like the marks appeared with it.
  const marked = markedCellCount(grid);

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
          className="mb-2 max-w-[80ch] rounded-xl border border-accent-danger/40 bg-accent-danger/5 px-3 py-2 text-[11.5px] leading-snug text-accent-danger"
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
        className={`overflow-hidden rounded-2xl border border-surface-border bg-surface-card ${GRID_SIZING} ${
          scrolls ? `overflow-x-auto lg:overflow-x-visible ${GRID_SCROLL_SNAP}` : ""
        }`}
        data-testid="grid-scroller"
      >
        {/* The phone's scroll floor. `lg:min-w-0` retires it in a desktop
            window, where the grid is already wider than this and pinning it to
            a phone measurement would be the only thing keeping the columns
            narrow. Ruling 5 applies where ruling 5 was measured. */}
        <div
          className={scrolls ? "lg:!min-w-0" : undefined}
          style={scrolls ? { minWidth: `${gridScrollFloorPx(grid.columns.length)}px` } : undefined}
        >
          <div
            className="grid items-center gap-1.5 border-b border-surface-border px-3.5 py-2 text-[9.5px] font-bold uppercase tracking-[0.05em] text-text-muted lg:px-5 lg:py-2.5 lg:text-[10.5px]"
            style={{ gridTemplateColumns: template }}
            data-testid="grid-header"
          >
            <span className={scrolls ? GRID_STICKY_NAME : undefined}>Player</span>
            {grid.columns.map((column) => (
              <span
                key={column.key}
                className={`text-right${scrolls ? " snap-start" : ""} ${
                  column.kind === "title" ? "text-text-secondary" : ""
                }`}
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
                className="grid items-center gap-1.5 border-t border-surface-border px-3.5 py-2 first:border-t-0 lg:px-5 lg:py-2.5"
                style={{ gridTemplateColumns: template }}
                data-testid="grid-row"
                data-entity={row.entityKey}
                data-rank={row.rank ?? undefined}
                data-on-board={row.onBoard ? "true" : "false"}
              >
                <span
                  className={`flex min-w-0 items-baseline${scrolls ? ` ${GRID_STICKY_NAME}` : ""}`}
                  data-testid="grid-name"
                >
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
                  {/* The 18px stays. A responsive avatar means a second render
                      path for an <img> whose intrinsic size is a prop, and the
                      desktop name box is 236px — the crop was never the reason
                      names truncated up there, the 118px box was. */}
                  <PlayerAvatar name={row.displayName} image={row.image} size={18} />
                  <span className="ml-1 self-center truncate text-[13.5px] font-semibold text-text-primary lg:text-[15px]">
                    {row.displayName}
                  </span>
                  {row.seed !== null && (
                    <span className="ml-1.5 shrink-0 text-[11px] font-normal text-text-muted">
                      [{row.seed}]
                    </span>
                  )}
                </span>
                {grid.columns.map((column) => (
                  <span
                    key={column.key}
                    className={`text-right${scrolls ? " snap-start" : ""}`}
                    data-testid="grid-value-cell"
                  >
                    <Cell
                      cell={row.cells[column.key]}
                      column={column}
                      sparkBars={sparkBars}
                    />
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
      {/* max-w on the PROSE, not on the grid (Alex: "sensible max-width for
          text sections only"). The table above wants every pixel of a 1280px
          shell; this paragraph at that width is ~200 characters a line. */}
      <p
        className="mt-2 max-w-[80ch] text-[11px] leading-snug text-text-muted"
        data-testid="grid-legend"
      >
        <b className="font-semibold text-text-secondary" data-testid="grid-coverage">
          {grid.pricedCells} of {grid.totalCells}
        </b>{" "}
        {/* UX-P146: was "cells carry a market price" / "every number is a price
            somebody quoted". Alex's product-wide ruling on the noun. */}
        cells carry a number from a real market.{" "}
        {grid.noMarketCells > 0 && (
          <span data-testid="grid-no-market">
            {/* Ruling 141 (Alex, 2026-08-28): venue names are banned in reader
                copy — "we asked Kalshi and Polymarket and neither runs that
                market" told a tennis reader our sourcing. The admission it
                carried is the load-bearing half and survives intact: the cell
                is blank because the QUESTION is not being answered anywhere,
                not because we failed to read it. */}
            <b className="font-semibold text-text-secondary">{grid.noMarketCells}</b> say{" "}
            <span className="uppercase">no mkt</span> — nobody is answering that
            question, so we have nothing to show.{" "}
          </span>
        )}
        Nothing here is calculated from anything else: every number is one a market
        quoted for exactly the question in its column.
      </p>

      {/* ═══ THE ILLIQUIDITY KEY (UX-P157, Alex's ruling / #2256) ═══

          Said ONCE, under the grid, and only when the grid actually has marks
          on it — a key to a symbol that is not on screen is furniture. The two
          glyphs are the real component at the real size, not a drawing of it:
          if the mark ever changes shape this key changes with it, which is the
          only way a key stays true without anybody remembering to update it. */}
      {marked > 0 && (
        <p
          className="mt-1.5 flex max-w-[80ch] items-start gap-1.5 text-[11px] leading-snug text-text-muted"
          data-testid="grid-liquidity-key"
          data-marked={marked}
        >
          <span className="mt-[3px] flex shrink-0 items-center gap-1">
            <LiquidityMark
              facts={{ liquidity: "thin", liquidity_reasons: ["no_trades_24h"] }}
              size="sm"
              decorative
            />
            <LiquidityMark
              facts={{
                liquidity: "barely",
                liquidity_reasons: ["no_trades_24h", "spread_exceeds_price"],
              }}
              size="sm"
              decorative
            />
          </span>
          {/* The lead-in is a COUNT and nothing else. It used to restate what
              the definition says next ("come off a market barely anybody is
              trading"), which put the same clause on screen twice in a row —
              the verbosity Alex's 2026-08-29 ruling was about, one paragraph
              below the tooltip it was about. */}
          <span>
            <b className="font-semibold text-text-secondary">{marked}</b> of{" "}
            {grid.pricedCells} numbers here carry a mark. {LIQUIDITY_DEFINITION}
          </span>
        </p>
      )}

      <SumCheck grid={grid} />
    </section>
  );
}
