// #6614 (Direction 199 unified headline) — A NON-COMPLEMENT `prematch_odds` PAIR ON
// A DRAW-PRICED SPORT KEEPS BOTH LEGS IN `Pregame`, WHILE A `1 - home` COMPLEMENT
// PAIR WITHHOLDS THE AWAY LEG, AND `opening_odds` / `"Opened"` IS NEVER PRINTED.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const SETTLED_AWAY_WINNER = {
  id: 15298749,
  sport: "soccer_uefa_europa_league",
  sport_name: "UEFA Europa League",
  home_team: "Lillestrom",
  away_team: "Torreense",
  home_score: 1,
  away_score: 2,
  status: "completed",
  commence_time: "2026-09-17T19:00:00+00:00",
  completed_at: "2026-09-17T20:58:07.882953+00:00",
  hero_settled_result: "away",
  win_probability_sources: {},
  prematch_odds: {
    home_probability: 0.5476,
    away_probability: 0.2103,
    source: "books",
  },
  opening_odds: {
    home_probability: 0.5476,
    away_probability: 0.2103,
    favorite: "home",
  },
};

const LIVE_NON_COMPLEMENT = {
  id: 15298544,
  sport: "soccer_uefa_europa_league",
  sport_name: "UEFA Europa League",
  home_team: "Anderlecht",
  away_team: "Lyon",
  home_score: 0,
  away_score: 1,
  status: "live",
  commence_time: new Date(Date.now() - 30 * 60 * 1000).toISOString(),
  win_probability_sources: {},
  current_odds: {
    home_probability: 0.3246,
    away_probability: null,
    home_rendered_percent: 32,
    away_rendered_percent: null,
  },
  prematch_odds: {
    home_probability: 0.3246,
    away_probability: 0.4044,
    source: "books",
  },
  opening_odds: { home_probability: 0.3246, away_probability: 0.4044 },
};

const LIVE_TWO_WAY = {
  ...LIVE_NON_COMPLEMENT,
  id: 15310565,
  sport: "americanfootball_nfl",
  sport_name: "NFL",
  home_team: "Kansas City Chiefs",
  away_team: "Denver Broncos",
  prematch_odds: {
    home_probability: 0.62,
    away_probability: 0.38,
    home_rendered_percent: 62,
    away_rendered_percent: 38,
    source: "kalshi",
  },
  opening_odds: { home_probability: 0.62, away_probability: 0.38 },
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
  usePathname: () => "/events/15298749",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "15298749" }),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const EventDetailPage = require("@/app/events/[id]/page").default;
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { AnalyticsProvider } = require("@/components/Analytics");

function draw(payload: unknown): string {
  eventPayload = payload;
  return renderToStaticMarkup(
    React.createElement(
      AnalyticsProvider,
      null,
      React.createElement(EventDetailPage, { params: { id: "15298749" } }),
    ),
  );
}

beforeEach(() => {
  historyPayload = { aggregate_line: [] };
});

describe("#6614 a non-complement prematch pair keeps BOTH legs on Direction 199", () => {
  it("names the away favourite in the single grey pregame line on a live non-complement pair", () => {
    const html = draw(LIVE_NON_COMPLEMENT);
    expect(html).toContain("Lyon 40%");
    expect(html).not.toMatch(/opened/i);
  });

  it("prints the away winner's 21% pregame cell in the finished Pregame column", () => {
    const html = draw(SETTLED_AWAY_WINNER);
    expect(html).toContain(">21%</span>");
    expect(html).toContain(">55%</span>");
    expect(html).toContain("Torreense");
    expect(html).toContain("Lillestrom");
    expect(html).not.toMatch(/opened/i);
  });
});

describe("#6614 a complement prematch pair still withholds the away leg", () => {
  it("withholds the away pregame cell when away_probability is 1 - home", () => {
    const html = draw({
      ...SETTLED_AWAY_WINNER,
      prematch_odds: {
        home_probability: 0.5476,
        away_probability: 1 - 0.5476,
        source: "books",
      },
    });
    expect(html).not.toContain(">45%</span>");
    expect(html).toContain(">55%</span>");
    expect(html).toContain("Torreense");
    expect(html).toContain("Lillestrom");
  });

  it("withholds opening_odds completely when prematch_odds is absent", () => {
    const { prematch_odds: _omitted, ...openingOnly } = SETTLED_AWAY_WINNER;
    void _omitted;
    const html = draw(openingOnly);
    expect(html).not.toContain(">21%</span>");
    expect(html).not.toContain(">55%</span>");
    expect(html).not.toMatch(/opened|opening/i);
  });
});

describe("#6614 two-way control", () => {
  it("CONTROL: a two-way sport prints its favourite pregame chance cleanly", () => {
    const html = draw(LIVE_TWO_WAY);
    expect(html).toContain("Chiefs 62%");
    expect(html).not.toMatch(/opened/i);
  });
});
