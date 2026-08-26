"use client";

import React from "react";
import {
  bracketProgress,
  roundIsUnreached,
  type BracketMatch,
  type BracketRound,
  type BracketSlot,
  type RoundName,
} from "@/lib/bracket";

/**
 * The draw bracket — ONE ROUND AT A TIME, chosen from a round strip.
 *
 * Built and shipped behind its own tab (direction C) so that it can never
 * displace the championship boards, which is the charter's explicit safety
 * property: "a janky bracket NEVER blocks or degrades layers 1-2 on the
 * marquee weekend."
 *
 * WHY NOT SEVEN COLUMNS (changed UX-P136, measured against the 128 fixture).
 *
 * The first cut laid the rounds out as seven side-by-side columns. Rendered
 * against a real 128-slot draw at the 390px viewport this page is designed
 * for, that is:
 *
 *   - ~1,360px wide (7 x 190px + gaps) — three and a half phone screens of
 *     horizontal scrolling, and
 *   - ~3,450px tall in the first column alone (64 match cards), while the
 *     Final is a single card at the top of a column you cannot see from there.
 *
 * So finding one player meant scrolling in two dimensions through mostly
 * whitespace. The charter makes mobile formatting a SHIP GATE and defines fun
 * as "fast and RELIABLE", and a tree you cannot read is neither. A 128 draw
 * does not fit on a phone as a tree; it fits as a round.
 *
 * The fold logic is untouched by this — `buildBracket` still produces the same
 * seven rounds. This is only how they are presented, so the desktop tree can
 * come back later without redoing the data path.
 *
 * Until the draw is released this renders the honest not-yet state rather than
 * an empty grid. An empty 128-slot skeleton reads as "we lost the data"; a
 * sentence reads as "this happens Thursday".
 */

function SlotLine({ slot, won, decided }: { slot: BracketSlot | null; won: boolean; decided: boolean }) {
  if (slot === null) {
    return (
      <div
        className="flex items-center py-1.5 text-[13px] text-text-muted"
        data-testid="bracket-slot-empty"
      >
        <span>&mdash;</span>
      </div>
    );
  }
  return (
    <div
      className={`flex items-center justify-between gap-2 py-1.5 text-[13px] ${
        won
          ? "font-semibold text-text-primary"
          : decided
            ? "text-text-muted"
            : "text-text-secondary"
      }`}
      data-testid="bracket-slot"
      data-entity={slot.entity_key}
      data-won={won ? "true" : "false"}
    >
      <span className="flex min-w-0 items-center gap-1.5">
        {slot.seed !== null && (
          <span className="shrink-0 rounded bg-surface-border/60 px-1 py-px text-[10px] font-semibold tabular-nums text-text-muted">
            {slot.seed}
          </span>
        )}
        <span className="truncate">{slot.display_name}</span>
      </span>
      {slot.probability !== null && (
        <span className="shrink-0 tabular-nums text-[11.5px] text-text-muted">
          {(slot.probability * 100).toFixed(1)}%
        </span>
      )}
    </div>
  );
}

function MatchCard({ match, index }: { match: BracketMatch; index: number }) {
  const decided = match.winnerKey !== null;
  return (
    <div
      className="flex items-stretch gap-2"
      data-testid="bracket-match"
      data-match={match.id}
      data-decided={decided ? "true" : "false"}
    >
      <div className="w-5 shrink-0 pt-2 text-right text-[10.5px] tabular-nums text-text-muted">
        {index + 1}
      </div>
      <div className="min-w-0 flex-1 rounded-xl border border-surface-border bg-surface-card px-3 py-1">
        <SlotLine
          slot={match.top}
          won={match.top !== null && match.winnerKey === match.top.entity_key}
          decided={decided}
        />
        <div className="h-px bg-surface-border" />
        <SlotLine
          slot={match.bottom}
          won={match.bottom !== null && match.winnerKey === match.bottom.entity_key}
          decided={decided}
        />
      </div>
    </div>
  );
}

export default function TournamentBracket({
  rounds,
  drawReleased,
  initialRound,
}: {
  rounds: BracketRound[];
  drawReleased: boolean;
  /**
   * Which round to open on. Defaults to the earliest round still undecided —
   * "where the tournament is" — so the tab does not open on a Round of 128
   * that finished a week ago. Also the seam the capture rig renders each round
   * through without needing a browser.
   */
  initialRound?: RoundName;
}) {
  const firstLive = rounds.find(
    (r) => !roundIsUnreached(r) && r.matches.some((m) => m.winnerKey === null)
  );
  const fallback = initialRound ?? firstLive?.round ?? rounds[0]?.round;
  const [selected, setSelected] = React.useState<RoundName | undefined>(fallback);

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

  const active = rounds.find((r) => r.round === selected) ?? rounds[0];
  const { played, total } = bracketProgress(rounds);
  const activeIndex = rounds.indexOf(active);
  const feeder = activeIndex > 0 ? rounds[activeIndex - 1] : null;
  const unreached = roundIsUnreached(active);

  return (
    <div data-testid="tournament-bracket">
      <div className="mb-2 text-[11.5px] text-text-muted" data-testid="bracket-progress">
        {played} of {total} matches decided
      </div>

      {/* The round strip. Horizontal, but seven short chips wide rather than
          seven 190px columns — it fits a phone without scrolling at all. */}
      <div className="-mx-4 overflow-x-auto px-4" data-testid="bracket-round-strip">
        <div className="flex gap-1.5 pb-3">
          {rounds.map((round) => {
            const done = round.matches.filter((m) => m.winnerKey !== null).length;
            const on = round.round === active.round;
            return (
              <button
                key={round.round}
                type="button"
                onClick={() => setSelected(round.round)}
                data-testid="bracket-round-chip"
                data-round={round.round}
                data-selected={on ? "true" : "false"}
                className={`shrink-0 rounded-full px-3 py-1.5 text-[12.5px] font-semibold transition-colors ${
                  on
                    ? "bg-text-primary text-surface-card"
                    : "bg-surface-border/50 text-text-secondary"
                }`}
              >
                {round.round}
                {done > 0 && (
                  <span className="ml-1 text-[10.5px] font-normal opacity-70 tabular-nums">
                    {done}/{round.matches.length}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      <div
        className="mb-2 text-[13px] font-semibold text-text-primary"
        data-testid="bracket-round-title"
        data-round={active.round}
      >
        {active.label}
      </div>

      {unreached ? (
        // One sentence instead of 16 identical empty cards. The empty cards
        // were not information; they were a wall in front of the rounds that
        // do have names in them.
        <div
          className="rounded-2xl border border-dashed border-surface-border bg-surface-card px-4 py-6 text-center text-[13px] text-text-secondary"
          data-testid="bracket-round-unreached"
        >
          Nobody has reached the {active.label.toLowerCase()} yet. It fills in as the{" "}
          {feeder ? feeder.label.toLowerCase() : "previous round"} is played.
        </div>
      ) : (
        <div className="flex flex-col gap-1.5" data-testid="bracket-round" data-round={active.round}>
          {active.matches.map((match, i) => (
            <MatchCard key={match.id} match={match} index={i} />
          ))}
        </div>
      )}
    </div>
  );
}
