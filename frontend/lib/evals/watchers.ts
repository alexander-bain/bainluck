/**
 * THE CHECKS THAT RUN ON THEIR OWN, STATIC VERSION (#12102 S5).
 *
 * `data/watchers-2026-11-06.json` lists the production watchers with their
 * schedules as written in the beat schedule (`backend/app/tasks/__init__.py`
 * at 80b7a1605c, quoted verbatim in the test-only receipts file), what each
 * checks in our own words, and the newest verdict on the public record where
 * one exists. It is a list we keep by hand, so the section is LAST REVIEWED;
 * each verdict carries its own LAST RUN date and receipt.
 *
 * Times are never typed in. The schedule is UTC crontab; the page works out
 * each run's Pacific time in the reader's browser, on the reader's date, so a
 * daylight-saving change moves the times without a deploy.
 *
 * A verdict is the record's: "running red, reporting" when the newest run on
 * record found problems and posted them on GitHub, filing new issues or adding
 * to open ones; "running red, reporting stopped" when it found problems and
 * could not post them; "closed as fixed" when its only posts re-checked
 * problems it had reported, found them gone and closed their issues. That last
 * one is never shown as green: a watcher posts nothing about the problems it
 * does not find. A red run can close issues too, and the page says so. The
 * verdict's time is GitHub's time for the run's first post. A watcher with no
 * public record of its last result says so (UNKNOWN).
 */

import WATCHERS from "@/lib/evals/data/watchers-2026-11-06.json";
import { PACIFIC_TIME_ZONE } from "@/lib/evals/truth";

export type VerdictState = "red_reporting" | "red_stopped" | "closed_fixed";
export const VERDICT_STATES: readonly VerdictState[] = ["red_reporting", "red_stopped", "closed_fixed"];

export interface WatcherVerdict {
  state: VerdictState;
  /** The run's instant, from its receipt. */
  runAt: string;
  receipt: { label: string; href: string };
  /** Issues the run filed or added to, or the issue that names its stopped reporting. */
  issues: number[];
  /** Issues the run re-checked, found fixed and closed. */
  closed: number[];
  /** A fix for stopped reporting that merged after this run, when there is one. */
  fix: number | null;
  /** The issue that recorded this watcher's reporting as stopped before this run. */
  earlier: number | null;
}

export interface Cron {
  minute: string;
  hour: string;
}

export interface Watcher {
  id: string;
  name: string;
  checks: string;
  group: "day" | "night";
  cron: Cron;
  source: string;
  verdict: WatcherVerdict | null;
}

export interface WatcherList {
  reviewedAt: string;
  sinceAt: string;
  scheduleSource: { label: string; href: string };
  alertsHref: string;
  watchers: Watcher[];
}

/** One crontab field ("*", "*\/2", "12,27,42,57", "45") as the values it allows, or null. */
export function cronField(field: string, max: number): number[] | null {
  const all = Array.from({ length: max + 1 }, (_, i) => i);
  if (field === "*") return all;
  const step = /^\*\/(\d+)$/.exec(field);
  if (step) {
    const n = Number(step[1]);
    return n >= 1 && n <= max ? all.filter((v) => v % n === 0) : null;
  }
  if (!/^\d+(,\d+)*$/.test(field)) return null;
  const values = field.split(",").map(Number);
  if (values.some((v) => v > max)) return null;
  return Array.from(new Set(values)).sort((a, b) => a - b);
}

/** Every run in a UTC day, as hour and minute, or null when the crontab is not one this page reads. */
export function cronRuns(cron: Cron): { hour: number; minute: number }[] | null {
  const minutes = cronField(cron.minute, 59);
  const hours = cronField(cron.hour, 23);
  if (!minutes || !hours) return null;
  return hours.flatMap((hour) => minutes.map((minute) => ({ hour, minute })));
}

/**
 * How often, in the units a reader uses: every N minutes (evenly spaced
 * minutes, every hour), every N hours (one minute, an hourly step), or once a
 * day. Null for any other shape, so the row is dropped rather than misread.
 */
export type Cadence =
  | { kind: "minutes"; every: number }
  | { kind: "hours"; every: number; minute: number }
  | { kind: "daily"; hour: number; minute: number };

export function cadence(cron: Cron): Cadence | null {
  const minutes = cronField(cron.minute, 59);
  const hours = cronField(cron.hour, 23);
  if (!minutes || !hours) return null;
  if (hours.length === 24 && minutes.length > 1) {
    const gap = minutes[1] - minutes[0];
    const even = minutes.every((m, i) => i === 0 || m - minutes[i - 1] === gap) && gap * minutes.length === 60;
    return even ? { kind: "minutes", every: gap } : null;
  }
  if (minutes.length !== 1) return null;
  if (hours.length === 1) return { kind: "daily", hour: hours[0], minute: minutes[0] };
  const step = /^\*\/(\d+)$/.exec(cron.hour);
  return step ? { kind: "hours", every: Number(step[1]), minute: minutes[0] } : null;
}

/** The instant a UTC hour and minute fall on, on the reader's UTC calendar day. */
export function utcInstantOn(day: Date, hour: number, minute: number): Date {
  return new Date(Date.UTC(day.getUTCFullYear(), day.getUTCMonth(), day.getUTCDate(), hour, minute));
}

/** Minutes after Pacific midnight for an instant, 0 to 1439. */
export function pacificMinuteOfDay(instant: Date): number {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: PACIFIC_TIME_ZONE,
    hour: "numeric",
    minute: "numeric",
    hourCycle: "h23",
  }).formatToParts(instant);
  const value = (type: string) => Number(parts.find((p) => p.type === type)?.value ?? NaN);
  return value("hour") * 60 + value("minute");
}

const isIssue = (n: unknown): n is number => Number.isInteger(n) && (n as number) > 0;

/** Why a watcher row cannot be shown, or null when it can. */
export function watcherProblem(raw: unknown): string | null {
  const w = raw as Record<string, unknown> | null;
  if (!w || typeof w !== "object") return "not an object";
  if (typeof w.id !== "string" || !w.id) return "no id";
  for (const key of ["name", "checks"] as const) {
    if (typeof w[key] !== "string" || !(w[key] as string).trim()) return `${w.id}: no ${key}`;
  }
  if (w.group !== "day" && w.group !== "night") return `${w.id}: group is not day or night`;
  const cron = w.cron as Cron | undefined;
  if (!cron || typeof cron.minute !== "string" || typeof cron.hour !== "string" || !cadence(cron)) {
    return `${w.id}: a crontab this page cannot read`;
  }
  if (typeof w.source !== "string" || !w.source.startsWith("https://")) return `${w.id}: no source link`;
  const v = w.verdict as Record<string, unknown> | null | undefined;
  if (v === null) return null;
  if (!v || !VERDICT_STATES.includes(v.state as VerdictState)) return `${w.id}: verdict state is not one this page knows`;
  if (typeof v.run_at !== "string" || Number.isNaN(Date.parse(v.run_at))) return `${w.id}: verdict has no readable run time`;
  const receipt = v.receipt as { label?: unknown; href?: unknown } | undefined;
  if (typeof receipt?.label !== "string" || typeof receipt?.href !== "string" || !receipt.href.startsWith("https://")) {
    return `${w.id}: verdict has no receipt`;
  }
  if (!Array.isArray(v.issues) || !v.issues.every(isIssue)) return `${w.id}: verdict issues are not issue numbers`;
  if (!Array.isArray(v.closed) || !v.closed.every(isIssue)) return `${w.id}: closed issues are not issue numbers`;
  if (v.state === "closed_fixed") {
    if (v.issues.length > 0 || v.closed.length === 0) return `${w.id}: a run closed as fixed names only the issues it closed`;
  } else if (v.issues.length === 0) {
    return `${w.id}: verdict names no issue`;
  }
  if (v.fix !== null && !isIssue(v.fix)) return `${w.id}: fix is not an issue number`;
  if (v.earlier !== null && !isIssue(v.earlier)) return `${w.id}: earlier is not an issue number`;
  return null;
}

/** The list, or null when it cannot be read. One unreadable row drops the section rather than a row. */
export function loadWatchers(raw: unknown = WATCHERS): WatcherList | null {
  const d = raw as {
    reviewed_at?: unknown;
    since_at?: unknown;
    schedule_source?: { label?: unknown; href?: unknown };
    alerts_href?: unknown;
    watchers?: unknown[];
  } | null;
  if (!d || typeof d.reviewed_at !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(d.reviewed_at)) return null;
  const sinceAt =
    typeof d.since_at === "string" && /^\d{4}-\d{2}-\d{2}$/.test(d.since_at) ? d.since_at : d.reviewed_at;
  if (typeof d.schedule_source?.label !== "string" || typeof d.schedule_source?.href !== "string") return null;
  if (typeof d.alerts_href !== "string" || !d.alerts_href.startsWith("https://")) return null;
  if (!Array.isArray(d.watchers) || d.watchers.length === 0) return null;
  if (d.watchers.some((w) => watcherProblem(w) !== null)) return null;
  return {
    reviewedAt: d.reviewed_at,
    sinceAt,
    scheduleSource: { label: d.schedule_source.label, href: d.schedule_source.href },
    alertsHref: d.alerts_href,
    watchers: (d.watchers as Record<string, unknown>[]).map((w) => {
      const v = w.verdict as Record<string, unknown> | null;
      return {
        id: w.id as string,
        name: w.name as string,
        checks: w.checks as string,
        group: w.group as "day" | "night",
        cron: w.cron as Cron,
        source: w.source as string,
        verdict: v
          ? {
              state: v.state as VerdictState,
              runAt: v.run_at as string,
              receipt: v.receipt as { label: string; href: string },
              issues: v.issues as number[],
              closed: v.closed as number[],
              fix: (v.fix as number | null) ?? null,
              earlier: (v.earlier as number | null) ?? null,
            }
          : null,
      };
    }),
  };
}

/**
 * The checks at a glance, counted from the list (the top screen's picture).
 * A check is working when its newest run is on the public record and its
 * reporting is not stopped. What it found is a second question: problems it
 * reported, or the problem it had reported now fixed. A check with no public
 * record is unknown, never working.
 */
export interface WatcherHealth {
  total: number;
  working: number;
  foundProblems: number;
  foundFixed: number;
  stopped: number;
  unknown: number;
}

export function watcherHealth(list: WatcherList): WatcherHealth {
  const states = list.watchers.map((w) => w.verdict?.state ?? null);
  const count = (s: VerdictState | null) => states.filter((x) => x === s).length;
  return {
    total: states.length,
    working: count("red_reporting") + count("closed_fixed"),
    foundProblems: count("red_reporting"),
    foundFixed: count("closed_fixed"),
    stopped: count("red_stopped"),
    unknown: count(null),
  };
}
