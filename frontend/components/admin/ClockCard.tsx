"use client";

/**
 * #5470 / ship 2 — the clock tile on `/admin`.
 *
 * YOUR-TURN's attended step for moving the `scheduler` dyno off the site app
 * reads: "Then open bainluck.com/admin — the clock tile should say **one
 * clock**, on the background app. If it ever says two: `heroku ps:scale
 * scheduler=0 -a bainluck`." That tile did not exist. The census behind it has
 * been live and correct since `/api/admin/celery/beat-instances` shipped; the
 * only reader was a curl with an admin token, which is not a verification step
 * anyone should be asked to type mid-handover.
 *
 * Why the count is the alarm and the location is not: celery beat has no
 * distributed lock here (default `PersistentScheduler`, state in a shelve file
 * on the dyno's own disk), so two beat dynos do not contend — they both tick
 * and EVERY scheduled task in the system runs twice. The window where that can
 * happen is the seconds between the two `ps:scale` commands, which is exactly
 * when someone is looking at this tile.
 *
 * `verdict` is three-valued and NONE is not the good one. An unreadable census
 * renders INCONCLUSIVE, never NONE (gotcha #53): an outage and an empty fleet
 * must not produce the same tile, because here that turns the loudest possible
 * alarm into a quiet one.
 */

import useSWR from "swr";
import { adminFetchJSON } from "@/lib/adminFetch";

export interface BeatCensus {
  status?: string;
  verdict?: string;
  count?: number;
  instances?: string[];
  slugs?: string[];
  ttl_s?: number;
}

/** Plain English for the two app names, per the standing rule that anything
 *  Alex reads names the thing, not the machine. An unrecognised app is printed
 *  verbatim rather than guessed at. */
export function appLabel(app: string): string {
  if (app === "bainluck") return "the site app";
  if (app === "bainluck-heavy") return "the background app";
  return app;
}

/** The app half of a beat identity (`bainluck/scheduler.1/2`). */
export function instanceApps(instances: string[] | undefined): string[] {
  const apps = (instances || [])
    .map((i) => i.split("/")[0])
    .filter((a) => a.length > 0);
  return Array.from(new Set(apps)).sort();
}

export type ClockTone = "ok" | "warn" | "bad";

export interface ClockReading {
  /** The headline a human reads first. */
  headline: string;
  /** One short line under it, or "" for none. */
  detail: string;
  /** The one command that fixes it, or "" when there is nothing to do. */
  fix: string;
  tone: ClockTone;
}

/**
 * The whole judgement, as a pure function of the census, so the tile's meaning
 * is testable without a render tree or a network.
 *
 * `undefined` is the pre-fetch state and is NOT a verdict — it must not read as
 * a healthy clock or a missing one.
 */
export function clockReading(census: BeatCensus | undefined): ClockReading {
  if (!census || !census.verdict) {
    return { headline: "Reading the clock…", detail: "", fix: "", tone: "warn" };
  }

  const apps = instanceApps(census.instances);
  const where = apps.map(appLabel).join(" and ");

  switch (census.verdict) {
    case "SINGLE":
      return {
        headline: `One clock, on ${where || "an unnamed app"}.`,
        detail:
          apps.length === 1 && apps[0] === "bainluck"
            ? "Still on the site app, so a site release restarts it."
            : "",
        fix: "",
        tone: apps.length === 1 && apps[0] === "bainluck" ? "warn" : "ok",
      };

    case "MULTIPLE":
      return {
        headline: `${census.count ?? apps.length} clocks — every scheduled job is running twice.`,
        detail: where ? `Running on ${where}.` : "",
        fix: "heroku ps:scale scheduler=0 -a bainluck",
        tone: "bad",
      };

    case "NONE":
      return {
        headline: "No clock — nothing is scheduling anything.",
        detail: "",
        fix: "heroku ps:scale scheduler=1:Standard-1X -a bainluck-heavy",
        tone: "bad",
      };

    default:
      // INCONCLUSIVE, or a verdict this tile has not been taught. Either way it
      // is an unread instrument, which is not evidence of a healthy clock.
      return {
        headline: "Can't read the clock.",
        detail: "This is not proof that one is running.",
        fix: "",
        tone: "warn",
      };
  }
}

const TONE_CLASS: Record<ClockTone, string> = {
  ok: "text-accent-live",
  warn: "text-accent-warning",
  bad: "text-accent-danger",
};

/** Presentational half — takes the census, never fetches. */
export function ClockTile({ census }: { census: BeatCensus | undefined }) {
  const reading = clockReading(census);

  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-4">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-text-primary">Clock</h3>
        {census?.verdict && (
          <span className={"text-micro font-medium " + TONE_CLASS[reading.tone]}>
            {census.verdict}
          </span>
        )}
      </div>

      <p className={"text-sm " + TONE_CLASS[reading.tone]}>{reading.headline}</p>

      {reading.detail && (
        <p className="mt-1 text-xs text-text-secondary">{reading.detail}</p>
      )}

      {reading.fix && (
        <code className="mt-2 block rounded bg-surface-elevated px-2 py-1 text-micro text-text-primary">
          {reading.fix}
        </code>
      )}

      {census?.instances && census.instances.length > 0 && (
        <ul className="mt-2 space-y-0.5">
          {census.instances.map((i) => (
            <li key={i} className="text-micro text-text-muted">
              {i}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Fetching half. Refreshes on the census's own 30s cadence so the seconds-long
 *  two-clock window during a handover is actually visible on an open tab. */
export default function ClockCard({ secret }: { secret: string }) {
  const { data, error } = useSWR<BeatCensus>(
    ["admin-beat-instances", secret],
    () =>
      adminFetchJSON<BeatCensus>("/api/admin/celery/beat-instances", secret),
    { refreshInterval: 30000 }
  );

  // A failed fetch is INCONCLUSIVE, not NONE — same reason the endpoint refuses
  // to render an unreadable Redis as an empty fleet.
  const census: BeatCensus | undefined = error
    ? { verdict: "INCONCLUSIVE" }
    : data;

  return <ClockTile census={census} />;
}
