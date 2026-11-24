/**
 * #10090 — the team page's championship-path card re-prices live without a reload.
 *
 * A championship-path step averages equivalent venues, withholds a step whose
 * venues disagree beyond 0.25 (`_TIER_AGREEMENT_BAR`), and carries grid
 * verdicts (`eliminated` / `won`). These pure rules:
 *   - Subscribe to every candidate market (`championship_path_market_ids` and
 *     each step's `market_ids`, falling back to `entry.market_id` during a
 *     split deploy).
 *   - Apply `market_preview` provisional moves immediately (`< 50 ms`) across
 *     matching `(market_id, outcome_id, source)` components, recomputing the
 *     mean only when agreement still holds and never mutating decided steps.
 *   - Replace committed steps forward-only by `built_at` when `/championship-path`
 *     responds, so newly withheld steps disappear and grid verdicts update.
 */
import type { ChampionshipPathEntry, TeamChampionshipPathResponse } from '@/lib/api';
import type { MarketPreviews } from '@/lib/discover/marketPreview';
import { observationOrder } from '@/lib/discover/priceRefresh';
import { decidedState } from '@/lib/teamSeasonJourney';

const TIER_AGREEMENT_BAR = 0.25;

export interface CommittedChampionshipState {
  path: ChampionshipPathEntry[];
  streamMarketIds: number[];
  builtAt: number | null;
}

export function championshipPathStreamMarketIds(
  entries: ChampionshipPathEntry[],
  streamMarketIds?: number[] | null,
): number[] {
  const ids = new Set<number>();
  const add = (value: unknown) => {
    if (typeof value === 'number' && Number.isSafeInteger(value) && value > 0) {
      ids.add(value);
    }
  };
  for (const id of streamMarketIds ?? []) add(id);
  for (const entry of entries) {
    if (entry.market_ids?.length) {
      entry.market_ids.forEach(add);
    } else {
      add(entry.market_id);
    }
    entry.components?.forEach((component) => add(component.market_id));
  }
  return [...ids].sort((a, b) => a - b);
}

export function adoptChampionshipPathResponse(
  current: CommittedChampionshipState,
  response: TeamChampionshipPathResponse | null | undefined,
): CommittedChampionshipState {
  if (!response || !Array.isArray(response.championship_path) || typeof response.built_at !== 'number') {
    return current;
  }
  if (current.builtAt !== null && response.built_at < current.builtAt) {
    return current;
  }
  return {
    path: response.championship_path,
    streamMarketIds: championshipPathStreamMarketIds(
      response.championship_path,
      response.stream_market_ids,
    ),
    builtAt: response.built_at,
  };
}

export function overlayChampionshipPathPreview(
  entries: ChampionshipPathEntry[],
  previews: MarketPreviews,
  now: number,
): ChampionshipPathEntry[] {
  if (!entries.length || !Object.keys(previews).length) return entries;
  let changed = false;
  const next = entries.map((entry) => {
    if (decidedState(entry.state) !== null || !entry.components?.length) return entry;
    let componentChanged = false;
    const probs = entry.components.map((component) => {
      const state = previews[component.market_id];
      if (!state || !component.source || state.source !== component.source || component.outcome_id == null) {
        return component.probability;
      }
      const leg = state.legs[String(component.outcome_id)];
      if (!leg || leg.expiresAt <= now) return component.probability;
      if (component.observed_at && (observationOrder(leg.observedAt, component.observed_at) ?? 0) <= 0) {
        return component.probability;
      }
      if (leg.p !== component.probability) componentChanged = true;
      return leg.p;
    });
    if (!componentChanged) return entry;
    const min = Math.min(...probs);
    const max = Math.max(...probs);
    if (max - min > TIER_AGREEMENT_BAR) return entry;
    const avg = Math.round((probs.reduce((sum, p) => sum + p, 0) / probs.length) * 10000) / 10000;
    if (avg === entry.probability) return entry;
    changed = true;
    return { ...entry, probability: avg };
  });
  return changed ? next : entries;
}
