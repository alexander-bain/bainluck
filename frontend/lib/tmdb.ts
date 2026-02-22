/**
 * TMDB (The Movie Database) API client for Oscars page enrichment.
 *
 * Client-side only — TMDB API has CORS headers, no backend proxy needed.
 * Images are cached in localStorage with 24h TTL.
 */

const TMDB_BASE = "https://api.themoviedb.org/3";
const TMDB_IMG = "https://image.tmdb.org/t/p";
const CACHE_PREFIX = "tmdb_";
const CACHE_TTL_MS = 24 * 60 * 60 * 1000; // 24 hours

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return process.env.NEXT_PUBLIC_TMDB_API_KEY || null;
}

/** TMDB fetch with Bearer token auth (supports Read Access Token). */
async function tmdbFetch(path: string, params?: URLSearchParams): Promise<Response> {
  const token = getToken();
  if (!token) throw new Error("No TMDB token");
  const qs = params ? `?${params}` : "";
  return fetch(`${TMDB_BASE}${path}${qs}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

// ============================================================================
// Cache helpers
// ============================================================================

interface CacheEntry<T> {
  data: T;
  ts: number;
}

function cacheGet<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(CACHE_PREFIX + key);
    if (!raw) return null;
    const entry: CacheEntry<T> = JSON.parse(raw);
    if (Date.now() - entry.ts > CACHE_TTL_MS) {
      localStorage.removeItem(CACHE_PREFIX + key);
      return null;
    }
    return entry.data;
  } catch {
    return null;
  }
}

function cacheSet<T>(key: string, data: T): void {
  try {
    const entry: CacheEntry<T> = { data, ts: Date.now() };
    localStorage.setItem(CACHE_PREFIX + key, JSON.stringify(entry));
  } catch {
    // localStorage full or unavailable — silently fail
  }
}

// ============================================================================
// TMDB API calls
// ============================================================================

export interface TMDBMovieResult {
  id: number;
  title: string;
  poster_path: string | null;
  backdrop_path: string | null;
}

export interface TMDBPersonResult {
  id: number;
  name: string;
  profile_path: string | null;
}

export interface TMDBVideo {
  key: string; // YouTube video ID
  type: string; // "Trailer", "Teaser", etc.
  site: string; // "YouTube"
}

/**
 * Search for a movie by title. Returns the best match or null.
 */
export async function searchMovie(name: string, year?: number): Promise<TMDBMovieResult | null> {
  const cacheKey = `movie_${name}_${year || ""}`;
  const cached = cacheGet<TMDBMovieResult | null>(cacheKey);
  if (cached !== null) return cached;

  try {
    const params = new URLSearchParams({ query: name, language: "en-US" });
    if (year) params.set("year", year.toString());

    const res = await tmdbFetch("/search/movie", params);
    if (!res.ok) return null;

    const data = await res.json();
    const result: TMDBMovieResult | null = data.results?.[0] ?? null;
    cacheSet(cacheKey, result);
    return result;
  } catch {
    return null;
  }
}

/**
 * Search for a person by name. Returns the best match or null.
 */
export async function searchPerson(name: string): Promise<TMDBPersonResult | null> {
  const cacheKey = `person_${name}`;
  const cached = cacheGet<TMDBPersonResult | null>(cacheKey);
  if (cached !== null) return cached;

  try {
    const params = new URLSearchParams({ query: name, language: "en-US" });

    const res = await tmdbFetch("/search/person", params);
    if (!res.ok) return null;

    const data = await res.json();
    const result: TMDBPersonResult | null = data.results?.[0] ?? null;
    cacheSet(cacheKey, result);
    return result;
  } catch {
    return null;
  }
}

/**
 * Get trailers for a movie by TMDB ID.
 */
export async function getTrailers(movieId: number): Promise<TMDBVideo[]> {
  const cacheKey = `trailers_${movieId}`;
  const cached = cacheGet<TMDBVideo[]>(cacheKey);
  if (cached !== null) return cached;

  try {
    const res = await tmdbFetch(`/movie/${movieId}/videos`);
    if (!res.ok) return [];

    const data = await res.json();
    const trailers: TMDBVideo[] = (data.results || []).filter(
      (v: TMDBVideo) => v.site === "YouTube" && (v.type === "Trailer" || v.type === "Teaser")
    );
    cacheSet(cacheKey, trailers);
    return trailers;
  } catch {
    return [];
  }
}

// ============================================================================
// Image URL helpers
// ============================================================================

/** Movie poster URL (342px wide — good for cards) */
export function posterUrl(posterPath: string | null): string | null {
  if (!posterPath) return null;
  return `${TMDB_IMG}/w342${posterPath}`;
}

/** Person headshot URL (185px wide) */
export function headshotUrl(profilePath: string | null): string | null {
  if (!profilePath) return null;
  return `${TMDB_IMG}/w185${profilePath}`;
}

/** Backdrop URL (780px wide — for hero sections) */
export function backdropUrl(backdropPath: string | null): string | null {
  if (!backdropPath) return null;
  return `${TMDB_IMG}/w780${backdropPath}`;
}
