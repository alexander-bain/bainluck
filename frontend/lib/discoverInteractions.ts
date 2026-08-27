import type {
  FeedEventData,
  FeedFuturesData,
  FeedItem,
  FeedTournamentData,
  FeedConceptData,
} from "@/lib/types";
import { resolveShape, SHAPE_UNSHAPED, type MarketShape } from "@/lib/marketShape";
import {
  getTelemetryConsent,
  isAnalyticsGranted,
  type ConsentLevel,
} from "@/lib/analytics/telemetryConsent";

// Concept feed items (UFC/F1/cycling event concepts) carry a `domain`, not an
// `llm_sport_category`. Map the domain to the canonical sport category so concept
// engagement attributes to the right sport (not the shared "golf" fallthrough)
// and stays in the sports lane. (L2-167 Item 3.)
const CONCEPT_DOMAIN_TO_CATEGORY: Record<string, string> = {
  ufc: "mma",
  f1: "motorsports",
  cycling: "cycling",
};

export function conceptDomainToCategory(domain: string | null | undefined): string {
  const d = (domain || "").toLowerCase();
  return CONCEPT_DOMAIN_TO_CATEGORY[d] || d || "sports";
}

export type DiscoverAction =
  | "impression"
  | "detail_click"
  | "dismiss"
  | "like"
  | "unlike"
  | "share"
  | "group_expand"
  | "challenge_start"
  | "challenge_complete"
  | "context_expand"
  | "context_collapse";

export interface DiscoverItemAnalytics {
  content_type: "event" | "futures" | "grid";
  item_id: number | string;
  category: string;
  item_name: string;
  score: number;
  headline?: string;
  personalized?: boolean;
  /**
   * Canonical market shape (Queue 310). Set here, on the ONE object that feeds
   * all three engagement rails — the `feed_card_impression` GA4 event, the
   * `feed_card_action` GA4 event, and the first-party `DiscoverInteraction`
   * row — so the tap RATE by shape is computable instead of just the tap count.
   * A numerator without its denominator would not have answered the question.
   */
  market_type: MarketShape;
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

/**
 * Mirrors `DiscoverInteractionBatch.interactions` (`max_length=50`) in
 * backend/app/routes/feed.py. The endpoint has ALWAYS accepted a batch; this
 * client sent exactly one interaction per request, which is what made a normal
 * Discover scroll self-throttling — see `flushDiscoverInteractions`.
 */
const MAX_BATCH = 50;

/**
 * How long a queued interaction waits for company before it is sent. Short
 * enough that a reader who taps straight through still records their taps,
 * long enough that a scroll past a screenful of cards is ONE request.
 */
const FLUSH_DELAY_MS = 2000;

const ACTION_WEIGHTS: Record<DiscoverAction, number> = {
  impression: 0.05,
  detail_click: 1.5,
  dismiss: -2,
  like: 2,
  unlike: -1,
  share: 3,
  group_expand: 0.75,
  challenge_start: 0.5,
  challenge_complete: 1,
  context_expand: 0.35,
  context_collapse: 0,
};

function normalizeCategory(category: string | null | undefined): string {
  return (category || "other").toLowerCase();
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

/** Never throw and never guess loudly: an unresolvable shape is `unshaped`. */
function shapeOf(signal: Parameters<typeof resolveShape>[0]): MarketShape {
  return resolveShape(signal) ?? SHAPE_UNSHAPED;
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
      // Two named sides + an event id — a duel by construction.
      market_type: shapeOf({
        eventId: data.id,
        outcomeNames: [data.away_team, data.home_team],
      }),
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
      // Stored `market_type` is authoritative; the structural fallback only
      // covers markets the #194 backfill hasn't reached.
      // NOTE: `groupSize` is deliberately NOT passed. It means "how many
      // markets are in this decomposed group", which the feed payload does not
      // carry — `outcome_count` is outcomes in THIS market and is a different
      // number. Passing it would drive the container-member branch off a value
      // that does not mean what the branch thinks it means. The stored
      // `market_type` comes from the backend classifier, which has the real
      // group context, so the fallback rarely runs at all.
      market_type: shapeOf({
        market_type: data.market_type,
        outcomeNames: (data.top_outcomes || []).map((o) => o.name),
        groupId: data.group_id,
      }),
    };
  }

  if (item.type === "concept") {
    const data = item.data as FeedConceptData;
    return {
      content_type: "grid",
      item_id: data.key,
      category: conceptDomainToCategory(data.domain),
      item_name: data.name,
      score: item.score,
      headline: item.headline || item.reason || undefined,
      personalized: item.personalized,
      // A concept/tournament card is a container of markets, not a market. It
      // has no outcome structure of its own, so it has no shape — `unshaped` is
      // the honest answer, not `container_member` (which means a member OF a
      // container, the opposite of what these cards are).
      market_type: SHAPE_UNSHAPED,
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
    market_type: SHAPE_UNSHAPED,
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
    if (action === "dismiss" || action === "unlike") bucket.dismisses += 1;
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

export function getDiscoverSessionId(): string | undefined {
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

/**
 * One interaction as the batch endpoint receives it.
 */
export interface DiscoverInteractionItem {
  action: DiscoverAction;
  item_type: DiscoverItemAnalytics["content_type"];
  item_id: string;
  category: string;
  item_name: string;
  score: number;
  rank?: number;
  surface: "web";
  source: string;
  market_type: MarketShape;
}

/**
 * MAY WE SEND THIS AT ALL — the pure gate, and the fix for the whole
 * `consent.*` browser-audit family.
 *
 * `/api/feed/interactions` is non-essential behavioural telemetry: it records
 * every card a reader scrolls past, keyed to their session id, so the server
 * can personalise their feed. It is exactly the kind of collection the consent
 * banner asks about — and it was the ONE rail on this page that never asked.
 * The GA4 event fired beside it (`trackEvent`) has always been consent-gated
 * and the localStorage profile never leaves the device; this call did neither.
 *
 * `null` (no choice yet) is a DENIAL, not a soft default, exactly as
 * `isAnalyticsGranted` defines it — a first visit must produce zero
 * non-essential telemetry, the same as an explicit Decline.
 */
export function mayCaptureDiscoverInteraction(consent: ConsentLevel): boolean {
  return isAnalyticsGranted(consent);
}

/** Interactions waiting for a batch. Never sent unless consent allows it. */
let pending: DiscoverInteractionItem[] = [];
let flushTimer: ReturnType<typeof setTimeout> | null = null;
let unloadHooked = false;

/** Drop everything queued. Used on revoke and after a send. */
export function dropPendingDiscoverInteractions(): void {
  pending = [];
  if (flushTimer !== null) {
    clearTimeout(flushTimer);
    flushTimer = null;
  }
}

/** Test seam: what is currently queued and unsent. */
export function peekPendingDiscoverInteractions(): DiscoverInteractionItem[] {
  return pending.slice();
}

/**
 * Send whatever is queued — if and only if consent allows it RIGHT NOW.
 *
 * The gate is re-read here and not just at enqueue time, because a reader can
 * revoke while a batch is still waiting. That is `consent.grant_then_revoke`
 * and `consent.deferred_event` precisely: a queued event must not land after a
 * revoke. Denied at flush time means the batch is DROPPED, never sent late.
 *
 * Reading the gate here also means an interaction captured before the consent
 * authority has hydrated is decided once it has, rather than being refused for
 * a race the reader did not cause.
 */
export function flushDiscoverInteractions(): void {
  if (flushTimer !== null) {
    clearTimeout(flushTimer);
    flushTimer = null;
  }
  const batch = pending;
  pending = [];
  if (batch.length === 0) return;

  // No grant, no request. The reader who declined generates no network traffic
  // at all — not a request that fails, not a request that is ignored.
  if (!mayCaptureDiscoverInteraction(getTelemetryConsent())) return;

  try {
    const sessionId = getDiscoverSessionId();
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      "X-Discover-Provenance": "user",
    };
    if (sessionId) headers["x-session-id"] = sessionId;

    void fetch(`${API_URL}/api/feed/interactions`, {
      method: "POST",
      headers,
      body: JSON.stringify({ interactions: batch, provenance: "user" }),
      keepalive: true,
    }).catch(() => {});
  } catch {
    // First-party interaction capture should never affect the feed.
  }
}

/**
 * Capture one interaction.
 *
 * TWO things changed here, and they are the same defect seen from two sides.
 *
 * ONE — it is consent-gated (see `mayCaptureDiscoverInteraction`).
 *
 * TWO — it BATCHES. This fired one cross-origin POST per card that crossed the
 * viewport (`app/discover/page.tsx`, threshold 0.55), so an ordinary scroll
 * through Discover issued dozens of requests in seconds and spent the reader's
 * own 60/minute anonymous budget (`ANON_RATE_LIMIT`) on impression beacons. The
 * 429s that followed are cross-origin, and a 429 the browser cannot read
 * surfaces to the page as an opaque CORS failure — which is why this arrived on
 * the board as ~20 separate `console.no_errors` / `network.no_unexpected_
 * failures` issues rather than as one rate-limit bug (#2081 named the
 * mechanism; this is the cause behind it). The endpoint has always taken 50 per
 * request; only the client refused to use it.
 */
export function sendDiscoverInteraction(
  analytics: DiscoverItemAnalytics,
  action: DiscoverAction,
  positionIndex?: number,
  source = "card"
): void {
  if (typeof window === "undefined") return;

  try {
    pending.push({
      action,
      item_type: analytics.content_type,
      item_id: String(analytics.item_id),
      category: analytics.category,
      item_name: analytics.item_name,
      score: analytics.score,
      rank: typeof positionIndex === "number" ? positionIndex + 1 : undefined,
      surface: "web",
      source,
      market_type: analytics.market_type,
    });

    // A full batch goes now — the server rejects a 51st, so the cap is a
    // contract and not a tuning knob.
    if (pending.length >= MAX_BATCH) {
      flushDiscoverInteractions();
      return;
    }

    // Anything still queued when the page goes away is sent with the batch.
    // Hooked lazily so a page nobody interacts with adds no listeners.
    if (!unloadHooked) {
      unloadHooked = true;
      window.addEventListener("pagehide", flushDiscoverInteractions);
    }

    if (flushTimer === null) {
      flushTimer = setTimeout(flushDiscoverInteractions, FLUSH_DELAY_MS);
    }
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
