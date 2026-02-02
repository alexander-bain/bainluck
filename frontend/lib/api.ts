/**
 * API client for OddsTracker backend
 */

import type {
  EventsResponse,
  EventDetailResponse,
  EventHistoryResponse,
  SportsResponse,
  LiveOddsResponse,
  SearchResponse,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Base fetch wrapper with error handling
 */
async function apiFetch<T>(endpoint: string): Promise<T> {
  const res = await fetch(`${API_URL}${endpoint}`);

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: "Unknown error" }));
    // Handle FastAPI validation errors (detail can be an array of objects)
    let message: string;
    if (typeof error.detail === "string") {
      message = error.detail;
    } else if (Array.isArray(error.detail)) {
      // FastAPI validation error format: [{loc: [...], msg: "...", type: "..."}]
      message = error.detail.map((e: { msg?: string }) => e.msg).join(", ");
    } else if (error.detail?.msg) {
      message = error.detail.msg;
    } else {
      message = `API error: ${res.status}`;
    }
    throw new Error(message);
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
 * Search events by team name, city, or keyword
 */
export async function searchEvents(params: {
  q: string;
  sport?: string;
  page?: number;
  per_page?: number;
  days_back?: number;
  include_upcoming?: boolean;
}): Promise<SearchResponse> {
  const searchParams = new URLSearchParams();
  searchParams.set("q", params.q);

  if (params.sport) searchParams.set("sport", params.sport);
  if (params.page) searchParams.set("page", params.page.toString());
  if (params.per_page) searchParams.set("per_page", params.per_page.toString());
  if (params.days_back) searchParams.set("days_back", params.days_back.toString());
  if (params.include_upcoming !== undefined) {
    searchParams.set("include_upcoming", params.include_upcoming.toString());
  }

  return apiFetch<SearchResponse>(`/api/events/search?${searchParams.toString()}`);
}

/**
 * Format probability as percentage string
 */
export function formatProbability(prob: number | null | undefined): string {
  if (prob === null || prob === undefined) return "-";
  return `${Math.round(prob * 100)}%`;
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
