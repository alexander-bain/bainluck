// UX-P052 (#1690) — display authority couples to the EXISTING SignalBars tier.
//
// The census finding: a card renders its leader % at full visual authority
// regardless of provenance, so "a single print, one source, 48h old" and a
// "3-source consensus 2 min ago" are indistinguishable at the same 62%. The
// bars already shipped — as a SIBLING of the number rather than something that
// governs how it is drawn.
//
// Both directions per gotcha #43, and the both-directions bar here is unusually
// load-bearing: this is a SUPPRESSION-shaped change to the one element the whole
// product exists to show. A bug that mutes a well-sourced number is worse than
// the gap being fixed, so "high renders byte-identically to before" is pinned as
// hard as "low mutes".

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import {
  probabilityAuthorityClass,
  PROBABILITY_AUTHORITY_CLASS,
} from "@/lib/confidence";
import { EventCard } from "../../components/discover/EventCard";
import type { FeedItem, FeedEventData } from "@/lib/types";

type Tier = "high" | "moderate" | "low" | null;

describe("probabilityAuthorityClass — the pure coupling", () => {
  it("leaves a high-confidence number at FULL authority", () => {
    expect(probabilityAuthorityClass("high")).toBe("");
  });

  it("mutes moderate, and mutes low strictly harder than moderate", () => {
    const moderate = probabilityAuthorityClass("moderate");
    const low = probabilityAuthorityClass("low");
    expect(moderate).not.toBe("");
    expect(low).not.toBe("");
    expect(low).not.toBe(moderate);
    // Monotonic: the tier order high > moderate > low must map to a strictly
    // decreasing opacity, or the glyph and the number can disagree.
    const opacityOf = (cls: string) => Number(/opacity-(\d+)/.exec(cls)?.[1] ?? 100);
    expect(opacityOf(PROBABILITY_AUTHORITY_CLASS.high)).toBeGreaterThan(
      opacityOf(PROBABILITY_AUTHORITY_CLASS.moderate)
    );
    expect(opacityOf(PROBABILITY_AUTHORITY_CLASS.moderate)).toBeGreaterThan(
      opacityOf(PROBABILITY_AUTHORITY_CLASS.low)
    );
  });

  it("does NOT mute when the tier is absent or unrecognised", () => {
    // "We did not measure this" must never render as "we doubt this" — that is a
    // stronger claim than the data supports, and the exact inversion #1690 fixes.
    for (const t of [null, undefined, "", "unknown", "HIGH"]) {
      expect(probabilityAuthorityClass(t as string | null | undefined)).toBe("");
    }
  });
});

function eventData(tier: Tier): FeedEventData {
  return {
    id: 15187586,
    sport: "baseball_mlb",
    sport_name: "MLB",
    sport_label: "MLB",
    home_team: "St.Louis Cardinals",
    away_team: "Philadelphia Phillies",
    commence_time: "2026-08-10T23:45:00+00:00",
    status: "live",
    home_score: 0,
    away_score: 2,
    // The live specimen this queue was measured on: a 45-point source spread
    // painted as a confident 68 / 32.
    win_probability_sources: {
      mlb: 0.341,
      espn: 0.677,
      polymarket: 0.715,
      stat_model: 0.2706,
    },
    current_odds: { home_probability: 0.677, away_probability: 0.323, source: "aggregate" },
    espn: { period: "Bottom 2nd" },
    confidence_tier: tier,
    confidence_signals: { sources_agree: false, has_closing_line: false },
  } as unknown as FeedEventData;
}

function renderEventCard(tier: Tier): string {
  const data = eventData(tier);
  const item = { type: "event", score: 35, reason: "", headline: "Live", data } as unknown as FeedItem;
  return renderToStaticMarkup(
    <EventCard
      item={item}
      data={data}
      liked={false}
      setLiked={() => {}}
      trending={false}
    />
  );
}

/** The class list on the home-probability span, which is the rendered answer. */
function homeProbabilityClass(html: string): string {
  const m = /<span class="([^"]*)"[^>]*data-testid="event-card-home-probability"/.exec(html);
  return m?.[1] ?? "";
}

describe("EventCard — the north-star 'read the probability' surface", () => {
  it("still paints the probability at every tier (coupling must never withhold)", () => {
    // The failure mode that would matter most: a styling coupling that
    // accidentally drops the number. The value is the product.
    for (const tier of ["high", "moderate", "low", null] as Tier[]) {
      const html = renderEventCard(tier);
      expect(html).toContain("68%");
      expect(html).toContain("32%");
    }
  });

  it("mutes a low-confidence number and does NOT mute a high-confidence one", () => {
    const high = homeProbabilityClass(renderEventCard("high"));
    const low = homeProbabilityClass(renderEventCard("low"));
    expect(high).toContain("font-bold");
    expect(high).not.toMatch(/opacity-/);
    expect(low).toContain("font-bold");
    expect(low).toContain(PROBABILITY_AUTHORITY_CLASS.low);
  });

  it("renders a tier-less card exactly as a high-confidence one", () => {
    // Byte-identical but for the tier data attribute — proof that the untiered
    // majority of cards are untouched by this change.
    const absent = homeProbabilityClass(renderEventCard(null));
    const high = homeProbabilityClass(renderEventCard("high"));
    expect(absent).toBe(high);
    expect(absent).not.toMatch(/opacity-/);
  });

  it("couples BOTH sides of the matchup, not just the favourite", () => {
    const html = renderEventCard("low");
    const away = /<span class="([^"]*)"[^>]*data-testid="event-card-away-probability"/.exec(html)?.[1] ?? "";
    expect(away).toContain(PROBABILITY_AUTHORITY_CLASS.low);
  });

  it("keeps the SignalBars glyph — the coupling supplements it, never replaces it", () => {
    // Silent styling is for the reader who never learns the vocabulary; the glyph
    // (and its aria-label) is what actually NAMES the tier to assistive tech.
    expect(renderEventCard("low")).toContain("Low confidence");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// UX-P059 (#1690) — the DISCOVER FUTURES HERO, which this suite never covered.
//
// THE HOLE. Everything above renders EventCard. But `FuturesCard` is what the
// Discover dispatcher routes most futures items to, and its two hero variants
// (`FuturesCard.tsx` Variant A image-led and Variant B data-pure) each apply
// `authorityClass` to the headline number. Neither was asserted anywhere, so both
// lines could be DELETED and CI would stay green — on the primary surface of the
// default landing page. `data-testid="futures-hero-probability"` exists precisely
// to be queried and nothing queried it.
//
// This is not a new coupling. #1690's coupling shipped in UX-P052; this pins it
// where it actually lives for most readers.
//
// NOT COVERED ON PURPOSE: the ladder/row percentages (ComparisonCard, heatmap
// rungs, compact rows) are uncoupled by an explicit recorded decision at
// FuturesCard.tsx:302-306 — "the finding (and the tier) is about the card's
// headline probability". Asserting them either way here would quietly convert a
// deliberate product decision into a test-enforced one; that call is Alex's.

import { FuturesCard } from "../../components/discover/FuturesCard";
import type { FeedFuturesData } from "@/lib/types";

// Mirror the exposure-level A/B hash (FuturesCard.tsx): seed = session_id + id.
// Under `testEnvironment: 'node'` there is no localStorage, so the seed is "anon".
function abHash(seed: string): number {
  return Array.from(seed).reduce((h, c) => ((h << 5) - h + c.charCodeAt(0)) | 0, 0);
}
/** A deterministic id landing on the requested variant, so BOTH heroes are exercised. */
function idForVariant(wantB: boolean): number {
  for (let id = 1; id < 100_000; id++) {
    if ((Math.abs(abHash(`anon_${id}`)) % 2 === 0) === wantB) return id;
  }
  throw new Error(`no id found for variant ${wantB ? "B" : "A"}`);
}

function futuresData(tier: Tier, wantB: boolean): FeedFuturesData {
  return {
    id: idForVariant(wantB),
    name: "Will the incumbent win the 2026 election?",
    llm_sport_category: "politics",
    sport_name: "Politics",
    resolution_date: "2026-11-03T00:00:00Z",
    source: "kalshi",
    top_outcomes: [{ id: 1, name: "Yes", probability: 0.62, movement: 2.1 }],
    outcome_count: 2,
    volume_24h: 1_400_000,
    confidence_tier: tier,
  } as unknown as FeedFuturesData;
}

function renderFuturesCard(tier: Tier, wantB: boolean): string {
  const data = futuresData(tier, wantB);
  const item = { type: "futures", score: 90, reason: "", headline: "", data } as unknown as FeedItem;
  return renderToStaticMarkup(
    <FuturesCard item={item} data={data} liked={false} setLiked={() => {}} trending={false} />
  );
}

/** The class list on the hero probability span — the rendered answer. */
function heroProbabilityClass(html: string): string {
  const m = /<span class="([^"]*)"[^>]*data-testid="futures-hero-probability"/.exec(html);
  return m?.[1] ?? "";
}

for (const [label, wantB] of [
  ["Variant B (data-pure)", true],
  ["Variant A (image-led)", false],
] as const) {
  describe(`FuturesCard hero — ${label}`, () => {
    it("actually rendered the variant under test, and rendered a hero at all", () => {
      // Non-vacuity twice over: every assertion below reads a regex capture that
      // silently yields "" if the testid is missing, and the A/B hash could
      // otherwise land us on the same variant for both passes.
      const html = renderFuturesCard("high", wantB);
      expect(html).toContain(`data-card-variant="${wantB ? "B" : "A"}"`);
      expect(html).toContain('data-testid="futures-hero-probability"');
      expect(heroProbabilityClass(html)).not.toBe("");
    });

    it("still paints the number at every tier (coupling must never withhold)", () => {
      for (const tier of ["high", "moderate", "low", null] as Tier[]) {
        expect(renderFuturesCard(tier, wantB)).toContain("62%");
      }
    });

    it("mutes a low-confidence hero and does NOT mute a high-confidence one", () => {
      const high = heroProbabilityClass(renderFuturesCard("high", wantB));
      const low = heroProbabilityClass(renderFuturesCard("low", wantB));
      expect(high).not.toMatch(/opacity-/);
      expect(low).toContain(PROBABILITY_AUTHORITY_CLASS.low);
      // The muting must be the ONLY difference — a coupling that also dropped the
      // font treatment would be a redesign smuggled in as a provenance signal.
      expect(low.replace(PROBABILITY_AUTHORITY_CLASS.low, "").trim()).toBe(high.trim());
    });

    it("mutes moderate strictly less than low", () => {
      const moderate = heroProbabilityClass(renderFuturesCard("moderate", wantB));
      expect(moderate).toContain(PROBABILITY_AUTHORITY_CLASS.moderate);
      expect(moderate).not.toContain(PROBABILITY_AUTHORITY_CLASS.low);
    });

    it("renders a tier-less hero exactly as a high-confidence one", () => {
      // "We did not measure this" must not render as "we doubt this".
      expect(heroProbabilityClass(renderFuturesCard(null, wantB))).toBe(
        heroProbabilityClass(renderFuturesCard("high", wantB))
      );
    });
  });
}
