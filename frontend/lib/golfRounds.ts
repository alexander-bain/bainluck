// L2-135 — pure helper: golf tournament round boundaries as chart time markers.
// A 72-hole stroke-play event runs one round per day (R1..R4, +R5 for a Monday
// finish), so a UTC-midnight day step from the tournament start labels each round.
// Ported from EvolutionView.tournamentDayBoundaries so the concept-page charts
// (RaceToTitleChart / SettledPathChart) get the same "sense of time" the legacy
// golf page already had. Times are epoch ms; the chart clips them to its window.

export interface TimeMarker {
  time: number;
  label: string;
}

const DAY_MS = 86_400_000;

/**
 * Round-boundary markers (R1..R5) from a tournament's start date. Uses UTC
 * midnight to align with the UTC snapshot timestamps the chart plots. Returns []
 * when no valid start date is given (honest empty — never invent boundaries).
 *
 * @param startDate ISO start date (tournament round 1).
 * @param endDate   ISO end date, optional — caps the last marker at end + 1 day.
 * @param now       Epoch ms "now" cap (defaults to Date.now()); markers never run
 *                  past the present, so a live event only shows rounds reached.
 */
export function golfRoundMarkers(
  startDate: string | null | undefined,
  endDate?: string | null,
  now: number = Date.now(),
): TimeMarker[] {
  if (!startDate) return [];
  const start = new Date(startDate);
  if (Number.isNaN(start.getTime())) return [];
  start.setUTCHours(0, 0, 0, 0);

  let endMs = now;
  if (endDate) {
    const end = new Date(endDate);
    if (!Number.isNaN(end.getTime())) {
      endMs = Math.min(end.getTime() + DAY_MS, now);
    }
  }

  const markers: TimeMarker[] = [];
  let t = start.getTime();
  let round = 1;
  while (t <= endMs && round <= 5) {
    markers.push({ time: t, label: `R${round}` });
    t += DAY_MS;
    round += 1;
  }
  return markers;
}
