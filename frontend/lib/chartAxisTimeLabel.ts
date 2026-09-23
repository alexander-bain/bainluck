/**
 * #8135 — HOW A TIME AXIS NAMES ITS TICKS, AND WHY THE SPAN IS NOT ENOUGH.
 *
 * THE DEFECT. `/futures/59520336` ("First Partner Illustration Collection …
 * Price Over/Under $60.58 on September 30?") holds six observations, all of them
 * on the afternoon of **24 August**. Read on production at 390px on 23 September
 * the x-axis said `1:48 PM · 4:03 PM · 6:19 PM` — bare clock times, which a
 * reader places on the day they are reading. The card said "Last number 29 days
 * ago" four lines below its own axis.
 *
 * The rule that produced it branched on the SPAN of the data and nothing else:
 *
 *     span < 24h  ->  "1:48 PM"        // clock only
 *     span < 7d   ->  "Aug 24 1 PM"
 *     else        ->  "Aug 24"
 *
 * That first branch is right for a market whose last five hours are *now* and
 * wrong for one whose only five hours were four weeks ago, and the span cannot
 * tell those two apart — it is the same five hours in both. A clock time with no
 * date is only self-describing while the reader can assume "today or last
 * night"; past that it is a label that names no day.
 *
 * This is the web twin of **#2885**'s second defect, fixed natively in
 * `OddsChartView.xAxisPlan` (PR #2883) and never carried across.
 *
 * ── WHY THE TEST IS ON THE DOMAIN'S START, NOT ITS END ──
 *
 * The obvious form is "does the domain END within the last day". It is not
 * enough: a 23-hour span ending 20 hours ago passes that test while covering 43
 * hours of wall clock, so two ticks a day apart can print the SAME clock label —
 * which is #2885's defect verbatim, reintroduced by the fix for it. Requiring
 * the whole domain to lie inside the last 24 hours makes that unexpressible:
 * within a window that short, no two instants share a clock-minute label.
 *
 * ── WHAT THIS DELIBERATELY DOES NOT TOUCH ──
 *
 * The other two branches already carry a date, so they are never ambiguous about
 * the day and are returned byte-for-byte as they were. The only behaviour that
 * changes is the clock-only branch on a domain that is not recent, and it
 * changes by ADDING the day — no tick loses information.
 *
 * ── TIME ZONES ──
 *
 * `timeZone` is for GUARDS. The app deliberately passes nothing, so a reader sees
 * their own zone (the same contract `futuresDetailDisplay.instantDayLabel` holds,
 * and the chart has formatted local for as long as it has existed). A guard that
 * relies on the process zone is a guard that passes for the wrong reason, so
 * every assertion about exact text pins the zone here rather than around jest.
 */

const HOUR_MS = 60 * 60 * 1000;
const DAY_MS = 24 * HOUR_MS;
const WEEK_MS = 7 * DAY_MS;

/**
 * `clock`    — `1:48 PM`      · a short span the reader is standing in
 * `dayClock` — `Aug 24, 1:48 PM` · a short span that is over; the minutes still
 *              discriminate the ticks, so they stay
 * `dayHour`  — `Sep 3 5 PM`   · unchanged
 * `day`      — `Sep 3`        · unchanged
 */
export type AxisTimeFormat = "clock" | "dayClock" | "dayHour" | "day";

/** A clock time names no day beyond this much of one. */
export const CLOCK_ONLY_WITHIN_MS = DAY_MS;

/**
 * Which label shape this domain earns.
 *
 * A non-finite `now` (or domain) can only make `domainStartMs >= now - DAY_MS`
 * false, so the fallback is `dayClock` — the label that says MORE. Failing
 * toward the more explicit label is the safe direction for a rule about
 * ambiguity.
 */
export function axisTimeFormat(
  domainStartMs: number,
  domainEndMs: number,
  now: number = Date.now(),
): AxisTimeFormat {
  const span = domainEndMs - domainStartMs;
  if (span < DAY_MS) {
    return domainStartMs >= now - CLOCK_ONLY_WITHIN_MS ? "clock" : "dayClock";
  }
  if (span < WEEK_MS) return "dayHour";
  return "day";
}

/** Render one tick in the shape `axisTimeFormat` chose. */
export function formatAxisTime(
  ts: number,
  format: AxisTimeFormat,
  timeZone?: string,
): string {
  const d = new Date(ts);
  const zone = timeZone ? { timeZone } : {};
  const day = () =>
    d.toLocaleDateString("en-US", { month: "short", day: "numeric", ...zone });

  switch (format) {
    case "clock":
      return d.toLocaleTimeString("en-US", {
        hour: "numeric",
        minute: "2-digit",
        ...zone,
      });
    case "dayClock":
      return `${day()}, ${d.toLocaleTimeString("en-US", {
        hour: "numeric",
        minute: "2-digit",
        ...zone,
      })}`;
    case "dayHour":
      return `${day()} ${d.toLocaleTimeString("en-US", {
        hour: "numeric",
        ...zone,
      })}`;
    case "day":
      return day();
  }
}
