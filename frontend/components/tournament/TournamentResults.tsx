"use client";

import React from "react";
import Link from "next/link";

import PlayerAvatar from "./PlayerAvatar";
import ShowMore, { COLLAPSED_LIST_COUNT } from "./ShowMore";
import {
  DRAW_LABELS,
  completionNote,
  drawIsPriced,
  formatPrematch,
  prematchAbsenceNote,
  prematchCoverage,
  prematchPercents,
  resultScoreLine,
  resultsEmptyReason,
  resultsForDraw,
  resultEventHref,
  resultLinkCoverage,
  resultsPopulationNote,
  roundHeading,
  sortedResults,
  type TournamentResult,
  type TournamentResults as ResultsModel,
} from "@/lib/tournamentResults";

/**
 * FINISHED MATCHES — Alex's item 9, with the data behind it.
 *
 * "Decided-match scores come from the ESPN API we already use for other scores
 * — wire it; 'no data behind it' is not accepted."
 *
 * Every score here is ESPN's own per-set line score for that competition,
 * joined by the unordered pair of REGISTERED PLAYER names within a draw. Not
 * by date (a rain delay moves it), not by round (the register buckets three
 * qualifying rounds into one), not by matchup (the slate retires a matchup the
 * moment it starts, so joining on one produced 0 results against 199 finished
 * competitions), and never by one name alone — a single-name join is how a
 * first-round result lands on a quarter-final card.
 *
 * ═══ ITEM 12 — DOUBLES, READY ═══
 *
 * This component takes a `draw` and does not care which of the five it is.
 * Censused 2026-08-26: no doubles market exists at either source, so the
 * doubles draws have no markets to show — but ESPN already carries their
 * RESULTS (63 men's, 63 women's, 21 mixed competitions), so those sections have
 * something true the day they are asked for and need no code to light up.
 *
 * ═══ UX-P146 — AND WHAT THE MARKET SAID BEFORE IT ═══
 *
 * Alex, on the UX-P145 desktop artifact: *"finished outcomes on the right must
 * show their PRE-MATCH probabilities alongside the result — a result without
 * the prior probability is half the story on a probability product."*
 *
 * The grey figure beside each name is the market's opening number for that
 * player in that match, normalized against its own pair. Not the last number we
 * saw: a decided match's market drifts toward the result, so "what the market
 * thought" would come out near 100% for every winner — the scoreline read back,
 * wearing the costume of a forecast. `_prematch_by_pair` in
 * `backend/app/utils/tournament_slate.py` has the full argument.
 *
 * IT IS ABSENT ON MOST ROWS, AND THAT IS STATED. A prior exists only where the
 * register pinned a MATCH market for the pair — 12 of 76 on the 2026-08-27
 * production payload. The other 64 are qualifying matches we hold player-level
 * markets for and no match market. The section prints the ratio rather than
 * leaving a column that appears on half the rows to read as a bug, and it never
 * substitutes the title board's number: a player's chance of winning the
 * tournament is not their chance of winning a first-round match, and printing
 * one as the other would be a fabricated answer to a different question under a
 * real player's name.
 *
 * ═══ ON PLAYER IMAGES (Alex's item 8) — PRESENT SINCE UX-P206 ═══
 *
 * Alex, 2026-08-30, on the live Tournament tab: *"player faces missing"*. He
 * was right, and the paragraph that used to sit here was the reason.
 *
 * IT WAS NOT A REVERTED COMMIT. This section never rendered a face; it refused
 * to, on a census, and the refusal was correct on the day it was written and
 * wrong within twenty-four hours. The census was **ESPN's own tennis
 * headshots** — 61% of the men's contenders and 48% of the women's — measured
 * 2026-08-26 against the ruling-8 gate, *"enable ONLY if coverage is ~complete
 * per draw; half-covered looks worse than none."* Half-covered it was, so the
 * gate refused it.
 *
 * The next day UX-P142 shipped a DIFFERENT source. `PlayerAvatar` renders a
 * register-pinned block whose subject is verified offline against the source's
 * own description (`backend/scripts/census_player_images.py`), and ESPN's
 * headshots are not in it — that component's own docstring records them
 * failing the same gate for the same reason. The board, the match list and the
 * playoff grid all moved onto the pinned block. This section kept refusing a
 * source nobody was offering it any more, and so it became the one list on the
 * tab with no faces on it — which is exactly what "half-covered looks worse
 * than none" was written to prevent, arrived at from the other direction.
 *
 * THE GATE, RE-RUN AGAINST THE SOURCE THAT ACTUALLY FEEDS THE COMPONENT,
 * over the 2026-08-30 production payload's 124 rows (248 player slots):
 *
 *   | draw            | slots | face      | flag     | any image  |
 *   |-----------------|-------|-----------|----------|------------|
 *   | men's singles   |  112  |  91  81%  |  21  19% |  112  100% |
 *   | women's singles |  136  | 115  85%  |  21  15% |  136  100% |
 *
 * Zero initials, on either draw. That clears the gate more comfortably than
 * the main-draw fixtures did (94% / 95% face) — because the gate is about
 * whether the COLUMN is uniform, and the flag step is what makes it uniform.
 *
 * The gate is now COMPUTED and not remembered: `build_results` emits
 * `player_slots` / `with_face` / `with_flag`, `resultsImageCoverage` reads
 * them, and a guard asserts the ratio, so the day the register drops a tranche
 * of pins it is a failing test rather than a lane re-arguing a census from
 * memory.
 */

/**
 * ═══ UX-P147, ALEX'S ITEM 3: THE COLUMNS HAVE TO BE COLUMNS ═══
 *
 * On the UX-P146 artifact: the two probabilities and the score column are
 * *"raggedly aligned"*. They were, and the reason is worth writing down because
 * it looks correct in the source.
 *
 * The row was `flex justify-between`: a `flex-1` block holding the two player
 * lines, then the score as a sibling. Inside the block each prior was pushed
 * right with `ml-auto`, which does align the two priors **to each other** — but
 * only to the right edge of a block whose width is `row − score − gap`. The
 * score is text, so its width is the score: `6-3, 6-4` is 56px and
 * `7-6 (7-4), 3-6, 6-4` is 128px. Every row therefore put its prior column at a
 * different x, and the score column's LEFT edge moved with it too. Two
 * quantities that mean the same thing on every row, drawn in a different place
 * on every row — which is precisely what a reader scanning a list cannot do.
 *
 * A flexbox cannot fix this: flex items are sized per line, and there are as
 * many lines as there are matches. Columns that line up across rows need ONE
 * grid whose tracks are shared by every row, which is what this is. The grid is
 * on the `<ul>`, not on the row, and each row is `display: contents` so its
 * three cells land in the parent's tracks.
 *
 * Three tracks:
 *   - **name** `minmax(0,1fr)` — takes the slack and truncates last.
 *   - **prior** `max-content` — as wide as the widest percentage in the whole
 *     list and not one pixel more, right-aligned, `tabular-nums` so `100%` and
 *     `49%` occupy the same box.
 *   - **score** `max-content` — as wide as the LONGEST score in the list, so
 *     the column has one left edge for every row.
 *
 * `max-content` and not a hard `w-[Npx]`: a hard width is a guess about the
 * longest three-set score with two tiebreaks, and the failure mode of guessing
 * low is a truncated result. The grid measures instead.
 *
 * The score spans BOTH player rows and centres against them, because a score
 * describes the match and not the winner — baseline-aligning it to the top line
 * (which is what the old markup did) reads as a property of the player it sits
 * beside.
 */
const RESULT_GRID =
  "grid grid-cols-[minmax(0,1fr)_max-content_max-content] items-center gap-x-3 lg:gap-x-4";

function ResultRow({
  result,
  href,
}: {
  result: TournamentResult;
  /** `/events/{id}` from `resultEventHref`, or `null` when the server did not
   *  resolve one. Never guessed here — see that function. */
  href: string | null;
}) {
  const winner = result.players.find((player) => player.is_winner);
  const loser = result.players.find((player) => !player.is_winner);
  if (!winner || !loser) return null;

  /* ITEM 4: the pair is rounded ONCE, together — see `prematchPercents`. */
  const percents = prematchPercents(result);
  const line = resultScoreLine(result);

  /* THE HOVER HAS TO BE THE ROW, and the row is three cells in the PARENT's
     grid tracks (see `RESULT_GRID`) — there is no box to paint. So the tint
     goes on each cell via `group-hover`, which is what makes a row that is
     three grid items read as one clickable thing. A row with no href gets the
     class and no group ancestor, so it never lights up: the affordance is a
     property of being a link, not of being a row. */
  const cellHover = href ? " transition-colors group-hover:bg-surface-elevated" : "";

  const cells = (
    <>
      {[winner, loser].map((player, index) => {
        /* THE PRIOR (UX-P146, Alex on the UX-P145 artifact): "a result
           without the prior probability is half the story on a probability
           product." In its own grid track, so the two numbers stack and a
           reader can see at a glance which way round the market had it. */
        const prior = formatPrematch(
          player.prematch_probability,
          percents[player.entity_key]
        );
        const edge = index === 0 ? "border-t border-surface-border pt-2.5" : "pb-2.5";
        return (
          <React.Fragment key={player.entity_key}>
            <span
              className={`flex min-w-0 items-baseline pl-3.5 ${edge}${cellHover}`}
              data-testid="result-player"
              data-entity={player.entity_key}
              data-outcome={player.is_winner ? "won" : "lost"}
              data-prematch={player.prematch_probability ?? undefined}
              data-prematch-percent={percents[player.entity_key] ?? undefined}
            >
              {/* RULING 8, ON THIS SECTION AT LAST (UX-P206). 20px and not the
                  match row's 26: two players share one grid row here, so the
                  circle is sized to the 13.5px line it sits on rather than to
                  the 15px line on the other list. `self-center` for the reason
                  `TournamentMatches` gives — the cell is a baseline flex, and a
                  circle on a text baseline reads as a bullet. `dim` on the
                  loser, matching the muted name beside it. */}
              <PlayerAvatar
                name={player.display_name}
                image={player.image}
                size={20}
                dim={!player.is_winner}
              />
              <span
                className={`ml-2 truncate text-[13.5px] ${
                  player.is_winner
                    ? "font-semibold text-text-primary"
                    : "font-normal text-text-muted"
                }`}
              >
                {player.display_name}
              </span>
              {player.seed !== null && (
                <span className="ml-1.5 shrink-0 text-[11px] text-text-muted">
                  [{player.seed}]
                </span>
              )}
              {player.is_winner && (
                <span className="ml-1.5 shrink-0 text-[10px] font-bold uppercase tracking-[0.05em] text-accent-live">
                  won
                </span>
              )}
            </span>

            {/* The prior's TRACK is always here — an empty grid cell is what
                keeps the score column in the same place on a row that has no
                prior, which is 64 of the 76 production rows. The `data-testid`
                is not, because "this row has a prior" must stay a queryable
                fact and an empty span carrying the name of a number would
                make every row look like it had one. */}
            <span
              className={`text-right text-[12px] tabular-nums text-text-secondary ${edge}${cellHover}`}
              data-testid={prior ? "result-prematch" : undefined}
            >
              {/* Ruling 2 again: a number names its own question. The column
                  has no header — there is no room for one beside a score — so
                  the sentence travels with each number for a screen reader,
                  and the section's footnote carries it for everyone else. */}
              {prior && (
                <>
                  <span className="sr-only">
                    Before the match, the market gave {player.display_name}{" "}
                  </span>
                  {prior}
                </>
              )}
            </span>

            {/* THE SCORE (UX-P137 ruling 2), drawn once and spanning both
                player rows. Winner's games first, set by set, so the reader
                never reverses it. UX-P147 gives it the completion: a walkover
                says walkover, and a retirement's real-but-partial score is
                marked rather than passed off as a finished one. */}
            {index === 0 && (
              <span
                className={`row-span-2 py-2.5 pr-3.5 text-right tabular-nums ${
                  line.kind === "score" || line.kind === "retired"
                    ? "text-[13px] font-semibold text-text-secondary"
                    : "text-[11px] font-medium text-text-muted"
                } border-t border-surface-border${cellHover}`}
                data-testid={line.kind === "absent" ? "result-no-score" : "result-score"}
                data-kind={line.kind}
                title={line.explanation}
              >
                <span className="sr-only">{line.explanation}</span>
                <span aria-hidden="true">{line.text}</span>
              </span>
            )}
          </React.Fragment>
        );
      })}
    </>
  );

  return (
    <li
      className="contents"
      data-testid="result-row"
      data-matchup={result.matchup_key}
      data-winner={result.winner_entity_key}
      data-has-score={result.score ? "true" : "false"}
      data-completion={result.completion ?? undefined}
      data-score-kind={line.kind}
      data-event-href={href ?? undefined}
    >
      {/* #2568: ONE anchor for the row, `display: contents` so the three cells
          stay direct children of the `<ul>`'s grid and keep the shared tracks
          the whole layout is built on. One link and not three — a reader
          tabbing this list should hear the match once, not once per column. */}
      {href ? (
        <Link
          href={href}
          className="group contents"
          data-testid="result-link"
          aria-label={`${winner.display_name} beat ${loser.display_name}${
            result.score ? `, ${result.score}` : ""
          } - open the match page`}
        >
          {cells}
        </Link>
      ) : (
        cells
      )}
    </li>
  );
}

export default function TournamentResults({
  results,
  draw,
  roundCount,
  eventIds,
  initialExpanded = false,
}: {
  results: ResultsModel | null | undefined;
  draw: string;
  /**
   * `event_links.by_matchup` from the hub payload — the server's id-anchored
   * `matchup_key -> events.id` map (#2568).
   *
   * Optional, and absent means every row renders as text: a results section
   * served by a server that predates the map degrades to what it did before
   * rather than throwing, and it never invents an address of its own.
   */
  eventIds?: Record<string, number> | null;
  /**
   * How many main-draw rounds this tournament plays (#2449).
   *
   * The anchor ESPN's ORDINAL round names resolve against: `Round 1` is the
   * round of 128 in a 128-draw and the round of 32 in a 32-draw, and the
   * results feed carries the ordinal without the ladder. Omitted means "the
   * full 7-round ladder", which is what every other surface on this page —
   * pills, grid, bracket — already assumes. See `roundHeading`.
   */
  roundCount?: number;
  /** Capture seam: render the full list rather than the collapsed five. */
  initialExpanded?: boolean;
}) {
  const [expanded, setExpanded] = React.useState(initialExpanded);
  const matches = sortedResults(resultsForDraw(results, draw));

  if (matches.length === 0) {
    const reason = resultsEmptyReason(results);
    // Nothing at all to say and no draw played: stay out of the way. Every
    // other empty is stated, because "why is this empty" has a different
    // answer each time and only one of them is "nothing has happened".
    if (reason === null || reason === "No match has finished yet.") {
      if (!drawIsPriced(draw)) return null;
    }
    return (
      <section data-testid="tournament-results" data-draw={draw} data-count={0}>
        <h2 className="mb-2 mt-6 text-xs font-bold uppercase tracking-[0.07em] text-text-muted">
          Finished
        </h2>
        <div
          className="rounded-2xl border border-surface-border bg-surface-card px-3.5 py-3.5"
          data-testid="results-empty"
        >
          <p className="text-[12.5px] leading-snug text-text-secondary" data-testid="results-empty-reason">
            {reason}
          </p>
        </div>
      </section>
    );
  }

  const shown = expanded ? matches : matches.slice(0, COLLAPSED_LIST_COUNT);
  const completion = completionNote(matches);
  /* Counted over THIS draw's rendered rows rather than read off the payload's
     `with_prematch`, which is the all-draws total. A footnote that says "12 of
     76" under a list of 24 is a footnote about a different list. */
  const prior = prematchCoverage(matches);
  /* #2450: the total says which population it is over, or says nothing. */
  const population = resultsPopulationNote(matches);
  /* #2568, and the payload's own "NO SILENT CAPS" rule applied to the reader:
     a list where some rows open a page and some do not has to say which, or the
     dead ones read as a broken page rather than as the edge of our coverage. */
  const links = resultLinkCoverage(matches, eventIds);

  return (
    <section data-testid="tournament-results" data-draw={draw} data-count={matches.length}>
      <h2 className="mb-2 mt-6 text-xs font-bold uppercase tracking-[0.07em] text-text-muted">
        Finished
        <span className="ml-1.5 font-normal normal-case tracking-normal">
          · {DRAW_LABELS[draw] ?? draw} · {matches.length}
        </span>
      </h2>

      {/* WHAT THE COUNT COUNTS (#2450). More than half of this total was
          qualifying on the live payload, and a reader adding up a 128-draw's
          main-draw matches will never reach it. See `resultsPopulationNote`. */}
      {population && (
        <p
          className="-mt-1 mb-2 text-[11px] leading-snug text-text-muted"
          data-testid="results-population-note"
        >
          {population}
        </p>
      )}
      <div className="overflow-hidden rounded-2xl border border-surface-border bg-surface-card">
        {/* ONE grid for the whole list, so a column is a column across every
            row — see `RESULT_GRID`. The round headings are `col-span-3` bands
            inside it rather than siblings of it, because a heading outside the
            grid would reset the tracks below it and put the second round's
            score column somewhere else again. */}
        <ul className={RESULT_GRID}>
          {shown.map((result) => (
            <React.Fragment key={result.matchup_key}>
              <li
                className="col-span-3 border-t border-surface-border bg-surface-elevated px-3.5 py-1 text-[10px] font-bold uppercase tracking-[0.05em] text-text-muted first:border-t-0"
                data-testid="result-round"
              >
                {roundHeading(result, roundCount)}
              </li>
              <ResultRow
                result={result}
                href={resultEventHref(result, eventIds)}
              />
            </React.Fragment>
          ))}
        </ul>
        {matches.length > COLLAPSED_LIST_COUNT && (
          <ShowMore
            expanded={expanded}
            total={matches.length}
            onToggle={() => setExpanded((value) => !value)}
          />
        )}
      </div>
      {/* PROVENANCE, and the coverage number with it. A results list shorter
          than the day's play is either a join problem or the schedule, and the
          reader is entitled to know which without asking. */}
      {/* WHAT THE GREY NUMBER IS (UX-P146). Two facts, and both are owed: what
          the number means, and why most rows have not got one. A column that
          appears on twelve rows out of twenty-four and explains itself nowhere
          reads as a bug in the page rather than as the edge of our coverage. */}
      {prior.withPrior > 0 && (
        <p
          className="mt-2 max-w-[80ch] text-[11px] leading-snug text-text-muted"
          data-testid="results-prematch-note"
          data-with-prematch={prior.withPrior}
          data-total={prior.total}
          data-held-without-opening={prior.heldWithoutOpening}
          data-untied={prior.untied}
        >
          The grey figure beside a name is what the market gave that player{" "}
          <b className="font-semibold text-text-secondary">before the match started</b> —
          its opening number, not a reading taken after the result was known.{" "}
          {prior.withPrior < prior.total && (
            <>
              Shown on{" "}
              <b className="font-semibold text-text-secondary">
                {prior.withPrior} of {prior.total}
              </b>
              .{" "}
              {/* ═══ ux/1034 A3: THIS SENTENCE USED TO BE A CLAIM ABOUT A VENUE
                  ═══

                  It read "The rest are matches nobody ran a market on". Alex
                  found it under Shelton–Hurkacz, where it is false and
                  measurably so: Polymarket had a market on that match, its
                  price history simply begins at 17:38Z and the match began at
                  17:08Z. What is missing is an OPENING, not a market.

                  The field it was written from only ever described US — whether
                  our register tied the fixture to a market of ours. Nothing in
                  this payload knows what Kalshi or Polymarket chose to list, so
                  the two cases it CAN tell apart are named and the third is not
                  asserted. `prematchCoverage` counts them. */}
              {prematchAbsenceNote(prior)}{" "}
              We would rather leave the space empty than fill it with a number about
              a different question.
            </>
          )}
        </p>
      )}
      {links.linked > 0 && links.linked < links.total && (
        <p
          className="mt-2 text-[11px] leading-snug text-text-muted"
          data-testid="results-link-note"
          data-linked={links.linked}
          data-total={links.total}
        >
          <b className="font-semibold text-text-secondary">
            {links.linked} of {links.total}
          </b>{" "}
          {/* Careful with this sentence: the rows that do not link fail for TWO
              different reasons — most are qualifying matches we hold no market
              for at all, but some do have a market that is simply not yet tied
              to an event (#2592). "We hold no market for them" would be false
              of the second group, so the claim is about the LINK, which is the
              only thing true of both. */}
          open a match page. We cannot link the rest to one yet.
        </p>
      )}
      <p className="mt-2 text-[11px] leading-snug text-text-muted" data-testid="results-provenance">
        Scores from ESPN.{" "}
        {/* UX-P147: this used to read "N finished without a completed set
            score (retirement or walkover)" — a hedge between two things the
            source distinguishes, whose count was the walkovers only while the
            retirements it named printed above as ordinary results. Both are
            named now, and both are counted. */}
        {completion && <span data-testid="results-completion-note">{completion} </span>}
        {(results?.unregistered_pairs ?? 0) > 0 &&
          `${results?.unregistered_pairs} other finished match${
            results?.unregistered_pairs === 1 ? "" : "es"
          } involve players we hold no market for.`}
      </p>
    </section>
  );
}
