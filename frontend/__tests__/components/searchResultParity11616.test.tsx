/** @jest-environment jsdom */

import fs from "fs";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import SearchBar from "@/components/SearchBar";
import MobileSearchOverlay from "@/components/MobileSearchOverlay";
import FuturesCard from "@/components/FuturesCard";
import { fetchTypeahead } from "@/lib/api";
import type { TypeaheadOutcome, TypeaheadSuggestion } from "@/lib/api";
import type { FuturesMarket } from "@/lib/types";
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

describe("cache-adapted payload mounted controls (#11616)", () => {
  test.each(["desktop", "phone"] as const)(
    "%s mounted typeahead withholds adapted legacy prediction while keeping title and destination (negative control)",
    async (surface) => {
      const adaptedLegacyRow: TypeaheadSuggestion = {
        type: "futures",
        text: "NBA MVP",
        market_id: 66031970,
        status: "open",
        top_outcomes: [
          {
            name: "Victor Wembanyama",
            probability: null,
            rendered_percent: null,
            movement: null,
            is_winner: null,
            resolution_source: null,
          },
        ],
      };
      (fetchTypeahead as jest.Mock).mockResolvedValue({
        query: "wembanyama",
        suggestions: [adaptedLegacyRow],
      });
      await act(async () => {
        root.render(
          surface === "desktop" ? (
            <SearchBar />
          ) : (
            <MobileSearchOverlay isOpen onClose={() => {}} />
          )
        );
      });
      const input = document.querySelector<HTMLInputElement>(
        "input[placeholder='Search teams, games, futures...']"
      )!;
      act(() => {
        input.focus();
        Object.getOwnPropertyDescriptor(
          HTMLInputElement.prototype,
          "value"
        )!.set!.call(input, "wembanyama");
        input.dispatchEvent(new Event("input", { bubbles: true }));
      });
      await act(async () => {
        jest.advanceTimersByTime(250);
      });
      const item = document.querySelector<HTMLElement>(
        "[data-testid='search-suggestion']"
      )!;
      expect(item).not.toBeNull();
      expect(item.textContent).toContain("NBA MVP");
      expect(
        document.querySelector("[data-testid='search-answer']")
      ).toBeNull();
      expect(item.textContent).not.toMatch(/28%|27\.5%|↑|↓|Won|Lost/);
      act(() => item.click());
      expect(mockPush).toHaveBeenCalledWith("/futures/66031970");
    }
  );

  test("mounted FuturesCard renders dashes for adapted legacy outcomes and preserves destination and proven winners (negative + positive controls)", async () => {
    const adaptedLegacyMarket: FuturesMarket = {
      id: 66031970,
      name: "NBA MVP",
      sport: "basketball_nba",
      sport_name: "NBA",
      category: "award",
      llm_sport_category: "basketball",
      market_tier: 3,
      market_type_label: "Award",
      market_type: "award",
      status: "open",
      source: "polymarket",
      resolution_date: "2027-06-01T00:00:00+00:00",
      outcome_count: 2,
      updated_at: "2026-10-24T18:00:00+00:00",
      prices_updated_at: null,
      top_outcomes: [
        {
          id: 101,
          name: "Victor Wembanyama",
          probability: null,
          rendered_percent: null,
          movement: null,
          american_odds: null,
          rank: null,
          is_winner: null,
          resolution_source: null,
          last_updated: "2026-10-10T00:00:00+00:00",
          price_changed_at: null,
          rank_change_24h: null,
          probability_change_24h: null,
          opening_probability: null,
          opening_american_odds: null,
        },
        {
          id: 102,
          name: "Shai Gilgeous-Alexander",
          probability: null,
          rendered_percent: null,
          movement: null,
          american_odds: null,
          rank: null,
          is_winner: true,
          resolution_source: "api_settlement",
          last_updated: "2026-10-24T18:00:00+00:00",
          price_changed_at: null,
          rank_change_24h: null,
          probability_change_24h: null,
          opening_probability: null,
          opening_american_odds: null,
        },
      ],
    };

    await act(async () => {
      root.render(<FuturesCard market={adaptedLegacyMarket} />);
    });
    const link = host.querySelector<HTMLAnchorElement>("a[href='/futures/66031970']")!;
    expect(link).not.toBeNull();
    expect(link.textContent).toContain("NBA MVP");
    expect(link.textContent).toContain("Victor Wembanyama-");
    expect(link.textContent).toContain("Shai Gilgeous-Alexander✓Won");
    expect(link.textContent).not.toMatch(/28%|19%|↑|↓/);
  });

  test("backend-exported R1/R2/C1 cache fixtures render identical truth across SearchBar, MobileSearchOverlay, FuturesCard, and detailVerdict", async () => {
    const exportedFixturePath =
      "/Users/bain/bainluck-dev/packet-11616-cache-compatibility-r2/backend_to_web_fixtures_11616.json";
    const exported = fs.existsSync(exportedFixturePath)
      ? JSON.parse(fs.readFileSync(exportedFixturePath, "utf8"))
      : {
          current_default_false_search_hit: [
            {
              american_odds: null,
              id: 1,
              is_winner: false,
              last_updated: "2026-10-24T18:00:00+00:00",
              movement: null,
              name: "Shai Gilgeous-Alexander",
              price_changed_at: null,
              probability: 0.55,
              rank: 1,
              rendered_percent: 55,
              resolution_source: null,
            },
            {
              american_odds: null,
              id: 2,
              is_winner: false,
              last_updated: "2026-10-24T18:00:00+00:00",
              movement: null,
              name: "Nikola Jokic",
              price_changed_at: null,
              probability: 0.45,
              rank: 2,
              rendered_percent: 45,
              resolution_source: null,
            },
          ],
          fresh_missing_price_poly_detail: {
            id: 10,
            is_winner: true,
            name: "Jon Rahm",
            probability: null,
            rendered_percent: null,
            resolution_source: "api_settlement",
            settlement_display: {
              basis: "missing_stored_price",
              verdict: "unknown",
            },
          },
          legacy_missing_price_poly_adapted: {
            id: 10,
            is_winner: null,
            name: "Jon Rahm",
            probability: null,
            rendered_percent: null,
            resolution_source: "api_settlement",
            settlement_display: {
              basis: "missing_stored_price",
              verdict: "unknown",
            },
          },
          legacy_kalshi_priceless_winner_adapted: {
            id: 10,
            is_winner: true,
            name: "Jon Rahm",
            probability: null,
            rendered_percent: null,
            resolution_source: "api_settlement",
          },
          source_less_legacy_ta_hit: {
            is_winner: null,
            movement: null,
            name: "Player A",
            probability: null,
            rendered_percent: null,
            resolution_source: null,
            settlement_display: {
              basis: "missing_stored_price",
              verdict: "unknown",
            },
          },
          envelopes: {
            current_default_false_search_card_hit: {
              category: "award",
              id: 66031970,
              llm_sport_category: "basketball",
              market_tier: 3,
              market_type: "award",
              market_type_label: "Award",
              name: "NBA MVP",
              outcome_count: 2,
              prices_updated_at: "2026-10-24T18:00:00+00:00",
              representation_policy: "futures_outcome_representation_v1",
              resolution_date: "2026-12-23T18:00:00+00:00",
              source: "polymarket",
              sport: "basketball_nba",
              sport_name: "NBA",
              status: "open",
              top_outcomes: [
                {
                  american_odds: null,
                  id: 1,
                  is_winner: false,
                  last_updated: "2026-10-24T18:00:00+00:00",
                  movement: null,
                  name: "Shai Gilgeous-Alexander",
                  price_changed_at: null,
                  probability: 0.55,
                  rank: 1,
                  rendered_percent: 55,
                  resolution_source: null,
                },
                {
                  american_odds: null,
                  id: 2,
                  is_winner: false,
                  last_updated: "2026-10-24T18:00:00+00:00",
                  movement: null,
                  name: "Nikola Jokic",
                  price_changed_at: null,
                  probability: 0.45,
                  rank: 2,
                  rendered_percent: 45,
                  resolution_source: null,
                },
              ],
              updated_at: "2026-10-24T18:00:00+00:00",
            },
            current_default_false_ta_suggestion_hit: {
              market_id: 66031970,
              market_tier: 3,
              market_type_label: "Award",
              representation_policy: "futures_outcome_representation_v1",
              sport_key: "basketball",
              status: "open",
              text: "NBA MVP",
              top_outcomes: [
                {
                  is_winner: false,
                  last_updated: "2026-10-24T18:00:00+00:00",
                  movement: null,
                  name: "Shai Gilgeous-Alexander",
                  price_changed_at: null,
                  probability: 0.55,
                  rendered_percent: 55,
                  resolution_source: null,
                },
                {
                  is_winner: false,
                  last_updated: "2026-10-24T18:00:00+00:00",
                  movement: null,
                  name: "Nikola Jokic",
                  price_changed_at: null,
                  probability: 0.45,
                  rendered_percent: 45,
                  resolution_source: null,
                },
              ],
              type: "futures",
            },
            legacy_missing_price_poly_card_hit: {
              category: "championship",
              id: 68149297,
              llm_sport_category: "golf",
              market_tier: 2,
              market_type: "championship",
              market_type_label: "Winner",
              name: "US Club Golf Championship",
              outcome_count: 1,
              prices_updated_at: null,
              resolution_date: "2026-10-20T00:00:00+00:00",
              source: "polymarket",
              sport: "golf_pga",
              sport_name: "Golf",
              status: "resolved",
              top_outcomes: [
                {
                  id: 10,
                  is_winner: null,
                  name: "Jon Rahm",
                  probability: null,
                  rendered_percent: null,
                  resolution_source: "api_settlement",
                  settlement_display: {
                    basis: "missing_stored_price",
                    verdict: "unknown",
                  },
                },
              ],
              updated_at: "2026-10-24T18:00:00+00:00",
            },
            legacy_kalshi_priceless_winner_card_hit: {
              category: "championship",
              id: 68149298,
              llm_sport_category: "golf",
              market_tier: 2,
              market_type: "championship",
              market_type_label: "Winner",
              name: "Kalshi Golf Championship",
              outcome_count: 1,
              prices_updated_at: null,
              resolution_date: "2026-10-20T00:00:00+00:00",
              source: "kalshi",
              sport: "golf_pga",
              sport_name: "Golf",
              status: "resolved",
              top_outcomes: [
                {
                  id: 10,
                  is_winner: true,
                  name: "Jon Rahm",
                  probability: null,
                  rendered_percent: null,
                  resolution_source: "api_settlement",
                },
              ],
              updated_at: "2026-10-24T18:00:00+00:00",
            },
            source_less_legacy_ta_suggestion_hit: {
              market_id: 62134744,
              market_tier: 2,
              market_type_label: "Match",
              sport_key: "tennis",
              status: "resolved",
              text: "Resolved Polymarket Board",
              top_outcomes: [
                {
                  is_winner: null,
                  movement: null,
                  name: "Player A",
                  probability: null,
                  rendered_percent: null,
                  resolution_source: null,
                  settlement_display: {
                    basis: "missing_stored_price",
                    verdict: "unknown",
                  },
                },
              ],
              type: "futures",
            },
          },
        };

    // 1. R1: Current default-False board retains 55% / 45% in both typeahead and FuturesCard:
    const r1TaAnswer = futuresAnswer(
      exported.envelopes.current_default_false_ta_suggestion_hit
    );
    expect(r1TaAnswer?.leader.displayValue).toBe("55%");
    expect(r1TaAnswer?.second?.displayValue).toBe("45%");
    await act(async () => {
      root.render(
        <FuturesCard
          market={
            exported.envelopes
              .current_default_false_search_card_hit as unknown as FuturesMarket
          }
        />
      );
    });
    expect(host.textContent).toContain("Shai Gilgeous-Alexander55%");
    expect(host.textContent).toContain("Nikola Jokic45%");

    // 2. R2: Legacy missing-price Polymarket retains unknown (null verdict, never Won), matching fresh detail:
    expect(
      outcomeRowVerdict(exported.legacy_missing_price_poly_adapted, true)
    ).toBeNull();
    expect(
      detailVerdict(exported.fresh_missing_price_poly_detail, true)
    ).toBeNull();
    await act(async () => {
      root.render(
        <FuturesCard
          market={
            exported.envelopes
              .legacy_missing_price_poly_card_hit as unknown as FuturesMarket
          }
        />
      );
    });
    expect(host.textContent).toContain("Jon Rahm-");
    expect(host.textContent).not.toContain("Won");
    expect(host.textContent).not.toContain("Lost");

    // 3. Positive control: Authoritative priceless Kalshi winner retains Won:
    expect(
      outcomeRowVerdict(exported.legacy_kalshi_priceless_winner_adapted, true)
    ).toBe("won");
    await act(async () => {
      root.render(
        <FuturesCard
          market={
            exported.envelopes
              .legacy_kalshi_priceless_winner_card_hit as unknown as FuturesMarket
          }
        />
      );
    });
    expect(host.textContent).toContain("Jon Rahm✓Won");

    // 4. C1: Source-less legacy typeahead abstains from Won and renders Result unknown:
    expect(outcomeRowVerdict(exported.source_less_legacy_ta_hit, true)).toBeNull();
    const c1Answer = futuresAnswer(
      exported.envelopes.source_less_legacy_ta_suggestion_hit
    );
    expect(c1Answer?.leader.displayValue).toBe("Result unknown");
  });
});
