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
 *
 * #6803 — AND A ROW THAT SHOWS NO PRICE CANNOT BE A FLOOR OVER PRICES.
 *
 * The floor doctrine above is a claim about what the reader can SEE: *nothing
 * you can see here is older than this*. A rung with `probability: null` renders
 * no number, so it has no age the sentence is about — yet it carried a
 * `last_updated` like any other row and the walk below took it. Routed by
 * native/207, who measured it on the iOS twin: `/api/futures/114175` serves 19
 * outcomes, 14 priced and rewritten at 2026-09-17T19:50Z, and five placeholder
 * rungs (`Fighter D/E/F/G`, `Other`) stamped 2026-05-12T16:16:06Z. The floor
 * over all nineteen is **May 12**; over the fourteen with a price it is **today**.
 * The iPhone drew "Updated May 12 at 9:16 AM" over a 66% hero whose every price
 * was 35 minutes old.
 *
 * This is the SCOPED-TO-THE-DRAWN-ROWS paragraph above arriving through a door
 * it did not cover. That paragraph names this very market's `Other` rung and
 * this very date, and leans on the server's `served`/`top_outcomes` scope to
 * keep the dead tail out. On the `/api/futures/{id}` shape there is no such
 * scope — the card gets the WHOLE ladder — so the scope has to be re-stated
 * here, in the only terms this payload can express it: does the row show a price.
 *
 * WORSE THAN THE DEFECT #6018 REPLACED, and that is why it is worth a branch.
 * The old pip overstated freshness; this understates it, telling a reader to
 * distrust a number that is current. A card that says nothing (`null`) is
 * honest; a card that says "May 12" over today's price is not.
 *
 * NOT a filter on smallness. A 0.1% leg nobody refreshes DOES show a price and
 * so keeps its vote, exactly as the doctrine above requires — `0` is a price,
 * not an absence (see `pct`). The test is `probability != null` and nothing
 * looser: a truthiness check here would silently drop every 0% rung and hand
 * the floor to whichever leg happened to be refreshed last, which is the
 * flattering half of #6018 all over again.
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
 * Does this rung put a number in front of the reader? (#6803, see the note above.)
 *
 * `!= null` on purpose, so it is `null` AND `undefined` and nothing else — `0`
 * is a price and must vote.
 */
function showsAPrice(row: FuturesOutcome | null | undefined): boolean {
  return row?.probability != null;
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
    // #6803: a priceless rung is not a price this floor is allowed to cover.
    if (!showsAPrice(row)) continue;
    const ms = parsedTime(row?.last_updated);
    if (ms === null) continue;
    if (oldest === null || ms < oldest) oldest = ms;
  }
  if (oldest === null) return null;
  return new Date(oldest).toISOString();
}
