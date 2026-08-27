"use client";

import React from "react";

import ShowMore, { COLLAPSED_LIST_COUNT } from "./ShowMore";
import {
  DRAW_LABELS,
  drawIsPriced,
  formatPrematch,
  prematchCoverage,
  resultsEmptyReason,
  resultsForDraw,
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
 * ═══ ON PLAYER IMAGES (Alex's item 8) — DELIBERATELY ABSENT ═══
 *
 * "Enable ONLY if coverage is ~complete per draw — half-covered looks worse
 * than none." Censused 2026-08-26 against ESPN's ATP and WTA rankings, which
 * is where our contenders resolve: **22 of 36 men's contenders (61%) and 21 of
 * 44 women's (48%)** have a headshot. Ben Shelton, Jack Draper, Holger Rune,
 * Emma Raducanu, Emma Navarro and Jasmine Paolini are all missing. That is
 * exactly the half-covered case the gate was written to refuse, so there are
 * no images here and the report carries the numbers rather than the decision
 * being re-litigated in a later lane.
 */

function ResultRow({ result }: { result: TournamentResult }) {
  const winner = result.players.find((player) => player.is_winner);
  const loser = result.players.find((player) => !player.is_winner);
  if (!winner || !loser) return null;

  return (
    <li
      className="border-t border-surface-border px-3.5 py-2.5 first:border-t-0"
      data-testid="result-row"
      data-matchup={result.matchup_key}
      data-winner={result.winner_entity_key}
      data-has-score={result.score ? "true" : "false"}
    >
      <div className="flex items-baseline justify-between gap-3">
        <div className="min-w-0 flex-1">
          {[winner, loser].map((player) => {
            /* THE PRIOR (UX-P146, Alex on the UX-P145 artifact): "a result
               without the prior probability is half the story on a probability
               product." Rendered on the player's OWN line and right-aligned in
               its own column, so the two numbers stack and a reader can see at
               a glance which way round the market had it. */
            const prior = formatPrematch(player.prematch_probability);
            return (
              <div
                key={player.entity_key}
                className="flex min-w-0 items-baseline"
                data-testid="result-player"
                data-entity={player.entity_key}
                data-outcome={player.is_winner ? "won" : "lost"}
                data-prematch={player.prematch_probability ?? undefined}
              >
                <span
                  className={`truncate text-[13.5px] ${
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
                {prior && (
                  <span
                    className="ml-auto shrink-0 pl-3 text-[12px] tabular-nums text-text-secondary"
                    data-testid="result-prematch"
                  >
                    {/* Ruling 2 again: a number names its own question. The
                        column has no header — there is no room for one beside a
                        score — so the sentence travels with each number for a
                        screen reader, and the section's footnote carries it for
                        everyone else. */}
                    <span className="sr-only">
                      Before the match, the market gave {player.display_name}{" "}
                    </span>
                    {prior}
                  </span>
                )}
              </div>
            );
          })}
        </div>

        {/* THE SCORE, on the card and beside the outcome (UX-P137 ruling 2).
            Winner's games first, set by set, so the reader never reverses it.
            Absent for a retirement, where a partial score printed as a final
            one would be the same class of defect as a stale price printed as
            live. */}
        {result.score ? (
          <span
            className="shrink-0 text-[13px] font-semibold tabular-nums text-text-secondary"
            data-testid="result-score"
          >
            {result.score}
          </span>
        ) : (
          <span
            className="shrink-0 text-[11px] text-text-muted"
            data-testid="result-no-score"
            title="The source reported a winner but no completed set scores — usually a retirement."
          >
            no score
          </span>
        )}
      </div>
    </li>
  );
}

export default function TournamentResults({
  results,
  draw,
  initialExpanded = false,
}: {
  results: ResultsModel | null | undefined;
  draw: string;
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
  const scored = matches.filter((match) => match.score).length;
  /* Counted over THIS draw's rendered rows rather than read off the payload's
     `with_prematch`, which is the all-draws total. A footnote that says "12 of
     76" under a list of 24 is a footnote about a different list. */
  const prior = prematchCoverage(matches);

  return (
    <section data-testid="tournament-results" data-draw={draw} data-count={matches.length}>
      <h2 className="mb-2 mt-6 text-xs font-bold uppercase tracking-[0.07em] text-text-muted">
        Finished
        <span className="ml-1.5 font-normal normal-case tracking-normal">
          · {DRAW_LABELS[draw] ?? draw} · {matches.length}
        </span>
      </h2>
      <div className="overflow-hidden rounded-2xl border border-surface-border bg-surface-card">
        <ul>
          {shown.map((result) => (
            <React.Fragment key={result.matchup_key}>
              <li
                className="border-t border-surface-border bg-surface-elevated px-3.5 py-1 text-[10px] font-bold uppercase tracking-[0.05em] text-text-muted first:border-t-0"
                data-testid="result-round"
              >
                {roundHeading(result)}
              </li>
              <ResultRow result={result} />
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
              . The rest are matches nobody ran a market on, and we would rather leave
              the space empty than fill it with a number about a different question.
            </>
          )}
        </p>
      )}
      <p className="mt-2 text-[11px] leading-snug text-text-muted" data-testid="results-provenance">
        Scores from ESPN.{" "}
        {scored < matches.length &&
          `${matches.length - scored} finished without a completed set score (retirement or walkover). `}
        {(results?.unregistered_pairs ?? 0) > 0 &&
          `${results?.unregistered_pairs} other finished match${
            results?.unregistered_pairs === 1 ? "" : "es"
          } involve players we hold no market for.`}
      </p>
    </section>
  );
}
