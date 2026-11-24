/**
 * #10090: Live committed `/api/feed/price-cards` + provisional SSE price overlays
 * (`authority-v3` for live/upcoming matchup children, `market_preview` for open
 * `evolution_market_id` / `props_script` markets, and debounced envelope refresh
 * on market/event invalidations) for `/event/[domain]/[slug]`.
 *
 * Honors settled-means-settled (#12506 / settled children & settled props_script
 * never overwritten) and #13509 (three-way / soccer matchups never fabricate
 * `1 - p` away probability when `p_away` is null).
 */
import { displayedPreview, type BlendPreviewState } from '@/lib/blendPreview';
import type { MarketPreviews } from '@/lib/discover/marketPreview';
import type { DiscoverPriceCards } from '@/lib/discover/priceRefresh';
import { sportPricesADraw } from '@/lib/drawPricedWinner';
import { isFinishedStatus } from '@/lib/eventState';
import { compareFoldRevision, parseFoldRevision, type FoldRevision } from '@/lib/foldRevision';
import type {
  EventConceptChild,
  EventConceptCompetitor,
  EventConceptResponse,
  FeedEventData,
} from '@/lib/types';

export interface HeldConceptMatchup {
  status: string;
  revision: FoldRevision;
  observedMs: number | null;
  homeProbability: number | null;
  awayProbability: number | null;
  heroSource: string | null;
  homeScore: number | null;
  awayScore: number | null;
}

export type ConceptMatchupBook = Map<number, HeldConceptMatchup>;

export function eventConceptMatchupStreamable(
  child: EventConceptChild,
  conceptStatus: string,
): boolean {
  if (conceptStatus === 'settled') return false;
  if (child.kind !== 'matchup' || typeof child.event_id !== 'number' || child.event_id <= 0) {
    return false;
  }
  if (child.settled) return false;
  if (isFinishedStatus(child.status)) return false;
  return true;
}

export function eventConceptMatchups(data: EventConceptResponse | undefined): EventConceptChild[] {
  if (!data || data.event.status === 'settled') return [];
  const seen = new Set<number>();
  const out: EventConceptChild[] = [];
  for (const child of data.children ?? []) {
    if (!eventConceptMatchupStreamable(child, data.event.status)) continue;
    const eid = child.event_id!;
    if (seen.has(eid)) continue;
    seen.add(eid);
    out.push(child);
  }
  return out;
}

export function eventConceptMarketIds(data: EventConceptResponse | undefined): number[] {
  if (!data || data.event.status === 'settled') return [];
  const ids = new Set<number>();
  if (
    typeof data.primary?.evolution_market_id === 'number' &&
    data.primary.evolution_market_id > 0
  ) {
    ids.add(data.primary.evolution_market_id);
  }
  for (const child of data.children ?? []) {
    if (child.settled) continue;
    if (typeof child.market_id === 'number' && child.market_id > 0) ids.add(child.market_id);
  }
  for (const prop of data.props_script ?? []) {
    if (prop.settled) continue;
    if (typeof prop.market_id === 'number' && prop.market_id > 0) ids.add(prop.market_id);
  }
  for (const section of data.sections ?? []) {
    for (const id of section.market_ids ?? []) {
      if (typeof id === 'number' && id > 0) ids.add(id);
    }
  }
  return [...ids];
}

function parseMs(raw: unknown): number | null {
  if (typeof raw !== 'string' || !raw) return null;
  const parsed = Date.parse(raw);
  return Number.isFinite(parsed) ? parsed : null;
}

export function adoptConceptMatchupCards(
  book: ConceptMatchupBook,
  matchups: EventConceptChild[],
  response: DiscoverPriceCards,
  requested: Set<number>,
): ConceptMatchupBook {
  if (!Array.isArray(response?.items)) return book;
  const byId = new Map(matchups.map((m) => [m.event_id!, m]));
  let next = book;
  for (const item of response.items) {
    if (item.type !== 'event') continue;
    const fresh = item.data as FeedEventData & {
      blend_fold_revision?: unknown;
      hero_probability_observed_at?: string | null;
      hero_probability_source?: string | null;
    };
    const served = byId.get(fresh.id);
    if (!served || !requested.has(fresh.id)) continue;
    if (response.dispositions?.[`event-${fresh.id}`] !== 'updated') continue;
    const servedStatus = served.status ?? 'scheduled';
    const finished = servedStatus === 'live' && isFinishedStatus(fresh.status);
    if (fresh.status !== servedStatus && !finished) continue;
    const revision = parseFoldRevision(fresh.blend_fold_revision);
    if (!revision) continue;
    if (finished && (typeof fresh.home_score !== 'number' || typeof fresh.away_score !== 'number')) {
      continue;
    }

    const observedMs = parseMs(fresh.hero_probability_observed_at);
    const held = next.get(fresh.id);
    if (held && isFinishedStatus(held.status)) continue;
    if (held) {
      const order = compareFoldRevision(revision, held.revision);
      if (order !== 'newer' && order !== 'same') continue;
      if (
        !finished &&
        held.observedMs !== null &&
        (observedMs === null || observedMs < held.observedMs)
      ) {
        continue;
      }
    }

    const matchup: HeldConceptMatchup = {
      status: fresh.status,
      revision,
      observedMs,
      homeProbability: fresh.current_odds?.home_probability ?? null,
      awayProbability: fresh.current_odds?.away_probability ?? null,
      heroSource: fresh.hero_probability_source ?? null,
      homeScore: fresh.home_score ?? null,
      awayScore: fresh.away_score ?? null,
    };
    if (held && JSON.stringify(held) === JSON.stringify(matchup)) continue;
    if (next === book) next = new Map(book);
    next.set(fresh.id, matchup);
  }
  return next;
}

export function patchConceptMatchupChild(
  child: EventConceptChild,
  domain: string,
  book: ConceptMatchupBook,
  preview: BlendPreviewState | null | undefined,
  now: number,
): EventConceptChild {
  if (child.kind !== 'matchup' || typeof child.event_id !== 'number' || child.settled) return child;
  const held = book.get(child.event_id);
  let next = child;

  if (held) {
    if (held.status !== (next.status ?? 'scheduled') && isFinishedStatus(held.status)) {
      next = {
        ...next,
        status: held.status,
        home: next.home ? { ...next.home, score: held.homeScore } : next.home,
        away: next.away ? { ...next.away, score: held.awayScore } : next.away,
      };
    } else if (!isFinishedStatus(next.status)) {
      const nextHome =
        next.home && (held.homeProbability !== null || held.homeScore !== null)
          ? {
              ...next.home,
              ...(held.homeProbability !== null ? { probability: held.homeProbability } : {}),
              ...(held.homeScore !== null ? { score: held.homeScore } : {}),
            }
          : next.home;
      const nextAway =
        next.away && (held.awayProbability !== null || held.awayScore !== null)
          ? {
              ...next.away,
              ...(held.awayProbability !== null ? { probability: held.awayProbability } : {}),
              ...(held.awayScore !== null ? { score: held.awayScore } : {}),
            }
          : next.away;
      if (nextHome !== next.home || nextAway !== next.away) {
        next = { ...next, home: nextHome, away: nextAway };
      }
    }
  }

  if (!preview || isFinishedStatus(next.status)) return next;

  const meta = next as EventConceptChild & {
    blend_fold_revision?: unknown;
    hero_probability_source?: string | null;
    sport?: string | null;
  };
  const status = held?.status ?? next.status ?? 'scheduled';
  const sport = meta.sport ?? (domain === 'soccer' ? 'soccer' : null);
  const p = displayedPreview(
    preview,
    {
      id: child.event_id,
      status,
      hero_probability_source: held?.heroSource ?? meta.hero_probability_source ?? null,
      blend_fold_revision: held?.revision ?? meta.blend_fold_revision,
      sport,
    },
    now,
  );
  if (p === null) return next;

  const hasDraw =
    domain === 'soccer' ||
    sportPricesADraw(sport) ||
    (next as { draw_probability?: number | null }).draw_probability != null;
  if (hasDraw && preview.pAway == null) return next;

  const awayP = preview.pAway != null ? preview.pAway : Number((1 - p).toFixed(6));
  return {
    ...next,
    home: next.home ? { ...next.home, probability: p } : next.home,
    away: next.away ? { ...next.away, probability: awayP } : next.away,
  };
}

function patchCompetitorFromPreview(
  comp: EventConceptCompetitor,
  marketId: number,
  previews: MarketPreviews,
  now: number,
): EventConceptCompetitor {
  if (comp.won || comp.eliminated === true) return comp;
  if (comp.eliminated && typeof comp.eliminated === 'object' && comp.eliminated.out) return comp;
  if (typeof comp.outcome_id !== 'number' || comp.probability === null) return comp;
  const state = previews[marketId];
  if (!state) return comp;
  const leg = state.legs[String(comp.outcome_id)];
  if (!leg || leg.expiresAt <= now || leg.p === comp.probability) return comp;
  return { ...comp, probability: leg.p, rendered_percent: null };
}

export function applyEventConceptLivePrices(
  data: EventConceptResponse | undefined,
  book: ConceptMatchupBook,
  eventPreviews: Record<number, BlendPreviewState>,
  eventNow: number,
  marketPreviews: MarketPreviews,
  marketNow: number,
): EventConceptResponse | undefined {
  if (!data || data.event.status === 'settled') return data;

  const evoId = data.primary?.evolution_market_id ?? null;
  let competitorsChanged = false;
  const nextCompetitors =
    typeof evoId === 'number' && marketPreviews[evoId]
      ? data.primary.competitors.map((comp) => {
          const updated = patchCompetitorFromPreview(comp, evoId, marketPreviews, marketNow);
          if (updated !== comp) competitorsChanged = true;
          return updated;
        })
      : data.primary.competitors;

  let childrenChanged = false;
  const nextChildren = data.children.map((child) => {
    const updated =
      child.kind === 'matchup' && typeof child.event_id === 'number'
        ? patchConceptMatchupChild(
            child,
            data.event.domain,
            book,
            eventPreviews[child.event_id],
            eventNow,
          )
        : child;
    if (updated !== child) childrenChanged = true;
    return updated;
  });

  if (!competitorsChanged && !childrenChanged) return data;
  return {
    ...data,
    primary: competitorsChanged
      ? { ...data.primary, competitors: nextCompetitors }
      : data.primary,
    children: childrenChanged ? nextChildren : data.children,
  };
}
