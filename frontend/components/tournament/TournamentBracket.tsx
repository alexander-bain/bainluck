"use client";

import React from "react";
import TournamentBoard from "./TournamentBoard";
import ShowMore, { COLLAPSED_LIST_COUNT } from "./ShowMore";
import {
  TITLE_COLUMN_LABEL,
  bracketProgress,
  reachColumnLabel,
  roundIsUnreached,
  type BracketMatch,
  type BracketRound,
  type BracketSlot,
  type PrematchPair,
  type RoundName,
} from "@/lib/bracket";
import { advanceMarketsForRound } from "@/lib/advanceToStage";
import type { PropMarket } from "@/lib/tournamentProps";
import type { TournamentBoardData } from "@/lib/tournament";

/**
 * The draw bracket — ONE ROUND AT A TIME, chosen from a round strip.
 *
 * Built and shipped behind its own tab (direction C) so that it can never
 * displace the championship boards, which is the charter's explicit safety
 * property: "a janky bracket NEVER blocks or degrades layers 1-2 on the
 * marquee weekend."
 *
 * WHY NOT SEVEN COLUMNS (changed UX-P136, measured against the 128 fixture).
 * A real 128 draw at the 390px viewport this page targets is ~1,360px wide and
 * ~3,450px tall in the first column alone, with the Final a single card at the
 * top of a column you cannot see from there. A 128 draw does not fit on a phone
 * as a tree; it fits as a round. The fold logic is untouched by that, so a
 * desktop tree can come back later without redoing the data path.
 *
 * UX-P137 — ALEX'S FIVE BRACKET RULINGS, all of one complaint: the page made
 * you ask it questions.
 *
 * 1. **The pre-draw view is not empty.** Both WINNER markets exist before the
 *    draw does, and they are the tradeable truth about this tournament today.
 *    So the not-yet-released state now says its sentence and then shows BOTH
 *    boards under it. Both, not the selected one — the ruling is explicit, and
 *    on the day before a ceremony "who wins this thing" is the only question
 *    anyone has.
 *
 * 2. **Every percentage carries its column header.** See `TITLE_COLUMN_LABEL`
 *    for what the number turned out to mean and why nobody could tell. A
 *    decided card means something different by its number, so it says so
 *    itself rather than inheriting the list's header.
 *
 * 3. **Nothing renders blank.** An undetermined slot names the match its
 *    occupant will come from; a decided match prints the pre-match probability
 *    and an explicit outcome. Bold-versus-muted is a font weight, not a result.
 *
 * 4. **An unreached round shows the markets on reaching it** — the register
 *    carries eight of them, priced, and the round the reader just tapped is
 *    the right place for them.
 *
 * 5. **Five then expand**, here as everywhere else on the hub.
 */

/** Half of a decided match: what the market said, and what happened. */
function Outcome({ won }: { won: boolean }) {
  return (
    <span
      className={`shrink-0 rounded px-1.5 py-px text-[10px] font-bold uppercase tracking-[0.04em] ${
        won ? "bg-accent-live/15 text-accent-live" : "bg-surface-border/60 text-text-muted"
      }`}
      data-testid="bracket-outcome"
      data-outcome={won ? "won" : "out"}
    >
      {won ? "Won" : "Out"}
    </span>
  );
}

function SlotLine({
  slot,
  won,
  decided,
  from,
  prematch,
}: {
  slot: BracketSlot | null;
  won: boolean;
  decided: boolean;
  /** The feeder match id, or `null` in round one. */
  from: string | null;
  /** This side's pre-match probability, when the slate had one. */
  prematch: number | null;
}) {
  if (slot === null) {
    // NEVER a bare em-dash (ruling 3). A hole in round one is a register gap
    // and a hole anywhere later is an unplayed feeder; they are different
    // facts and they get different sentences. "Winner of R64 #12" is checkable
    // against the chip strip directly above it.
    return (
      <div
        className="flex items-center py-1.5 text-[12.5px] italic text-text-muted"
        data-testid="bracket-slot-empty"
        data-from={from ?? undefined}
      >
        <span>
          {from === null
            ? "No registered player"
            : `Winner of ${from.replace("-", " #")}`}
        </span>
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

      {decided ? (
        // A decided row prints the PRE-MATCH number, not the title number: the
        // question a finished match answers is "was it the upset", and the
        // title probability of a player who is out is not a fact about
        // anything. Absent when the slate never covered the pair — the outcome
        // still shows, because the ruling is that a decided match is never
        // blank, not that it always has two numbers.
        <span className="flex shrink-0 items-center gap-1.5">
          {prematch !== null && (
            <span
              className="tabular-nums text-[11.5px] text-text-muted"
              data-testid="bracket-prematch"
            >
              {Math.round(prematch * 100)}%
            </span>
          )}
          <Outcome won={won} />
        </span>
      ) : (
        slot.probability !== null && (
          <span
            className="shrink-0 tabular-nums text-[11.5px] text-text-muted"
            data-testid="bracket-title-probability"
          >
            {(slot.probability * 100).toFixed(1)}%
          </span>
        )
      )}
    </div>
  );
}

function MatchCard({
  match,
  index,
  prematch,
}: {
  match: BracketMatch;
  index: number;
  prematch: PrematchPair | undefined;
}) {
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
        {decided && (
          // The card's own header, because this card's number means something
          // the list header does not describe (ruling 2). Only decided cards
          // carry it: sixty-four repetitions of an identical caption is the
          // noise the collapse rulings exist to remove.
          <div
            className="flex items-center justify-between gap-2 pt-1 text-[9.5px] font-bold uppercase tracking-[0.06em] text-text-muted"
            data-testid="bracket-match-header"
          >
            <span>Final</span>
            <span>Pre-match</span>
          </div>
        )}
        <SlotLine
          slot={match.top}
          won={match.top !== null && match.winnerKey === match.top.entity_key}
          decided={decided}
          from={match.topFrom}
          prematch={prematch?.top ?? null}
        />
        <div className="h-px bg-surface-border" />
        <SlotLine
          slot={match.bottom}
          won={match.bottom !== null && match.winnerKey === match.bottom.entity_key}
          decided={decided}
          from={match.bottomFrom}
          prematch={prematch?.bottom ?? null}
        />
      </div>
    </div>
  );
}

/**
 * The markets on REACHING this round (ruling 4).
 *
 * Row grammar borrowed from `components/ProgressionLadder.tsx`, the MLB/NBA
 * playoff table: name, mini bar, percentage. Not the component — that one
 * fires Wikipedia image lookups and wants team colours, neither of which a
 * tennis round has.
 */
function AdvanceTable({
  entries,
  round,
}: {
  entries: ReturnType<typeof advanceMarketsForRound>;
  round: RoundName;
}) {
  const [expanded, setExpanded] = React.useState(false);
  const visible = expanded ? entries : entries.slice(0, COLLAPSED_LIST_COUNT);

  return (
    <div
      className="mt-3 overflow-hidden rounded-2xl border border-surface-border bg-surface-card"
      data-testid="bracket-advance"
      data-round={round}
      data-count={entries.length}
    >
      <div className="flex items-center justify-between gap-2 border-b border-surface-border px-3.5 py-2 text-[10px] font-bold uppercase tracking-[0.06em] text-text-muted">
        <span>Priced to get there</span>
        <span data-testid="bracket-column-label">{reachColumnLabel(round)}</span>
      </div>
      <ul>
        {visible.map((entry) => (
          <li
            key={entry.key}
            className="flex items-center gap-2.5 border-t border-surface-border px-3.5 py-2 first:border-t-0"
            data-testid="bracket-advance-row"
            data-key={entry.key}
            data-live={entry.isLive ? "true" : "false"}
          >
            <span className="min-w-0 flex-1 truncate text-[13.5px] text-text-primary">
              {entry.displayName}
            </span>
            <span className="h-1 w-12 shrink-0 overflow-hidden rounded-full bg-surface-border">
              <span
                className="block h-full rounded-full bg-text-muted/60"
                style={{ width: `${Math.round(entry.probability * 100)}%` }}
              />
            </span>
            <span
              className={`w-9 shrink-0 text-right text-[13px] font-bold tabular-nums ${
                entry.isLive ? "text-text-primary" : "text-text-secondary"
              }`}
            >
              {Math.round(entry.probability * 100)}%
            </span>
          </li>
        ))}
      </ul>
      {entries.length > COLLAPSED_LIST_COUNT && (
        <ShowMore
          expanded={expanded}
          total={entries.length}
          onToggle={() => setExpanded((value) => !value)}
        />
      )}
    </div>
  );
}

export default function TournamentBracket({
  rounds,
  drawReleased,
  initialRound,
  preDrawBoards,
  propMarkets,
  draw,
  prematch,
  initialExpanded = false,
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
  /**
   * BOTH draws' championship boards, shown in the pre-draw state (ruling 1).
   * Deliberately not filtered by the gender pill: the ruling says both, and
   * the day before a ceremony there is exactly one question worth answering.
   */
  preDrawBoards?: TournamentBoardData[];
  /** Curated props, read only for their advance-to-stage members (ruling 4). */
  propMarkets?: PropMarket[];
  draw?: string;
  /** Pre-match probabilities by match id — see `prematchFromSlate` (ruling 3). */
  prematch?: Record<string, PrematchPair>;
  /** Capture seam: render the round list already expanded. */
  initialExpanded?: boolean;
}) {
  const firstLive = rounds.find(
    (r) => !roundIsUnreached(r) && r.matches.some((m) => m.winnerKey === null)
  );
  const fallback = initialRound ?? firstLive?.round ?? rounds[0]?.round;
  const [selected, setSelected] = React.useState<RoundName | undefined>(fallback);
  const [expanded, setExpanded] = React.useState(initialExpanded);

  if (!drawReleased || rounds.length === 0) {
    // NEVER AN EMPTY PAGE WHEN TRADEABLE TRUTH EXISTS (ruling 1). The sentence
    // stays — it is the honest answer to "where is the bracket" — but it is no
    // longer the whole tab. The winner markets are live, priced and the reason
    // most people open this page today, so they are on it.
    const boards = preDrawBoards ?? [];
    return (
      <div data-testid="bracket-unreleased">
        <div className="rounded-2xl border border-dashed border-surface-border bg-surface-card px-4 py-5 text-center">
          <div className="text-[15px] font-semibold text-text-primary">Draw not released</div>
          <div className="mt-1 text-[13px] text-text-secondary">
            The bracket fills in here once the draw is made.
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

  const active = rounds.find((r) => r.round === selected) ?? rounds[0];
  const { played, total } = bracketProgress(rounds);
  const activeIndex = rounds.indexOf(active);
  const feeder = activeIndex > 0 ? rounds[activeIndex - 1] : null;
  const unreached = roundIsUnreached(active);
  const advance =
    propMarkets && draw ? advanceMarketsForRound(propMarkets, active.round, draw) : [];

  const decidedHere = active.matches.filter((m) => m.winnerKey !== null).length;
  // The list header states what the UNDECIDED cards' number means, because
  // decided cards state their own. When every card is decided there are no
  // undecided ones left to describe, so it says the other thing instead —
  // a header describing a column that is not on screen is exactly the failure
  // ruling 2 is about.
  const columnLabel =
    decidedHere === active.matches.length ? "Pre-match" : TITLE_COLUMN_LABEL;

  const visible = expanded
    ? active.matches
    : active.matches.slice(0, COLLAPSED_LIST_COUNT);

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
                onClick={() => {
                  setSelected(round.round);
                  setExpanded(false);
                }}
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
        // One sentence instead of 16 identical empty cards — and then, since
        // UX-P137, the markets on reaching this round, which were never
        // nothing. An unreached round with priced advance markets is content.
        <>
          <div
            className="rounded-2xl border border-dashed border-surface-border bg-surface-card px-4 py-5 text-center text-[13px] text-text-secondary"
            data-testid="bracket-round-unreached"
          >
            Nobody has reached the {active.label.toLowerCase()} yet. It fills in as the{" "}
            {feeder ? feeder.label.toLowerCase() : "previous round"} is played.
          </div>
          {advance.length > 0 && <AdvanceTable entries={advance} round={active.round} />}
        </>
      ) : (
        <>
          {/* THE COLUMN HEADER (ruling 2). A number whose meaning needs asking
              fails the page, and this one meant "to win the whole tournament"
              while sitting beside the opponent it was about to play. */}
          <div
            className="mb-1.5 flex items-center justify-between gap-2 pl-7 pr-3 text-[10px] font-bold uppercase tracking-[0.06em] text-text-muted"
            data-testid="bracket-column-header"
          >
            <span>Match</span>
            <span data-testid="bracket-column-label">{columnLabel}</span>
          </div>

          <div
            className="flex flex-col gap-1.5"
            data-testid="bracket-round"
            data-round={active.round}
          >
            {visible.map((match, i) => (
              <MatchCard
                key={match.id}
                match={match}
                index={i}
                prematch={prematch?.[match.id]}
              />
            ))}
          </div>

          {active.matches.length > COLLAPSED_LIST_COUNT && (
            <div className="mt-1 overflow-hidden rounded-xl border border-surface-border bg-surface-card">
              <ShowMore
                expanded={expanded}
                total={active.matches.length}
                onToggle={() => setExpanded((value) => !value)}
                bordered={false}
              />
            </div>
          )}

          {advance.length > 0 && <AdvanceTable entries={advance} round={active.round} />}
        </>
      )}
    </div>
  );
}
