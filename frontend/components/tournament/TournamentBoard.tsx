"use client";

import React, { useState } from "react";
import TrendSparkline from "./TrendSparkline";
import ShowMore from "./ShowMore";
import { COLLAPSED_ROW_COUNT } from "@/lib/contenderChart";
import { TITLE_COLUMN_LABEL } from "@/lib/bracket";
import {
  boardNotice,
  formatBoardProbability,
  formatTrendDelta,
  rowFreshnessLabel,
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
  const freshness = rowFreshnessLabel(row);

  return (
    <li
      className="grid grid-cols-[22px_1fr_auto_52px] items-center gap-2.5 border-t border-surface-border px-3.5 py-2.5 first:border-t-0"
      data-testid="board-row"
      data-entity={row.entity_key}
      data-rank={row.rank}
      data-live={isLive ? "true" : "false"}
      data-price-state={row.price_state}
      data-mixed-freshness={row.mixed_freshness ? "true" : "false"}
    >
      <span className="text-right text-xs tabular-nums text-text-muted">{row.rank}</span>

      <div className="min-w-0">
        <div className="truncate text-[15px] font-semibold text-text-primary">
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
              {freshness !== null && (
                <span className="text-accent-warning" data-testid="row-age">
                  {" · "}
                  {freshness}
                </span>
              )}
            </>
          )}
        </div>
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

      <TrendSparkline trend={row.trend} delta={row.trend_delta} muted={!isLive} />
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

  return (
    <section data-testid="tournament-board" data-draw={board.draw}>
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
              No prices to show
            </div>
            We know who is in this draw, but nobody has priced it yet.
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

        {board.unpriced > 0 && board.rows.length > 0 && (
          <div
            className="border-t border-surface-border px-3.5 py-2 text-[11px] text-text-muted"
            data-testid="board-unpriced"
          >
            {board.unpriced} more registered {board.unpriced === 1 ? "player has" : "players have"} no
            price.
          </div>
        )}
      </div>
    </section>
  );
}
