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
