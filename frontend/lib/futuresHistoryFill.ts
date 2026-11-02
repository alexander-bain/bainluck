/**
 * #883 — THE FIRST READER STOPS GETTING THE COLD CHART.
 *
 * Alex, 2026-10-06 (as recorded on #883): after clicking a futures or props card
 * he finds "sparse charts without an interesting trend". The landing-page audit
 * (FABLE-LANDING-PAGE-AUDIT-20261006) measured why: on 17 of 21 pages the first
 * `/history` answer was thin AND told us it had asked the background lane for
 * the venue's history (`venue_history.fill: "requested"`). That fill landed
 * 99–219 s later — and the page never asked again, so the reader who triggered
 * the repair was the one reader guaranteed not to see it.
 *
 * The page now re-asks, boundedly, while the server says a fill is in flight.
 * It stops on the first answer that says anything else (the fill completed and
 * the planner reports `answered_recently`, or it refused, or there is nothing to
 * fill), and the caller stops on unmount or a range change. Nothing here draws a
 * point: the retry only fetches what the server has retained.
 */

/** The `venue_history.fill` values that mean "a fill is on its way". */
const PENDING_FILL = new Set(["requested", "already_claimed"]);

/**
 * Delays (ms) before each re-ask, measured from the previous answer. Sums to
 * 4 minutes, which covers the 219 s worst completion the audit observed; the
 * 7/21 pages whose fill never landed cost at most five extra reads, then stop.
 */
export const HISTORY_FILL_RETRY_DELAYS_MS: readonly number[] = [20_000, 30_000, 45_000, 60_000, 85_000];

/** True when this `/history` body says a venue-history fill is in flight. */
export function historyFillPending(
  body: { venue_history?: { fill?: string | null } | null } | null | undefined,
): boolean {
  const fill = body?.venue_history?.fill;
  return typeof fill === "string" && PENDING_FILL.has(fill);
}

/** The delay before re-ask number `attempt` (0-based), or null once spent. */
export function historyFillRetryDelay(attempt: number): number | null {
  if (!Number.isInteger(attempt) || attempt < 0) return null;
  return HISTORY_FILL_RETRY_DELAYS_MS[attempt] ?? null;
}
