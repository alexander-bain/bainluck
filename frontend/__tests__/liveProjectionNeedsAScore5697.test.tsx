// #5697 AC2 — A LIVE GAME WITH NO SCORE STOPS PROJECTING ITS FINAL SCORE.
//
// ── WHAT THE READER SAW ──────────────────────────────────────────────────────
//
// `/events/15310565` (Southeastern Louisiana Lions v North Alabama Lions,
// NCAAF FCS, `status='live'`, 90 minutes past its own kickoff), 390px,
// production, 2026-09-13 01:28Z. Top of the page, in this order:
//
//     LIVE                                       ⟳ 20s
//              69% – 31%
//         Opened 65% – 35%
//         Live · Bain Luck blend
//         Projected final: 29 – 22
//
// There is no score on the card. Every freshness signal is green and correct —
// `live · 26s ago`, a full chart, eight lead changes — which is the worst shape
// for a reader: nothing looks broken, so there is no way to tell a MISSING
// score from 0–0. And `29 – 22` is the only number on the card shaped like a
// scoreline, so it is the one a reader reaches for.
//
// Frame: `artifacts/ux-1225/BEFORE-5697AC2-PROD-390-15310565-hero.png`.
// live/181 shot three more of the same at 23:26Z (UCLA–SDSU,
// Nebraska–Bowling Green, Wisconsin–Western Illinois) plus a same-build control
// that renders correctly when the score is there.
//
// ── WHY THIS IS A RENDER RULE AND NOT A DATA FIX ─────────────────────────────
//
// live's PR #5772 shrinks this population and cannot empty it: 9 MMA/boxing
// rows carry no home/away score BY CONSTRUCTION, so a frame that projects a
// final over nothing survives any score-pipeline fix. The render rule is owed
// regardless of when the data half lands. Notice 41 hand-off: live owns the
// score pipeline, ux owns the layout.
//
// ── WHAT MUST NOT MOVE, AND IS ASSERTED BELOW ────────────────────────────────
//
// Deleting the projection outright would satisfy the ship assertion and break
// every control here, so each one is load-bearing:
//
//   * BEFORE KICKOFF THE PROJECTION IS THE HONEST THING. A forecast of a game
//     that has not started is exactly what it says it is, and there is no
//     absent score for a reader to read it against.
//   * A LIVE GAME WITH A SCORE still projects — that is the frame the feature
//     was built for.
//   * THE SCORE MAY COME FROM THE HISTORY PAYLOAD, not the event row. The page
//     resolves `bestHomeScore` through `computeLastChartPoint` first (#5521), so
//     a "fix" that read `event.home_score` alone would blank the projection on
//     every page whose score arrives by ESPN snapshot. That control is here
//     because the narrower fix passes every other arm in this file.
//   * THE PAGE STILL DRAWS. The failure mode of a suppression is a card that
//     reads as failed-to-load, which would pass the ship assertion for the
//     wrong reason.
//
// ── THE PAIR, NOT THE SIDE ───────────────────────────────────────────────────
//
// The projection renders as `29 – 22`, a pair. A half-reported score leaves the
// reader holding a projected pair against a single number, which is the same
// defect one column over — so the gate reads the pair, exactly as #5720's
// record gate does two lines above it in the source.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const PROJECTION = "Projected final";

/** NCAAF FCS resolves through the `americanfootball` entry in `SPORT_SCORING`,
 *  which declares `hasDerivedSpread: true` — the sport gate the projection sits
 *  behind. A tennis fixture could never reach this branch and so could never
 *  prove anything about it. */
function event(overrides: Record<string, unknown> = {}) {
  return {
    id: 15310565,
    sport_key: "americanfootball_ncaaf_fcs",
    sport: "americanfootball_ncaaf_fcs",
    sport_title: "NCAAF FCS",
    home_team: "Southeastern Louisiana Lions",
    away_team: "North Alabama Lions",
    home_score: null,
    away_score: null,
    status: "live",
    // 90 minutes in, which is what the production specimen was
    commence_time: new Date(Date.now() - 90 * 60 * 1000).toISOString(),
    win_probability_sources: {},
    ...overrides,
  };
}

/** The production numbers: 28.8 / 22.2, which the hero rounds to `29 – 22`. */
const HISTORY = {
  aggregate_line: [],
  pm_spread_data: {
    projected_final: { home_score: 28.8, away_score: 22.2 },
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
  usePathname: () => "/events/15310565",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "15310565" }),
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
      React.createElement(EventDetailPage, { params: { id: "15310565" } }),
    ),
  );
}

beforeEach(() => {
  historyPayload = HISTORY;
});

describe("#5697 AC2 a live game with no score does not project its final", () => {
  it("prints no projected final on a live event with neither score", () => {
    eventPayload = event();

    const html = draw();

    // The ship.
    expect(html).not.toContain(PROJECTION);
    // NON-VACUITY. A suppression whose real effect is a blank card would pass
    // the line above. This is the specimen's own hero, still drawn.
    expect(html).toContain("Southeastern Louisiana");
    expect(html).toContain("North Alabama");
    expect(html.length).toBeGreaterThan(2000);
  });

  it("prints no projected final when only one side's score arrived", () => {
    // THE PAIR, NOT THE SIDE. `29 – 22` against a lone `14` is the same
    // defect one column over.
    eventPayload = event({ home_score: 14 });

    const html = draw();

    expect(html).not.toContain(PROJECTION);
    // The half-score is still on the page — so this arm is reading a hero that
    // rendered, not a hero that bailed out.
    expect(html).toContain(">14<");
  });

  // ── controls: the projection must survive everywhere it was right ──────────

  it("still projects a live game that has both scores", () => {
    eventPayload = event({ home_score: 21, away_score: 17 });

    expect(draw()).toContain(PROJECTION);
  });

  it("still projects a game that has not kicked off", () => {
    // Before kickoff the forecast is the honest thing: there is no absent score
    // for a reader to read it against.
    eventPayload = event({
      status: "scheduled",
      commence_time: new Date(Date.now() + 3 * 60 * 60 * 1000).toISOString(),
    });

    expect(draw()).toContain(PROJECTION);
  });

  it("still projects when the score pair comes from the history payload, not the event row", () => {
    // #5521 — the page resolves its scores through `computeLastChartPoint`
    // FIRST and falls back to the event row. A gate written against
    // `event.home_score` alone passes every other arm in this file and blanks
    // the projection on every page whose score arrives by ESPN snapshot.
    eventPayload = event();
    historyPayload = {
      ...HISTORY,
      espn_history: [
        {
          timestamp: new Date(Date.now() - 60 * 1000).toISOString(),
          home_score: 24,
          away_score: 10,
        },
      ],
    };

    expect(draw()).toContain(PROJECTION);
  });
});
