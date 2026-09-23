// #4885 — A LIVE HERO STOPS PROJECTING A FINAL BELOW THE SCORE ALREADY ON THE BOARD.
//
// ── WHAT THE READER SAW ──────────────────────────────────────────────────────
//
// `/events/15316846`, Blue Jays @ Orioles, LIVE, Bottom 8th, 390px, production
// 2026-09-23 20:06Z (ux/1466):
//
//     Orioles 4        93% – 7%        Jays 2
//                Projected final: 3 – 2
//
// The Orioles projected to finish with fewer runs than they already had. The
// served pair was `3.3 / 1.9` (sportsbook, odds last captured four minutes
// before first pitch), and it passed every gate the line already had.
//
// ── THE RULE ─────────────────────────────────────────────────────────────────
//
// native/150's invariant on #4885: scores are never taken back, so a projected
// final below the current score is always false. It is decided per side, after
// the same `Math.round` the line prints, against the pair the hero PRINTS.
//
// ── WHAT MUST NOT MOVE, AND IS ASSERTED BELOW ────────────────────────────────
//
//   * THE ROW IS NOT THE SCORE. On the specimen the event row still held 0 – 0
//     (#8278) while the hero read 4 – 2 off the chart's live arm. A gate on the
//     row passes the photographed defect, so the ship arm reproduces that split.
//   * A REACHABLE PAIR STILL PROJECTS, including one that EQUALS the score (a
//     game with no more scoring is a real final) and one whose raw float is
//     below the score but whose printed integer is not (3.6 under 4 prints 4).
//   * PRE-GAME STILL PROJECTS. With no score pair there is nothing to contradict.
//   * THE PAGE STILL DRAWS. A suppression that blanked the card would pass the
//     ship assertion for the wrong reason.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const PROJECTION = "Projected final";
// The hero joins the pair with thin spaces around an en dash; written as
// escapes so an assertion cannot pass against glyphs the markup never holds.
const SEP = "\u2009\u2013\u2009";

function event(overrides: Record<string, unknown> = {}) {
  return {
    id: 15316846,
    sport_key: "baseball_mlb",
    sport: "baseball_mlb",
    sport_title: "MLB",
    home_team: "Baltimore Orioles",
    away_team: "Toronto Blue Jays",
    home_score: 4,
    away_score: 2,
    status: "live",
    commence_time: new Date(Date.now() - 150 * 60 * 1000).toISOString(),
    win_probability_sources: {},
    ...overrides,
  };
}

function history(
  home: number,
  away: number,
  extra: Record<string, unknown> = {},
) {
  return {
    aggregate_line: [],
    pm_spread_data: { projected_final: { home_score: home, away_score: away } },
    ...extra,
  };
}

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
  usePathname: () => "/events/15316846",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "15316846" }),
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
      React.createElement(EventDetailPage, { params: { id: "15316846" } }),
    ),
  );
}

beforeEach(() => {
  eventPayload = event();
  historyPayload = history(3.3, 1.9);
});

describe("#4885 a projected final below the score on the board is not printed", () => {
  it("prints no projected final when the hero's live score is past it, though the row says 0 – 0", () => {
    // The specimen exactly: row frozen at 0 – 0, the chart's live arm at 4 – 2.
    eventPayload = event({ home_score: 0, away_score: 0 });
    historyPayload = history(3.3, 1.9, {
      espn_history: [
        {
          timestamp: new Date(Date.now() - 60 * 1000).toISOString(),
          home_score: 4,
          away_score: 2,
        },
      ],
    });

    const html = draw();

    // PRECONDITION. The hero prints the chart's 4, not the row's 0; without it
    // this arm would be testing the row and could not see the split.
    expect(html).toMatch(/>4</);
    // The ship.
    expect(html).not.toContain(PROJECTION);
    expect(html).not.toContain(`3${SEP}2`);
    // NON-VACUITY: the specimen's hero is still drawn.
    expect(html).toContain("Orioles");
    expect(html).toContain("Jays");
    expect(html.length).toBeGreaterThan(2000);
  });

  it("prints no projected final when the row's own score is past it", () => {
    historyPayload = history(3.3, 1.9);

    expect(draw()).not.toContain(PROJECTION);
  });

  it("withholds it when only the TRAILING side is past its projection", () => {
    // Per side, not per total: 6.4 – 1.6 sums above 4 + 2, yet the Jays
    // already have 2 and are projected to finish with 2 → prints `6 – 2`, fine;
    // at 1.4 they would print 1, below their 2.
    historyPayload = history(6.4, 1.4);

    expect(draw()).not.toContain(PROJECTION);
  });

  // ── controls: everywhere the projection was reachable, it survives ─────────

  it("still projects a pair above the score", () => {
    historyPayload = history(5.2, 2.8);

    const html = draw();
    expect(html).toContain(PROJECTION);
    expect(html).toContain(`5${SEP}3`);
  });

  it("still projects a pair EQUAL to the score (no more scoring is a real final)", () => {
    historyPayload = history(4.1, 2.2);

    expect(draw()).toContain(`${PROJECTION}: 4${SEP}2`);
  });

  it("reads the PRINTED integer: 3.6 under a score of 4 prints 4 and stays", () => {
    // A gate on the raw float would withhold a line the reader reads as right.
    historyPayload = history(3.6, 2.4);

    expect(draw()).toContain(`${PROJECTION}: 4${SEP}2`);
  });

  it("still projects before first pitch, where there is no score to contradict", () => {
    eventPayload = event({
      status: "scheduled",
      home_score: null,
      away_score: null,
      commence_time: new Date(Date.now() + 3 * 60 * 60 * 1000).toISOString(),
    });
    historyPayload = history(3.3, 1.9);

    expect(draw()).toContain(`${PROJECTION}: 3${SEP}2`);
  });
});
