import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  buildSoccerEventCards,
  buildSoccerExactScoreCard,
  buildSoccerThreeWayCard,
  parseSoccerExactScoreOutcome,
  soccerCardsApply,
} from "@/lib/soccerEventCards";
import { cardTitle } from "@/lib/nflEventCardDeck";
import {
  buildStoryCardDetailsSheetProps,
  EventCardView,
  type CardTeams,
} from "@/components/event/NFLEventCards";

const NOW_MS = Date.parse("2026-11-05T20:00:00Z");

const TEAMS: CardTeams = {
  awayName: "Werder Bremen",
  homeName: "Borussia Dortmund",
  awayShort: "Bremen",
  homeShort: "Dortmund",
  awayColor: "#1D9053",
  homeColor: "#FDE100",
};

describe("#11974 Step E6c — Soccer story cards in mark grammar behind ?atlas=1", () => {
  it("gates soccerCardsApply strictly on atlasMode and soccer_* sport keys", () => {
    expect(soccerCardsApply("soccer_epl", true)).toBe(true);
    expect(soccerCardsApply("soccer_germany_dfb_pokal", true)).toBe(true);
    expect(soccerCardsApply("soccer_epl", false)).toBe(false);
    expect(soccerCardsApply("icehockey_nhl", true)).toBe(false);
    expect(soccerCardsApply(null, true)).toBe(false);
  });

  it("builds a three-way match outcome card without normalizing quotes and refuses two-way markets without an explicit draw leg", () => {
    // 1. Refuse a 2-way market (never invent draw = 1 - home - away)
    const twoWay = buildSoccerThreeWayCard({
      otherMarkets: [
        {
          market_name: "Hull City vs Everton",
          outcome_name: "Hull City",
          probability: 0.35,
          observed_at: "2026-11-05T19:55:00Z",
          source: "kalshi",
        },
        {
          market_name: "Hull City vs Everton",
          outcome_name: "Everton",
          probability: 0.65,
          observed_at: "2026-11-05T19:55:00Z",
          source: "kalshi",
        },
      ],
      status: "scheduled",
      commenceTime: "2026-11-05T22:00:00Z",
      homeTeam: "Hull City",
      awayTeam: "Everton",
      homeShort: "Hull City",
      awayShort: "Everton",
      nowMs: NOW_MS,
    });
    expect(twoWay).toBeNull();

    // 2. Build a 3-way market with unnormalized quotes summing to 99.5%
    const threeWay = buildSoccerThreeWayCard({
      otherMarkets: [
        {
          market_name: "Hull City vs Everton",
          outcome_name: "Hull City",
          probability: 0.255,
          observed_at: "2026-11-05T19:55:00Z",
          source: "kalshi",
        },
        {
          market_name: "Hull City vs Everton",
          outcome_name: "Tie",
          probability: 0.285,
          observed_at: "2026-11-05T19:55:00Z",
          source: "kalshi",
        },
        {
          market_name: "Hull City vs Everton",
          outcome_name: "Everton",
          probability: 0.455,
          observed_at: "2026-11-05T19:55:00Z",
          source: "kalshi",
        },
      ],
      status: "scheduled",
      commenceTime: "2026-11-05T22:00:00Z",
      homeTeam: "Hull City",
      awayTeam: "Everton",
      homeShort: "Hull City",
      awayShort: "Everton",
      nowMs: NOW_MS,
    });

    expect(threeWay).not.toBeNull();
    expect(threeWay!.legs.map((l) => l.role)).toEqual(["home", "draw", "away"]);
    expect(threeWay!.legs.map((l) => l.quotedChance)).toEqual([0.255, 0.285, 0.455]);
    expect(threeWay!.quotedSum).toBeCloseTo(0.995, 5);

    const html = renderToStaticMarkup(
      <EventCardView
        card={threeWay!}
        teams={TEAMS}
        selection={{}}
        onSelect={() => {}}
        atlasMode
        onDetails={() => {}}
      />,
    );
    expect(html).toContain('data-testid="soccer-three-way-card"');
    expect(html).toContain("A draw is a real third outcome");
    expect(html).toContain("Recorded three-way quotes total 99.5%");
  });

  it("parses Polymarket and Kalshi exact-score outcomes into (homeGoals, awayGoals) coordinates without inventing unlisted cells", () => {
    expect(
      parseSoccerExactScoreOutcome(
        "BV Borussia 09 Dortmund 3 - 2 SV Werder Bremen",
        "Borussia Dortmund",
        "Werder Bremen",
        "Dortmund",
        "Bremen",
      ),
    ).toEqual({ homeGoals: 3, awayGoals: 2 });

    expect(
      parseSoccerExactScoreOutcome(
        "Werder Bremen wins 2-1",
        "Borussia Dortmund",
        "Werder Bremen",
        "Dortmund",
        "Bremen",
      ),
    ).toEqual({ homeGoals: 1, awayGoals: 2 });

    expect(
      parseSoccerExactScoreOutcome(
        "Draw 1-1",
        "Borussia Dortmund",
        "Werder Bremen",
        "Dortmund",
        "Bremen",
      ),
    ).toEqual({ homeGoals: 1, awayGoals: 1 });

    const exactCard = buildSoccerExactScoreCard({
      otherMarkets: [
        {
          market_name: "Borussia Dortmund vs Werder Bremen: Correct Score",
          outcome_name: "Borussia Dortmund wins 3-2",
          probability: 1.0,
          pregame_mark: 0.05,
          is_winner: true,
          source: "kalshi",
        },
        {
          market_name: "Borussia Dortmund vs Werder Bremen: Correct Score",
          outcome_name: "Draw 1-1",
          probability: 0.0,
          pregame_mark: 0.095,
          is_winner: false,
          source: "kalshi",
        },
        {
          market_name: "Borussia Dortmund vs Werder Bremen: Correct Score",
          outcome_name: "Borussia Dortmund wins 2-1",
          probability: 0.0,
          pregame_mark: 0.11,
          is_winner: false,
          source: "kalshi",
        },
        {
          market_name: "Borussia Dortmund vs Werder Bremen: Correct Score",
          outcome_name: "Werder Bremen wins 1-0",
          probability: 0.0,
          pregame_mark: 0.04,
          is_winner: false,
          source: "kalshi",
        },
      ],
      status: "completed",
      commenceTime: "2026-11-05T17:00:00Z",
      homeTeam: "Borussia Dortmund",
      awayTeam: "Werder Bremen",
      homeShort: "Dortmund",
      awayShort: "Bremen",
      nowMs: NOW_MS,
    });

    expect(exactCard).not.toBeNull();
    expect(exactCard!.defaultSelectedKey).toBe("3-2");
    expect(exactCard!.cells.find((c) => c.key === "3-2")?.chance).toBe(0.05);
    expect(exactCard!.cells.find((c) => c.key === "3-2")?.result).toBe("won");
    expect(exactCard!.cells.find((c) => c.key === "0-3")).toBeUndefined();
  });

  it("builds a Goal expectations ladder card from full-game goal thresholds and wires AtlasDetailsSheet props", () => {
    const cards = buildSoccerEventCards({
      sportKey: "soccer_germany_dfb_pokal",
      atlasMode: true,
      status: "completed",
      commenceTime: "2026-11-05T17:00:00Z",
      homeTeam: "Borussia Dortmund",
      awayTeam: "Werder Bremen",
      homeShort: "Dortmund",
      awayShort: "Bremen",
      homeScore: 3,
      awayScore: 2,
      nowMs: NOW_MS,
      gameMarkets: {
        other: [
          {
            market_name: "BV Borussia 09 Dortmund vs. SV Werder Bremen",
            outcome_name: "BV Borussia 09 Dortmund",
            probability: 1.0,
            pregame_mark: 0.68,
            is_winner: true,
            source: "polymarket",
          },
          {
            market_name: "BV Borussia 09 Dortmund vs. SV Werder Bremen",
            outcome_name: "Draw (BV Borussia 09 Dortmund vs. SV Werder Bremen)",
            probability: 0.0,
            pregame_mark: 0.19,
            is_winner: false,
            source: "polymarket",
          },
          {
            market_name: "BV Borussia 09 Dortmund vs. SV Werder Bremen",
            outcome_name: "SV Werder Bremen",
            probability: 0.0,
            pregame_mark: 0.13,
            is_winner: false,
            source: "polymarket",
          },
          {
            market_name: "Borussia Dortmund vs Werder Bremen: Correct Score",
            outcome_name: "Borussia Dortmund wins 3-2",
            probability: 1.0,
            pregame_mark: 0.05,
            is_winner: true,
            source: "kalshi",
          },
          {
            market_name: "Borussia Dortmund vs Werder Bremen: Correct Score",
            outcome_name: "Draw 1-1",
            probability: 0.0,
            pregame_mark: 0.095,
            is_winner: false,
            source: "kalshi",
          },
          {
            market_name: "Borussia Dortmund vs Werder Bremen: Correct Score",
            outcome_name: "Borussia Dortmund wins 2-1",
            probability: 0.0,
            pregame_mark: 0.11,
            is_winner: false,
            source: "kalshi",
          },
          {
            market_name: "Borussia Dortmund vs Werder Bremen: Correct Score",
            outcome_name: "Werder Bremen wins 1-0",
            probability: 0.0,
            pregame_mark: 0.04,
            is_winner: false,
            source: "kalshi",
          },
        ],
        totals: [
          {
            threshold: 1.5,
            over_probability: 1.0,
            pregame_mark: 0.89,
            is_winner: true,
            market_type: "game_total",
            market_name: "Over 1.5 goals",
            source: "kalshi",
          },
          {
            threshold: 2.5,
            over_probability: 1.0,
            pregame_mark: 0.72,
            is_winner: true,
            market_type: "game_total",
            market_name: "Over 2.5 goals",
            source: "kalshi",
          },
          {
            threshold: 3.5,
            over_probability: 1.0,
            pregame_mark: 0.51,
            is_winner: true,
            market_type: "game_total",
            market_name: "Over 3.5 goals",
            source: "kalshi",
          },
        ],
      },
    });

    expect(cards.map((c) => c.id)).toEqual(["soccer:threeWay", "soccer:exactScore", "total"]);
    expect(cardTitle(cards[0])).toBe("Three-way outcome");
    expect(cardTitle(cards[1])).toBe("Exact score");
    expect(cardTitle(cards[2])).toBe("Goal expectations");

    const exactHtml = renderToStaticMarkup(
      <EventCardView
        card={cards[1]}
        teams={TEAMS}
        selection={{ "soccer:exactScore": "1-1" }}
        onSelect={() => {}}
        atlasMode
        onDetails={() => {}}
      />,
    );
    expect(exactHtml).toContain('data-testid="soccer-exact-score-card"');
    expect(exactHtml).toContain("The exact-score landscape");
    expect(exactHtml).toContain("Dortmund 1 – 1 Bremen");

    const sheetProps = buildStoryCardDetailsSheetProps({
      card: cards[1],
      rowId: "3-2",
      teams: TEAMS,
    });
    expect(sheetProps).toMatchObject({
      subjectName: "Dortmund 3 – 2 Bremen",
      marketTitle: "Borussia Dortmund vs Werder Bremen: Correct Score",
      isSettled: true,
      settledResult: "won",
      openingProbability: 0.05,
      source: "kalshi",
    });
  });
});
