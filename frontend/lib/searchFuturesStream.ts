/**
 * #10090 — Search's futures cards re-price live, the way Discover's do.
 *
 * The transport is the same one Discover and Sports use: `/api/markets/stream`
 * reports that a market moved, and the page re-reads it through
 * `/api/feed/price-cards`. What differs is the card. Search renders
 * `FuturesMarket` (the `/api/events/search` shape), which carries none of the
 * group/listing identity Discover's price book fences on, so this module keeps
 * its own, smaller book: per OUTCOME, the newest price and the row revision it
 * came with.
 *
 * THE RULES ON THE WAY IN AND BACK:
 *
 * * **Patch by outcome id, prices only.** `price-cards` runs the feed scorer,
 *   whose top outcomes can differ from the rows Search chose for this card. A
 *   fresh body never swaps the card's rows; it re-prices the rows the reader is
 *   already looking at, and a row it does not carry keeps its served price.
 * * **Never backwards.** A fresh leg is adopted only when its
 *   `price_revision_at` is no older than the one already adopted for that leg.
 *   A leg with no revision clock is adopted only if nothing dated is held.
 * * **Same listing.** The fresh card must be the same market id and source,
 *   with disposition `updated`.
 * * **Open markets only.** A market that settles while the page is open keeps
 *   its last served price until the next search read, as before this change:
 *   Search's settled rendering needs fields (`resolution_source`,
 *   `settlement_display`) that a price card does not carry.
 * * `prices_updated_at` is left alone. It is a FLOOR over the drawn rows
 *   (#6018), and a floor stays true when some of those rows get newer.
 *
 * Provisional `market_preview` moves are not shown here yet.
 */
import type { FeedFuturesData, FuturesMarket } from '@/lib/types';
import { marketResolved, type DiscoverPriceCards } from '@/lib/discover/priceRefresh';

/** One adopted leg: its price (null = withheld by the server) and revision. */
export interface HeldLeg {
  probability: number | null;
  revision: number | null;
}
/** market id → outcome id → adopted leg. */
export type SearchPriceBook = Map<number, Map<number, HeldLeg>>;

export function searchFuturesStreamable(market: FuturesMarket): boolean {
  return market.status === 'open' &&
    ['kalshi', 'polymarket'].includes(market.source ?? '') &&
    market.related_game_listing == null;
}

function revisionMs(raw: unknown): number | null {
  if (typeof raw !== 'string' || !raw) return null;
  const ms = Date.parse(raw);
  return Number.isFinite(ms) ? ms : null;
}

/**
 * The book after one `price-cards` answer. Returns `book` itself when nothing
 * was adopted, so a React state update can bail out.
 */
export function adoptSearchPriceCards(
  book: SearchPriceBook,
  markets: FuturesMarket[],
  response: DiscoverPriceCards,
  requested: Set<number>,
): SearchPriceBook {
  if (!Array.isArray(response?.items)) return book;
  const byId = new Map(markets.map((m) => [m.id, m]));
  let next = book;
  for (const item of response.items) {
    if (item.type !== 'futures') continue;
    const fresh = item.data as FeedFuturesData;
    const market = byId.get(fresh.id);
    if (!market || !requested.has(fresh.id) || !searchFuturesStreamable(market)) continue;
    if (response.dispositions?.[`futures-${fresh.id}`] !== 'updated') continue;
    if (fresh.source !== market.source || marketResolved(fresh)) continue;
    const held = next.get(fresh.id);
    let legs: Map<number, HeldLeg> | null = null;
    for (const row of fresh.top_outcomes ?? []) {
      const prior = held?.get(row.id);
      const revision = revisionMs((row as { price_revision_at?: unknown }).price_revision_at);
      if (prior) {
        if (prior.revision !== null && (revision === null || revision < prior.revision)) continue;
        if (prior.probability === row.probability && prior.revision === revision) continue;
      }
      legs ??= new Map(held ?? []);
      legs.set(row.id, { probability: row.probability ?? null, revision });
    }
    if (!legs) continue;
    if (next === book) next = new Map(book);
    next.set(fresh.id, legs);
  }
  return next;
}

/**
 * The search card with its shown rows re-priced from the book. Returns
 * `market` itself when nothing changed, so memoised children do not re-render.
 */
export function patchSearchFutures(market: FuturesMarket, book: SearchPriceBook): FuturesMarket {
  const legs = book.get(market.id);
  if (!legs || !searchFuturesStreamable(market)) return market;
  const patchRows = (rows: FuturesMarket['outcomes']) => {
    if (!rows) return rows;
    let changed = false;
    const next = rows.map((row) => {
      const leg = legs.get(row.id);
      if (!leg || leg.probability === row.probability) return row;
      changed = true;
      return { ...row, probability: leg.probability };
    });
    return changed ? next : rows;
  };
  const top = patchRows(market.top_outcomes);
  const all = patchRows(market.outcomes);
  if (top === market.top_outcomes && all === market.outcomes) return market;
  return { ...market, top_outcomes: top, outcomes: all };
}
