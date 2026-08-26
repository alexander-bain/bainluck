"use client";

import React from "react";
import TournamentBoard from "./TournamentBoard";
import PlayoffGrid from "./PlayoffGrid";
import type { PlayoffGrid as PlayoffGridModel } from "@/lib/playoffGrid";
import type { TournamentBoardData } from "@/lib/tournament";

/**
 * THE BRACKET TAB.
 *
 * Two states, and neither of them is a tree.
 *
 * ═══ BEFORE THE DRAW: BOTH WINNER BOARDS (UX-P137, ruling 1) ═══
 *
 * "Never an empty page when tradeable truth exists." The winner markets are
 * live and priced before the draw is made, and on the day before a ceremony
 * they are the only question anyone has. Unchanged by UX-P138, and this is the
 * state a real visitor sees until the ceremony — which is why it still leads
 * the capture artifact.
 *
 * ═══ AFTER THE DRAW: THE PLAYOFF GRID (UX-P138, Alex's ruling 4) ═══
 *
 * "Bracket tab = the PLAYOFF GRID — players × rounds with the probability of
 * reaching each, exactly like the league playoff tables."
 *
 * WHAT LEFT THIS FILE, and where it went. Until UX-P138 this tab held a round
 * strip and a list of match cards. That was a MATCH LIST, and the Tournament
 * tab had one too — the slate. The page shipped two match lists on two tabs
 * with nothing saying why they were different or which to trust, because they
 * were never different: they were the same fixtures split by which pipeline
 * produced them. Ruling 4 merges them onto the Tournament tab
 * (`TournamentMatches`) and gives this tab the one question a bracket is
 * actually read for.
 *
 * The advance-to-round markets left with them. They were rendered here as a
 * "Priced to get there" table under an unreached round, and as eight cards in
 * the questions section; ruling 8 says they are neither. They are cells.
 *
 * ADOPTED, NOT COUNTERED. Alex invited a counter-structure and asked for both
 * rendered if one existed. This lane has none worth his time: the tree was
 * measured unusable on a phone at UX-P136, one-round-at-a-time turned the tab
 * into a duplicate, and the grid is the only structure tried that answers
 * "how far does this player get" without either. The one reservation — the tab
 * is called Bracket and holds no bracket — is a word, not a structure, and the
 * report offers "Path" as a one-line change.
 */
export default function TournamentBracket({
  grid,
  drawReleased,
  preDrawBoards,
  drawLabel,
  initialExpanded = false,
}: {
  /** The players × rounds model. `null` before the draw. */
  grid?: PlayoffGridModel | null;
  drawReleased: boolean;
  /**
   * BOTH draws' championship boards, shown in the pre-draw state (ruling 1).
   * Deliberately not filtered by the gender pill: the ruling says both, and
   * the day before a ceremony there is exactly one question worth answering.
   */
  preDrawBoards?: TournamentBoardData[];
  drawLabel?: string;
  /** Capture seam: render the grid's full field rather than the collapsed five. */
  initialExpanded?: boolean;
}) {
  if (!drawReleased || !grid || grid.rows.length === 0) {
    const boards = preDrawBoards ?? [];
    return (
      <div data-testid="bracket-unreleased">
        <div className="rounded-2xl border border-dashed border-surface-border bg-surface-card px-4 py-5 text-center">
          <div className="text-[15px] font-semibold text-text-primary">Draw not released</div>
          <div className="mt-1 text-[13px] text-text-secondary">
            Who gets how far fills in here once the draw is made.
            {boards.length > 0
              ? " Until then, here is what the market already thinks about who wins it."
              : " The title boards do not move to make room for it."}
          </div>
        </div>

        {boards.map((board) => (
          <TournamentBoard key={board.draw} board={board} />
        ))}
      </div>
    );
  }

  return (
    <div data-testid="tournament-bracket">
      <PlayoffGrid grid={grid} drawLabel={drawLabel} initialExpanded={initialExpanded} />
    </div>
  );
}
