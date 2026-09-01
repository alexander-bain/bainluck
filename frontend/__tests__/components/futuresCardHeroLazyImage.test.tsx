// LAT-P179 (#1636 family / GO-2026-08-31-B Priority 2 — COLD LOADS) — the
// Variant A hero must be a lazy <img>, never a CSS background.
//
// THE DEFECT THIS PINS. The image-led card used to paint its photo with
// `style={{ background: `url(${image_url}) center/cover` }}`. A CSS background
// image is structurally un-deferrable: there is no `loading="lazy"` for it, the
// browser cannot skip it, and it is fetched for every mounted card. A cold
// Discover load mounts PAGE_SIZE = 20 cards at once (app/discover/page.tsx:580)
// while roughly two are above the fold, so ~18 off-screen photos were pulled
// from images.pexels.com at low priority, competing for bandwidth. Measured on
// the live feed 2026-09-01: 27 of 40 items carry an `image_url`, mean 33.7 KB
// (h=350) / 73.2 KB (h=650&w=940). That is what kept the cold load's last-byte
// `finish` at 10,508 ms while the `load` event fired at 983 ms
// (ARTIFACT-FABLE-COLD-LOAD-20260831.md, FINDING 2 — the tail resource was a
// Pexels photo that did not *start* until 10,449 ms).
//
// Both directions per gotcha #43:
//   - image present  -> a real <img loading="lazy"> carrying the url, and NO
//                       `background:url(` anywhere in the card;
//   - image absent   -> the category gradient still paints and NO <img> appears
//                       (so the fix cannot have introduced an empty request).
// Plus a fixture guard that we truly rendered Variant A, because every
// assertion below is vacuous on Variant B (which has no hero at all).

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

// A real url from the live feed, kept verbatim so the assertion is about the
// value the backend actually serves rather than a shape we invented.
const HERO_URL =
  "https://images.pexels.com/photos/16082426/pexels-photo-16082426.jpeg?auto=compress&cs=tinysrgb&h=650&w=940";

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

describe("FuturesCard Variant A hero — lazy <img>, never a CSS background", () => {
  it("actually exercises Variant A (guards the fixture — every other assertion is vacuous on B)", () => {
    expect(isVariantB(variantAId())).toBe(false);
    expect(render(HERO_URL)).toContain('data-card-variant="A"');
  });

  it("renders the hero as an <img> that the browser is allowed to defer", () => {
    const html = render(HERO_URL);

    // The element exists and carries the real url.
    expect(html).toContain('data-testid="futures-hero-image"');
    expect(html).toContain(`src="${HERO_URL.replace(/&/g, "&amp;")}"`);

    // The three attributes that make an off-screen hero free. `loading="lazy"`
    // is the whole ship: without it the browser fetches all ~18 below-the-fold
    // photos during the cold load exactly as the CSS background did.
    const img = /<img[^>]*data-testid="futures-hero-image"[^>]*>/.exec(html)?.[0] ?? "";
    expect(img).not.toBe("");
    expect(img).toContain('loading="lazy"');
    expect(img).toContain('decoding="async"');

    // Decorative: the accessible name lives on the <article>, and the CSS
    // background this replaced carried none. An alt here would be a new
    // screen-reader announcement, not a restoration.
    expect(img).toContain('alt=""');
  });

  it("does NOT paint the photo as a CSS background anywhere in the card", () => {
    // THE REGRESSION GUARD. This is the assertion that fails if anyone
    // reintroduces `background: url(...)` — including as a "placeholder" or a
    // belt-and-braces duplicate, which would silently restore the eager fetch
    // while the <img> above still passed.
    const html = render(HERO_URL);
    expect(html).not.toMatch(/background:\s*url\(/i);
    expect(html).not.toContain(HERO_URL.replace(/&/g, "&amp;") + ") center/cover");
  });

  // ⚠️ Assert the CATEGORY gradient by value, not `/linear-gradient/`. The scrim
  // overlay that sits above the hero prints `linear-gradient(to top, ...)` on
  // BOTH arms, so a generic match is satisfied by a sibling element and passes
  // against the pre-fix card too — measured: it did.
  const POLITICS_GRADIENT = "linear-gradient(135deg, #1e1b4b, #4338ca)";

  it("moves the category gradient onto the hero container, so a slow photo is not a blank box", () => {
    const html = render(HERO_URL);
    expect(html).toContain(POLITICS_GRADIENT);
  });

  it("NEGATIVE CONTROL — with no image_url there is no <img> and the gradient still renders", () => {
    const html = render(null);
    expect(html).toContain('data-card-variant="A"');
    expect(html).not.toContain('data-testid="futures-hero-image"');
    // An <img src=""> or src="null" would be a new, wasted request.
    expect(html).not.toContain('src=""');
    expect(html).not.toContain('src="null"');
    expect(html).toContain(POLITICS_GRADIENT);
  });
});
