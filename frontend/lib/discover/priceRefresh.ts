import type { FeedBundleData, FeedEventData, FeedFuturesData, FeedItem } from '../types';
import type { DiscoverGroupedItem } from '../../components/discover/types';
import { compareFoldRevision, parseFoldRevision } from '../foldRevision';
import { isFinishedStatus } from '../eventState';

export interface DiscoverPriceCards {
  items: FeedItem[];
  dispositions: Record<string, 'updated' | 'withheld' | 'missing' | 'unresolved'>;
  built_at: number;
}
type EventQuote = FeedEventData & { blend_fold_revision?: unknown; hero_probability_observed_at?: string | null;
  hero_probability_source?: string | null; hero_probability_away?: number | null };
type MarketQuote = Omit<FeedFuturesData, 'top_outcomes'> & {
  outcome_observed_at?: Record<string, string | null>;
  external_id?: string | null;
  group_type?: string | null;
  top_outcomes: (FeedFuturesData['top_outcomes'][number] & { price_observed_at?: string | null })[];
};
interface MarketFence { clocks: Record<string, string | null>; withdrawn: string[] }
export type PriceBook = Map<string, { item: FeedItem; builtAt: number; marketFence?: MarketFence }>;

export function priceKey(item: FeedItem): string | null {
  return item.type === 'event' || item.type === 'futures' ? `${item.type}-${(item.data as { id: number }).id}` : null;
}
export function priceLeaves(items: FeedItem[]): FeedItem[] {
  return items.flatMap(item => item.type === 'bundle' ? priceLeaves((item.data as FeedBundleData).items) : priceKey(item) ? [item] : []);
}
export function groupedLeaves(groups: DiscoverGroupedItem[]): FeedItem[] {
  const seen = new Set<string>();
  return priceLeaves(groups.flatMap(group => group.type === 'single' ? (group.item ? [group.item] : []) : group.items ?? []))
    .filter(item => { const key = priceKey(item)!; if (seen.has(key)) return false; seen.add(key); return true; });
}
export function marketResolved(data: FeedFuturesData): boolean {
  return data.resolved === true || !!data.winner?.trim() || ['resolved', 'closed', 'settled', 'finalized', 'final'].includes(data.status);
}

// Date.parse truncates sub-millisecond stamps. Preserve the stored fractional
// component so one outcome's newer microsecond cannot hide another's rollback.
function clock(raw: string | null | undefined): { seconds: number; fraction: string } | null {
  if (!raw) return null;
  const match = raw.match(/^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d+))?(Z|[+-]\d\d:\d\d)$/);
  if (!match) return null;
  const seconds = Date.parse(match[1] + match[3]);
  return Number.isFinite(seconds) ? { seconds, fraction: (match[2] ?? '').padEnd(9, '0').slice(0, 9) } : null;
}
function orderClock(next: ReturnType<typeof clock>, prior: NonNullable<ReturnType<typeof clock>>): number {
  if (!next) return -1;
  return next.seconds === prior.seconds ? (next.fraction > prior.fraction ? 1 : next.fraction < prior.fraction ? -1 : 0)
    : next.seconds > prior.seconds ? 1 : -1;
}

function marketClocks(data: MarketQuote): Record<string, string | null> {
  const clocks = { ...data.outcome_observed_at };
  for (const row of data.top_outcomes ?? []) {
    if (!(String(row.id) in clocks) && row.price_observed_at) clocks[String(row.id)] = row.price_observed_at;
  }
  return clocks;
}
function priced(data: MarketQuote, id: string): boolean {
  return data.top_outcomes?.some(row => String(row.id) === id && row.probability !== null) ?? false;
}

export function canAdoptPrice(incoming: FeedItem, held: FeedItem, withheld = false,
  options: { authoritative?: boolean; fence?: MarketFence } = {}): boolean {
  if (priceKey(incoming) !== priceKey(held) || incoming.type !== held.type) return false;
  if (held.type === 'event') {
    const old = held.data as EventQuote, next = incoming.data as EventQuote;
    if (isFinishedStatus(old.status) && !isFinishedStatus(next.status)) return false;
    if (!isFinishedStatus(old.status) && isFinishedStatus(next.status)) return true;
    const prior = parseFoldRevision(old.blend_fold_revision), revision = parseFoldRevision(next.blend_fold_revision);
    if (prior) {
      if (!revision) return false;
      const order = compareFoldRevision(revision, prior);
      if (order !== 'same' && order !== 'newer') return false;
      if (order === 'newer' || (withheld && !next.current_odds)) return true;
      // One complete fold revision binds one hero. Equal/unknown clocks do
      // not license another value or restore an explicitly withdrawn quote.
      if (!!old.current_odds !== !!next.current_odds ||
          old.current_odds?.home_probability !== next.current_odds?.home_probability ||
          old.current_odds?.away_probability !== next.current_odds?.away_probability ||
          (old.hero_probability_source != null && old.hero_probability_source !== next.hero_probability_source) ||
          (old.hero_probability_away != null && old.hero_probability_away !== next.hero_probability_away)) return false;
    }
    const priorClock = clock(old.hero_probability_observed_at);
    return !priorClock || orderClock(clock(next.hero_probability_observed_at), priorClock) >= 0;
  }
  if (held.type !== 'futures') return false;
  const old = held.data as MarketQuote, next = incoming.data as MarketQuote;
  if (old.source !== next.source || old.group_id !== next.group_id || old.group_type !== next.group_type ||
      old.canonical_market_key !== next.canonical_market_key ||
      (old.external_id && next.external_id && old.external_id !== next.external_id)) return false;
  if (old.winner?.trim() && old.winner.trim() !== next.winner?.trim()) return false;
  if (marketResolved(old) && !marketResolved(next)) return false;
  if (!marketResolved(old) && marketResolved(next)) return true;
  const priorClocks = { ...marketClocks(old), ...options.fence?.clocks };
  const nextClocks = marketClocks(next);
  let advanced = false;
  for (const [id, stamp] of Object.entries(priorClocks)) {
    const prior = clock(stamp);
    if (!prior) continue;
    const nextClock = clock(nextClocks[id]);
    const order = orderClock(nextClock, prior);
    // A fresh projection can withdraw an undatable leg. Keep its previous
    // watermark separately; never attach that clock to the new body.
    if (order < 0 && !(options.authoritative && !nextClock && !priced(next, id) &&
        (priced(old, id) || options.fence?.withdrawn.includes(id)))) return false;
    advanced ||= order > 0;
  }
  const withdrawn = new Set([...(options.fence?.withdrawn ?? []),
    ...(old.top_outcomes ?? []).filter(row => row.probability === null).map(row => String(row.id))]);
  for (const id of withdrawn) {
    if (!priced(next, id)) continue;
    const prior = clock(priorClocks[id]), nextClock = clock(nextClocks[id]);
    if (!nextClock || (prior && orderClock(nextClock, prior) <= 0)) return false;
  }
  if (Object.keys(priorClocks).length && !advanced) {
    const rows = old.top_outcomes ?? [], incomingRows = next.top_outcomes ?? [];
    const withdrawal = options.authoritative && rows.some(row => priced(old, String(row.id)) && !priced(next, String(row.id))) &&
      incomingRows.every(row => rows.some(prior => prior.id === row.id));
    if (!withdrawal && (rows.length !== incomingRows.length || rows.some((row, i) => row.id !== incomingRows[i].id || row.probability !== incomingRows[i].probability))) return false;
  }
  const prior = clock(old.price_observed_at);
  return Object.keys(priorClocks).length > 0 || !prior || orderClock(clock(next.price_observed_at), prior) >= 0;
}

export function strictlyNewerPrice(incoming: FeedItem, held: FeedItem, fence?: MarketFence): boolean {
  if (!canAdoptPrice(incoming, held, false, { fence })) return false;
  if (held.type === 'event') {
    const old = held.data as EventQuote, next = incoming.data as EventQuote;
    const prior = parseFoldRevision(old.blend_fold_revision), revision = parseFoldRevision(next.blend_fold_revision);
    if (prior && revision) return compareFoldRevision(revision, prior) === 'newer' || (!isFinishedStatus(old.status) && isFinishedStatus(next.status));
  }
  return !canAdoptPrice(held, incoming);
}

function retainedMarketFence(incoming: FeedItem, held: FeedItem, previous?: MarketFence): MarketFence | undefined {
  if (incoming.type !== 'futures') return undefined;
  const old = held.data as MarketQuote, next = incoming.data as MarketQuote;
  const priorClocks = { ...marketClocks(old), ...previous?.clocks }, nextClocks = marketClocks(next);
  const clocks = { ...priorClocks }, withdrawn = new Set(previous?.withdrawn ?? []);
  let advanced = false;
  for (const [id, stamp] of Object.entries(nextClocks)) {
    const current = clock(stamp), prior = clock(priorClocks[id]);
    if (current && (!prior || orderClock(current, prior) > 0)) { clocks[id] = stamp; advanced = true; }
    else if (!(id in clocks)) clocks[id] = stamp;
    if (priced(next, id) && current && (!prior || orderClock(current, prior) > 0)) withdrawn.delete(id);
  }
  for (const row of old.top_outcomes ?? []) {
    const id = String(row.id);
    if (priced(old, id) && !priced(next, id) && (!advanced || !clock(nextClocks[id]))) withdrawn.add(id);
  }
  // An explicit null is a withdrawal even while another raw leg advances.
  // Absence alone can instead be a legitimate change to the top-N selection.
  for (const row of next.top_outcomes ?? []) if (row.probability === null) withdrawn.add(String(row.id));
  return { clocks, withdrawn: [...withdrawn] };
}

function withPriceBody(held: FeedItem, fresh: FeedItem): FeedItem {
  // Keep editorial identity/copy and image treatment while replacing the whole
  // normalized source/price body. Never manufacture a standalone group price.
  const data = { ...fresh.data } as unknown as Record<string, unknown>;
  const old = held.data as unknown as Record<string, unknown>;
  for (const key of ['name', 'hook_description', 'image_url', 'image_width', 'image_height']) {
    if (key in old) data[key] = old[key];
  }
  return { ...held, data: data as unknown as FeedItem['data'] };
}

export function projectPriceGroups(groups: DiscoverGroupedItem[], book: PriceBook): DiscoverGroupedItem[] {
  const project = (item: FeedItem): FeedItem => {
    if (item.type === 'bundle') {
      const bundle = item.data as FeedBundleData;
      return { ...item, data: { ...bundle, items: bundle.items.map(project) } };
    }
    const held = book.get(priceKey(item) ?? '');
    return held ? withPriceBody(item, held.item) : item;
  };
  return groups.map(group => group.type === 'single' ? { ...group, item: group.item && project(group.item) }
    : { ...group, items: group.items?.map(project) });
}

/** Advance the retained fence when an ordinary feed genuinely has newer data. */
export function reconcilePriceBook(groups: DiscoverGroupedItem[], book: PriceBook): PriceBook {
  let next = book;
  for (const item of groupedLeaves(groups)) {
    const key = priceKey(item)!, held = book.get(key);
    if (held && strictlyNewerPrice(item, held.item, held.marketFence)) {
      if (next === book) next = new Map(book);
      next.set(key, { ...held, item, marketFence: retainedMarketFence(item, held.item, held.marketFence) });
    }
  }
  return next;
}

export function adoptPriceCards(book: PriceBook, painted: FeedItem[], response: DiscoverPriceCards, allowed: Set<string>): PriceBook {
  if (!Number.isFinite(response.built_at) || !Array.isArray(response.items)) return book;
  const current = new Map(painted.map(item => [priceKey(item), item]));
  let next = book;
  for (const item of response.items) {
    const key = priceKey(item), old = key && current.get(key), disposition = key && response.dispositions[key];
    if (!key || !old || !allowed.has(key) || !['updated', 'withheld'].includes(disposition || '') ||
        response.built_at < (book.get(key)?.builtAt ?? -Infinity) || !canAdoptPrice(item, old, disposition === 'withheld',
          { authoritative: true, fence: book.get(key)?.marketFence })) continue;
    if (next === book) next = new Map(book);
    next.set(key, { item: withPriceBody(old, item), builtAt: response.built_at,
      marketFence: retainedMarketFence(item, old, book.get(key)?.marketFence) });
  }
  return next;
}
