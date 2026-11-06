import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  AFTER_PROPS_CONTRACT,
  buildMlbEventCards,
  buildMlbExtraInningsCard,
  buildMlbHomeRunCard,
  buildMlbRunTotalsCard,
  buildMlbSeriesCard,
  buildMlbStrikeoutMilestoneCard,
  mlbCardsApply,
} from "@/lib/mlbEventCards";
import { MATRIX_CONTRACT } from "@/lib/nbaEventCards";
import {
  buildStoryCardDetailsSheetProps,
  EventCardView,
  type CardTeams,
} from "@/components/event/NFLEventCards";

const TEAMS: CardTeams = {
  awayName: "Milwaukee Brewers",
  homeName: "Los Angeles Dodgers",
  awayShort: "Brewers",
  homeShort: "Dodgers",
  awayColor: "#12284B",
  homeColor: "#005A9C",
};

const NOW_MS = Date.parse("2026-10-20T03:30:00Z");

describe("#11974 Step E6a — MLB story cards behind ?atlas=1", () => {
  it("gates MLB story cards strictly on atlasMode && sportKey === baseball_mlb", () => {
    expect(mlbCardsApply("baseball_mlb", false)).toBe(false);
    expect(mlbCardsApply("baseball_mlb", true)).toBe(true);
    expect(mlbCardsApply("americanfootball_nfl", true)).toBe(false);
  });

  it("builds MlbHomeRunCard in 'homered' story (lowest pregame chance first) and computes scaleCeiling", () => {
    const afterPlayerProps = {
      contract: AFTER_PROPS_CONTRACT,
      actuals: [
        { actual_key: "s:ohtani|home_runs|full_game", state: "final", value: 1, source_label: "ESPN final box" },
        { actual_key: "s:edman|home_runs|full_game", state: "final", value: 1, source_label: "ESPN final box" },
        { actual_key: "s:betts|home_runs|full_game", state: "final", value: 0, source_label: "ESPN final box" },
      ],
      questions: [
        {
          question_key: "q:ohtani|hr|1",
          actual_key: "s:ohtani|home_runs|full_game",
          subject: { key: "ohtani", label: "Shohei Ohtani", kind: "player" },
          stat_key: "home_runs",
          period_key: "full_game",
          predicate: { kind: "count_at_least", count: 1, side: "over", label: "1+" },
          expectation: {
            state: "available",
            probability: 0.28,
            observed_at: "2026-10-19T23:55:00Z",
            contributors: [{ source: "kalshi", probability: 0.28, observed_at: "2026-10-19T23:55:00Z" }],
          },
          venue_grade: { is_winner: true, resolution_source: "kalshi" },
          contributor_outcome_ids: [101],
        },
        {
          question_key: "q:edman|hr|1",
          actual_key: "s:edman|home_runs|full_game",
          subject: { key: "edman", label: "Tommy Edman", kind: "player" },
          stat_key: "home_runs",
          period_key: "full_game",
          predicate: { kind: "count_at_least", count: 1, side: "over", label: "1+" },
          expectation: {
            state: "available",
            probability: 0.09,
            observed_at: "2026-10-19T23:55:00Z",
            contributors: [{ source: "kalshi", probability: 0.09, observed_at: "2026-10-19T23:55:00Z" }],
          },
          venue_grade: { is_winner: true, resolution_source: "kalshi" },
          contributor_outcome_ids: [102],
        },
        {
          question_key: "q:betts|hr|1",
          actual_key: "s:betts|home_runs|full_game",
          subject: { key: "betts", label: "Mookie Betts", kind: "player" },
          stat_key: "home_runs",
          period_key: "full_game",
          predicate: { kind: "count_at_least", count: 1, side: "over", label: "1+" },
          expectation: {
            state: "available",
            probability: 0.19,
            observed_at: "2026-10-19T23:55:00Z",
            contributors: [{ source: "kalshi", probability: 0.19, observed_at: "2026-10-19T23:55:00Z" }],
          },
          venue_grade: null,
          contributor_outcome_ids: [103],
        },
      ],
    };

    const card = buildMlbHomeRunCard({
      afterPlayerProps,
      playerProps: [
        {
          market_name: "MIL at LAD: Home Runs",
          outcome_name: "Tommy Edman: 1+",
          threshold: 1,
          over_probability: 0.09,
          source: "kalshi",
          player_team: "home",
          contributor_outcome_ids: [102],
        },
      ],
      status: "completed",
      commenceTime: "2026-10-20T00:08:00Z",
      homeTeam: TEAMS.homeName,
      awayTeam: TEAMS.awayName,
      nowMs: NOW_MS,
    });

    expect(card).not.toBeNull();
    expect(card?.story).toBe("homered");
    expect(card?.entries.map((e) => e.player)).toEqual(["Tommy Edman", "Shohei Ohtani"]);
    expect(card?.scaleCeiling).toBe(0.3);

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
    expect(html).toContain("data-testid=\"mlb-home-run-card\"");
    expect(html).toContain("Who homered, against their pregame chances");
    expect(html).toContain("Tommy Edman");
    expect(html).toContain("1 HR · Final");
    expect(html).toContain("✓ Won");

    const sheet = buildStoryCardDetailsSheetProps({
      card: card!,
      rowId: card!.entries[0].id,
      teams: TEAMS,
    });
    expect(sheet).toMatchObject({
      subjectName: "Tommy Edman",
      isSettled: true,
      settledResult: "won",
      openingProbability: 0.09,
    });
  });

  it("builds strikeout milestone card, run totals ladder (unit='runs'), extra innings, and series card in fixed slot order", () => {
    const gameMarkets = {
      player_props: [
        {
          market_name: "MIL at LAD: Strikeouts",
          outcome_name: "Yoshinobu Yamamoto: 4+",
          threshold: 4,
          over_probability: 0.82,
          pregame_mark: 0.82,
          source: "kalshi",
          player_team: "home" as const,
        },
        {
          market_name: "MIL at LAD: Strikeouts",
          outcome_name: "Yoshinobu Yamamoto: 5+",
          threshold: 5,
          over_probability: 0.64,
          pregame_mark: 0.64,
          source: "kalshi",
          player_team: "home" as const,
        },
        {
          market_name: "MIL at LAD: Strikeouts",
          outcome_name: "Yoshinobu Yamamoto: 6+",
          threshold: 6,
          over_probability: 0.48,
          pregame_mark: 0.48,
          source: "kalshi",
          player_team: "home" as const,
        },
        {
          market_name: "MIL at LAD: Strikeouts",
          outcome_name: "Yoshinobu Yamamoto: 7+",
          threshold: 7,
          over_probability: 0.29,
          pregame_mark: 0.29,
          source: "kalshi",
          player_team: "home" as const,
        },
      ],
      game_question_matrix: {
        contract: MATRIX_CONTRACT,
        questions: [6.5, 7.5, 8.5, 9.5].map((line, idx) => ({
          question_key: `q:runs:${line}`,
          kind: "count_threshold",
          label: `Total Runs Over/Under ${line}`,
          market_name: `Total Runs O/U ${line}`,
          typing: { state: "typed" },
          quantity: { key: "runs" },
          subject: { side: "game" },
          period: { key: "full_game" },
          predicate: { relation: "ge", line },
          options: [
            {
              option_key: `o:runs:${line}`,
              label: `Over ${line} runs`,
              side: "over",
              contributor_outcome_ids: [200 + idx],
              published: { value_state: "result", source: "kalshi", observed_at: "2026-10-20T03:10:00Z" },
              comparison: {
                state: "comparable",
                baseline: {
                  basis: "pregame_pin",
                  probability: 0.72 - idx * 0.14,
                  observed_at: "2026-10-19T23:50:00Z",
                },
              },
              pregame_reading: {
                state: "available",
                reason: null,
                basis: "pregame_pin",
                probability: 0.72 - idx * 0.14,
                observed_at: "2026-10-19T23:50:00Z",
                outcome_id: 200 + idx,
              },
              result: { state: line < 10 ? "won" : "lost" },
            },
          ],
        })),
      },
      other: [
        {
          market_name: "MIL at LAD: Extra Innings",
          outcome_name: "Yes",
          pregame_mark: 0.11,
          observed_at: "2026-10-19T23:50:00Z",
          source: "kalshi",
          is_winner: false,
          resolution_source: "kalshi",
        },
        {
          market_name: "MIL at LAD: Extra Innings",
          outcome_name: "No",
          pregame_mark: 0.89,
          observed_at: "2026-10-19T23:50:00Z",
          source: "kalshi",
          is_winner: true,
          resolution_source: "kalshi",
        },
      ],
    };

    const relatedFutures = {
      series_question_matrix: {
        contract: MATRIX_CONTRACT,
        display_scope: "series",
        questions: [
          {
            question_key: "q:series:winner",
            kind: "binary_winner",
            label: "NLCS Winner",
            market_name: "NLCS Series Winner",
            typing: { state: "typed" },
            options: [
              {
                option_key: "o:series:lad",
                label: "Los Angeles Dodgers",
                side: "home",
                contributor_outcome_ids: [301],
                published: { value_state: "quoted", value: 0.68, source: "kalshi", observed_at: "2026-10-19T23:50:00Z" },
                comparison: {
                  state: "comparable",
                  baseline: {
                    basis: "pregame_pin",
                    probability: 0.64,
                    observed_at: "2026-10-19T23:50:00Z",
                  },
                },
                result: { state: "open" },
              },
              {
                option_key: "o:series:mil",
                label: "Milwaukee Brewers",
                side: "away",
                contributor_outcome_ids: [302],
                published: { value_state: "quoted", value: 0.32, source: "kalshi", observed_at: "2026-10-19T23:50:00Z" },
                comparison: {
                  state: "comparable",
                  baseline: {
                    basis: "pregame_pin",
                    probability: 0.36,
                    observed_at: "2026-10-19T23:50:00Z",
                  },
                },
                result: { state: "open" },
              },
            ],
          },
        ],
      },
    };

    const deck = buildMlbEventCards({
      sportKey: "baseball_mlb",
      atlasMode: true,
      status: "completed",
      commenceTime: "2026-10-20T00:08:00Z",
      homeTeam: TEAMS.homeName,
      awayTeam: TEAMS.awayName,
      homeShort: "Dodgers",
      awayShort: "Brewers",
      homeScore: 4,
      awayScore: 6,
      gameMarkets,
      relatedFutures,
      nowMs: NOW_MS,
    });

    expect(deck.map((c) => c.id)).toEqual(["mlb:strikeouts", "total", "mlb:extraInnings", "mlb:series"]);

    const strikeoutCard = buildMlbStrikeoutMilestoneCard({
      playerProps: gameMarkets.player_props,
      status: "completed",
      commenceTime: "2026-10-20T00:08:00Z",
      homeTeam: TEAMS.homeName,
      awayTeam: TEAMS.awayName,
      nowMs: NOW_MS,
    });
    expect(strikeoutCard?.player).toBe("Yoshinobu Yamamoto");
    expect(strikeoutCard?.actual).toBeNull(); // untyped in 10237.v1 -> null, never 0

    const totalsCard = buildMlbRunTotalsCard({
      gameQuestionMatrix: gameMarkets.game_question_matrix,
      status: "completed",
      commenceTime: "2026-10-20T00:08:00Z",
      homeScore: 4,
      awayScore: 6,
      homeShort: "Dodgers",
      awayShort: "Brewers",
      nowMs: NOW_MS,
    });
    expect(totalsCard?.unit).toBe("runs");
    expect(totalsCard?.actual).toBe(10);

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
    expect(totalsHtml).toContain("Run totals");
    expect(totalsHtml).toContain("10 runs");

    const extraCard = buildMlbExtraInningsCard({
      other: gameMarkets.other,
      status: "completed",
      commenceTime: "2026-10-20T00:08:00Z",
      nowMs: NOW_MS,
    });
    const extraHtml = renderToStaticMarkup(
      <EventCardView
        card={extraCard!}
        teams={TEAMS}
        selection={{}}
        onSelect={() => {}}
        atlasMode
        onDetails={() => {}}
      />,
    );
    expect(extraHtml).toContain("data-testid=\"mlb-extra-innings-card\"");
    expect(extraHtml).toContain("✓ Won");
    expect(extraHtml).toContain("✗ Lost");
    expect(extraHtml).not.toContain("Venue result");
    expect(extraHtml).not.toContain("Not confirmed");
    expect(extraHtml).not.toContain("kalshi");

    const seriesCard = buildMlbSeriesCard(relatedFutures.series_question_matrix);
    const seriesHtml = renderToStaticMarkup(
      <EventCardView
        card={seriesCard!}
        teams={TEAMS}
        selection={{}}
        onSelect={() => {}}
        atlasMode
        onDetails={() => {}}
      />,
    );
    expect(seriesHtml).toContain("data-testid=\"mlb-series-card\"");
    expect(seriesHtml).toContain("NLCS Winner");
    expect(seriesHtml).toContain("Chance before this game");
    expect(seriesHtml).not.toContain("Venue result");
  });

  it("blends multi-source extra-innings rows into one outcome per side (Yes / No) and never shows venue names or 'Not confirmed'", () => {
    const extraCard = buildMlbExtraInningsCard({
      other: [
        {
          market_name: "MIL at LAD: Extra Innings",
          outcome_name: "Yes",
          pregame_mark: 0.1,
          observed_at: "2026-10-19T23:45:00Z",
          source: "kalshi",
          is_winner: false,
          resolution_source: "espn_box",
        },
        {
          market_name: "MIL at LAD: Extra Innings",
          outcome_name: "Yes",
          pregame_mark: 0.14,
          observed_at: "2026-10-19T23:55:00Z",
          source: "polymarket",
          is_winner: false,
          resolution_source: "box_score",
        },
        {
          market_name: "MIL at LAD: Extra Innings",
          outcome_name: "No",
          pregame_mark: 0.9,
          observed_at: "2026-10-19T23:45:00Z",
          source: "kalshi",
          is_winner: true,
          resolution_source: "espn_box",
        },
        {
          market_name: "MIL at LAD: Extra Innings",
          outcome_name: "No",
          pregame_mark: 0.86,
          observed_at: "2026-10-19T23:55:00Z",
          source: "polymarket",
          is_winner: true,
          resolution_source: "box_score",
        },
      ],
      status: "completed",
      commenceTime: "2026-10-20T00:08:00Z",
      nowMs: NOW_MS,
    });

    expect(extraCard).not.toBeNull();
    expect(extraCard?.outcomes).toHaveLength(2);
    expect(extraCard?.outcomes[0]).toMatchObject({
      label: "Yes",
      sourceCount: 2,
      venueResult: "lost",
      observedAt: "2026-10-19T23:55:00Z",
    });
    expect(extraCard?.outcomes[0].pregameChance).toBeCloseTo(0.12, 5);
    expect(extraCard?.outcomes[1]).toMatchObject({
      label: "No",
      sourceCount: 2,
      venueResult: "won",
      observedAt: "2026-10-19T23:55:00Z",
    });
    expect(extraCard?.outcomes[1].pregameChance).toBeCloseTo(0.88, 5);

    const html = renderToStaticMarkup(
      <EventCardView
        card={extraCard!}
        teams={TEAMS}
        selection={{}}
        onSelect={() => {}}
        atlasMode
        onDetails={() => {}}
      />,
    );
    expect(html).toContain("12% pregame");
    expect(html).toContain("88% pregame");
    expect(html).toContain("✗ Lost");
    expect(html).toContain("✓ Won");
    expect(html).not.toContain("kalshi");
    expect(html).not.toContain("polymarket");
    expect(html).not.toContain("Venue");
    expect(html).not.toContain("Not confirmed");

    const sheet = buildStoryCardDetailsSheetProps({
      card: extraCard!,
      rowId: extraCard!.outcomes[0].id,
      teams: TEAMS,
    });
    expect(sheet).toMatchObject({
      subjectName: "Yes",
      isSettled: true,
      settledResult: "lost",
      source: "blended",
      sourceCount: 2,
      rulesText: "Result: Lost",
    });
  });
});
