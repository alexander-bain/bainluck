// #999 L2-60/L2-64: render guard for /event/[key]. The page P1-crashed in prod
// (SSR) while the unit suite stayed green because it only tested pure helpers.
// This SSR-renders the ACTUAL page component AND its L2-64 children (header,
// movers strip, race chart, leaderboard w/ sparklines, matchups rail) via
// renderToStaticMarkup — the same server path that crashed — with a real envelope
// + real history, so a render-time throw fails the test.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

// Next 14 client-component params come from useParams() — which returns the
// segment STILL percent-encoded. The page must decode ONCE before fetch, else it
// double-encodes (event%253A…) and 404s (L2-61).
jest.mock("next/navigation", () => ({
  useParams: () => ({ key: "event%3Agolf%3Athe-open-championship" }),
}));

// Capture the key the page hands to fetchEventConcept so we can assert it's
// singly-DECODED (literal colons) — never the raw %3A form.
const fetchCalls: string[] = [];

// SWR resolved to a golf envelope so the content branch renders (not loading).
const ENVELOPE = {
  event: {
    key: "event:golf:the-open-championship",
    domain: "golf",
    name: "The Open Championship",
    status: "live" as const,
    start_date: "2026-07-16",
    end_date: "2026-07-19",
    venue: "Royal Birkdale",
    location: "England",
    is_major: true,
  },
  primary: {
    kind: "winner_field" as const,
    label: "Winner",
    competitors: [
      { name: "Scottie Scheffler", probability: 0.22, movement_24h: 0.03 },
      { name: "Rory McIlroy", probability: 0.15, movement_24h: -0.01 },
    ],
    evolution_market_id: 1,
  },
  sections: [{ type: "winner", label: "Winner", market_ids: [1] }],
  children: [
    {
      market_id: 9,
      market_name: "H2H: Scheffler vs McIlroy",
      outcomes: [
        { name: "Scheffler", probability: 0.55 },
        { name: "McIlroy", probability: 0.45 },
      ],
    },
  ],
  movers: [{ name: "Rory McIlroy", change: 0.03 }],
};

// Real 2-point history so the race chart + per-row sparklines actually render
// (exercises FuturesChart + Sparkline under SSR).
const HISTORY = {
  market_id: 1,
  market_name: "Winner",
  hours: 168,
  outcomes: [
    {
      outcome_id: 1,
      name: "Scottie Scheffler",
      history: [
        { timestamp: "2026-07-01T00:00:00Z", probability: 0.2, american_odds: null, bookmaker: "" },
        { timestamp: "2026-07-02T00:00:00Z", probability: 0.22, american_odds: null, bookmaker: "" },
      ],
    },
    {
      outcome_id: 2,
      name: "Rory McIlroy",
      history: [
        { timestamp: "2026-07-01T00:00:00Z", probability: 0.16, american_odds: null, bookmaker: "" },
        { timestamp: "2026-07-02T00:00:00Z", probability: 0.15, american_odds: null, bookmaker: "" },
      ],
    },
  ],
};

// Key-aware swr mock: envelope for the page, history for chart/sparkline fetches.
// Calls the fetcher (unlike a plain data-return mock) so we observe the decoded
// key the page passes to fetchEventConcept — where the double-encoding bug lived.
jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown, fetcher?: () => unknown) => {
    if (fetcher) { try { fetcher(); } catch { /* ignore */ } }
    const tag = Array.isArray(key) ? key[0] : key;
    if (key == null) return { data: undefined, error: null, isLoading: false };
    if (tag === "event-concept") return { data: ENVELOPE, error: null, isLoading: false };
    return { data: HISTORY, error: null, isLoading: false };
  },
}));

jest.mock("@/hooks", () => ({
  usePageTracking: () => {},
  useScrollDepth: () => {},
  useEngagementTime: () => {},
}));

jest.mock("@/lib/api", () => ({
  fetchEventConcept: (k: string) => { fetchCalls.push(k); return Promise.resolve(null); },
  fetchFuturesHistory: () => Promise.resolve(HISTORY),
  formatProbability: (p: number | null) =>
    p == null ? "—" : `${Math.round(p * 100)}%`,
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
import EventConceptPage from "../../app/event/[key]/page";

describe("EventConceptPage SSR render (L2-60/L2-64 guard)", () => {
  test("renders header + movers + race chart + leaderboard + matchups without throwing", () => {
    const html = renderToStaticMarkup(<EventConceptPage />);
    // event-framed header
    expect(html).toContain("The Open Championship");
    expect(html).toContain("Live");
    expect(html).toContain("markets tracked"); // markets-tracked count
    // today's movers strip
    expect(html).toContain("movers");
    // race-to-the-title chart section
    expect(html).toContain("Race to the title");
    // winner-field leaderboard competitors (the render path that crashed)
    expect(html).toContain("Scottie Scheffler");
    expect(html).toContain("Rory McIlroy");
    // matchups rail
    expect(html).toContain("H2H: Scheffler vs McIlroy");
    // probability-only: no American-odds moneyline strings
    expect(html).not.toMatch(/[+-]\d{3,}/);
  });

  test("passes the DECODED key to fetchEventConcept (no double-encoding, L2-61)", () => {
    fetchCalls.length = 0;
    renderToStaticMarkup(<EventConceptPage />);
    // useParams gave the percent-encoded segment; the page must decode ONCE so
    // fetchEventConcept's own encodeURIComponent yields %3A (single), not %253A.
    expect(fetchCalls[0]).toBe("event:golf:the-open-championship");
    expect(fetchCalls[0]).not.toContain("%3A");
    expect(fetchCalls[0]).not.toContain("%253A");
  });
});
