/**
 * #10090: Patch CollectionSection.visualBlock items from the collection's
 * live `pricedByKey` map (committed `/api/feed/price-cards` + provisional
 * `authority-v3` / `market_preview` overlays) so machinery sections update
 * alongside standard collection cards without reload.
 */
import type { MachineryOutcomeVisual, MachineryVisualBlock } from '@/lib/collections';
import { sportPricesADraw } from '@/lib/drawPricedWinner';
import { isFinishedStatus } from '@/lib/eventState';
import { renderedDuelPercents, renderedPercent } from '@/lib/renderedPercent';
import type { FeedEventData, FeedFuturesData, FeedItem } from '@/lib/types';

function outcomeRenderedPercent(
  row: { probability?: number | null; rendered_percent?: number | null },
): number | null {
  if (typeof row.rendered_percent === 'number' && Number.isFinite(row.rendered_percent)) {
    return row.rendered_percent;
  }
  return renderedPercent(row.probability);
}

function patchVisualOutcomes(
  outcomes: MachineryOutcomeVisual[] | undefined,
  futuresData: FeedFuturesData,
): MachineryOutcomeVisual[] | undefined {
  if (!outcomes?.length || futuresData.status === 'resolved' || futuresData.status === 'settled') {
    return outcomes;
  }
  const byId = new Map<number, { probability: number; pct: number }>();
  for (const row of futuresData.top_outcomes ?? []) {
    if (typeof row.probability === 'number' && Number.isFinite(row.probability)) {
      const pct = outcomeRenderedPercent(row);
      if (pct !== null) {
        byId.set(row.id, { probability: row.probability, pct });
      }
    }
  }
  let changed = false;
  const next = outcomes.map((o) => {
    if (o.settled_out) return o;
    const hit = byId.get(o.outcome_id);
    if (!hit || (hit.probability === o.probability && hit.pct === o.rendered_percent)) return o;
    changed = true;
    const nextUnfloored = renderedPercent(hit.probability) ?? hit.pct;
    return {
      ...o,
      probability: hit.probability,
      rendered_percent: hit.pct,
      ...("unfloored_percent" in o ? { unfloored_percent: nextUnfloored } : {}),
    };
  });
  return changed ? next : outcomes;
}

export function patchMachineryVisualBlock(
  visualBlock: MachineryVisualBlock,
  pricedByKey: Map<string, FeedItem>,
): MachineryVisualBlock {
  if (!visualBlock.items?.length || pricedByKey.size === 0) return visualBlock;

  let changed = false;
  const nextItems = visualBlock.items.map((item) => {
    if (visualBlock.form_id === 'coin_flip_matchups') {
      const eid = Number(item.event_id ?? 0);
      const feedItem = eid > 0 ? pricedByKey.get(`event-${eid}`) : undefined;
      if (!feedItem || feedItem.type !== 'event') return item;
      const ev = feedItem.data as FeedEventData;
      if (isFinishedStatus(ev.status) || !ev.current_odds) return item;
      const drawProb = (ev.current_odds as { draw_probability?: number | null }).draw_probability;
      const hasDraw = sportPricesADraw(ev.sport) || drawProb != null;
      const homeP = ev.current_odds.home_probability;
      const awayP = ev.current_odds.away_probability;
      if (typeof homeP !== 'number' || !Number.isFinite(homeP)) return item;
      if (hasDraw && (typeof awayP !== 'number' || !Number.isFinite(awayP))) return item;
      const resolvedAwayP = typeof awayP === 'number' && Number.isFinite(awayP) ? awayP : 1 - homeP;
      const servedHome = ev.current_odds.home_rendered_percent;
      const servedAway = ev.current_odds.away_rendered_percent;
      let homePct: number | null;
      let awayPct: number | null;
      if (
        typeof servedHome === 'number' &&
        Number.isInteger(servedHome) &&
        typeof servedAway === 'number' &&
        Number.isInteger(servedAway)
      ) {
        homePct = servedHome;
        awayPct = servedAway;
      } else {
        const [pairedAway, pairedHome] = renderedDuelPercents(resolvedAwayP, homeP);
        awayPct = pairedAway ?? renderedPercent(resolvedAwayP);
        homePct = pairedHome ?? renderedPercent(homeP);
      }
      if (homePct === null || awayPct === null) return item;
      if (item.home_pct === homePct && item.away_pct === awayPct) return item;
      changed = true;
      return { ...item, home_pct: homePct, away_pct: awayPct };
    }

    const mid = Number(item.market_id ?? 0);
    const feedItem = mid > 0 ? pricedByKey.get(`futures-${mid}`) : undefined;
    if (!feedItem || feedItem.type !== 'futures') return item;
    const futuresData = feedItem.data as FeedFuturesData;

    if (visualBlock.form_id === 'probability_history_chart') {
      const series = item.series as
        | { outcome_id: number; current_pct: number; [k: string]: unknown }[]
        | undefined;
      if (!series?.length || futuresData.status === 'resolved' || futuresData.status === 'settled') {
        return item;
      }
      const byId = new Map<number, number>();
      for (const row of futuresData.top_outcomes ?? []) {
        if (typeof row.probability === 'number' && Number.isFinite(row.probability)) {
          const pct = outcomeRenderedPercent(row);
          if (pct !== null) byId.set(row.id, pct);
        }
      }
      let seriesChanged = false;
      const nextSeries = series.map((s) => {
        const pct = byId.get(s.outcome_id);
        if (pct === undefined || pct === s.current_pct) return s;
        seriesChanged = true;
        return { ...s, current_pct: pct };
      });
      if (!seriesChanged) return item;
      changed = true;
      return { ...item, series: nextSeries };
    }

    const outcomes = item.outcomes as MachineryOutcomeVisual[] | undefined;
    const patchedOutcomes = patchVisualOutcomes(outcomes, futuresData);
    if (patchedOutcomes === outcomes) return item;
    changed = true;
    return { ...item, outcomes: patchedOutcomes };
  });

  return changed ? { ...visualBlock, items: nextItems } : visualBlock;
}
