/**
 * #8647: a "when will it happen" card names the earliest date the market
 * calls more likely than not, not the latest date the card happened to draw.
 *
 * Production, 390px, 2026-09-25 16:20Z. Discover card "When will Anthropic
 * officially announce an IPO?" (futures 8430022, Kalshi). Every rung is a
 * cumulative "before this date" question, so chances rise down the ladder:
 *
 *     Before Nov 1, 2026    6%
 *     Before Dec 1, 2026   56%
 *     Before Jan 1, 2027   73%
 *     Before Feb 1, 2027   85%   <- highlighted
 *     More likely than not: Before Feb 1, 2027
 *
 * The caption took the LAST rung over 50% and the highlight took the HIGHEST
 * rung. Both rules were written for the comparator ladder, where chances fall
 * as the rungs climb. On this axis both land on the loosest question, and
 * "Feb 1" was only the eighth of ten rungs (the card draws eight).
 */
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

type Point = { label: string; probability: number; value: number; source?: string; direction?: string };

function ladderData(points: Point[], name: string): FeedFuturesData {
  return {
    id: 8430022,
    name,
    llm_sport_category: "economics",
    sport_name: "Economics",
    resolution_date: "2027-04-01T00:00:00Z",
    top_outcomes: [...points]
      .sort((a, b) => b.probability - a.probability)
      .slice(0, 3)
      .map((p, i) => ({ id: i + 1, name: p.label, probability: p.probability, movement: null })),
    outcome_count: points.length,
    volume_24h: 500_000,
    confidence_tier: "high",
    discover_card: { suggested_format: "threshold_heatmap", threshold_points: points },
  } as unknown as FeedFuturesData;
}

function render(points: Point[], name = "When will Anthropic officially announce an IPO?"): string {
  const data = ladderData(points, name);
  const item = { type: "futures", score: 90, reason: "", headline: "", data } as unknown as FeedItem;
  return renderToStaticMarkup(
    <FuturesCard item={item} data={data} liked={false} setLiked={() => {}} trending={false} />,
  );
}

/** The footer as the reader reads it: grey caption, then the accented rung label. */
function footerSentence(html: string): string | null {
  const m = html.match(
    /<span class="[^"]*text-text-secondary[^"]*">([^<]*)<\/span><span class="[^"]*text-accent-brand[^"]*">([^<]*)<\/span>/,
  );
  return m ? `${m[1]} ${m[2]}` : null;
}

/** Rungs drawn on the tinted inset row, which is how QuantityGroup marks the highlighted rung. */
function highlightedRungs(html: string): string[] {
  return Array.from(
    html.matchAll(/<div class="[^"]*bg-accent-brand\/\[0\.06\][^"]*" aria-label="([^"]*): [^"]*"/g),
    (m) => m[1],
  );
}

const date = (label: string, value: number, probability: number): Point => ({
  label,
  value,
  probability,
  source: "date_bucket",
  direction: "before",
});

/** The served payload's ten rungs, verbatim (probabilities off the wire at 16:20Z). */
const anthropicIpo: Point[] = [
  date("Before Oct 1, 2026", 20261001, 0.01),
  date("Before Oct 10, 2026", 20261010, 0.01),
  date("Before Oct 17, 2026", 20261017, 0.01),
  date("Before Oct 24, 2026", 20261024, 0.015),
  date("Before Nov 1, 2026", 20261101, 0.055),
  date("Before Dec 1, 2026", 20261201, 0.565),
  date("Before Jan 1, 2027", 20270101, 0.725),
  date("Before Feb 1, 2027", 20270201, 0.845),
  date("Before Mar 1, 2027", 20270301, 0.88),
  date("Before Apr 1, 2027", 20270401, 0.895),
];

describe("#8647 a date ladder names the earliest rung over even", () => {
  test("the production card captions Dec 1, not the last drawn rung", () => {
    const html = render(anthropicIpo);
    expect(footerSentence(html)).toBe("More likely than not: Before Dec 1, 2026");
  });

  test("the highlighted rung is the one the caption names", () => {
    expect(highlightedRungs(render(anthropicIpo))).toEqual(["Before Dec 1, 2026"]);
  });

  test("the answer does not depend on how many rungs the card draws", () => {
    // Same market, served with only its first seven rungs: before the fix the
    // caption moved to "Jan 1" with the cut; the answer the market gives did not move.
    const html = render(anthropicIpo.slice(0, 7));
    expect(footerSentence(html)).toBe("More likely than not: Before Dec 1, 2026");
    expect(highlightedRungs(html)).toEqual(["Before Dec 1, 2026"]);
  });

  test("CONTROL: a comparator ladder still names its last rung over even and marks its highest", () => {
    const html = render(
      [
        { label: "Above 52", probability: 0.92, value: 52 },
        { label: "Above 58", probability: 0.88, value: 58 },
        { label: "Above 64", probability: 0.64, value: 64 },
        { label: "Above 70", probability: 0.41, value: 70 },
      ],
      "Netflix App Downloads in September",
    );
    expect(footerSentence(html)).toBe("More likely than not: Above 64");
    expect(highlightedRungs(html)).toEqual(["Above 52"]);
  });

  test("CONTROL: an exclusive date ladder reads the same (one rung can clear even)", () => {
    const html = render(
      [
        date("Before 2027", 20270000, 0.58),
        date("2027", 20270100, 0.24),
        date("2029 or later", 20290100, 0.08),
      ],
      "When will Apple ship it?",
    );
    expect(footerSentence(html)).toBe("More likely than not: Before 2027");
    expect(highlightedRungs(html)).toEqual(["Before 2027"]);
  });

  test("CONTROL: a date ladder with no rung over even keeps no caption and marks its highest rung", () => {
    const html = render([
      date("Before Oct 1, 2026", 20261001, 0.02),
      date("Before Nov 1, 2026", 20261101, 0.11),
      date("Before Dec 1, 2026", 20261201, 0.3),
    ]);
    expect(html).not.toContain("More likely than not");
    expect(highlightedRungs(html)).toEqual(["Before Dec 1, 2026"]);
  });
});
