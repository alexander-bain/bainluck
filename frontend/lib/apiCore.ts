/**
 * The API transport, plus the endpoint wrappers the landing page's EAGER module
 * graph actually reaches.
 *
 * WHY THIS FILE EXISTS (LAT-P208). `lib/api.ts` is one module carrying every
 * endpoint wrapper in the app — golf leaderboards, admin source intelligence,
 * onboarding, March Madness, calibration, the themed dashboards. Because it is
 * a SINGLE module shared by ~30 route entries, webpack cannot tree-shake it per
 * route: the chunk it lands in carries the union of every route's needs, and
 * that chunk was eager on `/`. A reader waiting for the first Discover card was
 * downloading and parsing the golf client.
 *
 * The split is physical, not a barrel: a re-export barrel would keep the big
 * module in `/`'s graph. `lib/api.ts` re-exports everything here so the ~65
 * other call sites are unchanged, and only the modules on `/`'s eager path
 * import from `@/lib/apiCore` directly.
 *
 * THE RULE FOR ADDING TO THIS FILE — and it is a real constraint, not advice:
 * a symbol belongs here only if the eager graph of `/` (that is,
 * `app/layout.tsx` + `app/discover/page.tsx`, following static imports only)
 * reaches it. Anything else stays in `lib/api.ts`. The guard test
 * `frontend/__tests__/lib/emittedEntryGraph.test.ts` reads the emitted bundle
 * and fails if the wider client comes back onto `/`.
 */

import type {
  FeedResponse,
  UserPreferencesResponse,
} from "./types";
import { getDiscoverSessionId } from "./discoverInteractions";
import {
  formatProbabilityPercent,
  type ProbabilityFormatOptions,
} from "./probabilityDisplay";
import { reportFeedTelemetry } from "./feedTelemetry";
import { resolveSharedAnonSuppression } from "./discover/sharedAnonFeed";
import { bootDurationMs, claimBootFeed } from "./discover/feedBoot";

/** The API origin. Exported so `feedBoot.ts` builds its boot URL against the
 *  same value this module fetches from, rather than a second copy of the
 *  env-var-plus-fallback expression (LAT-P184). */
export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const AUTH_TOKEN_TIMEOUT_MS = 2500;

/**
 * Auth token getter — set by AuthProvider when user signs in.
 * This avoids a circular dependency between the API client and useAuth.ts.
 */
let _getAuthToken: (() => Promise<string | null>) | null = null;

export function setAuthTokenGetter(getter: (() => Promise<string | null>) | null) {
  _getAuthToken = getter;
}

async function getAuthTokenWithTimeout(): Promise<string | null> {
  if (!_getAuthToken) return null;

  let timeout: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      _getAuthToken(),
      new Promise<null>((resolve) => {
        timeout = setTimeout(() => resolve(null), AUTH_TOKEN_TIMEOUT_MS);
      }),
    ]);
  } catch (error) {
    console.warn("[API] Auth token unavailable; continuing without auth", error);
    return null;
  } finally {
    if (timeout) clearTimeout(timeout);
  }
}

/**
 * An HTTP error from `apiFetch`, carrying the status and the raw `detail` body
 * so a page can distinguish a typed degradation (a structured `detail` object)
 * from a generic failure and render accordingly.
 */
export interface ApiError extends Error {
  status?: number;
  detail?: unknown;
}

/**
 * Base fetch wrapper with error handling and optional auth
 */
export async function apiFetch<T>(
  endpoint: string,
  options?: RequestInit & {
    timeoutMs?: number;
    /**
     * Optional observability hook (L2-189). When provided, it is invoked with
     * the raw `Response` (before the body is parsed) and a small meta object,
     * so callers such as fetchFeed can read exposed headers without weakening
     * the generic `Promise<T>` contract. It must never throw; callers wrap
     * their own body in try/catch and this call site does too.
     */
    onResponse?: (res: Response, meta: { authenticated: boolean }) => void;
  }
): Promise<T> {
  const headers: Record<string, string> = {
    ...(options?.headers as Record<string, string> || {}),
  };

  // Attach auth token if available
  const token = await getAuthTokenWithTimeout();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const timeoutMs = options?.timeoutMs ?? 20000;
  const maxRetries = 2;

  // An externally-supplied signal (e.g. SearchBar's typeahead AbortController)
  // must cancel the in-flight fetch AND stop the retry loop. It is separate
  // from the per-attempt timeout controller below, so wire the two together.
  const externalSignal = options?.signal ?? undefined;
  if (externalSignal?.aborted) {
    throw new DOMException("Aborted", "AbortError");
  }

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    const onExternalAbort = () => controller.abort();
    externalSignal?.addEventListener("abort", onExternalAbort);

    try {
      const res = await fetch(`${API_URL}${endpoint}`, {
        ...options,
        headers,
        signal: controller.signal,
      });

      clearTimeout(timeout);
      externalSignal?.removeEventListener("abort", onExternalAbort);

      if (!res.ok) {
        const error = await res.json().catch(() => ({ detail: "Unknown error" }));
        // `detail` is a string on most routes but a structured object on the
        // typed-degradation routes (e.g. /api/calibration's unavailable
        // response). Stringifying an object here yields "[object Object]", so
        // read its message and hand the whole thing to the caller instead —
        // that's what lets a page render an honest state rather than a generic
        // "Failed to load".
        const detail: unknown = error?.detail;
        const message =
          typeof detail === "string" && detail
            ? detail
            : typeof (detail as { message?: unknown })?.message === "string"
              ? (detail as { message: string }).message
              : `API error: ${res.status}`;
        const apiError = new Error(message) as ApiError;
        apiError.status = res.status;
        apiError.detail = detail;
        throw apiError;
      }

      // Observability hook (L2-189). Runs before body parse so callers can read
      // response headers. Best-effort only — never let it affect the response.
      if (options?.onResponse) {
        try {
          options.onResponse(res, { authenticated: !!token });
        } catch {
          /* telemetry must never change rendering or retries */
        }
      }

      return res.json();
    } catch (err: unknown) {
      clearTimeout(timeout);
      externalSignal?.removeEventListener("abort", onExternalAbort);
      // Caller aborted (not a timeout) — surface immediately, never retry.
      if (externalSignal?.aborted) {
        throw new DOMException("Aborted", "AbortError");
      }
      const isTimeout = err instanceof DOMException && err.name === "AbortError";
      const isNetworkError = err instanceof TypeError && (err.message.includes("fetch") || err.message.includes("network"));
      if ((isTimeout || isNetworkError) && attempt < maxRetries) {
        await new Promise(r => setTimeout(r, 1000 * 2 ** attempt));
        continue;
      }
      if (isTimeout) {
        throw new Error(`Request timeout: ${endpoint}`);
      }
      throw err;
    }
  }
  throw new Error(`Request failed after ${maxRetries + 1} attempts: ${endpoint}`);
}

/**
 * Authenticated fetch wrapper for POST/PUT/DELETE with JSON body.
 * Optionally accepts a direct token to bypass _getAuthToken (useful when
 * the caller has already obtained a fresh token, e.g. after re-auth).
 */
export async function apiMutate<T>(
  endpoint: string,
  method: string,
  body?: unknown,
  directToken?: string | null,
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  // Use direct token if provided, otherwise fall back to the global getter
  if (directToken) {
    headers["Authorization"] = `Bearer ${directToken}`;
  } else if (_getAuthToken) {
    const token = await _getAuthToken();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
  }

  const res = await fetch(`${API_URL}${endpoint}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(error.detail || `API error: ${res.status}`);
  }

  return res.json();
}

/**
 * Format probability as percentage string
 */
export function formatProbability(
  prob: number | null | undefined,
  options?: ProbabilityFormatOptions,
): string {
  if (prob === null || prob === undefined) return "-";
  // UX-P046: delegate the rounding so a small-but-real probability never prints
  // as "0%" (which reads as impossible). The "-" for absent data is unchanged,
  // and every value that already rounded inside 1%-99% prints identically.
  // UX-P114: a caller drawing BOTH sides of one question passes the server's
  // card-level integer so the two do not sum to 101; omitting it is unchanged.
  // An OBJECT, not a bare number — see `formatProbabilityPercent` for the
  // `.map(fn)` index trap that shape exists to turn into a type error.
  return formatProbabilityPercent(prob, options);
}

// ============================================================================
// Typeahead (the header search bar — chrome, so eager on every route)
// ============================================================================

/**
 * Typeahead search — lightweight suggestions for the search bar
 */
export interface TypeaheadSuggestion {
  type: "team" | "event" | "futures" | "event_concept" | "hub";
  text: string;
  // Team fields
  abbreviation?: string;
  logo?: string;
  team_id?: number;
  team_slug?: string;
  sport_key?: string;
  // Event fields
  event_id?: number;
  status?: string;
  sport?: string;
  commence_time?: string;
  // Event concept fields (#999 L2-65: tournament pages)
  event_key?: string;
  // Hub fields (L2-88: competition-hub landing shortcut)
  competition?: string;
  href?: string;
  emoji?: string;
  // Futures fields
  market_id?: number;
  market_tier?: number;
  market_type_label?: string;
  // #993 Slice A: the answer, carried into the dropdown (top 3, #23-normalized)
  top_outcomes?: TypeaheadOutcome[];
}

/** Lean outcome shape carried by typeahead futures suggestions (#993). */
export interface TypeaheadOutcome {
  name: string;
  probability: number | null;
  movement: number | null;
}

export interface TypeaheadResponse {
  suggestions: TypeaheadSuggestion[];
  query: string;
  did_you_mean?: string;
}

export async function fetchTypeahead(
  q: string,
  signal?: AbortSignal
): Promise<TypeaheadResponse> {
  return apiFetch<TypeaheadResponse>(
    `/api/events/typeahead?q=${encodeURIComponent(q)}`,
    { signal }
  );
}

export async function fetchTrendingSearches(): Promise<{ trending: { query: string; count: number }[] }> {
  return apiFetch<{ trending: { query: string; count: number }[] }>("/api/events/search/trending");
}

// ============================================================================
// The Discover feed itself
// ============================================================================

export async function fetchFeed(
  params?: {
    limit?: number;
    offset?: number;
    sport?: string;
    my_teams_only?: boolean;
    include_futures?: boolean;
    include_events?: boolean;
    event_pct?: number;
    tags?: string[];
    mode?: string;
    category?: string;
  },
  // L2-242 / C133 — for the PROVEN first request of a fresh, signed-out,
  // zero-interaction visitor, omit `x-session-id` so the backend serves the
  // shared `anon` warm feed instead of minting a guaranteed-cold `s:<uuid>` key.
  // Omitting these opts (every existing caller, and all pagination) keeps the
  // exact prior behavior: mint + attach the session id.
  opts?: {
    sharedAnonEligible?: boolean;
    authenticated?: boolean;
    hasInMemoryInteraction?: boolean;
  }
): Promise<FeedResponse> {
  const searchParams = new URLSearchParams();

  if (params?.limit) searchParams.set("limit", params.limit.toString());
  if (params?.offset) searchParams.set("offset", params.offset.toString());
  if (params?.sport) searchParams.set("sport", params.sport);
  if (params?.my_teams_only) searchParams.set("my_teams_only", "true");
  if (params?.include_futures === false) searchParams.set("include_futures", "false");
  if (params?.include_events === false) searchParams.set("include_events", "false");
  if (params?.event_pct != null) searchParams.set("event_pct", params.event_pct.toString());
  if (params?.tags?.length) searchParams.set("tags", JSON.stringify(params.tags));
  if (params?.mode) searchParams.set("mode", params.mode);
  if (params?.category) searchParams.set("category", params.category);

  const query = searchParams.toString();
  // A suppressed request must NOT read-through-mint a session id; only the
  // session-scoped path calls the minting getter.
  const suppressSessionId = resolveSharedAnonSuppression({
    eligible: !!opts?.sharedAnonEligible,
    authenticated: !!opts?.authenticated,
    hasInMemoryInteraction: !!opts?.hasInMemoryInteraction,
  });
  const sessionId = suppressSessionId ? undefined : getDiscoverSessionId();
  const headers = sessionId ? { "x-session-id": sessionId } : undefined;

  const endpoint = `/api/feed${query ? `?${query}` : ""}`;

  // L2-189: measure client time-to-response and emit bounded, non-PII latency
  // telemetry from the exposed feed headers. All best-effort — never affects
  // the value returned to the caller.
  const startedAt =
    typeof performance !== "undefined" ? performance.now() : Date.now();

  // LAT-P184 (D-C, staged loading). The document may already have this exact
  // request in flight — issued at HTML parse time, before a single chunk of the
  // entry graph had executed. Claim it rather than re-issuing it.
  //
  // The claim is gated on `suppressSessionId` and on an exact URL match, so it
  // can only ever hand back the shared-anon warm response to the shared-anon
  // request. Anything else — a mismatch, a non-2xx, a rejected fetch — falls
  // through to the normal `apiFetch` path, which keeps its retries and its
  // typed errors.
  if (suppressSessionId && !headers) {
    const booted = claimBootFeed(`${API_URL}${endpoint}`);
    if (booted?.response) {
      try {
        const res = await booted.response;
        if (res.ok) {
          const parsed = (await res.json()) as FeedResponse;
          try {
            reportFeedTelemetry(res, {
              endpoint: "/api/feed",
              authenticated: false,
              hasSessionId: false,
              durationMs: bootDurationMs(
                booted,
                typeof performance !== "undefined"
                  ? performance.now()
                  : Date.now()
              ),
            });
          } catch {
            /* telemetry must never change what the caller receives */
          }
          return parsed;
        }
      } catch {
        /* boot fetch failed — the normal request below is the fallback */
      }
    }
  }

  return apiFetch<FeedResponse>(endpoint, {
    headers,
    onResponse: (res, meta) => {
      const now =
        typeof performance !== "undefined" ? performance.now() : Date.now();
      reportFeedTelemetry(res, {
        endpoint: "/api/feed",
        authenticated: meta.authenticated,
        hasSessionId: !!sessionId,
        durationMs: now - startedAt,
      });
    },
  });
}

/** A settled guess, rendered by the Discover resolution group. */
export interface ResolutionItem {
  /** FuturesMarket id — link the settled result back to /futures/{id}. */
  market_id: number;
  market_name: string;
  category: string | null;
  guess: string;
  threshold: number;
  actual: number;
  correct: boolean;
  created_at: string | null;
}

export async function fetchResolutions(): Promise<{ resolutions: ResolutionItem[] }> {
  return apiFetch<{ resolutions: ResolutionItem[] }>("/api/predictions/resolutions");
}

// ============================================================================
// Pins & preferences — mounted by the app shell, so eager on every route
// ============================================================================

export interface PinsResponse {
  events: number[];
  futures: number[];
}

/**
 * Fetch the current user's pinned event and futures IDs
 */
export async function fetchUserPins(): Promise<PinsResponse> {
  return apiFetch<PinsResponse>("/api/me/pins");
}

/**
 * Add a single pin
 */
export async function addPin(
  pinType: "event" | "future",
  targetId: number
): Promise<void> {
  await apiMutate("/api/me/pins", "POST", {
    pin_type: pinType,
    target_id: targetId,
  });
}

/**
 * Remove a single pin
 */
export async function removePin(
  pinType: "event" | "future",
  targetId: number
): Promise<void> {
  await apiMutate(`/api/me/pins/${pinType}/${targetId}`, "DELETE");
}

/**
 * In-flight coalescing for `GET /api/me/preferences`.
 *
 * On a single hard authenticated load, multiple mount-time consumers request the
 * same preferences: the app-shell `preferred_sport` GA4 property (via
 * `usePreferredSportProperty` in `PinSyncEffect`) plus a route's own
 * `useCategoryInterests` (on `/sports` and `/preferences`). Without coalescing
 * these fire as separate identical requests. We share ONE in-flight promise so
 * concurrent consumers hit the network once.
 *
 * Keyed by the resolved auth token so a user switch never reuses the prior user's
 * in-flight promise, and cleared on settle so nothing is cached across loads
 * (a subsequent load — including after logout — always makes a fresh request).
 * Anonymous callers never reach here: `useCategoryInterests` reads localStorage
 * when unauthenticated and never calls this function.
 */
let _inFlightPreferences: {
  token: string | null;
  promise: Promise<UserPreferencesResponse>;
} | null = null;

/**
 * Fetch the current user's preferences and team favorites
 */
export async function fetchUserPreferences(): Promise<UserPreferencesResponse> {
  const token = await getAuthTokenWithTimeout();

  // Reuse an in-flight request only for the SAME auth identity.
  if (_inFlightPreferences && _inFlightPreferences.token === token) {
    return _inFlightPreferences.promise;
  }

  const promise = apiFetch<UserPreferencesResponse>("/api/me/preferences").finally(
    () => {
      // Clear on settle so nothing persists across loads / user switches.
      if (_inFlightPreferences?.promise === promise) {
        _inFlightPreferences = null;
      }
    },
  );
  _inFlightPreferences = { token, promise };
  return promise;
}

/**
 * Update sport affinities
 */
export async function updateSportAffinities(
  affinities: Record<string, number>
): Promise<void> {
  await apiMutate("/api/me/preferences/sport-affinities", "PUT", {
    sport_affinities: affinities,
  });
}
