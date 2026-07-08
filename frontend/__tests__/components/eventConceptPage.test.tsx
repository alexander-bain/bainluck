// #999 L2-60: render guard for /event/[key]. The page P1-crashed in prod (SSR)
// while the unit suite stayed green because it only tested pure helpers. This
// SSR-renders the actual page component (renderToStaticMarkup — the same server
// path that crashed) with a real envelope, so a render-time throw (e.g. the
// `use(params)` bug) fails the test.

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
      { name: "Scottie Scheffler", probability: 0.22 },
      { name: "Rory McIlroy", probability: 0.15 },
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
  movers: [],
};

// Call the fetcher (unlike a plain data-return mock) so we observe the key the
// page passes to fetchEventConcept — that's where the double-encoding bug lived.
jest.mock("swr", () => ({
  __esModule: true,
  default: (_key: unknown, fetcher?: () => unknown) => {
    if (fetcher) { try { fetcher(); } catch { /* ignore */ } }
    return { data: ENVELOPE, error: null, isLoading: false };
  },
}));

jest.mock("@/hooks", () => ({
  usePageTracking: () => {},
  useScrollDepth: () => {},
  useEngagementTime: () => {},
}));

jest.mock("@/lib/api", () => ({
  fetchEventConcept: (k: string) => { fetchCalls.push(k); return Promise.resolve(null); },
  formatProbability: (p: number | null) =>
    p == null ? "—" : `${Math.round(p * 100)}%`,
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
import EventConceptPage from "../../app/event/[key]/page";

describe("EventConceptPage SSR render (L2-60 guard)", () => {
  test("renders the winner field + sections + children without throwing", () => {
    const html = renderToStaticMarkup(<EventConceptPage />);
    // header
    expect(html).toContain("The Open Championship");
    expect(html).toContain("Live");
    // winner field competitors (the render path that crashed)
    expect(html).toContain("Scottie Scheffler");
    expect(html).toContain("Rory McIlroy");
    // sections + children
    expect(html).toContain("Markets");
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
