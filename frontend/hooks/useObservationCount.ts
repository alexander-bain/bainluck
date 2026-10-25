'use client';

import { useEffect, useLayoutEffect, useState } from 'react';

const useCommittedLayoutEffect = typeof window === 'undefined' ? useEffect : useLayoutEffect;

type ObservationCount = { eventId: number; highWater: number | null; count: number };

function initialCount(eventId: number, timestamp: number | null): ObservationCount {
  return { eventId, highWater: timestamp, count: timestamp === null ? 0 : 1 };
}

/**
 * One owner per event page, shared by inline/fullscreen disclosures. The first
 * valid displayed observation counts once; only a strictly newer timestamp
 * advances it. A fallback may display an older time without rewriting history.
 */
export function useObservationCount(eventId: number, observedAt: string | null | undefined): number {
  const parsed = typeof observedAt === 'string' ? Date.parse(observedAt) : NaN;
  const timestamp = Number.isFinite(parsed) ? parsed : null;
  const [state, setState] = useState(() => initialCount(eventId, timestamp));
  useCommittedLayoutEffect(() => {
    setState(previous => {
      if (previous.eventId !== eventId) return initialCount(eventId, timestamp);
      if (timestamp === null || (previous.highWater !== null && timestamp <= previous.highWater)) return previous;
      return { eventId, highWater: timestamp, count: previous.count + 1 };
    });
  }, [eventId, timestamp]);
  // Navigation cannot expose the prior page's count before its commit effect.
  return state.eventId === eventId ? state.count : (timestamp === null ? 0 : 1);
}
