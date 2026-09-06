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
 * The category-label format for a rendered window, and the ONE place that
 * decides it (#3419).
 *
 * The XAxis is categorical on this label, so Recharts resolves a tick — and a
 * ReferenceLine's `x` — to the FIRST category string that equals it. "h:mm a"
 * repeats every 24 hours, so on any window at or beyond a day the label stops
 * identifying a minute and the axis silently folds later days onto earlier
 * ones. Measured on /events/15300276 ("Since Start", 45h05m): 2,703 minute
 * categories collapse to 1,440 distinct, and the eight ticks resolve to
 * [1439, 359, 719, 1079, 1439, 359, 719, 1079] — day two printed exactly on
 * top of day one. In "All" (29h07m) the END label resolved to category 307 of
 * 1,748, which is how a settled match drew its two surviving labels backwards
 * in the left quarter of the plot.
 *
 * Widening the label costs axis width, so it is spent only where it buys
 * uniqueness: a weekday inside a week (a game chart), a calendar date beyond
 * one (a pregame odds-drift window, which is deliberately left uncapped).
 *
 * Callers must format ticks, categories and marker keys with the SAME string
 * or nothing matches at all — that is why this returns the format rather than
 * each site choosing its own.
 */
export const CATEGORY_LABEL_FORMAT = "h:mm a";
export const CATEGORY_LABEL_FORMAT_DAY = "EEE h:mm a";
export const CATEGORY_LABEL_FORMAT_DATE = "MMM d h:mm a";

const DAY_MS = 24 * 60 * 60 * 1000;

export function categoryLabelFormat(startMs: number, endMs: number): string {
  const span = Math.abs(endMs - startMs);
  // A span of exactly one day already collides at its two endpoints, so the
  // boundary is inclusive. "EEE" repeats every 7 days, likewise.
  if (span >= 7 * DAY_MS) return CATEGORY_LABEL_FORMAT_DATE;
  if (span >= DAY_MS) return CATEGORY_LABEL_FORMAT_DAY;
  return CATEGORY_LABEL_FORMAT;
}

/**
 * Round an ISO timestamp to the start of its minute and return the ISO string.
 * Both charts bucket by minute so each category label is unique — required for
 * ReferenceLine period markers to land on a real XAxis value.
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
 *
 * `labelFormat` must be the format the axis ticks were built with — see
 * `categoryLabelFormat`. It defaults to the 12-hour clock, which is correct
 * for any window under a day.
 */
export function makeEnsurePoint<T extends MinuteKeyed>(
  dataMap: Map<string, T>,
  seedColumns: () => Partial<T>,
  labelFormat: string = CATEGORY_LABEL_FORMAT,
): (timestamp: string) => T {
  return (timestamp: string): T => {
    const minuteKey = toMinuteKey(timestamp);
    let point = dataMap.get(minuteKey);
    if (!point) {
      point = {
        timestamp: minuteKey,
        time: format(parseISO(minuteKey), labelFormat),
        ...seedColumns(),
      } as T;
      dataMap.set(minuteKey, point);
    }
    return point;
  };
}

/**
 * Seed every missing minute in `[first, last]` by calling `ensurePoint`, giving
 * the categorical XAxis equal pixel width per minute so time reads linearly and
 * both charts share an identical category set. No-op when the range is empty or
 * inverted. Floors both endpoints to the minute (mutates the passed Dates).
 *
 * `first` is INCLUSIVE (#3419). It used to be excluded, which was invisible
 * while these endpoints came from the data itself — the first minute was a real
 * point already in the map. Once the parent began passing a shared DOMAIN, the
 * start became a boundary that need not contain a datum, while
 * `computeSharedChartDomain` still always emits a tick at exactly that instant.
 * With no category to land on, Recharts drops the label and the axis loses its
 * leading tick. Measured on /events/15300276 "Since Start": the domain opens at
 * 00:00Z, the first Kalshi point is 15:56Z, and the "12:00 AM" tick resolved to
 * index -1. `ensurePoint` is idempotent, so seeding a `first` that does exist
 * costs nothing.
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
  while (cursor <= last) {
    ensurePoint(cursor.toISOString());
    cursor.setMinutes(cursor.getMinutes() + 1);
  }
}
