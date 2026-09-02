/**
 * CERT-717 — the two lifecycle defects that blocked live/034, and their fixes.
 *
 * Both were rated P1 / confidence high, and both were invisible to every gate:
 * backend live-push + startup 51/51 and frontend Jest 27/27 passed at the
 * blocked SHA. Nothing exercised either lifecycle, because the lifecycle was
 * welded into a React effect and this suite has no jsdom.
 *
 *   P1-a  Every healthy stream emits `reconnect` at the server's 900s ceiling.
 *         The client closed its only EventSource on that event and, with effect
 *         dependencies of `[eventId, enabled]`, never built a replacement — so
 *         push lasted exactly fifteen minutes and then silently became the 32s
 *         poll for the rest of the match.
 *
 *   P1-b  The heartbeat is emitted by the WEB subscriber on its own timer,
 *         independent of the publisher. The client treated each one as proof of
 *         delivery, so a dead `worker-ws` left `connected: true`, polling
 *         DISABLED, and a frozen number on screen until the 15-minute ceiling.
 *
 * Time is injected, so these advance a clock rather than wait on one, and no
 * assertion here branches on the wall clock (gotcha #44).
 */

import {
  DATA_SILENCE_TIMEOUT_MS,
  HEALTHY_STREAM_MS,
  RECONNECT_BASE_DELAY_MS,
  RECONNECT_MAX_DELAY_MS,
  SILENCE_TIMEOUT_MS,
  TICK_INTERVAL_MS,
  createLiveStreamController,
  type StreamHandle,
} from '@/lib/liveStreamController';

/** The server's own connection ceiling, `MAX_CONNECTION_S` in the route. */
const MAX_CONNECTION_MS = 900_000;

class FakeSource implements StreamHandle {
  readyState = 1;
  closed = false;
  private listeners = new Map<string, ((event: unknown) => void)[]>();

  addEventListener(type: string, listener: (event: unknown) => void) {
    const existing = this.listeners.get(type) ?? [];
    existing.push(listener);
    this.listeners.set(type, existing);
  }

  close() {
    this.closed = true;
    this.readyState = 2;
  }

  emit(type: string, data?: unknown) {
    for (const listener of this.listeners.get(type) ?? []) {
      listener(data === undefined ? {} : { data });
    }
  }
}

function harness() {
  let clock = 1_000_000;
  const sources: FakeSource[] = [];
  const delivering: boolean[] = [];
  const frames: unknown[] = [];

  const controller = createLiveStreamController({
    open: () => {
      const source = new FakeSource();
      sources.push(source);
      return source;
    },
    now: () => clock,
    onFrame: (frame) => frames.push(frame),
    onDeliveringChange: (value) => delivering.push(value),
  });

  /** Advance the clock, running a `tick()` on the hook's real cadence. */
  const advance = (ms: number) => {
    const until = clock + ms;
    while (clock < until) {
      clock = Math.min(until, clock + TICK_INTERVAL_MS);
      controller.tick();
    }
  };

  /**
   * Advance the way a HEALTHY server actually behaves: a heartbeat every 20s.
   *
   * Without this, advancing 900s in silence trips the transport watchdog at 60s
   * and the stream is already dead before the rollover under test arrives — a
   * false red that says nothing about the rollover. The real route heartbeats
   * on `HEARTBEAT_INTERVAL_S`, so a test reaching the 900s ceiling has to as
   * well.
   */
  const advanceLive = (ms: number) => {
    for (let elapsed = 0; elapsed < ms; elapsed += 20_000) {
      advance(Math.min(20_000, ms - elapsed));
      sources[sources.length - 1].emit('heartbeat');
    }
  };

  const live = () => sources[sources.length - 1];
  const frame = (p: number) =>
    JSON.stringify({
      event_id: 42,
      p,
      source: 'kalshi',
      source_value: p,
      updated_at: new Date(clock).toISOString(),
      status: 'live',
    });

  return {
    controller, sources, delivering, frames, advance, advanceLive, live, frame,
    at: () => clock,
  };
}

// ---------------------------------------------------------------------------
// P1-a — the rollover must reconnect, not retire
// ---------------------------------------------------------------------------

describe('CERT-717 P1-a: the server-directed rollover', () => {
  it('opens a REPLACEMENT stream instead of expiring into polling', () => {
    const h = harness();
    h.controller.start();
    h.live().emit('open');

    // A normal match: frames keep arriving right up to the ceiling.
    for (let elapsed = 0; elapsed < MAX_CONNECTION_MS; elapsed += 60_000) {
      h.advance(60_000);
      h.live().emit('probability', h.frame(0.55));
    }
    expect(h.sources).toHaveLength(1);
    expect(h.controller.state.delivering).toBe(true);

    // The server hits `MAX_CONNECTION_S` and asks for a fresh socket.
    h.live().emit('reconnect');

    expect(h.sources[0].closed).toBe(true);
    expect(h.controller.state.delivering).toBe(false);

    h.advance(RECONNECT_BASE_DELAY_MS + TICK_INTERVAL_MS);

    expect(h.sources).toHaveLength(2);
    h.live().emit('open');
    h.live().emit('probability', h.frame(0.61));
    expect(h.controller.state.delivering).toBe(true);
    expect(h.controller.state.stopped).toBe(false);
  });

  it('polls only during the gap, and the gap is short', () => {
    // The regression this pins is not "did it reconnect" but "how long was the
    // reader on the 32s poll while it did". The old behaviour was FOREVER.
    const h = harness();
    h.controller.start();
    h.live().emit('open');
    h.advanceLive(MAX_CONNECTION_MS);
    const ceiling = h.at();
    h.live().emit('reconnect');

    expect(h.controller.state.reopenAt).not.toBeNull();
    const gap = (h.controller.state.reopenAt as number) - ceiling;
    expect(gap).toBeLessThanOrEqual(RECONNECT_BASE_DELAY_MS);
  });

  it('a match longer than four ceilings keeps push the whole way', () => {
    // The user-visible claim, at the length that used to break it. Four
    // rollovers is an hour of play; the old client delivered the first fifteen
    // minutes of that and polled the other forty-five.
    const h = harness();
    h.controller.start();

    for (let i = 0; i < 4; i += 1) {
      h.live().emit('open');
      h.advanceLive(MAX_CONNECTION_MS);
      h.live().emit('probability', h.frame(0.5 + i / 100));
      h.live().emit('reconnect');
      h.advance(RECONNECT_BASE_DELAY_MS + TICK_INTERVAL_MS);
    }
    h.live().emit('open');
    h.live().emit('probability', h.frame(0.66));

    expect(h.sources).toHaveLength(5);
    expect(h.controller.state.delivering).toBe(true);
    expect(h.frames).toHaveLength(5);
    // Each stream lived a full ceiling, so no rollover was ever treated as a
    // failure and the backoff never grew past its base.
    expect(MAX_CONNECTION_MS).toBeGreaterThan(HEALTHY_STREAM_MS);
  });

  it('a server that rolls over instantly is backed off, not hammered', () => {
    const h = harness();
    h.controller.start();

    const gaps: number[] = [];
    for (let i = 0; i < 8; i += 1) {
      h.live().emit('open');
      const before = h.at();
      h.live().emit('reconnect');
      gaps.push((h.controller.state.reopenAt as number) - before);
      h.advance(RECONNECT_MAX_DELAY_MS + TICK_INTERVAL_MS);
    }

    // It keeps reconnecting — an instantly-rolling server is still a server —
    // but each gap is at least as long as the last and none exceeds the cap, so
    // this can never become a flood.
    expect(gaps[0]).toBe(RECONNECT_BASE_DELAY_MS);
    expect(gaps[gaps.length - 1]).toBe(RECONNECT_MAX_DELAY_MS);
    for (let i = 1; i < gaps.length; i += 1) {
      expect(gaps[i]).toBeGreaterThanOrEqual(gaps[i - 1]);
      expect(gaps[i]).toBeLessThanOrEqual(RECONNECT_MAX_DELAY_MS);
    }
  });

  it('`closed` is still terminal — a finished match must not reconnect', () => {
    // CONTROL, and the one that stops the fix from being "reconnect always".
    // The match ending and the connection ageing out arrive as different
    // events for exactly this reason.
    const h = harness();
    h.controller.start();
    h.live().emit('open');
    h.live().emit('closed');

    h.advance(RECONNECT_MAX_DELAY_MS * 4);

    expect(h.sources).toHaveLength(1);
    expect(h.controller.state.stopped).toBe(true);
    expect(h.controller.state.delivering).toBe(false);
  });

  it('a refused connect degrades to polling and does not retry-loop', () => {
    // CONTROL. 409 non-live, 503 at capacity and 404 all surface as `error`,
    // and reconnecting against a server that has said no would be a flood
    // dressed up as resilience.
    const h = harness();
    h.controller.start();
    const source = h.live();
    source.readyState = 2;
    source.emit('error');

    h.advance(RECONNECT_MAX_DELAY_MS * 4);

    expect(h.sources).toHaveLength(1);
    expect(h.controller.state.stopped).toBe(true);
  });

  it('stop() beats a scheduled reopen — an unmounted page opens nothing', () => {
    const h = harness();
    h.controller.start();
    h.live().emit('open');
    h.live().emit('reconnect');
    expect(h.controller.state.reopenAt).not.toBeNull();

    h.controller.stop();
    h.advance(RECONNECT_MAX_DELAY_MS * 2);

    expect(h.sources).toHaveLength(1);
    // Belt AND braces, and the second one is not decoration: `tick()` bails on
    // `stopped` before it ever reads `reopenAt`, so a stale timestamp left here
    // would never fire — but it would be reported, and a stopped controller
    // that says it is about to reconnect is a lie to whoever reads this state.
    expect(h.controller.state.reopenAt).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// P1-b — a heartbeat is not a delivery
// ---------------------------------------------------------------------------

describe('CERT-717 P1-b: a dead publisher behind a healthy transport', () => {
  it('resumes polling when heartbeats continue but no price is pushed', () => {
    // THE DEFECT, exactly: `worker-ws` dies, the web subscriber's Redis
    // subscription stays healthy, so heartbeats arrive forever. The old client
    // set `connected = true` on each one, polling stayed disabled, and the hero
    // held a stale number until the 15-minute ceiling.
    const h = harness();
    h.controller.start();
    h.live().emit('open');
    h.live().emit('probability', h.frame(0.5));
    expect(h.controller.state.delivering).toBe(true);

    // 20s heartbeats, and nothing else, for well past the delivery budget.
    for (let elapsed = 0; elapsed < DATA_SILENCE_TIMEOUT_MS + 30_000; elapsed += 20_000) {
      h.advance(20_000);
      h.live().emit('heartbeat');
    }

    expect(h.controller.state.delivering).toBe(false);
    // ...and the transport is NOT torn down: it is healthy, and the market may
    // simply be quiet. The moment something publishes, push takes back over.
    expect(h.controller.state.stopped).toBe(false);
    expect(h.live().closed).toBe(false);
  });

  it('a frame after the quiet spell restores push', () => {
    const h = harness();
    h.controller.start();
    h.live().emit('open');

    for (let elapsed = 0; elapsed < DATA_SILENCE_TIMEOUT_MS + 30_000; elapsed += 20_000) {
      h.advance(20_000);
      h.live().emit('heartbeat');
    }
    expect(h.controller.state.delivering).toBe(false);

    h.live().emit('probability', h.frame(0.72));

    expect(h.controller.state.delivering).toBe(true);
    expect(h.frames).toHaveLength(1);
  });

  it('a delivering stream is never demoted for being briefly quiet', () => {
    // CONTROL. Without this the fix reads as "flap to polling constantly",
    // which would throw away the ship — the whole point is that a moving
    // market never waits 32s.
    const h = harness();
    h.controller.start();
    h.live().emit('open');

    for (let elapsed = 0; elapsed < DATA_SILENCE_TIMEOUT_MS * 3; elapsed += 30_000) {
      h.advance(30_000);
      h.live().emit('probability', h.frame(0.5));
    }

    expect(h.controller.state.delivering).toBe(true);
    expect(h.delivering.filter((v) => v === false)).toHaveLength(0);
  });

  it('heartbeats still hold the TRANSPORT watchdog off', () => {
    // CONTROL for the other direction: the heartbeat was made a named event
    // precisely so the client could observe it, and if it stopped counting for
    // transport liveness the watchdog would tear down every quiet market.
    const h = harness();
    h.controller.start();
    h.live().emit('open');

    for (let elapsed = 0; elapsed < SILENCE_TIMEOUT_MS * 3; elapsed += 20_000) {
      h.advance(20_000);
      h.live().emit('heartbeat');
    }

    expect(h.controller.state.stopped).toBe(false);
    expect(h.live().closed).toBe(false);
  });

  it('total silence still tears the stream down', () => {
    // CONTROL. Transport death and publisher death are different failures with
    // different responses, and the fix must not have collapsed the first into
    // the second — a socket receiving literally nothing has to be abandoned.
    const h = harness();
    h.controller.start();
    h.live().emit('open');

    h.advance(SILENCE_TIMEOUT_MS + TICK_INTERVAL_MS * 2);

    expect(h.controller.state.stopped).toBe(true);
    expect(h.controller.state.delivering).toBe(false);
    expect(h.sources[0].closed).toBe(true);
  });

  it('the delivery budget is longer than the transport budget', () => {
    // Ordering matters: if delivery were the tighter of the two, a dead
    // transport would be reported as a quiet publisher and the stream would be
    // held open on a socket that will never speak again.
    expect(DATA_SILENCE_TIMEOUT_MS).toBeGreaterThan(SILENCE_TIMEOUT_MS);
  });
});

// ---------------------------------------------------------------------------
// The contract the caller depends on
// ---------------------------------------------------------------------------

describe('CERT-717: what the page is entitled to assume', () => {
  it('reports delivering=false exactly once per transition', () => {
    // `/events/[id]` refetches ONCE on the falling edge. A callback that fired
    // on every tick would turn a quiet market into a refetch storm.
    const h = harness();
    h.controller.start();
    h.live().emit('open');

    for (let elapsed = 0; elapsed < DATA_SILENCE_TIMEOUT_MS * 3; elapsed += 20_000) {
      h.advance(20_000);
      h.live().emit('heartbeat');
    }

    expect(h.delivering).toEqual([true, false]);
  });

  it('a malformed frame neither delivers nor abandons the stream', () => {
    const h = harness();
    h.controller.start();
    h.live().emit('open');
    h.live().emit('probability', '{not json');
    h.live().emit('probability', JSON.stringify({ p: 0.5 }));

    expect(h.frames).toHaveLength(0);
    expect(h.controller.state.stopped).toBe(false);
  });

  it('a transport that refuses to construct degrades to polling', () => {
    const controller = createLiveStreamController({
      open: () => {
        throw new Error('blocked');
      },
      now: () => 0,
      onFrame: () => undefined,
      onDeliveringChange: () => undefined,
    });

    controller.start();

    expect(controller.state.stopped).toBe(true);
    expect(controller.state.delivering).toBe(false);
  });
});
