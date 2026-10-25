/**
 * #1529 reader gate — the game-winner question is a Game lines question.
 *
 * Reader failure (event 15195694, 390 px, 2026-10-21 03:57Z): All markets →
 * Other held the Kalshi question "Philadelphia vs New York" (Philadelphia /
 * New York); Game lines held only totals and spreads. The server already knew
 * the market was the full game's winner but served its legs in `other` with no
 * class, and the catalog mapped `data.other` straight to Other.
 *
 * The server now stamps `market_type: "moneyline"` on exactly those rows
 * (backend/tests/test_game_market_winner_reaches_game_lines_1529.py). This
 * pins the consumer half: the class moves the question, the title never does.
 * Cases come from the fenced Codex fixture (commit 48d8c7cd); its synthetic
 * cases are guard specifications, not venue evidence.
 */
import { readFileSync } from "fs";
import { join } from "path";
import { buildQuestionCatalog } from "@/lib/questionCatalog";
import type { GameMarketsResponse } from "@/lib/api";

const FIXTURE = JSON.parse(
  readFileSync(
    join(__dirname, "../../../backend/tests/evals/fixtures/1529-reader-moneyline-other.json"),
    "utf8",
  ),
);
const CASES: Record<string, { market_name: string; outcome_names: string[] }> =
  Object.fromEntries(
    FIXTURE.synthetic_guard_specs_not_venue_evidence.map(
      (c: { case: string }) => [c.case, c],
    ),
  );

const NOW = Date.parse("2026-10-20T23:00:00Z");
const FRESH = "2026-10-20T22:59:00Z";

type OtherRow = GameMarketsResponse["other"][number];

function markets(over: Partial<GameMarketsResponse> = {}): GameMarketsResponse {
  return {
    event_id: 15195694,
    home_team: "Philadelphia 76ers",
    away_team: "New York Knicks",
    home_score: null,
    away_score: null,
    status: "scheduled",
    totals: [],
    player_props: [],
    team_totals: [],
    spreads: [],
    period_markets: [],
    matchups: [],
    other: [],
    pace: null,
    ...over,
  } as GameMarketsResponse;
}

/** The observed question, in the row shape `_build_game_markets` serves. */
function winnerRows(marketType?: string): OtherRow[] {
  const { winner_question, source_label, outcome_labels } = FIXTURE.observed;
  return outcome_labels.map((label: string, i: number) => ({
    market_name: winner_question,
    outcome_name: label,
    probability: i === 0 ? 0.62 : 0.38,
    source: source_label.toLowerCase(),
    observed_at: FRESH,
    _market_id: 152910,
    ...(marketType === undefined ? {} : { market_type: marketType }),
  }));
}

const familyOf = (data: GameMarketsResponse, question: string, status = "scheduled") =>
  buildQuestionCatalog(data, status, NOW)
    .filter((g) => g.question === question)
    .map((g) => g.family);

describe("#1529 the game's winner reaches Game lines", () => {
  test("the fixture is the observed failure", () => {
    expect(FIXTURE.observed.catalog_family).toBe("Other");
    expect(FIXTURE.expected_reader_contract.full_game_winner_family).toBe("Game lines");
  });

  test("a served full-game winner is one Game lines question, never Other", () => {
    const data = markets({
      other: winnerRows("moneyline"),
      totals: [{
        threshold: 221.5, over_probability: 0.5, source: "kalshi",
        market_type: "game_total", market_name: "Total points",
        outcome_name: "Over 221.5", movement: null,
      }],
    });
    const groups = buildQuestionCatalog(data, "scheduled", NOW);
    const winner = groups.filter((g) => g.question === "Philadelphia vs New York");

    expect(winner).toHaveLength(1);
    expect(winner[0].family).toBe("Game lines");
    expect(winner[0].source).toBe("Kalshi");
    // The quote rule is unchanged: the row's own probability, per outcome.
    expect(winner[0].outcomes.map((o) => [o.label, o.probability])).toEqual([
      ["Philadelphia", 0.62],
      ["New York", 0.38],
    ]);
    expect(groups.some((g) => g.family === "Other")).toBe(false);
    // Beside the totals the reader already found there.
    expect(groups.map((g) => g.family)).toEqual(["Game lines", "Game lines"]);
  });

  test("after the final the winner is still unpriced (settled means settled)", () => {
    const [group] = buildQuestionCatalog(
      markets({ other: winnerRows("moneyline"), status: "final" }), "final", NOW,
    );
    expect(group.family).toBe("Game lines");
    expect(group.outcomes.map((o) => o.probability)).toEqual([null, null]);
  });
});

describe("#1529 what must not move", () => {
  test("a row with no established class stays in Other — the title is never read", () => {
    // Same title, same outcomes, no class: the catalog may not guess.
    expect(familyOf(markets({ other: winnerRows() }), "Philadelphia vs New York"))
      .toEqual(["Other"]);
  });

  test.each(["segment_winner", "other", "btts", ""])(
    "a row classed %p stays in Other",
    (cls) => {
      expect(familyOf(markets({ other: winnerRows(cls) }), "Philadelphia vs New York"))
        .toEqual(["Other"]);
    },
  );

  test("the matchup-named player container stays Player props", () => {
    const c = CASES["same matchup name is a player-contract container"];
    const data = markets({
      player_props: [{
        market_name: c.market_name, outcome_name: c.outcome_names[0],
        threshold: 25, over_probability: 0.38, source: "polymarket",
        observed_at: FRESH,
      }] as GameMarketsResponse["player_props"],
      // The sibling the rescue leaves behind is served unclassified.
      other: [{
        market_name: c.market_name, outcome_name: "Tie", probability: 0.4,
        source: "polymarket", observed_at: FRESH,
      }],
    });
    expect(familyOf(data, c.market_name).sort()).toEqual(["Other", "Player props"]);
  });

  test("an unclassified question keeps its Other section beside a classified winner", () => {
    const u = CASES["unclassified question remains unknown"];
    const data = markets({
      other: [
        ...winnerRows("moneyline"),
        { market_name: u.market_name, outcome_name: "Yes", probability: 0.3,
          source: "kalshi", observed_at: FRESH },
      ],
    });
    expect(familyOf(data, "Philadelphia vs New York")).toEqual(["Game lines"]);
    expect(familyOf(data, u.market_name)).toEqual(["Other"]);
  });
});
