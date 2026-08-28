"use client";

import React from "react";

import PlayerAvatar from "./PlayerAvatar";
import { heroOrder, matchSubheading } from "@/lib/matchDetail";
import { renderedDuelPercents } from "@/lib/renderedPercent";
import { formatMove, moveDirection, slateRowFreshnessLabel, type SlateMatch } from "@/lib/slate";
import { resultScoreLine, type TournamentResult } from "@/lib/tournamentResults";

/**
 * THE MATCH-WINNER MARKET, at the top of its own page (UX-P149).
 *
 * Lane1's first reason for routing props here rather than into a feed was that
 * "Total Sets O/U 3.5 at 65% is meaningless without Wu 48.5% / Walton 51.5%
 * above it". This is that above-it. Every question further down the page is
 * legible only in relation to this pair, so it is the largest thing on the
 * screen and it is the same row the match list prints — same normalization,
 * same freshness verdict, same refusal to show an incoherent split.
 *
 * THE PAIR IS ROUNDED ONCE (UX-P147, Alex's item 4). Two probabilities rounded
 * independently print 74% and 27%; `renderedDuelPercents` rounds the favourite
 * and derives the other.
 *
 * ON A DECIDED MATCH THE WINNER LEADS, whatever the market thought. `heroOrder`
 * sorts by the result when there is one — a finished match whose loser is
 * listed first because they were favourite is a page arguing with its own
 * headline.
 */

/** The column header. Every number on these surfaces names its own question. */
export const HERO_COLUMN_LABEL = "To win this match";

function Bar({ percents }: { percents: Array<number | null> }) {
  const [first, second] = percents;
  if (first === null || second === null) return null;
  return (
    <div
      className="mt-3 flex h-1.5 overflow-hidden rounded-full bg-surface-border"
      data-testid="hero-bar"
      aria-hidden="true"
    >
      <div className="bg-text-primary" style={{ width: `${first}%` }} />
      <div className="bg-surface-border" style={{ width: `${second}%` }} />
    </div>
  );
}

export default function MatchHero({
  match,
  result,
  decided,
  now,
}: {
  match: SlateMatch;
  result: TournamentResult | null;
  decided: boolean;
  /** Injected so the capture rig and the guard suite do not branch on the clock. */
  now?: Date;
}) {
  const ordered = heroOrder(match, result) ?? match.sides;
  /**
   * A DECIDED MATCH'S HERO IS THE OPENING PAIR, NOT THE SETTLED ONE.
   *
   * The settled market reads 100% for the winner and 0% for the loser: a
   * perfectly confident number that is really just the result read back, which
   * is the exact trap `_prematch_by_pair` refuses for the finished list. Beside
   * a `Won` chip and a scoreline it is worse than useless — it is the page
   * telling the reader something they can already see, in the slot where the
   * one thing worth knowing goes. *Rodionov beat Fearnley* is a scoreline;
   * *Rodionov beat Fearnley, and the market had him at 34%* is the product.
   *
   * `build_match_row` has already normalized the opening pair on its own sum,
   * so this is a field read and not a second opinion. When it could not — an
   * incoherent opening pair — both sides are `null` and the hero prints no
   * number rather than falling back to the settled one.
   */
  const shown = ordered.map((side) =>
    decided ? side.opening_probability : side.probability
  );
  const percents =
    match.coherent || decided
      ? renderedDuelPercents(shown[0], shown[1])
      : [null, null];
  const freshness = slateRowFreshnessLabel(match);
  // The one place a score is worded, shared with the hub's finished list — so
  // a walkover says walkover and a retirement is marked `ret.` here too
  // (UX-P147, Alex's item 5) rather than this page re-deriving either.
  const score = result ? resultScoreLine(result) : null;

  return (
    <section
      className="rounded-2xl border border-surface-border bg-surface-card px-4 py-4 lg:px-6 lg:py-5"
      data-testid="match-hero"
      data-decided={decided ? "true" : "false"}
      data-coherent={match.coherent ? "true" : "false"}
      data-price-state={match.price_state}
    >
      <div
        className="flex flex-wrap items-baseline gap-x-2 text-[10.5px] uppercase tracking-[0.06em] text-text-muted"
        data-testid="match-hero-meta"
      >
        <span>{matchSubheading(match, now)}</span>
        {freshness !== null && !decided && (
          <span className="normal-case tracking-normal text-accent-warning" data-testid="match-hero-age">
            {freshness}
          </span>
        )}
      </div>

      <div className="mt-1 flex items-baseline justify-between gap-3 text-[9.5px] font-bold uppercase tracking-[0.06em] text-text-muted">
        <span>Match</span>
        {/* On a decided match the column is not a forecast any more, and
            saying "to win this match" over a settled result would be reading
            the tense wrong. */}
        <span data-testid="match-hero-column">
          {decided ? "Before the match" : HERO_COLUMN_LABEL}
        </span>
      </div>

      <ol className="mt-1.5">
        {ordered.map((side, index) => {
          const percent = percents[index];
          const won = result ? result.winner_entity_key === side.entity_key : false;
          const move = decided ? "" : formatMove(side.move);
          const direction = moveDirection(side.move);
          return (
            <li
              key={side.entity_key}
              className={`flex items-center justify-between gap-3 py-1.5 ${
                decided && !won ? "text-text-muted" : ""
              }`}
              data-testid="match-hero-side"
              data-entity={side.entity_key}
              data-won={won ? "true" : "false"}
            >
              <span className="flex min-w-0 items-center">
                <PlayerAvatar
                  name={side.display_name}
                  image={side.image}
                  size={34}
                  dim={decided && !won}
                />
                <span
                  className={`ml-2.5 min-w-0 truncate text-[18px] leading-tight lg:text-[20px] ${
                    won || (!decided && percent !== null && percent >= 50)
                      ? "font-bold text-text-primary"
                      : "font-medium text-text-secondary"
                  }`}
                >
                  {side.display_name}
                </span>
                {side.seed !== null && (
                  <span className="ml-1.5 shrink-0 text-xs text-text-muted">[{side.seed}]</span>
                )}
                {won && (
                  <span
                    className="ml-2 shrink-0 rounded bg-accent-live/15 px-1.5 py-px text-[10px] font-bold uppercase tracking-[0.04em] text-accent-live"
                    data-testid="match-hero-won"
                  >
                    Won
                  </span>
                )}
              </span>

              <span className="flex shrink-0 items-baseline gap-2">
                {move !== "" && (
                  <span
                    className={`text-[12px] tabular-nums ${
                      !match.probability_is_live
                        ? "text-text-muted"
                        : direction === "up"
                          ? "text-accent-live"
                          : "text-accent-danger"
                    }`}
                    data-testid="match-hero-move"
                  >
                    {move}
                  </span>
                )}
                <span
                  className={`text-[24px] font-bold tabular-nums leading-none tracking-tight lg:text-[28px] ${
                    match.probability_is_live && !decided
                      ? "text-text-primary"
                      : "text-text-secondary"
                  }`}
                  data-testid="match-hero-probability"
                >
                  {percent === null ? "—" : `${percent}%`}
                </span>
              </span>
            </li>
          );
        })}
      </ol>

      <Bar percents={percents} />

      {/* UNPRICED IS NOT INCOHERENT (UX-P142). Two different absences, two
          different sentences, because only one of them is our problem. */}
      {!match.coherent && !decided && (
        <p className="mt-2 text-[12px] text-text-secondary" data-testid="match-hero-no-split">
          {match.priced === false
            ? "No market has put a probability on this match yet."
            : "The two sides of this market do not add up yet, so we are not showing a split."}
        </p>
      )}

      {/* No opening pair to fall back on. Said once, plainly, rather than two
          em-dashes with no explanation under them. */}
      {decided && percents[0] === null && (
        <p className="mt-2 text-[12px] text-text-secondary" data-testid="match-hero-no-prior">
          We hold no number from before this match.
        </p>
      )}

      {result && score && (
        <div
          className="mt-3 border-t border-surface-border pt-2.5 text-[13px]"
          data-testid="match-hero-result"
          data-completion={result.completion ?? undefined}
          data-score-kind={score.kind}
        >
          <span className="sr-only">{score.explanation} </span>
          <span
            aria-hidden="true"
            className={`font-semibold tabular-nums ${
              score.kind === "absent" ? "text-text-muted" : "text-text-primary"
            }`}
            title={score.explanation}
          >
            {score.text}
          </span>
        </div>
      )}
    </section>
  );
}
