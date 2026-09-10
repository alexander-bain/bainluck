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

/**
 * When the clock on those hours starts (#4776).
 *
 * A completed event's age starts when it FINISHES. Ageing from `commence_time`
 * charged every finished card for its own duration: measured over the 39
 * finished games served at 2026-09-10T12:19Z, the median gap between kickoff
 * and `ended_at` is 2.26h — 2.78h for MLB and 3.11h for NFL — so the eight
 * hours the constant above promises were really 5.7, and 4.9 for an NFL game.
 * The season opener (SEA 13-10 NE, ended 8:26PM PT) left Discover at 1:20AM PT,
 * which is why #4681's marquee-final arm had no morning on which it could fire:
 * 0 of 20 tier-1 finals were in window aged from kickoff, 1 aged from the end.
 *
 * `ended_at` is D109/#4676's stamp and its two constraints come with it. It is
 * OPTIONAL — absent on every unsettled row, and a cached payload can predate
 * the backend that added it — so an absent stamp falls back to `commence_time`
 * and behaves exactly as before. And it is NOT FOR DISPLAY: it is
 * `completed_at` when StatPal reported no end, which runs later than the true
 * whistle by a variable margin. That margin is fine here and is fine in the
 * safe direction — it retains a card marginally longer, the opposite of the
 * 2.26h it stops losing — but it must never be printed as "ended at".
 *
 * The backend mirrors this choice in `client_deletes_finished_card`, and
 * `backend/tests/test_client_deletion_mirror_3836.py` reads THIS FILE and fails
 * if the two sides ever come to age on different fields.
 */
export function finishedEventAgeAnchor(ed: FeedEventData): string | null {
  return ed.ended_at || ed.commence_time || null;
}

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
      // #4776 — from the whistle, not the kickoff. `finishedEventAgeAnchor`
      // says why, and falls back to `commence_time` when `ended_at` is absent.
      // An unreadable anchor still yields NaN, and `NaN > 8` is false, so the
      // card is KEPT: unknown age has never meant "old" here.
      const anchor = finishedEventAgeAnchor(ed);
      const hoursAgo =
        (Date.now() - new Date(anchor as string).getTime()) / (1000 * 60 * 60);
      if (hoursAgo > COMPLETED_EVENT_MAX_AGE_HOURS) return true;
    }
  }
  return false;
}
