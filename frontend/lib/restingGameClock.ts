import { trustedLiveClock } from "@/lib/gameTimeLabel";
import type { ActiveChartPoint } from "@/lib/types";

/** Numeric period → "Q3"; an already-spelled period ("1st Quarter", "Halftime") is kept. */
export function formatPeriod(period?: string | null): string {
  if (!period) return "";
  if (period.length > 2) return period;
  const num = parseInt(period, 10);
  if (isNaN(num)) return period;
  return `Q${num}`;
}

export interface RestingGameClock {
  /** The trusted period the readout prints ("" when none). */
  period: string;
  /** The trusted clock the readout prints ("" when none). */
  gameClock: string;
  /** The period was carried from an earlier row (the readout's `~` / "as of"). */
  periodCarried: boolean;
  /** The clock was carried from an earlier row (the readout's `~`). */
  clockCarried: boolean;
  /**
   * The clock is the current clock of the period beside it: it was observed no
   * earlier than the period was. `false` for a clock inherited from before the
   * period changed — the previous quarter's 0:05 under "3rd Quarter".
   */
  clockIsCurrent: boolean;
}

/**
 * #4889 — THE ONE SELECTOR for the game's current period and clock. The resting
 * readout under the chart (`GamePlayCard` with no finger on the chart) and the
 * live header badge both read this over the same `computeLastChartPoint` point,
 * so the page cannot print two clocks: before, the header ran its own carry over
 * `/history` while the readout read `computeLastChartPoint`. With no ESPN rows,
 * the header took win-prob `game_state` Q2 5:10 and the readout fell through to
 * the detail payload's 5:31.
 *
 * `formatPeriod` runs before the trust rules, as it always has on the card, so
 * the trust decision is taken over the string a reader sees.
 */
export function restingGameClock(
  point: Pick<
    ActiveChartPoint,
    "timestamp" | "period" | "clock" | "periodApprox" | "clockApprox" | "periodObservedAt" | "clockObservedAt"
  >,
  sportKey?: string | null,
): RestingGameClock {
  const trusted = trustedLiveClock(formatPeriod(point.period), point.clock, sportKey);
  const periodCarried = point.periodApprox === true && !!trusted.period;
  const clockCarried = point.clockApprox === true && !!trusted.gameClock;
  // A field read off the newest row was observed at the point's own timestamp; a
  // carried one at the row that supplied it; a carried one with no stamp (the
  // event row's own clock, #925) is undated and is never judged older.
  const observedMs = (carried: boolean, at: string | null | undefined): number | null => {
    const stamp = carried ? at : point.timestamp;
    if (!stamp) return null;
    const ms = Date.parse(stamp);
    return Number.isNaN(ms) ? null : ms;
  };
  const periodMs = trusted.period ? observedMs(point.periodApprox === true, point.periodObservedAt) : null;
  const clockMs = trusted.gameClock ? observedMs(point.clockApprox === true, point.clockObservedAt) : null;
  const clockUndated = point.clockApprox === true && !point.clockObservedAt;
  const clockIsCurrent =
    !!trusted.gameClock && (periodMs == null || clockUndated || (clockMs != null && clockMs >= periodMs));
  return { period: trusted.period, gameClock: trusted.gameClock, periodCarried, clockCarried, clockIsCurrent };
}
