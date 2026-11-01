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
  authorityPreviewHandover,
  authorityPreviewOpen,
  authorityPreviewReset,
  authorityPreviewMembership,
  type AuthorityPreviewReader,
} from '@/lib/authorityPreview';
import type { BlendPreviewState } from '@/lib/blendPreview';
import { confirmationFloorsAfter, confirmationOwed } from '@/lib/event/liveConnectionStatus';
import type { FoldRevision } from '@/lib/foldRevision';
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
 * #10090: the preview reader and, beside it, a folded preview still on the
 * headline across a commit floor (`authorityPreviewHandover`). Only a floor
 * sets `handover`; every other change writes a fresh object without it, so a
 * revoke, reset, reconnect, reconcile, membership change or any other frame
 * ends the hand-over at once and the reader alone decides.
 */
type PreviewView = { reader: AuthorityPreviewReader; previewNow: number; handover?: BlendPreviewState | null };

function afterFloor(previous: PreviewView, reader: AuthorityPreviewReader, raw: unknown): PreviewView {
  const at = performance.now();
  return { reader, previewNow: at, handover: authorityPreviewHandover(previous.reader, reader, raw, previous.handover ?? null, at) };
}

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
   * C1: also null while a commit floor the stream announced is newer than the
   * committed revision on screen (`confirmationOwed`); the value received in
   * that window is kept and claimed once a committed revision covers it.
   */
  confirmedAt: string | null;
  /**
   * #10090 (Alex 2026-11-01) — the newest heartbeat `activity_at` for this
   * event: a venue reported in, whatever it agreed with. The EKG pulse only;
   * never a price's age. Null from an old server.
   */
  activityAt: string | null;
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
  const [activity, setActivity] = useState<{ eventId: number | undefined; at: string | null }>({
    eventId, at: null,
  });
  // #10090 J C1: the commit floors announced for this event, max per row, the
  // floors of rows that left the committed fold (parked, as the reader retires
  // them), and the rows of the committed revision they were last pruned against.
  const [gate, setGate] = useState<{
    eventId: number | undefined; floors: FoldRevision; parked: FoldRevision; members: string;
  }>({
    eventId, floors: {}, parked: {}, members: memberKeys,
  });
  const [{ reader, previewNow, handover }, setPreview] = useState<PreviewView>(
    { reader: EMPTY_AUTHORITY_PREVIEW, previewNow: 0 });
  const preview = reader.preview.held ?? handover ?? null;
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

  // #10090 J C1 R1: a row that leaves the committed fold parks its floor, as
  // the reader retires it, and gets it back if a later revision carries the row
  // again — a stale detail read re-adding it below its known floor stays owed.
  // A page with no revision on screen keeps every floor: nothing on screen
  // covers them. A new event clears both.
  useEffect(() => {
    setGate(previous => {
      if (previous.eventId !== eventId) return { eventId, floors: {}, parked: {}, members: memberKeys };
      if (!memberKeys || previous.members === memberKeys) return previous;
      const rows = memberKeys.split(',');
      const floors = { ...previous.floors };
      const parked = { ...previous.parked };
      for (const key of previous.members ? previous.members.split(',') : []) {
        if (rows.includes(key) || !(key in floors)) continue;
        parked[key] = Math.max(parked[key] ?? -1, floors[key]);
        delete floors[key];
      }
      for (const key of rows) {
        if (!(key in parked)) continue;
        floors[key] = Math.max(floors[key] ?? -1, parked[key]);
        delete parked[key];
      }
      return { eventId, floors, parked, members: memberKeys };
    });
  }, [eventId, memberKeys]);

  useEffect(() => {
    // Unchanged membership is a commit floor (a newly adopted detail's
    // vector); a changed one hands nothing over.
    if (eventId) setPreview(previous => afterFloor(
      previous, authorityPreviewMembership(previous.reader, membershipRef.current, eventId), membershipRef.current,
    ));
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

    // #10090 J C1: committed at once, not batched. A floor's other effects are
    // ordinary state, and the next frame's `deliver` commits only its own lane:
    // a chunk of floor → raw frame otherwise committed the reader's new floor
    // (preview dropped, the old committed value showing) with the confirmation
    // still claimed over it.
    const raiseFloors = (raw: unknown) => flushSync(() => setGate(previous => {
      const held = previous.eventId === eventId ? previous : { eventId, floors: {}, parked: {}, members: '' };
      const floors = confirmationFloorsAfter(held.floors, raw);
      return floors === held.floors && held === previous ? previous : { ...held, floors };
    }));

    const controller = createLiveStreamController({
      open: () =>
        new EventSource(
          `${API_URL}/api/events/${eventId}/stream?preview_protocol=authority-v3`,
        ) as unknown as StreamHandle,
      now: () => Date.now(),
      onFrame: (next) => {
        if (mounted.current) {
          // #10090: a raw frame that promises its folded result, in the same
          // status, may hand the displayed folded preview over until that
          // result; the result itself (adopted, held, null or refused) and any
          // other frame end it.
          const promise = next.folded_quote_pending === true && !('folded_quote' in next);
          if (next.event_id === eventId && next.rev) setPreview(previous => {
            const floored = authorityPreviewFloor(previous.reader, next.rev);
            const shown = previous.reader.preview.held ?? previous.handover;
            return promise && (next.status === undefined || next.status === shown?.status)
              ? afterFloor(previous, floored, next.rev) : { reader: floored, previewNow: performance.now() };
          });
          else if (next.event_id === eventId && !promise) setPreview(previous => previous.handover
            ? { reader: previous.reader, previewNow: performance.now() } : previous);
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
        raiseFloors(control.floor);
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
          raiseFloors(packet.floor);
          setPreview(previous => afterFloor(previous, authorityPreviewFloor(previous.reader, packet.floor), packet.floor));
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
      onActivityAt: (at) => {
        if (mounted.current) setActivity(previous => (
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

  // #10090 J C1 R2: a parked row back in the committed revision owes its floor
  // on THIS render. The membership effect restores it a commit late, and that
  // one commit would claim the confirmation over the stale rejoin.
  let gateFloors = gate.floors;
  for (const key of memberKeys ? memberKeys.split(',') : []) {
    if (key in gate.parked) gateFloors = { ...gateFloors, [key]: Math.max(gateFloors[key] ?? -1, gate.parked[key]) };
  }

  return {
    frame,
    connected,
    recoveryGeneration: enabled && recovery.eventId === eventId ? recovery.ordinal : 0,
    chartPoints: chartEventId === eventId ? points : [],
    blendPreview: enabled && preview?.eventId === eventId ? preview : null,
    blendPreviewNow: previewNow,
    confirmedAt: enabled && confirmed.eventId === eventId
      && !confirmationOwed(gate.eventId === eventId ? gateFloors : {}, authoritativeMembership)
      ? confirmed.at : null,
    activityAt: enabled && activity.eventId === eventId ? activity.at : null,
    // Before this event's controller has said anything, it is connecting if
    // it is going to try at all — never the last event's word.
    status: statusEventId === eventId ? status : enabled ? 'connecting' : 'idle',
  };
}
