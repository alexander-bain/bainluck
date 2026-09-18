/**
 * When an event page's PLAYER AWARDS row is too old to be an award probability — #3117.
 *
 * The Bigger Picture team cards on an event page draw a PLAYER AWARDS list:
 * a nominee, an award label, a percentage. Measured on production
 * 2026-09-18, across 40 event pages (NFL, MLB, NHL) fetched from
 * `GET /api/events/{id}/related-futures`, the 81 rows those pages actually
 * render split perfectly in two:
 *
 *   | price age  | rows |
 *   |------------|------|
 *   | < 1 day    |   21 |
 *   | 1–7 days   |   11 |
 *   | 7–30 days  |   27 |
 *   | 30–90 days |  *0* |
 *   | 90–180     |  *0* |
 *   | > 180 days |   22 |
 *
 * There is a **206-day empty gap** in the middle. The oldest row anybody is
 * still repricing is 20.7 days old; the freshest row on the other side of the
 * gap is 226.3 days old. Every one of those 22 rows belongs to a single
 * market — 479, `Pro Football Championship MVP?`, Kalshi `KXNFLSBMVP-26` —
 * and every row of market 479 is in that bucket.
 *
 * THE MARKET IS GONE FROM THE VENUE, so those prices can never move again.
 * Read at the venue's own door, the way notice 26 requires rather than from
 * our mirror: `GET /trade-api/v2/events/KXNFLSBMVP-26?with_nested_markets=true`
 * returns the event — Kalshi EVENT data is permanent — carrying **zero**
 * markets, and `GET /markets?series_ticker=KXNFLSBMVP` returns zero at any
 * status. That is gotcha #35 doing exactly what it says: Kalshi MARKET data
 * purges at ≥74/<86 days (`app/utils/kalshi_retention.py`), and these rows
 * were last written 2026-02-04, 226 days before this was measured.
 *
 * What the reader got for it, on `/events/15304746` at 390px:
 *
 *     WS  Will Sam Darn…   MVP 45%
 *     WJ  Will Jaxon Sm…   MVP 14%
 *
 * — a February price on a market that no longer exists, printed as this
 * season's MVP odds. And the stored field it comes from sums to **1,967%**
 * across 79 nominees with **37 of them at exactly 0.500**, the untraded
 * midpoint of an independent Kalshi binary (gotcha #23), so on 8 of the 9
 * affected pages a reader is told some player is a coin flip to win MVP.
 * Alex reported that half directly (#3117, 2026-09-15): *"five identical 50%s
 * under one crest, which reads as a coin flip on each of five players for one
 * award."*
 *
 * WHY A DAY BOUND AND NOT A DEAD-MARKET LOOKUP. The payload a card holds says
 * nothing about whether the venue still lists the market; the only thing it
 * can answer is how old the price is. 90 days is not a taste call — it is
 * placed inside the measured 206-day gap, and it is the age past which a
 * Kalshi price is, by the house's own measured retention bound, necessarily
 * from a market the venue has already purged. Any bound in 21..226 selects
 * exactly the same 22 rows today; 90 is the one with a reason behind it.
 *
 * FAILS OPEN, AND THAT IS THE WHOLE SAFETY ARGUMENT. This hides rows, and a
 * filter that hides rows is unfalsifiable from the outside — a wrongly hidden
 * row leaves no trace on the page for anyone to notice. So every case it
 * cannot decide renders: no stamp, an empty stamp, an unparseable stamp, a
 * stamp in the future. The only row it removes is one whose price it can read
 * and date past the bound.
 *
 * SCOPED TO THE AWARDS BLOCK ON PURPOSE. `display_category === "award"` is the
 * only population measured above. The same event page draws championship
 * paths, season stats and game props off the same endpoint, and a rule
 * widened by grammar reaches populations the ship never reasoned about —
 * a long-dated championship future that nobody has repriced in four months
 * may be perfectly honest. Measure those before extending this to them.
 */

/** Oldest an award price may be and still be printed as a live probability. */
export const AWARD_PRICE_MAX_AGE_DAYS = 90;

const MS_PER_DAY = 86_400_000;

/**
 * Is this award row's price older than an award probability is allowed to be?
 *
 * `false` for every case it cannot decide — see FAILS OPEN above.
 *
 * @param lastUpdated `futures_outcomes.last_updated` for the row, as served.
 *   This is the PRICE row's stamp, not the market row's — the related-futures
 *   serializer reads `outcome.last_updated` (`backend/app/routes/events.py`),
 *   which is the column `futuresCardPriceAge.ts` documents as the one prices
 *   actually live in. It is not a visit stamp: it says when the value last
 *   changed, not when a poller last looked. That is why the claim here is
 *   bounded by the venue read above rather than by the column alone.
 * @param now Injected so tests need no clock. A test anchor that branches on
 *   the real clock is not an anchor (gotcha #44).
 */
export function awardPriceIsStale(
  lastUpdated: string | null | undefined,
  now: Date = new Date(),
): boolean {
  if (typeof lastUpdated !== "string" || lastUpdated === "") return false;
  const written = new Date(lastUpdated).getTime();
  if (!Number.isFinite(written)) return false;
  const ageDays = (now.getTime() - written) / MS_PER_DAY;
  if (!Number.isFinite(ageDays)) return false;
  return ageDays > AWARD_PRICE_MAX_AGE_DAYS;
}
