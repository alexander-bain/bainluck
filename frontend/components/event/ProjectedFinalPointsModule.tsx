'use client';

/**
 * #10239 — the event-page mount for projected final points.
 *
 * NFL, before, during and after the game (#10461). It reads the event and the
 * history the page already adopted. No fetch, no polling. It renders nothing
 * unless every input below is present, and the page's win probability stays
 * the headline.
 *
 * - The page and the history must be in the same phase. The history carries
 *   its own served `status`; a finished page over a live, scheduled or
 *   status-less history, or a live page over a finished one, is refused, never
 *   reconciled by picking a side. A completion stamp on a history whose page
 *   is not finished is refused too: it never turns a live chart into "after".
 * - Rows count by their served provenance. Only a finished page over a
 *   finished history, served whole, may read rows that carry none.
 * - A scheduled page draws forecasts only: no score floor, no actual scores,
 *   no completion boundary, whatever markers or scores the history retains.
 * - The book is the existing deterministic picker's, never a hand-picked one.
 * - The score floor is the first recorded game state an instrument observed
 *   (`firstRecordedGameStateAt`). It is NOT a kickoff, so `kickoffAt` stays
 *   null. Without that marker the module is omitted, and the page's own final
 *   result is untouched.
 * - `asOf` is the recorded completion boundary, so the drawn view does not
 *   depend on the reader's clock.
 * - The final score is the page's own, the pair its hero prints, passed in
 *   apart from the history. `score_history`'s last row is only the last score
 *   recorded: on 14780549 with its 27–7 row missing, that row is 26–7 (before
 *   the extra point), and a completion timestamp does not make it final.
 */

import { useMemo } from "react";
import ProjectedFinalPointsChart from "@/components/event/ProjectedFinalPointsChart";
import SectionErrorBoundary from "@/components/SectionErrorBoundary";
import {
  buildProjectedFinalPointsSeries,
  FINISHED_HISTORY_STATUSES,
  firstRecordedGameStateAt,
  pickProjectionSportsbook,
  projectedFinalPointsInputFromHistory,
  PROJECTED_FINAL_POINTS_SPORTS,
  type ProjectedFinalPointsInput,
} from "@/lib/projectedFinalPointsSeries";
import type { EventHistoryResponse } from "@/lib/types";

/** Event statuses before and during a game. Anything else (postponed, cancelled, unknown) is not mounted. */
const SCHEDULED_STATUS = "scheduled";
const LIVE_STATUS = "live";

type MountPhase = "before" | "during" | "after";

/** The phase a status names, or null for a status this module does not mount. */
function phaseOf(status: string | null | undefined): MountPhase | null {
  if (FINISHED_HISTORY_STATUSES.has(status ?? "")) return "after";
  if (status === LIVE_STATUS) return "during";
  if (status === SCHEDULED_STATUS) return "before";
  return null;
}

export type ProjectedFinalPointsMountRefusal =
  | "sport_not_supported"
  | "status_not_supported"
  | "no_history"
  | "history_phase_mismatch"
  | "stale_completion"
  | "not_finished"
  | "no_named_book"
  | "no_recorded_game_state"
  | "no_valid_pair";

export type ProjectedFinalPointsMount =
  | { mount: true; input: ProjectedFinalPointsInput }
  | { mount: false; reason: ProjectedFinalPointsMountRefusal };

type MountHistory = Pick<EventHistoryResponse, "bookmaker_history" | "score_history" | "completed_at" | "period_markers" | "status">;

export function projectedFinalPointsMount(opts: {
  sportKey: string | null | undefined;
  eventStatus: string | null | undefined;
  history: MountHistory | null | undefined;
  /** The reader's now. Used before and during the game only; a finished game reads its completion boundary. */
  now: string;
}): ProjectedFinalPointsMount {
  const { sportKey, eventStatus, history } = opts;
  if (!PROJECTED_FINAL_POINTS_SPORTS.has(sportKey ?? "")) return { mount: false, reason: "sport_not_supported" };
  const phase = phaseOf(eventStatus);
  if (!phase) return { mount: false, reason: "status_not_supported" };
  if (!history) return { mount: false, reason: "no_history" };
  // The history must say it is in the page's phase. A missing status says nothing, so it refuses too.
  if (phaseOf(history.status) !== phase) return { mount: false, reason: "history_phase_mismatch" };
  const finishedPage = phase === "after";
  if (finishedPage && !history.completed_at) return { mount: false, reason: "not_finished" };
  // A completion stamp on a game the page and history both call unfinished is stale or early. It is
  // refused, never read as the end of the line, so a live chart cannot become "after".
  if (!finishedPage && history.completed_at) return { mount: false, reason: "stale_completion" };
  const asOf = finishedPage && history.completed_at ? history.completed_at : opts.now;
  // A finished game's history is served whole; a windowed one is never read the pre-contract way.
  const admission = { finishedPage, cutoffAt: null, asOf };
  const sourceKey = pickProjectionSportsbook(history, admission);
  if (!sourceKey) return { mount: false, reason: "no_named_book" };
  // Before the game there is no score floor at all, even when the history retains a first-quarter marker.
  const scoreObservationStartAt = phase === "before" ? null : firstRecordedGameStateAt(history.period_markers, sportKey);
  if (!scoreObservationStartAt && phase !== "before") {
    return { mount: false, reason: "no_recorded_game_state" };
  }
  const fromHistory = projectedFinalPointsInputFromHistory(history, {
    sportKey,
    sourceKey,
    kickoffAt: null,
    scoreObservationStartAt,
    ...admission,
  });
  // A scheduled page shows forecasts only: no retained score is an actual, and nothing is a final boundary.
  const input: ProjectedFinalPointsInput =
    phase === "before" ? { ...fromHistory, actuals: [], finalAt: null } : fromHistory;
  if (!buildProjectedFinalPointsSeries(input).supported) return { mount: false, reason: "no_valid_pair" };
  return { mount: true, input };
}

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
  sportKey: string | null | undefined;
  eventStatus: string | null | undefined;
  history: MountHistory | null | undefined;
  /** The final pair the page's hero prints for a finished game, or null when it shows none. */
  finalScore?: { home: number | null | undefined; away: number | null | undefined } | null;
  homeTeam: string;
  awayTeam: string;
  homeColor?: string | null;
  awayColor?: string | null;
}

export default function ProjectedFinalPointsModule({
  sportKey,
  eventStatus,
  history,
  finalScore,
  homeTeam,
  awayTeam,
  homeColor,
  awayColor,
}: ProjectedFinalPointsModuleProps) {
  // Keyed on the history fields it reads, so a live push that only moves the
  // win-probability line keeps the chart's memo and held cursor. The reader's
  // now is taken when those fields arrive.
  const bookmakerHistory = history?.bookmaker_history;
  const scoreHistory = history?.score_history;
  const completedAt = history?.completed_at;
  const periodMarkers = history?.period_markers;
  const historyStatus = history?.status;
  const hasHistory = !!history;
  const decision = useMemo(
    () =>
      projectedFinalPointsMount({
        sportKey,
        eventStatus,
        history: hasHistory
          ? {
              bookmaker_history: bookmakerHistory,
              score_history: scoreHistory,
              completed_at: completedAt,
              period_markers: periodMarkers,
              status: historyStatus,
            }
          : null,
        now: new Date().toISOString(),
      }),
    [sportKey, eventStatus, hasHistory, bookmakerHistory, scoreHistory, completedAt, periodMarkers, historyStatus],
  );
  const finalHome = finalScore?.home;
  const finalAway = finalScore?.away;
  const final = useMemo(() => admittedFinalScore({ home: finalHome, away: finalAway }), [finalHome, finalAway]);
  if (!decision.mount) return null;
  // Its own boundary, so a fault in this experiment can never take the page's score section with it.
  return (
    <SectionErrorBoundary label="The projected final points" resetKey={decision}>
      <ProjectedFinalPointsChart
        input={decision.input}
        homeTeam={homeTeam}
        awayTeam={awayTeam}
        homeColor={homeColor}
        awayColor={awayColor}
        finalScore={final}
      />
    </SectionErrorBoundary>
  );
}
