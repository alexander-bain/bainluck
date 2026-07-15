// #999 L2-60/L2-64: render guard for /event/[domain]/[slug]. The page P1-crashed in
// prod (SSR) while the unit suite stayed green because it only tested pure helpers.
// This SSR-renders the ACTUAL page component AND its L2-64 children (header,
// movers strip, race chart, leaderboard w/ sparklines, matchups rail) via
// renderToStaticMarkup — the same server path that crashed — with a real envelope
// + real history, so a render-time throw fails the test.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

// L2-113: params are now the two colon-free segments (domain + slug); the page
// reconstructs the API key `event:<domain>:<slug>` from them. useRouter is mocked
// because the page uses router.replace for the pretty-slug upgrade (an effect that
// never fires under renderToStaticMarkup, but the hook must exist at render).
jest.mock("next/navigation", () => ({
  useParams: () => ({ domain: "golf", slug: "the-open-championship" }),
  useRouter: () => ({ replace: () => {} }),
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
      {
        name: "Scottie Scheffler",
        probability: 0.22,
        movement_24h: 0.03,
        top_5_prob: 58,
        top_10_prob: 74,
        make_cut_prob: 96,
      },
      {
        name: "Rory McIlroy",
        probability: 0.15,
        movement_24h: -0.01,
        top_5_prob: 45,
        top_10_prob: 63,
        make_cut_prob: 94,
      },
    ],
    evolution_market_id: 1,
  },
  // L2-116: finish-position sections carry the placement markets whose odds are
  // fused onto competitors above — the FinishPositionLadder renders them.
  sections: [
    { type: "winner", label: "Winner", market_ids: [1] },
    { type: "top_5", label: "Top 5", market_ids: [21] },
    { type: "top_10", label: "Top 10", market_ids: [22] },
    { type: "make_cut", label: "Make Cut", market_ids: [23] },
  ],
  children: [
    {
      market_id: 9,
      market_name: "H2H: Scheffler vs McIlroy",
      outcomes: [
        { name: "Scheffler", probability: 0.55 },
        { name: "McIlroy", probability: 0.45 },
      ],
    },
    // L2-121: a round-leader prop child that ALSO appears in props_script below.
    // It must render once (in PropsSection), deduped out of the plain props grid.
    {
      market_id: 42,
      market_name: "Round 1 Leader",
      kind: "prop",
      prop_type: "round",
      outcomes: [{ name: "Scottie Scheffler", probability: 0.044 }],
    },
  ],
  // L2-121: the shared PropsSection body (THE SCRIPT → THE DIVERGENCE) for the
  // FIELD hero — opening (pregame_mark) → current per prop.
  props_script: [
    {
      key: 41,
      market_id: 41,
      label: "Playoff",
      pregame_mark: 0.28,
      current: 0.205,
      graded_result: null,
      graded_label: null,
    },
    {
      key: 42,
      market_id: 42,
      label: "Round 1 Leader: Scottie Scheffler",
      pregame_mark: 0.0495,
      current: 0.044,
      graded_result: null,
      graded_label: null,
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
import EventConceptPage from "../../app/event/[domain]/[slug]/page";

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
    // L2-116 finish-position ladder — the counted-but-formerly-invisible markets
    // now render (renders without throwing under SSR is the guard's whole point).
    expect(html).toContain("Finish position");
    expect(html).toContain("Top 5");
    expect(html).toContain("Make cut");
    // probability-only: no American-odds moneyline strings
    expect(html).not.toMatch(/[+-]\d{3,}/);
  });

  test("mounts PropsSection (THE SCRIPT/DIVERGENCE) and dedups its markets from the plain props grid (L2-121)", () => {
    const html = renderToStaticMarkup(<EventConceptPage />);
    // The shared props body renders under its own anchor (not the plain EventProps).
    expect(html).toContain('id="props-script"');
    // Live event -> THE DIVERGENCE state, with real props-script labels.
    expect(html).toContain("The divergence");
    expect(html).toContain("Playoff");
    expect(html).toContain("Round 1 Leader: Scottie Scheffler");
    // The round-leader prop child (market_id 42) is deduped out of the plain grid,
    // so the plain EventProps "By round" group must NOT also render it.
    expect(html).not.toContain("By round");
    // The H2H matchup (not a props-script market) still renders in the rail.
    expect(html).toContain("H2H: Scheffler vs McIlroy");
  });

  test("reconstructs the API key from the domain/slug segments (L2-113)", () => {
    fetchCalls.length = 0;
    renderToStaticMarkup(<EventConceptPage />);
    // The colon-free route segments recompose the canonical `event:<domain>:<slug>`
    // key the API expects — with literal colons, never percent-encoded.
    expect(fetchCalls[0]).toBe("event:golf:the-open-championship");
    expect(fetchCalls[0]).not.toContain("%3A");
    expect(fetchCalls[0]).not.toContain("%253A");
  });
});
