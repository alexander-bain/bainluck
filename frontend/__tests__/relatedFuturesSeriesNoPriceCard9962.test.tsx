/**
 * #9962 — a series card with no price and no result on any leg is not drawn.
 *
 * PHI @ ATL `/events/15321782` (live lane's capture, 2026-09-30 23:20Z): after #9934
 * correctly withdrew a Polymarket price its own book ruled out, the SERIES block drew
 * "MLB Playoffs: Who Will Win Series? - Braves vs. Phillies" as `Phillies --- / Braves
 * ---` — a card with nothing to say (notice 34: leave the space empty).
 *
 * The fixture is the served `/related-futures` payload banked 23:47Z with the team
 * futures emptied: three Kalshi series markets with prices, one Polymarket market with
 * `probability: null, settled: false` on both legs.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import RelatedFutures from "@/components/RelatedFutures";
import type { RelatedFuture, RelatedFuturesResponse, SeriesMarket } from "@/lib/types";

import banked from "./fixtures/relatedFutures.15321782.series-no-price-9962.json";

const B = banked as unknown as RelatedFuturesResponse;
const POLY = "MLB Playoffs: Who Will Win Series? - Braves vs. Phillies";
const KALSHI = [
  "Series Exact Score: Philadelphia vs Atlanta",
  "Series Total Games: Philadelphia vs Atlanta",
  "Series Winner: Philadelphia vs Atlanta",
];

let swrPayload: RelatedFuturesResponse;

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: swrPayload, error: undefined, isLoading: false, mutate: () => undefined }),
}));

function render(series: SeriesMarket[], home: RelatedFuture[] = []): string {
  swrPayload = { ...B, series_markets: series, home_team_futures: home };
  return renderToStaticMarkup(
    React.createElement(RelatedFutures, { eventId: B.event_id, homeTeam: B.home_team, awayTeam: B.away_team }),
  );
}

const text = (html: string) => html.replace(/<[^>]+>/g, "|").replace(/\|+/g, "|");
const poly = () => (B.series_markets ?? []).find((m) => m.market_name === POLY)!;

describe("#9962 · the specimen", () => {
  it("is a served Polymarket series market with no price and no result on either leg", () => {
    expect(poly().outcomes.map((o) => [o.name, o.probability, o.settled])).toEqual([
      ["Phillies", null, false],
      ["Braves", null, false],
    ]);
  });
});

describe("#9962 SHIP: the blank card is gone, the priced cards stay", () => {
  const t = text(render(B.series_markets ?? []));

  it("does not draw the Polymarket card or a dash for its legs", () => {
    expect(t).not.toContain(POLY);
    expect(t).not.toContain("|Phillies|---|");
    expect(t).not.toContain("|Braves|---|");
  });

  it("CONTROL — the three Kalshi cards still draw, numbers intact", () => {
    for (const k of KALSHI) expect(t).toContain(`|${k}|`);
    expect(t).toContain("|Philadelphia|52%|");
    expect(t).toContain("|SERIES|");
  });
});

describe("#9962 · the edges", () => {
  it("when every served market is blank, there is no SERIES card at all", () => {
    expect(text(render([poly()]))).not.toContain("|SERIES|");
  });

  it("…and the legacy home/away series list is not consulted in its place", () => {
    const legacyRow = {
      market_id: 1,
      market_name: POLY,
      clean_label: POLY,
      display_category: "series",
      category: "series",
      source: "polymarket",
      outcome_id: 2,
      outcome_name: "Phillies",
      probability: null,
    } as unknown as RelatedFuture;
    expect(text(render([poly()], [legacyRow]))).not.toContain("|SERIES|");
  });

  it("one priced leg keeps the card (the other leg's dash is per-leg, unchanged)", () => {
    const one = { ...poly(), outcomes: [{ ...poly().outcomes[0], probability: 0.6 }, poly().outcomes[1]] };
    const t = text(render([one]));
    expect(t).toContain(`|${POLY}|`);
    expect(t).toContain("|Phillies|60%|");
  });

  it("a leg with only a RESULT keeps the card", () => {
    const graded = { ...poly(), outcomes: [{ ...poly().outcomes[0], settled: true, is_winner: false }, poly().outcomes[1]] };
    expect(text(render([graded]))).toContain(`|${POLY}|`);
  });
});
