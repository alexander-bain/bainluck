/**
 * #8079 — a reader who loses signal for ~40 seconds must not lose live push for
 * the rest of the page-view.
 *
 * WHERE THE NUMBERS COME FROM. These are not invented thresholds. They are a
 * production capture on a live Kalshi-covered page (`15317099`, release
 * `0896cf4e`, 2026-09-22 20:09:38Z, one held page, socket-level cut —
 * `artifacts-live-515/`):
 *
 *   last heartbeat   159.9s
 *   network cut      178.0s   (18.1s into the heartbeat cycle)
 *   retries cease   ~219.9s   = lastMessageAt + SILENCE_TIMEOUT_MS
 *   network back     272.9s -> zero stream requests in the following 151s
 *
 * and, in the SAME run, a 25s outage that recovered `open` 0.7s after the
 * network returned and moved the hero on a real frame. So EventSource retries
 * perfectly well on its own; the only thing that stopped it was this controller
 * closing the handle on a silence it read as death.
 *
 * THE DISTINCTION UNDER TEST is refused vs failed. A server that answered (409
 * non-live, 503 at capacity, 404) leaves the browser at CLOSED and must stay
 * terminal — reconnecting into a server that said no is a flood dressed as
 * resilience, and that control lives in `liveStreamControllerCert717.test.ts`
 * as well as below. A network that went away leaves the browser at CONNECTING,
 * retrying, and deserves the grace.
 *
 * Every control here is the arm that stops the fix becoming "reconnect always".
 */
import {
  DATA_SILENCE_TIMEOUT_MS,
  RETRY_GIVEUP_MS,
  SILENCE_TIMEOUT_MS,
  TICK_INTERVAL_MS,
  createLiveStreamController,
  type StreamHandle,
} from '@/lib/liveStreamController';

const CONNECTING = 0;
const OPEN = 1;
const CLOSED = 2;

class FakeSource implements StreamHandle {
  readyState = OPEN;
  closed = false;
  private listeners = new Map<string, ((event: unknown) => void)[]>();

  addEventListener(type: string, listener: (event: unknown) => void) {
    const existing = this.listeners.get(type) ?? [];
    existing.push(listener);
    this.listeners.set(type, existing);
  }

  close() {
    this.closed = true;
    this.readyState = CLOSED;
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

  const advance = (ms: number) => {
    const until = clock + ms;
    while (clock < until) {
      clock = Math.min(until, clock + TICK_INTERVAL_MS);
      controller.tick();
    }
  };

  const live = () => sources[sources.length - 1];
  const frame = (p: number) =>
    JSON.stringify({
      event_id: 42, p, source: 'kalshi', source_value: p,
      updated_at: new Date(clock).toISOString(), status: 'live',
    });

  /** What the browser does when the network disappears under an open stream. */
  const loseNetwork = () => {
    live().readyState = CONNECTING;
    live().emit('error');
  };
  /** What it does when the network comes back and the retry succeeds. */
  const regainNetwork = () => {
    live().readyState = OPEN;
    live().emit('open');
  };

  return { controller, sources, delivering, frames, advance, live, frame, loseNetwork, regainNetwork };
}

describe('#8079: an outage must not be permanent', () => {
  it('keeps the retrying stream alive past the silence budget', () => {
    const h = harness();
    h.controller.start();
    h.live().emit('open');
    h.loseNetwork();

    h.advance(SILENCE_TIMEOUT_MS + TICK_INTERVAL_MS * 4);

    // Assert what SURVIVES, not merely that nothing was flagged: the handle is
    // the whole fix, because closing it is what made the loss permanent.
    expect(h.live().closed).toBe(false);
    expect(h.controller.state.stopped).toBe(false);
    // ...and the reader is on polling throughout, which is the floor this is
    // not allowed to trade away.
    expect(h.controller.state.delivering).toBe(false);
  });

  it('push comes back when the network does, on the same handle', () => {
    const h = harness();
    h.controller.start();
    h.live().emit('open');
    h.loseNetwork();
    h.advance(SILENCE_TIMEOUT_MS + TICK_INTERVAL_MS * 4);

    h.regainNetwork();
    h.live().emit('probability', h.frame(0.61));

    expect(h.controller.state.delivering).toBe(true);
    expect(h.frames).toHaveLength(1);
    // No second EventSource was constructed — the browser's own retry did it,
    // which is the mechanism the production run measured recovering in 0.7s.
    expect(h.sources).toHaveLength(1);
  });

  it('the measured 41.9s tunnel now survives', () => {
    // The production specimen, replayed to the second: a heartbeat, 18.1s of
    // normal running, the network goes, and 41.9s of nothing. That is 60.0s
    // since the last message — exactly where the old code retired the stream,
    // and the reason a reader only got 41.9s of grace rather than the 60s the
    // constant appears to promise.
    const CYCLE_SPENT_BEFORE_OUTAGE = 18_100;
    const OUTAGE = 41_900;
    // Self-check, because the first draft of this test advanced the 18.1s on
    // the WRONG side of the heartbeat: total silence came to 41.9s, never
    // crossed the budget, and the test passed against a controller with the fix
    // reverted. A replay that does not reach the branch proves nothing, so the
    // arithmetic asserts itself rather than being trusted.
    expect(CYCLE_SPENT_BEFORE_OUTAGE + OUTAGE).toBe(SILENCE_TIMEOUT_MS);

    const h = harness();
    h.controller.start();
    h.live().emit('open');
    h.live().emit('heartbeat');
    h.advance(CYCLE_SPENT_BEFORE_OUTAGE);
    h.loseNetwork();
    h.advance(OUTAGE + TICK_INTERVAL_MS * 2);

    // The branch was reached: the watchdog stood the caller back on polling.
    expect(h.controller.state.delivering).toBe(false);
    // ...and, unlike production, the stream is still there to recover on.
    expect(h.live().closed).toBe(false);

    h.regainNetwork();
    h.live().emit('probability', h.frame(0.58));

    expect(h.frames).toHaveLength(1);
    expect(h.controller.state.delivering).toBe(true);
  });

  it('past the transport budget the caller is polling, however it got there', () => {
    // `StreamHandle` is an injected interface, and nothing in it promises that
    // a transport announces its own failure: a handle may simply BE at
    // CONNECTING, with no error event ever dispatched. Every other route into
    // the silence branch has already reported delivering=false (the error
    // handler, or `stop()`), so without this case the branch's own
    // `setDelivering(false)` is unreachable — a mutant that deletes it passes
    // all the other tests. The invariant is worth holding on its own terms:
    // past the budget, push is not delivering, whatever route the transport took.
    const h = harness();
    h.controller.start();
    h.live().emit('open');
    expect(h.controller.state.delivering).toBe(true);

    // Silent failure: the state changes, nothing is announced.
    h.live().readyState = CONNECTING;
    h.advance(SILENCE_TIMEOUT_MS + TICK_INTERVAL_MS * 2);

    expect(h.controller.state.delivering).toBe(false);
    expect(h.live().closed).toBe(false);
  });

  it('CONTROL: a retry that never succeeds is still given up on', () => {
    // The bound. Without it this is an EventSource retrying into an unreachable
    // server until the reader closes the tab.
    const h = harness();
    h.controller.start();
    h.live().emit('open');
    h.loseNetwork();

    h.advance(RETRY_GIVEUP_MS + TICK_INTERVAL_MS * 2);

    expect(h.controller.state.stopped).toBe(true);
    expect(h.live().closed).toBe(true);
  });

  it('CONTROL: the giveup bound is looser than the silence budget', () => {
    // If these crossed, the grace window would be empty and every assertion
    // above would pass for the wrong reason.
    expect(RETRY_GIVEUP_MS).toBeGreaterThan(SILENCE_TIMEOUT_MS);
    expect(RETRY_GIVEUP_MS).toBeGreaterThan(DATA_SILENCE_TIMEOUT_MS);
  });

  it('CONTROL: a refused connect is still terminal on the silence path', () => {
    // 409/503/404 leave the browser CLOSED. The error handler already retires
    // these; this asserts the SILENCE path agrees, so the grace cannot be
    // reached by a server that said no.
    const h = harness();
    h.controller.start();
    h.live().readyState = CLOSED;

    h.advance(SILENCE_TIMEOUT_MS + TICK_INTERVAL_MS * 2);

    expect(h.controller.state.stopped).toBe(true);
    expect(h.sources).toHaveLength(1);
  });

  it('CONTROL: a half-open socket nothing is retrying is still torn down', () => {
    // readyState OPEN with no traffic at all: the browser thinks it is fine and
    // will never retry, so grace would just hold a dead socket. This is the
    // `total silence still tears the stream down` case, kept honest here.
    const h = harness();
    h.controller.start();
    h.live().emit('open');

    h.advance(SILENCE_TIMEOUT_MS + TICK_INTERVAL_MS * 2);

    expect(h.controller.state.stopped).toBe(true);
    expect(h.live().closed).toBe(true);
  });

  it('CONTROL: a heartbeat during the grace is not a delivery', () => {
    // The CERT-717 P1-b rule, re-asserted inside the new window: a transport
    // that revives without the publisher reviving must NOT report delivering,
    // or the caller switches polling off behind a frozen number.
    const h = harness();
    h.controller.start();
    h.live().emit('open');
    h.live().emit('probability', h.frame(0.5));
    h.loseNetwork();
    h.advance(SILENCE_TIMEOUT_MS + TICK_INTERVAL_MS * 2);
    expect(h.controller.state.delivering).toBe(false);

    // Network back, transport healthy, publisher silent.
    h.live().readyState = OPEN;
    for (let elapsed = 0; elapsed < DATA_SILENCE_TIMEOUT_MS * 2; elapsed += 20_000) {
      h.advance(20_000);
      h.live().emit('heartbeat');
    }

    expect(h.controller.state.delivering).toBe(false);
    expect(h.frames).toHaveLength(1);
  });

  it('CONTROL: an outage inside the budget is untouched by any of this', () => {
    // The short arm the production run used as its positive control: a blip
    // shorter than SILENCE_TIMEOUT_MS never reaches the new branch at all.
    const h = harness();
    h.controller.start();
    h.live().emit('open');
    h.loseNetwork();
    h.advance(SILENCE_TIMEOUT_MS / 2);
    h.regainNetwork();
    h.live().emit('probability', h.frame(0.58));

    expect(h.controller.state.stopped).toBe(false);
    expect(h.controller.state.delivering).toBe(true);
    expect(h.frames).toHaveLength(1);
  });
});
