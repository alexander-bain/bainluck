/**
 * #10005 — a live playoff SERIES card prints no `---` rows and never calls an open series "100%".
 *
 * WHAT THE READER SAW. `/events/15321946` (CHC @ SD, Wild Card G2, live, 2026-10-01 04:5xZ, 390px),
 * Bigger Picture → SERIES:
 *
 *   Series Exact Score   SD wins 2-0 ---  SD wins 2-1 ---  CHC wins 2-1 ---  CHC wins 2-0 Lost
 *   Series Winner        San Diego 100%   Chicago Cubs 1%
 *
 * #9962 keeps a market whose legs carry a price OR a result, so one Lost leg kept the card and
 * every unpriced leg beside it printed `---` (notice 34: an unshowable number leaves the space
 * empty). And the block rounded `0.995` to `100%` itself instead of using the shared formatter,
 * which refuses to claim a boundary an unsettled price is not on.
 *
 * The 04:52Z payload is reproduced below (three null legs). The fixture banked at 05:01Z is the
 * same game a few outs later, with the legs priced — the `>99%` arm on real served bytes.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import RelatedFutures from "@/components/RelatedFutures";
import type { RelatedFuturesResponse, SeriesMarket, SeriesMarketOutcome } from "@/lib/types";
import banked from "./fixtures/relatedFuturesSeries10005.15321946.20261001.json";

const EVENT_ID = 15321946;
const HOME = "San Diego Padres";
const AWAY = "Chicago Cubs";

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
): SeriesMarketOutcome => ({
  outcome_id, name, probability, probability_change_24h: null, settled: false, is_winner: null, ...grade,
});

const market = (market_id: number, market_name: string, outcomes: SeriesMarketOutcome[]): SeriesMarket => ({
  market_id, market_name, source: "kalshi", status: "open", resolution_date: null, outcomes,
} as SeriesMarket);

// /api/events/15321946/related-futures at 04:52Z, as quoted in #10005.
const AT_0452 = [
  market(62713436, "Series Exact Score: Chicago Cubs vs San Diego", [
    leg(236765872, "SD wins 2-0", null),
    leg(236765873, "SD wins 2-1", null),
    leg(236765874, "CHC wins 2-1", null),
    leg(236765875, "CHC wins 2-0", null, { settled: true, is_winner: false }),
  ]),
  market(62713437, "Series Total Games: Chicago Cubs vs San Diego", [
    leg(236765876, "Over 2.5 total games", null),
  ]),
  market(62713438, "Series Winner: Chicago Cubs vs San Diego", [
    leg(236765878, "San Diego", 0.995),
    leg(236765877, "Chicago Cubs", 0.01),
  ]),
];

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
    event_status: "live",
    box_score: null,
    league_context: null,
  } as RelatedFuturesResponse;
  return renderToStaticMarkup(
    React.createElement(RelatedFutures, { eventId: EVENT_ID, homeTeam: HOME, awayTeam: AWAY }),
  );
}

const text = (html: string) =>
  html.replace(/<[^>]+>/g, "|").replace(/\|+/g, "|").replace(/&gt;/g, ">");

describe("#10005 SHIP: the live CHC@SD series card", () => {
  const t = text(render(AT_0452));

  it("prints no --- for the three unpriced, unanswered legs", () => {
    expect(t).not.toContain("---");
    expect(t).toContain("|SD wins 2-0|SD wins 2-1|CHC wins 2-1|CHC wins 2-0|Lost|");
  });

  it("calls the open series >99%, never 100%", () => {
    expect(t).not.toContain("100%");
    expect(t).toContain("|San Diego|>99%|");
    expect(t).toContain("|Chicago Cubs|1%|");
  });

  it("still drops the market with nothing on any leg (#9962 unchanged)", () => {
    expect(t).not.toContain("Over 2.5 total games");
  });
});

describe("#10005 on the banked served bytes (05:01Z)", () => {
  const t = text(render((banked as RelatedFuturesResponse).series_markets ?? []));

  it("every 0.995 leg reads >99% and nothing reads 100% or ---", () => {
    expect(t).toContain("|SD wins 2-0|>99%|");
    expect(t).toContain("|San Diego|>99%|");
    expect(t).not.toContain("100%");
    expect(t).not.toContain("---");
  });

  it("the ruled-out leg keeps Lost and the Polymarket card keeps its numbers", () => {
    expect(t).toContain("|CHC wins 2-0|Lost|");
    expect(t).toContain("|Padres|99%|");
    expect(t).toContain("|Cubs|1%|");
  });
});

describe("#10005 CONTROLS", () => {
  it("a mid-range priced leg prints the same number it did before", () => {
    const t = text(render([market(1, "Series Winner: A vs B", [leg(1, "A", 0.54), leg(2, "B", 0.46)])]));
    expect(t).toContain("|A|54%|");
    expect(t).toContain("|B|46%|");
  });

  it("a crowned leg still reads Won", () => {
    const t = text(render([market(1, "Series Winner: A vs B", [leg(1, "A", 1, { settled: true, is_winner: true })])]));
    expect(t).toContain("|A|Won|");
    expect(t).not.toContain("100%");
  });
});
