/**
 * Standard "As of" timestamp formatter (Ruling 198-B, Wording Sweep #12759, #13203):
 * - Same calendar day as `now`: `"As of 1:29 PM"`
 * - Older day in the same year: `"As of Nov 13"`
 * - Different calendar year: `"As of Nov 13, 2025"`
 *
 * Uses `Intl.DateTimeFormat` directly so prototype spies on `toLocaleDateString`
 * remain undisturbed, and returns `null` on empty or unparseable input.
 *
 * Callers rendered during SSR MUST render via `<AsOfStamp>` (client-only after
 * hydration) rather than calling `formatAsOfStamp` directly during SSR, so the
 * reader's browser time zone and calendar day — never the server's UTC clock —
 * determine both the time and the same-day test (#13203).
 */
function calendarParts(
  date: Date,
  timeZone?: string,
): { year: number; month: number; day: number } {
  if (!timeZone) {
    return {
      year: date.getFullYear(),
      month: date.getMonth() + 1,
      day: date.getDate(),
    };
  }
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    year: "numeric",
    month: "numeric",
    day: "numeric",
  }).formatToParts(date);
  let year = 0;
  let month = 0;
  let day = 0;
  for (const part of parts) {
    if (part.type === "year") year = Number(part.value);
    else if (part.type === "month") month = Number(part.value);
    else if (part.type === "day") day = Number(part.value);
  }
  return { year, month, day };
}

export function formatAsOfStamp(
  iso: string | null | undefined,
  now: Date = new Date(),
  timeZone?: string,
): string | null {
  if (!iso) return null;
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return null;

  const atParts = calendarParts(at, timeZone);
  const nowParts = calendarParts(now, timeZone);

  const sameYear = atParts.year === nowParts.year;
  const sameDay =
    sameYear && atParts.month === nowParts.month && atParts.day === nowParts.day;

  if (sameDay) {
    const timeFmt = new Intl.DateTimeFormat("en-US", {
      hour: "numeric",
      minute: "2-digit",
      ...(timeZone ? { timeZone } : {}),
    });
    return `As of ${timeFmt.format(at)}`;
  }

  if (sameYear) {
    const monthDayFmt = new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
      ...(timeZone ? { timeZone } : {}),
    });
    return `As of ${monthDayFmt.format(at)}`;
  }

  const monthDayYearFmt = new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    ...(timeZone ? { timeZone } : {}),
  });
  return `As of ${monthDayYearFmt.format(at)}`;
}
