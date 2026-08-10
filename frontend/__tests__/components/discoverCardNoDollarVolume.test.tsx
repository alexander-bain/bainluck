// Queue 309 Item 4 — no dollar volume on a Discover feed card.
//
// Standing rule, docs/design-system.md: "Dollar volume as social proof is
// banned too (ruling 2026-07-30): '$6.6M changed hands' framing violates the
// same thesis." FuturesCard and ComparisonCard were the two live leaks.
//
// This is not in tension with ruling 011 ("well-traded" means volume evidence
// when present): that governs what counts as evidence for PUBLISHING a market.
// Volume keeps doing its job in ranking and gating — it stops being PRINTED as
// money. So every fixture below carries a large `volume_24h` on purpose: the
// data must still flow, and still render nothing.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import { FuturesCard } from "../../components/discover/FuturesCard";
import { ComparisonCard } from "../../components/discover/ComparisonCard";
import type { FeedItem, FeedFuturesData } from "@/lib/types";

const LOUD_VOLUME = 6_600_000; // the exact "$6.6M changed hands" the ruling names

function outcomes(n: number) {
  return Array.from({ length: n }, (_, i) => ({
    id: i + 1,
    name: `Candidate ${i + 1}`,
    probability: 0.5 - i * 0.07,
    movement: 1.4,
  }));
}

function futuresData(overrides: Partial<FeedFuturesData> = {}): FeedFuturesData {
  return {
    id: 7,
    name: "Who wins the 2026 election?",
    llm_sport_category: "politics",
    sport_name: "Politics",
    resolution_date: "2026-11-03T00:00:00Z",
    source: "kalshi",
    top_outcomes: outcomes(2),
    outcome_count: 2,
    volume_24h: LOUD_VOLUME,
    confidence_tier: "high",
    ...overrides,
  } as unknown as FeedFuturesData;
}

function itemFor(data: FeedFuturesData): FeedItem {
  return { type: "futures", score: 90, reason: "", headline: "", data } as unknown as FeedItem;
}

function renderFutures(data: FeedFuturesData): string {
  return renderToStaticMarkup(
    <FuturesCard item={itemFor(data)} data={data} liked={false} setLiked={() => {}} trending={false} />,
  );
}

function renderComparison(data: FeedFuturesData): string {
  return renderToStaticMarkup(
    <ComparisonCard item={itemFor(data)} data={data} liked={false} setLiked={() => {}} trending={false} />,
  );
}

// Both A/B variants are reachable by market id (hash of "anon_<id>"), and the
// heatmap variant by its suggested_format. Cover all three rather than whichever
// one this fixture happens to hash into.
const VARIANT_IDS = Array.from({ length: 24 }, (_, i) => i + 1);

const HEATMAP = futuresData({
  id: 99,
  discover_card: { suggested_format: "threshold_heatmap" },
  top_outcomes: [
    { id: 1, name: "Above 100", probability: 0.82 },
    { id: 2, name: "Above 200", probability: 0.61 },
    { id: 3, name: "Above 300", probability: 0.24 },
  ],
} as unknown as Partial<FeedFuturesData>);

const DISTRIBUTION = futuresData({
  id: 55,
  top_outcomes: outcomes(6),
  outcome_count: 6,
  discover_card: { suggested_format: "outcome_distribution" },
} as unknown as Partial<FeedFuturesData>);

describe("Item 4 — FuturesCard prints no dollar figure", () => {
  it.each(VARIANT_IDS)("market id %i (covers both A/B variants)", (id) => {
    const html = renderFutures(futuresData({ id }));
    expect(html).not.toContain("$");
    expect(html).not.toContain("vol");
  });

  it("the threshold-heatmap variant prints none either", () => {
    const html = renderFutures(HEATMAP);
    expect(html).not.toContain("$");
    expect(html).not.toContain(" vol");
  });

  it("keeps SignalBars — the confidence signal is not a dollar figure", () => {
    const withTier = renderFutures(futuresData({ confidence_tier: "high" } as Partial<FeedFuturesData>));
    expect(withTier).toContain('aria-label="High confidence');
  });

  it("keeps the resolve date on EVERY variant, now that it stands alone", () => {
    // `resolvesLabel` only speaks inside a 7-day window, so the fixture sits 3
    // days out. Asserted across enough ids to cover both A/B assignments.
    const soon = new Date(Date.now() + 72 * 36e5).toISOString();
    for (const id of VARIANT_IDS) {
      const html = renderFutures(futuresData({ id, resolution_date: soon }));
      expect(html).toContain("Closes");
      // Exactly once — Variant B prints it in its header, and the footer copy
      // that used to ride alongside the volume is gone rather than duplicated.
      expect(html.match(/Closes/g)).toHaveLength(1);
      // No orphaned separator pair left where the volume used to be.
      expect(html).not.toMatch(/>\s*·\s*<\/span>\s*<span[^>]*>\s*·/);
    }
  });

  it("renders no empty footer row when there is nothing left to say", () => {
    for (const id of VARIANT_IDS) {
      const bare = renderFutures(
        futuresData({ id, resolution_date: null, confidence_tier: null } as unknown as Partial<FeedFuturesData>),
      );
      expect(bare).not.toContain("·");
    }
  });
});

describe("Item 4 — ComparisonCard prints no dollar figure", () => {
  it("drops the ' · $N.NM vol' clause", () => {
    const html = renderComparison(DISTRIBUTION);
    expect(html).not.toContain("$");
    expect(html).not.toContain("vol");
  });

  it("keeps the market count", () => {
    const html = renderComparison(DISTRIBUTION);
    expect(html).toContain("6 markets");
  });

  it("keeps SignalBars", () => {
    const html = renderComparison(DISTRIBUTION);
    expect(html).toContain('aria-label="High confidence');
  });
});
