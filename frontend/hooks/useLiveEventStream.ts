'use client';

import { useEffect, useRef, useState } from 'react';
import { API_URL } from '@/lib/api';
import { rememberLiveChartFrame, type LiveChartFrame } from '@/lib/liveChartHistory';
import {
  TICK_INTERVAL_MS,
  createLiveStreamController,
  type LiveStreamFrame,
  type LiveTransportStatus,
  type StreamHandle,
} from '@/lib/liveStreamController';

/**
 * Subscribe to an eligible event's quote stream, independently of game phase.
 *
 * #9509: live, scheduled and suspended pages may subscribe; the server
 * checks actual contract eligibility. Refused connections retain polling.
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

/**
 * #10200 — the transport's own observation, or `idle` when this page is not
 * subscribing at all (not quote-eligible) and polling is the only path.
 */
export type LiveStreamStatus = LiveTransportStatus | 'idle';

interface UseLiveEventStreamResult {
  /** Latest frame, or null until one arrives. */
  frame: LiveFrame | null;
  /** True only while push is DELIVERING. Callers gate polling on this. */
  connected: boolean;
  /**
   * Actual publications received for this event while the page is open: the
   * blend each one stamped, and the venue reading behind it (#8066's
   * remainder — a single-source page has no blend line, so the frame has to
   * reach the source's own series or the chart waits for the 32 s poll).
   */
  chartPoints: LiveChartFrame[];
  /**
   * #10200 — what the transport is doing, for the reader-facing status by the
   * chart. Observational: `connected` above is still the polling gate. Keyed to
   * `eventId` like `chartPoints`, so a client-side navigation never shows the
   * previous event's interruption on the next one.
   */
  status: LiveStreamStatus;
}

export function useLiveEventStream(
  eventId: number | undefined,
  enabled: boolean,
): UseLiveEventStreamResult {
  const [frame, setFrame] = useState<LiveFrame | null>(null);
  const [connected, setConnected] = useState(false);
  const [{ chartEventId, points }, setChart] = useState<{
    chartEventId: number | undefined; points: LiveChartFrame[];
  }>({ chartEventId: eventId, points: [] });
  const [{ statusEventId, status }, setStatus] = useState<{
    statusEventId: number | undefined; status: LiveStreamStatus;
  }>({ statusEventId: eventId, status: 'idle' });
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
      setStatus({ statusEventId: eventId, status: 'idle' });
      return;
    }
    // Older browsers with no EventSource simply keep polling. Nothing to do.
    if (typeof EventSource === 'undefined') {
      setStatus({ statusEventId: eventId, status: 'unavailable' });
      return;
    }

    const controller = createLiveStreamController({
      open: () =>
        new EventSource(
          `${API_URL}/api/events/${eventId}/stream`,
        ) as unknown as StreamHandle,
      now: () => Date.now(),
      onFrame: (next) => {
        if (mounted.current) {
          setFrame(next);
          // Collect in the transport callback, not an effect on `frame`: React
          // may batch several publications into one render.
          setChart(previous => ({
            chartEventId: eventId,
            points: rememberLiveChartFrame(
              previous.chartEventId === eventId ? previous.points : [], next, eventId,
            ),
          }));
        }
      },
      onDeliveringChange: (delivering) => {
        if (mounted.current) setConnected(delivering);
      },
      onStatusChange: (next) => {
        if (mounted.current) setStatus({ statusEventId: eventId, status: next });
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

  return {
    frame,
    connected,
    chartPoints: chartEventId === eventId ? points : [],
    // Before this event's controller has said anything, it is connecting if
    // it is going to try at all — never the last event's word.
    status: statusEventId === eventId ? status : enabled ? 'connecting' : 'idle',
  };
}
