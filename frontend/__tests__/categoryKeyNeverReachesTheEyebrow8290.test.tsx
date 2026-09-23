/**
 * #8290 — an `llm_sport_category` key never reaches a reader raw.
 *
 * Specimen: production `GET /api/futures/59939103` serves `sport_name: null`,
 * `llm_sport_category: "table_tennis"`. The futures hero printed `TABLE_TENNIS`.
 * The same `||` chain fed the share card and `FuturesCard`'s sport eyebrow.
 */
import React from "react";
import fs from "fs";
import path from "path";
import { renderToStaticMarkup } from "react-dom/server";
import FuturesCard from "@/components/FuturesCard";
import { categoryKeyLabel } from "@/lib/sportCategories";
import type { FuturesMarket, FuturesOutcome } from "@/lib/types";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

function outcome(id: number, name: string, probability: number): FuturesOutcome {
  return {
    id,
    name,
    probability,
    american_odds: null,
    rank: null,
    rank_change_24h: null,
    probability_change_24h: null,
    movement: null,
    opening_probability: null,
    opening_american_odds: null,
    is_winner: null,
    last_updated: null,
  } as unknown as FuturesOutcome;
}

const SPECIMEN_59939103 = {
  id: 59939103,
  name: "W15 Cap d'Agde: Kayla Lorrimer vs Tatsiana Sasnouskaya",
  description: null,
  source: "polymarket",
  category: "championship",
  sport: null,
  sport_name: null,
  llm_sport_category: "table_tennis",
  external_id: null,
  mutually_exclusive: true,
  commence_time: null,
  resolution_date: null,
  outcome_count: 2,
  created_at: null,
  updated_at: null,
  status: "open",
  outcomes: [outcome(1, "Kayla Lorrimer", 0.6), outcome(2, "Tatsiana Sasnouskaya", 0.4)],
} as unknown as FuturesMarket;

describe("#8290 categoryKeyLabel", () => {
  it("reads the specimen's key as English", () => {
    expect(categoryKeyLabel("table_tennis")).toBe("Table Tennis");
  });

  it("uses the category map's own name where it has one", () => {
    expect(categoryKeyLabel("horse_racing")).toBe("Horse Racing");
  });

  it("never returns an underscore, for a key missing from the map", () => {
    expect(categoryKeyLabel("underwater_basket_weaving")).toBe("Underwater Basket Weaving");
  });

  it.each([null, undefined, "", "   "])("returns undefined for %p so the caller's fallback runs", (k) => {
    expect(categoryKeyLabel(k as string | null | undefined)).toBeUndefined();
  });
});

describe("#8290 FuturesCard's sport eyebrow on the specimen", () => {
  it("prints Table Tennis, not table_tennis", () => {
    const html = renderToStaticMarkup(<FuturesCard market={SPECIMEN_59939103} />);
    expect(html).toContain("Table Tennis");
    expect(html).not.toContain("table_tennis");
  });
});

describe("#8290 the futures page and its share card route the key through the helper", () => {
  const read = (f: string) =>
    fs.readFileSync(path.join(__dirname, "..", "app", "futures", "[id]", f), "utf8");

  it("page.tsx: the hero's categoryLabel never falls back to the raw key", () => {
    const src = read("page.tsx");
    expect(src).toContain(
      "categoryLabel={market.sport_name || categoryKeyLabel(market.llm_sport_category)}",
    );
    expect(src).not.toMatch(/categoryLabel=\{market\.sport_name \|\| market\.llm_sport_category/);
  });

  it("opengraph-image.tsx: the card's label never falls back to the raw key", () => {
    const src = read("opengraph-image.tsx");
    expect(src).toContain("categoryKeyLabel(market.llm_sport_category)");
    expect(src).not.toMatch(/market\.sport_name \|\| market\.llm_sport_category/);
  });
});
