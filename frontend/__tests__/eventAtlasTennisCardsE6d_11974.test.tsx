import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  tennisCards,
  tennisCardsApply,
  type TennisExactScoreCard,
  type TennisSetsCard,
} from "@/lib/tennisEventCards";
import {
  buildStoryCardDetailsSheetProps,
  EventCardView,
} from "@/components/event/NFLEventCards";
import type { LadderCard } from "@/lib/nbaEventCards";

const FINISHED_TENNIS_MATRIX = {
  contract: "10238.v1",
  display_scope: "game",
  questions: [
    {
      question_key: "m:68960551",
      kind: "named_options",
      label: "Djokovic vs. Hijikata: Match O/U 21.5",
      market_name: "Djokovic vs. Hijikata: Match O/U 21.5",
      source_array: "totals",
      period: { key: "full_game", label: "Game" },
      options: [
        {
          option_key: "o:258615150",
          label: "Over",
          side: "category",
          market_ids: [68960551],
          contributor_outcome_ids: [258615150],
          published: {
            value: null,
            value_state: "result",
            basis: "result",
            source: "polymarket",
            observed_at: "2026-11-04T17:08:25.252507+00:00",
          },
          result: { state: "won", evidence_kind: "settled_grade_fields" },
          pregame_reading: {
            state: "available",
            reason: null,
            probability: 0.57,
            observed_at: "2026-11-04T13:47:08.597576+00:00",
            basis: "pregame_pin",
            outcome_id: 258615150,
          },
        },
      ],
    },
    {
      question_key: "m:68960552",
      kind: "named_options",
      label: "Djokovic vs. Hijikata: Match O/U 22.5",
      market_name: "Djokovic vs. Hijikata: Match O/U 22.5",
      source_array: "totals",
      period: { key: "full_game", label: "Game" },
      options: [
        {
          option_key: "o:258615152",
          label: "Over",
          side: "category",
          market_ids: [68960552],
          contributor_outcome_ids: [258615152],
          published: {
            value: null,
            value_state: "result",
            basis: "result",
            source: "polymarket",
            observed_at: "2026-11-04T17:08:25.252507+00:00",
          },
          result: { state: "won", evidence_kind: "settled_grade_fields" },
          pregame_reading: {
            state: "available",
            reason: null,
            probability: 0.475,
            observed_at: "2026-11-04T13:47:08.546155+00:00",
            basis: "pregame_pin",
            outcome_id: 258615152,
          },
        },
      ],
    },
    {
      question_key: "m:68960553",
      kind: "named_options",
      label: "Djokovic vs. Hijikata: Match O/U 23.5",
      market_name: "Djokovic vs. Hijikata: Match O/U 23.5",
      source_array: "totals",
      period: { key: "full_game", label: "Game" },
      options: [
        {
          option_key: "o:258615154",
          label: "Over",
          side: "category",
          market_ids: [68960553],
          contributor_outcome_ids: [258615154],
          published: {
            value: null,
            value_state: "result",
            basis: "result",
            source: "polymarket",
            observed_at: "2026-11-04T17:08:25.252507+00:00",
          },
          result: { state: "won", evidence_kind: "settled_grade_fields" },
          pregame_reading: {
            state: "available",
            reason: null,
            probability: 0.4,
            observed_at: "2026-11-04T13:47:08.558576+00:00",
            basis: "pregame_pin",
            outcome_id: 258615154,
          },
        },
      ],
    },
    // Out-of-order Set 2 before Set 1 to prove numeric set sorting
    {
      question_key: "m:69079339",
      kind: "named_options",
      label: "Set 2 Winner: Novak Djokovic vs Rinky Hijikata",
      market_name: "Set 2 Winner: Novak Djokovic vs Rinky Hijikata",
      source_array: "other",
      options: [
        {
          option_key: "o:259075056",
          label: "Rinky Hijikata",
          side: "away",
          market_ids: [69079339],
          contributor_outcome_ids: [259075056],
          published: {
            value: null,
            value_state: "result",
            basis: "result",
            source: "polymarket",
            observed_at: "2026-11-04T17:08:25.252507+00:00",
          },
          result: { state: "won", evidence_kind: "settled_grade_fields" },
          pregame_reading: {
            state: "unavailable",
            reason: "no_pregame_pin",
            probability: null,
            observed_at: null,
            basis: null,
            outcome_id: null,
          },
        },
        {
          option_key: "o:259075055",
          label: "Novak Djokovic",
          side: "home",
          market_ids: [69079339],
          contributor_outcome_ids: [259075055],
          published: {
            value: null,
            value_state: "result",
            basis: "result",
            source: "polymarket",
            observed_at: "2026-11-04T17:08:25.252507+00:00",
          },
          result: { state: "lost", evidence_kind: "verdict_is_provable" },
          pregame_reading: {
            state: "unavailable",
            reason: "no_pregame_pin",
            probability: null,
            observed_at: null,
            basis: null,
            outcome_id: null,
          },
        },
      ],
    },
    {
      question_key: "m:68960548",
      kind: "named_options",
      label: "Set 1 Winner: Novak Djokovic vs Rinky Hijikata",
      market_name: "Set 1 Winner: Novak Djokovic vs Rinky Hijikata",
      source_array: "other",
      options: [
        {
          option_key: "o:258615144",
          label: "Novak Djokovic",
          side: "home",
          market_ids: [68960548],
          contributor_outcome_ids: [258615144],
          published: {
            value: null,
            value_state: "result",
            basis: "result",
            source: "polymarket",
            observed_at: "2026-11-04T17:08:25.252507+00:00",
          },
          result: { state: "won", evidence_kind: "settled_grade_fields" },
          pregame_reading: {
            state: "available",
            reason: null,
            probability: 0.72,
            observed_at: "2026-11-04T13:47:08.539145+00:00",
            basis: "pregame_pin",
            outcome_id: 258615144,
          },
        },
        {
          option_key: "o:258615145",
          label: "Rinky Hijikata",
          side: "away",
          market_ids: [68960548],
          contributor_outcome_ids: [258615145],
          published: {
            value: null,
            value_state: "result",
            basis: "result",
            source: "polymarket",
            observed_at: "2026-11-04T17:08:25.252507+00:00",
          },
          result: { state: "lost", evidence_kind: "verdict_is_provable" },
          pregame_reading: {
            state: "available",
            reason: null,
            probability: 0.28,
            observed_at: "2026-11-04T13:47:08.539145+00:00",
            basis: "pregame_pin",
            outcome_id: 258615145,
          },
        },
      ],
    },
    {
      question_key: "m:68941401",
      kind: "named_options",
      label: "Novak Djokovic vs Rinky Hijikata: Exact Match Score",
      market_name: "Novak Djokovic vs Rinky Hijikata: Exact Match Score",
      source_array: "other",
      options: [
        {
          option_key: "o:258532623",
          label: "Rinky Hijikata wins 2-1",
          side: "category",
          market_ids: [68941401],
          contributor_outcome_ids: [258532623],
          published: {
            value: null,
            value_state: "result",
            basis: "result",
            source: "kalshi",
            observed_at: "2026-11-05T20:52:00.025756+00:00",
          },
          result: { state: "won", evidence_kind: "settled_grade_fields" },
          pregame_reading: {
            state: "available",
            reason: null,
            probability: 0.14,
            observed_at: "2026-11-04T13:47:08.539145+00:00",
            basis: "pregame_pin",
            outcome_id: 258532623,
          },
        },
        {
          option_key: "o:258532621",
          label: "Novak Djokovic wins 2-0",
          side: "category",
          market_ids: [68941401],
          contributor_outcome_ids: [258532621],
          published: {
            value: null,
            value_state: "result",
            basis: "result",
            source: "kalshi",
            observed_at: "2026-11-05T20:52:00.025756+00:00",
          },
          result: { state: "lost", evidence_kind: "verdict_is_provable" },
          pregame_reading: {
            state: "available",
            reason: null,
            probability: 0.52,
            observed_at: "2026-11-04T13:47:08.539145+00:00",
            basis: "pregame_pin",
            outcome_id: 258532621,
          },
        },
        {
          option_key: "o:258532622",
          label: "Novak Djokovic wins 2-1",
          side: "category",
          market_ids: [68941401],
          contributor_outcome_ids: [258532622],
          published: {
            value: null,
            value_state: "result",
            basis: "result",
            source: "kalshi",
            observed_at: "2026-11-05T20:52:00.025756+00:00",
          },
          result: { state: "lost", evidence_kind: "verdict_is_provable" },
          pregame_reading: {
            state: "available",
            reason: null,
            probability: 0.24,
            observed_at: "2026-11-04T13:47:08.539145+00:00",
            basis: "pregame_pin",
            outcome_id: 258532622,
          },
        },
        {
          option_key: "o:258532624",
          label: "Rinky Hijikata wins 2-0",
          side: "category",
          market_ids: [68941401],
          contributor_outcome_ids: [258532624],
          published: {
            value: null,
            value_state: "result",
            basis: "result",
            source: "kalshi",
            observed_at: "2026-11-05T20:52:00.025756+00:00",
          },
          result: { state: "lost", evidence_kind: "verdict_is_provable" },
          pregame_reading: {
            state: "available",
            reason: null,
            probability: 0.1,
            observed_at: "2026-11-04T13:47:08.539145+00:00",
            basis: "pregame_pin",
            outcome_id: 258532624,
          },
        },
      ],
    },
  ],
};

describe("#11974 Step E6d — Tennis story cards", () => {
  it("gates tennisCardsApply on atlasMode and tennis_ sport keys", () => {
    expect(tennisCardsApply("tennis_atp_paris_masters", true)).toBe(true);
    expect(tennisCardsApply("tennis_wta", true)).toBe(true);
    expect(tennisCardsApply("tennis_atp_paris_masters", false)).toBe(false);
    expect(tennisCardsApply("soccer_epl", true)).toBe(false);
    expect(tennisCardsApply(null, true)).toBe(false);
  });

  it("builds Set-by-set, Exact match score, and Total games cards for finished tennis without inventing unquoted sets or using set scores as games actual", () => {
    const cards = tennisCards({
      sportKey: "tennis_atp_paris_masters",
      atlasMode: true,
      status: "completed",
      commenceTime: "2026-11-04T14:00:00Z",
      homeTeam: "Novak Djokovic",
      awayTeam: "Rinky Hijikata",
      homeShort: "Djokovic",
      awayShort: "Hijikata",
      // Event scores are 1-2 in sets, NEVER total games!
      homeScore: 1,
      awayScore: 2,
      gameMarkets: null,
      questionMatrix: FINISHED_TENNIS_MATRIX,
      nowMs: Date.parse("2026-11-05T22:00:00Z"),
    });

    expect(cards.map((c) => c.id)).toEqual([
      "tennis:sets",
      "tennis:exactScore",
      "total",
    ]);

    const setsCard = cards[0] as TennisSetsCard;
    expect(setsCard.title).toBe("The match, set by set");
    // Only Set 1 and Set 2 are supplied; Set 3 is NOT invented from the 2-1 match score
    expect(setsCard.sets.map((s) => s.setNumber)).toEqual([1, 2]);
    expect(setsCard.sets[0].winnerName).toBe("Novak Djokovic");
    expect(setsCard.sets[0].home.pregameProbability).toBe(0.72);
    expect(setsCard.sets[1].winnerName).toBe("Rinky Hijikata");

    const exactCard = cards[1] as TennisExactScoreCard;
    expect(exactCard.title).toBe("Hijikata in three sets");
    expect(exactCard.winningOutcome?.scoreLabel).toBe("Hijikata 2–1");
    expect(exactCard.outcomes).toHaveLength(4);

    const totalCard = cards[2] as LadderCard;
    expect(totalCard.unit).toBe("games");
    // CRITICAL TRUTH GUARD: tennis set scores (1 + 2 = 3) must NEVER become total games actual
    expect(totalCard.actual).toBeNull();
    expect(totalCard.points.map((p) => p.x)).toEqual([21.5, 22.5, 23.5]);
  });

  it("renders the Tennis deck and builds AtlasDetailsSheet props for step and tile selections", () => {
    const cards = tennisCards({
      sportKey: "tennis_atp_paris_masters",
      atlasMode: true,
      status: "completed",
      commenceTime: "2026-11-04T14:00:00Z",
      homeTeam: "Novak Djokovic",
      awayTeam: "Rinky Hijikata",
      homeShort: "Djokovic",
      awayShort: "Hijikata",
      homeScore: 1,
      awayScore: 2,
      gameMarkets: null,
      questionMatrix: FINISHED_TENNIS_MATRIX,
      nowMs: Date.parse("2026-11-05T22:00:00Z"),
    });

    const teams = {
      homeName: "Novak Djokovic",
      awayName: "Rinky Hijikata",
      homeShort: "Djokovic",
      awayShort: "Hijikata",
      homeColor: "#1D4ED8",
      awayColor: "#0F766E",
    };

    const setsHtml = renderToStaticMarkup(
      <EventCardView
        card={cards[0]}
        teams={teams}
        selection={{}}
        onSelect={jest.fn()}
        onDetails={jest.fn()}
        atlasMode
      />,
    );
    expect(setsHtml).toContain("tennis-sets-card");
    expect(setsHtml).toContain("The match, set by set");
    expect(setsHtml).toContain("Novak Djokovic");
    expect(setsHtml).toContain("72% pregame");
    expect(setsHtml).toContain("Rinky Hijikata");

    const exactHtml = renderToStaticMarkup(
      <EventCardView
        card={cards[1]}
        teams={teams}
        selection={{}}
        onSelect={jest.fn()}
        onDetails={jest.fn()}
        atlasMode
      />,
    );
    expect(exactHtml).toContain("tennis-exact-score-card");
    expect(exactHtml).toContain("Hijikata in three sets");
    expect(exactHtml).toContain("✓ Won");

    const totalHtml = renderToStaticMarkup(
      <EventCardView
        card={cards[2]}
        teams={teams}
        selection={{}}
        onSelect={jest.fn()}
        onDetails={jest.fn()}
        atlasMode
      />,
    );
    expect(totalHtml).toContain("Total games");
    expect(totalHtml).toContain("tennis-total-games-actual-absent");
    expect(totalHtml).toContain("Actual final");

    const setSheet = buildStoryCardDetailsSheetProps({
      card: cards[0],
      rowId: "set:1",
      teams,
    });
    expect(setSheet?.subjectName).toBe("Set 1 Winner · Novak Djokovic");
    expect(setSheet?.isSettled).toBe(true);
    expect(setSheet?.settledResult).toBe("won");
    expect(setSheet?.openingProbability).toBe(0.72);

    const exactSheet = buildStoryCardDetailsSheetProps({
      card: cards[1],
      rowId: "o:258532623",
      teams,
    });
    expect(exactSheet?.subjectName).toBe("Rinky Hijikata wins 2-1");
    expect(exactSheet?.isSettled).toBe(true);
    expect(exactSheet?.settledResult).toBe("won");
    expect(exactSheet?.openingProbability).toBe(0.14);
  });
});
