// #8800 — A FAILED REFRESH OF A LIVE GAME'S HISTORY MUST NOT ERASE THE CHART.
//
// ── WHAT THE READER SAW ──────────────────────────────────────────────────────
//
// Cal vs Clemson, live, 390px, 2026-09-26 04:48–04:56 UTC: the Win Probability
// chart that was drawn a moment ago became "Unable to load history · Failed to
// fetch · Retry", came back ~30 s later, went again — four times in three
// minutes, and each swap changed the card's height so the page jumped
// (scroll 0 → 531 → 727 → 471 → 275 px) with no input.
//
// ── THE MECHANISM ────────────────────────────────────────────────────────────
//
// SWR keeps the last good body when a refetch fails — `data` AND `error` are
// both set. The chart card tested `historyError` first, so the held curve was
// never reached. The error box now needs BOTH an error and nothing to draw.
//
// Harness copied from `aGameThatBegunDoesNotPromiseTracking3612.test.tsx`.
// `OddsChart` is `dynamic(..., { ssr: false })`, so server markup shows its
// skeleton, not the curve — the witness is which ARM of the card rendered:
// the error sentence, or not. Every case also asserts the card and the hero are
// on the page (#4286: a blank document passes every `not.toContain`).

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const ERROR_BOX = "Unable to load history";
const RETRY = ">Retry<";
const CARD = 'data-testid="win-probability-card"';

const HOUR = 3600 * 1000;
const past = () => new Date(Date.now() - 2 * HOUR).toISOString();

const LIVE_EVENT = {
  id: 15315987,
  sport_key: "americanfootball_ncaaf",
  sport_title: "NCAAF",
  home_team: "Clemson Tigers",
  away_team: "California Golden Bears",
  home_score: 10,
  away_score: 10,
  status: "live",
  win_probability_sources: {},
};

const EMPTY = { history: [], win_prob_history: [], espn_history: [], bookmaker_history: {} };

const CURVE = {
  ...EMPTY,
  history: [
    { timestamp: "2026-09-26T04:00:00Z", home_win_probability: 0.6, away_win_probability: 0.4 },
    { timestamp: "2026-09-26T04:30:00Z", home_win_probability: 0.55, away_win_probability: 0.45 },
  ],
};

let historyPayload: unknown;
let historyFailure: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    const name = Array.isArray(key) ? key[0] : undefined;
    if (name === "event") {
      return { data: { ...LIVE_EVENT, commence_time: past() }, error: undefined, isLoading: false, mutate: () => undefined };
    }
    if (name === "history") {
      return { data: historyPayload, error: historyFailure, isLoading: false, mutate: () => undefined };
    }
    return { data: undefined, error: undefined, isLoading: false, mutate: () => undefined };
  },
}));

jest.mock("@/hooks", () => ({
  ...jest.requireActual("@/hooks"),
  __esModule: true,
  usePageTracking: () => undefined,
  useScrollDepth: () => undefined,
  useEngagementTime: () => undefined,
  usePinnedEvents: () => ({ isPinned: () => false, togglePin: () => undefined, isMaxReached: false }),
}));

jest.mock("@/hooks/useLiveEventStream", () => ({
  __esModule: true,
  useLiveEventStream: () => ({ frame: null, connected: false }),
}));

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: () => {}, replace: () => {}, prefetch: () => {} }),
  usePathname: () => "/events/15315987",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "15315987" }),
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
      React.createElement(EventDetailPage, { params: { id: "15315987" } }),
    ),
  );
}

function expectPageAndCard(html: string) {
  expect(html).toContain("Tigers");
  expect(html).toContain("Golden Bears");
  expect(html).toContain(CARD);
}

beforeEach(() => {
  historyPayload = undefined;
  historyFailure = undefined;
});

describe("#8800 — the chart card's error box is for a card with nothing to draw", () => {
  it("CONTROL: a healthy poll over a curve draws the chart arm, no error box", () => {
    historyPayload = CURVE;
    const html = draw();
    expectPageAndCard(html);
    expect(html).not.toContain(ERROR_BOX);
  });

  it("a refetch that FAILED over a held curve keeps the chart arm — the specimen", () => {
    historyPayload = CURVE;
    historyFailure = new TypeError("Failed to fetch");
    const html = draw();
    expectPageAndCard(html);
    expect(html).not.toContain(ERROR_BOX);
    expect(html).not.toContain("Failed to fetch");
  });

  it("a failed FIRST fetch (nothing held) still shows the error box with Retry", () => {
    historyFailure = new TypeError("Failed to fetch");
    const html = draw();
    expectPageAndCard(html);
    expect(html).toContain(ERROR_BOX);
    expect(html).toContain(RETRY);
  });

  it("a failed refetch over an EMPTY held body still shows the error box — nothing to draw", () => {
    // #3612 keeps the card in this state so its Retry is reachable; this pins
    // that the Retry is actually there, not an empty chart in its place.
    historyPayload = EMPTY;
    historyFailure = new TypeError("Failed to fetch");
    const html = draw();
    expectPageAndCard(html);
    expect(html).toContain(ERROR_BOX);
    expect(html).toContain(RETRY);
  });

  it("a held aggregate line alone counts as something to draw", () => {
    historyPayload = {
      ...EMPTY,
      aggregate_line: [{ timestamp: "2026-09-26T04:30:00Z", home_probability: 0.55 }],
    };
    historyFailure = new TypeError("Failed to fetch");
    const html = draw();
    expectPageAndCard(html);
    expect(html).not.toContain(ERROR_BOX);
  });
});
