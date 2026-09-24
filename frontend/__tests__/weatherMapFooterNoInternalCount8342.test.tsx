/**
 * #8342 — `/weather`'s temperature map footer stops printing "0 cross-source".
 *
 * Seen on production at 390px, 2026-09-24 04:10Z: the footer read
 * `42 cities shown · tap a pin for distribution` on the left and
 * `0 cross-source` on the right. A coverage count on the page body (notice 34),
 * structurally 0 while every city's `srcs` is ["polymarket"].
 *
 * The fixture makes TWO of three cities cross-source, so the removed span
 * would print "2 cross-source" — a zero-only fixture would let a restored span
 * pass any assertion that only looked for "0".
 *
 *   TZ=UTC npx jest --testPathPatterns=weatherMapFooterNoInternalCount8342
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MapCanvas from "@/components/weather/MapCanvas";
import type { CityData } from "@/components/weather/data";

function visibleText(markup: string): string {
  return markup
    .replace(/<[^>]*>/g, " ")
    .replace(/&middot;/g, "·")
    .replace(/\s+/g, " ")
    .trim();
}

function city(id: string, name: string, srcs: CityData["srcs"]): CityData {
  return {
    id,
    name,
    preferredX: 18.8,
    preferredY: 45.4,
    x: 18.8,
    y: 45.4,
    region: "Americas",
    srcs,
    marketId: 61500175,
    high: { unit: "F", mode: 78, dist: [{ label: "78°F", prob: 100, probability: 1 }] },
  };
}

const CITIES = [
  city("nyc", "New York", ["polymarket", "kalshi"]),
  city("la", "Los Angeles", ["polymarket", "kalshi"]),
  city("sea", "Seattle", ["polymarket"]),
];

function render(cities: CityData[]): string {
  return visibleText(
    renderToStaticMarkup(
      <MapCanvas cities={cities} selected="nyc" hover={null} onHover={() => {}} onSelect={() => {}} />,
    ),
  );
}

describe("#8342 · the map footer carries no internal count", () => {
  test("no 'cross-source' count, even when cities ARE cross-source", () => {
    const seen = render(CITIES);
    expect(seen).not.toMatch(/cross-source/i);
    expect(seen).not.toMatch(/\b2 cross/i);
  });

  test("the reader-facing half of the footer survives", () => {
    expect(render(CITIES)).toContain("3 cities shown · tap a pin for distribution");
  });
});
