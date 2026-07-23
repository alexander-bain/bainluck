// L2-166 — THE SUNDAY DRESS REHEARSAL. Monday's graduation exam runs organic in
// prod (no sentinel pre-runs), but the FULL frontend stack for the settled-marquee
// moment has never rendered together: #241's `winner` field + `marquee_whathit` +
// L2-159's WHAT-HIT renderer + the settled evolution chart. This drives ONE
// coherent settled Tour de France payload — EXACTLY as backend routes/feed.py +
// the event-concept envelope will emit it Sunday — through the REAL components
// (both feed cards, the concept page hero, the settled evolution chart), and the
// LIVE (unsettled) direction to prove today's behavior is untouched (gotcha #43).
//
// Seam bug this rehearsal CAUGHT (now fixed in the same queue): the Discover-tab
// card switch (DiscoverCard) had no `concept` branch, yet routes/feed.py emits
// `type:"concept"` items into the DEFAULT Discover feed (include_events defaults
// true). The settled TdF WHAT-HIT marquee therefore rendered as an EMPTY card on
// the landing page. The `ConceptCard` guard below fails without the fix.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type {
  FeedItem,
  FeedConceptData,
  EventConceptResponse,
  FuturesHistoryResponse,
} from "@/lib/types";

// ── The ONE coherent settled Tour de France world (Pogačar crowned) ──

// Feed-card payload (routes/feed.py _score_event_concepts): a settled marquee
// concept in its T+36h WHAT-HIT window, champion named per #241/#1219.
const SETTLED_CONCEPT: FeedConceptData = {
  key: "event:cycling:tour-de-france-2026",
  name: "Tour de France 2026",
  domain: "cycling",
  status: "settled",
  start_date: "2026-07-04",
  is_major: true,
  fight_count: 0,
  is_marquee: true,
  marquee_whathit: true,
  winner: "Tadej Pogačar",
  result_summary: "by 3:24",
};

// Live (unsettled) counterpart — same tour, mid-race.
const LIVE_CONCEPT: FeedConceptData = {
  key: "event:cycling:tour-de-france-2026",
  name: "Tour de France 2026",
  domain: "cycling",
  status: "live",
  start_date: "2026-07-04",
  is_major: true,
  fight_count: 0,
  is_marquee: true,
  marquee_whathit: false,
};

function conceptFeedItem(data: FeedConceptData): FeedItem {
  return {
    type: "concept",
    score: 95,
    reason: "Stage 21 — the final ride into Paris",
    headline: "Today",
    data,
  };
}

// Concept-page envelope (the /event/cycling/tour-de-france-2026 surface). The
// settled winner-field crowns Pogačar via the authoritative `won` flag.
const SETTLED_ENVELOPE: EventConceptResponse = {
  event: {
    key: "event:cycling:tour-de-france-2026",
    domain: "cycling",
    name: "Tour de France 2026",
    status: "settled",
    start_date: "2026-07-04",
    end_date: "2026-07-26",
    is_major: true,
  },
  primary: {
    kind: "winner_field",
    label: "Winner",
    competitors: [
      { name: "Tadej Pogačar", probability: 1.0, won: true, outcome_id: 1 },
      { name: "Jonas Vingegaard", probability: 0.0, outcome_id: 2 },
      { name: "Remco Evenepoel", probability: 0.0, outcome_id: 3 },
    ],
    evolution_market_id: 501,
  },
  sections: [],
  children: [],
  movers: [],
} as unknown as EventConceptResponse;

const LIVE_ENVELOPE: EventConceptResponse = {
  event: {
    key: "event:cycling:tour-de-france-2026",
    domain: "cycling",
    name: "Tour de France 2026",
    status: "live",
    start_date: "2026-07-04",
    end_date: "2026-07-26",
    is_major: true,
  },
  primary: {
    kind: "winner_field",
    label: "Winner",
    competitors: [
      { name: "Tadej Pogačar", probability: 0.62, outcome_id: 1 },
      { name: "Jonas Vingegaard", probability: 0.28, outcome_id: 2 },
      { name: "Remco Evenepoel", probability: 0.1, outcome_id: 3 },
    ],
    evolution_market_id: 501,
  },
  sections: [],
  children: [],
  movers: [],
} as unknown as EventConceptResponse;

// Resolved evolution series for the settled path chart: Pogačar's blended win-prob
// line climbs to 1.0 (won), his rivals fall to 0. This is what /api/futures/501/
// history returns once the champion is graded (SettledPathChart passes the champion
// name so the winner's line resolves to 1.0 even if odds_api never graded it).
const SETTLED_HISTORY: FuturesHistoryResponse = {
  market_id: 501,
  market_name: "Winner",
  hours: 8760,
  outcomes: [
    {
      outcome_id: 1,
      name: "Tadej Pogačar",
      history: [
        { timestamp: "2026-07-04T00:00:00Z", probability: 0.35, american_odds: null, bookmaker: "" },
        { timestamp: "2026-07-15T00:00:00Z", probability: 0.72, american_odds: null, bookmaker: "" },
        { timestamp: "2026-07-26T00:00:00Z", probability: 1.0, american_odds: null, bookmaker: "" },
      ],
    },
    {
      outcome_id: 2,
      name: "Jonas Vingegaard",
      history: [
        { timestamp: "2026-07-04T00:00:00Z", probability: 0.30, american_odds: null, bookmaker: "" },
        { timestamp: "2026-07-15T00:00:00Z", probability: 0.22, american_odds: null, bookmaker: "" },
        { timestamp: "2026-07-26T00:00:00Z", probability: 0.0, american_odds: null, bookmaker: "" },
      ],
    },
  ],
} as unknown as FuturesHistoryResponse;

// ── Module-mutable holders the swr mock reads (mock-prefixed → hoist-safe) ──
let mockEnvelope: EventConceptResponse | null = SETTLED_ENVELOPE;
let mockHistory: FuturesHistoryResponse | null = SETTLED_HISTORY;

// ── Mocks (mirror marqueeWhatHit + eventConceptPage test patterns) ──
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

jest.mock("next/image", () => ({
  __esModule: true,
  default: ({ alt }: { alt: string }) => <img alt={alt} />,
}));

jest.mock("@/components/Analytics", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
}));

jest.mock("next/navigation", () => ({
  useParams: () => ({ domain: "cycling", slug: "tour-de-france-2026" }),
  useRouter: () => ({ replace: () => {} }),
}));

jest.mock("@/hooks", () => ({
  usePageTracking: () => {},
  useScrollDepth: () => {},
  useEngagementTime: () => {},
}));

// Key-aware swr: the "event-concept" tag returns the page envelope; anything else
// (the SettledPathChart's "event-settled-path" fetch) returns the resolved history.
jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    if (key == null) return { data: undefined, error: null, isLoading: false };
    const tag = Array.isArray(key) ? key[0] : key;
    if (tag === "event-concept")
      return { data: mockEnvelope, error: null, isLoading: false };
    return { data: mockHistory, error: null, isLoading: false };
  },
}));

jest.mock("@/lib/api", () => ({
  fetchEventConcept: () => Promise.resolve(null),
  fetchFuturesHistory: () => Promise.resolve(mockHistory),
  formatProbability: (p: number | null) => (p == null ? "—" : `${Math.round(p * 100)}%`),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
import FeedCard from "../../components/FeedCard";
import DiscoverCard from "../../components/DiscoverCard";
import EventConceptPage from "../../app/event/[domain]/[slug]/page";
import { FuturesChart } from "../../components/FuturesChart";

// ── 1. Feed card (Sports tab — ConceptFeedCard) ──
describe("Sunday rehearsal · Sports-tab feed card (ConceptFeedCard)", () => {
  test("settled marquee leads result-first: Pogačar named + Won + FINAL", () => {
    const html = renderToStaticMarkup(<FeedCard item={conceptFeedItem(SETTLED_CONCEPT)} />);
    expect(html).toContain("FINAL");
    expect(html).toContain("Tadej Pogačar");
    expect(html).toContain("Won");
    expect(html).toContain("by 3:24");
    // Result-first: the live-framing reason line is replaced by the result.
    expect(html).not.toContain("Stage 21 — the final ride into Paris");
  });

  test("live (unsettled) direction is unchanged — LIVE framing, no crown", () => {
    const html = renderToStaticMarkup(<FeedCard item={conceptFeedItem(LIVE_CONCEPT)} />);
    expect(html).toContain("LIVE");
    expect(html).not.toContain("FINAL");
    expect(html).not.toContain("Won");
  });
});

// ── 2. Feed card (Discover tab — the seam bug this rehearsal caught) ──
describe("Sunday rehearsal · Discover-tab feed card (DiscoverCard concept branch)", () => {
  test("settled marquee concept RENDERS (result-first) — not an empty card", () => {
    const html = renderToStaticMarkup(
      <DiscoverCard groupedItem={{ type: "single", item: conceptFeedItem(SETTLED_CONCEPT) }} />,
    );
    // The seam: before the ConceptCard branch, a concept item rendered nothing.
    expect(html).not.toBe("");
    expect(html).toContain("Tadej Pogačar");
    expect(html).toContain("Champion · Won");
    expect(html).toContain("Final");
    // Links to the canonical concept page.
    expect(html).toContain('href="/event/cycling/tour-de-france-2026"');
  });

  test("live (unsettled) concept renders its name, no crown", () => {
    const html = renderToStaticMarkup(
      <DiscoverCard groupedItem={{ type: "single", item: conceptFeedItem(LIVE_CONCEPT) }} />,
    );
    expect(html).toContain("Tour de France 2026");
    expect(html).toContain("Live");
    expect(html).not.toContain("Champion · Won");
  });
});

// ── 3. Concept page hero + leaderboard (settled → champion crowned, field frozen) ──
describe("Sunday rehearsal · concept page (EventConceptPage settled)", () => {
  beforeEach(() => {
    mockEnvelope = SETTLED_ENVELOPE;
    mockHistory = SETTLED_HISTORY;
  });

  test("renders the full settled stack without throwing: champion crowned, path chart hero, field frozen", () => {
    const html = renderToStaticMarkup(<EventConceptPage />);
    // Header — settled label.
    expect(html).toContain("Tour de France 2026");
    expect(html).toContain("Settled");
    // Hero for a settled winner-field is the completed-journey chart, NOT the live
    // race chart (L2-156 Item 5).
    expect(html).toContain("Path to resolution");
    expect(html).not.toContain("Race to the title");
    // Leaderboard crowns the authoritative champion once (settled-means-settled).
    expect(html).toContain("Final result");
    expect(html).toContain("Tadej Pogačar");
    expect(html).toContain("Won");
    // Exactly one crown — guards against a two-winner render (L2-89 lesson).
    expect(html.split("🏆").length - 1).toBe(1);
    // The field is frozen behind the dimmed "Did not win" group.
    expect(html).toContain("Did not win (2)");
  });

  test("the settled path chart plots the champion's line (winner threaded into the legend)", () => {
    const html = renderToStaticMarkup(<EventConceptPage />);
    // championName is threaded to /history so the winner's line leads the legend.
    expect(html).toContain("Path to resolution");
    // Chart mounted (fixed 0–100% axis renders the top gridline label).
    expect(html).toContain("100%");
    // Pogačar's line appears in the chart legend (drawn first, leader color).
    const legendCount = html.split("Tadej Pogačar").length - 1;
    expect(legendCount).toBeGreaterThanOrEqual(2); // leaderboard hero + chart legend
  });

  test("live (unsettled) direction is unchanged — race chart hero, live leaderboard", () => {
    mockEnvelope = LIVE_ENVELOPE;
    const html = renderToStaticMarkup(<EventConceptPage />);
    expect(html).toContain("Race to the title");
    expect(html).not.toContain("Path to resolution");
    expect(html).not.toContain("Final result");
    // A live winner-field shows probabilities.
    expect(html).toContain("%");
  });
});

// ── 4. The winner line resolves to ~100% (settled evolution chart) ──
describe("Sunday rehearsal · settled evolution chart resolves the winner to ~100%", () => {
  test("the champion's fixed-axis line rises to the 0–100% top (y = padding.top)", () => {
    // Render the same FuturesChart the SettledPathChart mounts (fixedYAxis +
    // stepInterpolation), champion selected. On a fixed 0–100% axis a probability
    // of 1.0 maps to the chart top (yScale(1.0) = padding.top = 20 at height 260).
    const html = renderToStaticMarkup(
      <FuturesChart
        historyData={[SETTLED_HISTORY.outcomes[0]]}
        selectedOutcomes={new Set([1])}
        fixedYAxis
        stepInterpolation
        showAxes
        showLegend
        height={260}
      />,
    );
    const match = html.match(/<path[^>]*\bd="([^"]+)"/);
    expect(match).not.toBeNull();
    const d = match![1];
    // Step path emits a `V <y>` per point; the champion's final point (prob 1.0)
    // must sit at the fixed-axis top.
    const vYs = [...d.matchAll(/V\s+([\d.]+)/g)].map((m) => parseFloat(m[1]));
    expect(vYs.length).toBeGreaterThan(0);
    expect(Math.min(...vYs)).toBeCloseTo(20, 0);
  });
});
