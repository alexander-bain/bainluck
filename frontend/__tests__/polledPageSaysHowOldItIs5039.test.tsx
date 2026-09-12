// #5039 / #5049 — A POLLED LIVE PAGE SAYS HOW OLD ITS NUMBER IS.
//
// ── THE SPECIMEN (SF@LAR, notice-42 mystery shop, Thu 2026-09-10) ────────────
//
// One browser context, opened 6:36pm PT and never reloaded, so this is one page
// changing its own header as the game state changed:
//
//     6:36   5:10 - 2nd Quarter     live · 7s ago
//     6:56   1:19 - 2nd Quarter     live · 4s ago
//     7:16   Halftime · 0:00        LIVE   Next update:  (27)
//
// At halftime the header stopped telling the reader how old the number was and
// started telling them when we would next poll for it.
//
// It is the wrong swap in both directions. A countdown is our plumbing and a
// reader cannot act on it (notice 34 / D102). And it is given up at the worst
// moment: during play the clock and score visibly move, so `live · 4s ago` is
// mostly redundant; at halftime NOTHING on the page moves for twelve minutes,
// which is exactly when "is this thing still working, or did it freeze?" is a
// real question and the age is the only thing that can answer it.
//
// #5049 is the same defect at its ugliest — a page frozen at a halftime
// snapshot for forty minutes, showing `LIVE` and promising an update in 29
// seconds, forty minutes behind the real score. #4861 gave the age back to that
// page once its fetches were visibly FAILING; this gives it to the page whose
// fetches are landing perfectly and whose number is simply not moving.
//
// ── WHAT THIS SUITE PINS ─────────────────────────────────────────────────────
//
// 1. the defect itself: a live, polled, freshly-fed page prints its age;
// 2. the boundary that stops the fix becoming a new lie: a PREGAME page on the
//    same poll must NOT print `live · 8s ago`, because the badge's fresh
//    presentation says the word "live" and the match has not started;
// 3. the retired LIVE pill: `headerAgeSubsumesLivePill` must be false on every
//    reachable input, which is the whole argument for deleting it;
// 4. the badge is still rendered exactly once (#4469).
//
// WHY A RENDER AND NOT ONLY THE HELPER: ux/1181's lesson — the payload said the
// bug was gone and the pixels said it was not. `headerShowsAge` returning true
// proves nothing about a header that never calls it.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  headerShowsAge,
  headerAgeSubsumesLivePill,
  shouldShowRefreshCountdown,
} from "@/lib/eventKeyStats";

/** The reader-facing string the whole ship exists to put back on the page. */
const AGE = "live ·";
/** The ring's label — present on both paths, and never the substitute for AGE. */
const PROMISE = "Next update:";

const BASE = {
  id: 14632820,
  sport: "americanfootball_nfl",
  home_team: "Los Angeles Rams",
  away_team: "San Francisco 49ers",
  home_score: 7,
  away_score: 10,
  status: "live",
  // Well past kickoff: `isLive` needs `hasStarted`, and the halftime specimen
  // is an hour into the game.
  commence_time: new Date(Date.now() - 60 * 60 * 1000).toISOString(),
};

/**
 * A price written `stampAgeMs` ago. Fresh by default and deliberately so: a
 * stale stamp would make the badge appear via #4861's arm instead, and the
 * suite would pass while asserting nothing about the arm it was written for.
 */
function event(opts: { stampAgeMs: number; status?: string; commenceInMs?: number }) {
  return {
    ...BASE,
    ...(opts.status ? { status: opts.status } : {}),
    ...(opts.commenceInMs === undefined
      ? {}
      : { commence_time: new Date(Date.now() + opts.commenceInMs).toISOString() }),
    win_probability_sources: {
      kalshi: {
        value: 0.48,
        display_name: "Kalshi",
        type: "market",
        color: "#22c55e",
        updated_at: new Date(Date.now() - opts.stampAgeMs).toISOString(),
      },
    },
  };
}

let eventPayload: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    const isEvent = Array.isArray(key) && key[0] === "event";
    return {
      data: isEvent ? eventPayload : undefined,
      error: undefined,
      isLoading: false,
      mutate: () => undefined,
    };
  },
}));

jest.mock("@/hooks", () => ({
  ...jest.requireActual("@/hooks"),
  __esModule: true,
  usePageTracking: () => undefined,
  useScrollDepth: () => undefined,
  useEngagementTime: () => undefined,
  usePinnedEvents: () => ({
    isPinned: () => false,
    togglePin: () => undefined,
    isMaxReached: false,
  }),
}));

// NOT connected — every case here is the POLL branch, which is the branch that
// lost the age. A pushed page has had the badge since live/034 S2.
jest.mock("@/hooks/useLiveEventStream", () => ({
  __esModule: true,
  useLiveEventStream: () => ({ frame: null, connected: false }),
}));

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: () => {}, replace: () => {}, prefetch: () => {} }),
  usePathname: () => "/events/14632820",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "14632820" }),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const EventDetailPage = require("@/app/events/[id]/page").default;
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { AnalyticsProvider } = require("@/components/Analytics");

function draw(): string {
  return renderToStaticMarkup(
    React.createElement(
      AnalyticsProvider,
      null,
      React.createElement(EventDetailPage, { params: { id: "14632820" } }),
    ),
  );
}

describe("#5039 the polled live header says how old its number is", () => {
  it("prints the age on a LIVE page whose fetches are landing", () => {
    // The halftime frame. Nothing is failing, nothing is stale, the stream is
    // simply not connected — and before this ship the header answered a
    // question the reader did not ask.
    eventPayload = event({ stampAgeMs: 8 * 1000 });

    const html = draw();

    expect(html).toContain(AGE);
    expect(html).toContain("8s ago");
  });

  it("does not take the countdown away to do it", () => {
    // The ring is the only thing on a still page that shows we are still
    // trying, and #5039's own argument is that the age should be ADDED, not
    // swapped in. A fix that deleted the ring would pass the test above.
    eventPayload = event({ stampAgeMs: 8 * 1000 });

    const html = draw();

    expect(html).toContain(PROMISE);
    expect(html).toContain(AGE);
  });

  it("renders the badge exactly once (#4469)", () => {
    // Two badges are two answers to "how old is this number". The merge of the
    // badge group and the ring group into one right-hand group is where a
    // second one could have crept in.
    eventPayload = event({ stampAgeMs: 8 * 1000 });

    expect(draw().split(AGE).length - 1).toBe(1);
  });

  it("BOUNDARY: a PREGAME page on the same poll does not claim to be live", () => {
    // The reason the polled arm is gated on liveness and not on the ring's own
    // window. #3802 draws the ring up to three hours before kickoff, where the
    // price stamp is seconds old — so "show the age whenever the ring shows"
    // would print a green `live · 8s ago` over a match that has not started.
    // This is the assertion that fails on that shortcut.
    eventPayload = event({
      stampAgeMs: 8 * 1000,
      status: "scheduled",
      commenceInMs: 60 * 60 * 1000,
    });

    const html = draw();

    expect(html).toContain(PROMISE);
    expect(html).not.toContain(AGE);
  });
});

describe("#5039 headerShowsAge", () => {
  const LIVE_POLLED = {
    isFinished: false,
    streamConnected: false,
    onVisiblePoll: true,
    feedStalled: false,
    effectivelyLive: true,
    isSuspended: false,
  };

  it("is the defect's own case: live, polled, fed", () => {
    expect(headerShowsAge(LIVE_POLLED)).toBe(true);
  });

  it("POSITIVE CONTROL — the same inputs WITHOUT the new arm are the old answer", () => {
    // Before this ship the polled page earned the badge only by being stalled.
    // If this stops being false the case above is not testing the new arm.
    expect(
      headerShowsAge({ ...LIVE_POLLED, effectivelyLive: false, isSuspended: false }),
    ).toBe(false);
  });

  it("keeps every arm it already had", () => {
    // Pushed (live/034 S2), and stalled-while-polled (#4861) — including the
    // pregame stalled page, where the age is by construction past its stale
    // boundary and so prints a grey `4m ago` claiming nothing.
    expect(headerShowsAge({ ...LIVE_POLLED, streamConnected: true })).toBe(true);
    expect(
      headerShowsAge({
        ...LIVE_POLLED,
        effectivelyLive: false,
        feedStalled: true,
      }),
    ).toBe(true);
  });

  it("covers the suspended page, which is where the disclosure matters most", () => {
    // `isSuspended` is `hasNoReportedResult(...) || liveClaimUnbacked`: a match
    // past its start that nobody has reported, and the pinned page #5459
    // withdrew the ring from. The withdrawal took the promise; it must not have
    // taken the admission with it — before this arm, an unbacked page whose
    // polls were landing showed NEITHER.
    expect(
      headerShowsAge({ ...LIVE_POLLED, effectivelyLive: false, isSuspended: true }),
    ).toBe(true);
  });

  it("says nothing on a finished page, whatever else is true", () => {
    // Settled means settled: a finished page has a result, not a number still
    // supposed to move. `isFinished` is checked first for that reason.
    expect(
      headerShowsAge({
        ...LIVE_POLLED,
        isFinished: true,
        streamConnected: true,
        feedStalled: true,
        isSuspended: true,
      }),
    ).toBe(false);
  });

  it("says nothing on a page that is not even polling", () => {
    expect(headerShowsAge({ ...LIVE_POLLED, onVisiblePoll: false })).toBe(false);
  });
});

describe("#5039 the retired LIVE pill", () => {
  /** Every combination of the six inputs the header derives. */
  function* inputs() {
    const bits = [false, true];
    for (const isFinished of bits)
      for (const streamConnected of bits)
        for (const feedStalled of bits)
          for (const effectivelyLive of bits)
            for (const isSuspended of bits)
              for (const commenceOffsetMs of [-3600_000, 3600_000, 86_400_000]) {
                // `onVisiblePoll` and the ring are DERIVED from the same helper
                // the page uses, not invented here — a sweep over invented
                // combinations would include states the page cannot reach and
                // would prove the rule on inputs nobody has.
                const onVisiblePoll = shouldShowRefreshCountdown({
                  isFinished,
                  streamConnected,
                  isLive: effectivelyLive,
                  isSuspended,
                  commenceTime: new Date(Date.now() + commenceOffsetMs).toISOString(),
                });
                yield {
                  isFinished,
                  streamConnected,
                  feedStalled,
                  effectivelyLive,
                  isSuspended,
                  onVisiblePoll,
                  ringVisible: onVisiblePoll && !feedStalled,
                };
              }
  }

  it("is subsumed by the badge on every reachable input", () => {
    // THE ARGUMENT FOR DELETING IT, AS AN ASSERTION. The pill drew only inside
    // the ring group and only when `effectivelyLive`; if the badge is on screen
    // for all of those, removing the pill removes a duplicate claim and nothing
    // else. And the pill was the worse of the two: keyed on the event's STATUS,
    // it stayed green and pulsing over a number of any age (#5049).
    const escapes = [...inputs()].filter((i) => headerAgeSubsumesLivePill(i));
    expect(escapes).toEqual([]);
  });

  it("POSITIVE CONTROL — the predicate can fire, so the sweep above is not vacuous", () => {
    // A hand-built input that is NOT reachable from the page (the ring visible
    // on a live page that is somehow not on a visible poll). If this returned
    // false too, the emptiness above would be a property of the predicate
    // rather than of the header.
    expect(
      headerAgeSubsumesLivePill({
        isFinished: false,
        streamConnected: false,
        onVisiblePoll: false,
        feedStalled: false,
        effectivelyLive: true,
        isSuspended: false,
        ringVisible: true,
      }),
    ).toBe(true);
  });

  it("leaves exactly one green live-styled pill on a live polled page", () => {
    // The sweep above proves the pill is REDUNDANT; this proves it is GONE.
    // Both are needed — a predicate cannot see markup, and re-adding the pill
    // would restore the duplicate claim with every helper test still green.
    //
    // `bg-emerald-500/15` is the shared class string of the two pills: the
    // badge's and the one that was deleted. Measured at 1 on the page as it
    // renders now; the phase badge's own "LIVE" is styled differently and is
    // not counted here.
    eventPayload = event({ stampAgeMs: 8 * 1000 });

    expect(draw().split("bg-emerald-500/15").length - 1).toBe(1);
  });

  it("POSITIVE CONTROL — the sweep really does visit live, ringed pages", () => {
    // Without this the sweep could be empty, or hold only finished events, and
    // still report no escapes.
    const live = [...inputs()].filter((i) => i.ringVisible && i.effectivelyLive);
    expect(live.length).toBeGreaterThan(0);
  });
});
