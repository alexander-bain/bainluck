// L2-199 — Discover A/B variant must be hydration-stable (C4 P2).
//
// The old FuturesCard read localStorage("bainluck_session_id") DURING RENDER:
// the server hashed "ssr_<id>" while the client hashed the real session, so
// server and first-client markup could pick structurally different card variants
// (React hydration mismatch), and a storage-access throw crashed the card
// subtree. The fix seeds a hydration-stable "anon" default for SSR AND the first
// client render, resolving the real session only in a post-mount effect.
//
// These tests prove the RENDER PATH no longer depends on storage (so SSR ===
// first hydration and blocked storage can't crash a card). Effects don't run
// under renderToStaticMarkup, which is exactly the first-paint markup we assert.

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

// Mirror the exposure hash so the test can predict the "anon"-seed variant.
function abHash(seed: string): number {
  return Array.from(seed).reduce((h, c) => ((h << 5) - h + c.charCodeAt(0)) | 0, 0);
}
function variantBFor(id: number, session: string): boolean {
  return Math.abs(abHash(`${session}_${id}`)) % 2 === 0;
}
function idWithAnon(target: boolean): number {
  for (let id = 1; id < 100_000; id++) {
    if (variantBFor(id, "anon") === target) return id;
  }
  throw new Error("no matching id");
}
// A session value that flips the anon assignment for `id` — the trap the old
// render-time read would fall into.
function sessionThatFlips(id: number, anonVariantB: boolean): string {
  for (let n = 0; n < 100_000; n++) {
    const s = `sess-${n}`;
    if (variantBFor(id, s) !== anonVariantB) return s;
  }
  throw new Error("no flipping session found");
}

function dataFor(id: number): FeedFuturesData {
  return {
    id,
    name: "Will the incumbent win the 2026 election?",
    llm_sport_category: "politics",
    sport_name: "Politics",
    resolution_date: "2026-11-03T00:00:00Z",
    source: "kalshi",
    top_outcomes: [{ id: 1, name: "Yes", probability: 0.58, movement: 2.1 }],
    outcome_count: 2,
    volume_24h: 1_400_000,
    confidence_tier: null,
  } as unknown as FeedFuturesData;
}
function itemFor(data: FeedFuturesData): FeedItem {
  return { type: "futures", score: 90, reason: "", headline: "", data } as unknown as FeedItem;
}
function render(data: FeedFuturesData): string {
  return renderToStaticMarkup(
    <FuturesCard item={itemFor(data)} data={data} liked={false} setLiked={() => {}} trending={false} />,
  );
}

describe("FuturesCard A/B hydration stability", () => {
  const realWindow = (global as { window?: unknown }).window;
  const realLocalStorage = (global as { localStorage?: unknown }).localStorage;

  afterEach(() => {
    (global as { window?: unknown }).window = realWindow;
    (global as { localStorage?: unknown }).localStorage = realLocalStorage;
    if (realWindow === undefined) delete (global as { window?: unknown }).window;
    if (realLocalStorage === undefined) delete (global as { localStorage?: unknown }).localStorage;
  });

  it("first-paint markup uses the hydration-stable 'anon' seed", () => {
    const bId = idWithAnon(true);
    const aId = idWithAnon(false);
    expect(render(dataFor(bId))).toContain('data-card-variant="B"');
    expect(render(dataFor(aId))).toContain('data-card-variant="A"');
  });

  it("render output is INVARIANT to the stored session (no SSR/client divergence)", () => {
    const bId = idWithAnon(true);
    const flip = sessionThatFlips(bId, true); // would pick Variant A under the old read
    // Simulate the client render environment: window + a populated session.
    (global as { window?: unknown }).window = {};
    (global as { localStorage?: unknown }).localStorage = {
      getItem: (k: string) => (k === "bainluck_session_id" ? flip : null),
      setItem: () => {},
      removeItem: () => {},
    };
    // Despite a session present that would flip the variant, the render still
    // uses the "anon" seed → server and first-hydration markup agree.
    expect(render(dataFor(bId))).toContain('data-card-variant="B"');
  });

  it("does not crash when localStorage access throws (blocked storage)", () => {
    const bId = idWithAnon(true);
    (global as { window?: unknown }).window = {};
    (global as { localStorage?: unknown }).localStorage = {
      getItem: () => {
        throw new Error("SecurityError: storage blocked");
      },
      setItem: () => {},
      removeItem: () => {},
    };
    expect(() => render(dataFor(bId))).not.toThrow();
    expect(render(dataFor(bId))).toContain('data-card-variant="B"');
  });

  it("is deterministic across renders for the same market", () => {
    const id = idWithAnon(true);
    const first = render(dataFor(id));
    const second = render(dataFor(id));
    expect(first).toBe(second);
  });
});
