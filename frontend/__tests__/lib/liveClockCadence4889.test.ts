/**
 * #4889 — ONE LIVE PAGE, ONE CLOCK.
 *
 * The header's game clock is read from `/api/events/{id}`; the play strip under
 * the chart is drawn from `/history`, which a live page polls every 32s. While
 * the price stream delivered, the detail read was stood down to 120s, so the two
 * clocks drifted apart on the same screen.
 *
 * Specimen (shopper, production web, 390px): Navy at Air Force, /events/15319770.
 * The page read detail once, at 17:04:47Z, and not again before the reader left
 * at 17:06:43Z. At 17:06:42Z the header read `8:14 - 2nd Quarter` over a strip
 * reading `6:56 - 2nd Quarter`; the server had served 6:56 on the detail endpoint
 * since at least 17:06:28Z.
 *
 * The walk is replayed here against swr@2.4.1's polling loop as it really runs
 * (`node_modules/swr/dist/index/index.js`, `next()` / `execute()`): the first
 * timer is priced ONCE, at mount, from the cache entry — which is still empty
 * because the first read has not landed — and every later timer is priced from
 * the data the previous poll left in the cache. A page held open never re-arms
 * any other way (#7621: the callback identity is stable).
 */

import { readFileSync } from "fs";
import path from "path";

import { eventRefreshInterval, makeEventRefreshInterval } from "@/lib/eventLivePush";

const LIVE = 32_000;
const SCHEDULED = 120_000;
const INTERVALS = { live: LIVE, scheduled: SCHEDULED };

/** The shopper's walk: page open 17:04:47Z, reader gone 17:06:43Z. */
const WALK_MS = 116_000;

/**
 * swr's polling loop for one held page. `served(t)` is what the server answers
 * at time t. The mount fetch lands at `firstReadAt`; the polling effect has
 * already priced its first timer by then, from an empty cache.
 */
function pollTimes(opts: {
  interval: (data?: { status?: string | null } | null) => number;
  served: (t: number) => { status: string };
  firstReadAt: number;
  forMs: number;
}): number[] {
  const reads: number[] = [];
  let cache: { status: string } | undefined;
  let now = 0;
  let nextFire = opts.interval(cache); // next(): priced before any data
  let mountPending = true;

  while (true) {
    if (mountPending && opts.firstReadAt <= nextFire) {
      now = opts.firstReadAt;
      if (now > opts.forMs) break;
      cache = opts.served(now);
      mountPending = false;
      continue;
    }
    now = nextFire;
    if (now > opts.forMs) break;
    reads.push(now);
    cache = opts.served(now);
    nextFire = now + opts.interval(cache); // revalidate().then(next)
  }
  return reads;
}

describe("#4889 — a live page re-reads its clock at the strip's cadence", () => {
  it("the specimen walk: the detail payload is re-read within 32s of open, then every 32s", () => {
    const reads = pollTimes({
      interval: makeEventRefreshInterval(INTERVALS),
      served: () => ({ status: "live" }),
      firstReadAt: 400,
      forMs: WALK_MS,
    });

    // At 120s the walk saw zero re-reads; 32s buys three inside 116s.
    expect(reads).toEqual([LIVE, 2 * LIVE, 3 * LIVE]);
  });

  it("the header's read is never slower than the strip's read while live", () => {
    // `/history` on the page: `isLive ? LIVE_REFRESH_INTERVAL : SCHEDULED_REFRESH_INTERVAL`.
    // Nothing about the stream enters either answer any more.
    expect(eventRefreshInterval("live", INTERVALS)).toBeLessThanOrEqual(LIVE);
  });

  it("the page hands the factory the same live constant the history poll uses", () => {
    const src = readFileSync(path.join(__dirname, "../../app/events/[id]/page.tsx"), "utf8");
    const at = src.indexOf("makeEventRefreshInterval({");
    expect(at).toBeGreaterThan(-1);
    expect(src.slice(at, at + 200)).toMatch(/live:\s*LIVE_REFRESH_INTERVAL/);
    expect(src).toMatch(/refreshInterval:\s*isLive \? LIVE_REFRESH_INTERVAL : SCHEDULED_REFRESH_INTERVAL/);
  });
});

describe("#4889 controls — the slow cadence survives where nothing is moving", () => {
  it("a scheduled page pays one extra read 32s after open, then returns to 120s", () => {
    const reads = pollTimes({
      interval: makeEventRefreshInterval(INTERVALS),
      served: () => ({ status: "scheduled" }),
      firstReadAt: 400,
      forMs: 10 * 60 * 1_000,
    });

    expect(reads[0]).toBe(LIVE);
    for (let i = 1; i < reads.length; i += 1) {
      expect(reads[i] - reads[i - 1]).toBe(SCHEDULED);
    }
  });

  it("a finished game stays at 120s", () => {
    expect(eventRefreshInterval("completed", INTERVALS)).toBe(SCHEDULED);
  });

  it("a page that goes live mid-walk picks the live cadence up at its next read", () => {
    const kickoff = 150_000;
    const reads = pollTimes({
      interval: makeEventRefreshInterval(INTERVALS),
      served: (t) => ({ status: t >= kickoff ? "live" : "scheduled" }),
      firstReadAt: 400,
      forMs: 5 * 60 * 1_000,
    });

    // 32 (unknown) → 152 (scheduled, now live) → every 32s after.
    expect(reads.slice(0, 4)).toEqual([LIVE, LIVE + SCHEDULED, LIVE + SCHEDULED + LIVE, LIVE + SCHEDULED + 2 * LIVE]);
  });
});
