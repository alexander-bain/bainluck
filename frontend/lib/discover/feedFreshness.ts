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
 * The same hours for the ONE OR TWO finished games Discover deliberately kept
 * (#4681's marquee arm) — D118 = B, Alex, Thu 2026-09-10 10:35am PT.
 *
 * WHY A SECOND NUMBER AND NOT A BIGGER FIRST ONE. Eight hours from the whistle
 * retired the NFL season opener (SEA 13-10 NE, ended 8:26pm PT) at 4:26am
 * Pacific. #4776 had already moved that clock off the kickoff, and 4:26am is
 * still before anyone is awake: the ship "last night's big game is there with
 * your coffee" is not delivered by any anchor change, only by a longer window.
 * Fourteen hours puts an 8:30pm final on the page at 10:30am, which is the
 * answer Alex picked from the three offered.
 *
 * It is scoped to the marquee cards because that is what he was told it did:
 * *"It only ever affects genuinely big finished games — there is a separate
 * limit of two such cards at a time, so Discover cannot turn into a
 * scoreboard."* Raising `COMPLETED_EVENT_MAX_AGE_HOURS` itself would also have
 * moved `/sports`' shared guard, which no ruling touched. So the flag below is
 * how the promise stays literally true in code rather than in a docstring.
 */
export const MARQUEE_FINAL_MAX_AGE_HOURS = 14;

/**
 * How long THIS finished card may live — 14h if the backend kept it as one of
 * Discover's marquee finals, 8h otherwise.
 *
 * `discover_marquee_final` is stamped by `_recent_marquee_final_ids`' caller in
 * `app/routes/feed.py`, on finished event cards only, and it is stamped `false`
 * as well as `true` — an absent flag means "this payload predates the stamp, or
 * came from a surface that does not select marquee finals", and both of those
 * must read as the ordinary 8 hours. Never `??`/`||` this into the long window:
 * the expensive direction of the error is keeping a dead card, and unknown
 * provenance is not evidence of marquee status.
 */
export function finishedEventMaxAgeHours(ed: FeedEventData): number {
  return ed.discover_marquee_final === true
    ? MARQUEE_FINAL_MAX_AGE_HOURS
    : COMPLETED_EVENT_MAX_AGE_HOURS;
}

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
      // D118 — and how many hours those are depends on whether Discover kept
      // this card on purpose. `finishedEventMaxAgeHours` says why.
      if (hoursAgo > finishedEventMaxAgeHours(ed)) return true;
    }
  }
  return false;
}
