// #5257 — A HERO STOPS FORECASTING A MATCH ITS OWN BADGE SAYS NOBODY REPORTED.
//
// ── WHAT THE READER SAW ──────────────────────────────────────────────────────
//
// `/events/15309533` (Lotte Giants vs KT Wiz, KBO, `status='suspended'`), 390px,
// production, 2026-09-11 15:45Z. The hero, top of the page, in this order:
//
//     No result reported            Sep 11, 2026 · 2:30 AM PDT
//                 1% – 99%
//            Projected final: 2 – 7
//
// The badge says nobody reported how this went. Four lines below, the same card
// projects its final score.
//
// ── THE MECHANISM ────────────────────────────────────────────────────────────
//
// The gate was a DENYLIST of two terminal states:
//
//     event.status !== "completed" && event.status !== "closed"
//
// `suspended` is not in it, so it renders — and neither is a `scheduled` event
// long past its own kickoff, which reaches the same branch by the same hole.
// This is #5206's defect one card up, written differently: there a three-value
// `status` had no arm for the fourth state, here a two-value denylist has no
// entry for it. #4018's line applies as verbatim as it did there: *a forecast
// and a result are two questions and they get two predicates.*
//
// ── WHY `isSuspended` AND NOT A THIRD PREDICATE ──────────────────────────────
//
// The page already computes its ONE `hasNoReportedResult` answer as
// `isSuspended` (#4015), and the "No result reported" badge four lines above the
// projection is drawn from it. Reusing it is what makes the card stop asking the
// question one way and answering it the other; a fresh status test here would be
// a second place this rule lives, free to drift from the badge.
//
// ── WHAT MUST NOT MOVE, AND IS ASSERTED BELOW ────────────────────────────────
//
// Deleting the projection outright would satisfy the ship assertion and break
// every control here, so each one is load-bearing: a live game still projects, a
// scheduled game inside its grace window still projects, and the suspended page
// still DRAWS (the failure mode of a suppression fix is a card that reads as
// failed-to-load).

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const PROJECTION = "Projected final";
const BADGE = "No result reported";

/** Baseball declares `hasDerivedSpread: true`, which is the sport gate the
 *  projection sits behind — a tennis fixture could never reach this branch and
 *  so could never prove anything about it. */
function event(overrides: Record<string, unknown> = {}) {
  return {
    id: 15309533,
    sport_key: "baseball_kbo",
    sport: "baseball_kbo",
    sport_title: "KBO",
    home_team: "Lotte Giants",
    away_team: "KT Wiz",
    home_score: null,
    away_score: null,
    status: "suspended",
    // well past its own start, which is what makes the state reachable at all
    commence_time: "2026-09-11T02:30:00+00:00",
    win_probability_sources: {},
    ...overrides,
  };
}

const HISTORY = {
  aggregate_line: [],
  pm_spread_data: {
    projected_final: { home_score: 1.5, away_score: 7.0 },
  },
};

let eventPayload: unknown;
let historyPayload: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    const k = Array.isArray(key) ? key[0] : null;
    const data =
      k === "event" ? eventPayload : k === "history" ? historyPayload : undefined;
    return { data, error: undefined, isLoading: false, mutate: () => undefined };
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
  usePathname: () => "/events/15309533",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "15309533" }),
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
      React.createElement(EventDetailPage, { params: { id: "15309533" } }),
    ),
  );
}

beforeEach(() => {
  historyPayload = HISTORY;
});

describe("#5257 the hero does not forecast a match nobody reported", () => {
  it("prints no projected final on a suspended event", () => {
    eventPayload = event();

    const html = draw();

    // The ship.
    expect(html).not.toContain(PROJECTION);
    // The card is still the one that made the claim — this asserts the fix
    // landed on the page under test and not on some other branch.
    expect(html).toContain(BADGE);
  });

  it("prints no projected final on a scheduled event long past its own kickoff", () => {
    // The other half of the denylist hole: never `suspended`, never terminal,
    // and just as unreportable.
    eventPayload = event({ status: "scheduled" });

    expect(draw()).not.toContain(PROJECTION);
  });

  // ── controls: the projection must survive everywhere it was right ──────────

  it("still projects a live game", () => {
    eventPayload = event({
      status: "live",
      commence_time: new Date(Date.now() - 30 * 60 * 1000).toISOString(),
      home_score: 1,
      away_score: 3,
    });

    expect(draw()).toContain(PROJECTION);
  });

  it("still projects a game that has not started yet", () => {
    eventPayload = event({
      status: "scheduled",
      commence_time: new Date(Date.now() + 3 * 60 * 60 * 1000).toISOString(),
    });

    expect(draw()).toContain(PROJECTION);
  });

  it("draws the suspended page rather than failing to render it", () => {
    // A suppression fix's failure mode is a blank card, which would pass the
    // ship assertion above for the wrong reason.
    eventPayload = event();

    const html = draw();

    // The hero prints the short team name, not the full one.
    expect(html).toContain("Giants");
    expect(html).toContain("Wiz");
    expect(html).toContain("Win Probability");
    expect(html.length).toBeGreaterThan(2000);
  });
});
