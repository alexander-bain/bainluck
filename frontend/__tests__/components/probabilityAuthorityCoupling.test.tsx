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
