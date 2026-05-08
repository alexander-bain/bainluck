import type { FeedEventData, FeedFuturesData, FeedItem, FeedTournamentData } from "@/lib/types";

export type DiscoverAction =
  | "impression"
  | "detail_click"
  | "dismiss"
  | "like"
  | "unlike"
  | "share"
  | "group_expand";

export interface DiscoverItemAnalytics {
  content_type: "event" | "futures" | "grid";
  item_id: number | string;
  category: string;
  item_name: string;
  score: number;
  headline?: string;
  personalized?: boolean;
}

export interface ProfileBucket {
  score: number;
  impressions: number;
  clicks: number;
  likes: number;
  dismisses: number;
  shares: number;
  last_interaction_at: string;
}

export interface DiscoverProfile {
  categories: Record<string, ProfileBucket>;
  updated_at: string;
}

const PROFILE_KEY = "discover_interaction_profile_v1";
const SESSION_KEY = "bainluck_session_id";
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const ACTION_WEIGHTS: Record<DiscoverAction, number> = {
  impression: 0.05,
  detail_click: 1.5,
  dismiss: -2,
  like: 2,
  unlike: -1,
  share: 3,
  group_expand: 0.75,
};

function normalizeCategory(category: string | null | undefined): string {
  return (category || "other").toLowerCase();
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

export function getDiscoverItemAnalytics(item: FeedItem): DiscoverItemAnalytics {
  if (item.type === "event") {
    const data = item.data as FeedEventData;
    return {
      content_type: "event",
      item_id: data.id,
      category: normalizeCategory(data.sport?.split("_")[0] || data.sport_name || "sports"),
      item_name: `${data.away_team} vs ${data.home_team}`,
      score: item.score,
      headline: item.headline || item.reason || undefined,
      personalized: item.personalized,
    };
  }

  if (item.type === "futures") {
    const data = item.data as FeedFuturesData;
    return {
      content_type: "futures",
      item_id: data.id,
      category: normalizeCategory(data.llm_sport_category || data.sport_name || data.sport),
      item_name: data.name,
      score: item.score,
      headline: item.headline || data.hook_description || item.reason || undefined,
      personalized: item.personalized,
    };
  }

  const data = item.data as FeedTournamentData;
  return {
    content_type: "grid",
    item_id: data.key,
    category: "golf",
    item_name: data.name,
    score: item.score,
    headline: item.headline || item.reason || undefined,
    personalized: item.personalized,
  };
}

function emptyBucket(now: string): ProfileBucket {
  return {
    score: 0,
    impressions: 0,
    clicks: 0,
    likes: 0,
    dismisses: 0,
    shares: 0,
    last_interaction_at: now,
  };
}

export function recordDiscoverInteraction(category: string, action: DiscoverAction): void {
  if (typeof window === "undefined") return;

  try {
    const now = new Date().toISOString();
    const raw = localStorage.getItem(PROFILE_KEY);
    const profile: DiscoverProfile = raw
      ? JSON.parse(raw)
      : { categories: {}, updated_at: now };
    const key = normalizeCategory(category);
    const bucket = profile.categories[key] || emptyBucket(now);

    bucket.score = Math.max(-10, Math.min(30, bucket.score + ACTION_WEIGHTS[action]));
    bucket.last_interaction_at = now;
    if (action === "impression") bucket.impressions += 1;
    if (action === "detail_click") bucket.clicks += 1;
    if (action === "like") bucket.likes += 1;
    if (action === "dismiss") bucket.dismisses += 1;
    if (action === "share") bucket.shares += 1;

    profile.categories[key] = bucket;
    profile.updated_at = now;
    localStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
    if (action !== "impression") {
      window.dispatchEvent(new CustomEvent("discover-profile-updated"));
    }
  } catch {
    // Interaction profiling is opportunistic; analytics should never break the feed.
  }
}

function getSessionId(): string | undefined {
  if (typeof window === "undefined") return undefined;

  try {
    const existing = localStorage.getItem(SESSION_KEY);
    if (existing) return existing;
    const next = globalThis.crypto?.randomUUID?.() || `sess_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
    localStorage.setItem(SESSION_KEY, next);
    return next;
  } catch {
    return undefined;
  }
}

export function sendDiscoverInteraction(
  analytics: DiscoverItemAnalytics,
  action: DiscoverAction,
  positionIndex?: number,
  source = "card"
): void {
  if (typeof window === "undefined") return;

  try {
    const sessionId = getSessionId();
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (sessionId) headers["x-session-id"] = sessionId;

    void fetch(`${API_URL}/api/feed/interactions`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        interactions: [{
          action,
          item_type: analytics.content_type,
          item_id: String(analytics.item_id),
          category: analytics.category,
          item_name: analytics.item_name,
          score: analytics.score,
          rank: typeof positionIndex === "number" ? positionIndex + 1 : undefined,
          surface: "web",
          source,
        }],
      }),
      keepalive: true,
    }).catch(() => {});
  } catch {
    // First-party interaction capture should never affect the feed.
  }
}

export function readDiscoverInteractionProfile(): DiscoverProfile | null {
  if (typeof window === "undefined") return null;

  try {
    const raw = localStorage.getItem(PROFILE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as DiscoverProfile;
    return parsed && parsed.categories ? parsed : null;
  } catch {
    return null;
  }
}

export function getDiscoverCategoryAdjustment(
  profile: DiscoverProfile | null,
  category: string
): number {
  const bucket = profile?.categories[normalizeCategory(category)];
  if (!bucket) return 0;

  const engagement = bucket.clicks + bucket.likes * 1.5 + bucket.shares * 2 + bucket.dismisses;
  if (engagement < 2) return 0;

  return clamp(bucket.score, -8, 12);
}

export function getDiscoverPersonalizationTrace(
  profile: DiscoverProfile | null,
  category: string
): string | undefined {
  const key = normalizeCategory(category);
  const bucket = profile?.categories[key];
  const adjustment = getDiscoverCategoryAdjustment(profile, key);
  if (!bucket || adjustment === 0) return undefined;

  return `${key}: ${adjustment > 0 ? "+" : ""}${adjustment.toFixed(1)} from ${bucket.clicks} clicks, ${bucket.likes} likes, ${bucket.shares} shares, ${bucket.dismisses} dismisses`;
}
