/**
 * #9919 — a playoff Series card draws a leg already ruled out as a result, not "---".
 *
 * WHAT THE READER SAW. `/events/15321907` (BOS @ NYY, Wild Card G2, 2026-09-30 ~20:15Z, 390px),
 * Bigger Picture → SERIES → "Series Exact Score: Boston vs New York Yankees":
 *
 *   NYY wins 2-0  54%   NYY wins 2-1  27%   BOS wins 2-1  19%   BOS wins 2-0  ---
 *
 * The Yankees won Game 1, so Kalshi graded BOS 2-0 lost (`is_winner false`, `api_settlement`).
 * "---" says we have no number; the question has been answered. The server now serves
 * `settled` / `is_winner` on each series outcome (backend guard
 * `test_route_related_futures_series_leg_lost_9919.py`); this is the render half, in the one
 * settled vocabulary (`SettledMark`, #3868 / #4036).
 *
 * The four legs are the served card's numbers after #9901's squeeze, with the grade fields added.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import RelatedFutures from "@/components/RelatedFutures";
import type { RelatedFuturesResponse, SeriesMarketOutcome } from "@/lib/types";

const EVENT_ID = 15321907;
const HOME = "New York Yankees";
const AWAY = "Boston Red Sox";

let swrPayload: RelatedFuturesResponse;

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: swrPayload, error: undefined, isLoading: false, mutate: () => undefined }),
}));

const leg = (
  outcome_id: number,
  name: string,
  probability: number | null,
  grade: Partial<SeriesMarketOutcome> = {},
): SeriesMarketOutcome => ({ outcome_id, name, probability, probability_change_24h: null, ...grade });

const LIVE = [
  leg(1, "NYY wins 2-0", 0.5392, { settled: false, is_winner: null }),
  leg(2, "NYY wins 2-1", 0.2696, { settled: false, is_winner: null }),
  leg(3, "BOS wins 2-1", 0.1912, { settled: false, is_winner: null }),
];
const RULED_OUT = leg(4, "BOS wins 2-0", null, { settled: true, is_winner: false });

function render(outcomes: SeriesMarketOutcome[]): string {
  swrPayload = {
    event_id: EVENT_ID,
    home_team: HOME,
    away_team: AWAY,
    home_team_futures: [],
    away_team_futures: [],
    series_markets: [
      {
        market_id: 62455755,
        market_name: "Series Exact Score: Boston vs New York Yankees",
        source: "kalshi",
        status: "open",
        resolution_date: null,
        outcomes,
      },
    ],
    total_count: 0,
    summary: null,
    event_status: "live",
    box_score: null,
    league_context: null,
  } as RelatedFuturesResponse;
  return renderToStaticMarkup(
    React.createElement(RelatedFutures, { eventId: EVENT_ID, homeTeam: HOME, awayTeam: AWAY }),
  );
}

const text = (html: string) => html.replace(/<[^>]+>/g, "|").replace(/\|+/g, "|");

describe("#9919 SHIP: the ruled-out leg reads Lost", () => {
  const t = text(render([...LIVE, RULED_OUT]));

  it("BOS wins 2-0 prints Lost, not ---", () => {
    expect(t).toContain("|BOS wins 2-0|Lost|");
    expect(t).not.toContain("---");
  });

  it("the live legs keep their numbers (the card still adds up to 100)", () => {
    expect(t).toContain("|NYY wins 2-0|54%|");
    expect(t).toContain("|NYY wins 2-1|27%|");
    expect(t).toContain("|BOS wins 2-1|19%|");
  });

  it("a crowned leg reads Won", () => {
    const won = text(render([leg(1, "NYY wins 2-0", 1, { settled: true, is_winner: true }), RULED_OUT]));
    expect(won).toContain("|NYY wins 2-0|Won|");
    expect(won).not.toContain("100%");
  });

  it("a settled leg drops its 24h move — a result has no movement to report", () => {
    const t2 = text(render([{ ...RULED_OUT, probability_change_24h: -0.03 }]));
    expect(t2).toContain("|BOS wins 2-0|Lost|");
    expect(t2).not.toContain("3.0%");
  });
});

describe("#9919 CONTROLS", () => {
  it("an OLDER payload (no grade keys) renders exactly as before: the dash stays", () => {
    const old = leg(4, "BOS wins 2-0", null);
    const t = text(render([...LIVE, old]));
    expect(t).toContain("|BOS wins 2-0|---|");
    expect(t).not.toContain("Lost");
  });

  it("an unpriced leg the server did NOT settle keeps its dash, never Lost", () => {
    // `is_winner: false` alone is the column's default, not a grade (#3617 / CERT-2222).
    const unlicensed = leg(4, "BOS wins 2-0", null, { settled: false, is_winner: false });
    const t = text(render([...LIVE, unlicensed]));
    expect(t).toContain("|BOS wins 2-0|---|");
    expect(t).not.toContain("Lost");
  });
});
