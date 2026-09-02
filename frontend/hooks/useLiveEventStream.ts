'use client';

import { useEffect, useRef, useState } from 'react';
import { API_URL } from '@/lib/api';
import {
  TICK_INTERVAL_MS,
  createLiveStreamController,
  type LiveStreamFrame,
  type StreamHandle,
} from '@/lib/liveStreamController';

/**
 * live/034 S2 — subscribe to a LIVE event's SSE push.
 *
 * Ruling (RULINGS-BATCH-2026-08-30, LIVE UPDATES): push for LIVE events only;
 * non-live keeps polling.
 *
 * The number in the database is already live — `worker-ws` flushes prices every
 * 2s and the blend is stamped at most once per event per 5s. What was not live
 * was the number on screen: the page polled every 32s, so a value 3s old in
 * Postgres could be 32s old in front of a user. This hook closes that gap.
 *
 * THE RULE THIS HOOK EXISTS TO ENFORCE: a push path that dies must degrade to
 * polling, never to a frozen number. Every failure mode — refused, errored,
 * closed, aged out, or *silently* dead — ends with `connected: false`, and the
 * caller restores its poll interval on that.
 *
 * THE LIFECYCLE ITSELF LIVES IN `@/lib/liveStreamController`, not here, and
 * that is deliberate. CERT-717 blocked this branch on two lifecycle defects
 * that every gate passed straight over — the server's 900s rollover
 * permanently killed push, and transport heartbeats masked a dead publisher —
 * because a lifecycle welded into a React effect cannot be tested in a Jest
 * that has no jsdom. This file is now the wiring; the rules are somewhere a
 * test can advance a clock through them.
 */

export type LiveFrame = LiveStreamFrame;

interface UseLiveEventStreamResult {
  /** Latest frame, or null until one arrives. */
  frame: LiveFrame | null;
  /** True only while push is DELIVERING. Callers gate polling on this. */
  connected: boolean;
}

export function useLiveEventStream(
  eventId: number | undefined,
  enabled: boolean,
): UseLiveEventStreamResult {
  const [frame, setFrame] = useState<LiveFrame | null>(null);
  const [connected, setConnected] = useState(false);
  // A ref so the controller's callbacks never close over a stale setter.
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    if (!enabled || !eventId || typeof window === 'undefined') {
      setConnected(false);
      return;
    }
    // Older browsers with no EventSource simply keep polling. Nothing to do.
    if (typeof EventSource === 'undefined') return;

    const controller = createLiveStreamController({
      open: () =>
        new EventSource(
          `${API_URL}/api/events/${eventId}/stream`,
        ) as unknown as StreamHandle,
      now: () => Date.now(),
      onFrame: (next) => {
        if (mounted.current) setFrame(next);
      },
      onDeliveringChange: (delivering) => {
        if (mounted.current) setConnected(delivering);
      },
    });

    controller.start();
    // ONE interval drives everything the controller schedules — the silence
    // watchdogs and the reopen after a server-directed rollover. No second
    // timer, and nothing scheduled inside a listener that a teardown could
    // miss.
    const timer = setInterval(() => controller.tick(), TICK_INTERVAL_MS);

    return () => {
      clearInterval(timer);
      controller.stop();
    };
  }, [eventId, enabled]);

  return { frame, connected };
}
