/**
 * THE TRUTH LABELS ON /evals (#12102, step S1).
 *
 * Every figure on the page says which of three things it is:
 *
 *   LIVE                 fetched from the production API when the page opens,
 *                        stamped with the payload's own time, never the visit's
 *   LAST RUN · NOV 5     read from a committed record, with the run's date and
 *                        its age; the age turns amber after `AGE_AMBER_DAYS`
 *   PLANNED              no figure at all — it names what it is waiting on
 *
 * plus LAST REVIEWED · NOV 5 for the hand-kept gaps list, which is a list we go
 * through rather than a run that produced numbers.
 *
 * The page renders a record's verdict and never recomputes one, so this module
 * holds labels and dates only. No figure is formatted here.
 *
 * ═══ THE DATE TRAP ═══
 *
 * `new Date("2026-11-05")` is midnight UTC, which is 4 PM on Nov 4 in
 * California. A run dated Nov 5 would print NOV 4 on every Pacific screen. So a
 * bare calendar date is read as a Pacific calendar date and never passed
 * through `Date`; only a full timestamp is converted, and it is converted in
 * `America/Los_Angeles` explicitly, because jest runs in UTC (#2462) and a
 * reader's browser runs wherever the reader is.
 */

import { CHIP_COPY } from "@/lib/evals/copy";

export const PACIFIC_TIME_ZONE = "America/Los_Angeles";

/**
 * After this many days, a dated record's age turns amber. Nothing is hidden.
 * The legend states it in words; `truth.test.ts` keeps the two in step.
 */
export const AGE_AMBER_DAYS = 14;

export interface SourceLink {
  /** What the reader clicks, in our own words. */
  label: string;
  href: string;
}

/** An issue or pull request on the repo, printed as "#12095". */
export interface RepoRef {
  kind: "issue" | "pull";
  number: number;
  href: string;
}

const REPO = "https://github.com/alexander-bain/bainluck";

export const issueRef = (number: number): RepoRef => ({
  kind: "issue",
  number,
  href: `${REPO}/issues/${number}`,
});

export const pullRef = (number: number): RepoRef => ({
  kind: "pull",
  number,
  href: `${REPO}/pull/${number}`,
});

/** A figure that exists: fetched now, or read from a committed record. */
export type MeasuredTruth =
  | { kind: "live"; asOf: string; source: SourceLink }
  | { kind: "last_run"; asOf: string; source: SourceLink };

export type Truth =
  | MeasuredTruth
  | { kind: "reviewed"; asOf: string; source?: SourceLink }
  | { kind: "planned"; waitingOn: string; ref?: RepoRef };

export type TruthKind = Truth["kind"];

export const TRUTH_KINDS: readonly TruthKind[] = ["live", "last_run", "reviewed", "planned"];

export type ResultKind = "pass" | "fail" | "held" | "not_run" | "not_eligible" | "unknown";

export const RESULT_KINDS: readonly ResultKind[] = [
  "pass",
  "fail",
  "held",
  "not_run",
  "not_eligible",
  "unknown",
];

/** The word on a result chip. Each chip carries the word, never only a colour. */
export const RESULT_WORD: Record<ResultKind, string> = {
  pass: "PASS",
  fail: "FAIL",
  held: "HELD",
  not_run: "NOT RUN",
  not_eligible: "NOT ELIGIBLE",
  unknown: "UNKNOWN",
};

const CALENDAR_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** `YYYY-MM-DD` of an instant, on the Pacific calendar. */
export function pacificCalendarDate(instant: Date): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: PACIFIC_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(instant);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

/**
 * Is `YYYY-MM-DD` a day that exists? The shape alone lets "2026-13-01" through,
 * and that would print "UNDEFINED 1" — a wrong date rather than an unreadable
 * one. Round-tripping through `Date.UTC` rejects month 13 and February 30.
 */
function isRealCalendarDate(ymd: string): boolean {
  const m = CALENDAR_DATE.exec(ymd);
  if (!m) return false;
  const [y, month, day] = [Number(m[1]), Number(m[2]), Number(m[3])];
  const t = new Date(Date.UTC(y, month - 1, day));
  return t.getUTCFullYear() === y && t.getUTCMonth() === month - 1 && t.getUTCDate() === day;
}

/**
 * The Pacific calendar date an `asOf` names, as `YYYY-MM-DD`, or null when the
 * string is not a real date. A bare date is taken as already Pacific.
 */
export function asOfCalendarDate(asOf: string): string | null {
  if (CALENDAR_DATE.test(asOf)) return isRealCalendarDate(asOf) ? asOf : null;
  const instant = new Date(asOf);
  if (Number.isNaN(instant.getTime())) return null;
  return pacificCalendarDate(instant);
}

/** "Nov 5" for an `asOf`, on the Pacific calendar; null when unreadable. */
export function pacificDayLabel(asOf: string): string | null {
  const day = asOfCalendarDate(asOf);
  if (!day) return null;
  const m = CALENDAR_DATE.exec(day);
  if (!m) return null;
  return `${MONTHS[Number(m[2]) - 1]} ${Number(m[3])}`;
}

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

/** "July 2026" for a `YYYY-MM`; null when it is not a real month. */
export function calendarMonthLabel(ym: string): string | null {
  const m = /^(\d{4})-(\d{2})$/.exec(ym);
  if (!m) return null;
  const month = Number(m[2]);
  if (month < 1 || month > 12) return null;
  return `${MONTH_NAMES[month - 1]} ${m[1]}`;
}

/** "4:19 PM PT" for a full timestamp; null for a bare date or an unreadable one. */
export function pacificClockLabel(asOf: string): string | null {
  if (CALENDAR_DATE.test(asOf)) return null;
  const instant = new Date(asOf);
  if (Number.isNaN(instant.getTime())) return null;
  const clock = new Intl.DateTimeFormat("en-US", {
    timeZone: PACIFIC_TIME_ZONE,
    hour: "numeric",
    minute: "2-digit",
  }).format(instant);
  return `${clock} PT`;
}

/**
 * When a LIVE number is true as of: the clock on the reader's own Pacific day,
 * and the day too when it is not today ("Nov 5, 9:31 PM PT"), so a payload
 * built yesterday never reads as tonight's. Without a clock (prerender) only
 * the time prints.
 */
export function liveStamp(asOf: string, now: Date | null): string | null {
  const clock = pacificClockLabel(asOf);
  if (!clock) return null;
  if (!now) return clock;
  const day = asOfCalendarDate(asOf);
  return day && day !== pacificCalendarDate(now) ? `${pacificDayLabel(asOf)}, ${clock}` : clock;
}

/**
 * The words on a truth chip. A date that cannot be read says so rather than
 * printing a wrong one.
 */
export function truthChipLabel(truth: Truth): string {
  switch (truth.kind) {
    case "live":
      return "LIVE";
    case "planned":
      return "PLANNED";
    case "last_run":
      return `LAST RUN · ${(pacificDayLabel(truth.asOf) ?? CHIP_COPY.dateUnreadable).toUpperCase()}`;
    case "reviewed":
      return `LAST REVIEWED · ${(pacificDayLabel(truth.asOf) ?? CHIP_COPY.dateUnreadable).toUpperCase()}`;
  }
}

/**
 * Whole Pacific calendar days from `asOf` to `now`; null when `asOf` is
 * unreadable. Calendar days, not 24-hour blocks, so a run at 11 PM is
 * "1 day ago" the next morning, the way a reader counts.
 */
export function ageInDays(asOf: string, now: Date): number | null {
  const then = asOfCalendarDate(asOf);
  if (!then) return null;
  const today = pacificCalendarDate(now);
  const toUtcDay = (ymd: string) => {
    const [y, m, d] = ymd.split("-").map(Number);
    return Date.UTC(y, m - 1, d) / (24 * 60 * 60 * 1000);
  };
  return Math.round(toUtcDay(today) - toUtcDay(then));
}

export function ageLabel(days: number): string {
  if (days <= 0) return "today";
  if (days === 1) return "1 day ago";
  return `${days} days ago`;
}

/** Amber strictly AFTER `AGE_AMBER_DAYS`: a record exactly two weeks old is not yet amber. */
export function isAgeAmber(days: number): boolean {
  return days > AGE_AMBER_DAYS;
}
