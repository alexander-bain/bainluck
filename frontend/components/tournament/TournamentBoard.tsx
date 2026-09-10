"use client";

import React, { useState } from "react";
import LiquidityMark from "../LiquidityMark";
import { FreshnessDot } from "../FreshnessDot";
import TrendSparkline from "./TrendSparkline";
import PlayerAvatar from "./PlayerAvatar";
import ShowMore from "./ShowMore";
import { COLLAPSED_ROW_COUNT, deltaWindowNote } from "@/lib/contenderChart";
import { TITLE_COLUMN_LABEL } from "@/lib/bracket";
import {
  boardNotice,
  formatBoardProbability,
  formatTrendDelta,
  rowFreshness,
  rowIsPresentedAsLive,
  trendDirection,
  type TournamentBoardData,
  type TournamentRow,
} from "@/lib/tournament";

/**
 * One draw's championship board — the page's reason to exist.
 *
 * The blend is the product: one number per player, large. Sources are present
 * and deliberately faint so the row can say "2 sources" without becoming a
 * comparison surface (standing Alex ruling).
 *
 * THE HONESTY RULE, which is the thing to preserve if this component is ever
 * rewritten: a row whose price is not live never renders in the live
 * treatment. It keeps its number — hiding it would throw away real information
 * — but the number is muted, it is followed by the age of the reading, and the
 * board carries a banner above it saying so in words. #2199 has these fields
 * dark for 8-32 days, so this is the live path this weekend, not an edge case.
 *
 * UX-P137: the chart LEFT this component (Alex's ruling 6 — it moved to the
 * top of the page, above the day's matches, where the title race belongs). The
 * board keeps the colour tie-in, but the colours now arrive as a prop from
 * whoever owns the chart's selection, because the reader can change it.
 *
 * And the number column has a header now (ruling 2). It is the same number the
 * bracket prints and it meant the same thing in both places — the chance of
 * winning the whole tournament — and neither of them said so.
 */

function BoardRow({ row, seriesColor }: { row: TournamentRow; seriesColor?: string }) {
  const isLive = rowIsPresentedAsLive(row);
  const settled = row.probability === null;
  // Names the old leg when only one of them is old (UX-P135), so a row muted
  // by a stale Polymarket price does not read as "nobody has looked at this".
  const freshness = rowFreshness(row);
  const [revealed, setRevealed] = React.useState<string | null>(null);
  const toggleReveal = React.useCallback((sentence: string) => {
    setRevealed((open) => (open === sentence ? null : sentence));
  }, []);

  return (
    <li
      /* RULING 8 adds a fifth column: rank, PICTURE, name, trend, number.
         28px + the 10px gap, taken from the name column, which was the only
         one with slack — the rank, the trend and the 52px number are all at
         their measured minimum (see GRID_COLUMN_WIDTH_PX's note).

         #4538: below `sm` there is no fifth column. Measured on production at
         390px, this row's content box is 332px and the name track was 102.6px
         of it — `Alexander Zverev` wants 125px and printed `Alexander Z…`. At
         360px ALL THREE visible rows clipped, `Ben Shelton` included. Dropping
         the sparkline track returns 52px + its 10px gap to the name. */
      className="grid grid-cols-[22px_28px_1fr_auto] items-center gap-2.5 border-t border-surface-border px-3.5 py-2.5 first:border-t-0 sm:grid-cols-[22px_28px_1fr_auto_52px]"
      data-testid="board-row"
      data-entity={row.entity_key}
      data-rank={row.rank}
      data-live={isLive ? "true" : "false"}
      data-price-state={row.price_state}
      data-mixed-freshness={row.mixed_freshness ? "true" : "false"}
    >
      <span className="text-right text-xs tabular-nums text-text-muted">{row.rank}</span>

      <PlayerAvatar name={row.display_name} image={row.image} size={28} />

      <div className="min-w-0">
        {/* #4538: the name WRAPS, it does not truncate. Returning the sparkline's
            62px covers every name in both US Open draws at 390px and all but the
            longest at 360px — `Felix Auger-Aliassime` and `Ekaterina
            Alexandrova` (21 chars, the longest of the 80 rows) still want more
            than a 360px phone has. An ellipsis answers that by hiding the one
            fact the row exists to state; a second line answers it by costing
            22px of height. `break-words` is the safety net for a name with no
            space in it, and does nothing to a name that has one. */}
        <div className="break-words text-[15px] font-semibold text-text-primary">
          {/* The reference's colour tie-in: a charted contender's name is
              underlined in its own line colour, so the list and the chart are
              legible as one thing rather than two coincident rankings. */}
          <span
            className={seriesColor ? "border-b-2 pb-px" : undefined}
            style={seriesColor ? { borderColor: seriesColor } : undefined}
            data-testid={seriesColor ? "board-row-series-tie" : undefined}
          >
            {row.display_name}
          </span>
          {row.seed !== null && (
            <span className="ml-1.5 text-xs font-normal text-text-muted">[{row.seed}]</span>
          )}
        </div>
        <div className="mt-px text-[10.5px] text-text-muted">
          {settled ? (
            <span data-testid="row-settled">{row.state}</span>
          ) : (
            <>
              <span>
                {row.source_count} source{row.source_count === 1 ? "" : "s"}
              </span>
              {/* #4283 / notice 34: an AGE is a method note about our pipeline
                  and goes to the mark's tooltip; an ANSWER ("no reading yet")
                  is what the reader asked and stays in the body. The split is
                  `rowFreshness().kind`, not a phrase match here. */}
              {freshness !== null && freshness.kind === "answer" && (
                <span className="text-accent-warning" data-testid="row-age">
                  {" · "}
                  {freshness.label}
                </span>
              )}
              {freshness !== null && freshness.kind === "age" && (
                <FreshnessDot
                  label={freshness.label}
                  ageHours={freshness.ageHours}
                  testId="row-age"
                  className="ml-1 align-baseline"
                />
              )}
              {/* UX-P157. On the honesty line rather than beside the number,
                  and that is a measurement, not a preference: the number track
                  is 52px and "100%" in 19px bold tabular figures already fills
                  it. This line is where the row's other caveats live, so the
                  mark is in company rather than alone.

                  Universal means ONE symbol and ONE sentence everywhere, not
                  one pixel offset everywhere — the four surfaces have four
                  different amounts of room and pretending otherwise is how a
                  signal gets dropped from the cramped one. */}
              <LiquidityMark
                facts={row}
                observedAt={row.observed_at}
                size="sm"
                className="ml-1 align-baseline"
                onReveal={toggleReveal}
              />
            </>
          )}
        </div>
        {revealed !== null && (
          <p
            className="mt-1 text-[10.5px] leading-snug text-text-secondary"
            data-testid="row-liquidity-reveal"
            role="status"
          >
            {revealed}
          </p>
        )}
      </div>

      <div className="text-right">
        <div
          className={`text-[19px] font-bold tabular-nums tracking-tight ${
            isLive ? "text-text-primary" : "text-text-secondary"
          }`}
          data-testid="row-probability"
        >
          {formatBoardProbability(row.probability)}
        </div>
        {!settled && row.trend_delta !== null && (
          <div
            className={`text-[11px] tabular-nums ${
              !isLive
                ? "text-text-muted"
                : trendDirection(row.trend_delta) === "up"
                  ? "text-accent-live"
                  : trendDirection(row.trend_delta) === "down"
                    ? "text-accent-danger"
                    : "text-text-muted"
            }`}
            data-testid="row-delta"
          >
            {formatTrendDelta(row.trend_delta)}
          </div>
        )}
      </div>

      {/* #4538. `hidden` is `display:none`, so below `sm` this is not a grid
          item at all and cannot open an implicit sixth row against the
          four-track template above.

          Why THIS element is the one that goes: the row prints the same fact
          twice, 10px apart. `+19.9` states the move in points; the sparkline
          draws it — and draws it at 52x26px on a fixed 0-100 axis, where a
          contender's whole fortnight is a near-flat line. It is also passed
          `delta` and takes its colour from `trendDirection(delta)`, so it is
          the same input rendered a second way. On this page the ContenderChart
          sits directly above the card drawing these very series full-size with
          an axis and range tabs, making the sparkline a THIRD rendering. At
          `sm` and up the row has the width for all of it and is unchanged. */}
      <div className="hidden sm:block" data-testid="board-row-trend-slot">
        <TrendSparkline trend={row.trend} delta={row.trend_delta} muted={!isLive} />
      </div>
    </li>
  );
}

export default function TournamentBoard({
  board,
  seriesColors,
}: {
  board: TournamentBoardData;
  /**
   * Chart colour per entity key, for the name-underline tie-in. Supplied by
   * whoever owns the chart's selection (UX-P137) — omitted, the board simply
   * renders no underlines, which is the right answer on the pre-draw bracket
   * view where there is no chart on screen to tie back to.
   */
  seriesColors?: Record<string, string>;
}) {
  const notice = boardNotice(board);

  // COLLAPSED BY DEFAULT — Alex called the uncollapsed list a P1 on this page,
  // not a polish item: the women's draw ran 44 rows and reading it meant
  // scrolling past everything else on the page. Three rows matches the chart's
  // three lines and the reference's own choice, which settled 3-vs-5.
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? board.rows : board.rows.slice(0, COLLAPSED_ROW_COUNT);
  const hidden = board.rows.length - visible.length;

  // #3033. Over the VISIBLE rows, not the whole board: the note reconciles the
  // deltas a reader can actually see against the chart above them.
  const deltaWindow = deltaWindowNote(visible);

  return (
    <section
      data-testid="tournament-board"
      data-draw={board.draw}
      data-delta-window={deltaWindow ?? undefined}
    >
      <h2 className="mb-2 mt-6 text-xs font-bold uppercase tracking-[0.07em] text-text-muted">
        {board.label}
        {board.contenders > 0 && (
          <span className="ml-1.5 font-normal normal-case tracking-normal">
            · {board.contenders} contenders
          </span>
        )}
      </h2>

      <div className="mt-3 overflow-hidden rounded-2xl border border-surface-border bg-surface-card">
        {notice && (
          <div
            className="flex items-start gap-2 border-b border-surface-border bg-accent-warning/10 px-3.5 py-2.5 text-[11.5px] text-text-secondary"
            data-testid="price-state-notice"
            data-tone={notice.tone}
            role="status"
          >
            <span aria-hidden="true" className="text-accent-warning">
              &#9888;
            </span>
            <span>
              <b className="font-bold text-text-primary">{notice.headline}.</b> {notice.detail}
            </span>
          </div>
        )}

        {board.rows.length === 0 ? (
          <div className="px-4 py-6 text-center text-[13.5px] text-text-secondary" data-testid="board-empty">
            <div className="mb-1 text-[15px] font-semibold text-text-primary">
              {/* UX-P145 took the trading VERB out of "nobody has priced it
                  yet" and kept the noun. UX-P146: Alex's product-wide ruling
                  takes the noun too — the word is PROBABILITY. */}
              No numbers to show
            </div>
            We know who is in this draw, but no market has put a number on it yet.
          </div>
        ) : (
          <>
            {/* THE COLUMN HEADER (ruling 2). "A number whose meaning needs
                asking fails the page" — and this column had no header at all
                while printing the same figure the bracket prints. */}
            <div
              className="flex items-center justify-between gap-2 border-b border-surface-border px-3.5 py-1.5 text-[9.5px] font-bold uppercase tracking-[0.06em] text-text-muted"
              data-testid="board-column-header"
            >
              <span>Contender</span>
              <span data-testid="board-column-label">{TITLE_COLUMN_LABEL}</span>
            </div>

            <ol>
              {visible.map((row) => (
                <BoardRow
                  key={row.entity_key}
                  row={row}
                  seriesColor={
                    row.probability !== null ? seriesColors?.[row.entity_key] : undefined
                  }
                />
              ))}
            </ol>

            {(hidden > 0 || expanded) && (
              <div data-testid="board-expander" data-expanded={expanded ? "true" : "false"}>
                <ShowMore
                  expanded={expanded}
                  total={board.rows.length}
                  onToggle={() => setExpanded((value) => !value)}
                />
              </div>
            )}
          </>
        )}

        {/* NOTICE 34 (#4278). `Movement since 10 Aug.` used to print here, in
            grey, at the foot of the contenders card. It is a method note — it
            tells the reader which window our `+19.8` was measured over — and
            notice 34 puts that class in the artifact or a tooltip, never in the
            page body. #3033's finding (a delta with no stated window is a
            number with no units) is not denied; the sentence is moved to
            `data-delta-window` on the section, where every guard and probe that
            asserted on it still reads it and a reader does not.
            `deltaWindowNote` is unchanged, still exported, still unit-tested,
            and still pinned against the Swift port in `RaceChartTests`. */}
        {board.unpriced > 0 && board.rows.length > 0 && (
          <div
            className="border-t border-surface-border px-3.5 py-2 text-[11px] text-text-muted"
            data-testid="board-unpriced"
          >
            {/* UX-P145: was "N more registered players" — *registered* is the
                name of our JSON file, not a fact about the draw. */}
            {board.unpriced} more {board.unpriced === 1 ? "player in" : "players in"} this draw{" "}
            {board.unpriced === 1 ? "has" : "have"} no number yet.
          </div>
        )}
      </div>
    </section>
  );
}
