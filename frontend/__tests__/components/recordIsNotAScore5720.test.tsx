/**
 * #5720 — a started game never presents a season record as its only
 * score-shaped number.
 *
 * ═══ WHAT A READER SAW, PRODUCTION, 390px, 2026-09-12 ═══
 *
 * `/events/15304455` — East Carolina at Appalachian State, LIVE, 3h26m past its
 * own kickoff, no score in the payload:
 *
 *     [ECP]        1% – 99%        [App State]
 *    Pirates   ↓ -67% Pirates     Mountaineers
 *               since open             0-0
 *              Opened 68% – 32%
 *            Projected final: 18 – 27
 *
 * **`0-0` is Appalachian State's season record.** It sits under the team name
 * where the score sits on every other live page, in the same small grey type,
 * and it says nil-nil over a game the card itself calls 99%–1%. East Carolina
 * carried no record, so the two slots read as a score line with one side
 * missing.
 *
 * `W-L` and a football score are the same shape. Nothing on the card
 * distinguishes them once the `text-4xl font-black` score is gone.
 *
 * ═══ REACH ═══
 *
 * 109 of 149 live events carried no score when #5697 was re-measured (73%).
 * Every one of those whose team has a record drew this.
 *
 * ═══ THE THREE STATES, AND WHY ALL THREE ARE HERE ═══
 *
 * A guard that only asserts the defect is gone passes on a ship that deleted the
 * record outright, which would cost every pre-game reader their framing and
 * every live reader the record they have always had beside a real score. So the
 * arms are a partition, not a spot check:
 *
 *   started + no score pair   the record must NOT render      (the ship)
 *   started + score pair      the record MUST render          (the regression)
 *   not started               the record MUST render          (the regression)
 *
 * The middle and last arms are the ones that fail on an over-broad fix, and they
 * are the reason this file is five arms rather than one.
 *
 * ═══ THE PAIR, NOT THE SIDE ═══
 *
 * The fourth arm is the half-reported score: one side has a number, the other
 * does not. A per-side gate leaves the scoreless team's RECORD sitting directly
 * across from the other team's SCORE, which is the filed defect one column over
 * and reads worse, not better. The predicate is the pair.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const HOME_RECORD = "7-2";
const AWAY_RECORD = "0-0";

let eventPayload: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    const k = Array.isArray(key) ? key[0] : null;
    return {
      data: k === "event" ? eventPayload : undefined,
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

jest.mock("@/hooks/useLiveEventStream", () => ({
  __esModule: true,
  useLiveEventStream: () => ({ frame: null, connected: false }),
}));

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: () => {}, replace: () => {}, prefetch: () => {} }),
  usePathname: () => "/events/15304455",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "15304455" }),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const EventDetailPage = require("@/app/events/[id]/page").default;
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { AnalyticsProvider } = require("@/components/Analytics");

type Scores = { home: number | null; away: number | null };

/**
 * The filed page's shape.
 *
 * `record` is on `*_team_data` rather than `standings_context` because the gate
 * reads the same `||` for both and the team-data arm is what production served
 * here. `win_probability_sources` is empty so `liveClaimIsUnbacked` reads no
 * stamp and a `live` row stays live rather than resolving from the chart.
 *
 * Kickoff is an OFFSET from `Date.now()` computed at call time, never a
 * wall-clock literal (gotcha #44) — `hasStarted` is a comparison against the
 * clock, and the `scheduled` arm below needs it in the FUTURE, which is the same
 * offset with the other sign.
 */
function event(scores: Scores, status: string, minutesFromNow: number) {
  return {
    id: 15304455,
    sport_key: "americanfootball_ncaaf",
    sport: "americanfootball_ncaaf",
    sport_title: "NCAAF",
    home_team: "Appalachian State Mountaineers",
    away_team: "East Carolina Pirates",
    home_score: scores.home,
    away_score: scores.away,
    status,
    commence_time: new Date(Date.now() + minutesFromNow * 60 * 1000).toISOString(),
    win_probability_sources: {},
    hero_probability_source: "blend",
    hero_probability: 0.99,
    hero_probability_away: 0.01,
    home_team_data: { record: AWAY_RECORD },
    away_team_data: { record: HOME_RECORD },
  };
}

function draw(scores: Scores, status = "live", minutesFromNow = -206): string {
  eventPayload = event(scores, status, minutesFromNow);
  const html = renderToStaticMarkup(
    React.createElement(
      AnalyticsProvider,
      null,
      React.createElement(EventDetailPage, { params: { id: "15304455" } }),
    ),
  );
  // A `not.toContain` against a page that did not draw is a pass that proves
  // nothing. The hero renders on every branch this file exercises.
  expect(html).toContain("Mountaineers");
  return html;
}

/** The record's own element, so a `0-0` elsewhere on the page cannot answer for it. */
function recordSpan(value: string): string {
  return `<span class="text-[11px] text-text-muted">${value}</span>`;
}

describe("#5720 a record is not a score", () => {
  it("prints no record on a started game with no score — the filed page", () => {
    const html = draw({ home: null, away: null });

    expect(html).not.toContain(recordSpan(AWAY_RECORD));
    expect(html).not.toContain(recordSpan(HOME_RECORD));
  });

  it("still prints both records once the game has a score pair", () => {
    // The regression arm. A ship that simply deleted the record passes the arm
    // above and fails this one.
    const html = draw({ home: 27, away: 18 });

    expect(html).toContain(recordSpan(AWAY_RECORD));
    expect(html).toContain(recordSpan(HOME_RECORD));
    // And the scores are the reason the records are unambiguous here.
    expect(html).toContain(">27</span>");
    expect(html).toContain(">18</span>");
  });

  it("still prints both records before kickoff, where there is no score slot", () => {
    // The second regression arm: pre-game framing is what the record is FOR.
    const html = draw({ home: null, away: null }, "scheduled", 90);

    expect(html).toContain(recordSpan(AWAY_RECORD));
    expect(html).toContain(recordSpan(HOME_RECORD));
  });

  it("prints no record when only ONE side has a score", () => {
    // A per-side gate leaves the scoreless team's RECORD across from the other
    // team's SCORE — the filed defect one column over. The predicate is the pair.
    const html = draw({ home: 27, away: null });

    expect(html).not.toContain(recordSpan(AWAY_RECORD));
    expect(html).not.toContain(recordSpan(HOME_RECORD));
  });

  it("suppresses the record on a finished game with no score, not just a live one", () => {
    // `completed` reaches the gate through `isFinished` rather than `isLive`, and
    // a settled page with no reported score is exactly the state #4015 exists
    // for. The record would be the only score-shaped number there too.
    const html = draw({ home: null, away: null }, "completed", -300);

    expect(html).not.toContain(recordSpan(AWAY_RECORD));
    expect(html).not.toContain(recordSpan(HOME_RECORD));
  });
});
