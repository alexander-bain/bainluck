/**
 * #13422 / Item 5 — Full-card date-ladder windowing around `betterThanEvenRung`
 * (matching iOS `HeatMapCardView.heatMapDrawnRungs`).
 */
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import { FuturesCard, heatmapShownCells } from "../../components/discover/FuturesCard";
import type { FeedItem, FeedFuturesData } from "@/lib/types";

type Point = {
  label: string;
  probability: number;
  value: number;
  unit?: string | null;
  source?: string | null;
  direction?: string | null;
};

const datePoint = (label: string, value: number, probability: number): Point => ({
  label,
  value,
  probability,
  unit: "date",
  source: "date_bucket",
});

function makeLadderMarket(
  id: number,
  name: string,
  points: Point[],
): { item: FeedItem; data: FeedFuturesData } {
  const outcomes = [...points]
    .sort((a, b) => b.probability - a.probability)
    .slice(0, 3)
    .map((p, i) => ({ id: i + 1, name: p.label, probability: p.probability, movement: null }));
  const data = {
    id,
    name,
    llm_sport_category: "politics",
    sport_name: "Politics",
    resolution_date: "2028-12-31T00:00:00Z",
    top_outcomes: outcomes,
    outcome_count: points.length,
    volume_24h: 100_000,
    confidence_tier: "high",
    discover_card: {
      suggested_format: "threshold_heatmap",
      threshold_points: points,
    },
  } as unknown as FeedFuturesData;
  const item = {
    type: "futures",
    score: 90,
    reason: "",
    headline: "",
    data,
  } as unknown as FeedItem;
  return { item, data };
}

function drawnRungLabels(html: string): string[] {
  return Array.from(
    html.matchAll(/<div class="[^"]*px-2 py-0\.5[^"]*" aria-label="([^"]*): [^"]*">/g),
    (m) => m[1],
  );
}

function highlightedRungs(html: string): string[] {
  return Array.from(
    html.matchAll(/<div class="[^"]*bg-accent-brand\/\[0\.06\][^"]*" aria-label="([^"]*): [^"]*">/g),
    (m) => m[1],
  );
}

function cardCaption(html: string): string | null {
  const m = html.match(
    /<span class="[^"]*text-text-secondary[^"]*">More likely than not:<\/span><span class="[^"]*text-accent-brand[^"]*">([^<]*)<\/span>/,
  );
  return m ? m[1] : null;
}

const IMPEACHMENT_112818_POINTS: Point[] = [
  datePoint("Before Jan 1, 2027", 20270101, 0.0075),
  datePoint("Before Feb 1, 2027", 20270201, 0.055),
  datePoint("Before Mar 1, 2027", 20270301, 0.105),
  datePoint("Before Apr 1, 2027", 20270401, 0.165),
  datePoint("Before May 1, 2027", 20270501, 0.25),
  datePoint("Before Jun 1, 2027", 20270601, 0.325),
  datePoint("Before Jul 1, 2027", 20270701, 0.365),
  datePoint("Before Aug 1, 2027", 20270801, 0.455),
  datePoint("Before Oct 1, 2027", 20271001, 0.505),
  datePoint("Before Jan 1, 2028", 20280101, 0.605),
];

describe("website full date-ladder 8-rung windowing (#8713 / #13422)", () => {
  afterEach(() => {
    jest.useRealTimers();
  });

  test("112818 10-rung impeachment card windows indices 2..9 so named Before Oct 1, 2027 rung is drawn, highlighted, and captioned", () => {
    const fixedNow = new Date("2026-11-26T18:00:00Z");
    jest.useFakeTimers().setSystemTime(fixedNow);
    const { item, data } = makeLadderMarket(112818, "Will the House impeach Trump?", IMPEACHMENT_112818_POINTS);

    const cells = heatmapShownCells(data, fixedNow);
    expect(cells).not.toBeNull();
    expect(cells!.map((c) => c.label)).toEqual([
      "Before Mar 1, 2027",
      "Before Apr 1, 2027",
      "Before May 1, 2027",
      "Before Jun 1, 2027",
      "Before Jul 1, 2027",
      "Before Aug 1, 2027",
      "Before Oct 1, 2027",
      "Before Jan 1, 2028",
    ]);

    const html = renderToStaticMarkup(
      <FuturesCard item={item} data={data} liked={false} setLiked={() => {}} trending={false} />,
    );
    expect(drawnRungLabels(html)).toEqual(cells!.map((c) => c.label));
    expect(cardCaption(html)).toBe("Before Oct 1, 2027");
    expect(highlightedRungs(html)).toEqual(["Before Oct 1, 2027"]);
  });

  test("windows early anchor at start 0..7 and middle/late anchor centered or end-clamped", () => {
    const fixedNow = new Date("2026-11-26T18:00:00Z");
    const points12: Point[] = Array.from({ length: 12 }, (_, idx) => {
      const month = String(idx + 1).padStart(2, "0");
      return datePoint(`2027-${month}-01`, Number(`2027${month}01`), 0.1);
    });

    // Anchor at index 1 -> start = max(0, 1 - 4) = 0 -> indices 0..7
    const earlyPoints = points12.map((p, idx) => (idx >= 1 ? { ...p, probability: 0.55 } : p));
    const earlyCells = heatmapShownCells(makeLadderMarket(1, "Early", earlyPoints).data, fixedNow)!;
    expect(earlyCells.map((c) => c.label)).toEqual(points12.slice(0, 8).map((p) => p.label));

    // Anchor at index 6 -> start = 6 - 4 = 2 -> indices 2..9
    const midPoints = points12.map((p, idx) => (idx >= 6 ? { ...p, probability: 0.55 } : p));
    const midCells = heatmapShownCells(makeLadderMarket(2, "Mid", midPoints).data, fixedNow)!;
    expect(midCells.map((c) => c.label)).toEqual(points12.slice(2, 10).map((p) => p.label));

    // Anchor at index 11 -> start = min(7, 12 - 8) = 4 -> indices 4..11
    const endPoints = points12.map((p, idx) => (idx === 11 ? { ...p, probability: 0.65 } : p));
    const endCells = heatmapShownCells(makeLadderMarket(3, "End", endPoints).data, fixedNow)!;
    expect(endCells.map((c) => c.label)).toEqual(points12.slice(4, 12).map((p) => p.label));
  });

  test("preserves passed-rung skip when anchor >= 50% was already past and later upcoming rung is past index 7", () => {
    const fixedNow = new Date("2026-11-26T18:00:00Z");
    const pointsWithPassed: Point[] = [
      datePoint("Before Nov 1, 2026", 20261101, 0.55),
      ...IMPEACHMENT_112818_POINTS.slice(0, 9), // total 10 rungs; upcoming >=50% is rung 9 Before Oct 1, 2027
    ];
    const cells = heatmapShownCells(makeLadderMarket(4, "Skipped passed", pointsWithPassed).data, fixedNow)!;
    expect(cells).toHaveLength(8);
    expect(cells.map((c) => c.label)).toContain("Before Oct 1, 2027");
    expect(cells[0].label).toBe("Before Feb 1, 2027");
  });

  test("leaves <= 8 date rungs, all-below-50% date ladders, and non-date ladders at first 8", () => {
    const fixedNow = new Date("2026-11-26T18:00:00Z");

    const eightDate = IMPEACHMENT_112818_POINTS.slice(2);
    expect(heatmapShownCells(makeLadderMarket(5, "Eight", eightDate).data, fixedNow)!.map((c) => c.label)).toEqual(
      eightDate.map((p) => p.label),
    );

    const lowDate = IMPEACHMENT_112818_POINTS.map((p) => ({ ...p, probability: 0.2 }));
    expect(heatmapShownCells(makeLadderMarket(6, "Low", lowDate).data, fixedNow)!.map((c) => c.label)).toEqual(
      lowDate.slice(0, 8).map((p) => p.label),
    );

    const comparator10: Point[] = Array.from({ length: 10 }, (_, idx) => ({
      label: `Above ${50 + idx}`,
      value: 50 + idx,
      probability: idx === 9 ? 0.6 : 0.2,
      unit: null,
      source: "outcome",
    }));
    expect(heatmapShownCells(makeLadderMarket(7, "Comp", comparator10).data, fixedNow)!.map((c) => c.label)).toEqual(
      comparator10.slice(0, 8).map((p) => p.label),
    );
  });
});
