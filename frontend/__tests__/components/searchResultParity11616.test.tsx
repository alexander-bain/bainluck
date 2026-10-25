/** @jest-environment jsdom */

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import SearchBar from "@/components/SearchBar";
import MobileSearchOverlay from "@/components/MobileSearchOverlay";
import { fetchTypeahead } from "@/lib/api";
import type { TypeaheadOutcome, TypeaheadSuggestion } from "@/lib/api";
import { futuresAnswer } from "@/lib/searchSuggestionDisplay";
import { outcomeRowVerdict } from "@/lib/futuresOutcomeVerdict";
import { outcomeRowVerdict as detailVerdict } from "@/components/futures/OutcomeRow";

const mockPush = jest.fn();
const mockTrack = jest.fn();
jest.mock("next/navigation", () => ({ useRouter: () => ({ push: mockPush }) }));
jest.mock("@/components/Analytics", () => ({ useAnalyticsContext: () => ({ track: mockTrack }) }));
jest.mock("@/lib/api", () => ({
  ...jest.requireActual("@/lib/api"),
  fetchTypeahead: jest.fn(),
  fetchTrendingSearches: jest.fn().mockResolvedValue({ trending: [] }),
}));

function suggestion(outcome: Partial<TypeaheadOutcome>, status = "open"): TypeaheadSuggestion {
  return {
    type: "futures", text: "NBA MVP", market_id: 11616, status,
    top_outcomes: [{ name: "Victor", probability: null, movement: null, ...outcome }],
  };
}

const cases: [string, TypeaheadSuggestion, string][] = [
  ["unpriced authoritative winner", suggestion({ is_winner: true, resolution_source: "api_settlement", movement: 0.5 }), "Victor Won"],
  ["resolved loser", suggestion({ is_winner: false, resolution_source: "api_settlement" }, "resolved"), "Victor Lost"],
  ["unknown settled result", suggestion({ probability: 0.5, is_winner: false, resolution_source: "api_settlement", settlement_display: { verdict: "unknown", basis: "nonterminal_stored_price" } }, "resolved"), "Victor Result unknown"],
  ["unsettled near certainty", suggestion({ probability: 0.999, is_winner: false, resolution_source: null }), "Victor >99%"],
  ["real zero", suggestion({ probability: 0, is_winner: false, resolution_source: null }), "Victor 0%"],
];

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
let host: HTMLDivElement;
let root: Root;
beforeEach(() => {
  jest.useFakeTimers();
  localStorage.clear();
  sessionStorage.clear();
  mockPush.mockClear();
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => { act(() => root.unmount()); host.remove(); jest.useRealTimers(); });

describe.each(["desktop", "phone"] as const)("%s suggestion result parity", (surface) => {
  test.each(cases)("%s keeps the same destination and honest state", async (_label, row, expected) => {
    (fetchTypeahead as jest.Mock).mockResolvedValue({ query: "parity", suggestions: [row] });
    await act(async () => {
      root.render(surface === "desktop" ? <SearchBar /> : <MobileSearchOverlay isOpen onClose={() => {}} />);
    });
    // The phone overlay portals into document.body; query the mounted surface.
    const input = document.querySelector<HTMLInputElement>("input[placeholder='Search teams, games, futures...']")!;
    expect(input).not.toBeNull();
    act(() => {
      input.focus();
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, "parity");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => { jest.advanceTimersByTime(250); });
    const answer = document.querySelector("[data-testid='search-answer']")!;
    expect(answer).not.toBeNull();
    expect(answer.textContent).toBe(expected);
    if (!expected.includes("%")) expect(answer.textContent).not.toMatch(/%|↑|↓/);
    act(() => document.querySelector<HTMLElement>("[data-testid='search-suggestion']")!.click());
    expect(mockPush).toHaveBeenCalledWith("/futures/11616");
  });
});

test("detail and suggestions share the actual verdict function", () => {
  expect(detailVerdict).toBe(outcomeRowVerdict);
});

test.each([null, "ungradeable_result", "unknown_source"])("open winner with unsupported source %s is not crowned", (source) => {
  const row = suggestion({ probability: null, is_winner: true, resolution_source: source });
  expect(futuresAnswer(row)).toBeNull();
});

test("absent legacy grade fields retain prices; inputs are not mutated", () => {
  const row = suggestion({ probability: 0.67, movement: 0.03 });
  const original = JSON.stringify(row);
  expect(futuresAnswer(row)?.leader.displayValue).toBe("67%");
  expect(futuresAnswer(row)?.movement).toBe(0.03);
  expect(JSON.stringify(row)).toBe(original);
});

test("known result second row is retained beside a live prediction", () => {
  const row = suggestion({ probability: 0.4 });
  row.top_outcomes?.push({ name: "Shai", probability: null, movement: 0.2, is_winner: true, resolution_source: "api_settlement" });
  expect(futuresAnswer(row)?.second?.displayValue).toBe("Won");
});
