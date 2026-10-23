// #9208 — THE DISCOVER HERO SAID "Paused" AND 0 · 0 OVER A RAINED-OUT GAME.
//
// shopper's 390px re-look on production (main v5757 `91ff0eaa`, 2026-10-17
// 04:18Z): ALCS G4 15330795, Rays @ Guardians, served `status: suspended` with
// `espn.period: "Postponed"` (ESPN STATUS_POSTPONED, rain, makeup Oct 18). After
// PR #11165 the Discover card's ROW read `POSTPONED · Oct 16`, but the hero —
// the slot between the two crests and the scores under them — still read
//
//   between crests    Paused
//   under the crests  0    0
//
// "Paused" says play stopped mid-game and 0-0 says it stood there; the row below
// had already refused both (#8810, #8960's filler rule). The slot hard-coded
// "Paused" for every suspended row and drew whatever scores were served.
//
// RENDERED, NOT GREPPED, and BOTH DIRECTIONS (gotcha #43): every stoppage case
// has a control asserting that a suspended card WITHOUT a stoppage word keeps
// "Paused" and its last score, and a stopped match WITH a score keeps it.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

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
jest.mock("@/hooks", () => ({
  useAnalytics: () => ({ trackEventCardClick: () => {}, track: () => {} }),
}));

import { EventCard } from "@/components/discover/EventCard";
import type { FeedEventData, FeedItem } from "@/lib/types";

const DAY = 24 * 3600_000;
const PLAYED_1D_AGO = new Date(Date.now() - DAY).toISOString();

/** The ALCS G4 shape, as `/api/feed` serves it after #11165. */
function render(over: Record<string, unknown> = {}): string {
  const data = {
    id: 15330795,
    sport: "baseball_mlb",
    sport_name: "MLB",
    home_team: "Cleveland Guardians",
    away_team: "Tampa Bay Rays",
    commence_time: PLAYED_1D_AGO,
    status: "suspended",
    home_score: 0,
    away_score: 0,
    espn: { period: "Postponed" },
    ...over,
  } as unknown as FeedEventData;
  const item = { type: "event", score: 50, reason: "", headline: "", data } as unknown as FeedItem;
  return renderToStaticMarkup(
    <EventCard item={item} data={data} liked={false} setLiked={() => {}} trending={false} />,
  );
}

/** The text of the slot between the crests (the only `text-white/70 text-sm` span). */
function slot(html: string): string {
  const m = html.match(/<span class="text-white\/70 text-sm font-semibold">([^<]*)<\/span>/);
  if (!m) throw new Error("hero slot not found — the selector, not the card, is wrong");
  return m[1];
}

/** The hero score numbers, in DOM order (away, home). */
function heroScores(html: string): string[] {
  return [...html.matchAll(/<span class="text-2xl font-black tabular-nums text-white drop-shadow">([^<]*)<\/span>/g)].map(
    (m) => m[1],
  );
}

function ariaLabel(html: string): string {
  return html.match(/<article[^>]*aria-label="([^"]*)"/)?.[1] ?? "";
}

describe("#9208 — the Discover hero takes the authority's stoppage word", () => {
  it("THE SPECIMEN: Postponed between the crests, ESPN's 0-0 filler not drawn", () => {
    const html = render();
    expect(slot(html)).toBe("Postponed");
    expect(heroScores(html)).toEqual([]);
    expect(html).not.toContain(">Paused<");
    expect(ariaLabel(html)).toBe("Tampa Bay Rays vs Cleveland Guardians - Postponed");
    // The row #11165 fixed stays fixed.
    expect(html).toMatch(/data-testid="event-card-suspended"[^>]*>Postponed</);
  });

  it("Canceled reads Canceled, the same way", () => {
    const html = render({ espn: { period: "Cancelled" } });
    expect(slot(html)).toBe("Canceled");
    expect(heroScores(html)).toEqual([]);
  });

  it("no scores served at all: still the word, still nothing drawn", () => {
    const html = render({ home_score: null, away_score: null });
    expect(slot(html)).toBe("Postponed");
    expect(heroScores(html)).toEqual([]);
  });

  it("a match stopped WITH a score keeps it (#8810's event-hero rule)", () => {
    const html = render({ away_score: 2, home_score: 1 });
    expect(slot(html)).toBe("Postponed");
    expect(heroScores(html)).toEqual(["2", "1"]);
  });

  it("CONTROL: a suspended card with no stoppage word is unchanged — Paused, last score drawn", () => {
    for (const espn of [undefined, null, { period: null }, { period: "End 9th" }]) {
      const html = render({ espn });
      expect(slot(html)).toBe("Paused");
      expect(heroScores(html)).toEqual(["0", "0"]);
      expect(ariaLabel(html)).toBe("Tampa Bay Rays vs Cleveland Guardians - No result reported");
    }
  });

  it("CONTROL: a live row holding a stale 'Postponed' period is not a stoppage card", () => {
    const html = render({ status: "live", away_score: 0, home_score: 0 });
    expect(slot(html)).not.toBe("Paused");
    expect(heroScores(html)).toEqual(["0", "0"]);
  });
});
