/**
 * live/058, CERT-854 + CERT-858 repairs — A CONNECTED STREAM MUST NOT FREEZE
 * THE SCORE, AND MUST NOT REFUSE TO GO AND GET ONE.
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
 * ## CERT-858: the first repair asked the right question one poll too late
 *
 * It gated on `hasLinescore`, a fact about the response in hand. A reader who
 * arrives before `poll_live_tennis_scores` has written its first line gets no
 * linescore, a connected stream, an interval of `0`, and therefore no request
 * that could ever fetch one. The page never acquires the score at all — a
 * strictly worse outcome than the freeze, and invisible to every assertion in
 * the first version of this file, all of which handed the rule a payload that
 * already had a line. The `first acquisition` block below is that gap.
 *
 * ## Both arms, on purpose
 *
 * Every assertion has its opposite here. A rule that simply always polled would
 * pass every tennis arm and undo live/034's whole ship for every other sport;
 * a rule that never polled would pass the NFL arm and ship the frozen card.
 *
 *   TZ=UTC npx jest --testPathPatterns=liveDetailRefresh
 */

import {
  FINER_GRAIN_SPORT_PREFIXES,
  LIVE_LINESCORE_REFRESH_INTERVAL,
  LIVE_REFRESH_INTERVAL,
  SCHEDULED_REFRESH_INTERVAL,
  liveDetailRefreshInterval,
  sportKeepsALinescore,
  streamIsBlindToTheScore,
} from "@/lib/liveDetailRefresh";

/** Popyrin 6-2 6-7(4) 6-5 Tabilo, third set in play. Only `state` is read. */
const IN_PROGRESS = { state: "in_progress" };
/** The same match an hour later. The score cannot move again. */
const DECIDED = { state: "decided" };

describe("a connected stream, on a payload that already carries a line", () => {
  it("keeps a bounded refresh while that line is still moving", () => {
    expect(
      liveDetailRefreshInterval({
        streamConnected: true,
        status: "live",
        sport: "tennis_atp_us_open",
        linescore: IN_PROGRESS,
      }),
    ).toBe(LIVE_LINESCORE_REFRESH_INTERVAL);
    expect(LIVE_LINESCORE_REFRESH_INTERVAL).toBeGreaterThan(0);
  });

  it("stops once the line says the match is decided", () => {
    /** `decided` lands on the 20 s score grid and `completed` lands on the 60 s
        status grid, so a decided line under a still-`live` status is an
        ordinary minute-long window. Reading the LINE's state and not the row's
        is what keeps that minute from being a minute of requests for a score
        that cannot change. */
    expect(
      liveDetailRefreshInterval({
        streamConnected: true,
        status: "live",
        sport: "tennis_atp_us_open",
        linescore: DECIDED,
      }),
    ).toBe(0);
  });
});

describe("a connected stream, before the first line exists (CERT-858)", () => {
  it("polls a live tennis page that has no linescore YET", () => {
    /** THE REGRESSION. This is the exact input the shipped rule scored `0`:
        connected, live, tennis, no line — a page that could never acquire the
        score it exists to show. */
    expect(
      liveDetailRefreshInterval({
        streamConnected: true,
        status: "live",
        sport: "tennis_atp_us_open",
        linescore: null,
      }),
    ).toBe(LIVE_LINESCORE_REFRESH_INTERVAL);
  });

  it("treats an ABSENT key the same as an explicit null", () => {
    /** The backend omits `linescore` rather than sending `null` on rows that
        have none, so `undefined` is the shape a real first payload arrives in
        and it must not take a different path from the one tested above. */
    expect(
      liveDetailRefreshInterval({
        streamConnected: true,
        status: "live",
        sport: "tennis_atp_us_open",
      }),
    ).toBe(LIVE_LINESCORE_REFRESH_INTERVAL);
  });

  it("STILL silences the poll for a live sport with no finer grain", () => {
    /** THE CONTROL, and it is the whole reason the rule takes a sport instead
        of always polling. live/034 S2's ship is that a streaming page stops
        polling; an NFL or MLB live page has no field the frame cannot carry,
        and must keep that behaviour exactly. */
    for (const sport of ["americanfootball_nfl", "baseball_mlb", null, undefined]) {
      expect(
        liveDetailRefreshInterval({
          streamConnected: true,
          status: "live",
          sport,
          linescore: null,
        }),
      ).toBe(0);
    }
  });

  it("does not poll a tennis page that is not live yet", () => {
    /** A scheduled tennis page has no line because there is no match, not
        because the poller is late. Polling it every 15 s would be the
        `always poll` mutant wearing a sport check. */
    for (const status of ["scheduled", "completed", "closed", undefined]) {
      expect(
        liveDetailRefreshInterval({
          streamConnected: true,
          status,
          sport: "tennis_atp_us_open",
          linescore: null,
        }),
      ).toBe(0);
    }
  });
});

describe("which sports keep a line", () => {
  it("matches on the PREFIX, so a new tournament inherits it", () => {
    /** The tennis key space grows by tournament. A literal list of sport keys
        would go green here and silently miss the next Slam — the same reason
        `_EVENT_DETAIL_LIVE_TTL_BY_SPORT_PREFIX` is keyed by prefix. */
    expect(sportKeepsALinescore("tennis_atp_us_open")).toBe(true);
    expect(sportKeepsALinescore("tennis_wta_wimbledon")).toBe(true);
    expect(sportKeepsALinescore("tennis")).toBe(true);
  });

  it("is a short list, and everything off it is unaffected", () => {
    expect([...FINER_GRAIN_SPORT_PREFIXES]).toEqual(["tennis"]);
    for (const sport of ["americanfootball_nfl", "baseball_mlb", "golf_pga", "", null]) {
      expect(sportKeepsALinescore(sport)).toBe(false);
    }
  });

  it("does not match a sport that merely starts with the same letters", () => {
    /** `startsWith` would claim this one. The split is on the key separator. */
    expect(sportKeepsALinescore("tennistable_wtt")).toBe(false);
  });
});

describe("the blindness predicate, read on its own", () => {
  it("says yes to a moving line whatever the row's status says", () => {
    /** A line in progress under a `completed` status is the other side of the
        same two-grid race: status flipped first. The line is the finer, fresher
        statement and it says the score is still moving. */
    expect(
      streamIsBlindToTheScore({
        status: "completed",
        sport: "tennis_atp_us_open",
        linescore: IN_PROGRESS,
      }),
    ).toBe(true);
  });

  it("says no to a decided line and no to a sport without one", () => {
    expect(
      streamIsBlindToTheScore({
        status: "live",
        sport: "tennis_atp_us_open",
        linescore: DECIDED,
      }),
    ).toBe(false);
    expect(
      streamIsBlindToTheScore({
        status: "live",
        sport: "americanfootball_nfl",
        linescore: null,
      }),
    ).toBe(false);
  });
});

describe("a stream that is down, refused, or never opened", () => {
  it("polls a live event at the backend's own cadence", () => {
    /** A push path that dies must degrade to polling, never to a frozen
        number — including for the sports that have no linescore. */
    for (const sport of ["tennis_atp_us_open", "americanfootball_nfl"]) {
      for (const linescore of [IN_PROGRESS, null]) {
        expect(
          liveDetailRefreshInterval({
            streamConnected: false,
            status: "live",
            sport,
            linescore,
          }),
        ).toBe(LIVE_REFRESH_INTERVAL);
      }
    }
  });

  it("falls back to the slow cadence for anything not live", () => {
    for (const status of ["scheduled", "completed", "closed", undefined]) {
      expect(
        liveDetailRefreshInterval({
          streamConnected: false,
          status,
          sport: "tennis_atp_us_open",
          linescore: null,
        }),
      ).toBe(SCHEDULED_REFRESH_INTERVAL);
    }
  });
});

describe("the bounded cadence is bounded by what the server can produce", () => {
  it("stays inside the 30 s bar and no faster than the write grid", () => {
    /** The budget: 10 s (20 s server write grid) + 5 s (10 s detail cache) +
        this/2. Polling faster than the server writes buys nothing but
        requests, and the total has to stay inside the 30 s bar. */
    expect(LIVE_LINESCORE_REFRESH_INTERVAL).toBeGreaterThanOrEqual(10000);
    expect(10 + 5 + LIVE_LINESCORE_REFRESH_INTERVAL / 2000).toBeLessThan(30);
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
   *
   * This is the SECOND of two layers, not the only one: the page is genuinely
   * rendered and its real SWR config genuinely driven in
   * `__tests__/capture/liveTennisAcquiresItsLineCert858.test.tsx`, because a
   * source scan cannot tell whether the values passed here are the right ones.
   */
  const source = require("fs").readFileSync(
    require("path").join(__dirname, "../../app/events/[id]/page.tsx"),
    "utf8",
  );

  it("imports and calls the shared rule", () => {
    expect(source).toContain('from "@/lib/liveDetailRefresh"');
    expect(source).toContain("liveDetailRefreshInterval({");
  });

  it("hands it the SPORT, not just the payload's line", () => {
    /** CERT-858: `hasLinescore: Boolean(data?.linescore)` was the whole call
        site, and no rule can recover the first-acquisition case from it. */
    expect(source).toContain("sport: data?.sport");
    expect(source).toContain("linescore: data?.linescore");
    expect(source).not.toContain("hasLinescore");
  });

  it("does not decide the interval inline any more", () => {
    /** The exact shape that shipped the freeze: a connected stream mapped
        straight to `0` with nothing asked about the payload. */
    expect(source).not.toMatch(/streamConnectedRef\.current\s*\n?\s*\?\s*0/);
  });
});
