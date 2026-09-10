"use client";

import React from "react";

import LiquidityMark from "../LiquidityMark";
import PlayerAvatar from "./PlayerAvatar";
import ShowMore, { COLLAPSED_LIST_COUNT } from "./ShowMore";
import {
  GRID_SECTION_LABEL,
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
 * **Ruling 3 (as amended twice) — every cell says what it is, and since #4171
 * one of them says it without words.** A priced cell prints its number; a
 * settled cell prints the result; an `unlinked` or `unregistered` cell prints
 * an alarm and names the market that did not resolve — OUR defect, styled as
 * one, Alex: *"the fix is linking the real markets"*.
 *
 * A `no_market` cell now prints NOTHING. It printed `NO MKT`, and notice 34
 * (Alex, 2026-09-08 4:00pm PT, about this page) is *"if a number cannot be
 * shown honestly, leave the space empty"*. The ruling's original point — that
 * a reader must be able to tell a hole from a layout artifact — is kept by the
 * per-cell `title` and `sr-only` sentence UX-P157 added, not by a word in the
 * track; see `gridCellGlyph`, which carries the whole argument.
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
 * tracks, so the men's five-column draw scrolls (446px against a measured 332px
 * card) where it used to be clipped; a three-column first-week grid still does
 * not (326 ≤ 332, unchanged by #4171's wider track). Since #3087 the name track
 * sticks while it scrolls — see
 * `GRID_STICKY_NAME`, because a number without the name beside it is half a
 * sentence.
 *
 * ═══ WHAT THE READER SEES WHEN A ROW HAS NO MARKETS ═══
 *
 * 28 of 80 board contenders have no round-advancement market at either source
 * — Sinner among them. His row is four empty cells and a title price, which
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
  "[--grid-name-w:118px] [--grid-col-w:54px] lg:[--grid-name-w:236px] lg:[--grid-col-w:84px]";

/**
 * ═══ #3087 (third pass): A FLEXIBLE VALUE TRACK EATS THE SCROLL FLOOR ═══
 *
 * `gridScrollFloorPx` rounds the scroll range up to a whole column step so the
 * END of a swipe — where a browser always lets a scroller rest — lands on a snap
 * point. That rounding only works if the extra pixels stay OUTSIDE the tracks.
 *
 * They did not. The value tracks were `minmax(var(--grid-col-w), 1fr)`, and the
 * big comment on `gridTemplate` below rests on a property that was true right up
 * until the floor shipped: *"THE PHONE IS UNTOUCHED — at 390px there is no free
 * space, so step 2 distributes nothing."* A `min-width` of 436 on a 406px grid
 * CREATES 30px of free space, and step 3 hands free space to the `1fr` tracks.
 * Measured on production the night the floor shipped, phone 390px, at the end
 * rest position:
 *
 *     column width  46 -> 52      (30px spread across 5 flexible tracks)
 *     column step   52 -> 58
 *     maxScroll     104           (not a multiple of 58 -> not a snap point)
 *
 * so a 6px sliver of the QF column survived beside the sticky name and the rows
 * printed a clipped `%` next to the player. Better than the half-eaten digit it
 * replaced, but not what the floor was for.
 *
 * So while the grid SCROLLS, the phone's value tracks are fixed at
 * `--grid-col-w` and the rounding becomes real trailing gutter, which is what
 * the floor always assumed. Two variants rather than one string with an
 * override, so there is no specificity question: exactly one is ever applied.
 *
 * ⚠️ Both are LITERALS for the JIT reason `GRID_SIZING` documents above, and
 * both spell `lg:` identically — a scrolling grid is a PHONE state (`lg:` gets
 * `overflow-x-visible` and `lg:!min-w-0`), so above `lg` the two must agree, and
 * they agree with what shipped before any of #3087.
 */
export const GRID_COL_TRACK_FLEX =
  "[--grid-col-track:minmax(54px,1fr)] lg:[--grid-col-track:minmax(84px,1fr)]";
export const GRID_COL_TRACK_FIXED =
  "[--grid-col-track:54px] lg:[--grid-col-track:minmax(84px,1fr)]";

/**
 * ═══ #4558: THE NAME TRACK HAD THE SAME LEAK, AND IT COST THE PHONE BOTH ═══
 * ═══ ITS COLUMN ALIGNMENT AND THE END OF THREE PLAYERS' NAMES.            ═══
 *
 * `GRID_COL_TRACK_FIXED` above closed the leak for the VALUE tracks: a scroll
 * floor above the natural width is free space, and free space goes into any
 * track that can grow. The name track was `minmax(var(--grid-name-w),
 * max-content)` and can grow, so it kept drinking from the same puddle. Two
 * claims in `gridTemplate`'s note were true when they were written and are
 * false now; both are corrected there, and both were measured on production
 * (`tools/grid-name-fit-4558.mjs`, `/tournaments/us-open`, 390px, 2026-09-09
 * 19:20 PT, the men's five-column grid):
 *
 *   header template          118px 54px 54px 54px 54px 54px
 *   row 1 (Alexander Zverev) name cell 144px   first value cell at 144
 *   row 2 (Ben Shelton)      name cell 138px   first value cell at 138
 *   row 5 (Lorenzo Musetti)  name cell 144px   first value cell at 144
 *
 * 1. *"The phone is untouched — at 390px there is no free space."* There is:
 *    `gridScrollFloorPx(5)` pins 452px over a 446px row, and those 6px went
 *    into the name track.
 * 2. *"`max-content` measures the longest name in the WHOLE table, because
 *    grid tracks are shared."* They are not shared here. The header and every
 *    `<li>` are each their OWN grid container, so the track resolves per row —
 *    118px on a row whose name fits, 124px on one whose name does not. The
 *    numbers below each other therefore sit 6px out of column, and the sticky
 *    box that `scroll-pl-[138px]` is transcribed from is 144px wide on exactly
 *    the rows with the long names, so a snapped column rests 6px under the
 *    name on those rows and nowhere else.
 *
 * The 6px also bought nothing: 102px of name where 114px was wanted still
 * printed `Alexander Zv…`. So below `sm` the name track is a FIXED length —
 * the floor stays in the gutter where #3087 assumed it was, every row's tracks
 * are identical, `138` is once again the true width of every sticky box, and
 * the name answers a track it cannot widen by wrapping (see the name span in
 * the row, and #4538, which took the same decision on this page's other list
 * the day before: *"an ellipsis answers that by hiding the one fact the row
 * exists to state"*).
 *
 * At `sm` and above the free space is REAL — a 560–1024px window is genuinely
 * wider than the floor — and UX-P147's ordering is exactly what Alex asked for
 * there, so the growable track comes back at `sm`. That is the whole range his
 * *"not super wide"* complaint was about; the phone was never in it.
 *
 * ⚠️ A LITERAL, for the JIT reason `GRID_SIZING` documents, and pinned by
 * `playoffGrid.test.tsx` against `gridTemplate` and the two width constants.
 */
export const GRID_NAME_TRACK =
  "[--grid-name-track:var(--grid-name-w)] " +
  "sm:[--grid-name-track:minmax(var(--grid-name-w),max-content)]";

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
    const glyph = gridCellGlyph(cell);
    return (
      <span
        {...shared}
        className={`text-[9.5px] font-semibold uppercase tracking-tight lg:text-[11px] ${
          isAlarm ? "text-accent-danger" : "text-text-muted/70"
        }`}
      >
        <span className="sr-only">{explanation}</span>
        {/* #4171 item 2: a `no_market` cell's glyph is now the empty string, so
            it would collapse to a zero-width box — and a zero-width box is not
            a hover target, which would take the cell's `title` (the sentence
            that replaced the words on screen) away from the reader at the same
            moment the words left. The NBSP keeps the line box and the target
            while painting nothing. */}
        <span aria-hidden="true">{glyph === "" ? "\u00a0" : glyph}</span>
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
 * ⚠️ THE PHONE WAS NOT UNTOUCHED, AND THIS PARAGRAPH USED TO SAY IT WAS
 * (corrected #4558). It read: *"At 390px there is no free space, step 2
 * distributes nothing, and the name track sits at its 118px minimum."* That
 * was true on the day it was written and stopped being true when #3087's
 * scroll floor shipped a `min-width` of 452 over a 446px row — 6px of free
 * space, which step 2 handed to the name track on the rows with long names and
 * to nobody on the rest. Below `sm` the name track is therefore a fixed length
 * now (`GRID_NAME_TRACK`), and the growable one starts at `sm`, where the free
 * space is a real window rather than a rounded-up floor. `max-content` still
 * cannot widen a track past the space available — it is a *growth limit*, not
 * a minimum — so it cannot overflow a narrow window either.
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
 * A NOTE ON WHAT `max-content` MEASURES — AND THE CLAIM HERE WAS WRONG
 * (corrected #4558). It said: *"the longest name in the WHOLE table, not per
 * row, because grid tracks are shared."* Tracks are shared inside ONE grid
 * container, and this component renders the header and every `<li>` as its own
 * container, so above `sm` each row still sizes its own name track and the
 * value columns stagger by however much the names differ. Measured on
 * production at 768px, five rows, first value cell at
 * `138 / 138.2 / 147.2 / 155.8 / 156.1` — an 18px stagger in a table whose
 * whole claim is that a column is a column. That is #4593 and it wants
 * `subgrid` (one container, tracks genuinely shared, and then this paragraph's
 * original sentence becomes true); it is NOT fixed here. What is fixed here is
 * the phone, where the same mechanism drank 6px of rounded-up scroll floor,
 * moved three rows' columns 6px right of the other two, and still left three
 * names clipped. Both states measured in `GRID_NAME_TRACK`.
 *
 * ═══ AND WHY THE VALUE TRACK IS NOW A VARIABLE (#3087, third pass) ═══
 *
 * The value track used to be written out here as `minmax(var(--grid-col-w),
 * 1fr)`. It is now `var(--grid-col-track)`, which resolves to exactly that
 * everywhere it used to — EXCEPT on a phone whose grid scrolls, where it is
 * fixed so the scroll floor cannot be absorbed into the columns. See
 * `GRID_COL_TRACK_FLEX` / `GRID_COL_TRACK_FIXED` above. Every clause of the
 * ordering argument below is unchanged: a fixed track is still non-flexible, so
 * the name still grows before the bars do.
 */
export function gridTemplate(columnCount: number): string {
  return `var(--grid-name-track) repeat(${columnCount}, var(--grid-col-track))`;
}

/**
 * ═══ THE SELF-AUDIT LEFT THE PAGE (#4278, notice 34) — READ THIS BEFORE
 *     PUTTING IT BACK ═══
 *
 * A `<details>` used to sit under this grid whose SUMMARY line — the part a
 * reader sees without clicking anything — read:
 *
 *     ▸ Does each column add up?   0 of 5 columns within tolerance
 *
 * Inside it were the five per-column sentences and, when the model found them,
 * a paragraph naming players whose later-round chance exceeds their earlier
 * one. It was ALEX'S RULING 4 rendered honestly: eight reach the quarters, four
 * the semis, two the final, one wins — so the column has to add to that, and
 * where it does not the page said by how much rather than quietly scaling the
 * numbers until it did.
 *
 * **Notice 34 (Alex, 2026-09-08 4:00pm PT) is later and is about THIS PAGE**:
 * *"all the grey text is madness, and shouldn't be user-facing at all"*, and
 * specifically *"any sentence written to satisfy a reviewer or the bus goes in
 * the PR, the artifact, or a tooltip on the source mark — never in the page
 * body."* A disclosure whose headline announces that every one of our five
 * columns failed our own coherence check is the purest instance of the class —
 * #4171 filed it as exactly that. A reader learns from it only that we do not
 * trust our own table.
 *
 * 🔴 **RULING 4'S SUBSTANCE IS UNCHANGED AND MUST STAY UNCHANGED.** What ruling
 * 4 forbids is *quietly scaling the numbers until they add up*, and nothing
 * here scales anything: every cell still prints the market's own quote. What
 * left is the paragraph ABOUT the arithmetic, not the arithmetic.
 *
 * 🔴 **AND REMOVING THE CAPTION MUST NOT CLOSE THE QUESTION IT WAS ASKING.**
 * `0 of 5` was a true report of a real defect and it is still true. It lives on
 * as **#4174** — open, untouched by this change, and now the only place the
 * question is tracked. The numbers themselves ride the section below as
 * `data-sum-columns` / `data-sum-failing` / `data-monotonicity`, the same
 * treatment #4122 gave `data-marked`, so a probe, a guard or a sentinel reads
 * every one of them exactly as before and a reader is not made to.
 * `columnSumSentence` and the model's `columnSums` are untouched.
 */

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

  /* 🔴 ABOVE THE EMPTY-GRID EARLY RETURN, AND NOT BY PREFERENCE. These four
     hooks first sat beside `marked`, below `if (grid.rows.length === 0) return
     <Nothing to chart yet/>` — three `react-hooks/rules-of-hooks` errors, caught
     by `npm run build` and NOT by `npm run typecheck` (gotcha #10: build is the
     ESLint gate, typecheck is the TS gate, and this class is invisible to the
     second). It is a real crash, not a lint opinion: a draw that gains its
     first priced row goes from 1 hook to 5 between renders. */
  /* #4171 item 3's affordance. `scrollWidth - clientWidth - scrollLeft > 4`
     rather than `> 0`: sub-pixel layout leaves a fraction of a pixel at a real
     scroll end on a device pixel ratio that is not 1, and a cue that never
     turns off at the end is worse than none — it says "more to the right"
     forever. 4px is latency/282b's threshold on the sibling table; same number
     on purpose. */
  const scrollRef = React.useRef<HTMLDivElement | null>(null);
  const headerRef = React.useRef<HTMLDivElement | null>(null);
  const [canScrollRight, setCanScrollRight] = React.useState(false);
  const [headerHeight, setHeaderHeight] = React.useState(0);

  const syncScrollCue = React.useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    setCanScrollRight(el.scrollWidth - el.clientWidth - el.scrollLeft > 4);
    setHeaderHeight(headerRef.current?.getBoundingClientRect().height ?? 0);
  }, []);

  React.useEffect(() => {
    syncScrollCue();
    const el = scrollRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    // Re-measured on RESIZE, not only on mount: the cue is `lg:hidden` and the
    // header changes height at that same breakpoint, so a window dragged across
    // it would otherwise keep a stale height. `expanded` is in the deps because
    // "show all" changes `scrollWidth`.
    const observer = new ResizeObserver(syncScrollCue);
    observer.observe(el);
    return () => observer.disconnect();
  }, [syncScrollCue, expanded, grid.columns.length, grid.rows.length]);

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
  /* `marked` no longer prints. It rides the section as `data-marked` so a probe
     can still read the count the deleted `grid-liquidity-key` paragraph used to
     say out loud (notice 34 / #4122). */
  const marked = markedCellCount(grid);
  /* The deleted `grid-sum-check` disclosure's two numbers, kept machine-readable
     — see the block above this component. Same treatment as `data-marked`. */
  /* #4174: `settled` is a FINISHED check, not a failed one. A round whose places
     have all been won has nothing left for a probability to be about, and
     counting it here made a coherent grid report itself broken to every probe
     reading this attribute. */
  const sumFailing = grid.columnSums.filter(
    (check) => check.verdict !== "pass" && check.verdict !== "settled"
  ).length;

  return (
    <section
      data-testid="playoff-grid"
      data-columns={grid.columns.length}
      data-rows={grid.rows.length}
      data-priced={grid.pricedCells}
      data-total-cells={grid.totalCells}
      data-no-market={grid.noMarketCells}
      data-alarms={grid.alarmCells}
      data-marked={marked}
      data-sum-columns={grid.columnSums.length}
      data-sum-failing={sumFailing}
      data-monotonicity={grid.monotonicityViolations.length}
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
          over the wrong column.

          ═══ #4171 item 3: IT ALWAYS SCROLLED, IT JUST NEVER SAID SO ═══

          Filed as "the grid overflows horizontally at 390px … the TITLE column
          is clipped … a reader on a phone cannot see the column the whole grid
          builds to". The clip is real and reproduces, but the conclusion does
          not: 5 columns is `2*14 + 118 + 5*54 + 5*6 = 446px` of grid inside a
          `GRID_CARD_CONTENT_PX` 332px card, so `gridScrolls` is true and this
          container has had `overflow-x-auto`, snap points and a rounded scroll
          floor since #3072/#3087. TITLE is one swipe away and always has been.

          What was missing is the AFFORDANCE. Nothing on screen distinguished
          "the table ends here" from "there is more to the right", so a reader
          with no reason to try a horizontal swipe never learns the column
          exists — which produces exactly the complaint that was filed.

          Same defect, same week, same fix as #4261 on `TournamentProgressionTable`
          (latency/282b, `aa22d84c`): a short fade at the right edge, drawn only
          while there is more to reach. Deliberately the same treatment and not a
          new one — notice 35, one family everywhere.

          🔴 AND THE SAME TRAP, WHICH THEY PAID FOR AND I AM NOT PAYING AGAIN.
          Their first cut faded the full height and washed out the last 32px of
          every cell, which on that table is where the bars differ — the
          affordance erased the encoding it shipped beside. This grid has
          `SparkBar` under every numeric cell for the same reason, so the cue is
          clamped to the HEADER ROW's measured height and never covers a bar. */}
      <div className="relative">
      <div
        className={`overflow-hidden rounded-2xl border border-surface-border bg-surface-card ${GRID_SIZING} ${GRID_NAME_TRACK} ${
          scrolls ? GRID_COL_TRACK_FIXED : GRID_COL_TRACK_FLEX
        } ${scrolls ? `overflow-x-auto lg:overflow-x-visible ${GRID_SCROLL_SNAP}` : ""}`}
        data-testid="grid-scroller"
        ref={scrollRef}
        onScroll={syncScrollCue}
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
            ref={headerRef}
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
                  {/* #4558: THE NAME WRAPS, IT DOES NOT TRUNCATE — the same
                      decision #4538 took on this page's other list the day
                      before, for the same reason in Alex's own words: a row
                      whose job is to say WHO must not answer with
                      `Alexander Zv…`. Below `sm` the track is fixed
                      (`GRID_NAME_TRACK`) at 118px, of which 96 reach the text
                      after the 18px face and its 4px gap, so `Alexander
                      Zverev` (114px), `Karen Khachanov` (114) and `Lorenzo
                      Musetti` (105) each take a second line and cost that row
                      ~17px of height. `break-words` is the safety net for a
                      name with no space in it and does nothing to a name that
                      has one. */}
                  <span className="ml-1 self-center break-words text-[13.5px] font-semibold text-text-primary lg:text-[15px]">
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
        {/* Clamped to the header row's MEASURED height, not a guess: the row is
            `text-[9.5px]` on a phone and `lg:text-[10.5px] lg:py-2.5` above it,
            so a hard-coded height would cover a `SparkBar` at one breakpoint or
            float above the header at the other. Drawn only while there is more
            to reach, so a grid already scrolled to its end — or one narrow
            enough not to scroll at all — shows nothing. */}
        {canScrollRight && headerHeight > 0 && (
          <div
            aria-hidden="true"
            data-testid="grid-scroll-affordance"
            style={{ height: headerHeight }}
            className="pointer-events-none absolute top-0 right-0 w-8 rounded-tr-2xl bg-gradient-to-l from-surface-card to-transparent lg:hidden"
          />
        )}
      </div>

      {/* ═══ notice 34 / #4122: THE LEGEND AND ITS COUNTERS ARE GONE ═══

          `grid-legend` printed "N of M cells carry a number from a real
          market", then "K say NO MKT — nobody is answering that question, so we
          have nothing to show", then "Nothing here is calculated from anything
          else: every number is one a market quoted for exactly the question in
          its column." A coverage count, an explanation of our own emptiness,
          and a method note — all three of the kinds notice 34 bans, in one
          paragraph, on the same page Alex was reading.

          Nothing a reader needs is lost, because the grid already answers all
          of it PER CELL. `gridCellExplanation` builds a sentence for every
          single cell — including `no_market`, whose text is exactly the
          admission this paragraph aggregated — and it is hung on the cell's own
          `title` and `sr-only`. A cell reading NO MKT is therefore explained
          where a reader is actually looking, on hover and to a screen reader,
          rather than by a paragraph below the fold that they must map back onto
          a cell themselves.

          The three counters ride the section as `data-priced`,
          `data-total-cells` and `data-no-market`, so the "every cell is in
          exactly one bucket and the buckets add to the total" property the old
          comment cared about is still checkable — by a probe, from the markup,
          which is a stricter check than a reader adding up prose. */}

      {/* ═══ notice 34 (Alex, 2026-09-08 4:00pm PT) / #4122: THE GRID
          LIQUIDITY KEY IS GONE ═══

          `grid-liquidity-key` printed a count ("N of M numbers here carry a
          mark") followed by the whole of LIQUIDITY_DEFINITION — so the Bracket
          tab carried both a coverage count and a method note, two of the three
          kinds the ruling bans, in one paragraph.

          Same disposal as the Tournament tab: the definition already rides
          every mark as `title` / `aria-label` via `LiquidityMark`, which is the
          tooltip notice 34 points method notes at. The count moved to
          `data-marked` on the grid section for probes.

          The marks on the cells are untouched — this removed the key, not the
          symbols it described. */}

      {/* The column self-audit used to render here. See the block above
          `PlayoffGrid` for why it is `data-sum-*` on the section instead, and
          for why #4174 stays open. */}
    </section>
  );
}
