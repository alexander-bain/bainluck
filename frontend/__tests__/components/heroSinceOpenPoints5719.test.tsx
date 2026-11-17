// #5719 / #5995 / #6064 (Direction 199 unified headline) — BOUNDARY CLAMPING ON
// `Now` AND ZERO `"Opened"` / `"since open"` / `pts` DELTA SENTENCES.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const HOME_SHORT = "Michigan";

let eventPayload: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    const k = Array.isArray(key) ? key[0] : null;
    const data =
      k === "event"
        ? eventPayload
        : k === "history"
          ? { aggregate_line: [] }
          : undefined;
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
  usePathname: () => "/events/1175875",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "1175875" }),
}));

jest.mock("@/lib/tenthsOptIn", () => ({
  ...jest.requireActual("@/lib/tenthsOptIn"),
  __esModule: true,
  useTenthsOptIn: () => false,
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const EventDetailPage = require("@/app/events/[id]/page").default;
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { AnalyticsProvider } = require("@/components/Analytics");

function liveEvent(homeProb: number, prematchHomeProb: number) {
  return {
    id: 1175875,
    sport_key: "americanfootball_ncaaf",
    sport: "americanfootball_ncaaf",
    sport_title: "NCAAF",
    home_team: "Michigan Wolverines",
    away_team: "Oklahoma Sooners",
    home_score: 17,
    away_score: 10,
    status: "live",
    commence_time: new Date(Date.now() - 90 * 60 * 1000).toISOString(),
    win_probability_sources: {},
    hero_probability_source: "blend",
    hero_probability: homeProb,
    hero_probability_away: 1 - homeProb,
    prematch_odds: {
      home_probability: prematchHomeProb,
      away_probability: 1 - prematchHomeProb,
      source: "kalshi",
    },
    opening_odds: {
      home_probability: prematchHomeProb,
      away_probability: 1 - prematchHomeProb,
    },
  };
}

function nowDigits(html: string): string[] {
  return [...html.matchAll(/data-hero-digits=""[^>]*>([^<]+)<\/span>/g)].map((m) =>
    m[1].replace(/&gt;/g, ">").replace(/&lt;/g, "<"),
  );
}

function draw(homeProb: number, prematchHomeProb: number): string {
  eventPayload = liveEvent(homeProb, prematchHomeProb);
  const html = renderToStaticMarkup(
    React.createElement(
      AnalyticsProvider,
      null,
      React.createElement(EventDetailPage, { params: { id: "1175875" } }),
    ),
  );
  expect(html).toContain(HOME_SHORT);
  return html;
}

describe("#5719/#5995/#6064 Direction 199 headline clamps boundaries and omits since-open/Opened lines", () => {
  it("prints no 'since open', 'Opened', or 'pts' delta on the headline, and carries pregame in the single grey line", () => {
    const html = draw(0.755, 0.344);
    expect(nowDigits(html)).toEqual(["24%", "76%"]);
    expect(html).toContain("Oklahoma 66%");
    expect(html).not.toMatch(/since open|opened|\bpts?\b/i);
  });

  it("clamps >99% and <1% at the high boundary", () => {
    const html = draw(0.996, 0.344);
    expect(nowDigits(html)).toEqual(["<1%", ">99%"]);
  });

  it("clamps <1% and >99% at the low boundary", () => {
    const html = draw(0.004, 0.344);
    expect(nowDigits(html)).toEqual([">99%", "<1%"]);
  });
});
