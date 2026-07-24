// L2-175 Item 3b/3c: a UFC CARD concept page must not render the main event twice
// (once in the "Main event" hero, again in the Matchups rail — one market, one
// display), and its head-to-head nav pill must be labelled to MATCH the section it
// targets (primary.label "Main event"), not the generic "Head to head" pointing at
// a mistitled anchor. SSR-rendered through the real page with a co-equal envelope.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

jest.mock("next/navigation", () => ({
  useParams: () => ({ domain: "ufc", slug: "26jul24" }),
  useRouter: () => ({ replace: () => {} }),
}));

const ENVELOPE = {
  event: {
    key: "event:ufc:26jul24",
    domain: "ufc",
    name: "UFC Fight Night",
    status: "live" as const,
    start_date: "2026-07-24",
    is_major: true,
  },
  primary: {
    kind: "co_equal_list" as const,
    label: "Main event",
    competitors: [
      { name: "Vanilto Antunes", probability: 0.76 },
      { name: "Markus Perez", probability: 0.24 },
    ],
    evolution_market_id: 100,
  },
  sections: [{ type: "matchup", label: "Fights", market_ids: [100, 101] }],
  children: [
    // The main event — ALSO the primary/evolution market. Must NOT re-render in the rail.
    {
      market_id: 100,
      market_name: "Vanilto Antunes vs Markus Perez",
      kind: "fight" as const,
      outcomes: [
        { name: "Vanilto Antunes", probability: 0.76 },
        { name: "Markus Perez", probability: 0.24 },
      ],
    },
    // A prelim — the sibling fight that SHOULD render in the rail.
    {
      market_id: 101,
      market_name: "Prelim: Charlie Campbell vs Danny Silva",
      kind: "fight" as const,
      outcomes: [
        { name: "Charlie Campbell", probability: 0.6 },
        { name: "Danny Silva", probability: 0.4 },
      ],
    },
  ],
  props_script: [],
  movers: [],
};

const HISTORY = {
  market_id: 100,
  market_name: "Main event",
  hours: 168,
  outcomes: [
    {
      outcome_id: 1,
      name: "Vanilto Antunes",
      history: [
        { timestamp: "2026-07-20T00:00:00Z", probability: 0.7, american_odds: null, bookmaker: "" },
        { timestamp: "2026-07-24T00:00:00Z", probability: 0.76, american_odds: null, bookmaker: "" },
      ],
    },
  ],
};

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
  fetchEventConcept: () => Promise.resolve(null),
  fetchFuturesHistory: () => Promise.resolve(HISTORY),
  formatProbability: (p: number | null) => (p == null ? "—" : `${Math.round(p * 100)}%`),
}));

import EventConceptPage from "../../app/event/[domain]/[slug]/page";

describe("UFC card page — dedupe + nav pill (L2-175 Item 3b/3c)", () => {
  const html = renderToStaticMarkup(<EventConceptPage />);

  test("the main event renders in the hero but NOT again in the Matchups rail", () => {
    // The hero (TwoSidedTimeline) shows the "Main event" label + competitor names.
    expect(html).toContain("Main event");
    expect(html).toContain("Markus Perez");
    // The rail (MatchupCard) prints the child market_name; the main event's must be
    // absent — it's excluded so one market renders in exactly one place.
    expect(html).not.toContain("Vanilto Antunes vs Markus Perez");
    // ...but the sibling prelim still renders in the rail.
    expect(html).toContain("Prelim: Charlie Campbell vs Danny Silva");
  });

  test("the head-to-head pill is labelled to match its section (not the generic 'Head to head')", () => {
    expect(html).toContain('href="#head-to-head"');
    expect(html).not.toContain("Head to head");
  });
});
