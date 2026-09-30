/**
 * #6158 — WHERE "SINCE START" OPENS ON A GAME THAT STARTED LATE.
 *
 * Both event charts cut "Since Start" at `commence_time`, the SCHEDULED start.
 * On a game that began late, that draws the pre-game stretch as game time: on
 * `/events/15321836` (White Sox @ Astros, 2026-09-30) the axis opened at 2:00 PM
 * and the first Top 1st observation is 21:13:06Z (2:13 PM), so the first
 * fifth of a one-hour "Since Start" window was a flat pre-game line. #6158's
 * specimens run to 47 minutes late (MLB 15316297), where it was 60% of the
 * window.
 *
 * The evidence of play is already on the page: the opening period boundary
 * (`T1`, `Q1`, `P1`, `1H`, `R1`) the chart draws at the moment it was first
 * OBSERVED (#7901). This returns where to cut instead of `commence_time`:
 *
 *   - never EARLIER than the scheduled start (this only ever narrows the
 *     window, and only when the evidence says play began later);
 *   - never past a `notBefore` bound — the last observation that still showed
 *     an earlier state, so everything cut is time we know was pre-game;
 *   - otherwise a short lead-in before the first observation, so the line
 *     enters the window with its pre-play value and the opening marker is not
 *     flush against the axis.
 *
 * It declines (returns `null` ⇒ keep `commence_time`) when the earliest
 * boundary is not an opening period (we started watching mid-game, e.g. first
 * saw `B1` or `T3`), when it is an estimate (`commence_time` arithmetic, not an
 * observation), or when it sits implausibly far after the scheduled start.
 * Alex, 2026-09-14: scheduled kickoff is not automatically the actual start,
 * and the chart may not crop to a boundary nobody observed.
 */
import { isEstimatedBoundary, type PeriodBoundary } from "@/lib/periodMarkers";

/** Normalized labels (`normalizePeriodLabel`) that name a game's first period. */
export const OPENING_PERIOD_LABEL = /^(?:Q1|P1|T1|R1|1H)$/;

/** Lead-in kept before the first observation of play (about one live poll). */
export const OBSERVED_START_LEAD_MS = 2 * 60_000;

/**
 * An opening boundary this far after the scheduled start is not read as a late
 * start: a rain delay of hours is a different story, and a boundary a day out
 * belongs to a rescheduled session. Past it, keep today's cut.
 */
export const OBSERVED_START_MAX_DELAY_MS = 3 * 60 * 60_000;

export function observedPlayStartMs(
  commenceTime: string | null | undefined,
  boundaries: PeriodBoundary[] | null | undefined,
): number | null {
  if (!commenceTime || !boundaries || boundaries.length === 0) return null;
  const scheduledMs = new Date(commenceTime).getTime();
  if (isNaN(scheduledMs)) return null;

  let first: PeriodBoundary | null = null;
  let firstMs = Infinity;
  for (const b of boundaries) {
    const t = new Date(b.timestamp).getTime();
    if (!isNaN(t) && t < firstMs) {
      first = b;
      firstMs = t;
    }
  }
  if (!first || !OPENING_PERIOD_LABEL.test(first.label)) return null;
  if (isEstimatedBoundary(first)) return null;
  if (firstMs - scheduledMs > OBSERVED_START_MAX_DELAY_MS) return null;

  let cutMs = firstMs - OBSERVED_START_LEAD_MS;
  const notBeforeMs = first.notBefore ? new Date(first.notBefore).getTime() : NaN;
  if (!isNaN(notBeforeMs) && notBeforeMs < cutMs) cutMs = notBeforeMs;
  return cutMs > scheduledMs ? cutMs : null;
}
