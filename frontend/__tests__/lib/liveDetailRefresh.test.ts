/**
 * live/058, CERT-854 repair — A CONNECTED STREAM MUST NOT FREEZE THE SCORE.
 *
 * live/034 S2 stops polling `/api/events/{id}` entirely while the SSE stream is
 * delivering, and for the probability that is exactly right: the frame IS the
 * new value. But a frame carries `p` and its source and nothing else.
 *
 * That was harmless while the only other live field was a set count that moved
 * twice an hour. `linescore` moves on every game won. Without the rule below, a
 * reader who leaves a live tennis page open — the entire point of a live tennis
 * page — watches the probability tick beside a scoreline frozen at whatever the
 * first load returned. That is MORE wrong than before the score existed,
 * because now it looks precise.
 *
 * ## Both arms, on purpose
 *
 * Every assertion has its opposite here. A rule that simply always polled would
 * pass the linescore arm and undo live/034's whole ship for every other sport;
 * a rule that never polled would pass the NFL arm and ship the frozen card.
 */

import {
  LIVE_LINESCORE_REFRESH_INTERVAL,
  LIVE_REFRESH_INTERVAL,
  SCHEDULED_REFRESH_INTERVAL,
  liveDetailRefreshInterval,
} from "@/lib/liveDetailRefresh";

describe("a connected stream", () => {
  it("keeps a bounded refresh for a payload carrying a linescore", () => {
    expect(
      liveDetailRefreshInterval({
        streamConnected: true,
        status: "live",
        hasLinescore: true,
      }),
    ).toBe(LIVE_LINESCORE_REFRESH_INTERVAL);
    expect(LIVE_LINESCORE_REFRESH_INTERVAL).toBeGreaterThan(0);
  });

  it("still silences the poll for a payload it can keep current", () => {
    /** THE CONTROL. live/034 S2's ship is that a streaming page stops polling;
        an NFL or MLB live page has no field the frame cannot carry, and must
        keep that behaviour exactly. */
    expect(
      liveDetailRefreshInterval({
        streamConnected: true,
        status: "live",
        hasLinescore: false,
      }),
    ).toBe(0);
  });

  it("is bounded below by what the server can actually produce", () => {
    /** The budget: 10 s (20 s server write grid) + 5 s (10 s detail cache) +
        this/2. Polling faster than the server writes buys nothing but requests,
        and the total has to stay inside the 30 s bar. */
    expect(LIVE_LINESCORE_REFRESH_INTERVAL).toBeGreaterThanOrEqual(10000);
    expect(10 + 5 + LIVE_LINESCORE_REFRESH_INTERVAL / 2000).toBeLessThan(30);
  });
});

describe("a stream that is down, refused, or never opened", () => {
  it("polls a live event at the backend's own cadence", () => {
    /** A push path that dies must degrade to polling, never to a frozen
        number — including for the sports that have no linescore. */
    expect(
      liveDetailRefreshInterval({
        streamConnected: false,
        status: "live",
        hasLinescore: false,
      }),
    ).toBe(LIVE_REFRESH_INTERVAL);
    expect(
      liveDetailRefreshInterval({
        streamConnected: false,
        status: "live",
        hasLinescore: true,
      }),
    ).toBe(LIVE_REFRESH_INTERVAL);
  });

  it("falls back to the slow cadence for anything not live", () => {
    for (const status of ["scheduled", "completed", "closed", undefined]) {
      expect(
        liveDetailRefreshInterval({
          streamConnected: false,
          status,
          hasLinescore: false,
        }),
      ).toBe(SCHEDULED_REFRESH_INTERVAL);
    }
  });
});

describe("the event page actually uses this rule", () => {
  /**
   * A PURE TEST CAN ONLY PROVE THE RULE, NOT THAT ANYTHING OBEYS IT.
   *
   * The defect CERT-854 found was an inline ternary in the SWR config that no
   * test could reach. Extracting it fixed that once; this is what stops it
   * being re-inlined, which is the cheapest way for the same freeze to come
   * back looking like a tidy-up.
   */
  const source = require("fs").readFileSync(
    require("path").join(__dirname, "../../app/events/[id]/page.tsx"),
    "utf8",
  );

  it("imports and calls the shared rule", () => {
    expect(source).toContain('from "@/lib/liveDetailRefresh"');
    expect(source).toContain("liveDetailRefreshInterval({");
    expect(source).toContain("hasLinescore: Boolean(data?.linescore)");
  });

  it("does not decide the interval inline any more", () => {
    /** The exact shape that shipped the freeze: a connected stream mapped
        straight to `0` with nothing asked about the payload. */
    expect(source).not.toMatch(/streamConnectedRef\.current\s*\n?\s*\?\s*0/);
  });
});
