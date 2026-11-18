import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { generateMetadata } from "@/app/events/[id]/layout";
import ShareImage from "@/app/events/[id]/opengraph-image";
import { resolveProbability } from "@/lib/eventKeyStats";
import { hasNoPriceForShare } from "@/lib/eventShareMeta";
import type { Event, EventDetailResponse, FeedEventData, FeedItem } from "@/lib/types";

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
jest.mock("next/og", () => ({
  ImageResponse: class {
    constructor(readonly tree: React.ReactNode) {}
  },
}));

import EventCard from "@/components/EventCard";
import FeedCard from "@/components/FeedCard";
import { EventCard as DiscoverEventCard } from "@/components/discover/EventCard";

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

function cachedReading(source: "opening" | "blend"): EventDetailResponse {
  return {
    ...billsPatriots(0.58),
    hero_probability_source: source,
    hero_probability: 0.58,
    hero_probability_away: 0.42,
    current_odds: {
      home_probability: 0.58,
      away_probability: 0.42,
      home_rendered_percent: 58,
      away_rendered_percent: 42,
    },
  } as EventDetailResponse;
}

async function renderShareImage() {
  const image = await ShareImage({ params: { id: "15184640" } });
  return renderToStaticMarkup((image as unknown as { tree: React.ReactNode }).tree);
}

it.each(["opening", "blend"] as const)("share surfaces read the %s provenance with the same numeric pair", async (source) => {
  const event = cachedReading(source);
  global.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => event });
  const meta = await generateMetadata({ params: Promise.resolve({ id: "15184640" }) });
  const image = await renderShareImage();
  const surfaces = [meta.title, meta.description, meta.openGraph?.title, meta.openGraph?.description,
    meta.twitter?.title, meta.twitter?.description, image];
  for (const text of surfaces) {
    if (source === "opening") {
      expect(String(text)).not.toMatch(/42%|58%/);
    } else {
      expect(String(text)).toContain("42%");
      expect(String(text)).toContain("58%");
    }
  }
});

it("the live share image can label a separate pregame reading when the cached forecast is opening-only", async () => {
  const event = {
    ...cachedReading("opening"),
    status: "live",
    commence_time: new Date(Date.now() - 25 * 60_000).toISOString(),
    opening_odds: { home_probability: 0.55, away_probability: 0.45, favorite: "home" },
  };
  global.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => event });
  const image = await renderShareImage();
  expect(image).not.toMatch(/42%|58%/);
  expect(image).toContain("55%");
  expect(image).toContain("45%");
  expect(image).toContain("Pregame");
});

it.each(["true", "false"])("web game cards respect the opening tag with the unified card flag set to %s", (flag) => {
  const priorFlag = process.env.NEXT_PUBLIC_GAME_CARD_183A;
  process.env.NEXT_PUBLIC_GAME_CARD_183A = flag;
  try {
    for (const source of ["opening", "blend"] as const) {
      const event = cachedReading(source);
      const data = event as unknown as FeedEventData;
      const item = { type: "event", headline: "", reason: "", context_summary: null, score: 60, data } as FeedItem;
      const cards = [
        <EventCard key="event" event={event} />,
        <FeedCard key="feed" item={item} />,
        <DiscoverEventCard key="discover" item={item} data={data} liked={false} setLiked={() => {}} trending={false} />,
      ];
      for (const card of cards) {
        const html = renderToStaticMarkup(card);
        if (source === "opening") {
          expect(html).not.toMatch(/42%|58%/);
        } else {
          expect(html).toContain("42%");
          expect(html).toContain("58%");
        }
      }
    }
  } finally {
    if (priorFlag === undefined) delete process.env.NEXT_PUBLIC_GAME_CARD_183A;
    else process.env.NEXT_PUBLIC_GAME_CARD_183A = priorFlag;
  }
});
