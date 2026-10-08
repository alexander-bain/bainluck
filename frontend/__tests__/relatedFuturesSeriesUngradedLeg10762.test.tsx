/**
 * #10762 — a settled series leg nobody graded prints no verdict, never "Lost".
 *
 * WHAT THE READER SAW. `/events/15326359` (SD 1 – 3 MIL, NLDS G4, final 05:10Z Oct 8, 390px),
 * Bigger Picture → SERIES, 17:21Z:
 *
 *   Series Winner: San Diego vs Milwaukee (Kalshi)          Milwaukee Won · San Diego Lost
 *   MLB Playoffs: Who Will Win Series? – Brewers vs. Padres  Brewers Lost · Padres Lost
 *   MLB Playoffs: Brewers vs. Padres Series Spread           Brewers (-1.5) Lost · …
 *
 * Both Polymarket markets went `resolved` without grading their winning legs, and the route
 * served those legs `settled: true, is_winner: null`. The card drew
 * `<SettledMark won={o.is_winner === true} />`, so null read as Lost (the #4788 class — #4824
 * OutcomeRow, #5549 FuturesCard). The legs below are the served `series_markets` for that page.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import RelatedFutures from "@/components/RelatedFutures";
import type { RelatedFuturesResponse, SeriesMarket, SeriesMarketOutcome } from "@/lib/types";

const EVENT_ID = 15326359;
const HOME = "Milwaukee Brewers";
const AWAY = "San Diego Padres";

let swrPayload: RelatedFuturesResponse;

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: swrPayload, error: undefined, isLoading: false, mutate: () => undefined }),
}));

const leg = (
  outcome_id: number,
  name: string,
  probability: number | null,
  settled: boolean,
  is_winner: boolean | null,
): SeriesMarketOutcome => ({ outcome_id, name, probability, probability_change_24h: null, settled, is_winner });

const market = (market_id: number, market_name: string, source: string, outcomes: SeriesMarketOutcome[]): SeriesMarket => ({
  market_id,
  market_name,
  source,
  status: "resolved",
  resolution_date: null,
  outcomes,
});

const KALSHI = market(63621762, "Series Winner: San Diego vs Milwaukee", "kalshi", [
  leg(239687440, "Milwaukee", 1, true, true),
  leg(239687441, "San Diego", 0, true, false),
]);
const PM_WINNER = market(63849227, "MLB Playoffs: Who Will Win Series? – Brewers vs. Padres", "polymarket", [
  leg(240726964, "Brewers", 1, true, null),
  leg(240726965, "Padres", 0, true, null),
]);
const PM_SPREAD = market(63849229, "MLB Playoffs: Brewers vs. Padres Series Spread", "polymarket", [
  leg(240726977, "Brewers (-1.5)", 1, true, null),
  leg(240726978, "Padres (-1.5)", 0, true, false),
  leg(240726979, "Padres (-2.5)", 0, true, false),
  leg(240726980, "Brewers (-2.5)", 0, true, false),
]);

function render(series_markets: SeriesMarket[]): string {
  swrPayload = {
    event_id: EVENT_ID,
    home_team: HOME,
    away_team: AWAY,
    home_team_futures: [],
    away_team_futures: [],
    series_markets,
    total_count: 0,
    summary: null,
    event_status: "completed",
    box_score: null,
    league_context: null,
  } as RelatedFuturesResponse;
  return renderToStaticMarkup(
    React.createElement(RelatedFutures, { eventId: EVENT_ID, homeTeam: HOME, awayTeam: AWAY }),
  );
}

const text = (html: string) => html.replace(/<[^>]+>/g, "|").replace(/\|+/g, "|");

describe("#10762 SHIP: an ungraded settled leg prints no verdict", () => {
  const t = text(render([KALSHI, PM_WINNER, PM_SPREAD]));

  it("the Polymarket winner card no longer says the Brewers lost", () => {
    expect(t).toContain("|Brewers|Padres|polymarket|");
    expect(t).not.toContain("|Brewers|Lost|");
    expect(t).not.toContain("|Padres|Lost|");
  });

  it("the ungraded spread winner Brewers (-1.5) prints nothing, never Lost", () => {
    expect(t).toContain("|Brewers (-1.5)|Padres (-1.5)|Lost|");
    expect(t).not.toContain("|Brewers (-1.5)|Lost|");
  });

  it("an ungraded settled leg never falls back to its price (a result is not offered as odds)", () => {
    expect(t).not.toContain("100%");
    expect(t).not.toContain("0%");
  });
});

describe("#10762 CONTROLS", () => {
  const t = text(render([KALSHI, PM_WINNER, PM_SPREAD]));

  it("Kalshi's graded legs are unchanged: Milwaukee Won, San Diego Lost", () => {
    expect(t).toContain("|Milwaukee|Won|San Diego|Lost|kalshi|");
  });

  it("the spread legs graded false still read Lost", () => {
    expect(t).toContain("|Padres (-1.5)|Lost|Padres (-2.5)|Lost|Brewers (-2.5)|Lost|polymarket|");
  });

  it("once calibration grades the Polymarket legs, the card reads Brewers Won · Padres Lost", () => {
    const graded = market(63849227, PM_WINNER.market_name, "polymarket", [
      leg(240726964, "Brewers", 1, true, true),
      leg(240726965, "Padres", 0, true, false),
    ]);
    expect(text(render([graded]))).toContain("|Brewers|Won|Padres|Lost|polymarket|");
  });

  it("a settled leg with no is_winner key at all (older payload) also prints no verdict", () => {
    const keyless: SeriesMarketOutcome = { outcome_id: 1, name: "Brewers", probability: 1, probability_change_24h: null, settled: true };
    const t2 = text(render([market(1, "Series", "polymarket", [keyless])]));
    expect(t2).toContain("|Brewers|polymarket|");
    expect(t2).not.toContain("Lost");
  });
});
