/**
 * #10090 — the team page's season-futures rows re-price live.
 *
 * `/api/feed/price-cards` returns a market's `top_outcomes` only, and a team's
 * leg of a 30-way field is rarely among them; the team page itself is a
 * 2.7-5.8 s read (Nov 9). So the page re-reads just its rows by outcome id
 * (`/api/feed/outcome-prices`) when `/api/markets/stream` says one of their
 * markets moved.
 *
 * THE RULES:
 * * **Never backwards.** A row's `price_revision_at` must be the same or newer
 *   than the one held; an older reading is ignored.
 * * **A refusal clears the number.** `withheld` or `closed` means the page
 *   would no longer serve that price, so the row shows no probability or move.
 * * **Unknown is not a refusal.** `missing` / `unresolved` change nothing.
 * * **Row fields only.** Probability, 24h move, rank, field size and graded
 *   winner; names, tiers and which rows the page shows stay as served.
 */
import type { TeamFutureItem } from '@/lib/api';

export interface OutcomePriceItem {
  outcome_id: number;
  market_id: number;
  probability: number | null;
  probability_change_24h: number | null;
  rank: number | null;
  total_outcomes: number | null;
  is_winner: boolean;
  price_revision_at: string | null;
}

export interface OutcomePricesResponse {
  items: OutcomePriceItem[];
  dispositions: Record<string, string>;
  built_at: number;
}

export interface HeldOutcome {
  revisionMs: number | null;
  refused: boolean;
  item: OutcomePriceItem | null;
}
export type TeamOutcomeBook = Map<number, HeldOutcome>;

const REFUSALS = new Set(['withheld', 'closed']);

function ms(raw: string | null | undefined): number | null {
  if (!raw) return null;
  const value = Date.parse(raw);
  return Number.isFinite(value) ? value : null;
}

/** The book after one answer; `book` itself when nothing was adopted. */
export function adoptOutcomePrices(
  book: TeamOutcomeBook,
  response: OutcomePricesResponse | null | undefined,
  requested: ReadonlySet<number>,
): TeamOutcomeBook {
  if (!response || !Array.isArray(response.items) || !response.dispositions) return book;
  const items = new Map(response.items.map((item) => [item.outcome_id, item]));
  let next = book;
  const put = (id: number, held: HeldOutcome) => {
    if (next === book) next = new Map(book);
    next.set(id, held);
  };
  for (const id of requested) {
    const disposition = response.dispositions[`outcome-${id}`];
    const held = next.get(id);
    if (disposition && REFUSALS.has(disposition)) {
      if (!held?.refused) put(id, { revisionMs: held?.revisionMs ?? null, refused: true, item: null });
      continue;
    }
    if (disposition !== 'updated') continue;
    const item = items.get(id);
    if (!item) continue;
    const revisionMs = ms(item.price_revision_at);
    if (held && held.revisionMs !== null && (revisionMs === null || revisionMs < held.revisionMs)) continue;
    if (held?.item && !held.refused && JSON.stringify(held.item) === JSON.stringify(item)) continue;
    put(id, { revisionMs, refused: false, item });
  }
  return next;
}

/** The served row with its adopted reading applied; `row` itself when nothing changed. */
export function patchTeamFuture(row: TeamFutureItem, book: TeamOutcomeBook): TeamFutureItem {
  const held = book.get(row.outcome_id);
  if (!held) return row;
  if (held.refused) {
    if (row.probability === null && row.probability_change_24h === null) return row;
    return { ...row, probability: null, probability_change_24h: null };
  }
  const item = held.item;
  if (!item || item.market_id !== row.market_id) return row;
  const next = {
    ...row,
    probability: item.probability,
    probability_change_24h: item.probability_change_24h,
    rank: item.rank,
    total_outcomes: item.total_outcomes,
    is_winner: item.is_winner,
  };
  const same = next.probability === row.probability && next.probability_change_24h === row.probability_change_24h
    && next.rank === row.rank && next.total_outcomes === row.total_outcomes
    && Boolean(next.is_winner) === Boolean(row.is_winner);
  return same ? row : next;
}
