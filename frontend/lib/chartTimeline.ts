// Shared time-axis skeleton for the two event-page game charts — OddsChart
// (win-probability path) and ScoreDifferentialChart (spread path). Both bucket
// their source series by minute, seed every minute so the categorical XAxis is
// linear in time, and fill the gaps between the shared domain endpoints so the
// two charts line up pixel-for-pixel (L2-151 dedup of drifting near-copies).
//
// Pure logic only — no React, no recharts. Kept deliberately small: only the
// genuinely-identical primitives live here (minute bucketing, point seeding,
// gap fill). Each chart still owns its own column shapes and domain derivation.

import { format, parseISO } from "date-fns";

/** Base shape every per-minute chart datum shares. */
export interface MinuteKeyed {
  timestamp: string;
  time: string;
}

/**
 * Round an ISO timestamp to the start of its minute and return the ISO string.
 * Both charts bucket by minute so each "h:mm a" label is a unique category —
 * required for ReferenceLine period markers to land on a real XAxis value.
 */
export function toMinuteKey(timestamp: string): string {
  const d = parseISO(timestamp);
  // Zero out seconds and milliseconds.
  d.setSeconds(0, 0);
  return d.toISOString();
}

/**
 * Build the `ensurePoint` helper shared by both charts: it buckets a timestamp
 * to its minute in `dataMap`, creating a freshly-seeded point on first touch
 * (with the chart-specific null columns from `seedColumns`) and returning the
 * existing/created point either way.
 */
export function makeEnsurePoint<T extends MinuteKeyed>(
  dataMap: Map<string, T>,
  seedColumns: () => Partial<T>,
): (timestamp: string) => T {
  return (timestamp: string): T => {
    const minuteKey = toMinuteKey(timestamp);
    let point = dataMap.get(minuteKey);
    if (!point) {
      point = {
        timestamp: minuteKey,
        time: format(parseISO(minuteKey), "h:mm a"),
        ...seedColumns(),
      } as T;
      dataMap.set(minuteKey, point);
    }
    return point;
  };
}

/**
 * Seed every missing minute in `(first, last]` by calling `ensurePoint`, giving
 * the categorical XAxis equal pixel width per minute so time reads linearly and
 * both charts share an identical category set. No-op when the range is empty or
 * inverted. Floors both endpoints to the minute (mutates the passed Dates).
 */
export function fillMinuteGaps(
  first: Date,
  last: Date,
  ensurePoint: (timestamp: string) => unknown,
): void {
  if (!(first < last)) return;
  first.setSeconds(0, 0);
  last.setSeconds(0, 0);
  const cursor = new Date(first.getTime());
  cursor.setMinutes(cursor.getMinutes() + 1);
  while (cursor <= last) {
    ensurePoint(cursor.toISOString());
    cursor.setMinutes(cursor.getMinutes() + 1);
  }
}
