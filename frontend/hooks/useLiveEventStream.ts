'use client';

import { useEffect, useRef, useState } from 'react';
import { API_URL } from '@/lib/api';

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
 * polling, never to a frozen number. Every failure mode below — refused,
 * errored, closed, aged out, or *silently* dead — ends with `connected: false`,
 * and the caller restores its poll interval on that. The silent case is the
 * dangerous one: a TCP connection that is open but receiving nothing looks
 * exactly like a quiet market, and would leave a stale number on screen
 * indefinitely while everything appeared healthy.
 */

export interface LiveFrame {
  event_id: number;
  /** The AGGREGATE home probability — the number the hero renders. */
  p: number | null;
  /** Which feed moved, for the sources rail. */
  source: string;
  source_value: number | null;
  /** The STAMPED write time, so "live · Ns ago" counts from when it was true. */
  updated_at: string;
  status: string | null;
}

interface UseLiveEventStreamResult {
  /** Latest frame, or null until one arrives. */
  frame: LiveFrame | null;
  /** True only while the stream is open AND delivering. Callers gate polling on this. */
  connected: boolean;
}

/**
 * Silence budget. The server heartbeats every 20s, so 60s is three missed
 * beats — long enough that a hiccup does not flap the client between push and
 * poll, short enough that a dead stream cannot hold a stale number for longer
 * than the poll interval it replaced would have.
 */
const SILENCE_TIMEOUT_MS = 60_000;

export function useLiveEventStream(
  eventId: number | undefined,
  enabled: boolean,
): UseLiveEventStreamResult {
  const [frame, setFrame] = useState<LiveFrame | null>(null);
  const [connected, setConnected] = useState(false);
  // A ref, not state: the watchdog rearms on every message and must not
  // re-render the page
  const lastMessageAt = useRef<number>(0);

  useEffect(() => {
    if (!enabled || !eventId || typeof window === 'undefined') {
      setConnected(false);
      return;
    }
    // Older browsers with no EventSource simply keep polling. Nothing to do.
    if (typeof EventSource === 'undefined') return;

    let source: EventSource | null = null;
    let watchdog: ReturnType<typeof setInterval> | null = null;
    let closed = false;

    const teardown = () => {
      closed = true;
      setConnected(false);
      if (watchdog) clearInterval(watchdog);
      watchdog = null;
      // EventSource reconnects on its own by default, which is exactly what we
      // do NOT want once we have given up — the caller has already gone back to
      // polling and a background reconnect would double-fetch forever.
      if (source) source.close();
      source = null;
    };

    try {
      source = new EventSource(`${API_URL}/api/events/${eventId}/stream`);
    } catch {
      setConnected(false);
      return;
    }

    source.addEventListener('open', () => {
      if (closed) return;
      lastMessageAt.current = Date.now();
      setConnected(true);
    });

    source.addEventListener('probability', (e) => {
      if (closed) return;
      lastMessageAt.current = Date.now();
      try {
        const parsed = JSON.parse((e as MessageEvent).data) as LiveFrame;
        // Guard the shape rather than trusting it: a malformed frame that set
        // `p` to undefined would blank a working hero.
        if (typeof parsed?.event_id === 'number') {
          setFrame(parsed);
          setConnected(true);
        }
      } catch {
        // One bad frame is not a reason to abandon the stream.
      }
    });

    // The match ended, or the server hit its connection ceiling and wants us
    // back. Either way: stop, and let the caller's polling take over. The
    // caller refetches once on `connected` going false, which settles a
    // just-finished match on its final number.
    source.addEventListener('closed', teardown);
    source.addEventListener('reconnect', teardown);

    // Fired for a refused connect (409 non-live, 503 at capacity, 404) as well
    // as for a dropped connection. All of them mean the same thing here.
    source.addEventListener('error', () => {
      if (closed) return;
      // EventSource retries by itself while CONNECTING; only give up once it
      // has actually closed, so a single blip does not bounce us to polling.
      if (source && source.readyState === EventSource.CLOSED) teardown();
      else setConnected(false);
    });

    // The server's heartbeat is a NAMED event, not the conventional `: ping`
    // comment, precisely so it can rearm the watchdog below. A comment fires no
    // handler, which would leave the watchdog measuring "is this market moving"
    // rather than "is this server alive" — and on a quiet market it would tear
    // down a perfectly healthy stream.
    source.addEventListener('heartbeat', () => {
      if (closed) return;
      lastMessageAt.current = Date.now();
      setConnected(true);
    });

    // The watchdog. Any frame or heartbeat rearms it; silence past the budget
    // means the stream is dead in a way no event will ever tell us about.
    watchdog = setInterval(() => {
      if (closed || !lastMessageAt.current) return;
      if (Date.now() - lastMessageAt.current > SILENCE_TIMEOUT_MS) teardown();
    }, 5_000);

    return teardown;
  }, [eventId, enabled]);

  return { frame, connected };
}
