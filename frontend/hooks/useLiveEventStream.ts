'use client';

import { useEffect, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { API_URL } from '@/lib/api';
import { frameFoldOrder } from '@/lib/foldRevision';
import { rememberLiveChartFrame, type LiveChartFrame } from '@/lib/liveChartHistory';
import { frameCarriesUnpricedSnapshot } from '@/lib/sourceSnapshot';
import {
  EMPTY_AUTHORITY_PREVIEW,
  authorityPreviewFrame,
  authorityPreviewFloor,
  authorityPreviewOpen,
  authorityPreviewReset,
  authorityPreviewMembership,
  type AuthorityPreviewReader,
} from '@/lib/authorityPreview';
import type { BlendPreviewState } from '@/lib/blendPreview';
import type { ReconcileControl } from '@/lib/reconcileControl';
import {
  TICK_INTERVAL_MS,
  createLiveStreamController,
  timerSchedule,
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
 * The page keeps its ordinary metadata polling. Push carries quote updates;
 * refusal or silence restores fallback behavior. A server resync signals a
 * possible missed publication and exposes catch-up intent separately from the
 * latest quote, so the page can read a fresh coherent detail/history pair.
 * A heartbeat or resync never claims that a new price was published.
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
 * #10090: the frame the page should see after `next` arrives.
 *
 * React batches transport callbacks that land in one chunk, so the page's
 * push effect sees only the LAST frame of a batch. Publishers do not reach
 * the stream in revision order: production delivered rev 12482 and then the
 * older 12481 in one chunk, and the headline held the older price until
 * history caught up (1.2 s) while the chart, which banks every frame, moved
 * in 21 ms. So an older priced frame never displaces a newer one here.
 * `applyLiveFrame` refuses it against the newer frame, and `chartPoints`
 * still records it.
 *
 * Narrow on purpose. Any frame that tells the page something other than a
 * price still replaces the held one exactly as before: no price (an
 * invalidation) or one outside [0, 1], a status change, a folded quote or its pending notice, a
 * different event, or a revision that is missing, the same, or not
 * comparable.
 */
export function heldFrameAfter(previous: LiveFrame | null, next: LiveFrame): LiveFrame {
  if (!previous || previous.event_id !== next.event_id) return next;
  // A price is what `applyLiveFrame` would adopt: finite and inside [0, 1].
  // A held frame it would refuse must not keep out the valid one behind it.
  const priced = (f: LiveFrame) =>
    typeof f.p === 'number' && Number.isFinite(f.p) && f.p >= 0 && f.p <= 1 &&
    f.folded_quote === undefined && !f.folded_quote_pending && !frameCarriesUnpricedSnapshot(f);
  if (!priced(previous) || !priced(next)) return next;
  if ((previous.status ?? null) !== (next.status ?? null)) return next;
  return frameFoldOrder(previous.rev, next.rev) === 'older' ? previous : next;
}

/**
 * #10200 — the transport's own observation, or `idle` when this page is not
 * subscribing at all (not quote-eligible) and polling is the only path.
 */
export type LiveStreamStatus = LiveTransportStatus | 'idle';

interface UseLiveEventStreamResult {
  /** Latest frame, or null until one arrives. */
  frame: LiveFrame | null;
  /** Controller delivery state; the page retains periodic metadata reads. */
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
   * chart. Observational: `connected` remains available for fallback decisions. Keyed to
   * `eventId` like `chartPoints`, so a client-side navigation never shows the
   * previous event's interruption on the next one.
   */
  status: LiveStreamStatus;
  /** #10666: hook-lifetime monotonic recovery ordinal, scoped to this event. */
  recoveryGeneration: number;
  /**
   * #10090: the held provisional blend, or null. Never part of `frame` or
   * `chartPoints`; the page overlays it on the hero only
   * (`lib/blendPreview.ts`). Always null when the server sends none.
   */
  blendPreview: BlendPreviewState | null;
  /** #10090: Monotonic time at the last preview change or expiry, for `displayedPreview`. */
  blendPreviewNow: number;
  /**
   * #10090 decision J = A — the newest heartbeat `confirmed_at` for this event
   * (ISO-8601 UTC), or null. Ages the "seconds ago" only; never a price, never a
   * receipt. Null from an old server, and keyed to `eventId` like `status`.
   */
  confirmedAt: string | null;
}

export function useLiveEventStream(
  eventId: number | undefined,
  enabled: boolean,
  /**
   * #10090: called with EVERY frame, in arrival order. `frame` is one value per
   * render, and React renders a chunk's callbacks once, so a consumer that must
   * act on each frame (the page: a price AND the invalidation behind it) takes
   * them here.
   */
  onFrame?: (frame: LiveFrame) => void,
  /**
   * #10090: every validated `reconcile` control, synchronously and in arrival
   * order (not through state, which a batch would collapse). The page checks
   * the event id and owns the ledger.
   */
  onReconcile?: (control: ReconcileControl) => void,
  authoritativeMembership?: unknown,
): UseLiveEventStreamResult {
  const memberKeys = authoritativeMembership && typeof authoritativeMembership === 'object' && !Array.isArray(authoritativeMembership)
    ? Object.keys(authoritativeMembership).sort().join(',') : '';
  const membershipRef = useRef(authoritativeMembership);
  membershipRef.current = authoritativeMembership;
  const [frame, setFrame] = useState<LiveFrame | null>(null);
  const [connected, setConnected] = useState(false);
  const [{ chartEventId, points }, setChart] = useState<{
    chartEventId: number | undefined; points: LiveChartFrame[];
  }>({ chartEventId: eventId, points: [] });
  const [{ statusEventId, status }, setStatus] = useState<{
    statusEventId: number | undefined; status: LiveStreamStatus;
  }>({ statusEventId: eventId, status: 'idle' });
  const [recovery, setRecovery] = useState({ eventId, ordinal: 0 });
  const [confirmed, setConfirmed] = useState<{ eventId: number | undefined; at: string | null }>({
    eventId, at: null,
  });
  const [{ reader, previewNow }, setPreview] = useState<{
    reader: AuthorityPreviewReader; previewNow: number;
  }>({ reader: EMPTY_AUTHORITY_PREVIEW, previewNow: 0 });
  const preview = reader.preview.held;
  // A replacement controller starts its own ordinal at one; the hook does not.
  const recoveryOrdinal = useRef(0);
  // A ref so the controller's callbacks never close over a stale setter.
  const mounted = useRef(true);
  // Updated at commit, and before the controller effect below runs, so a new
  // event's controller never delivers to the previous event's callback and an
  // abandoned render never redirects the current one.
  const onFrameRef = useRef(onFrame);
  const onReconcileRef = useRef(onReconcile);
  useEffect(() => {
    onFrameRef.current = onFrame;
    onReconcileRef.current = onReconcile;
  });

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    setPreview({ reader: EMPTY_AUTHORITY_PREVIEW, previewNow: 0 });
  }, [eventId]);

  useEffect(() => {
    if (eventId) setPreview(previous => ({
      reader: authorityPreviewMembership(previous.reader, membershipRef.current, eventId), previewNow: performance.now(),
    }));
  }, [eventId, authoritativeMembership]);

  useEffect(() => {
    setRecovery({ eventId, ordinal: 0 });
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
          `${API_URL}/api/events/${eventId}/stream?preview_protocol=authority-v3`,
        ) as unknown as StreamHandle,
      now: () => Date.now(),
      onFrame: (next) => {
        if (mounted.current) {
          if (next.event_id === eventId && next.rev) setPreview(previous => ({
            reader: authorityPreviewFloor(previous.reader, next.rev), previewNow: performance.now(),
          }));
          setFrame(previous => heldFrameAfter(previous, next));
          // Collect in the transport callback, not an effect on `frame`: React
          // may batch several publications into one render.
          setChart(previous => ({
            chartEventId: eventId,
            points: rememberLiveChartFrame(
              previous.chartEventId === eventId ? previous.points : [], next, eventId,
            ),
          }));
          try {
            onFrameRef.current?.(next);
          } catch (error) {
            // A consumer's bug must not unwind into the controller and skip
            // its delivery bookkeeping. Report it, uncaught, off this stack.
            setTimeout(() => {
              throw error;
            });
          }
        }
      },
      onRecovery: () => {
        if (mounted.current) {
          recoveryOrdinal.current += 1;
          setRecovery({ eventId, ordinal: recoveryOrdinal.current });
        }
      },
      onReconcile: (control) => {
        if (!mounted.current) return;
        setPreview(previous => ({
          reader: authorityPreviewFloor(previous.reader, control.floor),
          previewNow: performance.now(),
        }));
        try {
          onReconcileRef.current?.(control);
        } catch (error) {
          setTimeout(() => {
            throw error;
          });
        }
      },
      previewNow: () => performance.now(),
      onAuthorityPreview: (raw, receivedAt) => {
        if (!mounted.current) return;
        setPreview(previous => {
          const at = performance.now();
          const reader = authorityPreviewFrame(previous.reader, raw, eventId, receivedAt, at);
          return { reader, previewNow: performance.now() };
        });
      },
      onPreviewFloor: (raw) => {
        if (!mounted.current) return;
        try {
          const packet = typeof raw === 'string' ? JSON.parse(raw) : raw;
          if (!packet || packet.event_id !== eventId) return;
          setPreview(previous => ({
            reader: authorityPreviewFloor(previous.reader, packet.floor), previewNow: performance.now(),
          }));
        } catch {
          setPreview(previous => ({
            reader: authorityPreviewReset(previous.reader), previewNow: performance.now(),
          }));
        }
      },
      onAuthorityPreviewOpen: (raw) => {
        if (mounted.current) setPreview(previous => ({
          reader: authorityPreviewOpen(previous.reader, raw, eventId), previewNow: performance.now(),
        }));
      },
      onPreviewReset: (endSession = true) => {
        if (mounted.current) setPreview(previous => ({
          reader: authorityPreviewReset(previous.reader, endSession), previewNow: performance.now(),
        }));
      },
      onDeliveringChange: (delivering) => {
        if (mounted.current) setConnected(delivering);
      },
      onStatusChange: (next) => {
        if (mounted.current) setStatus({ statusEventId: eventId, status: next });
      },
      // Newest wins: a reconnect's on-connect confirmation can be older than
      // one the previous socket already delivered.
      onConfirmedAt: (at) => {
        if (mounted.current) setConfirmed(previous => (
          previous.eventId === eventId && previous.at !== null && Date.parse(previous.at) >= Date.parse(at)
            ? previous
            : { eventId, at }
        ));
      },
      // #10090: the reopen after a server-directed rollover fires at its own
      // deadline rather than at the next 5 s tick. The controller cancels it on
      // `stop()` below, and a deadline that outlives its rollover opens nothing.
      schedule: timerSchedule,
      // #10090: one committed frame is one render. The page's `onFrame` writes
      // its SWR cache, which React renders synchronously, while the frame/chart
      // state set above is ordinary state rendered a task later: two full page
      // renders per frame, and the headline could paint before the chart.
      // Only the transport's own listeners call this, never a render or effect.
      deliver: (run) => flushSync(run),
    });

    controller.start();
    // ONE interval drives the silence watchdogs and backs up the reopen
    // deadline above. Teardown clears it and stops the controller, which
    // cancels any armed reopen.
    const timer = setInterval(() => controller.tick(), TICK_INTERVAL_MS);

    return () => {
      clearInterval(timer);
      controller.stop();
      setPreview(previous => ({ reader: authorityPreviewReset(previous.reader), previewNow: performance.now() }));
    };
  }, [eventId, enabled, memberKeys]);

  // #10090: re-render once when the held preview's lifetime ends, so an
  // expired provisional value gives way to the committed one without a frame.
  const previewExpiresAt = preview?.expiresAt;
  useEffect(() => {
    if (previewExpiresAt === undefined) return;
    const wait = Math.max(0, previewExpiresAt - performance.now());
    const timer = setTimeout(() => {
      if (mounted.current) setPreview(previous => ({ ...previous, previewNow: performance.now() }));
    }, wait + 1);
    return () => clearTimeout(timer);
  }, [previewExpiresAt]);

  return {
    frame,
    connected,
    recoveryGeneration: enabled && recovery.eventId === eventId ? recovery.ordinal : 0,
    chartPoints: chartEventId === eventId ? points : [],
    blendPreview: enabled && preview?.eventId === eventId ? preview : null,
    blendPreviewNow: previewNow,
    confirmedAt: enabled && confirmed.eventId === eventId ? confirmed.at : null,
    // Before this event's controller has said anything, it is connecting if
    // it is going to try at all — never the last event's word.
    status: statusEventId === eventId ? status : enabled ? 'connecting' : 'idle',
  };
}
