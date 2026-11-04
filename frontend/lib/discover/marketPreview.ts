import type { FeedBundleData, FeedFuturesData, FeedItem } from '../types';
import type { DiscoverGroupedItem } from '../../components/discover/types';
import { isComplementPair, renderedCardPercents } from '../renderedPercent';
import { marketResolved, observationOrder } from './priceRefresh';

/**
 * #10090 — a held market's venue move at arrival (`backend/app/utils/market_preview.py`).
 *
 * A `market_preview` frame is PROVISIONAL: it is overlaid on the cards the
 * page returns, never written into the price book. A leg's preview shows only
 * while (a) its ttl has not run out, (b) its `observed_at` is newer than the
 * card's committed observation for that leg — so the committed re-read with an
 * equal or newer observation replaces it — and (c) the card prints raw prices
 * (`display_scale === 1`). Frames are fenced by the publisher's per-market
 * `seq`; a reconnect or an out-of-view card drops the market's state.
 */
export interface MarketPreviewFrame {
  market_id: number;
  source: string;
  outcomes: { outcome_id: number; p: number; observed_at: string }[];
  seq: number;
  ttl_ms: number;
}
export interface MarketPreviewLeg { p: number; observedAt: string; expiresAt: number }
export interface MarketPreviewState { source: string; seq: number; legs: Record<string, MarketPreviewLeg> }
export type MarketPreviews = Record<number, MarketPreviewState>;

const positive = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value > 0;

/** A well-formed frame (an SSE event or its data string), else null. */
export function parseMarketPreview(raw: unknown): MarketPreviewFrame | null {
  try {
    const data = typeof raw === 'string' ? raw : (raw as { data?: unknown } | null)?.data;
    if (typeof data !== 'string') return null;
    const frame = JSON.parse(data) as Record<string, unknown>;
    if (!frame || typeof frame !== 'object' || frame.type !== 'market_preview' || frame.preview !== true) return null;
    if (!positive(frame.market_id) || !positive(frame.seq) || typeof frame.source !== 'string') return null;
    if (!positive(frame.ttl_ms) || frame.ttl_ms > 60_000 || !Array.isArray(frame.outcomes) || !frame.outcomes.length) return null;
    const outcomes: MarketPreviewFrame['outcomes'] = [];
    for (const row of frame.outcomes as Record<string, unknown>[]) {
      if (!row || !positive(row.outcome_id) || typeof row.p !== 'number' || !(row.p > 0 && row.p < 1) ||
          typeof row.observed_at !== 'string' || observationOrder(row.observed_at, row.observed_at) === null) return null;
      outcomes.push({ outcome_id: row.outcome_id, p: row.p, observed_at: row.observed_at });
    }
    return { market_id: frame.market_id, source: frame.source, outcomes, seq: frame.seq, ttl_ms: frame.ttl_ms };
  } catch { return null; }
}

/** Admit a frame received at `receivedAt` (monotonic ms). Returns `states` itself when refused. */
export function applyMarketPreview(states: MarketPreviews, frame: MarketPreviewFrame, receivedAt: number): MarketPreviews {
  const prior = states[frame.market_id];
  if (prior && prior.source === frame.source && frame.seq <= prior.seq) return states;
  const legs: Record<string, MarketPreviewLeg> = {};
  if (prior && prior.source === frame.source) {
    for (const [id, leg] of Object.entries(prior.legs)) if (leg.expiresAt > receivedAt) legs[id] = leg;
  }
  for (const row of frame.outcomes) {
    legs[String(row.outcome_id)] = { p: row.p, observedAt: row.observed_at, expiresAt: receivedAt + frame.ttl_ms };
  }
  return { ...states, [frame.market_id]: { source: frame.source, seq: frame.seq, legs } };
}

/** Drop these markets' previews (a reconnect, or the card left view). Returns `states` itself when none held. */
export function dropMarketPreviews(states: MarketPreviews, ids: Iterable<number>): MarketPreviews {
  let next = states;
  for (const id of ids) {
    if (!(id in next)) continue;
    if (next === states) next = { ...states };
    delete next[id];
  }
  return next;
}

/** The soonest leg expiry after `now`, or Infinity. */
export function nextMarketPreviewExpiry(states: MarketPreviews, now: number): number {
  let soonest = Infinity;
  for (const state of Object.values(states)) {
    for (const leg of Object.values(state.legs)) if (leg.expiresAt > now && leg.expiresAt < soonest) soonest = leg.expiresAt;
  }
  return soonest;
}

type MarketCard = Omit<FeedFuturesData, 'top_outcomes'> & { outcome_observed_at?: Record<string, string | null>; display_scale?: number;
  top_outcomes: (FeedFuturesData['top_outcomes'][number] & { price_observed_at?: string | null })[] };

function overlayCard(data: MarketCard, state: MarketPreviewState, now: number): MarketCard {
  if (data.display_scale !== 1 || data.source !== state.source || marketResolved(data)) return data;
  const committedRows = data.top_outcomes ?? [];
  const admitted = committedRows.map(row => {
    const leg = state.legs[String(row.id)];
    // A withheld (null) price stays withheld: the server refused it on purpose.
    if (!leg || leg.expiresAt <= now || row.probability === null || row.probability === leg.p) return null;
    const committed = data.outcome_observed_at?.[String(row.id)] ?? row.price_observed_at ?? null;
    if (committed && (observationOrder(leg.observedAt, committed) ?? 0) <= 0) return null;
    return leg.p;
  });
  if (admitted.every(p => p === null)) return data;

  // A committed complement pair prints a total of 100 (#2060), and so must its
  // preview: a one-sided move carries its complement to the other leg, and two
  // previewed legs that are not a pair keep the committed pair rather than print
  // another total. The whole percents follow the card rule for the new pair.
  if (isComplementPair(committedRows.map(row => row.probability))) {
    let pair: [number, number];
    if (admitted[0] !== null && admitted[1] !== null) {
      if (!isComplementPair(admitted)) return data;
      pair = [admitted[0], admitted[1]];
    } else if (admitted[0] !== null) {
      pair = [admitted[0], complement(admitted[0])];
    } else {
      pair = [complement(admitted[1]!), admitted[1]!];
    }
    const printed = renderedCardPercents(pair);
    return { ...data, top_outcomes: committedRows.map((row, i) =>
      ({ ...row, probability: pair[i], rendered_percent: printed[i] ?? null })) };
  }

  // Any other card: each previewed leg on its own. The served whole percent
  // describes the committed value; the card's own rounding rule decides for the
  // provisional one.
  return { ...data, top_outcomes: committedRows.map((row, i) =>
    admitted[i] === null ? row : { ...row, probability: admitted[i]!, rendered_percent: null }) };
}

/** `1 - p` on the venues' decimal grid (bare `1 - .445` is .5549999…). */
const complement = (p: number) => (1000 - p * 1000) / 1000;

/**
 * The page's cards with each held market's admitted preview overlaid. Returns
 * `groups` itself when nothing is overlaid, so a page with no previews renders
 * exactly what the price book projects.
 */
export function overlayMarketPreviews(groups: DiscoverGroupedItem[], states: MarketPreviews, now: number): DiscoverGroupedItem[] {
  if (!Object.keys(states).length) return groups;
  let changed = false;
  const project = (item: FeedItem): FeedItem => {
    if (item.type === 'bundle') {
      const bundle = item.data as FeedBundleData;
      const items = bundle.items.map(project);
      return items.every((leaf, i) => leaf === bundle.items[i]) ? item : { ...item, data: { ...bundle, items } };
    }
    if (item.type !== 'futures') return item;
    const data = item.data as MarketCard;
    const state = states[data.id];
    if (!state) return item;
    const overlaid = overlayCard(data, state, now);
    if (overlaid === data) return item;
    changed = true;
    return { ...item, data: overlaid } as FeedItem;
  };
  const next = groups.map(group => {
    if (group.type === 'single') {
      const item = group.item && project(group.item);
      return item === group.item ? group : { ...group, item };
    }
    const items = group.items?.map(project);
    return items && items.every((leaf, i) => leaf === group.items![i]) ? group : { ...group, items };
  });
  return changed ? next : groups;
}
