/**
 * #8596: "Will there be a run scored in the first inning?" printed twice on
 * `/events/15318549` (Cubs @ Red Sox, scheduled, 2026-09-25 ~10:05Z): once in
 * Additional Markets (from `/game-markets` → `other`) and again in Bigger
 * Picture → Game props (from `/related-futures`), same market 62308451, same price.
 *
 * The wire and related-futures rows below are the production payloads for that
 * event, trimmed to the fields the code reads.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import RelatedFutures from "@/components/RelatedFutures";
import { buildMarketSection } from "@/lib/otherMarketGroups";
import {
  SPECIAL_MARKETS_MIN_WIRE_ROWS,
  specialMarketsDrawnIds,
  withoutGamePropsDrawnAbove,
} from "@/lib/gamePropsDrawnAbove";
import type { GameMarketsResponse } from "@/lib/api";
import type { RelatedFuture, RelatedFuturesResponse } from "@/lib/types";

const EVENT_ID = 15318549;
const HOME = "Boston Red Sox";
const AWAY = "Chicago Cubs";
const QUESTION_ID = 62308451;
const MONEYLINE_ID = 62236432;
const QUESTION = "Will there be a run scored in the first inning?: Chicago Cubs vs. Boston Red Sox";

const WIRE: GameMarketsResponse["other"] = [
  { market_name: "Chicago Cubs vs. Boston Red Sox", outcome_name: "Chicago Cubs", probability: 0.535, source: "polymarket", observed_at: "2026-09-25T09:37:05.903405+00:00", is_winner: null, resolution_source: null, _market_id: MONEYLINE_ID },
  { market_name: "Chicago Cubs vs. Boston Red Sox", outcome_name: "Boston Red Sox", probability: 0.465, source: "polymarket", observed_at: "2026-09-25T09:37:05.903405+00:00", is_winner: null, resolution_source: null, _market_id: MONEYLINE_ID },
  { market_name: QUESTION, outcome_name: "No", probability: 0.555, source: "polymarket", observed_at: "2026-09-25T09:37:05.861968+00:00", is_winner: null, resolution_source: null, _market_id: QUESTION_ID },
  { market_name: QUESTION, outcome_name: "Yes", probability: 0.445, source: "polymarket", observed_at: "2026-09-25T09:37:05.861968+00:00", is_winner: null, resolution_source: null, _market_id: QUESTION_ID },
];
const GAME_MARKETS = { other: WIRE, home_team: HOME, away_team: AWAY };

function rf(over: Partial<RelatedFuture>): RelatedFuture {
  return {
    market_id: QUESTION_ID,
    market_name: QUESTION,
    display_category: "game_prop",
    market_tier: 5,
    category: "game_prop",
    source: "polymarket",
    outcome_id: 1,
    outcome_name: "Yes",
    probability: 0.445,
    american_odds: null,
    probability_change_24h: null,
    opening_probability: null,
    rank: null,
    relevance_score: 44,
    relevance_reason: "shifting",
    last_updated: null,
    next_update_expected: "",
    resolution_date: "2026-10-02T17:05:00+00:00",
    ...over,
  };
}
const RF_YES = rf({});
const RF_NO = rf({ outcome_id: 2, outcome_name: "No", probability: 0.555 });
// A game prop Additional Markets does NOT draw: it must survive.
const OTHER_Q = "Will there be a home run in the game?: Chicago Cubs vs. Boston Red Sox";
const RF_OTHER_YES = rf({ market_id: 99990001, market_name: OTHER_Q, outcome_id: 3, outcome_name: "Yes", probability: 0.8 });
const RF_OTHER_NO = rf({ market_id: 99990001, market_name: OTHER_Q, outcome_id: 4, outcome_name: "No", probability: 0.2 });

let swrPayload: RelatedFuturesResponse;
jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: swrPayload, error: undefined, isLoading: false, mutate: () => undefined }),
}));

function render(home: RelatedFuture[], drawnGameMarketIds?: number[]): string {
  swrPayload = {
    event_id: EVENT_ID,
    home_team: HOME,
    away_team: AWAY,
    home_team_futures: home,
    away_team_futures: [],
    series_markets: [],
    total_count: home.length,
    summary: null,
    event_status: "scheduled",
    box_score: null,
    league_context: null,
  } as RelatedFuturesResponse;
  return renderToStaticMarkup(
    React.createElement(RelatedFutures, {
      eventId: EVENT_ID,
      homeTeam: HOME,
      awayTeam: AWAY,
      eventStatus: "scheduled",
      drawnGameMarketIds,
    }),
  );
}
const count = (html: string, needle: RegExp) => (html.match(needle) ?? []).length;
const FIRST_INNING = /run scored in the first inning/gi;

describe("#8596 buildMarketSection reports the markets it draws", () => {
  it("names the first-inning question and not the moneyline the hero owns", () => {
    const section = buildMarketSection(WIRE, { homeTeam: HOME, awayTeam: AWAY });
    // Precondition: Additional Markets really does draw the question on this wire.
    expect(JSON.stringify(section.categories)).toMatch(/first inning/i);
    expect(section.drawnMarketIds).toEqual([QUESTION_ID]);
    expect(section.drawnMarketIds).not.toContain(MONEYLINE_ID);
  });

  it("is empty when nothing draws", () => {
    expect(buildMarketSection([], {}).drawnMarketIds).toEqual([]);
    expect(buildMarketSection(WIRE.slice(0, 2), { homeTeam: HOME, awayTeam: AWAY }).drawnMarketIds).toEqual([]);
  });

  it("follows the page's mount gate: under the wire floor Additional Markets is not mounted, so it draws nothing", () => {
    expect(SPECIAL_MARKETS_MIN_WIRE_ROWS).toBe(3);
    expect(specialMarketsDrawnIds({ ...GAME_MARKETS, other: WIRE.slice(2) })).toEqual([]);
    expect(specialMarketsDrawnIds(GAME_MARKETS)).toEqual([QUESTION_ID]);
    expect(specialMarketsDrawnIds(null)).toEqual([]);
  });

  it("filters by id only", () => {
    const kept = withoutGamePropsDrawnAbove([RF_YES, RF_NO, RF_OTHER_YES], [QUESTION_ID]);
    expect(kept).toEqual([RF_OTHER_YES]);
    expect(withoutGamePropsDrawnAbove([RF_YES], undefined)).toEqual([RF_YES]);
    expect(withoutGamePropsDrawnAbove([RF_YES], [])).toEqual([RF_YES]);
  });
});

describe("#8596 Bigger Picture does not print a question Additional Markets already shows", () => {
  it("control: without the ids the question renders in Bigger Picture (the defect's shape)", () => {
    expect(count(render([RF_YES, RF_NO]), FIRST_INNING)).toBeGreaterThan(0);
  });

  it("with the page's ids the question is gone from Bigger Picture", () => {
    const html = render([RF_YES, RF_NO], specialMarketsDrawnIds(GAME_MARKETS));
    expect(count(html, FIRST_INNING)).toBe(0);
  });

  it("a game prop Additional Markets does not draw still renders", () => {
    const html = render([RF_YES, RF_NO, RF_OTHER_YES, RF_OTHER_NO], specialMarketsDrawnIds(GAME_MARKETS));
    expect(count(html, FIRST_INNING)).toBe(0);
    expect(html).toMatch(/home run in the game/i);
  });
});

describe("#8596 the event page wires it", () => {
  // The page is too heavy to mount here; its two lines are the whole wiring.
  const fs = require("fs") as typeof import("fs");
  const path = require("path") as typeof import("path");
  const page = fs.readFileSync(path.join(__dirname, "..", "app", "events", "[id]", "page.tsx"), "utf8");

  it("passes Additional Markets' drawn ids to RelatedFutures", () => {
    expect(page).toMatch(/drawnGameMarketIds=\{specialMarketsDrawnIds\(gameMarkets\b/);
  });

  it("mounts Additional Markets on the same floor the ids use", () => {
    expect(page).toMatch(/gameMarkets\.other\?\.length \?\? 0\) >= SPECIAL_MARKETS_MIN_WIRE_ROWS && \(\s*<SectionErrorBoundary label="Special markets"/);
  });
});
