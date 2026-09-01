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
}

/** Below this, winning is a surprise worth marking (L2-131 Item 1). */
const UPSET_THRESHOLD = 0.4;

export default function SettledOutcomeHero({
  outcome,
  hasNumericScore,
  winnerPregameProb,
}: SettledOutcomeHeroProps) {
  const wasUnderdog =
    winnerPregameProb !== null && winnerPregameProb < UPSET_THRESHOLD;

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
            <span
              className={`text-[11px] ${
                wasUnderdog ? "text-amber-600 font-semibold" : "text-text-muted"
              }`}
            >
              {wasUnderdog ? "Upset · " : ""}
              were {Math.round(winnerPregameProb * 100)}% pregame
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
