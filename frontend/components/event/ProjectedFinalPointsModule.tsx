'use client';

/**
 * #10239 — the event-page mount for projected final points.
 *
 * The leagues `PROJECTED_FINAL_POINTS_LEAGUES` names (football and
 * basketball), before, during and after the game (#10461), on the page's own
 * sport key. It draws the decision the
 * page already took (`useProjectedFinalPointsMount`, every admission rule is
 * documented there) from the history the page already adopted. No fetch, no
 * polling, and no second decision: #10539 drops the Score Differential card on
 * exactly the decision this renders, so the two can never both be absent or
 * both be shown through drift. It renders nothing on a refusal, and the
 * page's win probability stays the headline.
 *
 * The final score is the page's own, the pair its hero prints, passed in
 * apart from the history. `score_history`'s last row is only the last score
 * recorded: on 14780549 with its 27–7 row missing, that row is 26–7 (before
 * the extra point), and a completion timestamp does not make it final.
 *
 * Its error boundary is the page's, whose fallback is the differential card
 * this replaced: a fault here hands the score back rather than taking it away.
 */

import { useMemo } from "react";
import ProjectedFinalPointsChart from "@/components/event/ProjectedFinalPointsChart";
import type { ProjectedFinalPointsMount } from "@/lib/projectedFinalPointsSeries";
import type { PeriodBoundary } from "@/lib/periodMarkers";

/** A final score the page would print, as two whole non-negative numbers. Anything else is refused. */
export type ProjectedFinalScore = { home: number; away: number };

const isScore = (v: unknown): v is number => typeof v === "number" && Number.isInteger(v) && v >= 0;

export function admittedFinalScore(
  pair: { home: number | null | undefined; away: number | null | undefined } | null | undefined,
): ProjectedFinalScore | null {
  if (!pair || !isScore(pair.home) || !isScore(pair.away)) return null;
  return { home: pair.home, away: pair.away };
}

export interface ProjectedFinalPointsModuleProps {
  /** The page's one mount decision (`useProjectedFinalPointsMount`). */
  decision: ProjectedFinalPointsMount;
  /** The final pair the page's hero prints for a finished game, or null when it shows none. */
  finalScore?: { home: number | null | undefined; away: number | null | undefined } | null;
  /** #10573 — the pair the hero prints as `Projected final` (`heroProjectedFinal`), or null when it prints none. */
  projectedFinal?: { home: number; away: number } | null;
  /** The page's evidenced period boundaries (`derivePeriodBoundaries`), the same list its other charts mark. */
  periodBoundaries?: PeriodBoundary[];
  homeTeam: string;
  awayTeam: string;
  homeColor?: string | null;
  awayColor?: string | null;
}

export default function ProjectedFinalPointsModule({
  decision,
  finalScore,
  projectedFinal = null,
  periodBoundaries,
  homeTeam,
  awayTeam,
  homeColor,
  awayColor,
}: ProjectedFinalPointsModuleProps) {
  const finalHome = finalScore?.home;
  const finalAway = finalScore?.away;
  const final = useMemo(() => admittedFinalScore({ home: finalHome, away: finalAway }), [finalHome, finalAway]);
  if (!decision.mount) return null;
  return (
    <ProjectedFinalPointsChart
      input={decision.input}
      homeTeam={homeTeam}
      awayTeam={awayTeam}
      homeColor={homeColor}
      awayColor={awayColor}
      finalScore={final}
      projectedFinal={projectedFinal}
      periodBoundaries={periodBoundaries}
    />
  );
}
