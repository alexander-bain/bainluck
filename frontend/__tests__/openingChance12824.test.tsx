import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { generateMetadata } from "@/app/events/[id]/layout";
import { resolveProbability } from "@/lib/eventKeyStats";
import { hasNoPriceForShare } from "@/lib/eventShareMeta";
import type { Event, EventDetailResponse } from "@/lib/types";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ children }: { children: React.ReactNode }) => <a>{children}</a>,
}));
jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));
jest.mock("@/hooks", () => ({
  useAnalytics: () => ({ trackEventCardClick: () => {}, track: () => {} }),
}));

import EventCard from "@/components/EventCard";

function billsPatriots(home: number | null): EventDetailResponse {
  return {
    id: 15184640,
    sport: "americanfootball_nfl",
    sport_name: "NFL",
    home_team: "New England Patriots",
    away_team: "Buffalo Bills",
    status: "scheduled",
    commence_time: new Date(Date.now() + 19 * 86400_000).toISOString(),
    home_score: null,
    away_score: null,
    current_odds: {
      home_probability: home,
      away_probability: home === null ? null : 1 - home,
      bookmaker_count: 2,
      captured_at: new Date(Date.now() - 68 * 86400_000).toISOString(),
    },
  } as EventDetailResponse;
}

afterEach(() => jest.restoreAllMocks());

it("the real card loses the old 50/50 and retains a real source when it arrives", () => {
  const card = (home: number | null) => renderToStaticMarkup(
    <EventCard event={billsPatriots(home) as Event} />,
  );
  expect(card(0.5034)).toContain("50%");
  expect(card(null)).not.toMatch(/\d+%/);
  expect(card(0.14)).toContain("14%");
  expect(card(0.14)).toContain("86%");
});

it("the game page and share image have no chance to invent for an unpriced game", () => {
  const event = billsPatriots(null);
  const reading = resolveProbability(event, undefined, null, false, false);
  expect(reading.homeProb).toBeNull();
  expect(reading.awayProb).toBeNull();
  expect(hasNoPriceForShare(event)).toBe(true);
  expect(hasNoPriceForShare(billsPatriots(0))).toBe(false);
});

it("the real metadata route removes the old chance from title, description and sharing", async () => {
  global.fetch = jest.fn().mockResolvedValue({
    ok: true, json: async () => billsPatriots(null),
  });
  const meta = await generateMetadata({ params: Promise.resolve({ id: "15184640" }) });
  for (const text of [meta.title, meta.description, meta.openGraph?.title,
    meta.openGraph?.description, meta.twitter?.title, meta.twitter?.description]) {
    expect(String(text)).not.toMatch(/50%|win probability/);
  }
  expect(String(meta.title)).toContain("Buffalo Bills");
  expect(String(meta.title)).toContain("New England Patriots");
});
