"use client";

/**
 * #5470 / ship 2 — "is the background app running the code the site is
 * serving?", on `/admin`.
 *
 * THE GAP THIS CLOSES. Notice 48 names three reads of increasing truth for a
 * heavy release, and says the one that counts is
 * `/api/admin/celery/fleet-code` reporting MATCHED. YOUR-TURN's attended
 * recovery step says the same thing in Alex's words — "the coordinator/latency
 * lane must verify worker code matches" — which is to say the only reader of
 * the fact that decides whether a merged ship is actually running is a lane
 * with an admin token and a curl. `/health`, `heroku releases -a bainluck` and
 * a LOOK at the page are all blind to it, and the LOOK is the most misleading,
 * because the page renders a number the shipped gate would have changed.
 *
 * So this is the sibling of the clock tile and exists for the same reason: a
 * verification step nobody can type is not a verification step.
 *
 * WHAT IT REFUSES TO DO.
 *
 * 1. `on_slug_s` is null for a worker whose marker predates the age stamp, and
 *    a missing age must never render as a fresh one. Absent is printed as
 *    absent ("how long isn't known yet") — the whole reason the endpoint
 *    reports a NUMBER instead of minting a `BEHIND` verdict is that forty
 *    minutes and six days must stop rendering as the same word, and a null
 *    silently formatted as `0m` would hand that defect straight back.
 * 2. An unreadable census is INCONCLUSIVE, never MATCHED (gotcha #53). MATCHED
 *    is the only pass in a five-valued vocabulary, and "we could not check"
 *    sharing a tile with "we checked" is the drift itself, wearing an
 *    instrument.
 * 3. UNKNOWN_VERSION is not agreement. A worker that cannot name its own slug,
 *    or an expected worker family that has not stamped at all, is a silence —
 *    and the stalest app in the fleet is the one most likely to be silent.
 */

import useSWR from "swr";
import { adminFetchJSON } from "@/lib/adminFetch";

export interface FleetCodeReport {
  status?: string;
  verdict?: string;
  reader_slug?: string | null;
  drifted?: string[];
  matched?: string[];
  unknown?: string[];
  unstamped_expected?: string[];
  /** Seconds each worker has been on its current code. `null` = not known. */
  on_slug_s?: Record<string, number | null>;
  detail?: Record<string, { slug?: string | null }>;
  ttl_s?: number;
}

/** Plain English for the two app names. An app we have not been taught prints
 *  verbatim rather than guessed at. */
export function appLabel(app: string): string {
  if (app === "bainluck") return "the site app";
  if (app === "bainluck-heavy") return "the background app";
  return app;
}

/** `bainluck-heavy/worker-heavy.1` → "the background app's heavy worker". A
 *  slot shape we have not been taught keeps its own name. */
export function workerLabel(identity: string): string {
  const slash = identity.indexOf("/");
  if (slash <= 0) return identity;
  const app = identity.slice(0, slash);
  const slot = identity.slice(slash + 1);
  const family = slot.split(".")[0];
  const named: Record<string, string> = {
    "worker-heavy": "heavy worker",
    "worker-background": "background worker",
    "worker-realtime": "realtime worker",
  };
  return `${appLabel(app)}'s ${named[family] || family}`;
}

/**
 * How long, for a human. `null`/`undefined` is ABSENT and returns "", which the
 * caller renders as "isn't known yet" — never as a zero.
 */
export function humanAge(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "";
  if (!Number.isFinite(seconds) || seconds < 0) return "";
  if (seconds < 60) return "under a minute";
  const mins = Math.floor(seconds / 60);
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  return `${hours}h ${mins % 60}m`;
}

export type FleetTone = "ok" | "warn" | "bad";

export interface FleetLine {
  /** "the background app's heavy worker" */
  who: string;
  /** "on a1ba6f34 for 3h 12m", or "on a1ba6f34 — how long isn't known yet" */
  what: string;
}

export interface FleetReading {
  headline: string;
  detail: string;
  /** One row per worker that is not running the reader's code. */
  lines: FleetLine[];
  /** The one command that fixes it, or "" when there is nothing to do. */
  fix: string;
  tone: FleetTone;
}

/** YOUR-TURN's attended recovery command, verbatim: the same tested path the
 *  scheduled runs use, never a hand-rolled `git push heroku-heavy`. */
export const HEAVY_SYNC_COMMAND =
  "gh workflow run heavy-sync.yml --repo alexander-bain/bainluck";

function describe(
  identity: string,
  report: FleetCodeReport
): FleetLine {
  const slug = (report.detail || {})[identity]?.slug || null;
  const age = humanAge((report.on_slug_s || {})[identity]);
  const on = slug ? `on ${slug}` : "on code it will not name";
  return {
    who: workerLabel(identity),
    what: age ? `${on} for ${age}` : `${on} — how long isn't known yet`,
  };
}

/**
 * The whole judgement as a pure function of the report, so the tile's meaning
 * is testable without a render tree or a network.
 *
 * `undefined` is the pre-fetch state and is NOT a verdict.
 */
export function fleetCodeReading(
  report: FleetCodeReport | undefined
): FleetReading {
  if (!report || !report.verdict) {
    return {
      headline: "Reading the fleet…",
      detail: "",
      lines: [],
      fix: "",
      tone: "warn",
    };
  }

  const drifted = report.drifted || [];
  const silent = [...(report.unknown || []), ...(report.unstamped_expected || [])];

  switch (report.verdict) {
    case "MATCHED":
      return {
        headline: "Every worker is running the code the site is serving.",
        detail: report.reader_slug ? `Site is on ${report.reader_slug}.` : "",
        lines: [],
        fix: "",
        tone: "ok",
      };

    case "DRIFTED": {
      // A DRIFTED with an empty culprit list is the endpoint contradicting
      // itself. It must not round down to a calm tile.
      if (drifted.length === 0) {
        return {
          headline: "Something is on other code, and the census won't say what.",
          detail: "Treat this as behind, not as up to date.",
          lines: [],
          fix: HEAVY_SYNC_COMMAND,
          tone: "bad",
        };
      }
      const noun = drifted.length === 1 ? "worker is" : "workers are";
      return {
        headline: `${drifted.length} ${noun} running other code than the site.`,
        detail: report.reader_slug
          ? `The site is serving ${report.reader_slug}. A fix merged since then is not running there.`
          : "A fix merged since then is not running there.",
        lines: drifted.map((i) => describe(i, report)),
        fix: HEAVY_SYNC_COMMAND,
        tone: "bad",
      };
    }

    case "UNKNOWN_VERSION":
      return {
        headline: "A worker can't say what code it is running.",
        detail: "That is a silence, not agreement — the stalest app is the one most likely to be quiet.",
        lines: silent.map((i) => ({ who: workerLabel(i), what: "has not said" })),
        fix: "",
        tone: "warn",
      };

    case "NONE":
      return {
        headline: "No worker has reported its code at all.",
        detail: "Either nothing is running, or nothing has run a job since the last release.",
        lines: [],
        fix: "",
        tone: "bad",
      };

    default:
      // INCONCLUSIVE, or a verdict this tile has not been taught. Either way it
      // is an unread instrument, which is not evidence of an up-to-date fleet.
      return {
        headline: "Can't read the fleet.",
        detail: "This is not proof the background app is up to date.",
        lines: [],
        fix: "",
        tone: "warn",
      };
  }
}

const TONE_CLASS: Record<FleetTone, string> = {
  ok: "text-accent-live",
  warn: "text-accent-warning",
  bad: "text-accent-danger",
};

/** Presentational half — takes the report, never fetches. */
export function FleetCodeTile({ report }: { report: FleetCodeReport | undefined }) {
  const reading = fleetCodeReading(report);

  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-4">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-text-primary">
          Code the workers are running
        </h3>
        {report?.verdict && (
          <span className={"text-micro font-medium " + TONE_CLASS[reading.tone]}>
            {report.verdict}
          </span>
        )}
      </div>

      <p className={"text-sm " + TONE_CLASS[reading.tone]}>{reading.headline}</p>

      {reading.detail && (
        <p className="mt-1 text-xs text-text-secondary">{reading.detail}</p>
      )}

      {reading.lines.length > 0 && (
        <ul className="mt-2 space-y-0.5">
          {reading.lines.map((l) => (
            <li key={l.who} className="text-micro text-text-muted">
              {l.who} — {l.what}
            </li>
          ))}
        </ul>
      )}

      {reading.fix && (
        <code className="mt-2 block rounded bg-surface-elevated px-2 py-1 text-micro text-text-primary">
          {reading.fix}
        </code>
      )}
    </div>
  );
}

/** Fetching half. The census refreshes server-side every 60s, so asking more
 *  often than that buys nothing. */
export default function FleetCodeCard({ secret }: { secret: string }) {
  const { data, error } = useSWR<FleetCodeReport>(
    ["admin-fleet-code", secret],
    () => adminFetchJSON<FleetCodeReport>("/api/admin/celery/fleet-code", secret),
    { refreshInterval: 60000 }
  );

  // A failed fetch is INCONCLUSIVE, not MATCHED — same reason the endpoint
  // raises on an unreadable Redis rather than returning an empty fleet.
  const report: FleetCodeReport | undefined = error
    ? { verdict: "INCONCLUSIVE" }
    : data;

  return <FleetCodeTile report={report} />;
}
