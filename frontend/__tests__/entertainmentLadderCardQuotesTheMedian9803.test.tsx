/**
 * #9803 — an /entertainment ladder card quotes the rung the market leans on, not its loosest.
 *
 * Production 2026-09-30 10:50Z, 390px: every Rotten Tomatoes card printed
 * `top_outcomes[0]` beside `prob`, which on a cumulative ladder is the loosest
 * rung — "Clayface · Rotten Tomatoes score · Above 45 · 95%". The route now serves
 * `headline` (the `ladder_median_row` rung, #9283/#9531) when it differs from the
 * priced leader (`backend/tests/test_entertainment_ladder_card_quotes_the_median_9803.py`).
 * This file pins the card's half: it prints the headline, and a row without one
 * prints exactly what it did before.
 *
 * Rig: `entertainmentSpotifyLadderIsNotARace9468`'s — the page's DEFAULT export,
 * so `GenericMarketCard` stays module-local.
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

/** Clayface's served legs (production 10:55Z), price order, the 8-slot rack. */
const CLAYFACE_LEGS: [string, number][] = [
  ["Above 45", 94.5],
  ["Above 50", 92.5],
  ["Above 55", 87.5],
  ["Above 60", 82.5],
  ["Above 65", 70.5],
  ["Above 70", 65.5],
  ["Above 75", 55.5],
  ["Above 80", 42.5],
];

function row(over: Partial<EntMarketRow>): EntMarketRow {
  return {
    q: "Clayface · Rotten Tomatoes score",
    prob: 94.5,
    src: "kalshi",
    market_id: 58728375,
    external_id: "KXRTCLAYFACE",
    kind: "rt",
    top_outcomes: CLAYFACE_LEGS.map(([name, prob]) => ({ name, prob, delta_24h: 0 })),
    outcome_count: 10,
    volume_24h: 1,
    resolution_date: null,
    image_url: null,
    hook: null,
    ...over,
  };
}

function render(rtMarkets: EntMarketRow[]): string {
  const empty = { count: 0, side_markets: [] };
  (global as never as { __ENT__: EntertainmentData }).__ENT__ = {
    total_markets: 104,
    updated_at: "2026-09-30T10:00:00Z",
    trending: [],
    themes: {
      music: {
        ...empty,
        spotify_race: [],
        billboard_watch: [],
        billboard_groups: [],
        album_drops: [],
        artist_streaming: [],
      },
      movies_tv: {
        ...empty,
        count: rtMarkets.length,
        rt_groups: [],
        rt_markets: rtMarkets,
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

/** The markup of the one card linking to this market. */
function card(html: string, marketId: number): string {
  const at = html.indexOf(`href="/futures/${marketId}"`);
  expect(at).toBeGreaterThanOrEqual(0);
  const end = html.indexOf("</a>", at);
  return html.slice(at, end);
}

/** Visible text of a markup slice. */
function text(markup: string): string {
  return markup.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
}

describe("#9803 GenericMarketCard prints the served ladder headline", () => {
  it("quotes the median rung, not the loosest", () => {
    const t = text(card(render([row({ headline: { name: "Above 75", prob: 55.5 } })]), 58728375));
    expect(t).toContain("Above 75");
    expect(t).not.toContain("Above 45");
    expect(t).not.toMatch(/\b95\s*%/);
  });

  it("strawman: without a headline the card prints the loosest rung, as before", () => {
    const t = text(card(render([row({ headline: null })]), 58728375));
    expect(t).toContain("Above 45");
    expect(t).not.toContain("Above 75");
  });

  it("an older payload with no headline field renders the priced leader", () => {
    const race = row({
      q: "Big Brother Season 28 · Winner",
      market_id: 1,
      kind: "reality",
      prob: 52,
      top_outcomes: [
        { name: "Rick Devens", prob: 52, delta_24h: 0 },
        { name: "Drew Campbell", prob: 34, delta_24h: 0 },
      ],
      outcome_count: 3,
    });
    const t = text(card(render([race]), 1));
    expect(t).toContain("Rick Devens");
    expect(t).toMatch(/\b52\s*%/);
  });
});
