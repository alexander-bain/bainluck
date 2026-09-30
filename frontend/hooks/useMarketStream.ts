'use client';

import { useEffect, useRef } from 'react';
import { API_URL } from '@/lib/api';
import { createMarketStreamController } from '@/lib/marketStreamController';

/** Owners keep REST fallback/pacing/order. This hook reports no quote freshness. */
export function useMarketStream({ marketIds, enabled, onInvalidate }: {
  marketIds: number[];
  enabled: boolean;
  onInvalidate: (ids: number[]) => void;
}): void {
  const callback = useRef(onInvalidate);
  callback.current = onInvalidate;
  const key = [...new Set(marketIds)].sort((a, b) => a - b).join(',');
  useEffect(() => {
    if (!enabled || !key || typeof EventSource === 'undefined') return;
    const ids = key.split(',').map(Number);
    let controllers: ReturnType<typeof createMarketStreamController>[] = [];
    const close = () => { controllers.forEach(controller => controller.stop()); controllers = []; };
    const sync = () => {
      close();
      if (document.visibilityState === 'hidden') return;
      for (let start = 0; start < ids.length; start += 50) {
        const controller = createMarketStreamController({
          marketIds: ids.slice(start, start + 50), now: () => Date.now(),
          open: batch => new EventSource(`${API_URL}/api/markets/stream?ids=${batch.join(',')}`),
          onInvalidate: batch => callback.current(batch),
        });
        controllers.push(controller);
        controller.start();
      }
    };
    sync();
    const timer = setInterval(() => controllers.forEach(controller => controller.tick()), 5_000);
    document.addEventListener('visibilitychange', sync);
    return () => { clearInterval(timer); document.removeEventListener('visibilitychange', sync); close(); };
  }, [enabled, key]);
}
