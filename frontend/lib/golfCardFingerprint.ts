import type { GolfResponse } from "./types";

/**
 * A fingerprint of the win probabilities `GET /api/golf` is currently publishing
 * for the tournament the progression table is showing.
 *
 * UX-P270 (#2661 / CERT-740). The progression endpoint adopts the card's win
 * numbers server-side so that the two lists on `/categories/golf` print the same
 * number for the same golfer. That only reaches the screen if the two payloads
 * come from the same round of polling, and they are fetched independently: the
 * card refreshes every 120s, while the progression fetch was one-shot. The first
 * hourly precompute to land mid-session therefore moved the card and left the
 * table quoting the previous one — the backend fix correct, the screen still
 * showing two numbers.
 *
 * The page re-reads progression when this string changes. It is deliberately
 * built from the ADOPTED values only — the card's own golfer list for that
 * tournament — so it changes exactly when a number the table displays has
 * changed, and not when some unrelated part of the golf payload moves. The
 * progression endpoint is uncached and runs several ILIKE scans over a large
 * table, so refetching on a 120s timer instead would multiply its load by ~30
 * for a payload that is rebuilt hourly.
 *
 * Returns `null` when there is no current tournament to track, which the caller
 * treats as "nothing to refetch on".
 */
export function golfCardWinFingerprint(data: GolfResponse | null): string | null {
  const currentEvent = data?.current_event;
  const key = currentEvent?.key;
  if (!key) return null;

  // The card ships only its top golfers per tournament, and `current_event`
  // carries a shorter top-5 slice of the same list. Prefer the fuller list: the
  // authority overrides every golfer the card carries, so a fingerprint over the
  // top 5 alone would miss a change to the 6th-15th rows the table also adopts.
  const golfers =
    data?.tournaments?.find((t) => t.key === key)?.golfers ??
    currentEvent?.top_golfers ??
    [];

  return golfers.map((g) => `${g.name}=${g.probability}`).join("|");
}

/**
 * The server-issued receipt naming the card snapshot this payload IS.
 *
 * UX-P271 (#2661 / CERT-746). `golfCardWinFingerprint` above is computed from the
 * card response alone, which is exactly why it cannot see the defect CERT-746
 * named: `/api/golf` is served with `max-age=300, stale-while-revalidate=60` while
 * the progression request carries no `Cache-Control` at all, so the page can hold
 * a card up to 360s old while the table reads a newer one. Both readings of a
 * stale card produce the SAME fingerprint, so a fingerprint over one of two clocks
 * is stable precisely when they disagree.
 *
 * The receipt fixes that by being a property of the bytes rather than of the
 * moment: the page sends it, and the endpoint binds the Win column to that exact
 * snapshot. It is computed server-side and opaque here on purpose — deriving it in
 * TypeScript would mean reimplementing the participant-name normalizer, and a
 * second normalizer that drifts is how UX-P270 nearly dropped both Højgaards.
 *
 * Returns `null` when there is no current tournament, when the payload predates
 * UX-P271, or when the tournament publishes no golfers. The caller treats null as
 * "nothing to bind to" and falls back to the value fingerprint, which is the
 * pre-UX-P271 behaviour rather than a regression.
 */
export function golfCardWinReceipt(data: GolfResponse | null): string | null {
  const key = data?.current_event?.key;
  if (!key) return null;
  return data?.tournaments?.find((t) => t.key === key)?.win_receipt ?? null;
}

/**
 * Whether the page must re-read the card past its HTTP cache to converge.
 *
 * UX-P271. The endpoint echoes the receipt it actually bound the Win column to.
 * When that differs from the receipt we sent, the table is quoting a card this
 * page is not showing — the snapshot was evicted from Redis (a ~100MB LRU shared
 * with Celery), or this card predates the deploy. Rendering it anyway is the
 * original defect with a receipt attached, so the page fetches the newer card.
 *
 * A pure predicate rather than a condition buried in the effect, because jest
 * here cannot run effects: expressed inline, the single most important branch in
 * the convergence path would be unguarded.
 *
 * Refuses in every direction that could cost a request loop: no echo (a non-golf
 * or card-less response), nothing sent to compare against, an exact match, or a
 * receipt already attempted. The attempted set is keyed on the receipt we SENT,
 * and converging replaces the card and therefore that receipt, so a later genuine
 * mismatch is still allowed to converge.
 */
export function shouldRebindGolfCard(
  sentReceipt: string | null | undefined,
  appliedReceipt: string | null | undefined,
  alreadyAttempted: ReadonlySet<string>
): boolean {
  if (!sentReceipt || !appliedReceipt) return false;
  if (sentReceipt === appliedReceipt) return false;
  return !alreadyAttempted.has(sentReceipt);
}
