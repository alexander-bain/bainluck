// LAT-P191 (#1636) — the rendered Variant A hero carries the responsive ladder.
//
// `heroSrcSet.test.ts` pins the ladder's arithmetic. This file pins that the
// ladder REACHES THE RENDER: a helper nobody wires into the <img> saves nobody
// any bytes, and a unit test of a pure function cannot tell the difference.
//
// ARM DISCIPLINE (P190b). The three CONTROLS below assert only things that were
// already true before this ship — the hero exists, carries the url, and is
// lazy. They must stay green with the `srcSet`/`sizes` props removed; their job
// is to prove this harness can still see the hero at all, so a red DETECTOR
// means "the ladder is missing", not "the fixture broke". Every assertion about
// `srcset` or `sizes` — attributes this ship ADDS — lives in its own detector.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import { FuturesCard } from "../../components/discover/FuturesCard";
import type { FeedItem, FeedFuturesData } from "@/lib/types";

// Mirror the exposure-level A/B hash (FuturesCard.tsx). SSR seed is "anon".
function abHash(seed: string): number {
  return Array.from(seed).reduce((h, c) => ((h << 5) - h + c.charCodeAt(0)) | 0, 0);
}
function isVariantB(id: number): boolean {
  return Math.abs(abHash(`anon_${id}`)) % 2 === 0;
}
function variantAId(): number {
  for (let id = 1; id < 100_000; id++) {
    if (!isVariantB(id)) return id;
  }
  throw new Error("no Variant A id found");
}

// Verbatim from a live /api/feed?limit=40, 2026-09-01.
const HERO_URL =
  "https://images.pexels.com/photos/16587315/pexels-photo-16587315.jpeg?auto=compress&cs=tinysrgb&h=650&w=940";
const FOREIGN_URL = "https://cdn.example.com/photos/16587315.jpg";

function futuresData(imageUrl: string | null): FeedFuturesData {
  return {
    id: variantAId(),
    name: "Will the incumbent win the 2026 election?",
    llm_sport_category: "politics",
    sport_name: "Politics",
    resolution_date: "2026-11-03T00:00:00Z",
    source: "kalshi",
    top_outcomes: [{ id: 1, name: "Yes", probability: 0.58, movement: 2.1 }],
    outcome_count: 2,
    volume_24h: 1_400_000,
    confidence_tier: "high",
    image_url: imageUrl,
  } as unknown as FeedFuturesData;
}

function render(imageUrl: string | null): string {
  const data = futuresData(imageUrl);
  return renderToStaticMarkup(
    <FuturesCard
      item={{ type: "futures", score: 90, reason: "", headline: "", data } as unknown as FeedItem}
      data={data}
      liked={false}
      setLiked={() => {}}
      trending={false}
    />,
  );
}

function heroTag(html: string): string {
  const tag = /<img[^>]*data-testid="futures-hero-image"[^>]*>/.exec(html)?.[0] ?? "";
  expect(tag).not.toBe("");
  return tag;
}

const esc = (u: string) => u.replace(/&/g, "&amp;");

describe("CONTROLS — green with or without the ladder", () => {
  it("renders Variant A (without this every other assertion here is vacuous)", () => {
    expect(isVariantB(variantAId())).toBe(false);
    expect(render(HERO_URL)).toContain('data-card-variant="A"');
  });

  it("the hero <img> exists and still carries the served url as `src`", () => {
    const tag = heroTag(render(HERO_URL));
    expect(tag).toContain(`src="${esc(HERO_URL)}"`);
  });

  it("the hero is still deferrable — LAT-P179's ship is not traded away for this one", () => {
    const tag = heroTag(render(HERO_URL));
    expect(tag).toContain('loading="lazy"');
    expect(tag).toContain('decoding="async"');
  });
});

describe("DETECTORS — the ladder reaches the rendered hero", () => {
  it("emits a `srcset` on the hero <img>", () => {
    expect(heroTag(render(HERO_URL))).toContain("srcSet=");
  });

  it("emits the `sizes` the Discover masonry needs, or the browser assumes 100vw", () => {
    // Without `sizes` a `w`-descriptor srcset defaults to 100vw, which on a
    // 1280px desktop asks for a 1280px raster for a 300px slot — heavier than
    // today. `sizes` is not decoration here; it IS the desktop saving.
    const tag = heroTag(render(HERO_URL));
    expect(tag).toContain('sizes="');
    expect(tag).toContain("(min-width: 1280px) 300px");
  });

  it("the ladder's widest rung is the very url in `src`", () => {
    const tag = heroTag(render(HERO_URL));
    const srcSet = /srcSet="([^"]*)"/.exec(tag)?.[1] ?? "";
    expect(srcSet).not.toBe("");
    expect(srcSet.endsWith(`${esc(HERO_URL)} 940w`)).toBe(true);
  });

  it("offers a rung small enough for the 300 CSS px desktop slot", () => {
    // The whole point of the ship. A ladder whose smallest rung is 700w leaves
    // the four-column desktop reader downloading essentially what they do now.
    const srcSet = /srcSet="([^"]*)"/.exec(heroTag(render(HERO_URL)))?.[1] ?? "";
    // ⚠️ Assert the ladder EXISTS first. Without this line the width parse of
    // an absent `srcset` yields [0], `min` is 0, and the detector passes with
    // the ship unwired — measured: it did, on the first control run.
    expect(srcSet).not.toBe("");
    const widths = srcSet.split(", ").map((e) => Number(/(\d+)w$/.exec(e)?.[1] ?? 0));
    expect(widths.length).toBeGreaterThan(1);
    expect(Math.min(...widths)).toBeLessThanOrEqual(300);
  });
});

describe("the ladder is not applied where it cannot be trusted", () => {
  it("a non-Pexels hero renders exactly as before — no srcset, no sizes", () => {
    const tag = heroTag(render(FOREIGN_URL));
    expect(tag).toContain(`src="${esc(FOREIGN_URL)}"`);
    expect(tag).not.toContain("srcSet=");
    expect(tag).not.toContain("sizes=");
  });

  it("NEGATIVE CONTROL — no image_url still means no <img> and no wasted request", () => {
    const html = render(null);
    expect(html).toContain('data-card-variant="A"');
    expect(html).not.toContain('data-testid="futures-hero-image"');
    expect(html).not.toContain('srcSet=');
  });
});
