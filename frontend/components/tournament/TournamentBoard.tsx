import React from "react";
import TrendSparkline from "./TrendSparkline";
import {
  boardNotice,
  formatBoardProbability,
  formatTrendDelta,
  rowIsPresentedAsLive,
  stalenessLabel,
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
 */

function BoardRow({ row }: { row: TournamentRow }) {
  const isLive = rowIsPresentedAsLive(row);
  const settled = row.probability === null;

  return (
    <li
      className="grid grid-cols-[22px_1fr_auto_52px] items-center gap-2.5 border-t border-surface-border px-3.5 py-2.5 first:border-t-0"
      data-testid="board-row"
      data-entity={row.entity_key}
      data-rank={row.rank}
      data-live={isLive ? "true" : "false"}
      data-price-state={row.price_state}
    >
      <span className="text-right text-xs tabular-nums text-text-muted">{row.rank}</span>

      <div className="min-w-0">
        <div className="truncate text-[15px] font-semibold text-text-primary">
          {row.display_name}
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
              {!isLive && (
                <span className="text-accent-warning" data-testid="row-age">
                  {" · "}
                  {stalenessLabel(row.age_hours)}
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

export default function TournamentBoard({ board }: { board: TournamentBoardData }) {
  const notice = boardNotice(board);

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

      <div className="overflow-hidden rounded-2xl border border-surface-border bg-surface-card">
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
          <ol>
            {board.rows.map((row) => (
              <BoardRow key={row.entity_key} row={row} />
            ))}
          </ol>
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
