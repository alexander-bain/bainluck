// #9596 — A TOURNAMENT WITH NO DATES OF PLAY IS NOT "LIVE" BECAUSE ITS PRICES MOVED.
//
// `https://bainluck.com/sports` at 390px, 2026-09-29 10:25Z, under `Live Now 2`:
//
//     ⛳ LPGA Tour ● LIVE
//     LOTTE Championship presented by Hoakalei
//     12.5% Jeeno Thitikul — Leader +0.5 pts today
//
// Round 1 had not been played. ESPN's LPGA scoreboard still showed the finished
// Walmart NW Arkansas Championship, and Kalshi had opened the book the day before
// (`KXLPGATOUR-LOTCPBH26`, open 2026-09-28T17:22Z). `GET /api/golf` served no
// `start_date` / `end_date`, so `isTournamentLive` fell through to its last arm:
// any golfer's 24h movement ≥ 0.01 counted as live. Price discovery on a new book
// is exactly that, and it always comes BEFORE the first tee time.
//
// The payload below is the served row, trimmed to what the decision and the card
// read. Both readers of the decider are rendered: the card's badge and the
// section `/sports` files it under.
//
//   cd frontend && npx jest --testPathPatterns=tournamentNoDatePriceMoveNotLive9596

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import FeedCard from "@/components/FeedCard";
import { groupFeedIntoSections } from "@/lib/feedSections";
import { isTournamentLive } from "@/lib/tournamentLive";
import type { FeedItem, FeedTournamentData } from "@/lib/types";

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

function at<T>(now: string, fn: () => T): T {
  jest.useFakeTimers({ now: new Date(now) });
  try {
    return fn();
  } finally {
    jest.useRealTimers();
  }
}

/** `GET /api/golf`, 2026-09-29 10:26Z — no dates of play, prices moving. */
const LOTTE: FeedTournamentData = {
  key: "lotte_championship_presented_by_hoakalei",
  name: "LOTTE Championship presented by Hoakalei",
  slug: "lotte-championship",
  tour: "lpga",
  tour_label: "LPGA Tour",
  is_major: false,
  venue: null,
  location: null,
  start_date: null,
  end_date: null,
  schedule_status: null,
  commence_time: "2026-10-18T04:00:00+00:00",
  resolution_date: "2026-10-18T04:00:00+00:00",
  golfers: [
    { name: "Jeeno Thitikul", probability: 0.125, rank: 1, movement_24h: 0.005 },
    { name: "Megan Khang", probability: 0.091, rank: 2, movement_24h: null },
    { name: "Allisen Corpuz", probability: 0.091, rank: 7, movement_24h: -0.05 },
    { name: "Yuna Nishimura", probability: 0.08, rank: 12, movement_24h: -0.2 },
  ],
  market_ids: [63115883],
  source_count: 1,
  is_marquee: false,
  marquee_whathit: false,
};

const PHOTOGRAPH = "2026-09-29T10:25:00Z";

function item(data: FeedTournamentData): FeedItem {
  return { type: "tournament", score: 50, reason: "", headline: "", data } as unknown as FeedItem;
}

const BADGE = /animate-pulse"><\/span>([^<]*)<\/span>/;

function cardSaysLive(data: FeedTournamentData, now: string): boolean {
  return BADGE.test(at(now, () => renderToStaticMarkup(<FeedCard item={item(data)} />)));
}

function sectionKeyFor(data: FeedTournamentData, now: string): string {
  const sections = at(now, () => groupFeedIntoSections([item(data)]));
  const holder = sections.find((s) => s.items.length > 0);
  if (!holder) throw new Error("the bucketer dropped the tournament entirely");
  return holder.key;
}

describe("#9596 · a no-date tournament is not live on price movement alone", () => {
  it("the specimen's prices really are moving past the old threshold", () => {
    // The premise, asserted so the rest of this file cannot pass vacuously: the
    // retired arm WOULD have fired on this row.
    expect(LOTTE.start_date).toBeNull();
    expect(LOTTE.end_date).toBeNull();
    expect(LOTTE.golfers.some((g) => g.movement_24h != null && Math.abs(g.movement_24h) >= 0.01)).toBe(true);
  });

  it("the LOTTE card carries no LIVE badge and is not filed under Live Now", () => {
    expect(at(PHOTOGRAPH, () => isTournamentLive(LOTTE))).toBe(false);
    expect(cardSaysLive(LOTTE, PHOTOGRAPH)).toBe(false);
    expect(sectionKeyFor(LOTTE, PHOTOGRAPH)).not.toBe("live");
  });

  it("the same row with its real dates of play IS live inside them — the fix did not dim every golf card", () => {
    // Gotcha #43, the other direction. Play is Wed Sep 30 – Sat Oct 3 in Hawaii.
    const dated = { ...LOTTE, start_date: "2026-09-30T00:00:00+00:00", end_date: "2026-10-03T00:00:00+00:00" };
    const round2 = "2026-10-01T22:00:00Z";
    expect(cardSaysLive(dated, round2)).toBe(true);
    expect(sectionKeyFor(dated, round2)).toBe("live");
    // ...and not the day before round 1, with the prices still moving.
    expect(cardSaysLive(dated, PHOTOGRAPH)).toBe(false);
  });

  it("a no-date row the server marks in progress is still live", () => {
    const inProgress = { ...LOTTE, schedule_status: "in-progress" };
    expect(cardSaysLive(inProgress, PHOTOGRAPH)).toBe(true);
    expect(sectionKeyFor(inProgress, PHOTOGRAPH)).toBe("live");
  });
});
