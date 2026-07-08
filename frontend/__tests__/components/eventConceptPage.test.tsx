// #999 L2-60: render guard for /event/[key]. The page P1-crashed in prod (SSR)
// while the unit suite stayed green because it only tested pure helpers. This
// SSR-renders the actual page component (renderToStaticMarkup — the same server
// path that crashed) with a real envelope, so a render-time throw (e.g. the
// `use(params)` bug) fails the test.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

// Next 14 client-component params come from useParams() (a plain object).
jest.mock("next/navigation", () => ({
  useParams: () => ({ key: "event:golf:the-open-championship" }),
}));

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

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: ENVELOPE, error: null, isLoading: false }),
}));

jest.mock("@/hooks", () => ({
  usePageTracking: () => {},
  useScrollDepth: () => {},
  useEngagementTime: () => {},
}));

jest.mock("@/lib/api", () => ({
  fetchEventConcept: jest.fn(),
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
});
