/**
 * API client for Bain Luck backend
 */

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
  OscarsResponse,
  OscarsPoolResponse,
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
  SportHierarchyListResponse,
  SportHierarchy,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Auth token getter — set by AuthProvider when user signs in.
 * This avoids a circular dependency between api.ts and useAuth.ts.
 */
let _getAuthToken: (() => Promise<string | null>) | null = null;

export function setAuthTokenGetter(getter: (() => Promise<string | null>) | null) {
  _getAuthToken = getter;
}

/**
 * Base fetch wrapper with error handling and optional auth
 */
async function apiFetch<T>(endpoint: string, options?: RequestInit & { timeoutMs?: number }): Promise<T> {
  const headers: Record<string, string> = {
    ...(options?.headers as Record<string, string> || {}),
  };

  // Attach auth token if available
  if (_getAuthToken) {
    const token = await _getAuthToken();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
  }

  const timeoutMs = options?.timeoutMs ?? 20000;
  const maxRetries = 2;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const res = await fetch(`${API_URL}${endpoint}`, {
        ...options,
        headers,
        signal: controller.signal,
      });

      clearTimeout(timeout);

      if (!res.ok) {
        const error = await res.json().catch(() => ({ detail: "Unknown error" }));
        throw new Error(error.detail || `API error: ${res.status}`);
      }

      return res.json();
    } catch (err: unknown) {
      clearTimeout(timeout);
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
 * Fetch a single event by ID
 */
export async function fetchEvent(id: number): Promise<EventDetailResponse> {
  return apiFetch<EventDetailResponse>(`/api/events/${id}`);
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
  return apiFetch<EventHistoryResponse>(
    `/api/events/${id}/history?hours=${hours}`
  );
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

  return apiFetch<SearchResponse>(`/api/events/search?${searchParams.toString()}`);
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
  type: "team" | "event" | "futures";
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
  // Futures fields
  market_id?: number;
  market_tier?: number;
  market_type_label?: string;
}

export interface TypeaheadResponse {
  suggestions: TypeaheadSuggestion[];
  query: string;
  did_you_mean?: string;
}

export async function fetchTypeahead(q: string): Promise<TypeaheadResponse> {
  return apiFetch<TypeaheadResponse>(
    `/api/events/typeahead?q=${encodeURIComponent(q)}`
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
}

export interface ChampionshipPathEntry {
  tier: number;
  label: string;
  market_name: string;
  market_id: number;
  probability: number | null;
  rank: number | null;
  movement: number | null;
}

export interface TeamPageResponse {
  team: TeamPageTeam;
  upcoming_events: Event[];
  recent_events: Event[];
  futures: TeamFutureItem[];
  championship_path: ChampionshipPathEntry[];
}

export async function fetchTeamPage(identifier: string): Promise<TeamPageResponse> {
  return apiFetch<TeamPageResponse>(`/api/teams/${encodeURIComponent(identifier)}`);
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
export function formatProbability(prob: number | null | undefined): string {
  if (prob === null || prob === undefined) return "-";
  return `${Math.round(prob * 100)}%`;
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

/**
 * Format moneyline odds for display
 */
export function formatMoneyline(odds: number | null | undefined): string {
  if (odds === null || odds === undefined) return "-";
  return odds > 0 ? `+${odds}` : `${odds}`;
}

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
  limit?: number;
}): Promise<GroupedFeedResponse> {
  const params = new URLSearchParams();
  if (opts?.category) params.set("category", opts.category);
  if (opts?.sport) params.set("sport", opts.sport);
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
  topN?: number
): Promise<FuturesHistoryResponse> {
  const params = new URLSearchParams();
  params.set("hours", hours.toString());
  if (outcomeId) params.set("outcome_id", outcomeId.toString());
  if (topN) params.set("top_n", topN.toString());

  return apiFetch<FuturesHistoryResponse>(
    `/api/futures/${marketId}/history?${params.toString()}`
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
  topN?: number
): Promise<ProgressionResponse> {
  const params = topN ? `?top_n=${topN}` : "";
  return apiFetch<ProgressionResponse>(
    `/api/futures/${marketId}/progression${params}`
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
}

export async function fetchGameMarkets(
  eventId: number
): Promise<GameMarketsResponse> {
  return apiFetch<GameMarketsResponse>(
    `/api/events/${eventId}/game-markets`
  );
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
  return apiFetch<TeamProgressionResponse>(
    `/api/events/${eventId}/team-progression`
  );
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

/**
 * Format American odds for display
 */
export function formatAmericanOdds(odds: number | null | undefined): string {
  if (odds === null || odds === undefined) return "-";
  return odds > 0 ? `+${odds}` : `${odds}`;
}

// ============================================================================
// Unified Feed API
// ============================================================================

/**
 * Fetch the unified feed of interesting events and futures
 */
export async function fetchFeed(params?: {
  limit?: number;
  offset?: number;
  sport?: string;
  my_teams_only?: boolean;
  include_futures?: boolean;
  include_events?: boolean;
  event_pct?: number;
  tags?: string[];
}): Promise<FeedResponse> {
  const searchParams = new URLSearchParams();

  if (params?.limit) searchParams.set("limit", params.limit.toString());
  if (params?.offset) searchParams.set("offset", params.offset.toString());
  if (params?.sport) searchParams.set("sport", params.sport);
  if (params?.my_teams_only) searchParams.set("my_teams_only", "true");
  if (params?.include_futures === false) searchParams.set("include_futures", "false");
  if (params?.include_events === false) searchParams.set("include_events", "false");
  if (params?.event_pct != null) searchParams.set("event_pct", params.event_pct.toString());
  if (params?.tags?.length) searchParams.set("tags", JSON.stringify(params.tags));

  const query = searchParams.toString();
  return apiFetch<FeedResponse>(`/api/feed${query ? `?${query}` : ""}`);
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
 * Fetch the current user's preferences and team favorites
 */
export async function fetchUserPreferences(): Promise<UserPreferencesResponse> {
  return apiFetch<UserPreferencesResponse>("/api/me/preferences");
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
// Oscars API
// ============================================================================

/**
 * Fetch Oscars landing page data — all categories with aggregated odds
 */
export async function fetchOscarsData(): Promise<OscarsResponse> {
  return apiFetch<OscarsResponse>("/api/oscars");
}

// ============================================================================
// Oscars Pool API
// ============================================================================

export async function createOscarsPool(poolName: string, creatorName: string, avatarEmoji: string = "🎬") {
  return apiFetch<{
    pool_code: string;
    pool_name: string;
    member_token: string;
    member_id: number;
    display_name: string;
    avatar_emoji: string;
    avatar_options: string[];
  }>("/api/oscars/pool", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pool_name: poolName, creator_name: creatorName, avatar_emoji: avatarEmoji }),
  });
}

export async function joinOscarsPool(code: string, displayName: string, avatarEmoji: string = "🎬") {
  return apiFetch<{
    pool_code: string;
    pool_name: string;
    member_token: string;
    member_id: number;
    display_name: string;
    avatar_emoji: string;
  }>(`/api/oscars/pool/${code}/join`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ display_name: displayName, avatar_emoji: avatarEmoji }),
  });
}

export async function fetchOscarsPool(code: string, memberToken?: string) {
  const headers: Record<string, string> = {};
  if (memberToken) headers["X-Member-Token"] = memberToken;
  return apiFetch<OscarsPoolResponse>(`/api/oscars/pool/${code}`, { headers });
}

export async function submitOscarsPoolPicks(
  code: string,
  memberToken: string,
  picks: { category_key: string; nominee_name: string; probability_at_pick: number }[],
  confidencePicks: string[] = [],
) {
  return apiFetch<{ status: string; picks_count: number }>(`/api/oscars/pool/${code}/picks`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Member-Token": memberToken },
    body: JSON.stringify({ picks, confidence_picks: confidencePicks }),
  });
}

export async function submitOscarsPoolBonusPicks(
  code: string,
  memberToken: string,
  picks: { bonus_key: string; selected_option: string }[],
) {
  return apiFetch<{ status: string; count: number }>(`/api/oscars/pool/${code}/bonus-picks`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Member-Token": memberToken },
    body: JSON.stringify({ picks }),
  });
}

export async function lockOscarsPool(code: string, memberToken: string) {
  return apiFetch<{ status: string }>(`/api/oscars/pool/${code}/lock`, {
    method: "POST",
    headers: { "X-Member-Token": memberToken },
  });
}

export async function revealOscarsWinner(
  code: string,
  memberToken: string,
  categoryKey: string,
  winnerName: string,
) {
  return apiFetch<{
    category_key: string;
    winner: string;
    scored_members: { display_name: string; avatar_emoji: string; picked: string; is_correct: boolean; points_earned: number }[];
  }>(`/api/oscars/pool/${code}/reveal`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Member-Token": memberToken },
    body: JSON.stringify({ category_key: categoryKey, winner_name: winnerName }),
  });
}

export async function revealOscarsBonus(
  code: string,
  memberToken: string,
  bonusKey: string,
  correctOption: string,
) {
  return apiFetch<{
    bonus_key: string;
    correct_option: string;
    scored_members: { display_name: string; avatar_emoji: string; picked: string; is_correct: boolean; points_earned: number }[];
  }>(`/api/oscars/pool/${code}/reveal-bonus`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Member-Token": memberToken },
    body: JSON.stringify({ bonus_key: bonusKey, correct_option: correctOption }),
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
export async function fetchGolfData(): Promise<GolfResponse> {
  return apiFetch<GolfResponse>("/api/golf");
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
  market_tier: number | null;
  category: string;
  resolution_date: string | null;
  outcome_count: number;
  top_outcomes: LeagueMarketOutcome[];
  canonical_market_key: string | null;
  section: string;
}

export interface LeagueFuturesResponse {
  sport_key: string;
  sections: Record<string, LeagueMarket[]>;
  total_markets: number;
}

export async function fetchLeagueMarkets(sportKey: string): Promise<LeagueFuturesResponse> {
  return apiFetch<LeagueFuturesResponse>(`/api/leagues/${sportKey}`);
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
    government: EconThemeSimple;
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

// Entertainment types reuse the same market row shape as politics
export interface EntertainmentSection {
  label: string;
  count: number;
  markets: PoliticsMarketRow[];
}

export interface EntertainmentData {
  total_markets: number;
  updated_at: string;
  sections: Record<string, EntertainmentSection>;
  by_source: { kalshi: number; polymarket: number };
}

export async function fetchEntertainment(): Promise<EntertainmentData> {
  return apiFetch<EntertainmentData>("/api/entertainment");
}

export async function fetchTrendingSearches(): Promise<{ trending: { query: string; count: number }[] }> {
  return apiFetch<{ trending: { query: string; count: number }[] }>("/api/events/search/trending");
}

