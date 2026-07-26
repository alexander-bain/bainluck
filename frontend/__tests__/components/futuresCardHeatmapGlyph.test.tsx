// L2-183 — the confidence glyph (SignalBars, #490) must also render on the
// threshold_heatmap variant of FuturesCard (a multi-candidate "by WHEN" ladder),
// which was the last multi-candidate web kernel still missing it. Guards both
// directions: present tier → glyph + explanation; absent tier → nothing extra.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import { FuturesCard } from "../../components/discover/FuturesCard";
import { CONFIDENCE_TOOLTIP } from "@/lib/confidence";
import type { FeedItem, FeedFuturesData } from "@/lib/types";

function heatmapData(tier: "high" | "moderate" | "low" | null): FeedFuturesData {
  return {
    id: 77,
    name: "When will the Fed cut rates?",
    llm_sport_category: "economics",
    sport_name: "Economics",
    resolution_date: "2026-12-31T00:00:00Z",
    top_outcomes: [
      { id: 1, name: "Sep 2026", probability: 0.62, movement: null },
      { id: 2, name: "Dec 2026", probability: 0.24, movement: null },
      { id: 3, name: "2027 or later", probability: 0.14, movement: null },
    ],
    outcome_count: 3,
    volume_24h: 900_000,
    confidence_tier: tier,
    discover_card: {
      suggested_format: "threshold_heatmap",
      threshold_points: [
        { label: "Sep 2026", probability: 0.62, value: 1 },
        { label: "Dec 2026", probability: 0.24, value: 2 },
        { label: "2027 or later", probability: 0.14, value: 3 },
      ],
    },
  } as unknown as FeedFuturesData;
}

function itemFor(data: FeedFuturesData): FeedItem {
  return { type: "futures", score: 90, reason: "", headline: "", data } as unknown as FeedItem;
}

function render(tier: "high" | "moderate" | "low" | null): string {
  const data = heatmapData(tier);
  return renderToStaticMarkup(
    <FuturesCard
      item={itemFor(data)}
      data={data}
      liked={false}
      setLiked={() => {}}
      trending={false}
    />,
  );
}

describe("FuturesCard threshold_heatmap confidence glyph", () => {
  it("renders the SignalBars glyph with its explanation when a tier is present", () => {
    const html = render("moderate");
    expect(html).toContain('role="img"');
    expect(html).toContain(CONFIDENCE_TOOLTIP);
    expect(html).toContain("Moderate confidence");
    // Still the heatmap kernel (its labels render).
    expect(html).toContain("Sep 2026");
  });

  it("renders nothing extra (no glyph) when the tier is absent", () => {
    const html = render(null);
    expect(html).not.toContain('role="img"');
    expect(html).not.toContain(CONFIDENCE_TOOLTIP);
    expect(html).toContain("Sep 2026");
  });
});
