/**
 * #1469 — a returning reader sees last visit's first page while the fresh one loads.
 *
 * Alex, Oct 8: open useful content much faster. The parse-time boot fetch
 * (`feedBoot.ts`) only fires for a brand-new, signed-out visitor; everyone who
 * has been here before still stares at nine skeleton cards until `/api/feed`
 * answers — the whole network round trip after hydration. The app already
 * paints its last-good page from disk (`DiscoverFeedCache.swift`); this is the
 * web twin, deliberately narrower.
 *
 * WHAT IT IS NOT. It is not a cache the feed is READ from. The fresh request
 * runs exactly as before; the warm page is shown only while that request is in
 * flight and is replaced WHOLESALE (never reconciled) the moment it lands, so
 * no card the server has dropped can survive on screen.
 *
 * TRUTH BEFORE SPEED. A stored card is a claim about the past. Only the cards
 * whose state cannot have changed underneath them are shown:
 *   - a finished game (its result is permanent; `isStale` still ages it out),
 *   - a scheduled game whose start time is still in the future,
 *   - a futures market (its price moves, the live price stream re-prices it
 *     on screen, and `isStale` drops one that has closed or passed its date).
 * A game that was live, suspended, or scheduled-but-past-kickoff when stored
 * is NOT shown — it could be final now, and "LIVE" on a finished game is the
 * defect the truthful-state bar exists for. Tournament, bundle, concept and
 * collection cards carry nested live state or admission rules and are left to
 * the fresh page.
 *
 * WHOSE PAGE. A personalized signed-in page must never be painted for another
 * account or for signed-out mode. The stored entry carries the device identity
 * it was written under — the Firebase uid persisted in localStorage, or `anon`
 * — and is shown only when the identity read NOW is the same. An unreadable
 * auth record is `null`: neither read nor written.
 *
 * Everything here is pure except the two thin `localStorage` wrappers at the
 * bottom, so the decisions are testable without a browser.
 */

import type { FeedEventData, FeedItem } from "@/lib/types";
import { BOOT_AUTH_KEY_PREFIX } from "@/lib/discover/feedBoot";

/** One entry per device. localStorage, so it outlives the tab. */
export const WARM_FEED_KEY = "discover_feed_warm";

/** Bump when the stored shape changes; an older entry is refused, not coerced. */
export const WARM_FEED_VERSION = 1;

/**
 * How old a stored page may be and still be painted. Past this the reader has
 * been away long enough that last visit's page is a different edition.
 */
export const WARM_FEED_MAX_AGE_MS = 6 * 60 * 60 * 1000;

interface WarmFeedEnvelope {
  v: number;
  savedAt: number;
  identity: string;
  items: FeedItem[];
}

/** Minimal read surface of `Storage`, so tests can pass a plain object. */
export interface StorageLike {
  readonly length: number;
  key(index: number): string | null;
  getItem(key: string): string | null;
}

/**
 * The device identity a warm page belongs to: `fb:<uid>` when a Firebase user
 * is persisted, `anon` when none is, and `null` when one is present but cannot
 * be read (fail closed: no warm page either way).
 */
export function warmFeedIdentity(storage: StorageLike): string | null {
  for (let i = 0; i < storage.length; i++) {
    const key = storage.key(i);
    if (!key || !key.startsWith(BOOT_AUTH_KEY_PREFIX)) continue;
    try {
      const parsed = JSON.parse(storage.getItem(key) ?? "null") as { uid?: unknown } | null;
      return parsed && typeof parsed.uid === "string" && parsed.uid ? `fb:${parsed.uid}` : null;
    } catch {
      return null;
    }
  }
  return "anon";
}

/**
 * May this stored card be painted? See the header: only cards whose state
 * cannot have moved since they were stored.
 */
export function warmItemIsTruthful(item: FeedItem, nowMs: number): boolean {
  if (item.type === "futures") return true;
  if (item.type !== "event") return false;
  const ed = item.data as FeedEventData;
  if (ed.status === "completed" || ed.status === "closed") return true;
  if (ed.status !== "scheduled") return false;
  const start = Date.parse(ed.commence_time);
  return Number.isFinite(start) && start > nowMs;
}

export function encodeWarmFeed(items: FeedItem[], identity: string, nowMs: number): string {
  const envelope: WarmFeedEnvelope = { v: WARM_FEED_VERSION, savedAt: nowMs, identity, items };
  return JSON.stringify(envelope);
}

/**
 * The paintable cards from a stored entry, or `[]`. Refuses an entry of another
 * version, another identity, a future or over-age stamp, or any shape it does
 * not understand.
 */
export function decodeWarmFeed(raw: string | null, identity: string | null, nowMs: number): FeedItem[] {
  if (!raw || !identity) return [];
  let envelope: WarmFeedEnvelope;
  try {
    envelope = JSON.parse(raw) as WarmFeedEnvelope;
  } catch {
    return [];
  }
  if (!envelope || envelope.v !== WARM_FEED_VERSION) return [];
  if (envelope.identity !== identity) return [];
  if (typeof envelope.savedAt !== "number") return [];
  const age = nowMs - envelope.savedAt;
  if (age < 0 || age > WARM_FEED_MAX_AGE_MS) return [];
  if (!Array.isArray(envelope.items)) return [];
  return envelope.items.filter(
    (item) => !!item && typeof item === "object" && !!item.data && warmItemIsTruthful(item, nowMs)
  );
}

/** Read the paintable warm page for the current device identity. Never throws. */
export function readWarmFeed(): FeedItem[] {
  try {
    const storage = window.localStorage;
    return decodeWarmFeed(storage.getItem(WARM_FEED_KEY), warmFeedIdentity(storage), Date.now());
  } catch {
    return [];
  }
}

/** Store a freshly served first page for next visit. Never throws. */
export function writeWarmFeed(items: FeedItem[]): void {
  if (items.length === 0) return;
  try {
    const storage = window.localStorage;
    const identity = warmFeedIdentity(storage);
    if (!identity) return;
    storage.setItem(WARM_FEED_KEY, encodeWarmFeed(items, identity, Date.now()));
  } catch {
    // Quota or private mode: next visit simply loads cold, which is today.
  }
}
