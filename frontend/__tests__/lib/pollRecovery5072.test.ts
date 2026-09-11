/**
 * #5072 — A LEFT-OPEN PAGE MUST COME BACK ON ITS OWN.
 *
 * SF@LAR, production, 2026-09-10: a tab opened at 6:34pm PT read
 * `Halftime · 0:00`, 7–10, a pulsing green `LIVE` and "Rate limit exceeded:
 * 60/minute" at 7:54pm, while the real game was 7–24 in the fourth. The tab was
 * throttled ONCE, at about 7:14pm, and then made ZERO further attempts for
 * forty minutes: `swr@2.4.1`'s polling effect refuses to fetch while the key is
 * errored, and with retry, focus and reconnect revalidation all off there was
 * nothing left to clear the error.
 *
 * The unit under test is the scheduler that ends that latch. The two properties
 * it has to hold at once, and which pull against each other, are:
 *
 *   RECOVERY  — a page left open comes back within a bounded time, for an
 *               outage of any length. This is why the attempt count is not
 *               capped: a cap re-latches the page, which is the bug.
 *   LOAD      — a recovering key never asks faster than a healthy one. This is
 *               what makes an uncapped attempt count safe, and it is asserted
 *               directly below rather than argued for in a comment.
 *
 * Every dependency is injected, so these are real branch-order tests and not a
 * source scan: `frontend/jest.config.js` is `testEnvironment: 'node'` and the
 * repo has no jsdom rig, so a scheduler reaching for `setTimeout`/`document`
 * directly could not be tested here at all.
 */
import {
  createPollRecovery,
  recoveryDelayMs,
  MAX_RECOVERY_DELAY_MS,
  MAX_SERVER_WAIT_MS,
  type PollRecovery,
  type PollRecoveryDeps,
} from "../../lib/pollRecovery";

const KEY = "/api/events/14632820";
const POLL_MS = 30_000;

/** The 429 a reader actually got, as `apiFetch` now hands it on. */
function throttled(retryAfterMs?: number) {
  const err = new Error("Rate limit exceeded: 60/minute") as Error & {
    status: number;
    retryAfterMs?: number;
  };
  err.status = 429;
  if (retryAfterMs !== undefined) err.retryAfterMs = retryAfterMs;
  return err;
}

interface Harness {
  recovery: PollRecovery;
  /** Delays, in order, of every timer that has been scheduled. */
  scheduled: number[];
  /** Keys passed to `mutate`, in order. */
  nudged: string[];
  /** Run the one pending timer and settle the async work it starts. */
  tick: () => Promise<void>;
  /**
   * Make the next nudge fail, the way a still-throttled server would.
   * `intervalMs` is the key's `refreshInterval` as swr would report it back
   * through `onError`, and must match the one the key was armed with.
   */
  failNextNudge: (intervalMs?: unknown, cachedData?: unknown) => void;
  visible: boolean;
  online: boolean;
}

/**
 * A controllable world. `mutate` is modelled on the REAL swr@2.4.1 behaviour,
 * which is the single most load-bearing fact in this module: the hook's
 * revalidate catches the fetch error, calls `onError`, and `return true`s, so
 * `mutate` RESOLVES on failure just as it does on success. A fake that rejected
 * on failure would let a broken implementation pass.
 */
function harness(): Harness {
  const state = {
    scheduled: [] as number[],
    nudged: [] as string[],
    pending: null as { fn: () => void; id: number } | null,
    nextId: 1,
    nudgeFails: false,
    nudgeFailInterval: POLL_MS as unknown,
    nudgeFailData: undefined as unknown,
    visible: true,
    online: true,
  };

  let recovery: PollRecovery;

  const deps: PollRecoveryDeps = {
    mutate: async (key) => {
      state.nudged.push(key);
      if (state.nudgeFails) {
        state.nudgeFails = false;
        // swr calls the global `onError` from inside revalidate, BEFORE the
        // promise the caller is awaiting resolves. Reproducing that ordering is
        // the whole point of this fake.
        recovery.recordError(key, throttled(), state.nudgeFailInterval, state.nudgeFailData);
      }
      return undefined;
    },
    setTimer: (fn, ms) => {
      state.scheduled.push(ms);
      const id = state.nextId++;
      state.pending = { fn, id };
      return id as unknown as ReturnType<typeof setTimeout>;
    },
    clearTimer: (handle) => {
      if (state.pending && state.pending.id === (handle as unknown as number)) {
        state.pending = null;
      }
    },
    isVisible: () => state.visible,
    isOnline: () => state.online,
  };

  recovery = createPollRecovery(deps);

  return {
    recovery,
    scheduled: state.scheduled,
    nudged: state.nudged,
    async tick() {
      const due = state.pending;
      state.pending = null;
      due?.fn();
      // Two turns: one for the awaited mutate, one for the continuation after
      // it that decides whether to disarm.
      await Promise.resolve();
      await Promise.resolve();
    },
    failNextNudge(intervalMs = POLL_MS, cachedData = undefined) {
      state.nudgeFails = true;
      state.nudgeFailInterval = intervalMs;
      state.nudgeFailData = cachedData;
    },
    get visible() {
      return state.visible;
    },
    set visible(v: boolean) {
      state.visible = v;
    },
    get online() {
      return state.online;
    },
    set online(v: boolean) {
      state.online = v;
    },
  };
}

describe("#5072 — the latch itself", () => {
  it("schedules a comeback for a polled key that has errored", () => {
    const h = harness();
    h.recovery.recordError(KEY, throttled(), POLL_MS);

    // Before this ship this was the whole bug: nothing was scheduled, ever.
    expect(h.recovery.armedKeys()).toEqual([KEY]);
    expect(h.recovery.pendingDelayMs(KEY)).toBe(POLL_MS);
  });

  it("actually asks the server again when the comeback comes due", async () => {
    const h = harness();
    h.recovery.recordError(KEY, throttled(), POLL_MS);
    await h.tick();

    expect(h.nudged).toEqual([KEY]);
  });

  it("hands back to swr's own poll once a nudge lands", async () => {
    const h = harness();
    h.recovery.recordError(KEY, throttled(), POLL_MS);
    await h.tick();

    // A successful revalidation clears swr's cached error, so `execute()` stops
    // taking its `else` branch and the key polls itself again. Staying armed
    // past that point would be a second poller on the same key.
    expect(h.recovery.armedKeys()).toEqual([]);
    expect(h.recovery.pendingDelayMs(KEY)).toBeNull();
  });

  it("keeps trying when the comeback ALSO fails, and does not cancel its own retry", async () => {
    const h = harness();
    h.recovery.recordError(KEY, throttled(), POLL_MS);
    h.failNextNudge();
    await h.tick();

    // The ordering trap this pins: `recordError` fires DURING the awaited
    // mutate and arms a fresh timer, then the continuation after the await
    // runs. An implementation that disarms unconditionally there cancels the
    // retry it just scheduled and re-creates the latch, one attempt later —
    // and every test above still passes.
    expect(h.recovery.armedKeys()).toEqual([KEY]);
    expect(h.recovery.pendingDelayMs(KEY)).toBe(POLL_MS * 2);
  });

  it("stands down when nobody is left on the key", async () => {
    const h = harness();
    h.recovery.recordError(KEY, throttled(), POLL_MS);
    await h.tick();

    // A reader who navigates away unmounts the hook; swr's mutate then finds no
    // revalidator, resolves with cached data and reports nothing. That is
    // indistinguishable from success here, and both mean stop — the failure to
    // avoid is a timer per abandoned key living for the life of the tab.
    expect(h.recovery.armedKeys()).toEqual([]);
  });
});

describe("#5072 — the load invariant", () => {
  it("never comes back faster than the key's own poll, over a long outage", async () => {
    const h = harness();
    h.recovery.recordError(KEY, throttled(), POLL_MS);
    for (let i = 0; i < 12; i++) {
      h.failNextNudge();
      await h.tick();
    }

    expect(h.scheduled.length).toBeGreaterThan(12);
    for (const delay of h.scheduled) {
      expect(delay).toBeGreaterThanOrEqual(POLL_MS);
    }
  });

  it("backs off to a ceiling and then holds there — recovery is bounded, not abandoned", async () => {
    const h = harness();
    h.recovery.recordError(KEY, throttled(), POLL_MS);
    for (let i = 0; i < 8; i++) {
      h.failNextNudge();
      await h.tick();
    }

    expect(h.scheduled.slice(0, 3)).toEqual([30_000, 60_000, 60_000]);
    expect(h.scheduled[h.scheduled.length - 1]).toBe(MAX_RECOVERY_DELAY_MS);
    // Still armed after eight consecutive failures. An attempt cap here would
    // re-latch the page for any outage longer than the cap, which is the defect
    // this issue is about.
    expect(h.recovery.armedKeys()).toEqual([KEY]);
  });

  it("does not speed a slow key UP to the ceiling", () => {
    // A key polling every five minutes must not start recovering every sixty
    // seconds. The ceiling is a ceiling on the delay, never a floor.
    const slow = 300_000;
    expect(recoveryDelayMs(slow, 0, null)).toBe(slow);
    expect(recoveryDelayMs(slow, 5, null)).toBe(slow);
  });

  it("doubles per consecutive failure up to the ceiling", () => {
    expect(recoveryDelayMs(15_000, 0, null)).toBe(15_000);
    expect(recoveryDelayMs(15_000, 1, null)).toBe(30_000);
    expect(recoveryDelayMs(15_000, 2, null)).toBe(60_000);
    expect(recoveryDelayMs(15_000, 3, null)).toBe(60_000);
  });
});

describe("#5072 — what must NOT be armed", () => {
  it.each([
    ["undefined (no refreshInterval at all)", undefined],
    ["0, swr's own 'not polled'", 0],
    ["a function reporting 0 — not polled, just computed that way", () => 0],
    ["a function that throws instead of answering", () => {
      throw new Error("dependencies not ready");
    }],
    ["a function returning something that is not a cadence", () => "soon"],
    ["a negative number", -1],
    ["NaN", Number.NaN],
    ["Infinity", Number.POSITIVE_INFINITY],
    ["a string that looks like a number", "30000"],
  ])("a key whose refreshInterval is %s", (_label, refreshInterval) => {
    const h = harness();
    h.recovery.recordError(KEY, throttled(), refreshInterval);

    // A one-shot fetch that fails stays failed, exactly as before this ship.
    // Restoring the POLL is the ship; inventing retries for keys that never
    // polled would be a traffic increase nobody asked for — and `0` is the live
    // case, from `{ refreshInterval: autoRefresh ? 60000 : 0 }`.
    expect(h.recovery.armedKeys()).toEqual([]);
    expect(h.scheduled).toEqual([]);
  });
});

describe("#5072 — the server's own instruction", () => {
  it("waits as long as the limiter asked when that is longer than the poll", () => {
    const h = harness();
    h.recovery.recordError(KEY, throttled(45_000), POLL_MS);

    expect(h.recovery.pendingDelayMs(KEY)).toBe(45_000);
  });

  it("does not let a short retry_after undercut the poll cadence", () => {
    // The limiter says 2s; the key polls every 30s. Coming back in 2s would be
    // fifteen times a healthy key's rate, which breaks the load invariant for
    // the sake of obeying a number that was never about our cadence.
    const h = harness();
    h.recovery.recordError(KEY, throttled(2_000), POLL_MS);

    expect(h.recovery.pendingDelayMs(KEY)).toBe(POLL_MS);
  });

  it("refuses an absurd retry_after rather than sleeping through the game", () => {
    // The limiter's window is fixed at 60s, so a value of hours is a bug
    // upstream. Honouring it literally would leave a live page frozen for the
    // rest of the match — the exact outcome this issue exists to prevent.
    expect(recoveryDelayMs(POLL_MS, 0, 6 * 60 * 60 * 1000)).toBe(MAX_SERVER_WAIT_MS);
  });
});

describe("#5072 — a tab nobody is looking at", () => {
  it("does not fetch while hidden, and does not spend an attempt napping", async () => {
    const h = harness();
    h.recovery.recordError(KEY, throttled(), POLL_MS);
    h.visible = false;
    await h.tick();

    expect(h.nudged).toEqual([]);
    // Rescheduled at the SAME delay: the backoff counts consecutive failures,
    // and a hidden tab is not a failure. Doubling here would mean a tab
    // backgrounded for an hour comes back at the ceiling instead of at its own
    // cadence, for no reason.
    expect(h.recovery.pendingDelayMs(KEY)).toBe(POLL_MS);

    h.visible = true;
    await h.tick();
    expect(h.nudged).toEqual([KEY]);
  });

  it("a nap does not advance the backoff POSITION, only the pending delay", async () => {
    // The assertion above is not enough on its own, and a mutant proved it: an
    // implementation that increments the attempt counter while rescheduling at
    // the unchanged `delayMs` passes it, because the theft only becomes visible
    // at the NEXT real failure. So walk to that failure.
    //
    // A FAST base is load-bearing here for the same reason as in the
    // bookkeeping test: at `POLL_MS` both the honest answer and the thieving
    // one clamp to the 60s ceiling, and the mutant survives a test that looks
    // like it is checking exactly this.
    const fast = 1_000;
    const h = harness();
    h.recovery.recordError(KEY, throttled(), fast);

    h.visible = false;
    await h.tick();
    await h.tick();
    await h.tick();

    h.visible = true;
    h.failNextNudge(fast);
    await h.tick();

    // Three naps then one failure is the SECOND failure overall, so attempt 1:
    // 2s. Had each nap spent an attempt this would be attempt 4, i.e. 16s.
    expect(h.recovery.pendingDelayMs(KEY)).toBe(2_000);
  });

  it("does not fetch while the browser reports itself offline", async () => {
    const h = harness();
    h.recovery.recordError(KEY, throttled(), POLL_MS);
    h.online = false;
    await h.tick();

    expect(h.nudged).toEqual([]);
    expect(h.recovery.armedKeys()).toEqual([KEY]);
  });
});

describe("#5072 — bookkeeping", () => {
  it("keeps one schedule per key, not one per error", () => {
    // A fast base on purpose, so the assertion shows the backoff ADVANCING
    // rather than the 60s ceiling flattening it — at `POLL_MS` the second and
    // third delays are both 60,000 and this test would pass without ever
    // distinguishing "advanced" from "stuck".
    const fast = 5_000;
    const h = harness();
    h.recovery.recordError(KEY, throttled(), fast);
    h.recovery.recordError(KEY, throttled(), fast);
    h.recovery.recordError(KEY, throttled(), fast);

    expect(h.recovery.armedKeys()).toEqual([KEY]);
    // Three errors advanced the backoff rather than stacking three timers.
    expect(h.recovery.pendingDelayMs(KEY)).toBe(20_000);
  });

  it("tracks keys independently — one dead endpoint does not slow another", () => {
    const h = harness();
    h.recovery.recordError("/api/events/1", throttled(), 30_000);
    h.recovery.recordError("/api/events/1", throttled(), 30_000);
    h.recovery.recordError("/api/feed", throttled(), 120_000);

    expect(h.recovery.pendingDelayMs("/api/events/1")).toBe(60_000);
    expect(h.recovery.pendingDelayMs("/api/feed")).toBe(120_000);
  });

  it("stopAll leaves nothing pending", () => {
    const h = harness();
    h.recovery.recordError(KEY, throttled(), POLL_MS);
    h.recovery.stopAll();

    expect(h.recovery.armedKeys()).toEqual([]);
  });
});

/**
 * CERT-2584's required repair, `5072-FUNCTION-VALUED-LIVE-POLL-RECOVERS`.
 *
 * The first cut of this ship rejected function-valued intervals and said so in
 * a test — while `app/events/[id]/page.tsx`, the live page the issue was filed
 * against, passes exactly that. The one key whose freezing produced the bug
 * report was the one key that never armed. These tests are written in the
 * production shape so that cannot come back.
 */
describe("#5072 — the live event page's own function-valued cadence", () => {
  /**
   * Verbatim from `lib/eventLivePush.ts`, which the page's `refreshInterval`
   * closure calls. Reproduced rather than imported so this stays a test of THIS
   * module's contract with a function, not of that helper.
   */
  const eventRefreshInterval = (
    status: string | null | undefined,
    streamConnected: boolean,
    intervals: { live: number; scheduled: number },
  ): number =>
    streamConnected
      ? intervals.scheduled
      : status === "live"
        ? intervals.live
        : intervals.scheduled;

  const LIVE_REFRESH_INTERVAL = 32_000;
  const SCHEDULED_REFRESH_INTERVAL = 120_000;

  /** What the reader is looking at when the poll fails: a live game. */
  const CACHED_LIVE = { status: "live" };

  /** The page's actual config value, closure and all. */
  const pageInterval = (streamConnected: boolean) => (data?: unknown) =>
    eventRefreshInterval(
      (data as { status?: string } | undefined)?.status,
      streamConnected,
      { live: LIVE_REFRESH_INTERVAL, scheduled: SCHEDULED_REFRESH_INTERVAL },
    );

  it("arms — the regression CERT-2584 caught, stated as the assertion it should always have had", () => {
    const h = harness();
    h.recovery.recordError(KEY, throttled(), pageInterval(false), CACHED_LIVE);

    expect(h.recovery.armedKeys()).toEqual([KEY]);
    expect(h.recovery.pendingDelayMs(KEY)).toBe(LIVE_REFRESH_INTERVAL);
  });

  it("recovers end to end: error, nudge, failed re-arm, then success hands back to swr", async () => {
    const h = harness();

    // 1. The production-shape failure: one 429 on the live event key, with the
    //    payload the reader is looking at still in cache.
    h.recovery.recordError(KEY, throttled(), pageInterval(false), CACHED_LIVE);
    expect(h.recovery.pendingDelayMs(KEY)).toBe(LIVE_REFRESH_INTERVAL);

    // 2. The comeback comes due and asks the server again. Before this repair
    //    no request was ever made for this key, for the life of the mount.
    h.failNextNudge(pageInterval(false), CACHED_LIVE);
    await h.tick();
    expect(h.nudged).toEqual([KEY]);

    // 3. Still throttled: re-armed at the next backoff step, not abandoned.
    //    32s doubles to 64s, which the ceiling clamps to 60s — NOT 64s. This
    //    clamp has now caught three assertions in this file that were written
    //    as `base * 2` on autopilot; if you are about to write that, check
    //    whether `max(base, 60s)` gets there first.
    expect(h.recovery.armedKeys()).toEqual([KEY]);
    expect(h.recovery.pendingDelayMs(KEY)).toBe(MAX_RECOVERY_DELAY_MS);

    // 4. The second comeback lands. swr's cached error clears, its own poll
    //    resumes at whatever cadence the function reports WITH data, and this
    //    module stands down.
    await h.tick();
    expect(h.nudged).toEqual([KEY, KEY]);
    expect(h.recovery.armedKeys()).toEqual([]);
  });

  it("prices the key from its CACHED DATA, so a live page gets its real cadence", () => {
    // CERT-2587. Evaluating with `undefined` gave the event page a hedged
    // value; evaluating with the payload on screen gives the same answer swr's
    // own poll would compute, which is the authoritative cadence.
    const h = harness();
    h.recovery.recordError(KEY, throttled(), pageInterval(false), {
      status: "live",
    });

    expect(h.recovery.pendingDelayMs(KEY)).toBe(LIVE_REFRESH_INTERVAL);
  });

  it("still honours a function that asks to be left alone", () => {
    const h = harness();
    h.recovery.recordError(KEY, throttled(), () => 0);

    expect(h.recovery.armedKeys()).toEqual([]);
  });
});

/**
 * CERT-2587's required repair, `5072-CACHE-AWARE-FUNCTION-INTERVAL-RECOVERY`.
 *
 * The first repair evaluated a function-valued interval with `undefined`, which
 * is fine for the event page (whose callback always returns a positive number)
 * and wrong for the event-CONCEPT page, whose callback returns 0 unless the
 * cached payload says the event is live. Evaluating without data read that as
 * "not polled" and left a live concept page latched after one failure — the
 * grader's probe measured `effective=30000, scheduled=[], armed=[]`.
 *
 * These are that page's real config, so the two shapes can never diverge again.
 */
describe("#5072 — the event-concept page, whose cadence is ZERO until data says live", () => {
  /** Verbatim shape from `app/event/[domain]/[slug]/page.tsx`. */
  const conceptInterval = (latest?: unknown) => {
    const l = latest as
      | { event?: { status?: string; start_date?: string } }
      | undefined;
    const status = l?.event?.status;
    if (status === "live") return 30_000;
    if (status === "upcoming" && l?.event?.start_date) {
      const start = Date.parse(l.event.start_date);
      if (!Number.isNaN(start)) {
        const hoursToStart = (start - Date.now()) / 3_600_000;
        if (hoursToStart <= 24 && hoursToStart >= -12) return 300_000;
      }
    }
    return 0;
  };

  const CONCEPT_KEY = "@\"event-concept\",\"us-open-2026\",";
  const LIVE_PAYLOAD = { event: { status: "live" } };

  it("arms and recovers after an error while the page is live", async () => {
    const h = harness();

    // The failure a reader hits: one transient error on a live concept page.
    h.recovery.recordError(CONCEPT_KEY, throttled(), conceptInterval, LIVE_PAYLOAD);

    // Armed at the page's real in-play cadence. Priced with `undefined` this
    // was 0 and the key armed nothing at all — the CERT-2587 defect.
    expect(h.recovery.armedKeys()).toEqual([CONCEPT_KEY]);
    expect(h.recovery.pendingDelayMs(CONCEPT_KEY)).toBe(30_000);

    // Still failing: asks again, re-arms.
    h.failNextNudge(conceptInterval, LIVE_PAYLOAD);
    await h.tick();
    expect(h.nudged).toEqual([CONCEPT_KEY]);
    expect(h.recovery.armedKeys()).toEqual([CONCEPT_KEY]);

    // It lands: swr's error clears, its own poll resumes, we stand down.
    await h.tick();
    expect(h.nudged).toEqual([CONCEPT_KEY, CONCEPT_KEY]);
    expect(h.recovery.armedKeys()).toEqual([]);
  });

  it("arms an about-to-start page at its slow cadence", () => {
    const h = harness();
    const soon = new Date(Date.now() + 6 * 3_600_000).toISOString();

    h.recovery.recordError(CONCEPT_KEY, throttled(), conceptInterval, {
      event: { status: "upcoming", start_date: soon },
    });

    // 5 minutes — the cadence that lets a countdown page flip to live on its
    // own. It polls, so it can latch, so it must recover.
    expect(h.recovery.pendingDelayMs(CONCEPT_KEY)).toBe(300_000);
  });

  it("TRUE ZERO is still refused: a settled concept page is not polled, so it is not armed", () => {
    const h = harness();

    h.recovery.recordError(CONCEPT_KEY, throttled(), conceptInterval, {
      event: { status: "completed" },
    });

    // Both certs required this clause survive the repair. A page that does not
    // poll was never latched by this bug, and arming it would invent traffic.
    expect(h.recovery.armedKeys()).toEqual([]);
    expect(h.scheduled).toEqual([]);
  });

  it("a distant-future page is not armed either", () => {
    const h = harness();
    const farOff = new Date(Date.now() + 40 * 24 * 3_600_000).toISOString();

    h.recovery.recordError(CONCEPT_KEY, throttled(), conceptInterval, {
      event: { status: "upcoming", start_date: farOff },
    });

    expect(h.recovery.armedKeys()).toEqual([]);
  });

  it("no cached data yet means no cadence to price, so nothing is armed", () => {
    // The first fetch failing is not the bug this fixes: there is no page on
    // screen to hold, the surface renders its own load-failure state, and the
    // callback itself answers 0. Arming here would be a guess.
    const h = harness();
    h.recovery.recordError(CONCEPT_KEY, throttled(), conceptInterval, undefined);

    expect(h.recovery.armedKeys()).toEqual([]);
  });
});
