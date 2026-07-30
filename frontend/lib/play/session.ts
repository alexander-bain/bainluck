// L2-176 — THE PLAY PAGE per-kid identity, leaderboard, and vote plumbing.
//
// The Play identity is deliberately kept OFF the parent's real Discover session
// (`bainluck_session_id`) so a kid's swipes never pollute the grown-up feed's
// personalization. Every Play interaction is tagged with an OPAQUE, device-scoped
// session id `kid_device:<random>` — the entered display name NEVER enters the
// session id, transport, server persistence, or telemetry (L2-214 Item 3). The
// name stays local presentation data only. No schema work: votes ride the
// existing /api/feed/interactions and /api/predictions endpoints, under the
// opaque device id. The display name still keys LOCAL-only leaderboard stats.

import { getDiscoverItemAnalytics } from "@/lib/discoverInteractions";
import type { DiscoverAction } from "@/lib/discoverInteractions";
import type { FeedItem } from "@/lib/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const PLAYERS_KEY = "bainluck_play_players_v1";
const ACTIVE_KEY = "bainluck_play_active_v1";
const STATS_KEY = "bainluck_play_stats_v1";
const DEVICE_ID_KEY = "bainluck_play_device_id_v1";
const DEVICE_ID_PREFIX = "kid_device:";

export interface KidPlayer {
  name: string;
  emoji: string;
  /** Chosen "things you love" chips at signup — biases the card pool. */
  loves: string[];
}

export interface KidStats {
  rated: number;
  bestStreak: number;
}

// ---------------------------------------------------------------------------
// Identity / session id
// ---------------------------------------------------------------------------
export function kidSlug(name: string): string {
  return (
    (name || "")
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "") || "player"
  );
}

// Per-page fallback when localStorage is unavailable (private mode / quota):
// votes still transmit under a stable-for-this-page opaque id, never persisted.
let ephemeralDeviceId: string | null = null;

/** An opaque, name-free random token. Contains no display-name material. */
function randomOpaqueToken(): string {
  try {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      return crypto.randomUUID().replace(/-/g, "");
    }
    if (typeof crypto !== "undefined" && typeof crypto.getRandomValues === "function") {
      const bytes = new Uint8Array(16);
      crypto.getRandomValues(bytes);
      return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
    }
  } catch {
    /* fall through to the non-crypto fallback */
  }
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 14)}`;
}

/**
 * Device-scoped, opaque Play identifier. Generated once per device (browser
 * storage) and reused, so: the same device is STABLE across renames; two devices
 * NEVER collide even with the same display name; clearing storage rotates it. The
 * entered display name never enters this id, transport, persistence, or telemetry.
 * (L2-214 Item 3 — supersedes the old name-derived `kid:<slug>` rater tag.)
 */
export function playDeviceId(): string {
  if (typeof window === "undefined") return "";
  try {
    const existing = localStorage.getItem(DEVICE_ID_KEY);
    if (existing && existing.startsWith(DEVICE_ID_PREFIX)) return existing;
    const id = `${DEVICE_ID_PREFIX}${randomOpaqueToken()}`;
    localStorage.setItem(DEVICE_ID_KEY, id);
    return id;
  } catch {
    if (!ephemeralDeviceId) ephemeralDeviceId = `${DEVICE_ID_PREFIX}${randomOpaqueToken()}`;
    return ephemeralDeviceId;
  }
}

/**
 * Opaque, device-scoped rater tag for Play votes. Name-free by construction —
 * the display name is intentionally NOT a parameter. Legacy `kid:<name>` session
 * ids are never written again.
 */
export function kidSessionId(): string {
  return playDeviceId();
}

// ---------------------------------------------------------------------------
// localStorage helpers (all guarded — never throw)
// ---------------------------------------------------------------------------
function readJson<T>(key: string, fallback: T): T {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function writeJson(key: string, value: unknown): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* quota / private mode — playing without persistence is fine */
  }
}

export function getPlayers(): KidPlayer[] {
  const players = readJson<KidPlayer[]>(PLAYERS_KEY, []);
  return Array.isArray(players) ? players : [];
}

export function upsertPlayer(player: KidPlayer): KidPlayer[] {
  const players = getPlayers();
  const slug = kidSlug(player.name);
  const idx = players.findIndex((p) => kidSlug(p.name) === slug);
  if (idx >= 0) players[idx] = player;
  else players.push(player);
  writeJson(PLAYERS_KEY, players);
  return players;
}

export function getActivePlayerName(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return localStorage.getItem(ACTIVE_KEY);
  } catch {
    return null;
  }
}

export function setActivePlayerName(name: string | null): void {
  if (typeof window === "undefined") return;
  try {
    if (name) localStorage.setItem(ACTIVE_KEY, name);
    else localStorage.removeItem(ACTIVE_KEY);
  } catch {
    /* ignore */
  }
}

// ---------------------------------------------------------------------------
// Leaderboard (rating COUNT + best streak — volume of judgment, not correctness)
// ---------------------------------------------------------------------------
export function getAllStats(): Record<string, KidStats> {
  return readJson<Record<string, KidStats>>(STATS_KEY, {});
}

export function getStats(name: string): KidStats {
  const all = getAllStats();
  return all[kidSlug(name)] || { rated: 0, bestStreak: 0 };
}

export function bumpRated(name: string, by = 1): KidStats {
  const all = getAllStats();
  const slug = kidSlug(name);
  const cur = all[slug] || { rated: 0, bestStreak: 0 };
  cur.rated += by;
  all[slug] = cur;
  writeJson(STATS_KEY, all);
  return cur;
}

export function recordBestStreak(name: string, streak: number): KidStats {
  const all = getAllStats();
  const slug = kidSlug(name);
  const cur = all[slug] || { rated: 0, bestStreak: 0 };
  if (streak > cur.bestStreak) cur.bestStreak = streak;
  all[slug] = cur;
  writeJson(STATS_KEY, all);
  return cur;
}

// ---------------------------------------------------------------------------
// Vote plumbing — existing endpoints, kid session tag
// ---------------------------------------------------------------------------

/** "Cool or Boring?" swipe → the existing Discover interaction endpoint. */
export function sendKidInteraction(
  name: string,
  item: FeedItem,
  action: DiscoverAction
): void {
  if (typeof window === "undefined") return;
  try {
    const a = getDiscoverItemAnalytics(item);
    void fetch(`${API_URL}/api/feed/interactions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-session-id": kidSessionId(),
      },
      body: JSON.stringify({
        interactions: [
          {
            action,
            item_type: a.content_type,
            item_id: String(a.item_id),
            category: a.category,
            item_name: a.item_name,
            score: a.score,
            surface: "web",
            source: "play",
          },
        ],
      }),
      keepalive: true,
    }).catch(() => {});
  } catch {
    /* votes are opportunistic — never break the game */
  }
}

/** "Higher or Lower?" guess → the existing predictions endpoint. */
export function sendKidPrediction(
  name: string,
  payload: {
    market_id: number;
    guess: "higher" | "lower";
    threshold: number;
    actual_probability: number;
    correct: boolean;
  }
): void {
  if (typeof window === "undefined") return;
  try {
    void fetch(`${API_URL}/api/predictions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-session-id": kidSessionId(),
      },
      body: JSON.stringify(payload),
      keepalive: true,
    }).catch(() => {});
  } catch {
    /* ignore */
  }
}

// ---------------------------------------------------------------------------
// Affinity seeding — bias the (already kid-safe) pool toward the kid's picks
// ---------------------------------------------------------------------------
// Each love-chip maps to match tokens; a card that matches any of the active
// kid's chips floats to the front of the deck. Delight in the first 30 seconds.
export const LOVE_CHIPS: { id: string; emoji: string; label: string; tokens: string[] }[] = [
  { id: "baseball", emoji: "⚾", label: "Baseball", tokens: ["baseball", "mlb", "yankees", "dodgers", "world series", "home run"] },
  { id: "basketball", emoji: "🏀", label: "Basketball", tokens: ["basketball", "nba", "wnba", "dunk", "playoff"] },
  { id: "wrestling", emoji: "🤼", label: "WWE", tokens: ["wwe", "wrestl", "cena", "mania", "smackdown", "raw", "champion"] },
  { id: "music", emoji: "🎤", label: "Music", tokens: ["taylor swift", "swift", "music", "song", "album", "grammy", "concert", "tour", "billboard", "spotify"] },
  { id: "movies", emoji: "🎬", label: "Movies & TV", tokens: ["movie", "film", "box office", "oscar", "series", "show", "netflix", "disney"] },
  { id: "weather", emoji: "🌪", label: "Weather", tokens: ["weather", "rain", "snow", "storm", "hurricane", "temperature", "heat", "hot", "cold"] },
];

function itemMatchesTokens(item: FeedItem, tokens: string[]): boolean {
  const a = getDiscoverItemAnalytics(item);
  const hay = `${a.item_name} ${a.headline || ""} ${a.category}`.toLowerCase();
  return tokens.some((t) => hay.includes(t));
}

/** Stable sort: cards matching the kid's loves first, original order preserved within each group. */
export function seedByAffinity(items: FeedItem[], loves: string[]): FeedItem[] {
  if (!loves || loves.length === 0) return items;
  const tokens = LOVE_CHIPS.filter((c) => loves.includes(c.id)).flatMap((c) => c.tokens);
  if (tokens.length === 0) return items;
  const liked: FeedItem[] = [];
  const rest: FeedItem[] = [];
  for (const item of items) {
    if (itemMatchesTokens(item, tokens)) liked.push(item);
    else rest.push(item);
  }
  return [...liked, ...rest];
}
