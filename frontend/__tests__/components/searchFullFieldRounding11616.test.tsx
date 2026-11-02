import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "fs";
import { representedOutcomeRowPercents } from "@/lib/renderedPercent";
import { futuresAnswer } from "@/lib/searchSuggestionDisplay";
import FuturesCard from "@/components/FuturesCard";
import SearchFamilyCard from "@/components/SearchFamilyCard";
import type { FuturesMarket, FuturesFamily, FuturesOutcome } from "@/lib/types";

const rows = [
  { id: 1, name: "Victor", probability: 0.605, rendered_percent: 61 },
  { id: 2, name: "Shai", probability: 0.395, rendered_percent: 40 },
  { id: 3, name: "Nikola", probability: 0.2, rendered_percent: 20 },
].map(row => ({ ...row, movement: null, is_winner: null, resolution_source: null }));
const market = (outcomes: typeof rows): FuturesMarket => ({
  id: 11616, name: "Awards field", status: "open", source: "kalshi", market_type: "field",
  mutually_exclusive: false, outcome_count: 3, top_outcomes: outcomes as FuturesOutcome[],
} as FuturesMarket);
const text = (node: React.ReactElement) => renderToStaticMarkup(node)
  .replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();

test("a selected pair from a larger field retains its independent full-field integers", () => {
  for (const selection of [rows, rows.slice(0, 2), [rows[1], rows[0]], [rows[1]]]) {
    expect(representedOutcomeRowPercents(selection)).toEqual(selection.map(row => row.rendered_percent));
  }
  const visible = text(<FuturesCard market={market(rows.slice(0, 2))} />);
  expect(visible).toMatch(/Victor.*61%.*Shai.*40%/);
  expect(visible).not.toContain("39%");
});
test("family and typeahead consume the identical served integer for the selected outcome", () => {
  const selected = [rows[1], rows[0]];
  const family = { family_key: "awards", label: "Awards", headline: market(selected), members: [], more_count: 0 } as unknown as FuturesFamily;
  expect(text(<SearchFamilyCard family={family} />)).toMatch(/Shai 40%/);
  const answer = futuresAnswer({ type: "futures", text: "Awards", market_id: 11616, top_outcomes: selected });
  expect(answer?.leader.displayValue).toBe("40%");
  expect(answer?.second?.displayValue).toBe("61%");
});
test("an exclusive pair's canonical underdog integer survives a single-row suggestion", () => {
  const outcome = { ...rows[1], rendered_percent: 39 };
  expect(futuresAnswer({ type: "futures", text: "Awards", market_id: 11616, top_outcomes: [outcome] })?.leader.displayValue).toBe("39%");
});
test("legacy payloads retain pair fallback and malformed siblings do not start another pair", () => {
  expect(representedOutcomeRowPercents([{ probability: 0.605 }, { probability: 0.395 }])).toEqual([61, 39]);
  expect(representedOutcomeRowPercents([{ probability: 0.605, rendered_percent: 61 }, { probability: 0.395, rendered_percent: null }])).toEqual([61, null]);
  expect(representedOutcomeRowPercents([{ probability: 0, rendered_percent: 0 }, { probability: null, rendered_percent: null }])).toEqual([0, null]);
});
test("detail's current values consume the served decision while opening values retain their own rule", () => {
  const source = readFileSync("app/futures/[id]/page.tsx", "utf8");
  expect(source).toContain("const current = representedOutcomeRowPercents(outs)");
  expect(source).toContain("const opening = renderedOutcomeRowPercents(outs.map((o) => readableOpeningProbability(o)))");
  expect(source).toContain("current: current[i] ?? null");
});
