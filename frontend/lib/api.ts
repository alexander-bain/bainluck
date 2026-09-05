/**
 * API client for Bain Luck backend
 */

import type { EntityAvailability, EntityTier } from "@/lib/entityPageChrome";
import type { TournamentPayload } from "@/lib/tournament";
import type {
  EventsResponse,
  EventDetailResponse,
  EventHistoryResponse,
  SportsResponse,
  LiveOddsResponse,
  FuturesMarketsResponse,
  FuturesMarketDetailResponse,
  FuturesHistoryResponse,
  FuturesMoversResponse,
  SearchResponse,
  SearchSuggestionsResponse,
  EIRankingsResponse,
  RelatedFuturesResponse,
  RelatedEventsResponse,
  FeedResponse,
  TeamSearchResult,
  UserPreferencesResponse,
  OnboardingSubmission,
  FuturesBrowseResponse,
  FuturesCategoriesResponse,
  TeamFuturesResponse,
  SharedTeamFuturesResponse,
  GolfResponse,
  GolfTournamentDetailResponse,
  ProgressionResponse,
  ProbabilityTimelineResponse,
  PlayoffGridResponse,
  MarchMadnessResponse,
  FuturesGroupResponse,
  FuturesGroupsListResponse,
  GroupedFeedResponse,
  ChampionshipGridResponse,
  GolfScheduleResponse,
  TeamProgressionResponse,
  EventTournamentResponse,
  SportHierarchyListResponse,
  SportHierarchy,
  EventConceptResponse,
  Event,
  EventStatus,
  GolfLeaderboardResponse,
  TeamData,
} from "./types";
import { getDiscoverSessionId } from "./discoverInteractions";
import {
  formatProbabilityPercent,
  type ProbabilityFormatOptions,
} from "./probabilityDisplay";
import { reportFeedTelemetry } from "./feedTelemetry";
import { resolveSharedAnonSuppression } from "./discover/sharedAnonFeed";
import {
  FEED_BOOT_CLAIM_TIMEOUT_MS,
  bootDurationMs,
  claimBootFeed,
} from "./discover/feedBoot";
import {
  HUB_BOOT_CLAIM_TIMEOUT_MS,
  claimHubBoot,
  hubBootPath,
} from "./tournament/hubBoot";
import {
  EVENT_BOOT_CLAIM_TIMEOUT_MS,
  EVENT_BOOT_HISTORY_HOURS,
  claimEventBoot,
} from "./event/detailBoot";

/** The API origin. Exported so `feedBoot.ts` builds its boot URL against the
 *  same value this module fetches from, rather than a second copy of the
 *  env-var-plus-fallback expression (LAT-P184). */
export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const AUTH_TOKEN_TIMEOUT_MS = 2500;

/**
 * Auth token getter — set by AuthProvider when user signs in.
 * This avoids a circular dependency between api.ts and useAuth.ts.
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
async function apiFetch<T>(
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
async function apiMutate<T>(
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
 * Fetch list of events with optional filters
 */
export async function fetchEvents(params?: {
  sport?: string;
  status?: string;
  days?: number;
}): Promise<EventsResponse> {
  const searchParams = new URLSearchParams();

  if (params?.sport) searchParams.set("sport", params.sport);
  if (params?.status) searchParams.set("status", params.status);
  if (params?.days) searchParams.set("days", params.days.toString());

  const query = searchParams.toString();
  return apiFetch<EventsResponse>(`/api/events${query ? `?${query}` : ""}`);
}

/**
 * Claim the Event page's parse-time boot for one endpoint (LAT-P219, #2846).
 *
 * Shared by the four fetchers `app/events/[id]/page.tsx` calls before its hero can print an answer.
 * One helper rather than four copies of the race: the only thing that differs between the four call
 * sites is the endpoint string and the response type.
 *
 * Returns `null` for every "no usable boot" case — nothing parked, a different URL, a non-2xx, a
 * rejected fetch, or a boot that never settled — and the caller falls through to `apiFetch`, which
 * keeps its timeout, its retries and its typed errors.
 *
 * RACED, NOT AWAITED. A parked fetch is a bare `fetch()` in a script tag with no timeout and no
 * retries; during a #2724 database spell, awaiting it would strand the reader on a skeleton for as
 * long as the server held the connection, where the normal path would have given up and retried.
 * `hubBoot.ts` documented that hazard first and this is the same deadline for the same reason.
 */
async function claimEventBooted<T>(endpoint: string): Promise<T | null> {
  const booted = claimEventBoot(`${API_URL}${endpoint}`);
  if (!booted?.response) return null;

  const TIMED_OUT = Symbol("event-boot-timeout");
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const res = await Promise.race([
      booted.response,
      new Promise<typeof TIMED_OUT>((resolve) => {
        timer = setTimeout(() => resolve(TIMED_OUT), EVENT_BOOT_CLAIM_TIMEOUT_MS);
      }),
    ]);
    if (res !== TIMED_OUT && res.ok) {
      return (await res.json()) as T;
    }
  } catch {
    /* boot fetch failed — the caller's normal request below is the fallback */
  } finally {
    // `finally`, not a line after the race: a REJECTED boot skips straight to the catch, and a timer
    // left armed there keeps a 20 s handle alive for a request nobody is waiting on.
    if (timer) clearTimeout(timer);
  }
  return null;
}

/**
 * Fetch a single event by ID
 *
 * LAT-P219: on a cold `/events/{id}` load the document may already have this exact request in
 * flight, issued at HTML parse time. `fetchEventsByIds` calls this in a loop and is unaffected — the
 * claim is keyed on the exact URL, so at most the one booted id can match, and only once.
 */
export async function fetchEvent(id: number): Promise<EventDetailResponse> {
  const endpoint = `/api/events/${id}`;
  const booted = await claimEventBooted<EventDetailResponse>(endpoint);
  if (booted) return booted;
  return apiFetch<EventDetailResponse>(endpoint);
}

/**
 * Fetch multiple events by IDs
 * Returns events in the same order as the input IDs, filtering out any that fail to load
 */
export async function fetchEventsByIds(ids: number[]): Promise<EventDetailResponse[]> {
  if (ids.length === 0) return [];

  const results = await Promise.allSettled(ids.map(id => fetchEvent(id)));

  return results
    .filter((r): r is PromiseFulfilledResult<EventDetailResponse> => r.status === 'fulfilled')
    .map(r => r.value);
}

/**
 * Fetch odds history for an event
 */
export async function fetchEventHistory(
  id: number,
  hours = 24
): Promise<EventHistoryResponse> {
  const endpoint = `/api/events/${id}/history?hours=${hours}`;
  // LAT-P219: only the event page's own window (`EVENT_BOOT_HISTORY_HOURS`) is ever parked, so a
  // caller asking for a different `hours` simply finds no matching entry and falls through.
  const booted = await claimEventBooted<EventHistoryResponse>(endpoint);
  if (booted) return booted;
  return apiFetch<EventHistoryResponse>(endpoint);
}

/**
 * Fetch list of supported sports
 */
export async function fetchSports(): Promise<SportsResponse> {
  return apiFetch<SportsResponse>("/api/sports");
}

/**
 * Fetch live odds directly from API (bypasses database)
 */
export async function fetchLiveOdds(sportKey: string): Promise<LiveOddsResponse> {
  return apiFetch<LiveOddsResponse>(`/api/events/live-odds/${sportKey}`);
}

/**
 * Search events by team name or other criteria
 */
export async function searchEvents(params: {
  q: string;
  sport?: string;
  tags?: string[];
  page?: number;
  per_page?: number;
}): Promise<SearchResponse> {
  const searchParams = new URLSearchParams();
  searchParams.set("q", params.q);
  if (params.sport) searchParams.set("sport", params.sport);
  if (params.tags && params.tags.length > 0) searchParams.set("tags", JSON.stringify(params.tags));
  if (params.page) searchParams.set("page", params.page.toString());
  if (params.per_page) searchParams.set("per_page", params.per_page.toString());

  // #239 Item 4: send the Discover session id so the backend search-query log can
  // attribute anonymous searches (mirrors fetchFeed). Signed-in users are already
  // attributed via the Bearer token apiFetch attaches.
  const sessionId = getDiscoverSessionId();
  const headers = sessionId ? { "x-session-id": sessionId } : undefined;
  return apiFetch<SearchResponse>(`/api/events/search?${searchParams.toString()}`, { headers });
}

/**
 * Fetch smart search suggestions for the zero-state search page
 */
export async function fetchSearchSuggestions(): Promise<SearchSuggestionsResponse> {
  return apiFetch<SearchSuggestionsResponse>("/api/events/search-suggestions");
}

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

// Team page
export interface TeamPageTeam {
  id: number;
  slug: string;
  name: string;
  abbreviation: string | null;
  sport_key: string | null;
  sport_name: string | null;
  location: string | null;
  primary_color: string | null;
  secondary_color: string | null;
  logo_small: string | null;
  logo_large: string | null;
  record: string | null;
  standings: Record<string, unknown> | null;
  season_stats: Record<string, unknown> | null;
  roster: Array<{ name: string; headshot?: string; espn_id?: string }> | null;
}

export interface TeamFutureItem {
  outcome_id: number;
  outcome_name: string;
  market_id: number;
  market_name: string;
  market_tier: number | null;
  category: string | null;
  source: string;
  probability: number | null;
  probability_change_24h: number | null;
  rank: number | null;
  total_outcomes: number | null;
  resolution_date: string | null;
  /** L2-174 Item 3d — settled-WON grade (see types.ts TeamFutureItem). */
  is_winner?: boolean | null;
}

export interface ChampionshipPathEntry {
  tier: number;
  label: string;
  market_name: string;
  market_id: number;
  probability: number | null;
  rank: number | null;
  movement: number | null;
  // Season this number describes, e.g. "2026-27" / "2026" (Queue #242 Item 1,
  // backend teams.py::_get_championship_path). Absent/null when the market carries
  // no season and the league has no current-season string.
  season?: string | null;
}

/**
 * Season context descriptor attached to the team-page payload (Queue #242 Item 1,
 * backend `season_windows.season_descriptor`). Declares WHICH season every
 * team-page number describes. `season` is null for continuous/unknown leagues
 * (only NBA/MLB/NFL/NHL carry a season string), in which case chips stay hidden.
 */
export interface SeasonDescriptor {
  league: string | null;
  season: string | null; // e.g. "2026-27"
  phase: string; // e.g. "playoffs" | "regular_season" | "in_season"
  label: string; // e.g. "2026-27 · Playoffs"
}

/**
 * Compact per-game shape returned by the team page endpoint
 * (`backend/app/routes/teams.py::_format_event_brief`). This is intentionally
 * NOT the full `Event` type — the team payload carries only the fields below.
 * `win_probability` is the CURRENT aggregate for the team-in-question's side
 * (home if `is_home`, else away); it is not a pre-game/closing line.
 *
 * L2-158: `pregame_win_probability` / `completed_at` are declared here but NOT
 * yet emitted by the backend (filed gap — see teams.py `_format_event_brief`).
 * The recent-result "we had them at X%" + upset treatment reads them when they
 * land; until then recent cards stay result-first (a settled game's current
 * win_probability is the frozen outcome, not a pre-game expectation).
 */
export interface TeamGameBrief {
  id: number;
  home_team: string;
  away_team: string;
  home_score: number | null;
  away_score: number | null;
  // live/056 — was a fifth inline copy of the status union, and it was the copy
  // that had never heard of `suspended`. `EventStatus`' own docstring exists
  // because three payloads carried three copies; this one was outside that
  // sweep, so the team page could not even TYPE the state its rail now
  // carries. One definition, spent here.
  status: EventStatus;
  commence_time: string | null;
  sport_key: string | null;
  is_home: boolean;
  opponent: string;
  win_probability: number | null; // 0-1, team-relative, current aggregate
  pregame_win_probability?: number | null; // 0-1, team-relative, pre-game/closing (backend gap)
  completed_at?: string | null;
}

export interface TeamPageResponse {
  team: TeamPageTeam;
  // Season context for the whole page (Queue #242 Item 1). Null for leagues
  // without a modeled season string; consumers hide season chips when absent.
  season?: SeasonDescriptor | null;
  upcoming_events: TeamGameBrief[];
  recent_events: TeamGameBrief[];
  futures: TeamFutureItem[];
  championship_path: ChampionshipPathEntry[];
}

export async function fetchTeamPage(identifier: string): Promise<TeamPageResponse> {
  return apiFetch<TeamPageResponse>(`/api/teams/${encodeURIComponent(identifier)}`);
}

// Prop families (#242 backend / L2-167 card): a team's futures/prop markets grouped
// into cohort-compare "families" (Next Team races, award races, threshold ladders).
// Each family carries one row per distinct entity, pre-sorted (settled rows sink
// below live rows; live by probability desc). Only families with >=2 entities are
// returned by the backend.
export interface PropFamilyRow {
  entity: string;
  market_id: number | null;
  outcome_id: number | null;
  probability: number | null; // 0-1
  source: string;
  sources: string[];
  cross_source: Record<string, number | null>;
  group_id: string | null;
  status: string;
  settled: boolean;
  result: "won" | "lost" | null;
  top_outcome: string | null;
  merged_market_ids?: number[];
}

export interface PropFamily {
  family_key: string;
  label: string;
  entity_count: number;
  sources: string[];
  rows: PropFamilyRow[];
}

export interface TeamPropFamiliesResponse {
  team: { id: number; name: string; slug: string | null };
  families: PropFamily[];
  total_families: number;
}

export async function fetchTeamPropFamilies(
  identifier: string,
): Promise<TeamPropFamiliesResponse> {
  return apiFetch<TeamPropFamiliesResponse>(
    `/api/teams/${encodeURIComponent(identifier)}/prop-families`,
  );
}

/**
 * Fetch all-time highest and lowest Excitement Index events
 */
export async function fetchEIRankings(params?: {
  sport?: string;
  limit?: number;
}): Promise<EIRankingsResponse> {
  const searchParams = new URLSearchParams();

  if (params?.sport) searchParams.set("sport", params.sport);
  if (params?.limit) searchParams.set("limit", params.limit.toString());

  const query = searchParams.toString();
  return apiFetch<EIRankingsResponse>(`/api/events/ei-rankings${query ? `?${query}` : ""}`);
}

/** @deprecated Use fetchEIRankings instead */
export const fetchPulseRankings = fetchEIRankings;

/**
 * Format probability as percentage string
 */
export async function fetchEventConcept(key: string): Promise<EventConceptResponse> {
  return apiFetch<EventConceptResponse>(`/api/event/${encodeURIComponent(key)}`);
}

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

/**
 * For live games, returns the best available probability by checking model sources
 * (ESPN, stat model) against betting odds. When models significantly diverge from
 * stale betting odds (>15%), the model probability is used instead.
 *
 * For non-live games, always returns betting odds.
 */
export interface BestProbability {
  homeProb: number | null;
  awayProb: number | null;
  /** Whether we're using betting odds or a model source */
  source: "betting" | "model";
  /** Display name of the source when using a model (e.g., "ESPN") */
  sourceName: string | null;
}

export function getBestProbability(event: {
  status: string;
  current_odds?: { home_probability: number | null; away_probability: number | null } | null;
  win_probability_sources?: Record<string, { value: number; display_name: string; type: string; color: string }> | null;
}): BestProbability {
  const bettingHome = event.current_odds?.home_probability ?? null;
  const bettingAway = event.current_odds?.away_probability ?? null;

  // For non-live games, always use betting odds
  if (event.status !== "live") {
    return { homeProb: bettingHome, awayProb: bettingAway, source: "betting", sourceName: null };
  }

  // For live games, check model sources
  const sources = event.win_probability_sources;
  if (!sources) {
    return { homeProb: bettingHome, awayProb: bettingAway, source: "betting", sourceName: null };
  }

  // Prefer ESPN (gold standard during live games), then stat model
  const modelEntry = sources.espn || sources.stat_model;
  if (!modelEntry || modelEntry.value === undefined || modelEntry.value === null) {
    return { homeProb: bettingHome, awayProb: bettingAway, source: "betting", sourceName: null };
  }

  const modelHome = modelEntry.value;

  // If model and betting odds diverge significantly (>15%), betting odds are stale
  if (bettingHome !== null && Math.abs(modelHome - bettingHome) > 0.15) {
    return {
      homeProb: modelHome,
      awayProb: 1 - modelHome,
      source: "model",
      sourceName: modelEntry.display_name,
    };
  }

  // Betting odds are fresh enough, use them
  return { homeProb: bettingHome, awayProb: bettingAway, source: "betting", sourceName: null };
}

// L2-48: formatMoneyline removed — the no-odds thesis is categorical (probability
// only, never "-150/+130"). Do not reintroduce an American-odds formatter.

/**
 * Format date for display
 */
export function formatGameTime(isoString: string): string {
  const date = new Date(isoString);
  return date.toLocaleString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/**
 * Check if a game is starting soon (within 1 hour)
 */
export function isStartingSoon(isoString: string): boolean {
  const gameTime = new Date(isoString);
  const now = new Date();
  const diff = gameTime.getTime() - now.getTime();
  return diff > 0 && diff < 60 * 60 * 1000; // Within 1 hour
}

// ============================================================================
// Futures/Outrights API
// ============================================================================

/**
 * Fetch list of futures markets with optional filters
 */
export async function fetchFuturesMarkets(params?: {
  sport?: string;
  status?: string;
  limit?: number;
}): Promise<FuturesMarketsResponse> {
  const searchParams = new URLSearchParams();

  if (params?.sport) searchParams.set("sport", params.sport);
  if (params?.status) searchParams.set("status", params.status);
  if (params?.limit) searchParams.set("limit", params.limit.toString());

  const query = searchParams.toString();
  return apiFetch<FuturesMarketsResponse>(`/api/futures${query ? `?${query}` : ""}`);
}

/**
 * Fetch a single futures market by ID
 */
export async function fetchFuturesMarket(id: number): Promise<FuturesMarketDetailResponse> {
  return apiFetch<FuturesMarketDetailResponse>(`/api/futures/${id}`);
}

/**
 * Fetch a futures market group (cross-source comparison + threshold variants)
 */
export async function fetchFuturesGroup(groupId: string): Promise<FuturesGroupResponse> {
  return apiFetch<FuturesGroupResponse>(
    `/api/futures/groups/${encodeURIComponent(groupId)}`
  );
}

/**
 * List all market groups (multi-source and threshold groups)
 */
export async function fetchFuturesGroups(opts?: {
  source?: string;
  group_type?: string;
  sport?: string;
  limit?: number;
  offset?: number;
}): Promise<FuturesGroupsListResponse> {
  const params = new URLSearchParams();
  if (opts?.source) params.set("source", opts.source);
  if (opts?.group_type) params.set("group_type", opts.group_type);
  if (opts?.sport) params.set("sport", opts.sport);
  if (opts?.limit) params.set("limit", String(opts.limit));
  if (opts?.offset) params.set("offset", String(opts.offset));
  const qs = params.toString();
  return apiFetch<FuturesGroupsListResponse>(`/api/futures/groups${qs ? `?${qs}` : ""}`);
}

/**
 * Fetch grouped futures feed for display.
 *
 * Returns markets intelligently grouped into stat props, playoff progressions,
 * threshold variants, and ungrouped markets - ready for rendering with the
 * appropriate card components.
 */
export async function fetchGroupedFeed(opts?: {
  category?: string;
  sport?: string;
  sportsOnly?: boolean;
  limit?: number;
}): Promise<GroupedFeedResponse> {
  const params = new URLSearchParams();
  if (opts?.category) params.set("category", opts.category);
  if (opts?.sport) params.set("sport", opts.sport);
  if (opts?.sportsOnly) params.set("sports_only", "true");
  if (opts?.limit) params.set("limit", String(opts.limit));
  const qs = params.toString();
  return apiFetch<GroupedFeedResponse>(`/api/futures/grouped-feed${qs ? `?${qs}` : ""}`);
}

/**
 * Fetch multiple futures markets by IDs
 * Returns markets in the same order as the input IDs, filtering out any that fail to load
 */
export async function fetchFuturesByIds(ids: number[]): Promise<FuturesMarketDetailResponse[]> {
  if (ids.length === 0) return [];

  const results = await Promise.allSettled(ids.map(id => fetchFuturesMarket(id)));

  return results
    .filter((r): r is PromiseFulfilledResult<FuturesMarketDetailResponse> => r.status === 'fulfilled')
    .map(r => r.value);
}

/**
 * Fetch odds history for a futures market
 */
export async function fetchFuturesHistory(
  marketId: number,
  hours = 168,
  outcomeId?: number,
  topN?: number,
  champion?: string
): Promise<FuturesHistoryResponse> {
  const params = new URLSearchParams();
  params.set("hours", hours.toString());
  if (outcomeId) params.set("outcome_id", outcomeId.toString());
  if (topN) params.set("top_n", topN.toString());
  // #232: settled winner-field champion name so /history resolves the winner's
  // evolution line to 1.0 (odds_api winner fields never carry an is_winner grade).
  if (champion) params.set("champion", champion);

  return apiFetch<FuturesHistoryResponse>(
    `/api/futures/${marketId}/history?${params.toString()}`
  );
}

/**
 * Fetch aggregated odds history across multiple markets (cross-source).
 * Falls back to single-market history if only one ID is provided.
 */
export async function fetchMultiMarketHistory(
  marketIds: number[],
  hours = 168,
  topN?: number
): Promise<FuturesHistoryResponse> {
  if (marketIds.length === 1) {
    return fetchFuturesHistory(marketIds[0], hours, undefined, topN);
  }
  const params = new URLSearchParams();
  params.set("market_ids", marketIds.join(","));
  params.set("hours", hours.toString());
  if (topN) params.set("top_n", topN.toString());

  return apiFetch<FuturesHistoryResponse>(
    `/api/futures/multi-history?${params.toString()}`
  );
}

/**
 * Fetch futures movers (biggest probability changes)
 */
export async function fetchFuturesMovers(
  hours = 24,
  limit = 20
): Promise<FuturesMoversResponse> {
  return apiFetch<FuturesMoversResponse>(
    `/api/futures/movers?hours=${hours}&limit=${limit}`
  );
}

/**
 * Fetch tournament progression table for a futures market.
 * Cross-references sibling markets at different stages.
 */
export async function fetchProgression(
  marketId: number,
  topN?: number,
  golfCardReceipt?: string | null
): Promise<ProgressionResponse> {
  const query = new URLSearchParams();
  if (topN) query.set("top_n", String(topN));
  // UX-P271: name the golf card snapshot on screen so the Win column binds to it
  // rather than to whatever the server's cache holds at request time.
  if (golfCardReceipt) query.set("golf_card_receipt", golfCardReceipt);
  const params = query.toString();
  return apiFetch<ProgressionResponse>(
    `/api/futures/${marketId}/progression${params ? `?${params}` : ""}`
  );
}

/**
 * Fetch probability timeline for a futures market.
 * Returns time-bucketed median probabilities per outcome for multi-line charts.
 */
export async function fetchProbabilityTimeline(
  marketId: number,
  top?: number,
  hours?: number
): Promise<ProbabilityTimelineResponse> {
  const params = new URLSearchParams();
  if (top !== undefined) params.set("top", String(top));
  if (hours !== undefined) params.set("hours", String(hours));
  const qs = params.toString();
  return apiFetch<ProbabilityTimelineResponse>(
    `/api/futures/${marketId}/probability-timeline${qs ? `?${qs}` : ""}`
  );
}

/**
 * Fetch cross-source merged probability timeline for markets sharing a canonical key.
 * Returns averaged probabilities across sources in the same shape as fetchProbabilityTimeline.
 */
export async function fetchCrossSourceTimeline(
  canonicalKey: string,
  top?: number,
  hours?: number
): Promise<ProbabilityTimelineResponse> {
  const params = new URLSearchParams();
  params.set("canonical_key", canonicalKey);
  if (top !== undefined) params.set("top", String(top));
  if (hours !== undefined) params.set("hours", String(hours));
  return apiFetch<ProbabilityTimelineResponse>(
    `/api/futures/cross-source-timeline?${params.toString()}`
  );
}

/**
 * Fetch related futures for an event (team-linked championship/award markets)
 */
export async function fetchRelatedFutures(
  eventId: number
): Promise<RelatedFuturesResponse> {
  return apiFetch<RelatedFuturesResponse>(
    `/api/events/${eventId}/related-futures`
  );
}

/**
 * Fetch game-level markets for an event (totals spectrum, player props, spreads)
 */
export interface GameMarketsResponse {
  event_id: number;
  home_team: string;
  away_team: string;
  home_score: number | null;
  away_score: number | null;
  status: string;
  totals: {
    threshold: number;
    over_probability: number;
    source: string;
    market_type: string;
    market_name: string;
    outcome_name: string;
    movement: number | null;
    bookmaker_count?: number;
  }[];
  player_props: {
    market_name: string;
    outcome_name: string;
    threshold: number | null;
    over_probability: number;
    source: string;
    movement: number | null;
    player_headshot?: string;
    player_team?: "home" | "away";
    // Queue #190 Item 3: server-side settled grading (present only when the
    // event is completed/closed). actual = box-score stat value, hit = graded
    // result respecting over/under direction.
    actual?: number | null;
    hit?: boolean | null;
    is_winner?: boolean | null;
    resolution_source?: string | null;
    // #195: THE SCRIPT baseline (pregame mark as over-probability) + the opening
    // line it falls back to before the commence-time mark is pinned.
    pregame_mark?: number | null;
    opening_over_probability?: number | null;
  }[];
  team_totals: {
    threshold: number;
    over_probability: number;
    source: string;
    market_type: string;
    market_name: string;
    outcome_name: string;
    movement: number | null;
  }[];
  spreads: {
    market_name: string;
    outcome_name: string;
    threshold: number | null;
    probability: number | null;
    source: string;
  }[];
  period_markets: {
    market_name: string;
    outcome_name: string;
    threshold: number | null;
    probability: number | null;
    source: string;
    market_type: string;
    over_probability?: number;
    movement?: number | null;
    period?: string | null;
  }[];
  matchups: {
    market_name: string;
    type: "h2h" | "3ball";
    source: string;
    outcomes: {
      name: string;
      probability: number;
    }[];
  }[];
  other: {
    market_name: string;
    outcome_name: string;
    probability: number | null;
    source: string;
  }[];
  pace: {
    total_scored: number;
    projected_total: number | null;
    fraction_elapsed: number;
    time_remaining_display: string;
  } | null;
  // #195: THE SCRIPT → THE DIVERGENCE → WHAT HIT payload consumed by
  // components/event/PropsSection.tsx (PropMark contract). Present (possibly
  // empty) on every game-markets response; each row is a graded/priced prop.
  props_script?: {
    key: string;
    label: string;
    pregame_mark: number | null;
    current: number | null;
    graded_result?: "hit" | "miss" | "push" | null;
    graded_label?: string | null;
  }[];
}

export async function fetchGameMarkets(
  eventId: number
): Promise<GameMarketsResponse> {
  const endpoint = `/api/events/${eventId}/game-markets`;
  const booted = await claimEventBooted<GameMarketsResponse>(endpoint);
  if (booted) return booted;
  return apiFetch<GameMarketsResponse>(endpoint);
}

/**
 * Fetch related events for a futures market (upcoming/recent games featuring contender teams)
 */
export async function fetchRelatedEvents(
  marketId: number
): Promise<RelatedEventsResponse> {
  return apiFetch<RelatedEventsResponse>(
    `/api/futures/${marketId}/related-events`
  );
}

/**
 * Fetch team championship progression for an event's teams
 */
export async function fetchTeamProgression(eventId: number): Promise<TeamProgressionResponse> {
  const endpoint = `/api/events/${eventId}/team-progression`;
  const booted = await claimEventBooted<TeamProgressionResponse>(endpoint);
  if (booted) return booted;
  return apiFetch<TeamProgressionResponse>(endpoint);
}

/**
 * Fetch line movement analysis and AI explanations for an event
 */
export async function fetchLineMovement(eventId: number): Promise<LineMovementResponse> {
  return apiFetch<LineMovementResponse>(
    `/api/events/${eventId}/line-movement`
  );
}

export interface LineMovementResponse {
  event_id: number;
  movements: LineMovement[];
  explanation: string | null;
  disagreement_explanation: string | null;
  disagreement_data: {
    sportsbook_home_prob: number;
    prediction_market_home_prob: number;
    source: string;
    divergence: number;
  } | null;
  context: {
    injuries_count: number;
    news_count: number;
    has_game_state: boolean;
  } | null;
  cached: boolean;
  created_at: string;
}

export interface LineMovement {
  timestamp_start: string;
  timestamp_end: string;
  home_prob_before: number;
  home_prob_after: number;
  change: number;
  magnitude: number;
  direction: string;
  context: string;
  is_major: boolean;
}

// L2-48: formatAmericanOdds removed — the no-odds thesis is categorical
// (probability only). Do not reintroduce an American-odds formatter.

// ============================================================================
// Unified Feed API
// ============================================================================

/**
 * Fetch the unified feed of interesting events and futures
 */
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
  //
  // LAT-P218: THE CLAIM IS RACED AGAINST A DEADLINE. It used to `await` the parked promise bare. A
  // parked fetch is a naked `fetch()` in a script tag — no timeout, no retries — whereas `apiFetch`
  // has both (20 s per attempt, two retries). So during a #2724 database spell a bare await stranded
  // the reader on a skeleton for as long as the server held the connection, while the un-booted path
  // would have given up and retried. `hubBoot.ts` documented that hazard and raced its own claim;
  // this one did not, and LAT-P218 puts the Sports tab on this same claim, so the exposure now spans
  // two of the three highest-traffic surfaces. The deadline matches `apiFetch`'s own per-attempt
  // timeout, so the worst case is one extra attempt's wait rather than an unbounded one.
  if (suppressSessionId && !headers) {
    const booted = claimBootFeed(`${API_URL}${endpoint}`);
    if (booted?.response) {
      const TIMED_OUT = Symbol("feed-boot-timeout");
      let timer: ReturnType<typeof setTimeout> | undefined;
      try {
        const res = await Promise.race([
          booted.response,
          new Promise<typeof TIMED_OUT>((resolve) => {
            timer = setTimeout(() => resolve(TIMED_OUT), FEED_BOOT_CLAIM_TIMEOUT_MS);
          }),
        ]);
        if (res !== TIMED_OUT && res.ok) {
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
      } finally {
        if (timer) clearTimeout(timer);
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

// ============================================================================
// Tag Counts API (for category pages)
// ============================================================================

export interface TagCountsResponse {
  counts: Record<string, { events: number; futures: number }>;
}

/**
 * Fetch item counts grouped by sport tag.
 * Powers the category index grid showing "12 events, 5 futures" per category.
 */
export async function fetchTagCounts(): Promise<TagCountsResponse> {
  return apiFetch<TagCountsResponse>("/api/feed/tag-counts");
}

// ============================================================================
// Market Was Wrong API
// ============================================================================

export interface MarketMovesItem {
  type: "upset" | "market_error" | "futures_mover";
  score: number;
  description: string;
  // Event upset / market error fields
  event_id?: number;
  sport?: string;
  sport_name?: string;
  home_team?: string;
  away_team?: string;
  home_score?: number;
  away_score?: number;
  winner?: string;
  loser?: string;
  winner_score?: number;
  loser_score?: number;
  winner_opening_prob?: number;
  loser_opening_prob?: number;
  market_error?: number;
  is_upset?: boolean;
  commence_time?: string;
  // Futures mover fields
  market_id?: number;
  market_name?: string;
  market_tier?: number;
  llm_sport_category?: string;
  outcome_name?: string;
  current_probability?: number;
  change_24h?: number;
  direction?: string;
}

export interface MarketMovesResponse {
  items: MarketMovesItem[];
  total: number;
  hours: number;
  generated_at: string;
}

/**
 * Fetch 'The Market Was Wrong' — recent upsets and big market surprises
 */
export async function fetchMarketMoves(params?: {
  hours?: number;
  limit?: number;
}): Promise<MarketMovesResponse> {
  const searchParams = new URLSearchParams();
  if (params?.hours) searchParams.set("hours", params.hours.toString());
  if (params?.limit) searchParams.set("limit", params.limit.toString());
  const query = searchParams.toString();
  return apiFetch<MarketMovesResponse>(`/api/market-moves${query ? `?${query}` : ""}`);
}

// ============================================================================
// User & Pins API (authenticated endpoints)
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
 * Bulk sync pins to the server (used for localStorage migration on first login)
 */
export async function syncPins(pins: {
  events: number[];
  futures: number[];
}): Promise<PinsResponse> {
  return apiMutate<PinsResponse>("/api/me/pins", "PUT", pins);
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

// ============================================================================
// Onboarding & Preferences API
// ============================================================================

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
 * Submit complete onboarding data (location, teams, sport affinities).
 * Accepts an optional direct token to ensure the freshest auth token is used.
 */
export async function submitOnboarding(
  data: OnboardingSubmission,
  directToken?: string | null,
): Promise<{ status: string; onboarding_completed: boolean }> {
  return apiMutate("/api/me/onboarding", "POST", data, directToken);
}

/**
 * Search teams by name for autocomplete
 */
export async function searchTeams(q: string): Promise<TeamSearchResult[]> {
  if (q.length < 2) return [];
  return apiFetch<TeamSearchResult[]>(
    `/api/me/teams/search?q=${encodeURIComponent(q)}`
  );
}

/**
 * Find teams by location/city with metro alias expansion
 */
export async function searchTeamsByLocation(
  q: string
): Promise<TeamSearchResult[]> {
  if (q.length < 2) return [];
  return apiFetch<TeamSearchResult[]>(
    `/api/me/teams/by-location?q=${encodeURIComponent(q)}`
  );
}

// ============================================================================
// Favorites CRUD (inline editing from preferences page)
// ============================================================================

/**
 * Add a single team favorite
 */
export async function addFavorite(
  teamId: number,
  relationType: string
): Promise<void> {
  await apiMutate("/api/me/favorites", "POST", {
    team_id: teamId,
    relation_type: relationType,
  });
}

/**
 * Remove a single team favorite
 */
export async function removeFavorite(
  teamId: number,
  relationType: string
): Promise<void> {
  await apiMutate(
    `/api/me/favorites/${teamId}?relation_type=${encodeURIComponent(relationType)}`,
    "DELETE"
  );
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

// ============================================================================
// Golf API
// ============================================================================

/**
 * Fetch sport hierarchy — all sports with leagues and showcase events
 */
export async function fetchSportHierarchy(): Promise<SportHierarchyListResponse> {
  return apiFetch<SportHierarchyListResponse>("/api/sports/hierarchy");
}

/**
 * Fetch hierarchy for a single sport — leagues + showcase events
 */
export async function fetchSportHierarchyDetail(sportSlug: string): Promise<SportHierarchy> {
  return apiFetch<SportHierarchy>(`/api/sports/hierarchy/${encodeURIComponent(sportSlug)}`);
}

/**
 * Fetch Golf landing page data — all tournaments with aggregated odds
 */
export async function fetchGolfData(
  rebindToken?: string | null
): Promise<GolfResponse> {
  // UX-P271: this response is served `public, max-age=300,
  // stale-while-revalidate=60`, so a plain re-request can be answered from the
  // HTTP cache with the very card the progression endpoint just told us it could
  // not bind to. Varying the URL varies the cache key, which is what actually
  // reaches the origin — a request header would not, since the stale entry is
  // already storable and reusable.
  const suffix = rebindToken
    ? `?rebind=${encodeURIComponent(rebindToken)}`
    : "";
  return apiFetch<GolfResponse>(`/api/golf${suffix}`);
}

/**
 * Fetch Golf tournament detail — markets grouped by type for a single tournament
 */
export async function fetchGolfTournament(slug: string): Promise<GolfTournamentDetailResponse> {
  return apiFetch<GolfTournamentDetailResponse>(`/api/golf/tournaments/${encodeURIComponent(slug)}`);
}

/**
 * Fetch live golf leaderboard from DataGolf
 */
export async function fetchGolfLeaderboard(tour: string = "pga"): Promise<GolfLeaderboardResponse> {
  return apiFetch<GolfLeaderboardResponse>(`/api/golf/leaderboard?tour=${encodeURIComponent(tour)}`);
}

// ============================================================================
// March Madness API
// ============================================================================

export async function fetchMarchMadness(type: 'mens' | 'womens'): Promise<MarchMadnessResponse> {
  return apiFetch<MarchMadnessResponse>(`/api/march-madness/${type}`);
}

// ============================================================================
// Futures Browse API (Search tab category browsing)
// ============================================================================

/**
 * Browse futures markets by category with pagination.
 * Used by the Search tab for lazy-loading category sections.
 */
export async function fetchFuturesBrowse(params: {
  category?: string;
  q?: string;
  limit?: number;
  offset?: number;
}): Promise<FuturesBrowseResponse> {
  const searchParams = new URLSearchParams();
  if (params.category) searchParams.set("category", params.category);
  if (params.q) searchParams.set("q", params.q);
  if (params.limit) searchParams.set("limit", params.limit.toString());
  if (params.offset) searchParams.set("offset", params.offset.toString());

  const query = searchParams.toString();
  return apiFetch<FuturesBrowseResponse>(`/api/futures/browse${query ? `?${query}` : ""}`);
}

/**
 * Fetch lightweight category counts for the Search tab grid.
 */
export async function fetchFuturesCategories(): Promise<FuturesCategoriesResponse> {
  return apiFetch<FuturesCategoriesResponse>("/api/futures/categories");
}

// ============================================================================
// Team Futures API (My Stuff → "Your Teams' Odds")
// ============================================================================

/**
 * Fetch futures outcomes for the current user's followed teams.
 * Requires auth.
 */
export async function fetchMyTeamFutures(
  limit?: number
): Promise<TeamFuturesResponse> {
  const params = new URLSearchParams();
  if (limit) params.set("limit", limit.toString());
  const query = params.toString();
  return apiFetch<TeamFuturesResponse>(
    `/api/me/team-futures${query ? `?${query}` : ""}`
  );
}

/**
 * Fetch league-wide playoff progression grid.
 * Cross-source merged probabilities for each team at each playoff round.
 */
export async function fetchPlayoffGrid(
  sport: string,
  league?: string,
  season?: string,
  topN?: number
): Promise<PlayoffGridResponse> {
  const params = new URLSearchParams();
  params.set("sport", sport);
  if (league) params.set("league", league);
  if (season) params.set("season", season);
  if (topN) params.set("top_n", String(topN));
  return apiFetch<PlayoffGridResponse>(
    `/api/futures/playoff-grid?${params.toString()}`
  );
}

/**
 * Fetch championship progression grid for a league.
 * New endpoint: GET /api/playoffs/{league_slug}
 */
export async function fetchChampionshipGrid(
  leagueSlug: string,
  top?: number
): Promise<ChampionshipGridResponse> {
  const params = new URLSearchParams();
  if (top) params.set("top", String(top));
  const query = params.toString();
  return apiFetch<ChampionshipGridResponse>(
    `/api/playoffs/${leagueSlug}${query ? `?${query}` : ""}`
  );
}

/**
 * Fetch all open futures markets for a league, grouped by section.
 */
export interface LeagueMarketOutcome {
  id: number;
  name: string;
  probability: number | null;
  opening_probability: number | null;
  rank: number | null;
  movement_24h: number | null;
  team_id: number | null;
}

export interface LeagueMarket {
  id: number;
  name: string;
  source: string;
  external_id?: string | null;
  market_tier: number | null;
  category: string;
  resolution_date: string | null;
  outcome_count: number;
  top_outcomes: LeagueMarketOutcome[];
  canonical_market_key: string | null;
  section: string;
  /** Set on hub props that were reclassified out of "matches" (e.g. MMA). */
  prop_type?: string;
}

/**
 * One game on a league rail (UX-P062 / #1743, Alex's 2026-08-11 amendment).
 *
 * Served by `/api/leagues/{sport_key}` rather than fetched separately, because the
 * TIER is declared by that route and a census counting content the page sourced
 * elsewhere can silently diverge from what the reader sees.
 */
export interface LeagueGameBrief {
  id: number;
  home_team: string;
  away_team: string;
  commence_time: string | null;
  status: string;
  home_score: number | null;
  away_score: number | null;
  /** Null when we never measured one — render nothing, never a 0% claim. */
  home_win_probability: number | null;
  // ── UX-P074 (#1860), ruling 047 ──
  // The rail renders the SHARED event card, so the envelope carries what that
  // card draws. These use the SAME key names `/api/events` uses, because a
  // second name for the same field is a second thing to learn and a second
  // thing to get wrong. All optional: an older cached payload (the league
  // mirror lives up to 24h) still renders, just without the chrome.
  external_id?: string | null;
  sport?: string | null;
  completed_at?: string | null;
  current_odds?: { home_probability: number | null; away_probability: number | null };
  opening_odds?: { home_probability: number; away_probability: number };
  home_team_data?: TeamData;
  away_team_data?: TeamData;
  espn?: { period?: string; game_clock?: string; broadcast?: string };
}

export interface LeagueFuturesResponse {
  sport_key: string;
  sections: Record<string, LeagueMarket[]>;
  total_markets: number;
  // UX-P062 (#1743, epic #1741) — the same entity envelope the hub carries
  // (spec §7). `tier` is DECLARED and rendered, never inferred (ruling 021).
  tier?: EntityTier | null;
  availability?: EntityAvailability;
  pool_counts?: { answers: number; dropped: number; settled: number };
  section_counts?: Record<
    string,
    { total: number; shown: number; dropped: number; answers: number }
  >;
  // Alex's amendment: games are the league page's freshest content, and the tier
  // census counts them. `has_more` declares the cap rather than applying it
  // silently (spec §4 — an uncounted cap reads as coverage).
  upcoming_games?: LeagueGameBrief[];
  upcoming_games_has_more?: boolean;
  recent_results?: LeagueGameBrief[];
  recent_results_has_more?: boolean;
  /**
   * Matches whose kickoff has passed while the row still says `scheduled` —
   * #3211. Its OWN rail rather than part of `recent_results`, and the reason is
   * measured: these rows are stamped midnight of the current day (gotcha #14),
   * so on a `commence_time DESC LIMIT 8` rail they sort above every Final and
   * took all eight slots, pushing the league's actual results off the page.
   */
  unreported_games?: LeagueGameBrief[];
  unreported_games_has_more?: boolean;
  /** Settled games behind "The record" — spec §5.3. Deliberately excludes
   *  `unreported_games`: a match nobody reported is not a receipt. */
  record_n?: number;
}

export async function fetchLeagueMarkets(sportKey: string): Promise<LeagueFuturesResponse> {
  return apiFetch<LeagueFuturesResponse>(`/api/leagues/${sportKey}`);
}

// ---------------------------------------------------------------------------
// Competition Hub (B1 / #1028) — GET /api/hub/{competition}
// ---------------------------------------------------------------------------

/** An upcoming event/card in the hub rail (links to /event/{key}). */
export interface HubUpcoming {
  key: string;
  name: string;
  domain: string;
  // `unknown` is a first-class value, not a gap: the tennis rail has no
  // trustworthy start signal, so it declares the phase unknown rather than
  // guessing one (UX-P209 / CERT-519). `HubStatusPill` withholds the label for
  // it — see that file for why the open `| string` arm must stay silent too.
  status: "upcoming" | "live" | "settled" | "unknown" | string;
  start_date: string | null;
  is_major: boolean;
  fight_count?: number | null;
}

export interface HubResponse {
  competition: string;
  label: string;
  title: string;
  emoji: string;
  blurb: string;
  sport_key: string;
  // UX-P167 (#2167) — the section heading vocabulary, declared per competition.
  //
  // Sport-SPECIFIC words only: the combat hubs send
  // `{matches: "Fight Markets", props: "Fight Props", season_stats: "Fighter
  // Stats"}` and golf/tennis/esports send `{}`. The client holds the neutral
  // default for every key, so an absent field (an older cached payload — the hub
  // mirror lives up to 24h) reads plain and true rather than reading like
  // another sport. Optional for exactly that reason.
  section_labels?: Record<string, string>;
  /** Heading over the `upcoming` rail — "Upcoming Cards" for combat, "Upcoming Tournaments" for golf/tennis. */
  upcoming_label?: string;
  /**
   * The same heading with no phase claim in it — "Cards", "Tournaments".
   *
   * UX-P210 (CERT-525): "Upcoming Tournaments" is a claim about every card on
   * the rail, and the listers admit `live` and (for tennis) `unknown` cards
   * beside the upcoming ones. `lib/hubUpcomingHeading.ts` picks between the two
   * words against the cards actually rendered. Optional for the same reason
   * `section_labels` is: a payload cached before this shipped carries no twin,
   * and the rail then prints no heading rather than the affirmative one.
   */
  upcoming_label_neutral?: string;
  upcoming: HubUpcoming[];
  sections: Record<string, LeagueMarket[]>;
  total_markets: number;
  // UX-P061 (#1742, epic #1741) — the entity envelope, spec §7.
  //
  // `tier` is DECLARED by the backend and rendered, never inferred (ruling 021):
  // the moment web and SwiftUI each count arrays to pick a layout, the same
  // competition renders as a map on one and an answer on the other, and the
  // parity bug is unfindable because both clients are "correct".
  tier?: EntityTier | null;
  // Ruling 025's conforming vocabulary. Distinct from the legacy
  // `cache.availability` (`live|stale_ok|unavailable`), which stays where it is.
  availability?: EntityAvailability;
  // Every count the page renders arrives IN the payload; clients never derive
  // shown/total by measuring arrays.
  pool_counts?: { answers: number; dropped: number; settled: number };
  section_counts?: Record<
    string,
    { total: number; shown: number; dropped: number; answers: number }
  >;
}

export async function fetchHub(competition: string): Promise<HubResponse> {
  return apiFetch<HubResponse>(`/api/hub/${encodeURIComponent(competition)}`);
}

/**
 * Fetch golf season schedule from DataGolf across all tours.
 */
export async function fetchGolfSchedule(): Promise<GolfScheduleResponse> {
  return apiFetch<GolfScheduleResponse>("/api/playoffs/golf/schedule");
}

/**
 * Fetch futures outcomes for specified teams (public, no auth).
 * Used for share links.
 */
export async function fetchSharedTeamFutures(
  teamIds: number[],
  limit?: number
): Promise<SharedTeamFuturesResponse> {
  const params = new URLSearchParams();
  params.set("team_ids", teamIds.join(","));
  if (limit) params.set("limit", limit.toString());
  return apiFetch<SharedTeamFuturesResponse>(
    `/api/shared/team-futures?${params.toString()}`
  );
}

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

export interface EconMarketRow {
  q: string;
  prob: number;
  src: string;
  delta: number | null;
  market_id: number;
}

export interface EconThemeFed {
  count: number;
  fomc_meetings: { date: string; mo: string; dist: number[][]; resolved: boolean; market_id: number }[];
  rate_cuts: number[][];
  side_markets: EconMarketRow[];
}

export interface EconThemeInflation {
  count: number;
  cpi_releases: { mo: string; brackets: number[][]; upcoming: boolean; peakIs: number; market_id: number }[];
  side_markets: EconMarketRow[];
}

export interface EconThemeRecession {
  count: number;
  main_prob: number | null;
  /**
   * The question `main_prob` answers, straight off the selected market
   * (UX-P273 / #2674). The card renders this rather than a hardcoded label,
   * so the question and the number cannot describe different markets.
   */
  main_q: string | null;
  main_market_id: number | null;
  gdp_quarters: { q: string; dist: number[][]; market_id: number }[];
  side_markets: EconMarketRow[];
}

export interface EconThemeMarkets {
  count: number;
  today: { sym: string; prob: number; dir: string; range: string; src: string }[];
  stocks: { sym: string; prob: number; delta: number | null; src: string }[];
  side_markets: EconMarketRow[];
}

export interface EconThemeEnergy {
  count: number;
  gas: { label: string; val: string; prob: number; brackets: number[][]; src: string }[];
  oil: { sym?: string; prob: number; range?: string; src: string; q?: string }[];
}

export interface EconThemeSimple {
  count: number;
  markets: EconMarketRow[];
}

/** A multi-outcome market too wide for a Market row.
 *  `kind: "ladder"` rows are independent cumulative thresholds and legitimately
 *  sum over 100%; `kind: "brackets"` rows are a normalized partition. */
export interface EconDistribution {
  q: string;
  kind: "ladder" | "brackets";
  rows: [number, string][];
  src: string;
  market_id: number;
}

export interface EconThemeGovernment extends EconThemeSimple {
  distributions: EconDistribution[];
}

export interface EconThemeHousing {
  count: number;
  mortgage_brackets: number[][];
  markets: EconMarketRow[];
}

export interface EconData {
  total_markets: number;
  updated_at: string;
  themes: {
    fed: EconThemeFed;
    inflation: EconThemeInflation;
    jobs: EconThemeSimple;
    recession: EconThemeRecession;
    markets: EconThemeMarkets;
    energy: EconThemeEnergy;
    housing: EconThemeHousing;
    trade: EconThemeSimple;
    government: EconThemeGovernment;
  };
  by_source: { kalshi: number; polymarket: number };
}

export async function fetchEconomics(): Promise<EconData> {
  return apiFetch<EconData>("/api/economics");
}

export interface PoliticsMarketRow {
  q: string;
  prob: number;
  src: string;
  market_id: number;
  top_outcomes: { name: string; prob: number }[];
  outcome_count: number;
}

export interface PoliticsCandidate {
  name: string;
  party: "R" | "D" | "I";
  kalshi: number | null;
  poly: number | null;
  merged: number;
  change_7d: number | null;
  history: { t: string; p: number }[];
}

export interface PoliticsThemePresidential {
  count: number;
  headline_q: string | null;
  candidates: PoliticsCandidate[];
  has_dual_source: boolean;
  kalshi_market_id: number | null;
  poly_market_id: number | null;
  side_markets: PoliticsMarketRow[];
}

export interface ChamberControl {
  gop: number;
  dem: number;
  market_id: number;
}

export interface PoliticsThemeCongressional {
  count: number;
  markets: PoliticsMarketRow[];
  chamber_control: {
    senate: ChamberControl | null;
    house: ChamberControl | null;
  };
  senate_map: Record<string, number> | null;
}

export interface PoliticsThemeSimple {
  count: number;
  markets: PoliticsMarketRow[];
}

export interface CrossSourceMatch {
  q: string;
  /** The single outcome both `kalshi` and `poly` price. Optional only because
   *  /api/politics is served from an hourly precompute: for up to an hour
   *  after a deploy the cached body predates the field. */
  outcome?: string;
  kalshi: number;
  poly: number;
  delta: number;
  category: string;
  kalshi_market_id: number;
  poly_market_id: number;
}

export interface PoliticsData {
  total_markets: number;
  updated_at: string;
  themes: {
    presidential: PoliticsThemePresidential;
    congressional: PoliticsThemeCongressional;
    gubernatorial: PoliticsThemeSimple;
    policy: PoliticsThemeSimple;
    scotus: PoliticsThemeSimple;
    international: PoliticsThemeSimple;
    other: PoliticsThemeSimple;
  };
  cross_source: CrossSourceMatch[];
  by_source: { kalshi: number; polymarket: number };
}

export async function fetchPolitics(): Promise<PoliticsData> {
  return apiFetch<PoliticsData>("/api/politics");
}

// Entertainment v2 types — enriched market rows with kind/volume/delta/image
export interface EntMarketRow {
  q: string;
  prob: number;
  src: string;
  market_id: number;
  external_id: string;
  kind: string;
  top_outcomes: { name: string; prob: number; delta_24h: number }[];
  outcome_count: number;
  volume_24h: number | null;
  resolution_date: string | null;
  image_url: string | null;
  hook: string | null;
}

export interface EntThresholdGroup {
  title: string;
  image_url: string | null;
  thresholds: { label: string; prob: number; market_id: number }[];
}

export interface EntThemeMusic {
  count: number;
  spotify_race: EntMarketRow[];
  billboard_watch: EntMarketRow[];
  billboard_groups: EntThresholdGroup[];
  album_drops: EntMarketRow[];
  artist_streaming: EntMarketRow[];
  side_markets: EntMarketRow[];
}

export interface EntThemeMoviesTV {
  count: number;
  rt_groups: EntThresholdGroup[];
  rt_markets: EntMarketRow[];
  box_office_groups: EntThresholdGroup[];
  box_office: EntMarketRow[];
  reality_tv: EntMarketRow[];
  side_markets: EntMarketRow[];
}

export interface EntThemeTechCulture {
  count: number;
  markets: EntMarketRow[];
}

export interface EntertainmentData {
  total_markets: number;
  updated_at: string;
  trending: EntMarketRow[];
  themes: {
    music: EntThemeMusic;
    movies_tv: EntThemeMoviesTV;
    tech_culture: EntThemeTechCulture;
  };
  cultural_moments: EntMarketRow[];
  by_source: { kalshi: number; polymarket: number };
}

export async function fetchEntertainment(): Promise<EntertainmentData> {
  return apiFetch<EntertainmentData>("/api/entertainment");
}

export async function fetchTrendingSearches(): Promise<{ trending: { query: string; count: number }[] }> {
  return apiFetch<{ trending: { query: string; count: number }[] }>("/api/events/search/trending");
}

export interface CalibrationBucket {
  bucket_idx: number;
  source: string;
  category: string;
  price_moved?: boolean | null;
  n: number;
  winners: number;
  avg_prob: number;
  sum_prob: number;
  sum_sq_err: number;
  ci_lower: number;
  ci_upper: number;
}

/**
 * Queue 297: how fresh the served snapshot is. Absent (or `status !== "stale"`)
 * means the payload is current. When present and stale, the page MUST say so —
 * a dated last-good is honest, an undated one presented as live is not.
 */
export interface CalibrationCacheState {
  status: string; // "stale" when serving a last-good copy
  reason?: string; // main_key_absent | redis_unavailable | compute_deadline
  generated_at?: string; // when the served snapshot was actually built
  age_s?: number; // how old it is, in seconds
}

/**
 * #2007 (CAL-P076/P077): the payload dates its own INPUTS, not just itself.
 *
 * `generated_at` says when the curve was serialised. It said "two minutes ago"
 * over a futures bank that had not been re-read in six hours, because the bank
 * is complete-forever and every hourly beat re-serialises it under a fresh
 * timestamp. This block is the other half of the sentence: `staged_at` is when
 * the bank last actually advanced, and `units_drifted` is how much of it has
 * moved underneath since.
 *
 * `measured: false` is a real state and carries a `reason`. An unreadable
 * disclosure is undisclosed drift, and the server refuses `fresh` on it — so a
 * consumer must never read a missing count as zero. See
 * `lib/calibrationStaleness.ts` for the rendering decision.
 */
/**
 * `producer` as `calibration_publish_gate._producer_block` emits it (#2649).
 *
 * Every field optional and nullable: this crosses a version boundary, and
 * `beats_missed` is `null` server-side whenever the artifact age is unknown.
 */
export interface CalibrationProducerState {
  task?: string;
  interval_s?: number | null;
  stall_after_s?: number | null;
  age_s?: number | null;
  beats_missed?: number | null;
  stalled?: boolean;
}

export interface CalibrationStagedState {
  measured: boolean;
  reason?: string;
  staged_at?: string;
  staged_age_s?: number;
  units_banked?: number;
  units_this_beat?: number | null;
  units_drifted?: number | null;
  units_drift_checkable?: number | null;
  units_drift_unknown?: number | null;
  units_drifted_as_of?: string;
  bank_advanced_this_beat?: boolean | null;
  frozen_over_drift?: boolean;
}

export interface CalibrationData {
  cache?: CalibrationCacheState | null;
  /**
   * Ruling 025's envelope: `fresh` | `stale` | `degraded` | `empty`.
   *
   * Optional because an older cached payload predates it — and absent is NOT
   * `fresh`. The page treats absence as "this artifact carries no envelope" and
   * falls back to `cache.status`, which is the pre-#2007 behaviour.
   */
  availability?: string;
  staged?: CalibrationStagedState | null;
  /**
   * The hourly producer's own verdict on itself (#2649). Optional for the same
   * reason `availability` is — an older payload predates it — and absent must
   * never be read as a healthy beat. `stalled` is pessimistic by construction
   * server-side: an unknown artifact age publishes as `true`.
   */
  producer?: CalibrationProducerState | null;
  buckets: CalibrationBucket[];
  total_markets: number;
  total_outcomes: number;
  total_winners: number;
  mce_ci_lower: number;
  mce_ci_upper: number;
  mce_closing_line: number | null;
  mce_opening_price: number | null;
  /**
   * How many sportsbook rows actually have a closing line behind them.
   *
   * The events/Odds-API path selects `COALESCE(closing, opening)`, so a row
   * with no close silently degrades to the opening price. The page states the
   * basis rather than letting "closing line" stand for the whole table
   * (queue 316 item 2b). Optional: older cached payloads omit it.
   */
  closing_line_coverage?: {
    has_closing: number;
    needs_closing: number;
    total: number;
  } | null;
  liquidity_filter?: CalibrationLiquidityFilter | null;
  // #997: minimum resolved-outcome count for a chartable sub-category, set
  // server-side (Redis-tunable) so web + native gate on the same bar.
  min_category_outcomes?: number;
  // Queue 299 (#1012) made the held-out disposition machine-readable: a cohort
  // whose defective rows were excluded can legitimately fall under the sample
  // bar, and "parked" is the honest answer — not a quietly missing chart.
  // Optional: older cached payloads carry only category + outcomes.
  small_sample_categories?: {
    category: string;
    outcomes: number;
    disposition?: string;
    publish_bar?: number;
    ece?: number | null;
  }[];
  /**
   * Queue 297 Item 3 / C111 P2: the payload names its own population contract
   * (e.g. "q299"). Without it a last-good snapshot built under an older
   * population could be served under current UI labels and no consumer — web,
   * native, or the browser rail — could tell.
   */
  population_version?: string;
  // L2-73 payload v2 (#999 §F): display semantics server-side so web + native
  // render the same story. All optional (older cached payloads omit them).
  date_range?: { start: string; end: string } | null;
  by_source?: CalibrationSourceMetric[];
  by_category?: CalibrationCategoryMetric[];
  corrections?: CalibrationCorrection[];
  // L2-103 Item 4: read-side exclusion counts (raw → published reconciliation).
  void_filter?: CalibrationExclusionFilter | null;
  soccer_2way_filter?: CalibrationExclusionFilter | null;
  esports_multi_bundle_filter?: CalibrationExclusionFilter | null;
  /**
   * CAL-P114 / CAL-P117, ruled by Alex 2026-08-28 (option b): the structural
   * non-partition-bundle exclusion, and it ships WITH its disclosure. Rows that
   * were published as N independent rungs of one market — an intraday index
   * ladder, a player-prop container — stop entering the curve, and the count
   * that left is named on the page so nobody later reads the smaller curve as a
   * fixed one.
   *
   * `excluded_by_cell` is keyed `"<source>/<category>"`, because this filter is
   * allowlisted per `(source, category)` and a single total would hide which
   * cell it acted on. CAL-P114 measured why the allowlist cannot be keyed on
   * category alone: `polymarket/economics` goes 3.91 -> 17.75 if it is.
   */
  nonexclusive_bundle_filter?: CalibrationNonexclusiveBundleFilter | null;
  // Queue #220/221 Item 3: exclusion-symmetry census — the poly never-traded
  // cohort still counted in the curve (Kalshi excludes all bands, poly only the
  // near-0.50 placeholder band).
  exclusion_symmetry?: CalibrationExclusionSymmetry | null;
  /** CAL-P067 item 5: rows held out of the published curves pending review. */
  quarantine?: CalibrationQuarantine[] | null;
  generated_at: string;
}

export interface CalibrationExclusionSymmetry {
  note: string;
  poly_never_traded_total: number;
  poly_never_traded_in_curve: number;
  poly_never_traded_excluded_by_band: number;
  per_source?: Record<string, { never_traded_excluded: string; rule: string; asymmetry_note?: string }>;
}

/** L2-73: per-source calibration metrics computed server-side (ece = n-weighted,
 *  the headline; mce = equal-weighted worst-bucket sensitivity). */
export interface CalibrationSourceMetric {
  source: string;
  ece: number | null;   // n-weighted (headline)
  mce?: number | null;  // equal-weighted worst-bucket sensitivity (secondary)
  n: number;
  gated?: boolean;
}

export interface CalibrationCategoryMetric {
  category: string;
  ece: number | null;
  mce?: number | null;
  n: number;
  gated?: boolean;
  /**
   * CAL-P067 (Fable ruling): whether this cell's curve is a measurement of its
   * population or only of the graded part of it.
   *
   * A calibration cell answers "when we said 30%, how often did it happen?",
   * which needs a grade — so the rows in the curve are exactly the graded rows
   * and the selection criterion IS the measured property. Under a 50% graded
   * share the number is not provable, and the page says so instead of printing
   * a confident pp figure. `unknown` means the graded share was never measured,
   * which is NOT a pass.
   */
  provability?: "provable" | "not_provable_selection_biased" | "unknown";
  /** Graded / resolved for this cell. Shown whenever the verdict is not `provable`. */
  graded_share?: number | null;
  provability_reason?: string;
}

/**
 * CAL-P067 item 5: outcomes held OUT of the published curves pending review.
 *
 * Alex ruled the 2,069 date-disagreement outcomes out of published curves as
 * under-review. They are neither graded-and-counted nor quietly dropped: a
 * quarantine is a stated, dated, reversible exclusion, and the page discloses
 * its size so the curve's denominator is never silently short.
 */
export interface CalibrationQuarantine {
  reason: string;
  outcomes: number;
  status: "under_review";
  note?: string;
  opened?: string | null;
}

/** L2-73 §E: the corrections log — "what we found and fixed" (trust panel). */
export interface CalibrationCorrection {
  date: string;
  title: string;
  rows: number | null;
  description: string;
}

export interface CalibrationLiquidityFilter {
  applies_to: string;
  rule: string;
  kalshi_included: number;
  kalshi_excluded: number;
}

/** L2-103 Item 4: read-side exclusion transparency counts (already in the payload
 *  from the precompute task). Surfacing them reconciles the raw resolved-outcome
 *  count with the published curve count so the headline drop is fully explained. */
export interface CalibrationExclusionFilter {
  applies_to: string;
  rule: string;
  excluded: number;
  events_excluded?: number;
  bookmaker_excluded?: number;
}

export interface CalibrationNonexclusiveBundleFilter {
  /** Human-readable scope, e.g. "kalshi/economics, polymarket/baseball". */
  applies_to: string;
  rule: string;
  excluded: number;
  included?: number;
  /** `"<source>/<category>" -> rows removed`. */
  excluded_by_cell?: Record<string, number>;
  /**
   * CAL-P119, ruled by Alex 2026-08-28 ("EXCLUDE NOW + FIX WRITER"): the cells
   * whose exclusion is **temporary by design**, keyed `"<source>/<category>"`,
   * mapped to the named condition that ENDS the exclusion.
   *
   * Not every cell in this filter leaves for the same reason, and the
   * difference is the reader's, not a bookkeeping detail. An intraday index
   * ladder is excluded because its rungs were never competing answers to one
   * question — that is structural and permanent. `polymarket/baseball`'s
   * Player-Props legs are excluded because a WRITER produced their published
   * price, uncorrelated with the market's own quote (a leg quoted 0.0355
   * published at 0.5005). Those are real questions with intact market quotes,
   * so when the writer is repaired those rows return.
   *
   * 🔴 CERT-647: "those rows", NOT "this exclusion". Only the M1/R3 arms end
   * with the writer repair; the R1/R2 arms are the same defect already written
   * to the back catalogue and a forward fix does not un-write them. The cell is
   * present here ONLY while `temporary_excluded > 0`, so when the temporary
   * cohort empties the key disappears and the sentence leaves the page on its
   * own — while the historical remainder stays excluded and stays counted in
   * `excluded_by_cell`.
   *
   * A cell listed here MUST render its revert condition AND its count. The
   * failure this exists to stop is the page implying a temporary removal is a
   * permanent one; the failure CERT-647 caught is the mirror image — implying a
   * permanent removal is a temporary one, by rendering one promise over a count
   * whose majority never comes back.
   */
  temporary_by_cell?: Record<string, string>;
  /**
   * Rank 1's own counts, so the temporary half of the bullet is checkable on
   * its own rather than only as part of `excluded` — which is the SUM of two
   * different rules (the structural bundle filter and K').
   *
   * 🔴 CERT-647: `temporary_excluded` counts the M1/R3 cohort ONLY — the rows
   * that actually re-enter. It previously carried the full R1+R2+R3+M1 union,
   * which made the field's own name false. `historical_excluded` is the
   * complement; the two sum to K''s per-cell total in `excluded_by_cell`, so
   * the bullet still adds up. Neither may be derived by subtracting one rule's
   * total from another's.
   */
  temporary_excluded?: number;
  temporary_excluded_markets?: number;
  historical_excluded?: number;
}

export async function fetchCalibration(): Promise<CalibrationData> {
  return apiFetch<CalibrationData>("/api/calibration");
}

/** L2-103 Item 2: a real sample of the outcomes inside one calibration bucket,
 *  so a skeptic can click any point and verify what it's made of. */
export interface CalibrationExample {
  market_name: string;
  outcome_name: string;
  price: number; // predicted probability, 0-1
  result: string; // "Yes" / "No" (settled outcome)
  settle_date: string | null;
}

export interface CalibrationExamplesResponse {
  source: string;
  bucket_idx: number;
  examples: CalibrationExample[];
  note?: string | null;
}

export async function fetchCalibrationExamples(
  source: string,
  bucketIdx: number,
  wellTraded: boolean,
): Promise<CalibrationExamplesResponse> {
  const params = new URLSearchParams({
    source,
    bucket: String(bucketIdx),
    well_traded: wellTraded ? "1" : "0",
  });
  return apiFetch<CalibrationExamplesResponse>(`/api/calibration/examples?${params.toString()}`);
}

export interface SourceCoverageSport {
  sport: string;
  total: number;
  betting: number;
  espn: number;
  stat_model: number;
  kalshi: number;
  polymarket: number;
  mlb: number;
}

export interface SourceAccuracy {
  source: string;
  observations: number;
  brier: number;
  brier_ci: number;
  mae: number;
  buckets: { idx: number; n: number; avg_prob: number; actual: number }[];
}

export interface PairwiseDisagreement {
  source_a: string;
  source_b: string;
  count: number;
  avg_divergence: number;
  a_closer_pct: number;
  by_phase: Record<string, { comparisons: number; a_closer_pct: number }>;
  by_sport: Record<string, { comparisons: number; a_closer_pct: number }>;
}

export interface CaseStudy {
  event_id: number;
  home_team: string;
  away_team: string;
  sport: string;
  score: string;
  home_won: boolean;
  max_divergence: number;
  date: string;
  series: Record<string, { t: string; p: number }[]>;
}

export interface SourceIntelligenceData {
  generated_at: string;
  coverage: {
    total_events: number;
    multi_source_events: number;
    by_source_count: { sources: number; events: number }[];
    by_sport: SourceCoverageSport[];
  };
  source_accuracy: SourceAccuracy[];
  disagreements: {
    total_comparisons: number;
    rate_5pp: number;
    rate_10pp: number;
    rate_20pp: number;
    by_sport: { sport: string; comparisons: number; rate_5pp: number }[];
    pairwise: PairwiseDisagreement[];
  };
  case_studies: CaseStudy[];
}

export async function fetchSourceIntelligence(): Promise<SourceIntelligenceData> {
  return apiFetch<SourceIntelligenceData>("/api/source-intelligence");
}

/**
 * Tournament hub — the US Open championship boards (UX-P131).
 *
 * Types live in `lib/tournament.ts` beside the pure presentation logic they
 * belong to; only the fetcher is here. An unregistered slug 404s by design —
 * there is no nearest-tournament fallback, because that is exactly how the US
 * Open lost its own page to Cincinnati once already (#1793).
 */
export async function fetchTournament(
  slug: string,
  /**
   * Which half of the payload (latency/135). Omitted means the whole thing, which is what every
   * caller outside the hub page still asks for.
   *
   * `HUB_SECTIONS_FIRST` is the 20 KB (gzipped) first screen — the chart, the day's card and the
   * meta around them; `HUB_SECTIONS_REST` is the grid and the finished list, 67 KB that render
   * nothing until a reader scrolls or taps. The page asks for them in that order and merges with
   * `mergeTournamentSections`.
   */
  sections?: string
): Promise<TournamentPayload> {
  const endpoint = hubBootPath(slug, sections);

  // LAT-P217 (staged loading, after LAT-P184). The document may already have this exact request in
  // flight — issued at HTML parse time, before a single chunk of the entry graph had executed. On
  // Slow 4G that is 1.8 s of dead time on the hub's critical path. Claim it rather than re-issuing it.
  //
  // The claim is gated on an exact URL match and the boot only fires for signed-out readers, so the
  // parked body is one this reader's own request would have produced byte-for-byte. Anything else — a
  // mismatch, a non-2xx, a rejected fetch, a boot that never settles — falls through to `apiFetch`,
  // which keeps its timeout, its retries and its typed errors.
  const booted = claimHubBoot(`${API_URL}${endpoint}`);
  if (booted?.response) {
    // Raced, not awaited: see HUB_BOOT_CLAIM_TIMEOUT_MS. A bare parked fetch has no timeout, and
    // during a #2724 spell awaiting it would strand the reader on a skeleton indefinitely.
    const TIMED_OUT = Symbol("hub-boot-timeout");
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      const res = await Promise.race([
        booted.response,
        new Promise<typeof TIMED_OUT>((resolve) => {
          timer = setTimeout(() => resolve(TIMED_OUT), HUB_BOOT_CLAIM_TIMEOUT_MS);
        }),
      ]);
      if (res !== TIMED_OUT && res.ok) {
        return (await res.json()) as TournamentPayload;
      }
    } catch {
      /* boot fetch failed — the normal request below is the fallback */
    } finally {
      // `finally`, not a line after the race: a REJECTED boot skips straight to the catch, and a
      // timer left armed there keeps a 20 s handle alive for a request nobody is waiting on.
      if (timer) clearTimeout(timer);
    }
  }

  return apiFetch<TournamentPayload>(endpoint);
}

/* UX-P152: `fetchTournamentMatch` was DELETED here. The match page it fetched
 * is gone — a match is an ordinary event and renders on `/events/{id}`. Its
 * replacement is `fetchEventTournament` below, keyed on the event id rather
 * than on a tournament-private matchup key.
 */


/**
 * A standard event's tournament extensions — advancement and the match's other
 * questions (UX-P152).
 *
 * Returns `{tournament: null}` for almost every event, which is the ordinary
 * answer and not an error: the caller renders nothing and the endpoint answers
 * it in one indexed read.
 */
export async function fetchEventTournament(
  eventId: number
): Promise<EventTournamentResponse> {
  return apiFetch<EventTournamentResponse>(`/api/tournaments/by-event/${eventId}`);
}
