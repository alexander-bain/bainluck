'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import type { DiscoverGroupedItem } from '@/components/discover/types';
import {
  applyMarketPreview, dropMarketPreviews, nextMarketPreviewExpiry, overlayMarketPreviews,
  type MarketPreviewFrame, type MarketPreviews,
} from '@/lib/discover/marketPreview';

/**
 * #10090: the held markets' provisional venue moves (`market_preview` frames
 * from `useMarketStream`), judged at a monotonic time. Never written into the
 * price book: `overlay` lays them over the cards the page returns. A market
 * that leaves `marketIds` (scrolled out of view, or resolved) drops its state,
 * and so does every market of a connection that ends.
 */
export function useMarketPreviews(marketIds: number[]) {
  const [previews, setPreviews] = useState<{ states: MarketPreviews; now: number }>({ states: {}, now: 0 });
  const onPreview = useCallback((frame: MarketPreviewFrame) => {
    const at = performance.now();
    setPreviews(previous => {
      const states = applyMarketPreview(previous.states, frame, at);
      return states === previous.states ? previous : { states, now: at };
    });
  }, []);
  const onPreviewReset = useCallback((ids: number[]) => {
    setPreviews(previous => {
      const states = dropMarketPreviews(previous.states, ids);
      return states === previous.states ? previous : { states, now: performance.now() };
    });
  }, []);

  const key = [...new Set(marketIds)].sort((a, b) => a - b).join(',');
  useEffect(() => {
    const kept = new Set(key ? key.split(',').map(Number) : []);
    setPreviews(previous => {
      const states = dropMarketPreviews(previous.states, Object.keys(previous.states).map(Number).filter(id => !kept.has(id)));
      return states === previous.states ? previous : { states, now: performance.now() };
    });
  }, [key]);

  // Re-render when the next shown leg's lifetime ends, so an expired
  // provisional value gives way to the committed one without a frame.
  const nextExpiry = nextMarketPreviewExpiry(previews.states, previews.now);
  useEffect(() => {
    if (!Number.isFinite(nextExpiry)) return;
    const timer = setTimeout(() => setPreviews(previous => ({ ...previous, now: performance.now() })),
      Math.max(0, nextExpiry - performance.now()) + 1);
    return () => clearTimeout(timer);
  }, [nextExpiry]);

  const overlay = useCallback((groups: DiscoverGroupedItem[]) => overlayMarketPreviews(groups, previews.states, previews.now),
    [previews]);
  return useMemo(() => ({ onPreview, onPreviewReset, overlay }), [onPreview, onPreviewReset, overlay]);
}
