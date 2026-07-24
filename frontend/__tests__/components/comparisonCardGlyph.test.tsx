// L2-174 Item 2 — the confidence glyph (SignalBars, #490/L2-171) must render on
// the MULTI-CANDIDATE layout (World Series / election leaderboards → ComparisonCard),
// not just the image-led FuturesCard. confidence_tier is already in the payload; the
// glyph was simply never wired into this card. Guards both directions.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import { ComparisonCard } from "../../components/discover/ComparisonCard";
import { CONFIDENCE_TOOLTIP } from "@/lib/confidence";
import type { FeedItem, FeedFuturesData } from "@/lib/types";

function multiCandidateData(tier: "high" | "moderate" | "low" | null): FeedFuturesData {
  return {
    id: 42,
    name: "Who will win the 2026 World Series?",
    llm_sport_category: "baseball",
    sport_name: "MLB",
    resolution_date: "2026-11-01T00:00:00Z",
    top_outcomes: [
      { id: 1, name: "Dodgers", probability: 0.28, movement: null },
      { id: 2, name: "Yankees", probability: 0.19, movement: null },
      { id: 3, name: "Braves", probability: 0.12, movement: null },
      { id: 4, name: "Astros", probability: 0.1, movement: null },
    ],
    outcome_count: 30,
    volume_24h: 1_500_000,
    confidence_tier: tier,
  } as unknown as FeedFuturesData;
}

function itemFor(data: FeedFuturesData): FeedItem {
  return { type: "futures", score: 90, reason: "", headline: "", data } as unknown as FeedItem;
}

function render(tier: "high" | "moderate" | "low" | null): string {
  const data = multiCandidateData(tier);
  return renderToStaticMarkup(
    <ComparisonCard
      item={itemFor(data)}
      data={data}
      liked={false}
      setLiked={() => {}}
      trending={false}
    />,
  );
}

describe("ComparisonCard confidence glyph (multi-candidate)", () => {
  it("renders the SignalBars glyph with its explanation when a tier is present", () => {
    const html = render("high");
    expect(html).toContain('role="img"');
    expect(html).toContain(CONFIDENCE_TOOLTIP);
    expect(html).toContain("High confidence");
    // The card still shows its multi-candidate leader + market meta.
    expect(html).toContain("Dodgers");
    expect(html).toContain("markets");
  });

  it("renders nothing extra (no glyph) when the tier is absent", () => {
    const html = render(null);
    expect(html).not.toContain('role="img"');
    expect(html).not.toContain(CONFIDENCE_TOOLTIP);
    // The card itself still renders.
    expect(html).toContain("Dodgers");
  });
});
