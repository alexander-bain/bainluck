/** @jest-environment jsdom */

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import SearchBar from "@/components/SearchBar";
import MobileSearchOverlay from "@/components/MobileSearchOverlay";
import FuturesCard from "@/components/FuturesCard";
import { fetchTypeahead } from "@/lib/api";
import type { TypeaheadOutcome, TypeaheadSuggestion } from "@/lib/api";
import type { FuturesMarket, FuturesOutcome } from "@/lib/types";
import { futuresAnswer } from "@/lib/searchSuggestionDisplay";
import { outcomeRowVerdict } from "@/lib/futuresOutcomeVerdict";
import { outcomeRowVerdict as detailVerdict } from "@/components/futures/OutcomeRow";
// Static import, not an fs read: same committed repo-relative file and no
// fallback, and no file-data source reaching FuturesCard's image fetch (CodeQL
// js/file-access-to-http on 35549713).
import exportedFixture from "../fixtures/backend_to_web_fixtures_11616.json";

// A search row is not a detail market: it carries `market_type_label` and each
// outcome's `price_changed_at`, and omits detail-only fields. Typed narrowly so
// a misspelled or mistyped fixture field still fails tsc; FuturesMarket is
// assignable to it, so the card boundary needs only a plain `as`.
type SearchRowOutcome = FuturesOutcome & { price_changed_at?: string | null };
type SearchRow = Omit<
  FuturesMarket,
  "description" | "external_id" | "mutually_exclusive" | "commence_time" | "created_at" | "top_outcomes"
> & { market_type_label?: string; top_outcomes?: SearchRowOutcome[] };

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
    const adaptedLegacyMarket: SearchRow = {
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
      root.render(<FuturesCard market={adaptedLegacyMarket as FuturesMarket} />);
    });
    const link = host.querySelector<HTMLAnchorElement>("a[href='/futures/66031970']")!;
    expect(link).not.toBeNull();
    expect(link.textContent).toContain("NBA MVP");
    expect(link.textContent).toContain("Victor Wembanyama-");
    expect(link.textContent).toContain("Shai Gilgeous-Alexander✓Won");
    expect(link.textContent).not.toMatch(/28%|19%|↑|↓/);
  });

  test("committed backend-exported R1/R2/C1/R3 cache fixtures render identical truth across SearchBar, MobileSearchOverlay, FuturesCard, and detailVerdict", async () => {
    // Untyped runtime JSON, exactly as the JSON.parse this replaces read it:
    // each use below asserts its own client shape at the boundary it feeds.
    const exported: any = exportedFixture;

    // 1. R1: Current default-False board retains 55% / 45% in both typeahead and FuturesCard:
    const r1TaAnswer = futuresAnswer(
      exported.r1_open_default_false.adapted_typeahead
    );
    expect(r1TaAnswer?.leader.displayValue).toBe("55%");
    expect(r1TaAnswer?.second?.displayValue).toBe("45%");
    await act(async () => {
      root.render(
        <FuturesCard
          market={
            exported.r1_open_default_false
              .adapted_search as unknown as FuturesMarket
          }
        />
      );
    });
    expect(host.textContent).toContain("First Contender55%");
    expect(host.textContent).toContain("Second Contender45%");
    expect(host.textContent).not.toMatch(/Won|Lost/);

    // 2. R1: Open non-exclusive ladder mixes 68% priced default-False and priceless settled Won:
    await act(async () => {
      root.render(
        <FuturesCard
          market={
            exported.r1_open_mixed_priceless
              .adapted_search as unknown as FuturesMarket
          }
        />
      );
    });
    expect(host.textContent).toContain("3.75%68%");
    expect(host.textContent).toContain("4.25%✓Won");
    expect(host.textContent).not.toContain("Lost");

    // 3. R2: Legacy missing-price Polymarket retains unknown (null verdict, never Won), matching fresh detail:
    expect(exported.r2_resolved_poly_missing_price.fresh_search.top_outcomes).toEqual([]);
    expect(
      outcomeRowVerdict(
        exported.r2_resolved_poly_missing_price.legacy_search.top_outcomes[0],
        true
      )
    ).toBeNull();
    expect(
      outcomeRowVerdict(
        exported.r2_resolved_poly_missing_price.legacy_normalized_one
          .top_outcomes[0],
        true
      )
    ).toBeNull();
    expect(
      detailVerdict(
        exported.r2_resolved_poly_missing_price.fresh_detail.outcomes[0],
        true
      )
    ).toBeNull();
    await act(async () => {
      root.render(
        <FuturesCard
          market={
            exported.r2_resolved_poly_missing_price
              .legacy_search as unknown as FuturesMarket
          }
        />
      );
    });
    expect(host.textContent).toContain("Jon Rahm-");
    expect(host.textContent).not.toContain("Won");
    expect(host.textContent).not.toContain("Lost");
    const r2TaAnswer = futuresAnswer(
      exported.r2_resolved_poly_missing_price.legacy_typeahead
    );
    expect(r2TaAnswer?.leader.displayValue).toBe("Result unknown");

    // 4. Positive control: Authoritative priceless Kalshi winner retains Won across fresh/detail/cache:
    expect(
      outcomeRowVerdict(
        exported.r2_resolved_kalshi_priceless_winner.legacy_search
          .top_outcomes[0],
        true
      )
    ).toBe("won");
    expect(
      detailVerdict(
        exported.r2_resolved_kalshi_priceless_winner.fresh_detail.outcomes[0],
        true
      )
    ).toBe("won");
    await act(async () => {
      root.render(
        <FuturesCard
          market={
            exported.r2_resolved_kalshi_priceless_winner
              .legacy_search as unknown as FuturesMarket
          }
        />
      );
    });
    expect(host.textContent).toContain("Confirmed Kalshi Winner✓Won");
    const r2KalshiTaAnswer = futuresAnswer(
      exported.r2_resolved_kalshi_priceless_winner.legacy_typeahead
    );
    expect(r2KalshiTaAnswer?.leader.displayValue).toBe("Won");

    // 5. C1: Source-less legacy typeahead abstains from Won and renders Result unknown:
    expect(
      outcomeRowVerdict(
        exported.c1_sourceless_legacy_typeahead.missing_price.top_outcomes[0],
        true
      )
    ).toBeNull();
    expect(
      outcomeRowVerdict(
        exported.c1_sourceless_legacy_typeahead.nonterminal_price
          .top_outcomes[0],
        true
      )
    ).toBeNull();
    expect(
      futuresAnswer(exported.c1_sourceless_legacy_typeahead.missing_price)
        ?.leader.displayValue
    ).toBe("Result unknown");
    expect(
      futuresAnswer(exported.c1_sourceless_legacy_typeahead.nonterminal_price)
        ?.leader.displayValue
    ).toBe("Result unknown");

    // 6. R3: Open 55/45 with raw (is_winner=True, resolution_source=None) and (is_winner=False, resolution_source="pass2_guess"):
    const r3OpenTaAnswer = futuresAnswer(
      exported.r3_open_raw_metadata.adapted_typeahead
    );
    expect(r3OpenTaAnswer?.leader.displayValue).toBe("55%");
    expect(r3OpenTaAnswer?.second?.displayValue).toBe("45%");
    expect(
      detailVerdict(
        exported.r3_open_raw_metadata.fresh_detail.outcomes[0],
        false
      )
    ).toBeNull();
    expect(
      detailVerdict(
        exported.r3_open_raw_metadata.fresh_detail.outcomes[1],
        false
      )
    ).toBeNull();
    await act(async () => {
      root.render(
        <FuturesCard
          market={
            exported.r3_open_raw_metadata
              .fresh_search as unknown as FuturesMarket
          }
        />
      );
    });
    const r3FreshCardText = host.textContent;
    await act(async () => {
      root.render(
        <FuturesCard
          market={
            exported.r3_open_raw_metadata
              .adapted_search as unknown as FuturesMarket
          }
        />
      );
    });
    expect(host.textContent).toBe(r3FreshCardText);
    expect(host.textContent).toContain("55%");
    expect(host.textContent).toContain("45%");
    expect(host.textContent).not.toMatch(/Won|Lost/);

    // 7. R3: Resolved Polymarket 1/0 with resolution_source="pass2_guess" retains Won/Lost:
    expect(
      outcomeRowVerdict(
        exported.r3_resolved_poly_pass2_guess.adapted_search.top_outcomes[0],
        true
      )
    ).toBe("won");
    expect(
      outcomeRowVerdict(
        exported.r3_resolved_poly_pass2_guess.adapted_search.top_outcomes[1],
        true
      )
    ).toBe("lost");
    expect(
      detailVerdict(
        exported.r3_resolved_poly_pass2_guess.fresh_detail.outcomes[0],
        true
      )
    ).toBe("won");
    expect(
      detailVerdict(
        exported.r3_resolved_poly_pass2_guess.fresh_detail.outcomes[1],
        true
      )
    ).toBe("lost");
    const r3PolyTaAnswer = futuresAnswer(
      exported.r3_resolved_poly_pass2_guess.adapted_typeahead
    );
    expect(r3PolyTaAnswer?.leader.displayValue).toBe("Won");
    await act(async () => {
      root.render(
        <FuturesCard
          market={
            exported.r3_resolved_poly_pass2_guess
              .adapted_search as unknown as FuturesMarket
          }
        />
      );
    });
    expect(host.textContent).toContain("Resolved Winner✓Won");
    expect(host.textContent).toContain("Resolved LoserLost");
  });
});
