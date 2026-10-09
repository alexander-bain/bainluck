'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { FeedItem } from '@/lib/types';
import { priceKey, priceLeaves } from '@/lib/discover/priceRefresh';

type Report = (owner: string, keys: string[], visible: boolean) => void;

/**
 * Reports whether a card is on screen to `useDiscoverPriceStream`, which only
 * refreshes and streams prices for cards a reader can see. Same rule as
 * Discover's FeedItemShell observer: any pixel in the viewport counts.
 * Returns a ref callback for the card's outer element.
 */
export function usePriceVisibility(owner: string, items: FeedItem[], report?: Report) {
  const [node, setNode] = useState<Element | null>(null);
  const keys = priceLeaves(items).map(priceKey).filter((key): key is string => !!key).join(',');
  const reportRef = useRef(report);
  reportRef.current = report;
  useEffect(() => {
    const send = reportRef.current;
    if (!node || !send || !keys || typeof IntersectionObserver === 'undefined') return;
    const list = keys.split(',');
    const observer = new IntersectionObserver(([entry]) => send(owner, list, entry.isIntersecting), { threshold: 0 });
    observer.observe(node);
    return () => { observer.disconnect(); send(owner, list, false); };
  }, [node, owner, keys]);
  return useCallback((next: Element | null) => setNode(next), []);
}
