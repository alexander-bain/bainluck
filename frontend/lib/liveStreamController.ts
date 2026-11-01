/**
 * live/034 — the SSE lifecycle, lifted out of the React hook so it can be proved.
 *
 * WHY THIS FILE EXISTS. CERT-717 blocked live/034 on two P1 lifecycle defects,
 * and its fix-sketch asked for tests that advance a clock through the server's
 * rollover and through a heartbeats-but-no-data window. Neither can be written
 * against the hook: this repo's Jest runs `testEnvironment: 'node'` with no
 * jsdom and no `@testing-library/react`, so a hook's effects never run, and the
 * registry is unreachable so adding them is not on the table.
 *
 * A lifecycle nobody can test is how both defects shipped green in the first
 * place — 51/51 backend and 27/27 frontend passed at the blocked SHA, and no
 * test exercised either broken path. So the lifecycle lives here as a plain
 * object with its dependencies injected, and `useLiveEventStream` is a thin
 * React wrapper over it.
 *
 * THE TWO DEFECTS THIS ENCODES THE FIX FOR:
 *
 * 1. `reconnect` is a ROLLOVER, not a death. The server closes every stream at
 *    its `MAX_CONNECTION_S` ceiling (900s) and says so. The old client handled
 *    that by closing its only EventSource and building no replacement, so a fan
 *    watching a normal game got push for fifteen minutes and then silently went
 *    back to the 32s poll for the rest of the match.
 *
 * 2. A HEARTBEAT IS NOT A DELIVERY. The heartbeat is emitted by the web
 *    subscriber on its own timer, independent of the publisher. If `worker-ws`
 *    or its publish path dies while this process's Redis subscription stays
 *    healthy, heartbeats continue forever. Treating one as proof of delivery
 *    kept polling disabled over a dead publisher — the exact silent-failure
 *    mode the hook promises to degrade out of (gotcha #53: a heartbeat that
 *    arrives regardless of the thing it is supposed to be evidence FOR is a
 *    response shape, not a signal).
 *
 * 3. (#8079, added from a production capture) A NETWORK THAT WENT AWAY IS NOT A
 *    SERVER THAT SAID NO. Silence past the transport budget used to be terminal
 *    whatever caused it, and since heartbeats rearm that budget, an outage
 *    beginning late in a heartbeat cycle got barely 40s of grace: measured on a
 *    live page, 41.9s of lost signal ended push permanently, and reconnecting
 *    53s later opened nothing. The same run showed a 25s outage recovering
 *    0.7s after the network returned — EventSource retries perfectly well on
 *    its own, and the only thing that had stopped it was this controller
 *    closing the handle. `tick()` now reads `readyState` to separate the two.
 *
 * TIME IS A PARAMETER, NOT AN AMBIENT FACT. Everything schedules against `now()`
 * and is driven by `tick()`, so a test advances the clock rather than waiting on
 * one. No test in here branches on the wall clock (gotcha #44).
 */

import { heartbeatUpdates } from '@/lib/event/liveUpdateStream';
import { parseReconcileControl, type ReconcileControl } from "./reconcileControl";
import { snapshotFrameIsOversize } from "./sourceSnapshot";

export interface LiveStreamFrame {
  event_id: number;
  p: number | null;
  source: string;
  source_value: number | null;
  updated_at: string;
  status?: string | null;
  /**
   * #9051: `{ "<row id>": rev }` for the one row this frame's write touched —
   * see `lib/foldRevision.ts`. Absent from a producer before the contract.
   */
  rev?: Record<string, number> | null;
  /** Explicit full fold carried by the optional folded_probability event. */
  folded_quote?: unknown;
  /** Raw actual-fold notification promises an object/null projection result. */
  folded_quote_pending?: boolean;
  /**
   * #10090: the same write's complete source map (`lib/sourceSnapshot.ts`).
   * Dropped here when the raw frame is over the decoder's size bound (D3), so
   * the frame is then exactly its legacy shape.
   */
  source_snapshot?: unknown;
}

/** The slice of `EventSource` this controller uses. */
export interface StreamHandle {
  addEventListener(type: string, listener: (event: unknown) => void): void;
  close(): void;
  /**
   * `EventSource.CONNECTING` (0) while the browser is retrying on its own,
   * `OPEN` (1), `CLOSED` (2) once it has given up. The controller reads this to
   * tell a transport that FAILED from one that was REFUSED — see `tick()`.
   */
  readonly readyState: number;
}

/**
 * #10090 decision J = A — the `confirmed_at` a heartbeat carries, or null. An
 * old server's heartbeat (`{"t": ...}`), a body that is not JSON, or a value
 * that is not a parseable time all read as no confirmation.
 */
export function heartbeatConfirmedAt(raw: unknown): string | null {
  return heartbeatClock(raw, 'confirmed_at');
}

/**
 * #10090 (Alex 2026-11-01) — the `activity_at` a heartbeat carries, or null:
 * the newest venue input for the event, WHATEVER it agreed with. It feeds the
 * EKG pulse only and must never age or date a price (`confirmed_at` does that).
 */
export function heartbeatActivityAt(raw: unknown): string | null {
  return heartbeatClock(raw, 'activity_at');
}

function heartbeatClock(raw: unknown, key: 'confirmed_at' | 'activity_at'): string | null {
  let body: unknown = raw;
  if (typeof raw === 'string') {
    try {
      body = JSON.parse(raw);
    } catch {
      return null;
    }
  }
  if (!body || typeof body !== 'object') return null;
  const value = (body as Record<string, unknown>)[key];
  return typeof value === 'string' && Number.isFinite(Date.parse(value)) ? value : null;
}

export interface LiveStreamDeps {
  /** Opens a transport. Throwing is treated as a refused connect. */
  open: () => StreamHandle;
  now: () => number;
  /** A validated frame arrived. */
  onFrame: (frame: LiveStreamFrame) => void;
  /**
   * Whether push is DELIVERING — which is not the same as whether a socket is
   * open. The caller gates its polling on this.
   */
  onDeliveringChange: (delivering: boolean) => void;
  /** #10666: local monotonic recovery ordinal, never a quote revision. */
  onRecovery?: (ordinal: number) => void;
  /** #10090: a validated `reconcile` control — an owed read, never a price. */
  onReconcile?: (control: ReconcileControl) => void;
  /**
   * #10090: a raw `preview` event's data — a
   * provisional blend that is NOT a committed frame (`lib/blendPreview.ts`).
   * Touches no clock, cursor or status: it can neither keep push "delivering"
   * nor postpone the data-silence fallback.
   */
  onPreview?: (raw: unknown) => void;
  /** #10090: previews are never replayed, so every (re)open and the end of the match clear them. */
  onPreviewReset?: (endSession?: boolean) => void;
  onPreviewFloor?: (raw: unknown) => void;
  onPreviewOpen?: (raw: unknown) => void;
  onAuthorityPreviewOpen?: (raw: unknown) => void;
  onAuthorityPreview?: (raw: unknown, receivedAt: number) => void;
  previewNow?: () => number;
  /**
   * #10090 decision J = A — the heartbeat's `confirmed_at` (ISO-8601 UTC): the
   * newest venue input that AGREED with what the stream has published. The
   * server never advances it while a different price is held. It ages the
   * reader's "seconds ago" only; like the heartbeat itself it is NOT a delivery
   * and touches no clock, cursor or status here.
   */
  onConfirmedAt?: (confirmedAt: string) => void;
  /**
   * #10090 (Alex 2026-11-01) — the heartbeat's `activity_at`: a venue reported
   * in. The EKG pulse only; touches no clock, cursor or status here.
   */
  onActivityAt?: (activityAt: string) => void;
  /** #10090 (Alex 2026-11-01) — the heartbeat's `updates`, for the EKG's list. Activity only. */
  onUpdates?: (updates: { source: string; at: number }[]) => void;
  /**
   * #10200 — what the TRANSPORT is doing, for the reader-facing status only.
   *
   * OBSERVATIONAL. Nothing in here reads it back: every decision above
   * (`onDeliveringChange`, the silence rails, the rollover, the retry give-up)
   * is taken exactly as before and this is told afterwards. It exists because
   * `delivering` cannot answer the reader's question — it is true on `open`
   * before any price has been published, and false both for a socket that
   * failed and for a healthy one whose market simply went quiet. See
   * `LiveTransportStatus` for what each value does and does not prove.
   */
  onStatusChange?: (status: LiveTransportStatus) => void;
  /**
   * #10090 — run `action` once, `ms` from now; returns its cancel. The owner
   * passes `setTimeout`/`clearTimeout`, so a scheduled reopen fires AT its
   * deadline instead of at the first `tick()` after it. Omitted, the reopen
   * waits for `tick()` exactly as before; `tick()` stays the backstop either way.
   */
  schedule?: (action: () => void, ms: number) => () => void;
  /** #10090 — the healthy-rollover wait, in ms. Injected so a test can pin it. */
  healthyRolloverDelay?: () => number;
  /**
   * #10090 — runs one committed frame's delivery (`onFrame` and the delivery
   * state it implies) as a unit. The hook passes react-dom's `flushSync`: the
   * page writes the frame to its SWR cache (a synchronous store update) while
   * the hook's own frame/chart state is ordinary state, so without one flush a
   * frame rendered the whole page twice — headline first, chart a task later.
   * Omitted, the delivery simply runs.
   */
  deliver?: (run: () => void) => void;
}

/**
 * #10200 — the transport's own observations, named.
 *
 * - `connecting`  — a socket has been asked for and has not opened yet.
 * - `open`        — the socket opened and nothing has outlived a silence rail.
 *                   NOT a claim that a price is current: a heartbeat keeps this
 *                   alive and a heartbeat proves only the socket (defect 2).
 * - `quiet`       — the socket is open but nothing has been PUBLISHED for
 *                   `DATA_SILENCE_TIMEOUT_MS`, so polling has resumed. A quiet
 *                   market and a dead publisher look identical from here, so
 *                   this is not an outage claim either.
 * - `retrying`    — the transport actually failed and the browser is retrying.
 * - `rollover`    — the server asked for a fresh socket (the 900s ceiling).
 *                   Healthy, and never an interruption — but reported AFTER
 *                   the old socket is closed, so it is not a connection either.
 * - `unavailable` — push is over for this page-view: refused, given up, or a
 *                   half-open socket retired. Polling carries the page.
 * - `closed`      — the server said the match ended.
 */
export type LiveTransportStatus =
  | 'connecting'
  | 'open'
  | 'quiet'
  | 'retrying'
  | 'rollover'
  | 'unavailable'
  | 'closed';

/** Transport silence: three missed 20s heartbeats. The stream is dead. */
export const SILENCE_TIMEOUT_MS = 60_000;

/**
 * How long a silent transport that is STILL RETRYING is given before the
 * controller retires it for good.
 *
 * #8079 — silence alone used to be terminal, and because `lastMessageAt` is
 * rearmed by heartbeats (every 20s), the budget was already part-spent when an
 * outage began: measured on production, a page tolerated 41.9s before push
 * ended for the rest of the page-view, and restoring the network 53s later
 * reopened nothing. A reader in a tunnel is not a server refusing a connect.
 *
 * Long enough to outlast a tunnel, a lift or a backgrounded tab; short enough
 * that a page left open against an unreachable server is not retrying all
 * evening. Polling covers the whole window either way — this only decides
 * whether push can come BACK.
 */
export const RETRY_GIVEUP_MS = 300_000;

/**
 * Delivery silence. Longer than the transport budget on purpose: a genuinely
 * quiet market publishes nothing, and the right answer to "push has nothing to
 * say" is to resume the 32s poll while KEEPING the stream open — not to tear it
 * down. The instant a frame arrives, push takes back over.
 */
export const DATA_SILENCE_TIMEOUT_MS = 90_000;

export const RECONNECT_BASE_DELAY_MS = 1_000;
export const RECONNECT_MAX_DELAY_MS = 30_000;
/** A stream that lasted this long was healthy; its rollover is not a failure. */
export const HEALTHY_STREAM_MS = 60_000;

/**
 * #10090 — how long a HEALTHY stream's rollover waits before it reopens:
 * 250 ms, jittered ×1–2, the same policy native reviewed (PR #11144). The
 * server rolls every stream at its age ceiling and replays only the latest
 * frame on the new socket, so every second spent here is a second the page
 * holds a number no socket stands behind. The jitter keeps one server rolling
 * every page at once from bringing them all back in the same instant. A FAST
 * rollover keeps the 1 s doubling backoff above.
 */
export const HEALTHY_ROLLOVER_MIN_DELAY_MS = 250;
export const HEALTHY_ROLLOVER_MAX_DELAY_MS = 500;

/**
 * How often the owner should call `tick()`. A scheduled reopen does not wait
 * for it when the owner injects `schedule` (#10090): the controller arms its
 * own deadline, and `tick()` only backs it up.
 */
export const TICK_INTERVAL_MS = 5_000;

/** #10090 — the production `schedule`: one `setTimeout`, cancelled by `clearTimeout`. */
export function timerSchedule(action: () => void, ms: number): () => void {
  const id = setTimeout(action, ms);
  return () => clearTimeout(id);
}

const EVENT_SOURCE_CONNECTING = 0;
const EVENT_SOURCE_CLOSED = 2;

export interface LiveStreamController {
  start(): void;
  /** Drive the clock. Call every `TICK_INTERVAL_MS`. */
  tick(): void;
  /** Terminal. No reopen, ever. */
  stop(): void;
  /** For assertions and debugging; not part of the render path. */
  readonly state: {
    delivering: boolean;
    stopped: boolean;
    connections: number;
    reopenAt: number | null;
    status: LiveTransportStatus | null;
  };
}

export function createLiveStreamController(
  deps: LiveStreamDeps,
): LiveStreamController {
  const { open, now, onFrame, onDeliveringChange, onStatusChange, onRecovery, onReconcile, onPreview, onPreviewReset, schedule } = deps;
  const deliver = deps.deliver ?? ((run: () => void) => run());
  const healthyRolloverDelay =
    deps.healthyRolloverDelay ??
    (() =>
      HEALTHY_ROLLOVER_MIN_DELAY_MS +
      Math.random() * (HEALTHY_ROLLOVER_MAX_DELAY_MS - HEALTHY_ROLLOVER_MIN_DELAY_MS));

  let handle: StreamHandle | null = null;
  let delivering = false;
  let stopped = false;
  let connections = 0;
  let recoveryNotifications = 0;
  let openedAt = 0;
  let lastMessageAt = 0;
  let lastDataAt = 0;
  let reopenAt: number | null = null;
  let consecutiveFastRollovers = 0;
  let status: LiveTransportStatus | null = null;
  // #10090 — the armed reopen deadline's cancel, and which deadline is current.
  // A deadline that fires after `connect()` or `stop()` already ran (a late
  // timer, or a tick that got there first) finds its generation retired and
  // opens nothing, so one rollover can never open two sockets.
  let cancelReopen: (() => void) | null = null;
  let reopenGeneration = 0;

  const disarmReopen = () => {
    reopenGeneration += 1;
    const cancel = cancelReopen;
    cancelReopen = null;
    try {
      cancel?.();
    } catch {
      // A timer that cannot be cancelled is retired by its generation instead.
    }
  };

  // #10200 — report, never decide. Every call site sits AFTER the decision it
  // describes, so deleting all of them changes no behaviour above.
  const setStatus = (next: LiveTransportStatus) => {
    if (status === next) return;
    status = next;
    onStatusChange?.(next);
  };

  const setDelivering = (next: boolean) => {
    if (delivering === next) return;
    delivering = next;
    onDeliveringChange(next);
  };

  const closeHandle = () => {
    if (!handle) return;
    // EventSource retries on its own by default, which is exactly what we do
    // NOT want once we have decided: a background reconnect under a caller that
    // has gone back to polling would double-fetch forever.
    try {
      handle.close();
    } catch {
      // A transport that cannot be closed is already gone.
    }
    handle = null;
  };

  const stop = () => {
    onPreviewReset?.();
    stopped = true;
    reopenAt = null;
    disarmReopen();
    closeHandle();
    setDelivering(false);
  };

  /**
   * The server asked for a fresh socket. Close this one and schedule the next.
   *
   * NOTHING ELSE CALLS THIS. A refused connect (409 non-live, 503 at capacity,
   * 404) or a stream gone silent must still degrade to polling rather than
   * retry-loop against a server that has already said no. Only the explicit
   * `reconnect` frame — the server asking, in words — reopens.
   */
  const rollOver = () => {
    if (stopped) return;
    onPreviewReset?.();
    const lived = now() - openedAt;
    closeHandle();
    setDelivering(false);
    if (lived >= HEALTHY_STREAM_MS) consecutiveFastRollovers = 0;
    else consecutiveFastRollovers += 1;
    // #10090: a healthy stream comes straight back — see
    // `HEALTHY_ROLLOVER_MIN_DELAY_MS`. Only a fast one pays the 1 s doubling
    // backoff, so a server that rolls over instantly is still never hammered.
    const delay =
      consecutiveFastRollovers === 0
        ? healthyRolloverDelay()
        : Math.min(
            RECONNECT_MAX_DELAY_MS,
            RECONNECT_BASE_DELAY_MS * 2 ** (consecutiveFastRollovers - 1),
          );
    reopenAt = now() + delay;
    armReopen(delay);
    setStatus('rollover');
  };

  /**
   * #10090 — reopen AT the deadline, not at the first tick after it. The owner
   * ticks every 5 s, so a reopen left to `tick()` waited up to five seconds past
   * its own delay while the page held a number with no socket behind it.
   */
  const armReopen = (delay: number) => {
    disarmReopen();
    if (!schedule) return;
    const generation = reopenGeneration;
    try {
      cancelReopen = schedule(() => {
        // `connect()` and `stop()` both retire the generation, so this is the
        // whole test; `connect()` itself still refuses once stopped.
        if (generation !== reopenGeneration) return;
        connect();
      }, delay);
    } catch {
      // No timer: `reopenAt` is already set, so the next tick reopens instead.
    }
  };

  const connect = () => {
    if (stopped) return;
    reopenAt = null;
    // Whichever of the deadline and the tick arrives second finds nothing to do.
    disarmReopen();
    let next: StreamHandle;
    try {
      next = open();
    } catch {
      // A transport that will not even construct is a refused connect.
      setDelivering(false);
      stopped = true;
      setStatus('unavailable');
      return;
    }
    handle = next;
    connections += 1;
    openedAt = now();
    // Seed BOTH clocks. A stream that has just opened has not failed to deliver
    // anything yet; demanding a frame before one could arrive would flap the
    // caller straight back to polling on every rollover.
    lastMessageAt = openedAt;
    lastDataAt = openedAt;
    setStatus('connecting');

    let recoveryGeneration = 0;
    let transportRecoveryPending = false;
    next.addEventListener('open', (event) => {
      if (stopped || handle !== next) return;
      onPreviewReset?.();
      deps.onPreviewOpen?.((event as { data?: unknown })?.data);
      // Native retry can reopen this handle against another server worker.
      recoveryGeneration = 0;
      lastMessageAt = now();
      lastDataAt = now();
      setDelivering(true);
      setStatus('open');
      // A failed transport may have missed the final quote beyond replay age.
      // Reuse the page's jittered paired catch-up; an open is not a new price.
      // Native and server 'open' events may both fire for one connection.
      if (transportRecoveryPending) {
        transportRecoveryPending = false;
        onRecovery?.(++recoveryNotifications);
      }
    });

    next.addEventListener('resync', (event) => {
      if (stopped || handle !== next) return;
      let generation: unknown;
      try {
        generation = JSON.parse(String((event as { data?: unknown })?.data)).generation;
      } catch {
        return;
      }
      if (typeof generation !== 'number' || !Number.isSafeInteger(generation) || generation <= recoveryGeneration) return;
      recoveryGeneration = generation;
      // The hub has discarded its provisional authority. Withdraw the held
      // headline/chart/clock before requesting committed recovery coverage.
      onPreviewReset?.(false);
      // Recovery signals delivery debt, never fresh data or a new quote clock.
      onRecovery?.(++recoveryNotifications);
    });

    // #10090: separate from `resync` — a named owed read with its own custody id
    // and row-wise floor. Like `resync` it touches no clock, cursor or status,
    // so a control can neither postpone the data-silence fallback nor pass for
    // a price. Not deduped here: the page's ledger owns what is still owed.
    next.addEventListener('reconcile', (event) => {
      if (stopped || handle !== next) return;
      const control = parseReconcileControl((event as { data?: unknown })?.data);
      if (control) onReconcile?.(control);
    });

    const onProbability = (event: unknown) => {
      if (stopped || handle !== next) return;
      lastMessageAt = now();
      const raw = (event as { data?: unknown })?.data;
      let parsed: LiveStreamFrame | null = null;
      try {
        parsed = JSON.parse(String(raw)) as LiveStreamFrame;
      } catch {
        // One bad frame is not a reason to abandon the stream.
        return;
      }
      // Guard the shape rather than trusting it: a malformed frame that set `p`
      // to undefined would blank a working hero.
      if (typeof parsed?.event_id !== 'number') return;
      if (parsed.source_snapshot !== undefined && snapshotFrameIsOversize(String(raw))) {
        delete parsed.source_snapshot;
      }
      // THE ONLY place the delivery clock is rearmed. A frame is the only
      // evidence that anything is still publishing.
      lastDataAt = now();
      const frame = parsed;
      try {
        deliver(() => {
          onFrame(frame);
          setDelivering(true);
          setStatus('open');
        });
      } finally {
        // Both are idempotent: a delivery that threw still leaves push marked
        // delivering, exactly as before the wrapper existed.
        setDelivering(true);
        setStatus('open');
      }
    };
    next.addEventListener('probability', onProbability);
    // Legacy clients ignore this event. It is not deduped by raw revision:
    // the authoritative fold can arrive after the same write's invalidation.
    next.addEventListener('folded_probability', onProbability);

    // #10090: a provisional blend, never routed through `onProbability`.
    next.addEventListener('preview', (event) => {
      if (stopped || handle !== next) return;
      onPreview?.((event as { data?: unknown })?.data);
    });
    next.addEventListener('preview_open_v3', (event) => {
      if (stopped || handle !== next) return;
      deps.onAuthorityPreviewOpen?.((event as { data?: unknown })?.data);
    });
    next.addEventListener('preview_v3', (event) => {
      if (stopped || handle !== next) return;
      const receivedAt = (deps.previewNow ?? now)();
      deps.onAuthorityPreview?.((event as { data?: unknown })?.data, receivedAt);
    });
    next.addEventListener('fold_preview_floor', (event) => {
      if (stopped || handle !== next) return;
      deps.onPreviewFloor?.((event as { data?: unknown })?.data);
    });

    next.addEventListener('heartbeat', (event) => {
      if (stopped || handle !== next) return;
      // TRANSPORT clock only. A heartbeat proves this server process is alive
      // and its socket is open. It proves nothing about the publisher, because
      // the web subscriber emits it regardless — which is exactly how a dead
      // `worker-ws` kept polling switched off behind a frozen number.
      lastMessageAt = now();
      const data = (event as { data?: unknown })?.data;
      const confirmedAt = heartbeatConfirmedAt(data);
      if (confirmedAt !== null) deps.onConfirmedAt?.(confirmedAt);
      const activityAt = heartbeatActivityAt(data);
      if (activityAt !== null) deps.onActivityAt?.(activityAt);
      const updates = heartbeatUpdates(data);
      if (updates.length > 0) deps.onUpdates?.(updates);
    });

    // The match ended. Terminal: the caller refetches once and settles the page
    // on the final number.
    next.addEventListener('closed', () => {
      if (handle !== next) return;
      stop();
      setStatus('closed');
    });

    // The connection ceiling. NOT terminal — see `rollOver`.
    next.addEventListener('reconnect', () => {
      if (handle !== next) return;
      rollOver();
    });

    next.addEventListener('error', () => {
      if (stopped || handle !== next) return;
      // EventSource retries by itself while CONNECTING; only give up once it
      // has actually closed, so a single blip does not bounce us to polling.
      if (next.readyState === EVENT_SOURCE_CLOSED) {
        stop();
        setStatus('unavailable');
      } else {
        onPreviewReset?.();
        transportRecoveryPending = true;
        setDelivering(false);
        setStatus('retrying');
      }
    });
  };

  const tick = () => {
    if (stopped) return;
    const at = now();

    // The backstop for an armed deadline (#10090), and the only reopen path
    // for an owner that injects no `schedule`.
    if (reopenAt !== null && at >= reopenAt) {
      connect();
      return;
    }
    if (!handle) return;

    // 1. TRANSPORT silent — no frames and no heartbeats for longer than we are
    //    willing to trust. Polling resumes either way; what the transport is
    //    DOING about the silence decides whether this is terminal.
    if (at - lastMessageAt > SILENCE_TIMEOUT_MS) {
      setDelivering(false);
      // Still CONNECTING: EventSource is retrying by itself and may well
      // succeed — this is a network that went away, not a server that said no,
      // and the two used to be the same branch. Closing the handle here is what
      // made a ~40s tunnel cost a reader push for the whole match (#8079): in
      // the production capture a 25s outage recovered 0.7s after the network
      // came back, while a 95s one reopened nothing, because by then this line
      // had closed the only handle that would have.
      //
      // Bounded, so an unreachable server is not retried forever.
      if (handle.readyState === EVENT_SOURCE_CONNECTING) {
        if (at - lastMessageAt > RETRY_GIVEUP_MS) {
          stop();
          setStatus('unavailable');
        } else {
          setStatus('retrying');
        }
        return;
      }
      // CLOSED (the browser gave up — a refused connect the server actually
      // answered) or OPEN-but-silent (a half-open socket nothing is retrying).
      // Neither will change on its own, so retire the stream as before.
      stop();
      setStatus('unavailable');
      return;
    }
    // 2. PUBLISHER dead (or the market is quiet) — the socket is fine and
    //    heartbeats keep arriving, but no price has been pushed for longer than
    //    we are willing to trust. Report NOT DELIVERING so polling resumes, and
    //    keep the stream open.
    if (at - lastDataAt > DATA_SILENCE_TIMEOUT_MS) {
      setDelivering(false);
      // Only an open socket can be quiet: a retrying one already said so.
      if (status === 'open') setStatus('quiet');
    }
  };

  return {
    start: connect,
    tick,
    stop,
    get state() {
      return { delivering, stopped, connections, reopenAt, status };
    },
  };
}
