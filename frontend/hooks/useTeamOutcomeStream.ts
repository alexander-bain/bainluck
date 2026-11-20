'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { API_URL } from '@/lib/api';
import {
  adoptOutcomePrices, patchTeamFuture,
  type OutcomePricesResponse, type TeamOutcomeBook,
} from '@/lib/teamOutcomePrices';
import type { TeamFutureItem } from '@/lib/api';
import { useMarketStream } from './useMarketStream';

const MAX_IDS = 50;
const COALESCE_MS = 400;

/**
 * #10090: the team page's season-futures rows, re-read by outcome id when their
 * market moves (`lib/teamOutcomePrices` holds the rules). A new team starts from
 * its own served rows; an answer for the previous team is dropped.
 */
export function useTeamOutcomeStream(rows: TeamFutureItem[]): (row: TeamFutureItem) => TeamFutureItem {
  const key = useMemo(() => rows.map((r) => `${r.market_id}:${r.outcome_id}`).join(','), [rows]);
  const [book, setBook] = useState<TeamOutcomeBook>(() => new Map());
  const generation = useRef(0);
  const rowsRef = useRef(rows);
  rowsRef.current = rows;
  const pending = useRef(new Set<number>());
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    generation.current += 1;
    setBook(new Map());
    pending.current.clear();
    return () => { if (timer.current) clearTimeout(timer.current); timer.current = null; };
  }, [key]);

  const flush = useCallback(() => {
    timer.current = null;
    const markets = pending.current;
    pending.current = new Set();
    const ids = rowsRef.current.filter((r) => markets.has(r.market_id)).map((r) => r.outcome_id);
    const mine = generation.current;
    for (let start = 0; start < ids.length; start += MAX_IDS) {
      const batch = ids.slice(start, start + MAX_IDS);
      fetch(`${API_URL}/api/feed/outcome-prices?outcome_ids=${batch.join(',')}`, { cache: 'no-store' })
        .then((response) => (response.ok ? (response.json() as Promise<OutcomePricesResponse>) : null))
        .then((answer) => {
          if (answer && generation.current === mine) {
            setBook((previous) => adoptOutcomePrices(previous, answer, new Set(batch)));
          }
        })
        .catch(() => { /* the served row stands; the next invalidation re-reads */ });
    }
  }, []);

  const marketIds = useMemo(() => [...new Set(rows.map((r) => r.market_id))], [rows]);
  useMarketStream({
    marketIds,
    enabled: marketIds.length > 0,
    onInvalidate: (ids) => {
      ids.forEach((id) => pending.current.add(id));
      if (!timer.current) timer.current = setTimeout(flush, COALESCE_MS);
    },
  });

  return useCallback((row: TeamFutureItem) => (book.size ? patchTeamFuture(row, book) : row), [book]);
}
