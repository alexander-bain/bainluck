// #8277 — THE PRE-GAME SLOT BETWEEN THE CRESTS NEVER COUNTS PAST ZERO.
//
// Seen on production 2026-09-23 12:44 PM PDT: the Twins @ Giants card printed `0m`
// seconds before first pitch. The same arithmetic, `Math.round(diffH * 60)m` with no
// floor, printed `-3m` … `-120m` for every minute a game sat past its scheduled start
// without the server calling it live (poll lag, rain delay, late kickoff).
//
// A scheduled start is not proof the game began, so the answer is not "Started": past
// the scheduled time the slot prints that time of day, which stays true.
//
// Asserted on the rendered card, not only the helper — a helper that is right and a
// card that stopped calling it would pass a helper-only file. Both directions (gotcha
// #43): an ordinary upcoming card still counts down, and a live card still says Live.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { EventCard as DiscoverEventCard } from "@/components/discover/EventCard";
import { pregameSlotLabel } from "@/components/discover/utils";
import type { FeedEventData, FeedItem } from "@/lib/types";

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));

const NOW = Date.parse("2026-09-23T19:40:00Z");
const TIME_OF_DAY = /^\d{1,2}:\d{2}\s?[AP]M$/;
const MIN = 60_000;

describe("pregameSlotLabel (#8277)", () => {
  it("prints the scheduled time of day once the start has passed — never a negative count", () => {
    for (const pastMin of [0, 1, 3, 45, 120, 600]) {
      const label = pregameSlotLabel(new Date(NOW - pastMin * MIN).toISOString(), NOW);
      expect(label).toMatch(TIME_OF_DAY);
      expect(label).not.toMatch(/-|^0m$/);
    }
  });

  it("never prints 0m in the last seconds before the start", () => {
    for (const secs of [1, 10, 29, 30, 59]) {
      expect(pregameSlotLabel(new Date(NOW + secs * 1000).toISOString(), NOW)).toBe("1m");
    }
  });

  it("still counts down normally before the start", () => {
    expect(pregameSlotLabel(new Date(NOW + 5 * MIN).toISOString(), NOW)).toBe("5m");
    expect(pregameSlotLabel(new Date(NOW + 59 * MIN).toISOString(), NOW)).toBe("59m");
    expect(pregameSlotLabel(new Date(NOW + 3 * 60 * MIN).toISOString(), NOW)).toBe("3h");
    expect(pregameSlotLabel(new Date(NOW + 30 * 60 * MIN).toISOString(), NOW)).toBe("Tomorrow");
  });

  it("an unparseable start prints nothing rather than NaNm", () => {
    expect(pregameSlotLabel("not a date", NOW)).toBe("");
  });
});

function makeData(over: Partial<FeedEventData>): FeedEventData {
  return {
    id: 15317579,
    external_id: "evt-15317579",
    sport: "baseball_mlb",
    sport_name: "MLB",
    home_team: "San Francisco Giants",
    away_team: "Minnesota Twins",
    status: "scheduled",
    home_team_data: { primary_color: "#fd5a1e", logo_small: "h.png" },
    away_team_data: { primary_color: "#002b5c", logo_small: "a.png" },
    current_odds: {
      captured_at: new Date(Date.now() - 5 * MIN).toISOString(),
      home_probability: 0.42,
      away_probability: 0.58,
      spread: null,
      over_under: null,
      projected_home_score: null,
      projected_away_score: null,
    },
    ...over,
  } as unknown as FeedEventData;
}

function renderText(data: FeedEventData): string {
  const item = { type: "event", score: 50, reason: "", headline: "", data } as unknown as FeedItem;
  return renderToStaticMarkup(
    <DiscoverEventCard item={item} data={data} liked={false} setLiked={() => {}} trending={false} />
  ).replace(/<[^>]*>/g, " ");
}

describe("Discover EventCard renders the floored slot (#8277)", () => {
  it("a scheduled game 12 minutes past its start prints no negative minute count", () => {
    const t = renderText(makeData({ commence_time: new Date(Date.now() - 12 * MIN).toISOString() }));
    expect(t).not.toMatch(/-\d+m\b/);
    expect(t).not.toMatch(/\b0m\b/);
    expect(t).toMatch(/\d{1,2}:\d{2}\s?[AP]M/);
  });

  it("a scheduled game 20 minutes out still counts down", () => {
    const t = renderText(makeData({ commence_time: new Date(Date.now() + 20 * MIN + 10_000).toISOString() }));
    expect(t).toMatch(/\b2[01]m\b/);
  });

  it("a live game past its start still says Live, not a time of day", () => {
    const t = renderText(makeData({ status: "live", commence_time: new Date(Date.now() - 12 * MIN).toISOString() }));
    expect(t).toMatch(/Live/);
    expect(t).not.toMatch(/-\d+m\b/);
  });
});
