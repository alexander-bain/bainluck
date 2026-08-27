"use client";

import React from "react";
import TournamentBoard from "./TournamentBoard";
import PlayoffGrid from "./PlayoffGrid";
import type { PlayoffGrid as PlayoffGridModel } from "@/lib/playoffGrid";
import type { TournamentBoardData } from "@/lib/tournament";

/**
 * THE BRACKET TAB.
 *
 * ═══ BEFORE THE DRAW: THE GRID IS ALREADY THERE, AND SO IS THE DATE ═══
 *
 * UX-P138 showed the winner boards and a panel reading "Draw not released /
 * Who gets how far fills in here once the draw is made." Alex, item 1: it
 * must state **WHEN** it releases — date and time, not just absence.
 *
 * Two things changed, and the second is the bigger one:
 *
 * 1. The panel names the ceremony's date and time, and the day the main draw
 *    starts. Both come from the payload rather than from a constant here, so
 *    the day they are wrong is a data edit and not a deploy.
 * 2. **The grid no longer waits for the draw.** It used to, because its cells
 *    came from the match list and there are no matches before a draw. Its
 *    cells now come from the register's round-advancement markets, which are
 *    live and priced *today* — 336 of them. Withholding a fully-priced grid
 *    until a ceremony would be the "never an empty page when tradeable truth
 *    exists" rule broken by the component that was written to honour it.
 *
 * So the pre-draw state is: the date, then the grid, then the boards. The
 * ceremony changes what the ROWS are ordered by, not whether there is a grid.
 */

function DrawNotice({
  drawReleaseLabel,
  mainDrawLabel,
  hasGrid,
}: {
  drawReleaseLabel?: string | null;
  mainDrawLabel?: string | null;
  hasGrid: boolean;
}) {
  return (
    <div
      className="rounded-2xl border border-dashed border-surface-border bg-surface-card px-4 py-4"
      data-testid="draw-notice"
      data-has-release-time={drawReleaseLabel ? "true" : "false"}
    >
      <div className="text-[15px] font-semibold text-text-primary">
        {/* ITEM 1. The date is the headline, not a footnote: "not released" is
            the state a reader can already see, and "when" is the only thing
            they came to this panel to find out. */}
        {drawReleaseLabel ? (
          <>
            Draw is made <span data-testid="draw-release-label">{drawReleaseLabel}</span>
          </>
        ) : (
          "Draw not released"
        )}
      </div>
      <p className="mt-1 text-[13px] leading-snug text-text-secondary">
        {mainDrawLabel && (
          <>
            First round begins{" "}
            <span data-testid="main-draw-label">{mainDrawLabel}</span>.{" "}
          </>
        )}
        {hasGrid
          ? "Who plays whom fills in then. The chances below are already live — the market prices how far each player gets before it knows the path."
          : "Who gets how far fills in here once the draw is made."}
      </p>
    </div>
  );
}

export default function TournamentBracket({
  grid,
  drawReleased,
  preDrawBoards,
  drawLabel,
  drawReleaseLabel,
  mainDrawLabel,
  initialExpanded = false,
}: {
  /** The players × rounds model, built server-side from the register. */
  grid?: PlayoffGridModel | null;
  drawReleased: boolean;
  /**
   * BOTH draws' championship boards, shown when there is no grid to show
   * (UX-P137, ruling 1: never an empty page when tradeable truth exists).
   */
  preDrawBoards?: TournamentBoardData[];
  drawLabel?: string;
  /** "Thursday 27 August, 12:00 ET" — Alex's item 1. */
  drawReleaseLabel?: string | null;
  mainDrawLabel?: string | null;
  /** Capture seam: render the grid's full field rather than the collapsed five. */
  initialExpanded?: boolean;
}) {
  const hasGrid = Boolean(grid && grid.rows.length > 0 && grid.columns.length > 0);

  if (!hasGrid) {
    const boards = preDrawBoards ?? [];
    return (
      <div data-testid="bracket-unreleased">
        <DrawNotice
          drawReleaseLabel={drawReleaseLabel}
          mainDrawLabel={mainDrawLabel}
          hasGrid={false}
        />
        {boards.map((board) => (
          <TournamentBoard key={board.draw} board={board} />
        ))}
      </div>
    );
  }

  return (
    <div data-testid="tournament-bracket">
      {!drawReleased && (
        <div className="mb-3">
          <DrawNotice
            drawReleaseLabel={drawReleaseLabel}
            mainDrawLabel={mainDrawLabel}
            hasGrid
          />
        </div>
      )}
      <PlayoffGrid
        grid={grid as PlayoffGridModel}
        drawLabel={drawLabel}
        initialExpanded={initialExpanded}
      />
    </div>
  );
}
