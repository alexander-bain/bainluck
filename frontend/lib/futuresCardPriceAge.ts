/**
 * When the prices a futures card is drawing were last written — #6018.
 *
 * `components/FuturesCard` has printed one relative-age pip in its footer for as
 * long as it has existed, and it fed that pip `market.updated_at`. That column is
 * the moment the MARKET ROW was touched. Prices live one table down, in
 * `futures_outcomes.last_updated`, and a different set of passes writes them:
 * metadata/tier/volume/image work bumps the row without moving a price, and the
 * pollers move prices on rows whose metadata has not changed in months. So the
 * pip has never been about the numbers next to it, and it is wrong in BOTH
 * directions. Measured on one production screenshot, `/search?q=WNBA Champion`
 * at 22:47Z on 2026-09-13:
 *
 *   - "WNBA: 2026 Champion" (market 9413479, tier 1) printed **"Jul 21"** over
 *     five prices that had all been rewritten at 16:50Z that same afternoon.
 *   - "WNBA Champion" (market 55254662, tier 1) printed **"21h ago"** — its row
 *     was touched minutes before the shot — over twelve legs frozen since
 *     2026-08-07.
 *
 * Two cards in one result list, both reading 48% Minnesota, five weeks apart on
 * the label, and the fresher market wearing the older date.
 *
 * THE FLOOR, NOT THE CEILING. A single pip above five rows is read as covering
 * all five, so the only honest claim is the oldest of the rows the card draws:
 * *nothing you can see here is older than this*. Taking the newest would let one
 * refreshed favourite vouch for four stale rungs, which is the flattering half of
 * the very defect this replaces.
 *
 * SCOPED TO THE DRAWN ROWS, not the whole ladder. Market 9413479 carries an
 * `Other` rung last written in May and a tail of 0.1% legs nobody refreshes;
 * ageing the card to those would print "May 12" over a ladder whose every visible
 * answer is hours old — honest about rows the reader cannot see and misleading
 * about the ones they can.
 *
 * `null` means "this payload cannot say", and the card renders NOTHING then
 * rather than falling back to `updated_at`. An empty corner claims nothing; the
 * old pip claimed something false. (Alex, standing notice 34: if a number cannot
 * be shown honestly, leave the space empty.)
 */
import type { FuturesMarket, FuturesOutcome } from "@/lib/types";

/** The subset of a market this needs — so callers can pass a card payload. */
export type PriceAgeSource = Pick<FuturesMarket, "top_outcomes" | "outcomes"> & {
  prices_updated_at?: string | null;
};

function parsedTime(value: string | null | undefined): number | null {
  if (typeof value !== "string" || value === "") return null;
  const ms = new Date(value).getTime();
  return Number.isFinite(ms) ? ms : null;
}

/**
 * ISO string for the oldest price the card draws, or `null` when unknowable.
 *
 * Two payload shapes reach `FuturesCard` and both are served here:
 *
 *  1. `/api/events/search` sends `top_outcomes[]` WITHOUT per-row stamps, and
 *     the server does this arithmetic for us in `prices_updated_at`
 *     (`_served_prices_as_of`, `backend/app/routes/events.py`).
 *  2. `/api/futures/{id}` — what My Stuff and Preferences fetch for a pinned
 *     market — sends full `outcomes[]`, each with its own `last_updated`, and
 *     no `prices_updated_at`. The same floor is computed client-side.
 *
 * The server's value wins when present: it is computed over the rows the server
 * chose to serve, which is by construction what the card draws.
 */
export function renderedPricesAsOf(market: PriceAgeSource): string | null {
  const served = parsedTime(market.prices_updated_at);
  if (served !== null) return market.prices_updated_at as string;

  // Mirror the card's own row pick (`market.top_outcomes || market.outcomes`),
  // so the age covers exactly the rows drawn beneath it and not a wider set.
  const rows: FuturesOutcome[] = market.top_outcomes || market.outcomes || [];
  let oldest: number | null = null;
  for (const row of rows) {
    const ms = parsedTime(row?.last_updated);
    if (ms === null) continue;
    if (oldest === null || ms < oldest) oldest = ms;
  }
  if (oldest === null) return null;
  return new Date(oldest).toISOString();
}
