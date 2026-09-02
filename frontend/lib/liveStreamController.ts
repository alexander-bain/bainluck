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
 * TIME IS A PARAMETER, NOT AN AMBIENT FACT. Everything schedules against `now()`
 * and is driven by `tick()`, so a test advances the clock rather than waiting on
 * one. No test in here branches on the wall clock (gotcha #44).
 */

export interface LiveStreamFrame {
  event_id: number;
  p: number | null;
  source: string;
  source_value: number | null;
  updated_at: string;
  status: string | null;
}

/** The slice of `EventSource` this controller uses. */
export interface StreamHandle {
  addEventListener(type: string, listener: (event: unknown) => void): void;
  close(): void;
  /** `EventSource.CLOSED` (2) once the browser has given up retrying. */
  readonly readyState: number;
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
}

/** Transport silence: three missed 20s heartbeats. The stream is dead. */
export const SILENCE_TIMEOUT_MS = 60_000;

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

/** How often the owner should call `tick()`. */
export const TICK_INTERVAL_MS = 5_000;

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
  };
}

export function createLiveStreamController(
  deps: LiveStreamDeps,
): LiveStreamController {
  const { open, now, onFrame, onDeliveringChange } = deps;

  let handle: StreamHandle | null = null;
  let delivering = false;
  let stopped = false;
  let connections = 0;
  let openedAt = 0;
  let lastMessageAt = 0;
  let lastDataAt = 0;
  let reopenAt: number | null = null;
  let consecutiveFastRollovers = 0;

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
    stopped = true;
    reopenAt = null;
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
    const lived = now() - openedAt;
    closeHandle();
    setDelivering(false);
    if (lived >= HEALTHY_STREAM_MS) consecutiveFastRollovers = 0;
    else consecutiveFastRollovers += 1;
    const delay = Math.min(
      RECONNECT_MAX_DELAY_MS,
      RECONNECT_BASE_DELAY_MS * 2 ** Math.max(0, consecutiveFastRollovers - 1),
    );
    reopenAt = now() + delay;
  };

  const connect = () => {
    if (stopped) return;
    reopenAt = null;
    let next: StreamHandle;
    try {
      next = open();
    } catch {
      // A transport that will not even construct is a refused connect.
      setDelivering(false);
      stopped = true;
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

    next.addEventListener('open', () => {
      if (stopped || handle !== next) return;
      lastMessageAt = now();
      lastDataAt = now();
      setDelivering(true);
    });

    next.addEventListener('probability', (event) => {
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
      // THE ONLY place the delivery clock is rearmed. A frame is the only
      // evidence that anything is still publishing.
      lastDataAt = now();
      onFrame(parsed);
      setDelivering(true);
    });

    next.addEventListener('heartbeat', () => {
      if (stopped || handle !== next) return;
      // TRANSPORT clock only. A heartbeat proves this server process is alive
      // and its socket is open. It proves nothing about the publisher, because
      // the web subscriber emits it regardless — which is exactly how a dead
      // `worker-ws` kept polling switched off behind a frozen number.
      lastMessageAt = now();
    });

    // The match ended. Terminal: the caller refetches once and settles the page
    // on the final number.
    next.addEventListener('closed', () => {
      if (handle !== next) return;
      stop();
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
      if (next.readyState === EVENT_SOURCE_CLOSED) stop();
      else setDelivering(false);
    });
  };

  const tick = () => {
    if (stopped) return;
    const at = now();

    if (reopenAt !== null && at >= reopenAt) {
      connect();
      return;
    }
    if (!handle) return;

    // 1. TRANSPORT dead — no frames, no heartbeats, and no error event either.
    //    Nothing will ever tell us; give up so the caller polls.
    if (at - lastMessageAt > SILENCE_TIMEOUT_MS) {
      stop();
      return;
    }
    // 2. PUBLISHER dead (or the market is quiet) — the socket is fine and
    //    heartbeats keep arriving, but no price has been pushed for longer than
    //    we are willing to trust. Report NOT DELIVERING so polling resumes, and
    //    keep the stream open.
    if (at - lastDataAt > DATA_SILENCE_TIMEOUT_MS) {
      setDelivering(false);
    }
  };

  return {
    start: connect,
    tick,
    stop,
    get state() {
      return { delivering, stopped, connections, reopenAt };
    },
  };
}
