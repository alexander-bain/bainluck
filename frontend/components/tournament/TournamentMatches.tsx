"use client";

import React from "react";

import EventCardShell from "@/components/EventCardShell";
import LiquidityMark from "@/components/LiquidityMark";
import PlayerAvatar from "./PlayerAvatar";
import ShowMore, { COLLAPSED_LIST_COUNT } from "./ShowMore";
import {
  defaultMatchRound,
  matchRoundPills,
  matchesInRound,
  titleChipDescription,
  titleChipLabel,
  type MatchListEntry,
  type MatchListSide,
  type MatchRoundKey,
} from "@/lib/matchList";
import {
  dayHeading,
  formatMove,
  formatSlateProbability,
  localDayKey,
  moveDirection,
  type SlateNotice,
} from "@/lib/slate";

/**
 * THE MATCH LIST — the Tournament tab's spine (UX-P138, Alex's ruling 4).
 *
 * Supersedes `TournamentSlate`. Same job, one level up: the slate was "today's
 * matches", this is **the tournament's matches**, organised by round, with the
 * qualifying feed and the main draw in one list because they were always one
 * list. See `lib/matchList.ts` for the join and for why the two tabs stopped
 * each having their own.
 *
 * FOUR RULINGS LAND ON THIS COMPONENT, and they pull against each other, which
 * is the interesting part:
 *
 * 1. **MATCH ODDS EVERYWHERE A MATCH SHOWS** — standing rule. And the
 *    nothing-played view carries BOTH the match number and the title number.
 *    That is two numbers per player, four per card, on a 390px phone.
 *
 * 6. **KILL THE REDUNDANCY** — "probability + movement delta + a sentence
 *    restating both is three renderings of one fact."
 *
 * Ruling 1 adds density and ruling 6 removes it, and Alex named the tension
 * himself: "the density problem is yours to solve ... without it being too
 * busy". The resolution this component commits to, so it can be argued with:
 *
 *   - **One number is big.** The match probability, 17px, tabular, right-
 *     aligned. It is the answer to the question the row is about.
 *   - **The title chance is a chip, and the chip says what it is.** `22%
 *     title`, 10px, muted, inline after the name. Self-labelling is not
 *     decoration here: UX-P137's whole ruling 2 was Alex unable to tell what a
 *     bare percentage on this page meant, and the answer was the title
 *     probability printed beside the opponent a player was about to play. A
 *     chip reading `22%` would rebuild that confusion in a smaller font.
 *   - **The delta stays, the sentence goes.** `−4` beside the number is the
 *     movement; the sentence that used to restate both is deleted at the
 *     source (see `lib/slate.ts`).
 *   - **The row gets one line of metadata, not three.** Time, draw, age.
 *
 * 7. **Where to watch moves to the DETAIL view** — Alex's clarification,
 *    overruling UX-P137's per-row placement. UX-P154 kept the ruling and moved
 *    the view: the detail view is the EVENT PAGE now, so the channel renders in
 *    `TournamentExtensions` and this list carries no broadcast at all. It did
 *    not come back onto the row; the row got shorter, not busier.
 *
 * ═══ AND THE STRUCTURE ITSELF (UX-P154, Alex's item 2) ═══
 *
 * *"it kinda feels like we're reinventing the event card inside the tournament
 * product"*. The accordion, the link row and the bespoke bordered container are
 * gone; each row is `EventCardShell` — the same component `EventCard` renders —
 * and the whole card routes to `/events/{id}`. See `MatchRow` for what moved
 * where, and `EventCardShell` for why this is the shell rather than `EventCard`
 * itself.
 *
 * 2. **A decided match shows the SCORE with the outcome.** The seam is here
 *    and rendered. It is empty on real data and will be until a result feed
 *    exists — see `SlateMatch.score`, which says so at length rather than
 *    letting the blank be discovered.
 */

/** The column header. Every number on this page names its own question. */
export const MATCH_COLUMN_LABEL = "To win this match";

function TitleChip({ side }: { side: MatchListSide }) {
  const label = titleChipLabel(side.titleChance);
  if (label === null) return null;
  return (
    <span
      className="ml-1.5 shrink-0 rounded bg-surface-border/50 px-1 py-px text-[10px] font-semibold tabular-nums text-text-muted"
      data-testid="match-title-chip"
      data-entity={side.entityKey ?? undefined}
      title={titleChipDescription(side.displayName, side.titleChance as number)}
    >
      <span className="sr-only">
        {titleChipDescription(side.displayName, side.titleChance as number)}.{" "}
      </span>
      <span aria-hidden="true">{label}</span>
    </span>
  );
}

/** Won / Out — a font weight is not a result (UX-P137, ruling 3). */
function OutcomeChip({ won }: { won: boolean }) {
  return (
    <span
      className={`shrink-0 rounded px-1.5 py-px text-[10px] font-bold uppercase tracking-[0.04em] ${
        won ? "bg-accent-live/15 text-accent-live" : "bg-surface-border/60 text-text-muted"
      }`}
      data-testid="match-outcome"
      data-outcome={won ? "won" : "out"}
    >
      {won ? "Won" : "Out"}
    </span>
  );
}

function SideLine({
  side,
  entry,
  favourite,
}: {
  side: MatchListSide;
  entry: MatchListEntry;
  favourite: boolean;
}) {
  if (side.placeholder !== "none") {
    // NEVER a bare em-dash (UX-P137, ruling 3). A round-one hole is a register
    // gap and a later hole is an unplayed feeder; they are different facts and
    // they get different sentences.
    return (
      <div
        className="flex items-center py-1 text-[13px] italic text-text-muted"
        data-testid="match-side-empty"
        data-placeholder={side.placeholder}
      >
        {side.displayName}
      </div>
    );
  }

  const move = formatMove(side.move);
  const direction = moveDirection(side.move);

  return (
    <div
      className={`flex items-baseline justify-between gap-2 py-0.5 ${
        entry.decided && !side.isWinner ? "text-text-muted" : ""
      }`}
      data-testid="match-side"
      data-entity={side.entityKey ?? undefined}
      data-favourite={favourite ? "true" : "false"}
      data-won={side.isWinner ? "true" : "false"}
    >
      <span className="flex min-w-0 items-baseline">
        {/* RULING 8. `self-center` because the row is a baseline flex — a
            26px circle on a text baseline sits a third of its height below
            the line and reads as a bullet, not a portrait. */}
        <PlayerAvatar
          name={side.displayName}
          image={side.image}
          size={26}
          dim={entry.decided && !side.isWinner}
        />
        <span
          className={`ml-2 min-w-0 self-center truncate text-[15px] ${
            favourite || side.isWinner
              ? "font-semibold text-text-primary"
              : "font-normal text-text-secondary"
          }`}
        >
          {side.displayName}
        </span>
        {side.seed !== null && (
          <span className="ml-1.5 shrink-0 text-xs font-normal text-text-muted">
            [{side.seed}]
          </span>
        )}
        {/* RULING 1's secondary. Muted, small, and it says the word "title". */}
        <TitleChip side={side} />
      </span>

      <span className="flex shrink-0 items-baseline gap-2">
        {entry.decided && <OutcomeChip won={side.isWinner} />}
        {/* NO EM-DASH ON AN UNPRICED ROW (UX-P142). Two "—" in the number
            column, once per side, on 96 rows, is the em-dash UX-P137's ruling
            3 deleted: it says "we have nothing" where the truth is "nobody has
            opened a book on a match four days out". The row's own metadata
            line already says `No market yet`, once, in words. */}
        {move !== "" && !entry.decided && (
          <span
            className={`text-[11px] tabular-nums ${
              !entry.isLive
                ? "text-text-muted"
                : direction === "up"
                  ? "text-accent-live"
                  : "text-accent-danger"
            }`}
            data-testid="match-move"
          >
            {move}
          </span>
        )}
        {/* UX-P157. Before the number and inside the same baseline run, so it
            qualifies THIS side rather than the row: on a match the two sides
            are two venue rows and the underdog's is routinely the thin one.
            Decorative — the whole match card is a link (Alex's UX-P154 item 2)
            and a focusable control inside it would put a second tab stop in
            front of every fixture. The `title` still answers a mouse, and the
            row's own detail note carries the sentence for everyone else. */}
        {entry.priced && (
          <LiquidityMark
            facts={{
              liquidity: side.liquidity,
              liquidity_reasons: side.liquidity_reasons,
            }}
            observedAt={side.observedAt}
            size="sm"
            decorative
          />
        )}
        {entry.priced && (
          <span
            className={`text-[17px] font-bold tabular-nums tracking-tight ${
              entry.isLive && !entry.decided ? "text-text-primary" : "text-text-secondary"
            }`}
            data-testid="match-probability"
          >
            {formatSlateProbability(side.matchProbability)}
          </span>
        )}
      </span>
    </div>
  );
}

/**
 * ═══ THE WHOLE CARD IS THE TARGET (UX-P154, Alex's item 2) ═══
 *
 * Alex, reviewing the UX-P152 artifact's panel 4 (2026-08-28, relayed through
 * the UX-P154 runner directive):
 *
 *   *"it kinda feels like we're reinventing the event card inside the
 *   tournament product"* — and the instruction: **no "See more on this match"
 *   link row; the whole match card is clickable, exactly like every other card
 *   in the product; the tournament list uses THE standard event-card
 *   component.**
 *
 * So three things went, and they went together because they were one mistake:
 *
 *   - **the link row.** `See more on this match` was a link INSIDE a card, in a
 *     product where a card IS a link. A reader who taps the card and gets an
 *     accordion has learned that this list works differently from every other
 *     list on the site, which is a cost paid on every row for a fact worth one.
 *   - **the accordion.** The expand/collapse existed to hold the link and two
 *     lines. With the whole card routing to `/events/{id}`, the tap is the
 *     navigation and there is nothing left to expand.
 *   - **the bespoke shell.** The row drew its own bordered container. It now
 *     renders `EventCardShell` — the same component `EventCard` renders — so
 *     `data-testid="event-card"` is true of this list, which is the DOM-level
 *     claim ruling 047 is written against.
 *
 * WHERE THE DRAWER'S CONTENTS WENT, since a deleted surface has to say:
 *
 *   - **where to watch** → the event page's tournament extensions. Alex's
 *     ruling 7 put it "in the DETAIL view" rather than on every row, and the
 *     detail view is now the event page. It did not come back onto the row.
 *   - **the one sentence** (`detailNote`, ruling 6) → onto the card. It only
 *     fires when it adds something the numbers cannot say — an upset, a
 *     disagreement, an unquoted fixture — and it was behind the tap only
 *     because the drawer happened to exist.
 *
 * A FIXTURE WITH NO EVENT GETS NO LINK, and the card says so by not being one.
 * `entry.eventId` is resolved server-side by id (the register's pinned
 * match-winner `market_id` dereferenced through `futures_markets.event_id`) and
 * is `null` rather than guessed. 28 of the register's fixtures are qualifying
 * matches whose draw was never ingested as events; a link to the wrong match is
 * worse than no link.
 */
function MatchRow({
  entry,
  matchHref,
}: {
  entry: MatchListEntry;
  /** `/events/{id}` — the STANDARD event page — or `null` when the fixture
   *  has no `events` row to route to. Never a tournament-private URL. */
  matchHref: string | null;
}) {
  const time = entry.scheduledDate ? formatMatchTime(entry.scheduledDate) : null;
  const names = entry.sides.map((side) => side.displayName).join(" v ");

  return (
    <li
      data-testid="match-row"
      data-match={entry.id}
      data-round={entry.round}
      data-live={entry.isLive ? "true" : "false"}
      data-decided={entry.decided ? "true" : "false"}
      data-coherent={entry.coherent ? "true" : "false"}
    >
      <EventCardShell
        href={matchHref}
        live={entry.isLive && !entry.decided}
        finished={entry.decided}
        ariaLabel={`${names}${entry.decided ? " - Final" : ""}`}
        /* `cn` is tailwind-merge, so this REPLACES the shell's `p-3 sm:p-4`
           rather than fighting it — no `!important` needed, and the shell's
           default stays the default for every other caller. */
        className="p-3.5 sm:p-3.5"
        dataAttrs={{ "data-match-card": entry.id }}
      >
        <div className="mb-1 flex items-center gap-2 text-[10.5px] uppercase tracking-[0.06em] text-text-muted">
          {time && <span className="tabular-nums">{time}</span>}
          {time && entry.drawLabel && <span aria-hidden="true">·</span>}
          {entry.drawLabel && <span>{entry.drawLabel}</span>}
          {entry.freshnessLabel !== null && (
            <span
              className="normal-case tracking-normal text-accent-warning"
              data-testid="match-age"
            >
              {entry.freshnessLabel}
            </span>
          )}
        </div>

        {/* UNPRICED IS NOT INCOHERENT (UX-P142).

            `!entry.coherent` used to be one branch, and it collapsed the row
            to a single "A vs B" line. That is the right treatment for two
            quotes that disagree: there is a split and we are refusing to show
            it, so the two names and a sentence are all the row may say.

            It is the WRONG treatment for the released main draw. Alex's
            finding was "the page shows none of the draw", and this line is how
            it would have stayed shown: 96 fixtures rendered as bare text — no
            faces, no seeds, no title chip, no structure — because a price rule
            wrote the layout. Nothing is being withheld on these rows; there is
            simply no match market yet, and everything else about the fixture
            is known and worth printing.

            So an unpriced row renders as a full row with no match number. The
            `SideLine` prints `—` for a null probability, which is what it has
            always done. */}
        {!entry.coherent && entry.priced ? (
          <div data-testid="match-incoherent">
            <div className="text-[15px] font-semibold text-text-primary">
              {entry.sides.map((side) => side.displayName).join(" vs ")}
            </div>
          </div>
        ) : (
          <>
            <SideLine
              side={entry.sides[0]}
              entry={entry}
              favourite={
                !entry.decided &&
                (entry.sides[0].matchProbability ?? 0) >=
                  (entry.sides[1].matchProbability ?? 0)
              }
            />
            <SideLine
              side={entry.sides[1]}
              entry={entry}
              favourite={
                !entry.decided &&
                (entry.sides[1].matchProbability ?? 0) >
                  (entry.sides[0].matchProbability ?? 0)
              }
            />
          </>
        )}

        {/* RULING 2. The score rides WITH the outcome, on the card, not behind
            the tap: "6-1, 6-4" is the result, and a result is not a detail. */}
        {entry.decided && entry.score !== null && (
          <div
            className="mt-1 text-[12px] font-semibold tabular-nums text-text-secondary"
            data-testid="match-score"
          >
            {entry.score}
          </div>
        )}

        {/* RULING 6: the ONE sentence, and only when it adds something. On the
            card since UX-P154 deleted the drawer it used to sit in. */}
        {entry.detailNote && (
          <div
            className="mt-1.5 text-[11.5px] leading-snug text-text-secondary"
            data-testid="match-detail-note"
          >
            {entry.detailNote}
          </div>
        )}
      </EventCardShell>
    </li>
  );
}

/**
 * When the match is, in the READER's timezone — "10:35 AM", or "Tomorrow 10:35 AM".
 *
 * The day rides the row rather than a heading. `TournamentSlate` grouped by
 * calendar day, which was right when the list was "today's matches"; ruling 4
 * groups by ROUND instead, and a round spans days. Two nested groupings on one
 * list is a structure the reader has to learn, so the day becomes a token on
 * the row and only when it is not today — a list where every row says "Today"
 * has taught the reader to stop reading the first token.
 */
function formatMatchTime(scheduled: string, now: Date = new Date()): string {
  const at = new Date(scheduled);
  if (Number.isNaN(at.getTime())) return scheduled;
  const clock = at.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  const day = dayHeading(localDayKey(scheduled), now);
  return day === "Today" ? clock : `${day} ${clock}`;
}

export default function TournamentMatches({
  entries,
  initialRound,
  initialExpanded = false,
  emptyHint,
  notice,
}: {
  entries: MatchListEntry[];
  /* UX-P152: the `slug` prop is gone. It existed to build a tournament-private
     match URL; a row now routes to `/events/{id}`, which needs no tournament
     context at all. Callers that still pass it are harmless — TS just ignores
     an extra prop on a spread — but none do. */
  /** Capture seam and deep-link seam: which round pill is active. */
  initialRound?: MatchRoundKey;
  /** Capture seam: render the round already expanded. */
  initialExpanded?: boolean;
  /* UX-P154: `initialOpenMatchId` is gone with the drawer it opened. There is
     no per-row expanded state left to seed — the tap navigates. */
  /** What to say when this draw has no matches at all. */
  emptyHint?: string;
  /**
   * The feed-wide honesty banner (`slateNotice`). Kept verbatim from
   * `TournamentSlate`: it is the ONLY thing that says "these are the last
   * prices we saw, not live prices" about the list as a whole, and the
   * per-row age labels do not add up to that sentence.
   */
  notice?: SlateNotice | null;
}) {
  const pills = matchRoundPills(entries);
  const fallback = initialRound ?? defaultMatchRound(entries) ?? undefined;
  const [round, setRound] = React.useState<MatchRoundKey | undefined>(fallback);
  const [expanded, setExpanded] = React.useState(initialExpanded);

  if (entries.length === 0) {
    return (
      <section
        className="mt-6 rounded-2xl border border-surface-border bg-surface-card px-4 py-6 text-center"
        data-testid="matches-empty"
      >
        <div className="text-[15px] font-semibold text-text-primary">No matches scheduled</div>
        <p className="mt-1 text-[13px] text-text-secondary">
          {/* Ruling 142: "Matches appear here as they are scheduled" described
              what the section would hold. The schedule is the fact. */}
          {emptyHint ?? "Nothing is on right now. This is where the day's matches sit."}
        </p>
      </section>
    );
  }

  const active = round && pills.some((pill) => pill.round === round) ? round : pills[0].round;
  const inRound = matchesInRound(entries, active);
  const visible = expanded ? inRound : inRound.slice(0, COLLAPSED_LIST_COUNT);
  const activePill = pills.find((pill) => pill.round === active);
  const incoherent = inRound.filter((entry) => !entry.coherent).length;

  return (
    <section data-testid="tournament-matches" data-round={active}>
      {notice && (
        <div
          className="mt-6 flex items-start gap-2 rounded-2xl border border-surface-border bg-accent-warning/10 px-3.5 py-2.5 text-[11.5px] text-text-secondary"
          data-testid="matches-notice"
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

      {/* THE ROUND PILLS (ruling 4). Only rounds that HAVE matches get a pill:
          a pill onto a wall is the empty-tab failure with a smaller footprint.
          Suppressed entirely at one round, because a strip of one is a label
          pretending to be a control. */}
      {pills.length > 1 && (
        <div
          className={`-mx-4 overflow-x-auto px-4 ${notice ? "mt-3" : "mt-6"}`}
          data-testid="match-round-strip"
          role="group"
          aria-label="Round"
        >
          <div className="flex gap-1.5 pb-1">
            {pills.map((pill) => {
              const on = pill.round === active;
              return (
                <button
                  key={pill.round}
                  type="button"
                  aria-pressed={on}
                  onClick={() => {
                    setRound(pill.round);
                    setExpanded(false);
                  }}
                  data-testid="match-round-pill"
                  data-round={pill.round}
                  data-selected={on ? "true" : "false"}
                  className={`shrink-0 rounded-full px-3 py-1.5 text-[12.5px] font-semibold transition-colors ${
                    on
                      ? "bg-text-primary text-surface-card"
                      : "bg-surface-border/50 text-text-secondary"
                  }`}
                >
                  {pill.shortLabel}
                  <span className="ml-1 text-[10.5px] font-normal tabular-nums opacity-70">
                    {pill.decided > 0 ? `${pill.decided}/${pill.total}` : pill.total}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      <h2
        className={`mb-2 text-xs font-bold uppercase tracking-[0.07em] text-text-muted ${
          pills.length > 1 ? "mt-3" : "mt-6"
        }`}
        data-testid="match-round-heading"
      >
        {activePill?.label ?? ""}
        <span className="ml-1.5 font-normal normal-case tracking-normal">
          · {inRound.length} {inRound.length === 1 ? "match" : "matches"}
        </span>
      </h2>

      {/* Every number says what it means (UX-P137, ruling 2). */}
      <div
        className="mb-1.5 flex items-center justify-between gap-2 px-3.5 text-[9.5px] font-bold uppercase tracking-[0.06em] text-text-muted"
        data-testid="match-column-header"
      >
        <span>Match</span>
        <span data-testid="match-column-label">{MATCH_COLUMN_LABEL}</span>
      </div>

      {/* A STACK OF CARDS, NOT A TABLE WITH DIVIDERS (UX-P154). The single
          bordered container with hairline rows was the bespoke shell Alex
          named; the product's other event lists are a gapped stack of cards
          and this one now is too. */}
      <ol className="space-y-2">
        {visible.map((entry) => (
          <MatchRow
            key={entry.id}
            entry={entry}
            matchHref={entry.eventId !== null ? `/events/${entry.eventId}` : null}
          />
        ))}
      </ol>
      {inRound.length > COLLAPSED_LIST_COUNT && (
        <div className="mt-2 overflow-hidden rounded-2xl border border-surface-border bg-surface-card">
          <ShowMore
            expanded={expanded}
            total={inRound.length}
            onToggle={() => setExpanded((value) => !value)}
          />
        </div>
      )}

      {incoherent > 0 && (
        <p className="mt-2 text-[11px] text-text-muted" data-testid="match-incoherent-count">
          {/* UX-P146: was "prices that do not agree". Alex's product-wide
              ruling on the noun; "numbers" is what they are to a reader. */}
          {incoherent} {incoherent === 1 ? "match has" : "matches have"} numbers that do not agree
          yet.
        </p>
      )}
    </section>
  );
}
