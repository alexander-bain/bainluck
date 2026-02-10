/**
 * API client for OddsTracker backend
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
  PulseRankingsResponse,
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
async function apiFetch<T>(endpoint: string, options?: RequestInit): Promise<T> {
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

  const res = await fetch(`${API_URL}${endpoint}`, {
    ...options,
    headers,
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(error.detail || `API error: ${res.status}`);
  }

  return res.json();
}

/**
 * Authenticated fetch wrapper for POST/PUT/DELETE with JSON body
 */
async function apiMutate<T>(
  endpoint: string,
  method: string,
  body?: unknown,
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  if (_getAuthToken) {
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
  page?: number;
  per_page?: number;
}): Promise<SearchResponse> {
  const searchParams = new URLSearchParams();
  searchParams.set("q", params.q);
  if (params.sport) searchParams.set("sport", params.sport);
  if (params.page) searchParams.set("page", params.page.toString());
  if (params.per_page) searchParams.set("per_page", params.per_page.toString());

  return apiFetch<SearchResponse>(`/api/events/search?${searchParams.toString()}`);
}

/**
 * Fetch all-time highest and lowest Pulse events
 */
export async function fetchPulseRankings(params?: {
  sport?: string;
  limit?: number;
}): Promise<PulseRankingsResponse> {
  const searchParams = new URLSearchParams();

  if (params?.sport) searchParams.set("sport", params.sport);
  if (params?.limit) searchParams.set("limit", params.limit.toString());

  const query = searchParams.toString();
  return apiFetch<PulseRankingsResponse>(`/api/events/pulse-rankings${query ? `?${query}` : ""}`);
}

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
  outcomeId?: number
): Promise<FuturesHistoryResponse> {
  const params = new URLSearchParams();
  params.set("hours", hours.toString());
  if (outcomeId) params.set("outcome_id", outcomeId.toString());

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
 * Format American odds for display
 */
export function formatAmericanOdds(odds: number | null | undefined): string {
  if (odds === null || odds === undefined) return "-";
  return odds > 0 ? `+${odds}` : `${odds}`;
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
