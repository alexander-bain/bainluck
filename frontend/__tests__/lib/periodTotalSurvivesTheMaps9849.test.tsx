/**
 * #9849, the web half — a one-period total leaves the event page once it says
 * what it asks.
 *
 * PR #9851 made `GET /api/events/{id}/game-markets` serve Kalshi's threshold
 * label on `other` rows ("Over 1.5 runs in the 1st inning" where it served a bare
 * `Yes`). The served half passed its after-check (2026-09-30 17:13Z). The page did
 * not: `isRedundantWithMarketMaps` reads "total" in the name plus "over" in the
 * outcome as "the runs map already drew this line", so the card that used to read
 * `Yes · Lost` vanished instead of reading `Over 1.5 runs in the 1st inning · Lost`.
 * The runs maps draw the game total and the first five innings — never one
 * inning — and the 2nd–8th inning totals had been hidden the same way all along.
 *
 * The fixture is the VERBATIM `other[]` of `/events/15320289` (Phillies @ Braves,
 * WC Game 1, final), read 2026-09-30 17:13Z, trimmed to the fields this module
 * reads.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import SpecialEventMarkets from "../../components/SpecialEventMarkets";
import type { GameMarketsResponse } from "@/lib/api";
import {
  buildMarketSection,
  findWinProbMarkets,
  isPeriodTotalMarket,
  isRedundantWithMarketMaps,
  type OtherMarketRow,
} from "../../lib/otherMarketGroups";

const WIRE: OtherMarketRow[] = [
  {"market_name": "Will there be a run scored in the first inning?: Philadelphia Phillies vs. Atlanta Braves", "outcome_name": "Yes", "probability": 1.0, "source": "polymarket", "is_winner": true, "resolution_source": "api_settlement", "_market_id": 63031612},
  {"market_name": "Will there be a run scored in the first inning?: Philadelphia Phillies vs. Atlanta Braves", "outcome_name": "No", "probability": null, "source": "polymarket", "is_winner": false, "resolution_source": "api_settlement", "_market_id": 63031612},
  {"market_name": "Game 1: Philadelphia vs Atlanta", "outcome_name": "Atlanta", "probability": 1.0, "source": "kalshi", "is_winner": true, "resolution_source": "api_settlement", "_market_id": 62924885},
  {"market_name": "Game 1: Philadelphia vs Atlanta", "outcome_name": "Philadelphia", "probability": null, "source": "kalshi", "is_winner": false, "resolution_source": "api_settlement", "_market_id": 62924885},
  {"market_name": "Philadelphia vs Atlanta: First Inning Run", "outcome_name": "Yes", "probability": 0.99, "source": "kalshi", "is_winner": true, "resolution_source": "api_settlement", "_market_id": 62972591},
  {"market_name": "Philadelphia vs Atlanta: Outs Recorded", "outcome_name": "Yes", "probability": 1.0, "source": "kalshi", "is_winner": true, "resolution_source": "api_settlement", "_market_id": 62972593},
  {"market_name": "Philadelphia vs Atlanta: 3rd Inning Total", "outcome_name": "Over 0.5 runs in the 3rd inning", "probability": 0.01, "source": "kalshi", "is_winner": false, "resolution_source": "api_settlement", "_market_id": 63153638},
  {"market_name": "Philadelphia vs Atlanta: 6th Inning Total", "outcome_name": "Over 0.5 runs in the 6th inning", "probability": 1.0, "source": "kalshi", "is_winner": true, "resolution_source": "api_settlement", "_market_id": 63153635},
  {"market_name": "Philadelphia vs Atlanta: 2nd Inning Total", "outcome_name": "Over 0.5 runs in the 2nd inning", "probability": 0.99, "source": "kalshi", "is_winner": true, "resolution_source": "api_settlement", "_market_id": 63153639},
  {"market_name": "Philadelphia vs Atlanta: 7th Inning Total", "outcome_name": "Over 0.5 runs in the 7th inning", "probability": 1.0, "source": "kalshi", "is_winner": true, "resolution_source": "api_settlement", "_market_id": 63153634},
  {"market_name": "Philadelphia vs Atlanta: 8th Inning Total", "outcome_name": "Over 0.5 runs in the 8th inning", "probability": 1.0, "source": "kalshi", "is_winner": true, "resolution_source": "api_settlement", "_market_id": 63153633},
  {"market_name": "Philadelphia vs Atlanta: RBIs", "outcome_name": "Ronald Acuña Jr.: 1+", "probability": null, "source": "kalshi", "is_winner": false, "resolution_source": "api_settlement", "_market_id": 62972592},
  {"market_name": "Philadelphia vs Atlanta: Walks Allowed", "outcome_name": "Jesús Luzardo: 1+", "probability": 1.0, "source": "kalshi", "is_winner": true, "resolution_source": "api_settlement", "_market_id": 63153621},
  {"market_name": "Philadelphia vs Atlanta: 1st Inning Winner", "outcome_name": "Philadelphia wins 1st inning", "probability": 0.99, "source": "kalshi", "is_winner": true, "resolution_source": "api_settlement", "_market_id": 63153631},
  {"market_name": "Philadelphia vs Atlanta: 1st Inning Winner", "outcome_name": "Tie 1st inning", "probability": 0.01, "source": "kalshi", "is_winner": false, "resolution_source": "api_settlement", "_market_id": 63153631},
  {"market_name": "Philadelphia vs Atlanta: 1st Inning Winner", "outcome_name": "Atlanta wins 1st inning", "probability": 0.01, "source": "kalshi", "is_winner": false, "resolution_source": "api_settlement", "_market_id": 63153631},
  {"market_name": "Philadelphia vs Atlanta: 1st Inning Total", "outcome_name": "Over 1.5 runs in the 1st inning", "probability": 0.01, "source": "kalshi", "is_winner": false, "resolution_source": "api_settlement", "_market_id": 63153640},
  {"market_name": "Philadelphia vs Atlanta: 3rd Inning Total", "outcome_name": "Over 1.5 runs in the 3rd inning", "probability": 0.01, "source": "kalshi", "is_winner": false, "resolution_source": "api_settlement", "_market_id": 63153638},
  {"market_name": "Philadelphia vs Atlanta: 6th Inning Total", "outcome_name": "Over 1.5 runs in the 6th inning", "probability": null, "source": "kalshi", "is_winner": false, "resolution_source": "api_settlement", "_market_id": 63153635},
  {"market_name": "Philadelphia vs Atlanta: 2nd Inning Total", "outcome_name": "Over 1.5 runs in the 2nd inning", "probability": 0.01, "source": "kalshi", "is_winner": false, "resolution_source": "api_settlement", "_market_id": 63153639},
  {"market_name": "Philadelphia vs Atlanta: 7th Inning Total", "outcome_name": "Over 1.5 runs in the 7th inning", "probability": 1.0, "source": "kalshi", "is_winner": true, "resolution_source": "api_settlement", "_market_id": 63153634},
  {"market_name": "Philadelphia vs Atlanta: 8th Inning Total", "outcome_name": "Over 1.5 runs in the 8th inning", "probability": 1.0, "source": "kalshi", "is_winner": true, "resolution_source": "api_settlement", "_market_id": 63153633},
  {"market_name": "Philadelphia vs Atlanta: RBIs", "outcome_name": "Ronald Acuña Jr.: 2+", "probability": null, "source": "kalshi", "is_winner": false, "resolution_source": "api_settlement", "_market_id": 62972592},
  {"market_name": "Philadelphia vs Atlanta: 2nd Inning Winner", "outcome_name": "Atlanta wins 2nd inning", "probability": 0.99, "source": "kalshi", "is_winner": true, "resolution_source": "api_settlement", "_market_id": 63153630},
  {"market_name": "Philadelphia vs Atlanta: 2nd Inning Winner", "outcome_name": "Philadelphia wins 2nd inning", "probability": 0.01, "source": "kalshi", "is_winner": false, "resolution_source": "api_settlement", "_market_id": 63153630},
  {"market_name": "Philadelphia vs Atlanta: 2nd Inning Winner", "outcome_name": "Tie 2nd inning", "probability": 0.01, "source": "kalshi", "is_winner": false, "resolution_source": "api_settlement", "_market_id": 63153630},
  {"market_name": "Philadelphia vs Atlanta: Total Bases", "outcome_name": "Ronald Acuña Jr.: 2+", "probability": null, "source": "kalshi", "is_winner": false, "resolution_source": "api_settlement", "_market_id": 62972590},
  {"market_name": "Philadelphia vs Atlanta: First 3 Innings", "outcome_name": "Tie first 3 innings", "probability": 0.99, "source": "kalshi", "is_winner": true, "resolution_source": "api_settlement", "_market_id": 62972602},
  {"market_name": "Philadelphia vs Atlanta: First 3 Innings", "outcome_name": "Philadelphia wins first 3 innings", "probability": 0.01, "source": "kalshi", "is_winner": false, "resolution_source": "api_settlement", "_market_id": 62972602},
  {"market_name": "Philadelphia vs Atlanta: First 3 Innings", "outcome_name": "Atlanta wins first 3 innings", "probability": 0.01, "source": "kalshi", "is_winner": false, "resolution_source": "api_settlement", "_market_id": 62972602},
  {"market_name": "Philadelphia vs Atlanta: 3rd Inning Winner", "outcome_name": "Tie 3rd inning", "probability": 0.99, "source": "kalshi", "is_winner": true, "resolution_source": "api_settlement", "_market_id": 63153629},
  {"market_name": "Philadelphia vs Atlanta: 3rd Inning Winner", "outcome_name": "Philadelphia wins 3rd inning", "probability": 0.01, "source": "kalshi", "is_winner": false, "resolution_source": "api_settlement", "_market_id": 63153629},
  {"market_name": "Philadelphia vs Atlanta: 3rd Inning Winner", "outcome_name": "Atlanta wins 3rd inning", "probability": 0.01, "source": "kalshi", "is_winner": false, "resolution_source": "api_settlement", "_market_id": 63153629},
  {"market_name": "Philadelphia vs Atlanta: Total Bases", "outcome_name": "Ronald Acuña Jr.: 3+", "probability": null, "source": "kalshi", "is_winner": false, "resolution_source": "api_settlement", "_market_id": 62972590},
  {"market_name": "Philadelphia vs Atlanta: 4th Inning Winner", "outcome_name": "Tie 4th inning", "probability": 1.0, "source": "kalshi", "is_winner": true, "resolution_source": "api_settlement", "_market_id": 63153628},
  {"market_name": "Philadelphia vs Atlanta: 4th Inning Winner", "outcome_name": "Atlanta wins 4th inning", "probability": null, "source": "kalshi", "is_winner": false, "resolution_source": "api_settlement", "_market_id": 63153628},
  {"market_name": "Philadelphia vs Atlanta: 4th Inning Winner", "outcome_name": "Philadelphia wins 4th inning", "probability": null, "source": "kalshi", "is_winner": false, "resolution_source": "api_settlement", "_market_id": 63153628},
  {"market_name": "Philadelphia vs Atlanta: Total Bases", "outcome_name": "Ronald Acuña Jr.: 4+", "probability": null, "source": "kalshi", "is_winner": false, "resolution_source": "api_settlement", "_market_id": 62972590},
  {"market_name": "Philadelphia vs Atlanta: 5th Inning Winner", "outcome_name": "Tie 5th inning", "probability": 1.0, "source": "kalshi", "is_winner": true, "resolution_source": "api_settlement", "_market_id": 63153627},
  {"market_name": "Philadelphia vs Atlanta: 5th Inning Winner", "outcome_name": "Atlanta wins 5th inning", "probability": null, "source": "kalshi", "is_winner": false, "resolution_source": "api_settlement", "_market_id": 63153627},
  {"market_name": "Philadelphia vs Atlanta: 5th Inning Winner", "outcome_name": "Philadelphia wins 5th inning", "probability": null, "source": "kalshi", "is_winner": false, "resolution_source": "api_settlement", "_market_id": 63153627},
  {"market_name": "Philadelphia vs Atlanta: First 5 Innings", "outcome_name": "Tie first 5 innings", "probability": 1.0, "source": "kalshi", "is_winner": true, "resolution_source": "api_settlement", "_market_id": 62972601},
  {"market_name": "Philadelphia vs Atlanta: First 5 Innings", "outcome_name": "Atlanta wins first 5 innings", "probability": null, "source": "kalshi", "is_winner": false, "resolution_source": "api_settlement", "_market_id": 62972601},
  {"market_name": "Philadelphia vs Atlanta: First 5 Innings", "outcome_name": "Philadelphia wins first 5 innings", "probability": null, "source": "kalshi", "is_winner": false, "resolution_source": "api_settlement", "_market_id": 62972601},
  {"market_name": "Philadelphia vs Atlanta: Total Bases", "outcome_name": "Ronald Acuña Jr.: 5+", "probability": null, "source": "kalshi", "is_winner": false, "resolution_source": "api_settlement", "_market_id": 62972590},
  {"market_name": "Philadelphia vs Atlanta: 6th Inning Winner", "outcome_name": "Atlanta wins 6th inning", "probability": 1.0, "source": "kalshi", "is_winner": true, "resolution_source": "api_settlement", "_market_id": 63153626},
  {"market_name": "Philadelphia vs Atlanta: 6th Inning Winner", "outcome_name": "Tie 6th inning", "probability": null, "source": "kalshi", "is_winner": false, "resolution_source": "api_settlement", "_market_id": 63153626},
  {"market_name": "Philadelphia vs Atlanta: 6th Inning Winner", "outcome_name": "Philadelphia wins 6th inning", "probability": null, "source": "kalshi", "is_winner": false, "resolution_source": "api_settlement", "_market_id": 63153626},
  {"market_name": "Philadelphia vs Atlanta: First 7 Innings", "outcome_name": "Philadelphia wins first 7 innings", "probability": 1.0, "source": "kalshi", "is_winner": true, "resolution_source": "api_settlement", "_market_id": 62972598},
  {"market_name": "Philadelphia vs Atlanta: First 7 Innings", "outcome_name": "Atlanta wins first 7 innings", "probability": null, "source": "kalshi", "is_winner": false, "resolution_source": "api_settlement", "_market_id": 62972598},
  {"market_name": "Philadelphia vs Atlanta: First 7 Innings", "outcome_name": "Tie first 7 innings", "probability": null, "source": "kalshi", "is_winner": false, "resolution_source": "api_settlement", "_market_id": 62972598},
  {"market_name": "Philadelphia vs Atlanta: 7th Inning Winner", "outcome_name": "Philadelphia wins 7th inning", "probability": 1.0, "source": "kalshi", "is_winner": true, "resolution_source": "api_settlement", "_market_id": 63153625},
  {"market_name": "Philadelphia vs Atlanta: 7th Inning Winner", "outcome_name": "Atlanta wins 7th inning", "probability": null, "source": "kalshi", "is_winner": false, "resolution_source": "api_settlement", "_market_id": 63153625},
  {"market_name": "Philadelphia vs Atlanta: 7th Inning Winner", "outcome_name": "Tie 7th inning", "probability": null, "source": "kalshi", "is_winner": false, "resolution_source": "api_settlement", "_market_id": 63153625},
  {"market_name": "Philadelphia vs Atlanta: 8th Inning Winner", "outcome_name": "Atlanta wins 8th inning", "probability": 1.0, "source": "kalshi", "is_winner": true, "resolution_source": "api_settlement", "_market_id": 63153624},
  {"market_name": "Philadelphia vs Atlanta: 8th Inning Winner", "outcome_name": "Philadelphia wins 8th inning", "probability": null, "source": "kalshi", "is_winner": false, "resolution_source": "api_settlement", "_market_id": 63153624},
  {"market_name": "Philadelphia vs Atlanta: 8th Inning Winner", "outcome_name": "Tie 8th inning", "probability": null, "source": "kalshi", "is_winner": false, "resolution_source": "api_settlement", "_market_id": 63153624},
  {"market_name": "Philadelphia vs Atlanta: 9th Inning Winner", "outcome_name": "Tie 9th inning", "probability": 1.0, "source": "kalshi", "is_winner": true, "resolution_source": "api_settlement", "_market_id": 63153623},
  {"market_name": "Philadelphia vs Atlanta: 9th Inning Winner", "outcome_name": "Philadelphia wins 9th inning", "probability": null, "source": "kalshi", "is_winner": false, "resolution_source": "api_settlement", "_market_id": 63153623},
  {"market_name": "Philadelphia vs Atlanta: 9th Inning Winner", "outcome_name": "Atlanta wins 9th inning", "probability": null, "source": "kalshi", "is_winner": false, "resolution_source": "api_settlement", "_market_id": 63153623},
];

function renderedCards(rows: OtherMarketRow[]) {
  return buildMarketSection(rows).categories.flatMap((c) => c.cards);
}

function cardNamed(rows: OtherMarketRow[], fragment: string) {
  return renderedCards(rows).find((c) => c.name.includes(fragment));
}

describe("#9849 a one-period total stays on the event page", () => {
  it("renders the specimen card with the label the route serves", () => {
    const card = cardNamed(WIRE, "1st Inning Total");
    expect(card).toBeDefined();
    expect(card!.outcomes.map((o) => o.label)).toEqual(["Over 1.5 runs in the 1st inning"]);
  });

  it("renders the 2nd inning total too, whose two lines sum to one", () => {
    // Over 0.5 at 0.99 / Over 1.5 at 0.01 — the shape `findWinProbMarkets`
    // takes for the moneyline. Its 3rd-inning sibling (0.01 / 0.01) is the control
    // that survives either way.
    expect(findWinProbMarkets(WIRE).has("Philadelphia vs Atlanta: 2nd Inning Total")).toBe(false);
    expect(cardNamed(WIRE, "2nd Inning Total")).toBeDefined();
    expect(cardNamed(WIRE, "3rd Inning Total")).toBeDefined();
  });

  it("renders every inning total the wire carries", () => {
    const names = renderedCards(WIRE).map((c) => c.name).filter((n) => /Inning Total/.test(n));
    expect(names.sort()).toEqual([
      "Philadelphia vs Atlanta: 1st Inning Total",
      "Philadelphia vs Atlanta: 2nd Inning Total",
      "Philadelphia vs Atlanta: 3rd Inning Total",
      "Philadelphia vs Atlanta: 6th Inning Total",
      "Philadelphia vs Atlanta: 7th Inning Total",
      "Philadelphia vs Atlanta: 8th Inning Total",
    ]);
  });

  it("still hides the totals the maps DO draw", () => {
    for (const market_name of [
      "Philadelphia vs Atlanta: Total Runs",
      "1st 5 Innings Total: O/U 4.5",
      "Philadelphia vs Atlanta: F5 Innings Total",
      "Kansas City vs Denver: 1st Half Total",
      "Total: O/U 8.5",
    ]) {
      expect(isPeriodTotalMarket(market_name)).toBe(false);
      expect(isRedundantWithMarketMaps({ market_name, outcome_name: "Over 4.5" })).toBe(true);
    }
  });

  it("names one-period totals in both name orders", () => {
    for (const name of [
      "Philadelphia vs Atlanta: 1st Inning Total",
      "Set 1 Total Games: Swiatek vs Zheng",
      "Vitality vs FaZe: Map 2 Total Rounds",
      "Kansas City vs Denver: 3rd Quarter Total",
    ]) {
      expect(isPeriodTotalMarket(name)).toBe(true);
    }
  });

  it("prints the label in the rendered section, on a settled page", () => {
    const data = {
      event_id: 15320289,
      home_team: "Atlanta Braves",
      away_team: "Philadelphia Phillies",
      home_score: 5,
      away_score: 3,
      status: "completed",
      totals: [],
      player_props: [],
      team_totals: [],
      spreads: [],
      period_markets: [],
      matchups: [],
      other: WIRE,
      pace: null,
    } as unknown as GameMarketsResponse;
    const html = renderToStaticMarkup(
      React.createElement(SpecialEventMarkets, { data, eventStatus: "completed" }),
    );
    expect(html).toContain("1st Inning Total");
    expect(html).toContain("Over 1.5 runs in the 1st inning");
  });
});
