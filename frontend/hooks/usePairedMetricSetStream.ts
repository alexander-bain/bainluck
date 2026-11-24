'use client';

import { useCallback, useEffect, useMemo, useRef } from 'react';
import type { PairedMetricSet } from '@/lib/discover/visualForms';
import { pairedMetricSetMarketIds } from '@/lib/pairedMetricStream';
import { useMarketStream } from './useMarketStream';

const PAIRED_REFRESH_FLOOR_MS = 2_000;

/**
 * #10090: Subscribes to `/api/markets/stream` for all open legs of the
 * provided `PairedMetricSet[]` and invokes a debounced (leading-edge + 2 s
 * floor) `onRefresh` callback on invalidation so server `blend_with_verdict`
 * remains the sole blending authority.
 */
export function usePairedMetricSetStream(
  sets: readonly PairedMetricSet[],
  onRefresh: () => void,
  enabled = true,
): void {
  const marketIds = useMemo(() => pairedMetricSetMarketIds(sets), [sets]);
  const marketIdSet = useMemo(() => new Set(marketIds), [marketIds]);

  const onRefreshRef = useRef(onRefresh);
  onRefreshRef.current = onRefresh;
  const lastRefreshAt = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (timer.current) {
        clearTimeout(timer.current);
        timer.current = null;
      }
    },
    [],
  );

  const scheduleRefresh = useCallback(() => {
    const now = Date.now();
    const wait = PAIRED_REFRESH_FLOOR_MS - (now - lastRefreshAt.current);
    if (wait <= 0) {
      if (timer.current) {
        clearTimeout(timer.current);
        timer.current = null;
      }
      lastRefreshAt.current = now;
      onRefreshRef.current();
      return;
    }
    if (timer.current) return;
    timer.current = setTimeout(() => {
      timer.current = null;
      lastRefreshAt.current = Date.now();
      onRefreshRef.current();
    }, wait);
  }, []);

  const handleInvalidate = useCallback(
    (batch: number[]) => {
      if (batch.some((id) => marketIdSet.has(id))) {
        scheduleRefresh();
      }
    },
    [marketIdSet, scheduleRefresh],
  );

  useMarketStream({
    marketIds,
    enabled: enabled && marketIds.length > 0,
    onInvalidate: handleInvalidate,
  });
}
