// #4861 — A PAGE THAT IS NO LONGER BEING FED MUST STOP SAYING IT IS LIVE.
//
// ── WHAT THE READER SAW ──────────────────────────────────────────────────────
//
// SF@LAR, the season opener, production, 2026-09-10. A tab opened at 6:36pm PT
// and never touched again, shot on a schedule without reloading. Eleven minutes
// AFTER the final whistle it still read:
//
//     LIVE   Next update: 11        48% – 52%      Live · Bain Luck blend
//     Rams 7                                       49ers 27
//
// on a game that had ended 7–27. The server was never at fault: it served
// `status: completed` with a settled hero from 03:25:31Z, and a fresh load of
// the same url in the same minute rendered Final correctly.
//
// ── WHY IT LOOKED ALIVE, WHICH IS THE PART THAT MATTERS ──────────────────────
//
// The page's other fetches were still landing. The hero's SCORE comes from
// `historyData` (`lastChartPoint`), not from the event payload — so the score
// advanced 7–10 → 7–17 → 7–24 → 7–27 beside a probability frozen at the
// halftime value, and the chart drew the collapse the hero refused to show. A
// reader cannot tell those two apart. The header then removed all doubt in the
// wrong direction: the countdown ring is a `setInterval` that ticks whether or
// not anything arrives, so it went on promising "Next update: 11" for three
// hours while nothing came.
//
// #5016 fixed the other half of this sentence — a failed refresh must not take
// the page away. A page we keep must also stop asserting it is live.
//
// ── WHY A RENDER TEST AND NOT A SEAM ─────────────────────────────────────────
//
// `eventFeedIsStalled` is pure and has its own cases below, but a test that
// only called it would have passed throughout this bug: the defect is that the
// HEADER prints a promise, and only a render can see the header. This is the
// #5016 lesson applied to its sibling — `loadFailure2783` covered which heading
// a failure earns and never once rendered the page.
//
// The page is mocked down to the seam under test: every SWR key but the event
// resolves to `undefined`, so the rails below the hero draw their own empty
// states. The assertion is about the header, not about what the rails render.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { eventFeedIsStalled, STALLED_POLL_INTERVALS } from "@/lib/eventLivePush";

/**
 * A live NFL event, past its own kickoff, which is what makes the header draw
 * the countdown ring at all (`shouldShowRefreshCountdown`).
 *
 * The source stamp is fixed and far in the past on purpose (gotcha #44): the
 * age it produces only ever grows, so the badge is permanently past its stale
 * boundary and its label is stable under any clock the suite runs on.
 */
const EVENT = {
  id: 14632820,
  sport_key: "americanfootball_nfl",
  sport_title: "NFL",
  home_team: "Los Angeles Rams",
  away_team: "San Francisco 49ers",
  home_score: 7,
  away_score: 27,
  status: "live",
  commence_time: "2026-09-11T00:35:00+00:00",
  win_probability_sources: {
    kalshi: {
      value: 0.48,
      display_name: "Kalshi",
      type: "market",
      color: "#22c55e",
      updated_at: "2026-09-11T02:16:00+00:00",
    },
  },
};

/** The promise the header must not make while nothing is arriving. */
const PROMISE = "Next update:";

let eventPayload: unknown;
let eventFailure: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    const isEvent = Array.isArray(key) && key[0] === "event";
    return {
      data: isEvent ? eventPayload : undefined,
      error: isEvent ? eventFailure : undefined,
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

describe("#4861 a page that stopped being fed stops claiming to be live", () => {
  it("drops the LIVE pill and the update promise when the event fetch is failing", () => {
    eventPayload = EVENT;
    eventFailure = new Error("Rate limit exceeded: 60/minute");

    const html = draw();

    // The bug: this promise ticked for three hours while nothing arrived.
    expect(html).not.toContain(PROMISE);
    // #5016 still holds — the page itself is kept, not thrown away.
    expect(html).toContain("Rams");
    expect(html).toContain("49ers");
  });

  it("says how old the number is instead, and does not call it live", () => {
    eventPayload = EVENT;
    eventFailure = new Error("Rate limit exceeded: 60/minute");

    const html = draw();

    // `LiveAgeStamp` past its stale boundary: an age, greyed, with the word
    // "live" dropped. The stamp above is old enough that this cannot flip.
    expect(html).toContain("ago");
    expect(html).not.toContain("live ·");
  });

  it("CONTROL: keeps the countdown on a live page whose fetches are landing", () => {
    eventPayload = EVENT;
    eventFailure = undefined;

    // `lastRefresh` initialises to now, so nothing is overdue on first render.
    expect(draw()).toContain(PROMISE);
  });
});

describe("#4861 eventFeedIsStalled", () => {
  const INTERVAL = 32000;

  it("is loud immediately on an error — a 429 needs no waiting out", () => {
    expect(
      eventFeedIsStalled({
        hasError: true,
        msSinceLastLanding: 0,
        refreshInterval: INTERVAL,
      }),
    ).toBe(true);
  });

  it("tolerates one missed interval, which is an ordinary slow response", () => {
    expect(
      eventFeedIsStalled({
        hasError: false,
        msSinceLastLanding: INTERVAL * 1.5,
        refreshInterval: INTERVAL,
      }),
    ).toBe(false);
  });

  it("calls silence past two intervals a stall, error or not", () => {
    // The iPad case: a suspended timer makes no request, so it raises no error.
    expect(
      eventFeedIsStalled({
        hasError: false,
        msSinceLastLanding: INTERVAL * STALLED_POLL_INTERVALS + 1,
        refreshInterval: INTERVAL,
      }),
    ).toBe(true);
  });

  it("clears the moment something lands", () => {
    expect(
      eventFeedIsStalled({
        hasError: false,
        msSinceLastLanding: 0,
        refreshInterval: INTERVAL,
      }),
    ).toBe(false);
  });

  it("invents no verdict when the caller is not polling on a clock", () => {
    expect(
      eventFeedIsStalled({
        hasError: false,
        msSinceLastLanding: 10 * 60 * 1000,
        refreshInterval: 0,
      }),
    ).toBe(false);
  });
});
