import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  buildNhlContributionMilestoneCard,
  buildNhlEventCards,
  buildNhlGoalTotalsCard,
  buildNhlPuckLineMarginCard,
  buildNhlScoringCard,
  nhlCardsApply,
} from "@/lib/nhlEventCards";
import { MATRIX_CONTRACT } from "@/lib/nbaEventCards";
import {
  buildStoryCardDetailsSheetProps,
  EventCardView,
  type CardTeams,
} from "@/components/event/NFLEventCards";

const TEAMS: CardTeams = {
  awayName: "Boston Bruins",
  homeName: "Pittsburgh Penguins",
  awayShort: "Bruins",
  homeShort: "Penguins",
  awayColor: "#FFB81C",
  homeColor: "#000000",
};

const NOW_MS = Date.parse("2026-11-05T04:00:00Z");

describe("#11974 Step E6b — NHL story cards behind ?atlas=1", () => {
  it("gates NHL story cards strictly on atlasMode && sportKey === icehockey_nhl", () => {
    expect(nhlCardsApply("icehockey_nhl", false)).toBe(false);
    expect(nhlCardsApply("icehockey_nhl", true)).toBe(true);
    expect(nhlCardsApply("baseball_mlb", true)).toBe(false);
  });

  it("builds NhlScoringCard ('Who found the net?') sorted by goals desc then pregame chance asc", () => {
    const playerProps = [
      {
        market_name: "Boston vs Pittsburgh: Goals",
        outcome_name: "Pavel Zacha: 1+",
        threshold: 1,
        over_probability: 0.265,
        pregame_mark: 0.265,
        observed_at: "2026-11-04T23:50:00Z",
        actual: 2,
        hit: true,
        source: "kalshi",
        player_team: "away" as const,
      },
      {
        market_name: "Boston vs Pittsburgh: Goals",
        outcome_name: "Mark Kastelic: 1+",
        threshold: 1,
        over_probability: 0.09,
        pregame_mark: 0.09,
        observed_at: "2026-11-04T23:50:00Z",
        actual: 1,
        hit: true,
        source: "kalshi",
        player_team: "away" as const,
      },
      {
        market_name: "Boston vs Pittsburgh: Goals",
        outcome_name: "Justin Brazeau: 1+",
        threshold: 1,
        over_probability: 0.165,
        pregame_mark: 0.165,
        observed_at: "2026-11-04T23:50:00Z",
        actual: 1,
        hit: true,
        source: "kalshi",
        player_team: "home" as const,
      },
      {
        market_name: "Boston vs Pittsburgh: Goals",
        outcome_name: "Charlie McAvoy: 1+",
        threshold: 1,
        over_probability: 0.145,
        pregame_mark: 0.145,
        observed_at: "2026-11-04T23:50:00Z",
        actual: 0,
        hit: false,
        source: "kalshi",
        player_team: "away" as const,
      },
    ];

    const card = buildNhlScoringCard({
      playerProps,
      status: "completed",
      commenceTime: "2026-11-05T00:08:00Z",
      homeTeam: TEAMS.homeName,
      awayTeam: TEAMS.awayName,
      nowMs: NOW_MS,
    });

    expect(card).not.toBeNull();
    expect(card?.story).toBe("scored");
    expect(card?.entries.map((e) => e.player)).toEqual([
      "Pavel Zacha",
      "Mark Kastelic",
      "Justin Brazeau",
    ]);

    const html = renderToStaticMarkup(
      <EventCardView
        card={card!}
        teams={TEAMS}
        selection={{}}
        onSelect={() => {}}
        atlasMode
        onDetails={() => {}}
      />,
    );
    expect(html).toContain("data-testid=\"nhl-scoring-card\"");
    expect(html).toContain("Who found the net?");
    expect(html).toContain("2 goals · Final");
    expect(html).toContain("✓ Won");

    const sheet = buildStoryCardDetailsSheetProps({
      card: card!,
      rowId: card!.entries[0].id,
      teams: TEAMS,
    });
    expect(sheet).toMatchObject({
      subjectName: "Pavel Zacha",
      isSettled: true,
      settledResult: "won",
      openingProbability: 0.265,
    });
  });

  it("builds goal totals ladder (unit='goals'), puck-line margin ladder (unit='goals'), and skater points milestone in fixed slot order", () => {
    const gameMarkets = {
      player_props: [
        {
          market_name: "Boston vs Pittsburgh: Goals",
          outcome_name: "Pavel Zacha: 1+",
          threshold: 1,
          over_probability: 0.265,
          pregame_mark: 0.265,
          observed_at: "2026-11-04T23:50:00Z",
          actual: 2,
          hit: true,
          source: "kalshi",
          player_team: "away" as const,
        },
        {
          market_name: "Boston vs Pittsburgh: Points",
          outcome_name: "David Pastrnak: 1+",
          threshold: 1,
          over_probability: 0.72,
          pregame_mark: 0.72,
          actual: 2,
          hit: true,
          source: "kalshi",
          player_team: "away" as const,
        },
        {
          market_name: "Boston vs Pittsburgh: Points",
          outcome_name: "David Pastrnak: 2+",
          threshold: 2,
          over_probability: 0.365,
          pregame_mark: 0.365,
          actual: 2,
          hit: true,
          source: "kalshi",
          player_team: "away" as const,
        },
        {
          market_name: "Boston vs Pittsburgh: Points",
          outcome_name: "David Pastrnak: 3+",
          threshold: 3,
          over_probability: 0.11,
          pregame_mark: 0.11,
          actual: 2,
          hit: false,
          source: "kalshi",
          player_team: "away" as const,
        },
      ],
      game_question_matrix: {
        contract: MATRIX_CONTRACT,
        questions: [
          ...[4.5, 5.5, 6.5, 7.5].map((line, idx) => ({
            question_key: `q:goals:${line}`,
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
                option_key: `o:goals:${line}`,
                label: `Over ${line} goals`,
                side: "over",
                contributor_outcome_ids: [400 + idx],
                published: { value_state: "result", source: "kalshi", observed_at: "2026-11-05T03:00:00Z" },
                comparison: {
                  state: "comparable",
                  baseline: {
                    basis: "pregame_pin",
                    probability: 0.78 - idx * 0.16,
                    observed_at: "2026-11-04T23:50:00Z",
                  },
                },
                pregame_reading: {
                  state: "available",
                  reason: null,
                  basis: "pregame_pin",
                  probability: 0.78 - idx * 0.16,
                  observed_at: "2026-11-04T23:50:00Z",
                  outcome_id: 400 + idx,
                },
                result: { state: line < 8 ? "won" : "lost" },
              },
            ],
          })),
          ...[
            { side: "away", line: -1.5, prob: 0.34, won: true },
            { side: "away", line: -2.5, prob: 0.18, won: true },
            { side: "home", line: -1.5, prob: 0.31, won: false },
          ].map((h, idx) => ({
            question_key: `q:puckline:${h.side}:${h.line}`,
            kind: "signed_handicap",
            label: `${h.side} ${h.line}`,
            market_name: "Puck Line",
            typing: { state: "typed" },
            quantity: { key: "goals" },
            subject: { side: h.side },
            period: { key: "full_game" },
            predicate: { relation: "handicap", line: h.line },
            options: [
              {
                option_key: `o:puckline:${idx}`,
                label: `${h.side === "home" ? "Penguins" : "Bruins"} ${h.line}`,
                side: h.side,
                contributor_outcome_ids: [500 + idx],
                published: { value_state: "result", source: "kalshi", observed_at: "2026-11-05T03:00:00Z" },
                comparison: {
                  state: "comparable",
                  baseline: {
                    basis: "pregame_pin",
                    probability: h.prob,
                    observed_at: "2026-11-04T23:50:00Z",
                  },
                },
                pregame_reading: {
                  state: "available",
                  reason: null,
                  basis: "pregame_pin",
                  probability: h.prob,
                  observed_at: "2026-11-04T23:50:00Z",
                  outcome_id: 500 + idx,
                },
                result: { state: h.won ? "won" : "lost" },
              },
            ],
          })),
        ],
      },
    };

    const deck = buildNhlEventCards({
      sportKey: "icehockey_nhl",
      atlasMode: true,
      status: "completed",
      commenceTime: "2026-11-05T00:08:00Z",
      homeTeam: TEAMS.homeName,
      awayTeam: TEAMS.awayName,
      homeShort: "Penguins",
      awayShort: "Bruins",
      homeScore: 2,
      awayScore: 6,
      gameMarkets,
      nowMs: NOW_MS,
    });

    expect(deck.map((c) => c.id)).toEqual(["nhl:scoring", "total", "margin", "nhl:contributions"]);

    const totalsCard = buildNhlGoalTotalsCard({
      gameQuestionMatrix: gameMarkets.game_question_matrix,
      status: "completed",
      commenceTime: "2026-11-05T00:08:00Z",
      homeScore: 2,
      awayScore: 6,
      homeShort: "Penguins",
      awayShort: "Bruins",
      nowMs: NOW_MS,
    });
    expect(totalsCard?.unit).toBe("goals");
    expect(totalsCard?.actual).toBe(8);

    const totalsHtml = renderToStaticMarkup(
      <EventCardView
        card={totalsCard!}
        teams={TEAMS}
        selection={{}}
        onSelect={() => {}}
        atlasMode
        onDetails={() => {}}
      />,
    );
    expect(totalsHtml).toContain("Goal expectations");
    expect(totalsHtml).toContain("8 goals");

    const marginCard = buildNhlPuckLineMarginCard({
      gameQuestionMatrix: gameMarkets.game_question_matrix,
      status: "completed",
      commenceTime: "2026-11-05T00:08:00Z",
      homeScore: 2,
      awayScore: 6,
      homeShort: "Penguins",
      awayShort: "Bruins",
      nowMs: NOW_MS,
    });
    expect(marginCard?.unit).toBe("goals");
    expect(marginCard?.actual).toBe(-4);

    const contribCard = buildNhlContributionMilestoneCard({
      playerProps: gameMarkets.player_props,
      status: "completed",
      commenceTime: "2026-11-05T00:08:00Z",
      homeTeam: TEAMS.homeName,
      awayTeam: TEAMS.awayName,
      nowMs: NOW_MS,
    });
    expect(contribCard?.player).toBe("David Pastrnak");
    expect(contribCard?.actual).toBe(2);
  });
});
