// #8526 — Variant B (the no-photo half of the FuturesCard A/B split) printed its
// hero number with no label: production served "Which party will win the U.S.
// Senate?" (futures 108620) as a bare `61%` on Variant B while Variant A's scrim
// read "61% · Democratic Party". Both roots now print the same `heroOutcome`
// name under the number.
//
// Each case asserts it really rendered the variant it names, so a hash change
// cannot turn this into a Variant A test that passes for Variant A's reason.

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

// Mirror the exposure-level A/B hash (FuturesCard.tsx `computeVariantB`).
// jsdom has no `bainluck_session_id`, so the seed is "anon".
function isVariantB(id: number): boolean {
  const h = Array.from(`anon_${id}`).reduce((a, c) => ((a << 5) - a + c.charCodeAt(0)) | 0, 0);
  return Math.abs(h) % 2 === 0;
}
function idFor(wantB: boolean): number {
  for (let id = 1; id < 100_000; id++) if (isVariantB(id) === wantB) return id;
  throw new Error("no id found");
}

type Outcome = { id: number; name: string; probability: number; movement: number | null };

// The production specimen's shape (futures 108620, 2026-09-25 03:35Z).
const SENATE: Outcome[] = [
  { id: 1593959, name: "Democratic Party", probability: 0.605, movement: null },
  { id: 1593958, name: "Republican Party", probability: 0.385, movement: null },
];
const YES_MARKET: Outcome[] = [{ id: 1, name: "Yes", probability: 0.83, movement: null }];

function render(outcomes: Outcome[], opts: { variantB: boolean; name: string }): string {
  const data = {
    id: idFor(opts.variantB),
    name: opts.name,
    llm_sport_category: "politics",
    resolution_date: "2027-02-01T15:00:00Z",
    source: "kalshi",
    status: "open",
    top_outcomes: outcomes,
    outcome_count: outcomes.length,
    confidence_tier: "moderate",
    // Variant A draws its hero over the photo; B ignores the image either way.
    image_url: opts.variantB ? null : "https://images.pexels.com/photos/1/x.jpeg",
  } as unknown as FeedFuturesData;
  const item = {
    type: "futures",
    score: 94,
    reason: "",
    headline: "Democratic Party leads at 61%, up 21 points since Feb 18",
    data,
  } as unknown as FeedItem;
  return renderToStaticMarkup(
    <FuturesCard item={item} data={data} liked={false} setLiked={() => {}} trending={false} />,
  );
}

// The label must sit between the hero number and the title, which is the
// place Variant A puts it. A match anywhere else (the caption) does not count.
function labelUnderHero(html: string): string | null {
  const hero = html.indexOf('data-testid="futures-hero-probability"');
  const title = html.indexOf("<h3");
  if (hero < 0 || title < 0) return null;
  const between = html.slice(hero, title);
  const m = between.match(/data-testid="futures-hero-outcome"[^>]*>([^<]*)</);
  return m ? m[1] : null;
}

describe("#8526 — Variant B names whose number it prints", () => {
  it("the Senate race: Variant B prints 'Democratic Party' under 61%", () => {
    const html = render(SENATE, { variantB: true, name: "Which party will win the U.S. Senate?" });
    expect(html).toContain('data-card-variant="B"');
    expect(html).toMatch(/data-testid="futures-hero-probability"[^>]*>61%</);
    expect(labelUnderHero(html)).toBe("Democratic Party");
  });

  it("a yes/no market: Variant B prints 'Yes', as Variant A does", () => {
    const html = render(YES_MARKET, { variantB: true, name: "Will François Hollande announce?" });
    expect(html).toContain('data-card-variant="B"');
    expect(labelUnderHero(html)).toBe("Yes");
  });

  it("both variants print the same label for the same market", () => {
    const b = render(SENATE, { variantB: true, name: "Which party will win the U.S. Senate?" });
    const a = render(SENATE, { variantB: false, name: "Which party will win the U.S. Senate?" });
    expect(a).toContain('data-card-variant="A"');
    // Variant A's label is the scrim line after its hero number.
    const aHero = a.indexOf('data-testid="futures-hero-probability"');
    expect(a.slice(aHero, a.indexOf("<h3"))).toContain(">Democratic Party<");
    expect(labelUnderHero(b)).toBe("Democratic Party");
  });

  it("no number, no label: an empty field prints neither", () => {
    const html = render([], { variantB: true, name: "Which party will win the U.S. Senate?" });
    expect(html).toContain('data-card-variant="B"');
    expect(html).not.toContain('data-testid="futures-hero-probability"');
    expect(html).not.toContain('data-testid="futures-hero-outcome"');
  });
});
