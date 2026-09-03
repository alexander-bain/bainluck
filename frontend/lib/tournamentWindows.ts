/**
 * WHEN DID THIS TOURNAMENT START? (ux/1034, Alex's item A1)
 *
 * The contender chart's two date-anchored ranges — `DRAW` and `QUAL` — need two
 * days, and this is the only module allowed to decide what they are.
 *
 * Both come off the payload, and neither is a constant. `30 August` is a fact
 * about the 2026 US Open; written into a component it would be wrong for the
 * Australian Open in January, wrong for next year's US Open, and — worst —
 * wrong SILENTLY, because a chart drawn from the wrong start still draws.
 *
 * The two are read differently on purpose:
 *
 * - **The main draw is PUBLISHED.** `main_draw_starts_at` is the register's own
 *   value, the same one the empty-slate hint already prints as "the draw fills
 *   them in Sunday 30 August". One fact, one source, and the chart cannot
 *   disagree with the sentence beside it.
 *
 * - **Qualifying is OBSERVED.** Nothing in the payload names the day qualifying
 *   began, and inventing "five days before the main draw" would be a rule about
 *   one tournament wearing the shape of a fact. What the payload does carry is
 *   every finished qualifying match with the day it finished on, so the day
 *   qualifying began is the earliest of those — measured, and absent when the
 *   tournament has no qualifying rows to measure it from.
 *
 * The dates are taken as the LOCAL DAY of each timestamp — the leading ten
 * characters of the ISO string — not the UTC day. `main_draw_starts_at` is
 * `2026-08-30T11:00:00-04:00`, and the tournament's own answer to "what day did
 * play start" is the one printed on the ticket, not the one a UTC conversion
 * would give an evening session.
 */

import type { TournamentPayload } from "./tournament";
import type { TournamentResult, TournamentResults } from "./tournamentResults";
import type { WindowStarts } from "./contenderChart";

/** ESPN's own word for the rounds played before the draw proper. */
const QUALIFYING_ROUND_PREFIX = "qualifying";

const ISO_DAY = /^\d{4}-\d{2}-\d{2}/;

/** The local day an ISO timestamp names, or `null` if it is not one. */
export function isoDay(value: string | null | undefined): string | null {
  if (typeof value !== "string") return null;
  const match = ISO_DAY.exec(value.trim());
  return match ? match[0] : null;
}

/** Is this result one of the qualifying rounds? Either round field may say so. */
export function isQualifyingResult(result: TournamentResult): boolean {
  return [result.round, result.source_round].some(
    (round) =>
      typeof round === "string" &&
      round.trim().toLowerCase().startsWith(QUALIFYING_ROUND_PREFIX)
  );
}

/**
 * The first day a qualifying match finished, over every draw.
 *
 * Deliberately not scoped to the draw the reader is looking at. Qualifying runs
 * as one event across both draws in the same week, and scoping would make the
 * chip appear on the men's board and vanish on the women's on any day one tour
 * happened to finish nothing — a control that flickers with the schedule.
 */
export function qualifyingStart(
  results: TournamentResults | null | undefined
): string | null {
  let earliest: string | null = null;
  for (const match of results?.matches ?? []) {
    if (!isQualifyingResult(match)) continue;
    const day = isoDay(match.completed_at);
    if (day && (earliest === null || day < earliest)) earliest = day;
  }
  return earliest;
}

/**
 * The chart's two window starts for a payload.
 *
 * `QUAL` is dropped when it is not STRICTLY earlier than `DRAW`: two chips that
 * draw the same window are one chip and a puzzle. That happens whenever a
 * tournament plays no qualifying, and it would also catch a payload whose
 * qualifying rows were misdated into the main draw — which is the case where
 * offering the chip would quietly redraw the reader's window.
 */
export function tournamentWindowStarts(
  payload: TournamentPayload | null | undefined
): WindowStarts {
  const draw = isoDay(payload?.main_draw_starts_at);
  const qualifying = qualifyingStart(payload?.results);
  return {
    DRAW: draw,
    QUAL: qualifying && (draw === null || qualifying < draw) ? qualifying : null,
  };
}
