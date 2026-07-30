// L2-214 Item 2 — Discover client freshness: only AUTHORITATIVE lifecycle/date
// evidence hides a card. Probability alone never settles a card.
//
// This mirrors backend/scripts/evals/feed_credibility_fixtures.json:
//   • market_status closed/resolved              → stale (authoritative)
//   • resolution_date in the past                → stale (deterministic date age)
//   • linked event completed/closed (age policy) → stale (authoritative)
//   • a near-certain but OPEN market             → NOT stale (price is not authority)
//
// Removed (Queue L2-214): the old price-only heuristics that hid any card whose
// leader was >= 0.95, or >= 0.90 with no recent movement. A live market at 0.99
// with a future resolution date is still a valid prediction — inferring
// settlement from price alone produced false "stale" hides. Unknown authority
// stays unknown (i.e. surfaces), it is never inferred settled.

import type { FeedItem, FeedEventData, FeedFuturesData } from "@/lib/types";

/** Hours a completed/closed linked event may still show before it is aged out. */
export const COMPLETED_EVENT_MAX_AGE_HOURS = 8;

export function isStale(item: FeedItem): boolean {
  if (item.type === "futures") {
    const fd = item.data as FeedFuturesData;
    // Authoritative lifecycle: the market itself reports it is done.
    if (fd.status === "closed" || fd.status === "resolved") return true;
    // Deterministic date age: a known resolution date has already passed.
    if (fd.resolution_date && new Date(fd.resolution_date) < new Date()) return true;
  }
  if (item.type === "event") {
    const ed = item.data as FeedEventData;
    // Authoritative lifecycle + deterministic age policy.
    if (ed.status === "completed" || ed.status === "closed") {
      const hoursAgo =
        (Date.now() - new Date(ed.commence_time).getTime()) / (1000 * 60 * 60);
      if (hoursAgo > COMPLETED_EVENT_MAX_AGE_HOURS) return true;
    }
  }
  return false;
}
