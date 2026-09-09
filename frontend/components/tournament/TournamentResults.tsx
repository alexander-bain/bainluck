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
  prematchAttribution,
  prematchCoverage,
  prematchPercents,
  resultScoreLine,
  resultsEmptyReason,
  resultsForDraw,
  resultEventHref,
  resultLinkCoverage,
  resultsPopulationNote,
  roundHeading,
  scoreWrapChunks,
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
 *
 * ═══ live/071: ON A PHONE THE SCORE TRACK WAS EATING THE NAMES ═══
 *
 * `max-content` is the right sizing on a screen with slack and the wrong one on
 * a screen without any. Measured on production, 390px, the men's finished list
 * (the `ul` is 332px wide there):
 *
 *     name 114.16   prior 64.59   score 129.25   (+ two 12px gaps)
 *
 * The score column — sized by `max-content` to the longest score in the WHOLE
 * list, `7-6, 6-7, 6-3, 6-4` — took 39% of the card, and the name track took
 * what was left. Inside it the avatar, its margin and the padding cost 42px, so
 * the loser's name span was 72px and the winner's, which also carries the win
 * marker, was 39px: FOUR CHARACTERS. Every one of the ten names on the served
 * list was clipped, and the winner's worse than the loser's — `Stefanos
 * Tsitsipas` beat `Jiri Lehecka` and the row read `Ste… won  Jiri Lehecka`. A
 * finished-match list whose one job is to say who won printed the winner as the
 * least readable thing on the row.
 *
 * `fit-content(76px)` is `max-content` capped: the track takes what the score
 * needs up to 76px and then WRAPS, so a four-set score becomes two lines inside
 * a cell that already spans two player rows, and the row does not grow. It is
 * not a hard width and the comment above still holds: a score longer than the
 * cap is not truncated, because `fit-content` floors at min-content, so the
 * widest unbreakable chunk (`7-6 (7-4),`, ~66px) always fits and the column
 * simply grows past the cap on a list that contains one.
 *
 * 76 AND NOT 72, AND THE 4px IS THE CELL'S OWN PADDING. The cap sizes the
 * TRACK; the text gets the track minus the score cell's `pr-3.5`. At 72 the
 * text area was 58px and a two-set line (`7-6, 6-7,` — 27.3 + 3.9 + 27.3 =
 * 58.5px, measured in the capture rig) missed it by half a pixel, so every
 * four-set score came out `7-6,` / `6-7,` / `6-3, 6-4`: three ragged lines in a
 * column sized for two. 76 leaves 62px of text and the same score sets two
 * balanced lines. A cap chosen against the text width alone is 14px wrong here.
 *
 * From `sm:` up the cap is gone and the track is `max-content` exactly as it
 * was — at 640px the three columns fit with ~400px of name to spare, so a
 * wrapped score there would be a wrap nothing asked for.
 *
 * ⚠️ THE CAP ONLY WORKS WHILE THE SCORE MAY WRAP. A `whitespace-nowrap` on the
 * score cell would raise its min-content to the full score and put the 129px
 * column straight back, with the classes here still reading as if they capped
 * it. `tournamentAxisAndResults.test.tsx` guards the pair.
 */
const RESULT_GRID =
  "grid grid-cols-[minmax(0,1fr)_max-content_fit-content(76px)] sm:grid-cols-[minmax(0,1fr)_max-content_max-content] items-center gap-x-3 lg:gap-x-4";

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
        /* CERT-812: which rung this ONE number came from, in both registers.
           Per player and not per match — `prematchPercents` already has a
           branch for a row where only one side carries a prior, and a
           match-level label would put the wrong claim on the other side. */
        const attribution = prematchAttribution(player);
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
              {/* THE WIN MARKER, AND WHY IT IS A TICK ON A PHONE (live/071).
                  It is `shrink-0` — correctly, a marker that truncates says
                  nothing — so its width comes out of the name beside it, and
                  the word cost 33px of a 114px cell: the winner's name got 39px
                  and the loser's, which carries no marker, got 72. The one name
                  the row exists to state was the one cut hardest.

                  The tick is 14px with its margin, so the phone spends 19px
                  fewer on saying the same thing, and the WORD is still there
                  for anyone who cannot see the tick — `sr-only` is not
                  `hidden`. From `sm:` up the word is visible again exactly as
                  it was; there is room for it there. */}
              {player.is_winner && (
                <span
                  className="ml-1.5 shrink-0 text-[10px] font-bold uppercase tracking-[0.05em] text-accent-live"
                  data-testid="result-won-marker"
                >
                  <span aria-hidden="true" className="sm:hidden">
                    ✓
                  </span>
                  <span className="sr-only sm:not-sr-only">won</span>
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
              /* CERT-812 required this at the ROW, not just in the footer. The
                 rung is a queryable fact per number now, so a guard can assert
                 which claim each figure is making. */
              data-prematch-source={prior ? attribution.source ?? undefined : undefined}
            >
              {/* Ruling 2 again: a number names its own question. The column
                  has no header — there is no room for one beside a score — so
                  the sentence travels with each number for a screen reader,
                  and the section's footnote carries it for everyone else.

                  CERT-812: that sentence used to be the literal string "the
                  market gave" on EVERY row, so the one reader who cannot see a
                  label got the exact false claim this ship exists to stop
                  making — on 61 of today's 172 priors. It is now the rung's own
                  clause, from the same decision the marker uses. */}
              {prior && (
                <>
                  <span className="sr-only">
                    {attribution.said} {player.display_name}{" "}
                  </span>
                  {prior}
                  {/* ═══ #4125 ITEM 2: THE VISIBLE MARKER IS GONE ═══
                      Alex, on this page, 2026-09-08 4:00pm PT: *"Why does the
                      tournament page awkwardly include the word 'books' on each
                      completed event card and then show a weird disclaimer
                      underneath. Keep the design consistent with event cards
                      elsewhere."*

                      "Elsewhere" is measurable, and neither surface does what
                      this one did. `FeedCard` (`/sports`, every feed list)
                      prints the pre-match figure as a bare grey `NN%` beside
                      the name with NO visible word — the rung lives only in the
                      spoken clause and `data-prematch-source`
                      (`FeedCard.tsx:694-706`). Discover's `EventCard` prints
                      ONE caption for the whole card
                      (`Pre-match · sportsbooks`, `EventCard.tsx:301`). This
                      list printed the word on BOTH player rows, so a
                      five-match list said it ten times.

                      🔴 THIS DOES NOT RE-OPEN CERT-812, and the reason is the
                      whole argument. CERT-812's finding was a FALSE CLAIM: the
                      spoken clause said "the market gave" on 61 of 172 rows
                      that were a sportsbook median. Two things were shipped
                      against it — a rung-specific clause and this marker. D65
                      (ux/1071) then replaced the forked clause with
                      `PREMATCH_SAID`, "Pre-match probability:", which is true
                      of every rung, on Alex's words *"Shouldn't reference
                      sportsbooks."* A clause that names no venue cannot name
                      the wrong one, so the false claim is already dead and the
                      marker is the last thing still saying a venue out loud.
                      Both of CERT-812's registers survive here: the sr-only
                      clause above, and `data-prematch-source` on the cell,
                      which is what every guard and census actually reads.

                      D91 sanctions "small source marks", and this stays true —
                      what it does not sanction is the same word twice per
                      match in the column the names need. Measured at 390px
                      before this change: the prior track is `max-content`, so
                      it sized to `NN% SPORTSBOOKS` and the name track
                      (`minmax(0,1fr)`) gave up the difference — 8 of the 10
                      names on the served list were clipped (`Jessica …`,
                      `Emma Nava…`, `Aryna S…`). #4067 caused that half by
                      itself: it renamed the word from `books` (5 chars) to
                      `sportsbooks` (11), correctly under notice 33, and this
                      `max-content` column silently charged the names for it. */}
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
                {/* live/071: the visible score is drawn CHUNK BY CHUNK so the
                    phone's capped column can only break between sets — the
                    default break opportunities include the hyphen inside one,
                    and `7-6, 6-` / `7, 6-3, 6-4` is a different score. See
                    `scoreWrapChunks`. The sentence above is untouched: a screen
                    reader gets one plain string, not a pile of spans. */}
                <span aria-hidden="true">
                  {scoreWrapChunks(line.text).map((chunk, chunkIndex, all) => (
                    <React.Fragment key={chunk + chunkIndex}>
                      {chunkIndex > 0 ? " " : null}
                      <span className="whitespace-nowrap">
                        {chunk}
                        {chunkIndex < all.length - 1 ? "," : ""}
                      </span>
                    </React.Fragment>
                  ))}
                </span>
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
  espnEventIds,
  initialExpanded = false,
  pending = false,
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
   * `event_links.by_espn` from the hub payload — the server's id-anchored
   * `ESPN competition id -> events.id` map (#2693 step 2).
   *
   * The channel that reaches THIS list. A finished match has usually lost its
   * register matchup (`build_slate` retires one the moment its match starts),
   * so `eventIds` above cannot cover it and 118 of 235 rows rendered as dead
   * text. Optional and absent-tolerant for the same reason as `eventIds`: an
   * older cached payload degrades to the market channel alone.
   */
  espnEventIds?: Record<string, number> | null;
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
  /**
   * The finished list's half of the payload is still in flight (latency/135).
   *
   * `resultsEmptyReason(undefined)` says "Results are not loaded.", which is
   * true and reads as a fault. For the second and a half between the hub's two
   * requests it is not a fault, it is a wait, and those are different sentences
   * — the same distinction `bracket-pending` draws one tab over.
   */
  pending?: boolean;
}) {
  const [expanded, setExpanded] = React.useState(initialExpanded);
  const matches = sortedResults(resultsForDraw(results, draw));

  if (matches.length === 0) {
    const reason =
      pending && !results ? "Loading finished matches…" : resultsEmptyReason(results);
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
  const links = resultLinkCoverage(matches, eventIds, espnEventIds);

  /* ═══ notice 34 (Alex, 2026-09-08 4:00pm PT) / #4122: THE COUNTS SURVIVE, THE
     PARAGRAPHS DO NOT ═══

     `completion`, `prior` and `links` used to be printed at the foot of this
     section as three grey paragraphs — a prematch explainer carrying a coverage
     count ("Shown on 124 of 166") and a limitation ("42 are fixtures we could
     not tie to a market of ours"), a link count ("113 of 166 open a match
     page"), and a provenance line counting the matches we hold no market for.
     Alex, about this page: *"all the grey text is madness, and shouldn't be
     user-facing at all."* Two of the three examples the ruling gives were
     transcribed off those very sentences.

     So they are attributes now. A probe, a guard or a sentinel reads every one
     of those numbers exactly as before; a reader is not made to. That is the
     shape of the ruling — "the number, the small source mark, and at most one
     short caption" — so the statistics move to where machines look and leave
     the page to the tennis.

     The reader loses nothing that is a fact about the tennis: the score, the
     winner, the per-row grey prematch number and the D91 source mark beside it
     all stay. What went is the aggregate re-telling of what those per-row marks
     already say, plus our own join statistics.

     KEEP THESE POPULATED. If a later change stops calling `prematchCoverage` /
     `resultLinkCoverage` / `completionNote`, the attributes go silently
     undefined and the honesty guards lose the only thing they can still assert
     against the render.

     `lib/tournamentResults.ts` is deliberately untouched — the pure functions
     and their unit tests are unchanged, and that file belongs to ux/1138's
     #4067 right now. This is a render-side change only.

     ── #4278 ADDENDUM (ux/1151): `population` WAS THE FOURTH, AND IT WAS MISSED.
     `Includes 43 qualifying matches.` was still rendering under the FINISHED
     heading on production this morning, three sweeps after the ruling. It is
     the same shape as the three above — a coverage qualifier on a total — and
     it now takes the same treatment: `data-population-note`. Nothing else about
     it changes, and `resultsPopulationNote` stays exported and unit-tested for
     exactly the reason the KEEP THESE POPULATED paragraph gives. */
  return (
    <section
      data-testid="tournament-results"
      data-draw={draw}
      data-count={matches.length}
      data-with-prematch={prior.withPrior}
      data-prematch-total={prior.total}
      data-held-without-opening={prior.heldWithoutOpening}
      data-untied={prior.untied}
      data-linked={links.linked}
      data-link-total={links.total}
      data-completion={completion ?? undefined}
      data-population-note={population ?? undefined}
      data-unregistered-pairs={results?.unregistered_pairs ?? undefined}
    >
      <h2 className="mb-2 mt-6 text-xs font-bold uppercase tracking-[0.07em] text-text-muted">
        Finished
        <span className="ml-1.5 font-normal normal-case tracking-normal">
          · {DRAW_LABELS[draw] ?? draw} · {matches.length}
        </span>
      </h2>

      {/* WHAT THE COUNT COUNTS (#2450) is now `data-population-note` on the
          section above, not a grey line here — notice 34 / #4278. See the
          addendum in the block over the `return`. */}
      <div className="overflow-hidden rounded-2xl border border-surface-border bg-surface-card">
        {/* ONE grid for the whole list, so a column is a column across every
            row — see `RESULT_GRID`. The round headings are `col-span-3` bands
            inside it rather than siblings of it, because a heading outside the
            grid would reset the tracks below it and put the second round's
            score column somewhere else again. */}
        <ul className={RESULT_GRID}>
          {shown.map((result, index) => {
            /* #3163, found in a phone-width LOOK: the band was emitted once per
               ROW, so five consecutive round-of-32 matches each got their own
               `ROUND OF 32` header and the band grouped nothing. A group heading
               belongs to the RUN, so it is drawn only where the run starts.

               Compared against the previous SHOWN row, not the previous match,
               because the collapsed list is a slice: its first row starts a run
               whatever preceded it in the full array.

               Dropping the band leaves no gap — `ResultRow` already draws
               `border-t` on its own winner cell, so rows inside a run stay
               separated. That is why this is a deletion and not a swap. */
            const heading = roundHeading(result, roundCount);
            const startsRun =
              index === 0 || heading !== roundHeading(shown[index - 1], roundCount);

            return (
              <React.Fragment key={result.matchup_key}>
                {startsRun && (
                  <li
                    className="col-span-3 border-t border-surface-border bg-surface-elevated px-3.5 py-1 text-[10px] font-bold uppercase tracking-[0.05em] text-text-muted first:border-t-0"
                    data-testid="result-round"
                  >
                    {heading}
                  </li>
                )}
                <ResultRow
                  result={result}
                  href={resultEventHref(result, eventIds, espnEventIds)}
                />
              </React.Fragment>
            );
          })}
        </ul>
        {matches.length > COLLAPSED_LIST_COUNT && (
          <ShowMore
            expanded={expanded}
            total={matches.length}
            onToggle={() => setExpanded((value) => !value)}
          />
        )}
      </div>
    </section>
  );
}
