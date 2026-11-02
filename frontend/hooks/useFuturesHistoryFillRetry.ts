"use client";

import { useEffect, useRef } from "react";
import { historyFillPending, historyFillRetryDelay } from "@/lib/futuresHistoryFill";

/**
 * #883 — re-ask a futures `/history` read while its answer says a venue-history
 * fill is in flight (`lib/futuresHistoryFill.ts` for the why and the schedule).
 *
 * `rungKey` names the chart on screen (market + range). Changing it, clearing
 * `inFlight`, or unmounting aborts the in-flight read and cancels the next, so
 * a late answer can never be applied under another rung. The loop ends on the
 * first answer that no longer says "pending", or when the schedule is spent.
 * A failed read spends one attempt and leaves the chart already drawn alone.
 */
export function useFuturesHistoryFillRetry<T extends { venue_history?: { fill?: string | null } | null }>(opts: {
  inFlight: boolean;
  rungKey: string;
  refetch: (signal: AbortSignal) => Promise<T>;
  apply: (body: T) => unknown;
}): void {
  const { inFlight, rungKey } = opts;
  // The callbacks close over the current render; reading them through a ref
  // keeps a re-render from restarting the schedule at attempt 0.
  const latest = useRef(opts);
  latest.current = opts;

  useEffect(() => {
    if (!inFlight) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | null = null;
    let attempt = 0;
    const scheduleNext = () => {
      const delay = historyFillRetryDelay(attempt);
      if (delay == null || controller.signal.aborted) return;
      timer = setTimeout(async () => {
        attempt += 1;
        try {
          const body = await latest.current.refetch(controller.signal);
          if (controller.signal.aborted) return;
          await latest.current.apply(body);
          if (historyFillPending(body)) scheduleNext();
        } catch {
          scheduleNext();
        }
      }, delay);
    };
    scheduleNext();
    return () => {
      controller.abort();
      if (timer) clearTimeout(timer);
    };
  }, [inFlight, rungKey]);
}
