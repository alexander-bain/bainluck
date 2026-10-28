import { parseISO } from "date-fns";

// #10090 — one `chartData` transform in `OddsChart` parses the same row
// timestamp many times (every sort comparison, then the forward-fill and
// recorded-window passes). This reuses the milliseconds for an explicit-zone ISO
// string within ONE transform: the map is created per call and dies with it, so
// a source or commit change naturally starts empty.
//
// Every return is exactly `parseISO(timestamp).getTime()`. Only finite numbers
// are held — never a `Date`, never `NaN`. A string that is not an explicit-zone
// ISO timestamp, one that parses to `NaN`, or any new string once the map holds
// `CHART_TIMESTAMP_MS_MAX_ENTRIES` takes the plain parse every time: the cap
// stops growth, it does not evict, so the strings already held stay held.
const EXPLICIT_ZONE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})$/;

export const CHART_TIMESTAMP_MS_MAX_ENTRIES = 1024;

export function createChartTimestampMs(): (timestamp: string) => number {
  const held = new Map<string, number>();
  return (timestamp: string): number => {
    if (typeof timestamp !== "string" || !EXPLICIT_ZONE.test(timestamp)) {
      return parseISO(timestamp).getTime();
    }
    const known = held.get(timestamp);
    if (known !== undefined) return known;
    const ms = parseISO(timestamp).getTime();
    if (Number.isFinite(ms) && held.size < CHART_TIMESTAMP_MS_MAX_ENTRIES) held.set(timestamp, ms);
    return ms;
  };
}
