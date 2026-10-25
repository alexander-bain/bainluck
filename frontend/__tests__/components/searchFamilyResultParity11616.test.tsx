/** @jest-environment jsdom */
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import SearchFamilyCard from "@/components/SearchFamilyCard";
import { leaderOutcome } from "@/components/searchFamilyDisplay";
import type { FuturesFamily, FuturesMarket, FuturesOutcome } from "@/lib/types";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
const outcome = (patch: Partial<FuturesOutcome> = {}): FuturesOutcome => ({
  id: 1, name: "Victor", probability: null, movement: 0.3, is_winner: null,
  last_updated: null, resolution_source: null, american_odds: null, rank: null, rank_change_24h: null,
  probability_change_24h: null, opening_probability: null, opening_american_odds: null, ...patch,
});
const market = (rows: FuturesOutcome[], patch: Partial<FuturesMarket> = {}): FuturesMarket => ({
  id: 11616, name: "NBA MVP", status: "open", source: "kalshi", market_type: "field",
  top_outcomes: rows, outcome_count: rows.length, ...patch,
} as FuturesMarket);
let host: HTMLDivElement;
let root: Root;
beforeEach(() => { host = document.createElement("div"); document.body.append(host); root = createRoot(host); });
afterEach(() => { act(() => root.unmount()); host.remove(); });
function render(headline: FuturesMarket, members: FuturesMarket[] = []) {
  const family = { family_key: "nba", label: "Awards", headline, members, more_count: 0 } as FuturesFamily;
  act(() => root.render(<SearchFamilyCard family={family} />));
  return [...host.querySelectorAll("a")];
}
const results: [string, Partial<FuturesOutcome>, Partial<FuturesMarket>, string][] = [
  ["unpriced authoritative winner", { is_winner: true, resolution_source: "api_settlement" }, {}, "Won"],
  ["unpriced resolved loser", { is_winner: false, resolution_source: "api_settlement" }, { status: "resolved" }, "Lost"],
  ["unpriced explicit unknown", { settlement_display: { verdict: "unknown", basis: "nonterminal_stored_price" } }, { status: "resolved" }, "Result unknown"],
  ["priced explicit unknown", { probability: 0.5, is_winner: false, resolution_source: "api_settlement", settlement_display: { verdict: "unknown", basis: "nonterminal_stored_price" } }, { status: "resolved" }, "Result unknown"],
  ["legacy nonterminal Polymarket", { probability: 0.5, is_winner: false, resolution_source: "clob_authoritative" }, { status: "resolved", source: "polymarket" }, "Result unknown"],
  ["legacy terminal Polymarket winner", { probability: 1, is_winner: true, resolution_source: "clob_authoritative" }, { status: "resolved", source: "polymarket" }, "Won"],
  ["legacy terminal Polymarket loser", { probability: 0, is_winner: false, resolution_source: "clob_authoritative" }, { status: "resolved", source: "polymarket" }, "Lost"],
  ["explicit stored-price verdict without represented price", { is_winner: true, resolution_source: "clob_authoritative", settlement_display: { verdict: "won", basis: "terminal_stored_price" } }, { status: "resolved", source: "polymarket" }, "Won"],
  ["unpriced open-field elimination", { is_winner: false, resolution_source: "api_settlement" }, {}, "Out"],
];
test.each(results)("%s survives in headline and member without prediction or movement", (_label, patch, context, expected) => {
  const m = market([outcome(patch)], context);
  const original = JSON.stringify(m);
  const links = render(m, [{ ...m, id: 11617 }]);
  expect(links).toHaveLength(2);
  for (const [index, link] of links.entries()) {
    expect(link.textContent).toContain(`Victor${expected}`);
    expect(link.textContent).not.toMatch(/%|↑|↓/);
    expect(link.getAttribute("href")).toBe(`/futures/${11616 + index}`);
  }
  expect(JSON.stringify(m)).toBe(original);
});
test.each([null, "ungradeable_result", "unknown_source"])("unsupported unpriced grade %s is skipped", source => {
  const valid = outcome({ id: 2, name: "Shai", probability: 0.67 });
  const m = market([outcome({ is_winner: true, resolution_source: source }), valid]);
  expect(leaderOutcome(m)).toBe(valid);
  expect(render(m)[0].textContent).toContain("Shai67%");
  expect(host.textContent).not.toMatch(/Won|Lost|Result unknown/);
});
test.each([[0, "0%"], [0.006, "1%"], [0.994, "99%"], [0.999, ">99%"], [1, "100%"]] as const)("ordinary probability %s retains boundary label %s and movement", (probability, label) => {
  expect(render(market([outcome({ probability })]))[0].textContent).toContain(`Victor${label}↑30`);
});
test("wire order retains an unpriced supported result ahead of a priced sibling", () => {
  const first = outcome({ is_winner: true, resolution_source: "api_settlement" });
  const m = market([first, outcome({ id: 2, probability: 0.7 })]);
  expect(leaderOutcome(m)).toBe(first);
  expect(render(m)[0].textContent).toContain("VictorWon");
});
test("ladder still chooses its priced crossing; all-unpriced ladder retains its result", () => {
  const first = outcome({ name: "Above 3.50%", is_winner: true, resolution_source: "api_settlement" });
  const crossing = outcome({ id: 2, name: "Above 4.00%", probability: 0.6 });
  const m = market([first, crossing], { market_type: "ladder" });
  expect(leaderOutcome(m)).toBe(crossing);
  expect(leaderOutcome(market([first, { ...crossing, probability: null }], { market_type: "ladder" }))).toBe(first);
});
test("unknown contract on an open market does not override a live price", () => {
  expect(render(market([outcome({ probability: 0.4, settlement_display: { verdict: "unknown", basis: "nonterminal_stored_price" } })]))[0].textContent).toContain("Victor40%");
});
