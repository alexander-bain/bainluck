/**
 * #8344 — a Yes/No prop is headed by its question, and the game's own Kalshi moneyline leaves the
 * rail even when Kalshi spells a club by its initials.
 *
 * WHAT THE READER SAW. `/events/15318167` (Royals vs White Sox, 2026-09-24) at 390px, Bigger
 * Picture:
 *
 *   CHICAGO WHITE SOX VS. KANSAS CITY ROYALS (2)
 *     [KC]  Kansas City Royals Win  51%
 *     [WT]  Will there be a run scored in the …  /  Chicago White Sox Win  50%
 *   OTHER (1)   Kansas City 47%
 *   OTHER (1)   Chicago WS 54%
 *
 * Market 62155956 stores `Yes` / `No`. The server fabricated the two "Win" labels (fixed in
 * `resolve_binary_matchup_outcome_name`, backend guard in
 * `test_derivative_market_is_not_a_moneyline_6174.py`); this file covers the two render halves:
 *
 *   1. the group was headed with the MATCHUP because `extractStatCategory` read the text after the
 *      colon, and here the subject is the question BEFORE it — and "Yes" drew a face;
 *   2. the two OTHER cards are market 61827719, "Chicago WS vs Kansas City" — the game's own
 *      moneyline, which `isEventOwnMoneylineMarket` missed because "Chicago WS" is not a whole-word
 *      affix of "Chicago White Sox".
 *
 * Fixtures are the served rows, verbatim except that 62155956's legs carry their stored names.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import RelatedFutures from "@/components/RelatedFutures";
import { isEventOwnMoneylineMarket, labelNamesSide } from "@/lib/eventOwnMoneyline";
import type { RelatedFuture, RelatedFuturesResponse } from "@/lib/types";

const EVENT_ID = 15318167;
const HOME = "Kansas City Royals";
const AWAY = "Chicago White Sox";
const QUESTION =
  "Will there be a run scored in the first inning?: Chicago White Sox vs. Kansas City Royals";
const KALSHI_MONEYLINE = "Chicago WS vs Kansas City";

function row(over: Partial<RelatedFuture>): RelatedFuture {
  return {
    market_id: 62155956,
    market_name: QUESTION,
    display_category: "game_prop",
    market_tier: 5,
    category: "game_prop",
    source: "polymarket",
    outcome_id: 234826520,
    outcome_name: "Yes",
    probability: 0.495,
    american_odds: null,
    probability_change_24h: null,
    opening_probability: null,
    rank: null,
    relevance_score: 44,
    relevance_reason: "shifting",
    last_updated: null,
    next_update_expected: "",
    resolution_date: "2026-10-01T18:10:00+00:00",
    ...over,
  };
}

const YES = row({});
const NO = row({ outcome_id: 234826521, outcome_name: "No", probability: 0.505 });
const KALSHI_KC = row({
  market_id: 61827719,
  market_name: KALSHI_MONEYLINE,
  category: "championship",
  source: "kalshi",
  outcome_id: 233181224,
  outcome_name: "Kansas City",
  probability: 0.465,
});
const KALSHI_CWS = row({
  market_id: 61827719,
  market_name: KALSHI_MONEYLINE,
  category: "championship",
  source: "kalshi",
  outcome_id: 233181223,
  outcome_name: "Chicago WS",
  probability: 0.535,
});

let swrPayload: RelatedFuturesResponse;

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: swrPayload, error: undefined, isLoading: false, mutate: () => undefined }),
}));

function render(home: RelatedFuture[], away: RelatedFuture[]): string {
  swrPayload = {
    event_id: EVENT_ID,
    home_team: HOME,
    away_team: AWAY,
    home_team_futures: home,
    away_team_futures: away,
    series_markets: [],
    total_count: home.length + away.length,
    summary: null,
    event_status: "scheduled",
    box_score: null,
    league_context: null,
  } as RelatedFuturesResponse;
  return renderToStaticMarkup(
    React.createElement(RelatedFutures, { eventId: EVENT_ID, homeTeam: HOME, awayTeam: AWAY }),
  );
}

const text = (html: string) => html.replace(/<[^>]+>/g, "|");

describe("#8344 labelNamesSide — Kalshi's city-plus-initials spelling", () => {
  it.each([
    ["Chicago WS", "Chicago White Sox"],
    ["Los Angeles D", "Los Angeles Dodgers"],
    ["New York Y", "New York Yankees"],
    ["Chicago C", "Chicago Cubs"],
  ])("%s names %s", (label, team) => {
    expect(labelNamesSide(label, team)).toBe(true);
  });

  it.each([
    ["Chicago C", "Chicago White Sox"], // the other club in the same city
    ["Chicago WS", "Chicago Cubs"],
    ["WS", "Chicago White Sox"], // initials with no city name nothing
    ["Chicago W", "Chicago White Sox"], // partial initials are not the club
    ["Boston WS", "Chicago White Sox"],
  ])("%s does NOT name %s", (label, team) => {
    expect(labelNamesSide(label, team)).toBe(false);
  });

  it("makes the specimen the event's own moneyline, and another game's still is not", () => {
    expect(isEventOwnMoneylineMarket(KALSHI_MONEYLINE, HOME, AWAY)).toBe(true);
    expect(isEventOwnMoneylineMarket("Chicago WS vs St. Louis", HOME, AWAY)).toBe(false);
    expect(isEventOwnMoneylineMarket("Chicago WS vs Kansas City: Total Runs", HOME, AWAY)).toBe(
      false,
    );
  });
});

describe("#8344 the rail, rendered from the specimen rows", () => {
  const html = render([YES, NO, KALSHI_KC], [KALSHI_CWS]);
  const shown = text(html);

  it("heads the Yes/No legs with their question, not the matchup", () => {
    expect(shown).toContain("|Will there be a run scored in the first inning?|");
    expect(shown).not.toMatch(/\|Chicago White Sox vs\. Kansas City Royals\|/i);
  });

  it("labels the legs Yes and No, and neither claims a team won", () => {
    expect(shown).toContain("|Yes|");
    expect(shown).toContain("|No|");
    expect(shown).not.toMatch(/ Win\|/);
  });

  it("draws no face for a Yes/No leg", () => {
    expect(shown).not.toMatch(/\|YE\||\|NO\|/);
  });

  it("drops the game's own Kalshi moneyline — no orphan OTHER cards", () => {
    expect(shown).not.toContain("|Chicago WS|");
    expect(shown).not.toContain("|Kansas City|");
    expect(shown).not.toMatch(/\|Other\|/i);
  });

  it("a question that contains a stat word keeps the whole question as its heading", () => {
    const hr = "Will there be 2+ home runs?: Chicago White Sox vs. Kansas City Royals";
    const shown2 = text(
      render([row({ market_name: hr }), row({ market_name: hr, outcome_id: 9, outcome_name: "No" })], []),
    );
    expect(shown2).toContain("|Will there be 2+ home runs?|");
    expect(shown2).not.toContain("|Home Runs|");
  });

  it("CONTROL: another game's Kalshi matchup on the same rail still draws", () => {
    const other = row({
      market_id: 1,
      market_name: "Chicago WS vs St. Louis: Total Runs",
      source: "kalshi",
      outcome_id: 2,
      outcome_name: "Over 8.5",
      probability: 0.52,
    });
    expect(text(render([YES, NO], [other]))).toContain("|Over||8.5|");
  });
});
