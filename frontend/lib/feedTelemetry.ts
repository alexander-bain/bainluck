/**
 * Feed latency telemetry (L2-189, Item 1)
 *
 * Turns the backend's per-request feed headers (`X-Feed-Elapsed-Ms`,
 * `X-Feed-Cache`) — now exposed cross-origin via CORS `expose_headers` — into
 * a bounded, non-PII analytics event so the broken-cache / slow-compute state
 * that the L2-188 audit could only see from `curl` becomes observable in the
 * field.
 *
 * Privacy contract: an emitted event carries ONLY endpoint, cohort,
 * cache-status, and durations. It NEVER carries a token, cookie, session id,
 * user id, or any market payload. The cohort is a coarse label derived from
 * whether the request was authenticated and whether an anonymous session id
 * was present — the underlying ids themselves are never sent.
 *
 * Everything here is best-effort: any failure is swallowed so telemetry can
 * never change rendering, retries, or the value fetchFeed returns.
 */

import { trackEvent } from "@/lib/analytics";

export type FeedCohort = "authenticated" | "session_anon" | "shared_anon";

export interface FeedTelemetry {
  /** Endpoint path only (no query string / ids). */
  endpoint: string;
  /** Coarse audience bucket — never the underlying token/session/user id. */
  cohort: FeedCohort;
  /** `X-Feed-Cache` value (hit/miss/stale_hit/error/disabled/…) or "unknown". */
  cache_status: string;
  /** `X-Feed-Elapsed-Ms` backend compute time, or null if header unreadable. */
  backend_elapsed_ms: number | null;
  /** Client-observed time-to-response in ms (includes any retry/backoff). */
  duration_ms: number;
}

/**
 * Coarse audience cohort. Signed-in wins; otherwise an anonymous session id
 * (personalized-anon) vs no session id at all (shared-anon).
 */
export function resolveFeedCohort(
  authenticated: boolean,
  hasSessionId: boolean
): FeedCohort {
  if (authenticated) return "authenticated";
  if (hasSessionId) return "session_anon";
  return "shared_anon";
}

/** Parse `X-Feed-Elapsed-Ms` → number, or null on missing/malformed input. */
export function parseElapsedMs(raw: string | null | undefined): number | null {
  if (raw == null || raw === "") return null;
  const n = Number(raw);
  return Number.isFinite(n) && n >= 0 ? Math.round(n) : null;
}

/** Normalize `X-Feed-Cache` → non-empty string, or "unknown" when unreadable. */
export function normalizeCacheStatus(raw: string | null | undefined): string {
  if (raw == null) return "unknown";
  const trimmed = raw.trim();
  return trimmed === "" ? "unknown" : trimmed;
}

/**
 * Build the telemetry payload from raw header values + measured duration.
 * Pure and side-effect free so it is directly unit-testable. Malformed or
 * missing headers degrade to "unknown"/null rather than throwing.
 */
export function buildFeedTelemetry(args: {
  endpoint: string;
  cohort: FeedCohort;
  cacheHeader: string | null | undefined;
  elapsedHeader: string | null | undefined;
  durationMs: number;
}): FeedTelemetry {
  return {
    endpoint: args.endpoint,
    cohort: args.cohort,
    cache_status: normalizeCacheStatus(args.cacheHeader),
    backend_elapsed_ms: parseElapsedMs(args.elapsedHeader),
    duration_ms: Math.max(0, Math.round(args.durationMs)),
  };
}

/**
 * Read the exposed feed headers off a cross-origin `Response`, build the
 * bounded event, and emit it through the existing consent-aware analytics rail
 * (`trackEvent` → GA4 Consent Mode). Never throws.
 */
export function reportFeedTelemetry(
  res: Response,
  args: {
    endpoint: string;
    authenticated: boolean;
    hasSessionId: boolean;
    durationMs: number;
  }
): FeedTelemetry | null {
  try {
    const telemetry = buildFeedTelemetry({
      endpoint: args.endpoint,
      cohort: resolveFeedCohort(args.authenticated, args.hasSessionId),
      // A cross-origin header the CORS layer does not expose reads back as
      // null here — normalizeCacheStatus/parseElapsedMs handle that silently.
      cacheHeader: res.headers?.get?.("X-Feed-Cache") ?? null,
      elapsedHeader: res.headers?.get?.("X-Feed-Elapsed-Ms") ?? null,
      durationMs: args.durationMs,
    });
    trackEvent("feed_telemetry", telemetry);
    return telemetry;
  } catch {
    // Telemetry is strictly best-effort: swallow everything.
    return null;
  }
}
