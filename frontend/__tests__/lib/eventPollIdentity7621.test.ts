/**
 * #7621 — A LEFT-OPEN EVENT PAGE MUST KEEP ASKING THE SERVER.
 *
 * ux/1399 watched an NFL event page, opened once and never reloaded, read
 * "No result reported · last score 19-23" with a 0% – 100% hero thirteen minutes
 * after the game ended 23–19, while a fresh load of the same url in the same
 * minute rendered `Final / Browns WON`.
 *
 * The cause is an identity bug, not a logic bug: swr keeps `refreshInterval` in
 * its polling effect's dependency array and clears the pending timeout on
 * cleanup, so an inline arrow — a new function every render — restarted the
 * poll's countdown from zero on every render. The event page re-renders about
 * once a second for its countdown ring, so a 120,000ms timer could never reach
 * its deadline.
 *
 * ═══ WHAT EACH GUARD BELOW IS FOR, AND WHY NONE OF THEM IS THE OTHERS ═══
 *
 * 1. THE PREMISE. That swr behaves as described is a fact about a pinned
 *    dependency, not about our code, and every other test here is worthless if
 *    it stops being true. So it is read out of the installed package rather than
 *    trusted from a comment — an swr upgrade that changes it fails HERE, loudly,
 *    instead of quietly making the fix pointless.
 *
 * 2. THE RULE, EXERCISED BOTH WAYS (gotcha #43). A stalled page must refetch AND
 *    a healthy page must not gain a fetch per render. Both arms are driven
 *    through the same simulation of swr's real effect lifecycle, so the test can
 *    fail in either direction.
 *
 * 3. THE APPLICATION. That the pages actually pass a stable reference. A rule
 *    nothing calls is not a fix, and this is the assertion that fails if someone
 *    inlines the arrow again — which is the precise regression.
 *
 * 4. STABILITY IS NOT STALENESS. A permanently-stable callback is only correct
 *    because it closes over nothing reactive. That is an assumption about OUR
 *    factory, so it is measured: one held reference must still track the ref
 *    flipping underneath it.
 */

import { readFileSync } from "fs";
import path from "path";

import {
  eventRefreshInterval,
  makeEventRefreshInterval,
} from "@/lib/eventLivePush";

const LIVE = 32_000;
const SCHEDULED = 120_000;

// ───────────────────────────────────────────────────────────────────────────
// 1. THE PREMISE: swr@2.4.1 really does re-arm on a new `refreshInterval`.
// ───────────────────────────────────────────────────────────────────────────

describe("the swr behaviour this fix depends on", () => {
  const swrSource = readFileSync(
    path.join(__dirname, "../../node_modules/swr/dist/index/index.js"),
    "utf8",
  );

  /**
   * The polling effect, isolated by its only unique marker. Anchored on
   * `refreshWhenHidden` rather than on a line number so an swr patch release
   * that moves the code does not read as a behaviour change.
   */
  const pollingEffect = (() => {
    const at = swrSource.indexOf("refreshWhenHidden || getConfig().isVisible()");
    expect(at).toBeGreaterThan(-1);
    // From the effect's opening through the end of its dependency array.
    const start = swrSource.lastIndexOf("useIsomorphicLayoutEffect", at);
    const end = swrSource.indexOf("]);", at);
    return swrSource.slice(start, end + 3);
  })();

  it("keeps refreshInterval in the polling effect's dependency array", () => {
    // This is the whole reason identity matters. If swr ever drops it from the
    // deps, the inline arrow stops being a defect and this guard should be
    // revisited rather than silently kept.
    const deps = pollingEffect.slice(pollingEffect.lastIndexOf("}, ["));
    expect(deps).toContain("refreshInterval");
  });

  it("clears the pending timeout when that effect is torn down", () => {
    // Re-arming alone would be harmless; it is re-arming *after* discarding the
    // in-flight timer that loses the poll.
    expect(pollingEffect).toContain("clearTimeout(timer)");
  });

  it("prices a function-valued interval by CALLING it, so a stable reference still tracks fresh data", () => {
    // Why a permanently-stable callback does not freeze the cadence: swr invokes
    // it with the key's current cache data every time it re-arms.
    expect(pollingEffect).toContain("refreshInterval(getCache().data)");
  });
});

// ───────────────────────────────────────────────────────────────────────────
// 2. THE RULE, BOTH DIRECTIONS.
// ───────────────────────────────────────────────────────────────────────────

/**
 * swr's polling effect, reduced to the part under test and driven by a fake
 * clock.
 *
 * This mirrors the source quoted above — re-arm when the `refreshInterval`
 * IDENTITY changes, `clearTimeout` on teardown — and exists because the repo's
 * jest is `testEnvironment: 'node'` with no jsdom and no React renderer, so the
 * real hook cannot be mounted here. It is deliberately a model of swr's
 * lifecycle and NOT of our page: the thing being varied is only ever the
 * identity the page hands over, which is the real input, and the pass/fail
 * difference between the two arms below comes entirely from that.
 */
function simulatePolling(opts: {
  /** Called once per render; returns what the page passed as `refreshInterval`. */
  intervalForRender: () => (data?: { status?: string | null } | null) => number;
  renderEveryMs: number;
  forMs: number;
}): { fetches: number[] } {
  const { intervalForRender, renderEveryMs, forMs } = opts;
  const fetches: number[] = [];

  let now = 0;
  let armedAt: number | null = null;
  let armedFor = 0;
  let current: ((data?: { status?: string | null } | null) => number) | null = null;

  const arm = (fn: (data?: { status?: string | null } | null) => number) => {
    const interval = fn({ status: "live" });
    if (interval > 0) {
      armedAt = now;
      armedFor = interval;
    } else {
      armedAt = null;
    }
  };

  // Mount.
  current = intervalForRender();
  arm(current);

  while (now < forMs) {
    const nextRender = now + renderEveryMs;
    const nextFire = armedAt === null ? Infinity : armedAt + armedFor;

    if (nextFire <= nextRender) {
      // The timer won the race: swr fetches, then `next()` re-arms.
      now = nextFire;
      fetches.push(now);
      arm(current!);
      continue;
    }

    now = nextRender;
    const next = intervalForRender();
    if (next !== current) {
      // Identity changed ⇒ effect cleanup (clearTimeout) then re-run (next()).
      current = next;
      arm(current);
    }
  }

  return { fetches };
}

describe("the poll survives a page that re-renders (#7621)", () => {
  const ref = { current: false };
  const intervals = { live: LIVE, scheduled: SCHEDULED };

  it("STALLED ARM: an inline arrow never lets the 120s poll fire on a page rendering once a second", () => {
    // This is the shipped defect, reproduced. Each render mints a new arrow, so
    // the timer is discarded ~120 times before its deadline.
    const { fetches } = simulatePolling({
      intervalForRender: () =>
        (data) => eventRefreshInterval(data?.status, ref.current, intervals),
      renderEveryMs: 1_000,
      forMs: 10 * 60 * 1_000,
    });

    expect(fetches).toEqual([]);
  });

  it("HEALTHY ARM: a stable reference fires on its own cadence through the same renders", () => {
    const stable = makeEventRefreshInterval(ref, intervals);
    const tenMinutes = 10 * 60 * 1_000;

    const { fetches } = simulatePolling({
      intervalForRender: () => stable,
      renderEveryMs: 1_000,
      forMs: tenMinutes,
    });

    // Live + disconnected ⇒ 32s. Ten minutes buys about nineteen polls; assert
    // the CADENCE rather than a magic count, so tuning a constant does not
    // rewrite the guard.
    expect(fetches.length).toBeGreaterThan(1);
    expect(fetches[0]).toBe(LIVE);
    for (let i = 1; i < fetches.length; i += 1) {
      expect(fetches[i] - fetches[i - 1]).toBe(LIVE);
    }
    expect(fetches[fetches.length - 1]).toBeLessThanOrEqual(tenMinutes);
  });

  it("HEALTHY ARM, other direction: a stable reference does NOT add a fetch per render", () => {
    // The mirror of the arm above, and the one that would catch a "fix" that
    // simply refetched on every render — which would turn a frozen page into a
    // page hammering the API once a second.
    const stable = makeEventRefreshInterval(ref, intervals);
    const window = 60 * 1_000;

    const { fetches } = simulatePolling({
      intervalForRender: () => stable,
      renderEveryMs: 100,
      forMs: window,
    });

    const rendersInWindow = window / 100;
    expect(fetches.length).toBeLessThan(rendersInWindow);
    expect(fetches.length).toBe(Math.floor(window / LIVE));
  });
});

// ───────────────────────────────────────────────────────────────────────────
// 3. STABILITY IS NOT STALENESS.
// ───────────────────────────────────────────────────────────────────────────

describe("a permanently-stable callback still answers freshly", () => {
  it("returns the same reference no matter how often it is read", () => {
    const ref = { current: false };
    const stable = makeEventRefreshInterval(ref, { live: LIVE, scheduled: SCHEDULED });
    expect(stable).toBe(stable);
  });

  it("tracks the stream ref flipping underneath one held reference", () => {
    // The assumption that makes an empty dependency list safe, measured rather
    // than asserted in a comment: if this callback had captured `connected` by
    // value, the page would poll at the wrong cadence forever after the stream
    // came up.
    const ref = { current: false };
    const stable = makeEventRefreshInterval(ref, { live: LIVE, scheduled: SCHEDULED });

    expect(stable({ status: "live" })).toBe(LIVE);
    ref.current = true;
    expect(stable({ status: "live" })).toBe(SCHEDULED);
    ref.current = false;
    expect(stable({ status: "live" })).toBe(LIVE);
  });

  it("tracks the status argument swr passes it", () => {
    const ref = { current: false };
    const stable = makeEventRefreshInterval(ref, { live: LIVE, scheduled: SCHEDULED });

    expect(stable({ status: "live" })).toBe(LIVE);
    expect(stable({ status: "completed" })).toBe(SCHEDULED);
    // swr calls with the cache entry, which is undefined before the first fetch.
    expect(stable(undefined)).toBe(SCHEDULED);
    expect(stable(null)).toBe(SCHEDULED);
  });

  it("never answers 0 — a zero would disarm swr's timer entirely", () => {
    // `if (interval && timer !== -1)`: a falsy interval means swr schedules
    // nothing at all, which is the freeze this issue is about arriving by a
    // different door.
    const ref = { current: false };
    const stable = makeEventRefreshInterval(ref, { live: LIVE, scheduled: SCHEDULED });
    for (const status of ["live", "completed", "scheduled", "suspended", "", null, undefined]) {
      expect(stable({ status })).toBeGreaterThan(0);
    }
  });
});

// ───────────────────────────────────────────────────────────────────────────
// 4. THE APPLICATION: the pages pass a stable reference.
// ───────────────────────────────────────────────────────────────────────────

describe("no page prices a polled key with an inline function", () => {
  const pages = [
    "app/events/[id]/page.tsx",
    "app/event/[domain]/[slug]/page.tsx",
  ];

  it.each(pages)("%s passes a named reference, not an arrow", (rel) => {
    const src = readFileSync(path.join(__dirname, "../..", rel), "utf8");

    // Every `refreshInterval:` option site in the file must be followed by an
    // identifier, not by `(` (an arrow) or `function`. Written as a scan over
    // ALL sites rather than a check of one known line so a second polled key
    // added to either page is covered the day it lands.
    const sites = [...src.matchAll(/refreshInterval:\s*([^,\n]*)/g)].map((m) =>
      m[1].trim(),
    );
    expect(sites.length).toBeGreaterThan(0);

    for (const value of sites) {
      expect(value).not.toMatch(/^\(/);
      expect(value).not.toMatch(/^function\b/);
      expect(value).not.toMatch(/=>/);
    }
  });

  it("the event page builds its callback once, with an empty dependency list", () => {
    // The empty list is the load-bearing part: `useMemo` with the wrong deps
    // would re-mint the callback and restore the bug while still looking fixed.
    const src = readFileSync(
      path.join(__dirname, "../../app/events/[id]/page.tsx"),
      "utf8",
    );
    const at = src.indexOf("makeEventRefreshInterval(streamConnectedRef");
    expect(at).toBeGreaterThan(-1);
    // The memo's dependency array closes the call a few lines below.
    expect(src.slice(at, at + 400)).toMatch(/\}\),\s*\[\],/);
  });
});
