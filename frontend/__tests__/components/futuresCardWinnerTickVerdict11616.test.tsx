/** @jest-environment jsdom */

// #11616 W1-b: the FuturesCard winner tick follows the shared result contract.
//
// The `✓` read the raw `is_winner` bit while the row's own verdict, detail and
// the typeahead suggestion all refused a result for `(is_winner true,
// resolution_source null)` on an OPEN board — Shopper's R10 screenshot showed a
// green tick beside "First Contender 55%". The tick now draws only when
// `outcomeRowVerdict` says "won" wherever the payload carries the field;
// a payload that omits `resolution_source` (feed shapes) keeps today's
// behaviour, the same absent-is-not-null rule the verdict itself states.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import FuturesCard from "@/components/FuturesCard";
import type { FuturesMarket, FuturesOutcome } from "@/lib/types";

jest.mock("next/navigation", () => ({ useRouter: () => ({ push: jest.fn() }) }));
jest.mock("@/components/Analytics", () => ({ useAnalyticsContext: () => ({ track: jest.fn() }) }));

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
let host: HTMLDivElement;
let root: Root;
beforeEach(() => {
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => { act(() => root.unmount()); host.remove(); });

type Leg = Partial<FuturesOutcome> & { settlement_display?: { verdict: string; basis: string } };

function market(status: string, leader: Leg): FuturesMarket {
  const legs = [
    { id: 1, name: "First Contender", probability: 0.55, rendered_percent: 55, movement: null, rank: 1, ...leader },
    { id: 2, name: "Second Contender", probability: 0.45, rendered_percent: 45, movement: null, rank: 2, is_winner: false, resolution_source: null },
  ];
  return {
    id: 116160, name: "Winner tick probe", sport: "basketball_nba", sport_name: "NBA",
    category: "award", market_tier: 3, status, source: "kalshi", outcome_count: 2,
    top_outcomes: legs,
  } as unknown as FuturesMarket;
}

async function ticks(status: string, leader: Leg): Promise<number> {
  await act(async () => { root.render(<FuturesCard market={market(status, leader)} />); });
  return Array.from(host.querySelectorAll("span")).filter((s) => s.textContent === "✓").length;
}

test("an open board's raw winner flag with no grader draws no tick (R10)", async () => {
  expect(await ticks("open", { is_winner: true, resolution_source: null })).toBe(0);
  expect(host.textContent).toContain("55%");
});

test("an authoritative open winner keeps its tick", async () => {
  expect(await ticks("open", { is_winner: true, resolution_source: "api_settlement" })).toBe(1);
});

test("a supported resolved winner keeps its tick", async () => {
  expect(await ticks("resolved", { is_winner: true, resolution_source: "api_settlement" })).toBe(1);
});

test("a retracted grade draws no tick", async () => {
  expect(await ticks("resolved", { is_winner: true, resolution_source: "ungradeable_result" })).toBe(0);
});

test("a resolved result the contract calls unknown draws no tick", async () => {
  expect(await ticks("resolved", {
    is_winner: true, resolution_source: "api_settlement",
    settlement_display: { verdict: "unknown", basis: "nonterminal_stored_price" },
  })).toBe(0);
});

test("control: a payload that omits resolution_source keeps today's tick", async () => {
  const leader: Leg = { is_winner: true };
  expect(await ticks("open", leader)).toBe(1);
});
