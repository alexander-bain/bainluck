import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  buildSoccerEventCards,
  buildSoccerExactScoreCard,
  buildSoccerGoalTotalCard,
  buildSoccerThreeWayCard,
  parseSoccerExactScoreOutcome,
  soccerCardsApply,
} from "@/lib/soccerEventCards";
import { MATRIX_CONTRACT } from "@/lib/nbaEventCards";
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
    expect(html).toContain("Recorded three-way quotes total 100%");
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
          resolution_source: "exchange_settlement",
          source: "kalshi",
        },
        {
          market_name: "Borussia Dortmund vs Werder Bremen: Correct Score",
          outcome_name: "Draw 1-1",
          probability: 0.0,
          pregame_mark: 0.095,
          is_winner: false,
          resolution_source: "exchange_settlement",
          source: "kalshi",
        },
        {
          market_name: "Borussia Dortmund vs Werder Bremen: Correct Score",
          outcome_name: "Borussia Dortmund wins 2-1",
          probability: 0.0,
          pregame_mark: 0.11,
          is_winner: false,
          resolution_source: "exchange_settlement",
          source: "kalshi",
        },
        {
          market_name: "Borussia Dortmund vs Werder Bremen: Correct Score",
          outcome_name: "Werder Bremen wins 1-0",
          probability: 0.0,
          pregame_mark: 0.04,
          is_winner: false,
          resolution_source: "exchange_settlement",
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
            resolution_source: "exchange_settlement",
            source: "polymarket",
          },
          {
            market_name: "BV Borussia 09 Dortmund vs. SV Werder Bremen",
            outcome_name: "Draw (BV Borussia 09 Dortmund vs. SV Werder Bremen)",
            probability: 0.0,
            pregame_mark: 0.19,
            is_winner: false,
            resolution_source: "exchange_settlement",
            source: "polymarket",
          },
          {
            market_name: "BV Borussia 09 Dortmund vs. SV Werder Bremen",
            outcome_name: "SV Werder Bremen",
            probability: 0.0,
            pregame_mark: 0.13,
            is_winner: false,
            resolution_source: "exchange_settlement",
            source: "polymarket",
          },
          {
            market_name: "Borussia Dortmund vs Werder Bremen: Correct Score",
            outcome_name: "Borussia Dortmund wins 3-2",
            probability: 1.0,
            pregame_mark: 0.05,
            is_winner: true,
            resolution_source: "exchange_settlement",
            source: "kalshi",
          },
          {
            market_name: "Borussia Dortmund vs Werder Bremen: Correct Score",
            outcome_name: "Draw 1-1",
            probability: 0.0,
            pregame_mark: 0.095,
            is_winner: false,
            resolution_source: "exchange_settlement",
            source: "kalshi",
          },
          {
            market_name: "Borussia Dortmund vs Werder Bremen: Correct Score",
            outcome_name: "Borussia Dortmund wins 2-1",
            probability: 0.0,
            pregame_mark: 0.11,
            is_winner: false,
            resolution_source: "exchange_settlement",
            source: "kalshi",
          },
          {
            market_name: "Borussia Dortmund vs Werder Bremen: Correct Score",
            outcome_name: "Werder Bremen wins 1-0",
            probability: 0.0,
            pregame_mark: 0.04,
            is_winner: false,
            resolution_source: "exchange_settlement",
            source: "kalshi",
          },
        ],
        totals: [
          {
            threshold: 1.5,
            over_probability: 1.0,
            pregame_mark: 0.89,
            is_winner: true,
            resolution_source: "exchange_settlement",
            market_type: "game_total",
            market_name: "Over 1.5 goals",
            source: "kalshi",
          },
          {
            threshold: 2.5,
            over_probability: 1.0,
            pregame_mark: 0.72,
            is_winner: true,
            resolution_source: "exchange_settlement",
            market_type: "game_total",
            market_name: "Over 2.5 goals",
            source: "kalshi",
          },
          {
            threshold: 3.5,
            over_probability: 1.0,
            pregame_mark: 0.51,
            is_winner: true,
            resolution_source: "exchange_settlement",
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
    expect(exactHtml).toContain(">10%</button>");
    expect(exactHtml).not.toContain(">9.5<");

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
      sourceCount: 1,
    });
  });

  it("de-duplicates candidates by source when both game_question_matrix and gameMarkets.other describe the same venue's market", () => {
    const sameSourceThreeWay = buildSoccerThreeWayCard({
      gameQuestionMatrix: {
        contract: MATRIX_CONTRACT,
        questions: [
          {
            question_key: "q:soccer:3way",
            kind: "categorical",
            label: "Match Winner",
            market_name: "Match Winner",
            typing: { state: "typed" },
            period: { key: "full_game" },
            options: [
              {
                option_key: "o:home",
                label: "Borussia Dortmund",
                contributor_outcome_ids: [101],
                published: { value_state: "result", source: "kalshi", observed_at: "2026-11-05T19:00:00Z" },
                pregame_reading: {
                  state: "available",
                  reason: null,
                  basis: "pregame_pin",
                  probability: 0.65,
                  observed_at: "2026-11-05T16:50:00Z",
                  outcome_id: 101,
                },
                result: { state: "won" },
              },
              {
                option_key: "o:draw",
                label: "Draw",
                contributor_outcome_ids: [102],
                published: { value_state: "result", source: "kalshi", observed_at: "2026-11-05T19:00:00Z" },
                pregame_reading: {
                  state: "available",
                  reason: null,
                  basis: "pregame_pin",
                  probability: 0.2,
                  observed_at: "2026-11-05T16:50:00Z",
                  outcome_id: 102,
                },
                result: { state: "lost" },
              },
              {
                option_key: "o:away",
                label: "Werder Bremen",
                contributor_outcome_ids: [103],
                published: { value_state: "result", source: "kalshi", observed_at: "2026-11-05T19:00:00Z" },
                pregame_reading: {
                  state: "available",
                  reason: null,
                  basis: "pregame_pin",
                  probability: 0.15,
                  observed_at: "2026-11-05T16:50:00Z",
                  outcome_id: 103,
                },
                result: { state: "lost" },
              },
            ],
          },
        ],
      },
      otherMarkets: [
        {
          _market_id: 99,
          market_name: "Match Winner",
          outcome_name: "Borussia Dortmund",
          pregame_mark: 0.65,
          is_winner: true,
          resolution_source: "exchange_settlement",
          source: "kalshi",
        },
        {
          _market_id: 99,
          market_name: "Match Winner",
          outcome_name: "Draw",
          pregame_mark: 0.2,
          is_winner: false,
          resolution_source: "exchange_settlement",
          source: "kalshi",
        },
        {
          _market_id: 99,
          market_name: "Match Winner",
          outcome_name: "Werder Bremen",
          pregame_mark: 0.15,
          is_winner: false,
          resolution_source: "exchange_settlement",
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

    expect(sameSourceThreeWay).not.toBeNull();
    expect(sameSourceThreeWay?.source).toBe("kalshi");
    expect(sameSourceThreeWay?.sourceCount).toBe(1);
    expect(sameSourceThreeWay?.legs.map((l) => l.pregameChance)).toEqual([0.65, 0.2, 0.15]);
  });

  it("after full-time, reads only admitted pregame_reading on soccer goal-total ladders and withholds unblended probabilities when multiple unblended sources price a three-way market (#11125 contract)", () => {
    const gameQuestionMatrix = {
      contract: MATRIX_CONTRACT,
      questions: [1.5, 2.5, 3.5, 4.5].map((line, idx) => ({
        question_key: `q:soccer:goals:${line}`,
        kind: "count_threshold",
        label: `Total Goals Over/Under ${line}`,
        market_name: `Total Goals O/U ${line}`,
        typing: { state: "typed" },
        quantity: { key: "goals" },
        subject: { side: "game" },
        period: { key: "full_game" },
        predicate: { relation: "ge", line },
        options: [
          {
            option_key: `o:soccer:goals:${line}`,
            label: `Over ${line} goals`,
            side: "over",
            contributor_outcome_ids: idx === 3 ? [603, 604] : [600 + idx],
            published: { value_state: "result", source: "kalshi", observed_at: "2026-11-05T19:00:00Z" },
            comparison: {
              state: "comparable",
              baseline: {
                basis: "pregame_pin",
                probability: 0.85 - idx * 0.2,
                observed_at: "2026-11-05T16:50:00Z",
              },
            },
            pregame_reading:
              idx === 3
                ? { state: "unavailable", reason: "multi_contributor" }
                : {
                    state: "available",
                    reason: null,
                    basis: "pregame_pin",
                    probability: 0.85 - idx * 0.2,
                    observed_at: "2026-11-05T16:50:00Z",
                    outcome_id: 600 + idx,
                  },
            result: { state: "won" },
          },
        ],
      })),
    };

    const totalCard = buildSoccerGoalTotalCard({
      gameQuestionMatrix,
      status: "completed",
      commenceTime: "2026-11-05T17:00:00Z",
      homeScore: 3,
      awayScore: 2,
      homeShort: "Dortmund",
      awayShort: "Bremen",
      nowMs: NOW_MS,
    });
    expect(totalCard).not.toBeNull();
    const unpinnedLine = totalCard?.points.find((p) => p.x === 4.5);
    expect(unpinnedLine?.chance).toBeNull();
    expect(unpinnedLine?.detail.baseline).toBeNull();

    // Multi-source unblended three-way market withholds pregameChance rather than picking one source
    const multiThreeWay = buildSoccerThreeWayCard({
      otherMarkets: [
        {
          _market_id: 1,
          market_name: "Borussia Dortmund vs Werder Bremen",
          outcome_name: "Borussia Dortmund",
          pregame_mark: 0.66,
          is_winner: true,
          resolution_source: "kalshi",
          source: "kalshi",
        },
        {
          _market_id: 1,
          market_name: "Borussia Dortmund vs Werder Bremen",
          outcome_name: "Draw",
          pregame_mark: 0.20,
          is_winner: false,
          resolution_source: "kalshi",
          source: "kalshi",
        },
        {
          _market_id: 1,
          market_name: "Borussia Dortmund vs Werder Bremen",
          outcome_name: "Werder Bremen",
          pregame_mark: 0.14,
          is_winner: false,
          resolution_source: "kalshi",
          source: "kalshi",
        },
        {
          _market_id: 2,
          market_name: "BV Borussia 09 Dortmund vs. SV Werder Bremen",
          outcome_name: "BV Borussia 09 Dortmund",
          pregame_mark: 0.69,
          is_winner: true,
          resolution_source: "polymarket",
          source: "polymarket",
        },
        {
          _market_id: 2,
          market_name: "BV Borussia 09 Dortmund vs. SV Werder Bremen",
          outcome_name: "Draw (BV Borussia 09 Dortmund vs. SV Werder Bremen)",
          pregame_mark: 0.18,
          is_winner: false,
          resolution_source: "polymarket",
          source: "polymarket",
        },
        {
          _market_id: 2,
          market_name: "BV Borussia 09 Dortmund vs. SV Werder Bremen",
          outcome_name: "SV Werder Bremen",
          pregame_mark: 0.13,
          is_winner: false,
          resolution_source: "polymarket",
          source: "polymarket",
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
    expect(multiThreeWay).not.toBeNull();
    expect(multiThreeWay?.source).toBeNull();
    expect(multiThreeWay?.legs.map((l) => l.pregameChance)).toEqual([null, null, null]);
    expect(multiThreeWay?.legs.map((l) => l.result)).toEqual(["won", "lost", "lost"]);
  });

  it("never falls back to opening_probability after full-time on gameMarkets.other or gameMarkets.totals, withholds when multiple candidates have null source, and never cross-assigns clubs that share a stem", () => {
    // 1. After full-time, opening_probability is ignored when pregame_mark is null
    const finishedThreeWayOpeningOnly = buildSoccerThreeWayCard({
      otherMarkets: [
        {
          market_name: "Borussia Dortmund vs Werder Bremen",
          outcome_name: "Borussia Dortmund",
          opening_probability: 0.65,
          pregame_mark: null,
          is_winner: true,
          resolution_source: "exchange_settlement",
          source: "kalshi",
        },
        {
          market_name: "Borussia Dortmund vs Werder Bremen",
          outcome_name: "Draw",
          opening_probability: 0.2,
          pregame_mark: null,
          is_winner: false,
          resolution_source: "exchange_settlement",
          source: "kalshi",
        },
        {
          market_name: "Borussia Dortmund vs Werder Bremen",
          outcome_name: "Werder Bremen",
          opening_probability: 0.15,
          pregame_mark: null,
          is_winner: false,
          resolution_source: "exchange_settlement",
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
    expect(finishedThreeWayOpeningOnly).not.toBeNull();
    expect(finishedThreeWayOpeningOnly?.legs.map((l) => l.pregameChance)).toEqual([
      null,
      null,
      null,
    ]);

    const finishedExactOpeningOnly = buildSoccerExactScoreCard({
      otherMarkets: ["1-0", "2-0", "1-1", "2-1"].map((score, idx) => ({
        market_name: "Borussia Dortmund vs Werder Bremen: Correct Score",
        outcome_name: score,
        opening_probability: 0.12,
        pregame_mark: null,
        is_winner: idx === 0,
        resolution_source: "exchange_settlement",
        source: "kalshi",
      })),
      status: "completed",
      commenceTime: "2026-11-05T17:00:00Z",
      homeTeam: "Borussia Dortmund",
      awayTeam: "Werder Bremen",
      homeShort: "Dortmund",
      awayShort: "Bremen",
      nowMs: NOW_MS,
    });
    expect(finishedExactOpeningOnly).not.toBeNull();
    expect(finishedExactOpeningOnly?.cells.every((c) => c.chance === null && c.pregameChance === null)).toBe(true);

    const finishedTotalsOpeningOnly = buildSoccerGoalTotalCard({
      totalsMarkets: [1.5, 2.5, 3.5].map((threshold) => ({
        threshold,
        over_probability: 1.0,
        opening_probability: 0.55,
        pregame_mark: null,
        is_winner: true,
        resolution_source: "exchange_settlement",
        market_type: "game_total",
        market_name: `Over ${threshold} goals`,
        source: "kalshi",
      })),
      status: "completed",
      commenceTime: "2026-11-05T17:00:00Z",
      homeScore: 3,
      awayScore: 2,
      homeShort: "Dortmund",
      awayShort: "Bremen",
      nowMs: NOW_MS,
    });
    expect(finishedTotalsOpeningOnly).not.toBeNull();
    expect(finishedTotalsOpeningOnly?.points.every((p) => p.chance === null && p.detail.baseline === null)).toBe(true);

    // 2. Multiple unblended candidates with source: null still withhold probabilities
    const multiNullSource = buildSoccerThreeWayCard({
      otherMarkets: [
        {
          _market_id: 10,
          market_name: "Match Winner A",
          outcome_name: "Borussia Dortmund",
          pregame_mark: 0.62,
          is_winner: true,
          resolution_source: "exchange_settlement",
          source: null,
        },
        {
          _market_id: 10,
          market_name: "Match Winner A",
          outcome_name: "Draw",
          pregame_mark: 0.22,
          is_winner: false,
          resolution_source: "exchange_settlement",
          source: null,
        },
        {
          _market_id: 10,
          market_name: "Match Winner A",
          outcome_name: "Werder Bremen",
          pregame_mark: 0.16,
          is_winner: false,
          resolution_source: "exchange_settlement",
          source: null,
        },
        {
          _market_id: 11,
          market_name: "Match Winner B",
          outcome_name: "Borussia Dortmund",
          pregame_mark: 0.70,
          is_winner: true,
          resolution_source: "exchange_settlement",
          source: null,
        },
        {
          _market_id: 11,
          market_name: "Match Winner B",
          outcome_name: "Draw",
          pregame_mark: 0.18,
          is_winner: false,
          resolution_source: "exchange_settlement",
          source: null,
        },
        {
          _market_id: 11,
          market_name: "Match Winner B",
          outcome_name: "Werder Bremen",
          pregame_mark: 0.12,
          is_winner: false,
          resolution_source: "exchange_settlement",
          source: null,
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
    expect(multiNullSource).not.toBeNull();
    expect(multiNullSource?.source).toBeNull();
    expect(multiNullSource?.legs.map((l) => l.pregameChance)).toEqual([null, null, null]);

    // 3. Clubs sharing a stem ("AC Milan" vs "Inter Milan") never cross-assign Home and Away
    const derbyCard = buildSoccerThreeWayCard({
      otherMarkets: [
        {
          market_name: "AC Milan vs Inter Milan",
          outcome_name: "Inter Milan",
          probability: 0.45,
          observed_at: "2026-11-05T19:55:00Z",
          source: "kalshi",
        },
        {
          market_name: "AC Milan vs Inter Milan",
          outcome_name: "Draw",
          probability: 0.27,
          observed_at: "2026-11-05T19:55:00Z",
          source: "kalshi",
        },
        {
          market_name: "AC Milan vs Inter Milan",
          outcome_name: "AC Milan",
          probability: 0.28,
          observed_at: "2026-11-05T19:55:00Z",
          source: "kalshi",
        },
      ],
      status: "scheduled",
      commenceTime: "2026-11-05T22:00:00Z",
      homeTeam: "AC Milan",
      awayTeam: "Inter Milan",
      homeShort: "AC Milan",
      awayShort: "Inter Milan",
      nowMs: NOW_MS,
    });
    expect(derbyCard).not.toBeNull();
    expect(derbyCard?.legs.map((l) => ({ role: l.role, quoted: l.quotedChance }))).toEqual([
      { role: "home", quoted: 0.28 },
      { role: "draw", quoted: 0.27 },
      { role: "away", quoted: 0.45 },
    ]);

    expect(
      parseSoccerExactScoreOutcome(
        "Inter Milan wins 2-1",
        "AC Milan",
        "Inter Milan",
        "AC Milan",
        "Inter Milan",
      ),
    ).toEqual({ homeGoals: 1, awayGoals: 2 });
  });
});
