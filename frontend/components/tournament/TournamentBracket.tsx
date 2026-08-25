import React from "react";
import {
  bracketProgress,
  type BracketMatch,
  type BracketRound,
  type BracketSlot,
} from "@/lib/bracket";

/**
 * The draw bracket — horizontally scrollable columns, one per round.
 *
 * Built and shipped behind its own tab (direction C) so that it can never
 * displace the championship boards, which is the charter's explicit safety
 * property: "a janky bracket NEVER blocks or degrades layers 1-2 on the
 * marquee weekend."
 *
 * Until the draw is released this renders the honest not-yet state rather than
 * an empty grid. An empty 128-slot skeleton reads as "we lost the data"; a
 * sentence reads as "this happens Thursday".
 */

function SlotLine({ slot, won }: { slot: BracketSlot | null; won: boolean }) {
  if (slot === null) {
    return (
      <div className="flex items-center justify-between py-1 text-[12.5px] text-text-muted">
        <span>—</span>
      </div>
    );
  }
  return (
    <div
      className={`flex items-center justify-between gap-2 py-1 text-[12.5px] ${
        won ? "font-semibold text-text-primary" : "text-text-secondary"
      }`}
      data-testid="bracket-slot"
      data-entity={slot.entity_key}
      data-won={won ? "true" : "false"}
    >
      <span className="truncate">
        {slot.seed !== null && (
          <span className="mr-1 text-[10.5px] text-text-muted">{slot.seed}</span>
        )}
        {slot.display_name}
      </span>
      {slot.probability !== null && (
        <span className="shrink-0 tabular-nums text-[11px] text-text-muted">
          {(slot.probability * 100).toFixed(1)}%
        </span>
      )}
    </div>
  );
}

function MatchCard({ match }: { match: BracketMatch }) {
  return (
    <div
      className="rounded-xl border border-surface-border bg-surface-card px-2.5 py-1.5"
      data-testid="bracket-match"
      data-match={match.id}
      data-decided={match.winnerKey !== null ? "true" : "false"}
    >
      <SlotLine slot={match.top} won={match.winnerKey === match.top?.entity_key} />
      <div className="h-px bg-surface-border" />
      <SlotLine slot={match.bottom} won={match.winnerKey === match.bottom?.entity_key} />
    </div>
  );
}

export default function TournamentBracket({
  rounds,
  drawReleased,
}: {
  rounds: BracketRound[];
  drawReleased: boolean;
}) {
  if (!drawReleased || rounds.length === 0) {
    return (
      <div
        className="rounded-2xl border border-dashed border-surface-border bg-surface-card px-4 py-6 text-center"
        data-testid="bracket-unreleased"
      >
        <div className="text-[15px] font-semibold text-text-primary">Draw not released</div>
        <div className="mt-1 text-[13px] text-text-secondary">
          The bracket fills in here once the draw is made. The title boards do not move to make
          room for it.
        </div>
      </div>
    );
  }

  const { played, total } = bracketProgress(rounds);

  return (
    <div data-testid="tournament-bracket">
      <div className="mb-2 text-[11.5px] text-text-muted" data-testid="bracket-progress">
        {played} of {total} matches decided
      </div>
      <div className="-mx-4 overflow-x-auto px-4 pb-2">
        <div className="flex min-w-min gap-3">
          {rounds.map((round) => (
            <div key={round.round} className="w-[190px] shrink-0" data-testid="bracket-round" data-round={round.round}>
              <div className="mb-1.5 text-[11px] font-bold uppercase tracking-[0.06em] text-text-muted">
                {round.label}
              </div>
              <div className="flex flex-col gap-1.5">
                {round.matches.map((match) => (
                  <MatchCard key={match.id} match={match} />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
