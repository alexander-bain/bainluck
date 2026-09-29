/**
 * THE SETTLED HERO — WHO WON, AND BY WHAT (#2443).
 *
 * Lifted out of `app/events/[id]/page.tsx` unchanged in appearance, for two
 * reasons that are both about proof rather than tidiness:
 *
 *   1. The defect Alex found is a RENDER defect — "the page says FINAL and
 *      never shows the score" — and the only guard that can fail on it is one
 *      that renders the thing and reads the text. The hero was 45 lines inline
 *      in a 1,400-line client component behind three SWR calls, so the only
 *      way to reach it from a test was to render the route, and a route
 *      rendered under jest resolves no SWR and paints the loading spinner. A
 *      guard written against that proves nothing; this component can be
 *      rendered with a settled outcome and asserted on directly.
 *   2. "Settled means settled" is a standing ruling about every surface, not
 *      about this page. A named component is what a second surface can adopt.
 *
 * The one behaviour change is the middle line: an outcome whose winner was
 * named by something other than a pair of integers now prints its result in
 * its own units (`7-6, 7-6, 6-0`), because for those sports there is no number
 * under either competitor for it to duplicate. See `lib/eventOutcome.ts` for
 * the authority ladder that decides which of those two cases a given event is.
 */

import type { SettledOutcome } from "@/lib/eventOutcome";
import { renderedPercent } from "@/lib/renderedPercent";

export interface SettledOutcomeHeroProps {
  /** `null` when nothing authoritative named a winner — draw, or not graded yet. */
  outcome: SettledOutcome | null;
  /**
   * Whether the event carries a numeric final score at all. Only used to tell
   * an honest draw ("Final · Tied") from an unresolved one ("Final"), which is
   * the distinction the inline version already drew and this keeps.
   */
  hasNumericScore: boolean;
  /** The winner's pre-match probability, 0-1, or `null` when the side is unknown. */
  winnerPregameProb: number | null;
  /**
   * #8315 — the whole percent the game's CARD prints for the winner (the
   * server's pair rounding, UX-P114). When absent the probability is rounded
   * here, as before.
   */
  winnerPregamePercent?: number | null;
  /** The ladder rung the number came from, for measurement only. */
  winnerPregameSource?: string | null;
  /** "sportsbooks" when the rung is not a prediction market — the card's label. */
  winnerPregameLabel?: string | null;
  /** #9490 — the losing side's leg of the same pair. Decides "Upset"; never printed. */
  loserPregameProb?: number | null;
  /** The loser's whole percent from the same pair rounding as the winner's. */
  loserPregamePercent?: number | null;
}

/**
 * #9490 — an upset is the winner priced BELOW the side it beat, on the pair
 * this hero prints. It used to be a fixed cut (`winner < 0.40`) on the winner
 * alone, which called a three-way favourite an upset — Italy at 0.395 over
 * Turkey at 0.325, the draw taking the rest. Compared on the whole percents the
 * pair renders, so the label never contradicts the number beside it (0.395
 * printed "40%" under a "< 40%" rule), and a tie on screen is no upset. No
 * loser number, no comparison, no label.
 */
export function pregameUpset(args: {
  winnerProb: number | null;
  winnerPercent?: number | null;
  loserProb?: number | null;
  loserPercent?: number | null;
}): boolean {
  const winner = args.winnerPercent ?? renderedPercent(args.winnerProb);
  const loser = args.loserPercent ?? renderedPercent(args.loserProb);
  return winner !== null && loser !== null && winner < loser;
}

export default function SettledOutcomeHero({
  outcome,
  hasNumericScore,
  winnerPregameProb,
  winnerPregamePercent = null,
  winnerPregameSource = null,
  winnerPregameLabel = null,
  loserPregameProb = null,
  loserPregamePercent = null,
}: SettledOutcomeHeroProps) {
  const wasUnderdog = pregameUpset({
    winnerProb: winnerPregameProb,
    winnerPercent: winnerPregamePercent,
    loserProb: loserPregameProb,
    loserPercent: loserPregamePercent,
  });

  return (
    /* UX-P043 (#1649): the settled hero's stable hook. The browser pack read
       `event-hero-probability` as "the hero rendered", but that testid lives on
       the !isFinished branch only — by design, since "settled means settled:
       heroes show winners". In the evening the first game on /sports IS final,
       so the pack failed 4/4 on a hero working exactly as intended. */
    <div
      className="flex flex-col items-center gap-1.5"
      data-testid="event-hero-settled"
      data-winner={outcome?.winnerName ?? ""}
      /* #2443: the rung that named the winner, so a guard can assert that a
         tennis page is being answered by the container and not by a score it
         does not have. */
      data-outcome-authority={outcome?.authority ?? ""}
      data-result-kind={outcome?.resultKind ?? ""}
    >
      {outcome ? (
        <>
          <span className="text-base sm:text-lg font-semibold text-text-primary tracking-tight text-center">
            {outcome.winnerName}
          </span>
          <span className="text-[11px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded bg-accent-live/15 text-accent-live">
            Won
          </span>
          {outcome.resultLine && (
            /* The result, in the units the sport is scored in. `resultKind`
               separates a fact from an absence without the styling having to
               match on English: "no score" is the one branch that must not
               read like a scoreline, because it is our gap and not the
               match's. */
            <span
              className={`text-xs tabular-nums font-mono ${
                outcome.resultKind === "absent"
                  ? "text-text-muted italic"
                  : "text-text-secondary"
              }`}
              title={outcome.resultExplanation ?? undefined}
              data-testid="event-hero-result-line"
            >
              {outcome.resultLine}
            </span>
          )}
          {winnerPregameProb !== null && (
            /* #3619: no verb, deliberately. This line used to read "were N%
               pregame", which is right for a team ("the Yankees were 55%") and
               wrong for every one-on-one sport — tennis, golf, UFC, F1 — i.e.
               the whole of the surface during a Slam.

               The obvious repair is to agree the verb with the subject, but
               this component cannot know the subject's number and neither can
               the page. `isTournamentSportKey` — the only team-vs-individual
               signal the hero has, and the one that draws the player faces —
               is `/^tennis_(atp|wta)_/` and is documented in `eventOutcome.ts`
               as deliberately over-permissive because it gates a REQUEST.
               Reusing it here would fix tennis and leave golf, UFC and F1 still
               saying "were". Enumerating individual sports instead is what the
               issue explicitly warned against: the list goes stale the day a
               sport is added, and it fails silently, in copy nobody re-reads.

               Dropping the verb removes grammatical number from the sentence,
               so the line is correct for one player and eleven of them, now and
               for any sport added later. It also matches the terse register the
               rest of the surface already uses — "Opened 72/28", "Proj 18-21".
               No label is renamed: this is not the #2442/#3563 family. */
            <span
              className={`text-[11px] ${
                wasUnderdog ? "text-amber-600 font-semibold" : "text-text-muted"
              }`}
              data-testid="event-hero-pregame"
              data-prematch-source={winnerPregameSource ?? ""}
            >
              {wasUnderdog ? "Upset · " : ""}
              {winnerPregamePercent ?? renderedPercent(winnerPregameProb)}% pregame
            </span>
          )}
          {winnerPregameProb !== null && winnerPregameLabel && (
            /* #8315 — the card's label for a sportsbook median ("labelled when
               not a prediction market", Alex), so the two surfaces name the
               same rung the same way. Its OWN line, not appended: this column
               sits between the two team blocks, and at 390px a " · sportsbooks"
               suffix widened it enough to wrap both teams' records. */
            <span
              className="text-[10px] text-text-muted -mt-1"
              data-testid="event-hero-pregame-label"
            >
              {winnerPregameLabel}
            </span>
          )}
        </>
      ) : (
        <span className="text-[11px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded bg-text-muted/15 text-text-secondary">
          {hasNumericScore ? "Final · Tied" : "Final"}
        </span>
      )}
    </div>
  );
}
