import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { FeedFuturesData, FeedItem } from "@/lib/types";
import { rottenTomatoesComparison } from "@/lib/discover/rottenTomatoesComparison";

jest.mock("next/navigation", () => ({ useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }) }));
jest.mock("next/link", () => ({ __esModule: true, default: ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a> }));
jest.mock("next/image", () => ({ __esModule: true, default: ({ alt }: { alt: string }) => <img alt={alt} /> }));
jest.mock("@/components/Analytics", () => ({ useAnalyticsContext: () => ({ track: () => {} }) }));

import DiscoverCard from "@/components/DiscoverCard";

// Retained September30 market names and prices from #9803. This fixture is a
// reconstruction of the feed shape, not current supply, outcome-ID evidence or
// provider settlement-equivalence proof. IDs below identify the actual markets.
function film(id: number, name: string, probabilities: number[]): FeedItem {
  return {
    type: "futures", score: 75, reason: "", headline: null,
    data: {
      id, name: `${name} · Rotten Tomatoes score`, status: "open",
      llm_sport_category: "entertainment", source: "kalshi", source_count: 1,
      resolution_date: "2027-12-31T00:00:00Z", price_observed_at: null,
      top_outcomes: [{ id: id + 1, name: "Above 45", probability: probabilities[0], movement: null }],
      outcome_count: probabilities.length,
      discover_card: {
        comparison_theme: "rotten_tomatoes_scores", suggested_format: "threshold_heatmap",
        threshold_points: probabilities.map((probability, i) => ({
          source: "outcome", label: `Above ${45 + i * 5}`, value: 45 + i * 5,
          direction: "above", unit: "", probability,
        })),
      },
    },
  } as unknown as FeedItem;
}
function films() {
  return [
    film(58728375, "Clayface", [.945, .925, .875, .825, .705, .655, .555, .425, .245, .065]),
    film(60653755, "The Social Reckoning", [.935, .875, .805, .725, .645, .515, .375, .255, .125, .055]),
  ];
}
function card(items: FeedItem[]): FeedItem {
  return { type: "bundle", score: 75, reason: "", data: {
    id: "comparison:rotten_tomatoes_scores:58728375-60653755", title: "Rotten Tomatoes score ranges",
    kind: "comparison", comparison_theme: "rotten_tomatoes_scores",
    shared_question: "Which of these lands best with the critics?",
    item_count: items.length, member_ids: items.map(i => (i.data as FeedFuturesData).id), items,
  } } as unknown as FeedItem;
}
function data(item: FeedItem): any { return item.data; }

test("the existing bundle renders aligned score columns, original numbers and both destinations", () => {
  const items = films();
  const before = JSON.stringify(items);
  const grid = rottenTomatoesComparison(items)!;
  expect(grid.columns.map(c => c.label)).toEqual(["Above 70", "Above 75", "Above 80"]);
  expect(grid.rows.map(r => r.points.map(p => p.probability))).toEqual([[.655, .555, .425], [.515, .375, .255]]);
  const html = renderToStaticMarkup(<DiscoverCard groupedItem={{ type: "single", item: card(items) }} />);
  expect(html).toContain("<table");
  expect(html).toContain("Forecasts for each score threshold");
  for (const label of ["Above 70", "Above 75", "Above 80", "66%", "56%", "43%", "52%", "38%", "26%"])
    expect(html).toContain(label);
  expect(html).toContain('href="/futures/58728375"');
  expect(html).toContain('href="/futures/60653755"');
  expect(html).toContain("Clayface · Rotten Tomatoes score");
  expect(html).toContain("The Social Reckoning · Rotten Tomatoes score");
  expect(html).not.toContain("lands best with the critics");
  expect(JSON.stringify(items)).toBe(before);
});

test.each(["inclusive", "audience", "dates", "missing", "invalid", "duplicate", "resolved", "other-theme", "coordinate-mismatch", "direction-mismatch"])("%s has no aligned grid and retains ordinary member rows", condition => {
  const items = films();
  const d = data(items[1]);
  const points = d.discover_card.threshold_points;
  if (condition === "direction-mismatch") points.forEach((p: any) => { p.direction = "below"; });
  if (condition === "coordinate-mismatch") points[0].value = 99;
  if (condition === "inclusive") points.forEach((p: any) => { p.label = `${p.value}+`; });
  if (condition === "audience") d.name = "Film · Rotten Tomatoes audience score";
  if (condition === "dates") points.forEach((p: any) => { p.source = "date_bucket"; });
  if (condition === "missing") delete d.discover_card;
  if (condition === "invalid") points.forEach((p: any) => { p.probability = NaN; });
  if (condition === "duplicate") points.push(points[0]);
  if (condition === "resolved") d.status = "resolved";
  if (condition === "other-theme") d.discover_card.comparison_theme = "commodity_ranges";
  expect(rottenTomatoesComparison(items)).toBeNull();
});

test("old cache and unknown shapes keep the existing rendered links", () => {
  const items = films();
  items.forEach(i => { delete data(i).discover_card; });
  const html = renderToStaticMarkup(<DiscoverCard groupedItem={{ type: "single", item: card(items) }} />);
  expect(html).not.toContain("<table");
  expect(html).toContain('href="/futures/58728375"');
  expect(html).toContain('href="/futures/60653755"');
});

test("null and unverified zero ladder prices cannot become a shared reading", () => {
  const items = films();
  for (const item of items) data(item).discover_card.threshold_points = data(item).discover_card.threshold_points.slice(0, 4);
  data(items[0]).discover_card.threshold_points[0].probability = null;
  data(items[1]).discover_card.threshold_points[1].probability = 0;
  const grid = rottenTomatoesComparison(items)!;
  expect(grid.columns.map(c => c.label)).toEqual(["Above 55", "Above 60"]);
  expect(grid.rows.flatMap(r => r.points).every(p => p.probability > 0)).toBe(true);
});

test("row order remains server order and input arrays are never sorted in place", () => {
  const items = films().reverse();
  const before = JSON.stringify(items);
  expect(rottenTomatoesComparison(items)!.rows.map(r => r.data.id)).toEqual([60653755, 58728375]);
  expect(JSON.stringify(items)).toBe(before);
});
