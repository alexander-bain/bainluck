// UX-1034f — the finished-card guard for /sports.
//
// THE DEFECT, MEASURED ON PRODUCTION. `GET /api/feed?limit=40&mode=sports` at
// 2026-09-03T03:15Z returned 24 event cards, **20 of them `status=completed`**,
// and /sports rendered every one. The same pull against Discover
// (`GET /api/feed?limit=40`) returned **0** dead cards. The two feeds do not
// disagree about what is settled — Discover runs `isStale` over its payload
// (`app/discover/page.tsx`) and /sports simply never called it. The gate already
// existed in production code; this surface was the one that didn't use it.
//
// SO THIS IS A DELEGATION, NOT A SECOND FRESHNESS LADDER. One authority for
// "settled and old", shared by both feeds, exactly as `feedFreshness.ts`
// defines it: authoritative lifecycle (`completed`/`closed`/`resolved`) plus a
// deterministic age policy. No new threshold is invented here — a second
// staleness rule on the second surface is how the two answers drift apart.
//
// WHAT IT REMOVES, on that same payload: 7 of the 20 completed cards, including
// all three the 19:39Z freshness bucket named as persisting —
// Nakashima–Michelsen (#15299603, 12.2h), Merida–Rublev (#15299604, 12.3h),
// Bu Yunchaokete–Jodar (#15300190, 10.1h) — and Reds–Padres (#15300436, 10.7h),
// the one it filed as new. The 13 that stay started 2.8–7.7h ago, which is what
// the "Just Happened" section exists to carry.
//
// 🔴 THIS IS THE SYMPTOM GUARD, NOT THE RANKING FIX. It ages out results that
// have stopped being results. It does NOT decide how much of page one a day's
// finished games may occupy — a day-turnover wall of 13 same-day finals is a
// ranking call, it belongs to the feed scorer, and no frontend filter should
// quietly make that decision on the scorer's behalf.
//
// ═══ ux/1053: THE RANKING FIX ARRIVED, AND TOOK THE GAME CARDS ═══
//
// `lib/sports/finishedSection.ts` is that fix — the finals get their own capped
// section below Upcoming, ordered today-then-yesterday. /sports now partitions
// the settled GAME cards out BEFORE calling this function, so what arrives here
// is futures, concepts, tournaments and unfinished games. Nothing below changed;
// the caller changed.
//
// The two clauses this leaves standing but unexercised on that surface, kept
// rather than deleted because they are still the right answer if a caller ever
// hands game cards back:
//
//   - the `completed`/`closed` age-out (the section's calendar window and cap
//     supersede the 8-hour clock, which could not express "yesterday" at all);
//   - the #1091 `keptToAvoidEmptyGames` reprieve, which is now unreachable from
//     /sports because an unfinished game is never `isStale`.
//
// Both remain covered by `__tests__/lib/sportsFinishedCardGuard.test.ts`, which
// tests THIS function rather than the page, and is unchanged.
//
// #1091 / gotcha #43 — NEVER FILTER A SPORTS FEED INTO HAVING NO GAMES. A
// diversity/freshness cap that empties the surface it is protecting has traded
// one defect for a worse one, so the guard declines its own age-out when the
// aged-out games are the only games in the payload. Same shape as the Discover
// pipeline's `cooldownSafe` fallback, and asserted in both directions by
// `__tests__/lib/sportsFinishedCardGuard.test.ts`.

import { isStale } from "@/lib/discover/feedFreshness";
import type { FeedItem } from "@/lib/types";

export interface FinishedCardGuardResult {
  /** The cards to render, in their original order. */
  items: FeedItem[];
  /** The cards the freshness gate removed (for suppression telemetry). */
  agedOut: FeedItem[];
  /**
   * True when the age-out was declined for the game cards because applying it
   * would have left the sports feed with no games at all (#1091).
   */
  keptToAvoidEmptyGames: boolean;
}

/** A game card. Futures/concepts/tournaments/bundles are not games. */
function isGameItem(item: FeedItem): boolean {
  return item.type === "event";
}

/**
 * Apply the shared Discover freshness gate to a /sports payload.
 *
 * Pure — no clock of its own beyond the one `isStale` already reads, no state,
 * no network. Order is preserved so the backend's ranking survives intact.
 */
export function applyFinishedCardGuard(items: FeedItem[]): FinishedCardGuardResult {
  const stale = new Set<FeedItem>();
  for (const item of items) {
    if (isStale(item)) stale.add(item);
  }
  if (stale.size === 0) {
    return { items, agedOut: [], keptToAvoidEmptyGames: false };
  }

  // #1091 — would the age-out leave this sports feed with zero game cards?
  // A settled market is never what keeps a sports feed from being gameless, so
  // only the games are reprieved; stale futures still go.
  const hadGames = items.some(isGameItem);
  const keepsAGame = items.some((item) => isGameItem(item) && !stale.has(item));
  const keptToAvoidEmptyGames = hadGames && !keepsAGame;

  const kept: FeedItem[] = [];
  const agedOut: FeedItem[] = [];
  for (const item of items) {
    const drop = stale.has(item) && !(keptToAvoidEmptyGames && isGameItem(item));
    (drop ? agedOut : kept).push(item);
  }
  return { items: kept, agedOut, keptToAvoidEmptyGames };
}
