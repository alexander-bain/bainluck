import { renderToStaticMarkup } from "react-dom/server";
import FuturesCard from "../../components/FuturesCard";
import type { FuturesMarket } from "../../lib/types";

function field(status: "open" | "resolved"): FuturesMarket {
  const resolved = status === "resolved";
  return {
    id: 227,
    name: "College Football Playoff field",
    source: "kalshi",
    sport: "americanfootball_ncaaf",
    sport_name: "NCAAF",
    category: "sports",
    llm_sport_category: "football",
    market_type: "playoff",
    market_tier: 1,
    status,
    mutually_exclusive: false,
    outcome_count: 2,
    resolution_date: null,
    updated_at: null,
    prices_updated_at: null,
    top_outcomes: ["Ohio State", "Oregon"].map((name, index) => ({
      id: 22700 + index,
      name,
      probability: resolved ? null : 0.68 - index * 0.02,
      american_odds: null,
      rank: null,
      movement: null,
      is_winner: resolved,
      resolution_source: resolved ? "api_settlement" : null,
    })),
  } as unknown as FuturesMarket;
}

function renderedText(market: FuturesMarket): string {
  return renderToStaticMarkup(<FuturesCard market={market} />)
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ");
}

test("the selected-field wire prints its confirmed results with every price withheld", () => {
  const text = renderedText(field("resolved"));
  expect(text).toContain("Ohio State");
  expect(text).toContain("Oregon");
  expect(text.match(/Won/g)).toHaveLength(2);
  expect(text).not.toMatch(/Lost|\d+%/);
});

test("the same shared card keeps probabilities for an open field", () => {
  const text = renderedText(field("open"));
  expect(text).toContain("Ohio State");
  expect(text).toMatch(/\d+%/);
  expect(text).not.toMatch(/Won|Lost/);
});
