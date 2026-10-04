'use client';

/**
 * #10239 — the event-page mount for projected final points.
 *
 * First mount, FINISHED NFL ONLY (root admission 2026-10-04). It reads the
 * event and the history the page already adopted. No fetch, no polling. It
 * renders nothing unless every input below is present, and the page's win
 * probability stays the headline.
 *
 * - Finished only: a finished game's history is served whole (route cutoff
 *   None), so no row is a cutoff re-stamp and `cutoffAt` is null. A live or
 *   pregame game would need the unresolved client/server cutoff heuristic,
 *   so it is not mounted here.
 * - The book is the existing deterministic picker's, never a hand-picked one.
 * - The score floor is the first recorded game state an instrument observed
 *   (`firstRecordedGameStateAt`). It is NOT a kickoff, so `kickoffAt` stays
 *   null. Without that marker the module is omitted, and the page's own final
 *   result is untouched.
 * - `asOf` is the recorded completion boundary, so the drawn view does not
 *   depend on the reader's clock.
 */

import { useMemo } from "react";
import ProjectedFinalPointsChart from "@/components/event/ProjectedFinalPointsChart";
import SectionErrorBoundary from "@/components/SectionErrorBoundary";
import {
  buildProjectedFinalPointsSeries,
  firstRecordedGameStateAt,
  pickProjectionSportsbook,
  projectedFinalPointsInputFromHistory,
  PROJECTED_FINAL_POINTS_SPORTS,
  type ProjectedFinalPointsInput,
} from "@/lib/projectedFinalPointsSeries";
import type { EventHistoryResponse } from "@/lib/types";

/** Event statuses that mean the game is over. */
const FINISHED_STATUSES: ReadonlySet<string> = new Set(["completed", "closed"]);

export type ProjectedFinalPointsMountRefusal =
  | "sport_not_supported"
  | "not_finished"
  | "no_named_book"
  | "no_recorded_game_state"
  | "no_valid_pair";

export type ProjectedFinalPointsMount =
  | { mount: true; input: ProjectedFinalPointsInput }
  | { mount: false; reason: ProjectedFinalPointsMountRefusal };

type MountHistory = Pick<EventHistoryResponse, "bookmaker_history" | "score_history" | "completed_at" | "period_markers">;

export function projectedFinalPointsMount(opts: {
  sportKey: string | null | undefined;
  eventStatus: string | null | undefined;
  history: MountHistory | null | undefined;
}): ProjectedFinalPointsMount {
  const { sportKey, eventStatus, history } = opts;
  if (!PROJECTED_FINAL_POINTS_SPORTS.has(sportKey ?? "")) return { mount: false, reason: "sport_not_supported" };
  if (!history || !FINISHED_STATUSES.has(eventStatus ?? "") || !history.completed_at) {
    return { mount: false, reason: "not_finished" };
  }
  const sourceKey = pickProjectionSportsbook(history);
  if (!sourceKey) return { mount: false, reason: "no_named_book" };
  const scoreObservationStartAt = firstRecordedGameStateAt(history.period_markers, sportKey);
  if (!scoreObservationStartAt) return { mount: false, reason: "no_recorded_game_state" };
  const input = projectedFinalPointsInputFromHistory(history, {
    sportKey,
    sourceKey,
    kickoffAt: null,
    scoreObservationStartAt,
    asOf: history.completed_at,
    cutoffAt: null,
  });
  if (!buildProjectedFinalPointsSeries(input).supported) return { mount: false, reason: "no_valid_pair" };
  return { mount: true, input };
}

export interface ProjectedFinalPointsModuleProps {
  sportKey: string | null | undefined;
  eventStatus: string | null | undefined;
  history: MountHistory | null | undefined;
  homeTeam: string;
  awayTeam: string;
  homeColor?: string | null;
  awayColor?: string | null;
}

export default function ProjectedFinalPointsModule({
  sportKey,
  eventStatus,
  history,
  homeTeam,
  awayTeam,
  homeColor,
  awayColor,
}: ProjectedFinalPointsModuleProps) {
  // Keyed on the adopted history, so the chart's own memo and held cursor survive unrelated re-renders.
  const decision = useMemo(
    () => projectedFinalPointsMount({ sportKey, eventStatus, history }),
    [sportKey, eventStatus, history],
  );
  if (!decision.mount) return null;
  // Its own boundary, so a fault in this experiment can never take the page's score section with it.
  return (
    <SectionErrorBoundary label="The projected final points" resetKey={history}>
      <ProjectedFinalPointsChart
        input={decision.input}
        homeTeam={homeTeam}
        awayTeam={awayTeam}
        homeColor={homeColor}
        awayColor={awayColor}
      />
    </SectionErrorBoundary>
  );
}
