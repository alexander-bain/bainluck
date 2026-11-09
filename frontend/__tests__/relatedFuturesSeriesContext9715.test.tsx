/**
 * #9715 — Playoff series context in RelatedFutures:
 * 1. Renders 3-family series markets (series_winner, exact_series_score, series_total_games)
 *    with data-series-family and data-distribution-kind attributes.
 * 2. Renders independent_binary sum_note on Series Total Games rungs so readers
 *    never mistake cumulative/binary rungs for a 100% exhaustive distribution.
 * 3. Renders during-game movement with explicit "since game start" baseline label
 *    when baseline_kind === "game_start", never conflating opening_probability
 *    or 24h change with game start.
 * 4. Preserves settled states (Won / Lost) and never overwrites them with live movement.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import RelatedFutures from "@/components/RelatedFutures";
import type { RelatedFuturesResponse, SeriesMarket } from "@/lib/types";

const EVENT_ID = 15319563;
const HOME = "New York Yankees";
const AWAY = "Boston Red Sox";

let swrPayload: RelatedFuturesResponse;

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({
    data: swrPayload,
    error: undefined,
    isLoading: false,
    mutate: () => undefined,
  }),
}));

function buildSeriesMarkets(): SeriesMarket[] {
  return [
    {
      market_id: 62383730,
      market_name: "Series Winner: Boston vs New York Yankees",
      source: "kalshi",
      status: "open",
      resolution_date: null,
      series_family: "series_winner",
      series_family_label: "Series Winner",
      distribution_kind: "exhaustive",
      exhaustive: true,
      normalize_to_unit_sum: true,
      sum_note: null,
      baseline_status: "ok",
      baseline_kind: "game_start",
      baseline_label: "since game start",
      outcomes: [
        {
          outcome_id: 235705604,
          name: "New York Yankees",
          probability: 0.64,
          probability_change_24h: 0.09,
          settled: false,
          is_winner: null,
          baseline_status: "ok",
          baseline_kind: "game_start",
          baseline_label: "since game start",
          baseline_probability: 0.575,
          movement_since_baseline: 0.065,
          movement_percentage_points: 6.5,
        },
        {
          outcome_id: 235705605,
          name: "Boston Red Sox",
          probability: 0.36,
          probability_change_24h: -0.09,
          settled: false,
          is_winner: null,
          baseline_status: "ok",
          baseline_kind: "game_start",
          baseline_label: "since game start",
          baseline_probability: 0.4,
          movement_since_baseline: -0.04,
          movement_percentage_points: -4.0,
        },
      ],
    },
    {
      market_id: 62455755,
      market_name: "Series Exact Score: Boston vs New York Yankees",
      source: "kalshi",
      status: "open",
      resolution_date: null,
      series_family: "exact_series_score",
      series_family_label: "Exact Series Score",
      distribution_kind: "exhaustive",
      exhaustive: true,
      normalize_to_unit_sum: true,
      sum_note: null,
      baseline_status: "settled_preserved",
      baseline_kind: null,
      baseline_label: null,
      outcomes: [
        {
          outcome_id: 236000923,
          name: "NYY wins 2-0",
          probability: 0.54,
          probability_change_24h: null,
          settled: false,
          is_winner: null,
        },
        {
          outcome_id: 236000926,
          name: "BOS wins 2-0",
          probability: null,
          probability_change_24h: -0.22,
          settled: true,
          is_winner: false,
          settled_state: "Lost",
          baseline_status: "settled_preserved",
        },
      ],
    },
    {
      market_id: 62455756,
      market_name: "Series Total Games: Boston vs New York Yankees",
      source: "kalshi",
      status: "open",
      resolution_date: null,
      series_family: "series_total_games",
      series_family_label: "Series Total Games",
      distribution_kind: "independent_binary",
      exhaustive: false,
      normalize_to_unit_sum: false,
      sum_note:
        "Each line is its own yes-or-no question, so these don't add up to 100%.",
      baseline_status: "missing_baseline",
      baseline_kind: null,
      baseline_label: null,
      outcomes: [
        {
          outcome_id: 236000927,
          name: "Over 2.5 total games",
          probability: 0.47,
          probability_change_24h: null,
          settled: false,
          is_winner: null,
          baseline_status: "missing_baseline",
          baseline_kind: null,
          movement_since_baseline: null,
        },
      ],
    },
  ];
}

describe("#9715 Series Context in RelatedFutures", () => {
  it("renders 3-family distribution kinds, independent binary note, labeled game-start baseline, and preserves settled Lost state", () => {
    const markets = buildSeriesMarkets();
    swrPayload = {
      event_id: EVENT_ID,
      home_team: HOME,
      away_team: AWAY,
      home_team_futures: [],
      away_team_futures: [],
      series_markets: markets,
      series_context: {
        section_title: "Series Outlook",
        series_hub_slug: "mlb-2026-alwc-bos-nyy",
        series_hub_href: "/collections/mlb-2026-alwc-bos-nyy",
        series_score_summary: "Red Sox vs Yankees: AL Wild Card Series",
        families_present: [
          "series_winner",
          "exact_series_score",
          "series_total_games",
        ],
        core_families_present: [
          "series_winner",
          "exact_series_score",
          "series_total_games",
        ],
        missing_families: [],
        inventory_status: "complete",
        baseline_status: "ok",
        baseline_kind: "game_start",
        baseline_label: "since game start",
        game_start: "2026-09-29T23:08:00+00:00",
        markets,
        markets_by_family: {},
      },
      total_count: 0,
      summary: null,
      event_status: "live",
      box_score: null,
      league_context: null,
    };

    const html = renderToStaticMarkup(
      React.createElement(RelatedFutures, {
        eventId: EVENT_ID,
        homeTeam: HOME,
        awayTeam: AWAY,
      }),
    );

    // 1. Distribution kinds, family attributes & series hub link
    expect(html).toContain('data-series-family="series_winner"');
    expect(html).toContain('data-series-family="exact_series_score"');
    expect(html).toContain('data-series-family="series_total_games"');
    expect(html).toContain('data-distribution-kind="exhaustive"');
    expect(html).toContain('data-distribution-kind="independent_binary"');
    expect(html).toContain('href="/collections/mlb-2026-alwc-bos-nyy"');
    expect(html).toContain("Red Sox vs Yankees: AL Wild Card Series");
    expect(html).toContain("Series hub →");

    // 2. Independent binary rung note
    expect(html).toContain(
      "Each line is its own yes-or-no question, so these don&#x27;t add up to 100%.",
    );

    // 3. Labeled game-start baseline movement (rounded whole-number +7% at game start, NOT 9.0% 24h change)
    expect(html).toContain('data-baseline-kind="game_start"');
    expect(html).toContain("7%");
    expect(html).toContain("since game start");
    expect(html).not.toContain("9.0%");

    // 4. Settled Lost state preserved and never overwritten by movement
    expect(html).toContain("BOS wins 2-0");
    expect(html).toContain("Lost");
    expect(html).not.toContain("22.0%");
  });
});
