'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  fetchTeamChampionshipPath,
  type ChampionshipPathEntry,
} from '@/lib/api';
import {
  applyMarketPreview,
  dropMarketPreviews,
  nextMarketPreviewExpiry,
  type MarketPreviewFrame,
  type MarketPreviews,
} from '@/lib/discover/marketPreview';
import {
  adoptChampionshipPathResponse,
  championshipPathStreamMarketIds,
  overlayChampionshipPathPreview,
  type CommittedChampionshipState,
} from '@/lib/teamChampionshipStream';
import { useMarketStream } from './useMarketStream';

const BURST_COALESCE_MS = 400;

/**
 * #10090: the team page's championship-path card and headline, re-priced live.
 *
 * Subscribes `/api/markets/stream` to every market candidate contributing to
 * the team's championship steps (`championship_path_market_ids`). Provisional
 * `market_preview` frames overlay within `< 50 ms`; committed invalidations
 * trigger a leading-edge refresh of `/api/teams/{id}/championship-path` (0 ms
 * on quiet arrival, 400 ms trailing coalesce under bursts).
 */
export function useTeamChampionshipStream(
  teamId: number | null | undefined,
  servedPath: ChampionshipPathEntry[],
  servedStreamMarketIds?: number[] | null,
): ChampionshipPathEntry[] {
  const seedKey = useMemo(
    () =>
      `${teamId ?? 'none'}:${JSON.stringify(
        servedPath.map((e) => [e.tier, e.market_id, e.probability, e.state ?? null, e.market_ids ?? null]),
      )}:${(servedStreamMarketIds ?? []).join(',')}`,
    [teamId, servedPath, servedStreamMarketIds],
  );

  const [committed, setCommitted] = useState<CommittedChampionshipState>(() => ({
    path: servedPath,
    streamMarketIds: championshipPathStreamMarketIds(servedPath, servedStreamMarketIds),
    builtAt: null,
  }));
  const [previews, setPreviews] = useState<{ states: MarketPreviews; now: number }>({
    states: {},
    now: 0,
  });

  const generation = useRef(0);
  const flight = useRef<AbortController | null>(null);
  const cooldownUntil = useRef(0);
  const trailingTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingRefresh = useRef(false);
  const teamIdRef = useRef(teamId);
  teamIdRef.current = teamId;

  useEffect(() => {
    generation.current += 1;
    flight.current?.abort();
    flight.current = null;
    if (trailingTimer.current) clearTimeout(trailingTimer.current);
    trailingTimer.current = null;
    pendingRefresh.current = false;
    cooldownUntil.current = 0;
    setCommitted({
      path: servedPath,
      streamMarketIds: championshipPathStreamMarketIds(servedPath, servedStreamMarketIds),
      builtAt: null,
    });
    setPreviews({ states: {}, now: 0 });
    return () => {
      flight.current?.abort();
      flight.current = null;
      if (trailingTimer.current) clearTimeout(trailingTimer.current);
      trailingTimer.current = null;
    };
  }, [seedKey, servedPath, servedStreamMarketIds]);

  const dispatchRefresh = useCallback(() => {
    const targetId = teamIdRef.current;
    if (targetId == null || flight.current) return;
    pendingRefresh.current = false;
    const mine = generation.current;
    const controller = new AbortController();
    flight.current = controller;
    cooldownUntil.current = Date.now() + BURST_COALESCE_MS;
    Promise.resolve(fetchTeamChampionshipPath(targetId, controller.signal))
      .then((response) => {
        if (generation.current !== mine || controller.signal.aborted) return;
        setCommitted((previous) => adoptChampionshipPathResponse(previous, response));
      })
      .catch(() => {
        /* served/held path stands; the next invalidation retries */
      })
      .finally(() => {
        if (flight.current === controller) flight.current = null;
        if (generation.current === mine && pendingRefresh.current && !trailingTimer.current) {
          const wait = Math.max(0, cooldownUntil.current - Date.now());
          trailingTimer.current = setTimeout(() => {
            trailingTimer.current = null;
            dispatchRefresh();
          }, wait);
        }
      });
  }, []);

  const invalidate = useCallback(() => {
    if (teamIdRef.current == null) return;
    const wait = Math.max(0, cooldownUntil.current - Date.now());
    if (!flight.current && wait === 0) {
      if (trailingTimer.current) {
        clearTimeout(trailingTimer.current);
        trailingTimer.current = null;
      }
      dispatchRefresh();
      return;
    }
    pendingRefresh.current = true;
    if (!flight.current && !trailingTimer.current) {
      trailingTimer.current = setTimeout(() => {
        trailingTimer.current = null;
        dispatchRefresh();
      }, wait);
    }
  }, [dispatchRefresh]);

  const onPreview = useCallback((frame: MarketPreviewFrame) => {
    const at = performance.now();
    setPreviews((previous) => {
      const states = applyMarketPreview(previous.states, frame, at);
      return states === previous.states ? previous : { states, now: at };
    });
  }, []);

  const onPreviewReset = useCallback((ids: number[]) => {
    setPreviews((previous) => {
      const states = dropMarketPreviews(previous.states, ids);
      return states === previous.states ? previous : { states, now: performance.now() };
    });
  }, []);

  const marketIds = useMemo(
    () => championshipPathStreamMarketIds(committed.path, committed.streamMarketIds),
    [committed.path, committed.streamMarketIds],
  );

  useMarketStream({
    marketIds,
    enabled: teamId != null && marketIds.length > 0,
    onInvalidate: invalidate,
    onPreview,
    onPreviewReset,
  });

  const nextExpiry = nextMarketPreviewExpiry(previews.states, previews.now);
  useEffect(() => {
    if (!Number.isFinite(nextExpiry)) return;
    const timer = setTimeout(
      () => setPreviews((previous) => ({ ...previous, now: performance.now() })),
      Math.max(0, nextExpiry - performance.now()) + 1,
    );
    return () => clearTimeout(timer);
  }, [nextExpiry]);

  return useMemo(
    () => overlayChampionshipPathPreview(committed.path, previews.states, previews.now),
    [committed.path, previews.states, previews.now],
  );
}
