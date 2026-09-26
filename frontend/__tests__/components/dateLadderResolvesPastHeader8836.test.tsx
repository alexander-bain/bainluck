/**
 * #8836: a date ladder's header does not print one rung's close as the card's.
 *
 * Production, 390px, 2026-09-26 14:57Z. Discover card "Will the U.S. confirm
 * that aliens exist?" (futures 109435, Kalshi KXALIENS, group
 * kalshi:KXALIENS-27). Header: "Resolves Jan 1, 2027". Rungs:
 *
 *     Before October        1%
 *     Before November       2%
 *     Before December       3%
 *     Before 2027           4%
 *     Before 2028          13%
 *     Before Jan 20, 2029  19%   <- highlighted
 *
 * Kalshi closes each rung on its own date (KXALIENS-27-29 closes
 * 2029-01-20T15:00Z); the served `resolution_date` is the Before-2027 rung's
 * close. The payload carries no per-rung close, so the header says nothing.
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

type Point = { label: string; probability: number; value: number; source?: string; direction?: string; unit?: string };

function render(points: Point[], resolutionDate: string): string {
  const data = {
    id: 109435,
    name: "Will the U.S. confirm that aliens exist?",
    llm_sport_category: "tech",
    sport_name: null,
    market_type: "quantity",
    status: "open",
    resolution_date: resolutionDate,
    top_outcomes: [...points]
      .sort((a, b) => b.probability - a.probability)
      .slice(0, 3)
      .map((p, i) => ({ id: i + 1, name: p.label, probability: p.probability, movement: null })),
    outcome_count: points.length,
    confidence_tier: "low",
    discover_card: { suggested_format: "threshold_heatmap", threshold_points: points },
  } as unknown as FeedFuturesData;
  const item = { type: "futures", score: 93, reason: "", headline: null, data } as unknown as FeedItem;
  return renderToStaticMarkup(
    <FuturesCard item={item} data={data} liked={false} setLiked={() => {}} trending={false} />,
  );
}

const date = (label: string, value: number, probability: number): Point => ({
  label,
  value,
  probability,
  source: "date_bucket",
  unit: "date",
  direction: "before",
});

/** The served `threshold_points`, verbatim off `/api/feed` at 15:1xZ. */
const aliens: Point[] = [
  date("Before October", 20261000, 0.01),
  date("Before November", 20261100, 0.015),
  date("Before December", 20261200, 0.025),
  date("Before 2027", 20270100, 0.044),
  date("Before 2028", 20280100, 0.125),
  date("Before Jan 20, 2029", 20290120, 0.185),
];
const SERVED_RESOLUTION = "2027-01-01T15:00:00+00:00";

describe("#8836 a date ladder's header never names one rung's close as the card's", () => {
  test("the production card prints no 'Resolves Jan 1, 2027' over rungs to 2029", () => {
    const html = render(aliens, SERVED_RESOLUTION);
    expect(html).toContain("Before Jan 20, 2029");
    expect(html).not.toContain("Jan 1, 2027");
    expect(html).not.toMatch(/Resolves/);
  });

  test("no orphan separator is left beside the confidence glyph", () => {
    const html = render(aliens, SERVED_RESOLUTION);
    expect(html).not.toMatch(/<span>·<\/span>/);
  });

  test("CONTROL: the same ladder whose served date IS its latest rung keeps its line", () => {
    const html = render(aliens, "2029-01-20T15:00:00+00:00");
    expect(html).toContain("Resolves Jan 20, 2029");
  });

  test("CONTROL: a venue closing the last rung the evening before its label's date keeps its line", () => {
    const html = render(aliens.slice(0, 5), "2027-12-31T23:59:00+00:00");
    expect(html).toMatch(/Resolves Dec 31, 2027/);
  });

  test("CONTROL: a comparator ladder is never read as dates", () => {
    const html = render(
      [
        { label: "Above 52", probability: 0.92, value: 52 },
        { label: "Above 58", probability: 0.88, value: 58 },
        { label: "Above 64", probability: 0.64, value: 64 },
      ],
      SERVED_RESOLUTION,
    );
    expect(html).toContain("Resolves Jan 1, 2027");
  });
});
