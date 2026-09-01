"use client";

/**
 * THE TRANSPORT for the live look — one `EventSource`, many subscribers.
 *
 * Alex, 2026-09-01, LIVE UPDATES ruling (1):
 *
 *   > PUSH for live events only — SSE stream for LIVE events, web + iOS
 *   > subscribe, non-live keeps polling.
 *
 * ═══ 🔴 THE STREAM IS NOT BUILT YET, AND THIS SHIPS ANYWAY ═══
 *
 * The endpoint is the live lane's, in flight as of 2026-09-01. Building the
 * look against a hook rather than against the endpoint is what lets the visual
 * half land, be reviewed and be certed now — and it is also the honest shape
 * even after the stream exists, because a card must render correctly for a
 * reader whose browser blocked EventSource, whose connection dropped, or who
 * is looking at a market that is not live.
 *
 * So the contract is: **no stream, no live look, and the card renders exactly
 * what the feed served it.** Nothing here degrades to a fake — there is no
 * simulated tick, no client-side interpolation between polls, no "last known
 * value plus elapsed time" guess. A number we did not receive is not shown.
 *
 * ⚠️ THE CARD MUST NOT LOOK LIVE WHEN THE STREAM IS SILENT. The pulse is driven
 * by the OBSERVATION timestamp, not by connection state, so a stream that
 * connects and then says nothing for three minutes produces "updates paused ·
 * 3m ago" — not a green dot on a stale hero. An open socket is not freshness.
 *
 * ═══ THE WIRE CONTRACT ═══
 *
 *   GET /api/live/stream?events=<id>,<id>      (text/event-stream)
 *
 *   event: blend_update
 *   data: {"event_id":123,"probability":0.614,"observed_at":"2026-09-01T18:04:11Z"}
 *
 * `probability` is the 0-1 blend, matching every other payload in the product;
 * this hook converts to points once, here, so no component does it twice.
 * `observed_at` is when the BLEND observed it — see ruling (3): a source older
 * than ~2 min is already out of the blend, so this timestamp is the age the
 * reader is entitled to see.
 *
 * Any other event name is ignored rather than parsed, so the live lane can add
 * `score_update` / `heartbeat` without touching this file. A heartbeat
 * DELIBERATELY does not refresh the age: nothing was observed.
 */

import { useEffect, useMemo, useRef, useState } from "react";

import {
  INITIAL_LIVE_DISPLAY,
  appendLivePoint,
  receiveLivePoint,
  tickLiveDisplay,
  type LiveDisplayState,
  type LivePoint,
} from "@/lib/live/liveNumber";

/** How often the display re-evaluates: paints a held point, ages the label. */
const TICK_MS = 1_000;

export interface LiveBlend {
  /** The point currently on screen, or null when nothing has arrived. */
  shown: LivePoint | null;
  /** Direction of the last painted change, for the tint. */
  direction: -1 | 0 | 1;
  /** The bounded observation ring, for the sparkline. */
  series: LivePoint[];
  /** Client clock, ticked once a second so ages re-render without a timer per chip. */
  now: number;
  /** True once a frame has been received on this subscription. */
  connected: boolean;
}

const IDLE: LiveBlend = {
  shown: null,
  direction: 0,
  series: [],
  now: 0,
  connected: false,
};

function streamUrl(eventId: number): string | null {
  const base = process.env.NEXT_PUBLIC_API_URL;
  if (!base) return null;
  return `${base.replace(/\/$/, "")}/api/live/stream?events=${eventId}`;
}

/**
 * Subscribe to the blend for one live event.
 *
 * `enabled` is the LIVE gate and the caller owns it — ruling (1) is "live
 * events only", and only the card knows whether its event is in play. Passing
 * `false` opens no socket at all, which is the difference between "push for
 * live events" and "a socket per card in the feed".
 */
export function useLiveBlend(eventId: number | null | undefined, enabled: boolean): LiveBlend {
  const [display, setDisplay] = useState<LiveDisplayState>(INITIAL_LIVE_DISPLAY);
  const [series, setSeries] = useState<LivePoint[]>([]);
  const [now, setNow] = useState(0);
  const [connected, setConnected] = useState(false);
  // Read inside the tick without making the tick depend on it — a tick that
  // re-subscribes every second is a tick that never fires.
  const displayRef = useRef(display);
  displayRef.current = display;

  const url = enabled && typeof eventId === "number" ? streamUrl(eventId) : null;

  useEffect(() => {
    if (!url) return;
    if (typeof window === "undefined" || typeof window.EventSource === "undefined") return;

    let source: EventSource;
    try {
      source = new EventSource(url);
    } catch {
      // A blocked or malformed EventSource is a card with no live look, never
      // a card that throws inside the feed's render tree.
      return;
    }

    const onBlend = (raw: MessageEvent) => {
      const point = parseBlendUpdate(raw.data, eventId as number);
      if (!point) return;
      const at = Date.now();
      setConnected(true);
      setDisplay((prev) => receiveLivePoint(prev, point, at));
      setSeries((prev) => appendLivePoint(prev, point));
    };

    source.addEventListener("blend_update", onBlend as EventListener);
    // No `onerror` handler that closes the socket: EventSource reconnects on
    // its own, and tearing it down on the first blip is how a live card goes
    // permanently quiet after one dropped packet. The age label already tells
    // the reader the truth while it is down.
    return () => {
      source.removeEventListener("blend_update", onBlend as EventListener);
      source.close();
    };
  }, [url, eventId]);

  useEffect(() => {
    if (!url) return;
    // The clock lives here rather than in each chip: one interval per card, not
    // one per label, and it is what paints a point the throttle is holding.
    const tick = () => {
      const at = Date.now();
      setNow(at);
      setDisplay((prev) => tickLiveDisplay(prev, at));
    };
    tick();
    const id = window.setInterval(tick, TICK_MS);
    return () => window.clearInterval(id);
  }, [url]);

  return useMemo(() => {
    if (!url) return IDLE;
    return {
      shown: display.shown,
      direction: display.lastDirection,
      series,
      now,
      connected,
    };
  }, [url, display.shown, display.lastDirection, series, now, connected]);
}

/**
 * One `blend_update` frame → a point, or null.
 *
 * Deliberately strict. Every rejection below is a frame that would otherwise
 * put a wrong number under a green dot:
 *
 *   • a frame for a different event (the endpoint takes a comma list, so a
 *     shared connection can and will carry siblings);
 *   • a non-finite or out-of-range probability;
 *   • an unparseable or absent `observed_at` — a point with no honest age has
 *     no place in a feature whose whole claim is the age.
 */
export function parseBlendUpdate(data: unknown, expectEventId: number): LivePoint | null {
  if (typeof data !== "string") return null;
  let frame: Record<string, unknown>;
  try {
    frame = JSON.parse(data) as Record<string, unknown>;
  } catch {
    return null;
  }
  if (!frame || typeof frame !== "object") return null;
  if (Number(frame.event_id) !== expectEventId) return null;

  const probability = Number(frame.probability);
  if (!Number.isFinite(probability) || probability < 0 || probability > 1) return null;

  const observedAt = Date.parse(String(frame.observed_at ?? ""));
  if (!Number.isFinite(observedAt)) return null;

  return { value: probability * 100, observedAt };
}
