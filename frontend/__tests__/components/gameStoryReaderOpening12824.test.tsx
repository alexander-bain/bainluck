/** @jest-environment jsdom */

import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { SWRConfig, unstable_serialize } from "swr";
import EventPage from "@/app/events/[id]/page";
import { useGameMarketsStream } from "@/hooks/useGameMarketsStream";
import type { EventDetailResponse } from "@/lib/types";

jest.mock("next/navigation", () => ({
  usePathname: () => "/events/14780556",
  useRouter: () => ({ replace: jest.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: jest.fn(), showConsentBanner: false }),
}));
jest.mock("@/hooks", () => ({
  ...jest.requireActual("@/hooks"),
  useAnalytics: () => ({ track: jest.fn(), trackNavigationClick: jest.fn(), recordEvent: jest.fn() }),
  usePageTracking: jest.fn(),
  useScrollDepth: jest.fn(),
  useEngagementTime: jest.fn(),
  usePinnedEvents: () => ({ isPinned: () => false, togglePin: jest.fn(), isMaxReached: false }),
}));
jest.mock("@/hooks/useGameMarketsStream");

const now = new Date("2026-09-28T23:00:00Z");
const eventId = 14780556;
// The retained Packers–Bears pair from the #9470 production specimen.
const opening: EventDetailResponse = {
  id: eventId,
  external_id: String(eventId),
  sport: "americanfootball_nfl",
  sport_name: "NFL",
  home_team: "Green Bay Packers",
  away_team: "Chicago Bears",
  home_score: null,
  away_score: null,
  status: "scheduled",
  commence_time: "2026-10-11T17:00:00Z",
  hero_probability: 0.5996,
  hero_probability_away: 0.4004,
  hero_probability_source: "opening",
  current_odds: {
    captured_at: "2026-09-13T15:10:39.053494+00:00",
    home_probability: 0.5996,
    away_probability: 0.4004,
    bookmaker_count: 2,
    spread: null,
    over_under: null,
    projected_home_score: null,
    projected_away_score: null,
  },
};

let host: HTMLDivElement;
let root: ReturnType<typeof createRoot>;

beforeEach(() => {
  (globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;
  jest.useFakeTimers({ now });
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  // The player prop quotes have their own clock and can outlive the game moneyline.
  jest.mocked(useGameMarketsStream).mockReturnValue({ data: {
    event_id: eventId,
    home_team: opening.home_team,
    away_team: opening.away_team,
    home_score: null,
    away_score: null,
    status: "scheduled",
    pace: null,
    totals: [], team_totals: [], spreads: [], period_markets: [], other: [], matchups: [],
    player_props: [200.5, 225.5, 250.5].map((threshold, index) => ({
      market_name: "Passing Yards",
      outcome_name: `Jordan Love: ${threshold}+`,
      threshold,
      over_probability: [0.75, 0.5, 0.25][index],
      source: "kalshi",
      movement: null,
      observed_at: now.toISOString(),
    })),
  } });
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
  jest.useRealTimers();
});

async function openStory(event: EventDetailResponse) {
  await act(async () => root.render(
    <SWRConfig value={{
      provider: () => new Map(),
      fallback: { [unstable_serialize(["event", eventId])]: event },
      revalidateOnMount: false,
    }}>
      <EventPage params={{ id: String(eventId) }} />
    </SWRConfig>,
  ));
  const open = host.querySelector<HTMLButtonElement>('button[aria-label^="Open Jordan Love"]');
  expect(open).not.toBeNull();
  await act(async () => open!.click());
  const header = host.querySelector('[data-testid="reader-match"]');
  expect(header?.textContent).toMatch(/Bears vs Packers · Pregame/);
  return header!.parentElement!;
}

it("keeps the scheduled Game Story and withholds the first stored win chance", async () => {
  const header = await openStory(opening);
  expect(header.textContent).not.toContain("Win chances");
});

it("shows the same pair when a dated blend supplies the win chances", async () => {
  const header = await openStory({
    ...opening,
    hero_probability_source: "blend",
    hero_probability_observed_at: now.toISOString(),
  });
  expect(header.textContent).toContain("Win chances · Bears 40% · Packers 60%");
});
