// L2-184 — the confidence glyph (SignalBars, #490) must also render on the
// data-pure single-number FuturesCard *Variant B* (the no-image A/B treatment),
// at the same semantic footer location as Variant A. Guards both directions:
// present tier → glyph + explanation; absent tier → nothing extra. Also proves
// we actually exercised Variant B (data-card-variant="B") so the assertion can't
// silently pass on Variant A.

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

// Mirror the exposure-level A/B hash (FuturesCard.tsx): seed = session_id + id.
// With no session id set, jsdom localStorage returns null → "anon".
function abHash(seed: string): number {
  return Array.from(seed).reduce((h, c) => ((h << 5) - h + c.charCodeAt(0)) | 0, 0);
}
function isVariantB(id: number): boolean {
  return Math.abs(abHash(`anon_${id}`)) % 2 === 0;
}
// Pick a deterministic id that lands on Variant B (no image treatment).
function variantBId(): number {
  for (let id = 1; id < 100_000; id++) {
    if (isVariantB(id)) return id;
  }
  throw new Error("no Variant B id found");
}

// A plain single-number futures fixture: no discover_card format, so it falls
// through the multi-candidate kernels into the A/B variant branch. No image_url
// keeps Variant A/B purely data-driven; the A/B hash decides the layout.
function singleNumberData(tier: "high" | "moderate" | "low" | null): FeedFuturesData {
  return {
    id: variantBId(),
    name: "Will the incumbent win the 2026 election?",
    llm_sport_category: "politics",
    sport_name: "Politics",
    resolution_date: "2026-11-03T00:00:00Z",
    source: "kalshi",
    top_outcomes: [{ id: 1, name: "Yes", probability: 0.58, movement: 2.1 }],
    outcome_count: 2,
    volume_24h: 1_400_000,
    confidence_tier: tier,
  } as unknown as FeedFuturesData;
}

function itemFor(data: FeedFuturesData): FeedItem {
  return { type: "futures", score: 90, reason: "", headline: "", data } as unknown as FeedItem;
}

function render(tier: "high" | "moderate" | "low" | null): string {
  const data = singleNumberData(tier);
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

describe("FuturesCard Variant B confidence glyph", () => {
  it("actually exercises Variant B (guards the fixture)", () => {
    expect(isVariantB(variantBId())).toBe(true);
    expect(render("high")).toContain('data-card-variant="B"');
  });

  function expectGlyph(tier: "high" | "moderate" | "low", label: string) {
    const html = render(tier);
    expect(html).toContain('role="img"');
    expect(html).toContain(CONFIDENCE_TOOLTIP);
    expect(html).toContain(label);
    // Still the single-number Variant B card (title renders).
    expect(html).toContain("Will the incumbent win the 2026 election?");
  }

  it("renders the SignalBars glyph with its explanation when tier=high", () => {
    expectGlyph("high", "High confidence");
  });

  it("renders the SignalBars glyph with its explanation when tier=moderate", () => {
    expectGlyph("moderate", "Moderate confidence");
  });

  it("renders the SignalBars glyph with its explanation when tier=low", () => {
    expectGlyph("low", "Low confidence");
  });

  it("renders nothing extra (no glyph) when the tier is absent", () => {
    const html = render(null);
    expect(html).not.toContain('role="img"');
    expect(html).not.toContain(CONFIDENCE_TOOLTIP);
    // Card body still renders.
    expect(html).toContain("Will the incumbent win the 2026 election?");
    expect(html).toContain('data-card-variant="B"');
  });
});
