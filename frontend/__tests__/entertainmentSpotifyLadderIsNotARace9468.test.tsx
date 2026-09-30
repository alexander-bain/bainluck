/**
 * #9468 — /entertainment stops ranking Spotify Wrapped release dates as a chart race.
 *
 * Production 2026-09-28: the Music section's "Spotify Chart Race" card was Kalshi's
 * "When will Spotify release 2026 Wrapped?", drawn as `1 Before Dec 4 · 2 Before
 * Dec 5 · 3 Before Dec 3 …` with the #1 slot lit as the leader. Those legs nest —
 * "Before Dec 5" contains "Before Dec 4" — so no date is ahead of another.
 *
 * The route now serves such a row with `ladder: true` and its legs in rung order
 * (`backend/tests/test_entertainment_spotify_ladder_9468.py`). This file pins the
 * card's half: a ladder draws the legs in the order served, with no rank number,
 * no leader and no "Chart Race" eyebrow — and a real race still draws all three.
 *
 * Rig: `entertainmentResolvesKeepsYearAndDay6773`'s — it mounts the page's
 * DEFAULT export, so `SpotifyRace` stays module-local.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { EntertainmentData, EntMarketRow } from "@/lib/api";

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({
    data: (global as never as { __ENT__: EntertainmentData }).__ENT__,
    error: undefined,
  }),
}));
jest.mock("@/hooks", () => ({
  usePageTracking: () => undefined,
  useScrollDepth: () => undefined,
  useEngagementTime: () => undefined,
}));
jest.mock("@/lib/tmdb", () => ({
  hasTMDBToken: () => false,
  searchMovie: async () => null,
  posterUrl: (p: string) => p,
}));

import EntertainmentPage from "@/app/entertainment/page";

/** The production legs, in the calendar order the route now serves them. */
const WRAPPED_LEGS: [string, number][] = [
  ["Before Nov 28, 2026", 7],
  ["Before Nov 29, 2026", 8],
  ["Before Nov 30, 2026", 10],
  ["Before Dec 1, 2026", 12],
  ["Before Dec 2, 2026", 20],
  ["Before Dec 3, 2026", 78],
  ["Before Dec 4, 2026", 82.5],
  ["Before Dec 5, 2026", 82.5],
];

function row(over: Partial<EntMarketRow>): EntMarketRow {
  return {
    q: "When will Spotify release 2026 Wrapped?",
    prob: 82.5,
    src: "kalshi",
    market_id: 109527,
    external_id: "KXSPOTIFYWRAPPED-26",
    kind: "spotify",
    top_outcomes: WRAPPED_LEGS.map(([name, prob]) => ({ name, prob, delta_24h: 0 })),
    outcome_count: 9,
    volume_24h: 1,
    resolution_date: null,
    image_url: null,
    hook: null,
    ...over,
  };
}

function render(spotifyRace: EntMarketRow[]): string {
  const empty = { count: 0, side_markets: [] };
  (global as never as { __ENT__: EntertainmentData }).__ENT__ = {
    total_markets: 182,
    updated_at: "2026-09-28T21:00:00Z",
    trending: [],
    themes: {
      music: {
        ...empty,
        spotify_race: spotifyRace,
        billboard_watch: [],
        billboard_groups: [],
        album_drops: [],
        artist_streaming: [],
      },
      movies_tv: {
        ...empty,
        rt_groups: [],
        rt_markets: [],
        box_office_groups: [],
        box_office: [],
        reality_tv: [],
      },
      tech_culture: { count: 0, markets: [] },
    },
    cultural_moments: [],
    by_source: { kalshi: 0, polymarket: 0 },
  } as unknown as EntertainmentData;
  return renderToStaticMarkup(React.createElement(EntertainmentPage));
}

/** The rank numbers the race card printed, read off its rank spans. */
function ranks(html: string): string[] {
  return [...html.matchAll(/<span class="raceRank(?:Lead)?">(\d+)<\/span>/g)].map((m) => m[1]);
}

/** Leg labels in document order, restricted to the specimen's own names. */
function legOrder(html: string, names: string[]): string[] {
  return names
    .map((n) => [n, html.indexOf(`>${n}<`)] as const)
    .filter(([, at]) => at >= 0)
    .sort((a, b) => a[1] - b[1])
    .map(([n]) => n);
}

describe("#9468 SpotifyRace draws a cumulative ladder as dates, not ranks", () => {
  const names = WRAPPED_LEGS.map(([n]) => n);

  it("prints no rank number and no leader for a ladder row", () => {
    const html = render([row({ ladder: true })]);
    // Non-vacuous: the card rendered its legs at all.
    expect(legOrder(html, names)).toHaveLength(8);
    expect(ranks(html)).toEqual([]);
    expect(html).not.toContain("raceRankLead");
    expect(html).not.toContain("Spotify Chart Race");
  });

  it("keeps the calendar order the route served", () => {
    const html = render([row({ ladder: true })]);
    expect(legOrder(html, names)).toEqual(names);
  });

  it("still ranks a real race of named contenders", () => {
    const contenders: [string, number][] = [
      ["Bad Bunny", 41],
      ["Taylor Swift", 33],
      ["The Weeknd", 12],
    ];
    const html = render([
      row({
        q: "Top artist on Spotify this week?",
        ladder: false,
        top_outcomes: contenders.map(([name, prob]) => ({ name, prob, delta_24h: 0 })),
      }),
    ]);
    expect(ranks(html)).toEqual(["1", "2", "3"]);
    expect(html).toContain("raceRankLead");
    expect(html).toContain("Spotify Chart Race");
  });

  it("treats a row with no ladder field (an older payload) as a race", () => {
    const html = render([row({})]);
    expect(ranks(html)).toEqual(["1", "2", "3", "4", "5", "6", "7", "8"]);
  });
});
