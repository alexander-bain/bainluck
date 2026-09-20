/**
 * #7396 — a settled "✓ Won" outcome is never the team page's live headline number.
 *
 * Arsenal led its Premier League page with `CHAMPIONSHIP 100%` five games into a
 * season it had not won yet (Barcelona the same in La Liga), because the graded
 * 2025-26 winner sits at ~0.995 and `pickJourneyFuture`'s tie-break is "higher
 * probability wins". The same page listed the same outcome correctly as
 * `What hit / ✓ Won` with the live market at 47% a component below.
 *
 * ⚠️ NON-VACUITY IS THE WHOLE POINT OF THIS FILE. A test that merely asserts
 * "picks the live one" passes on the OLD code whenever the live row happens to
 * be higher. Every arm below puts the SETTLED row at the HIGHER probability on
 * the SAME tier, so it wins the tie-break unless `is_winner` is actually read.
 * Production shape reproduced verbatim: settled 0.995 vs live 0.465 (Arsenal)
 * and 0.995 vs 0.70 (Barcelona), both tier 1.
 *
 * The three consumers this covers all route through `pickJourneyFuture`: the
 * hero (`teamHeadline`), the Season Journey chart (`TeamSeasonJourney`), and the
 * unfurl card (`teamShareMeta`, #5912) — so they cannot disagree with each other.
 */
import { pickJourneyFuture } from "../../lib/teamSeasonJourney";
import { teamHeadline } from "../../lib/teamHeadline";
import type { TeamFutureItem } from "../../lib/api";

function item(overrides: Partial<TeamFutureItem>): TeamFutureItem {
  return {
    outcome_id: 1,
    outcome_name: "Arsenal",
    market_id: 10,
    market_name: "Market",
    market_tier: 1,
    category: null,
    source: "kalshi",
    probability: 0.2,
    probability_change_24h: null,
    rank: null,
    total_outcomes: null,
    resolution_date: null,
    is_winner: false,
    ...overrides,
  };
}

/**
 * The live Arsenal payload, reduced to the two rows that decide the hero.
 *
 * ⚠️ ORDER IS LOAD-BEARING: the LIVE row is first and the settled row second.
 * `Array.prototype.sort` is stable, so if the settled row led this array a
 * comparator that returned a constant would still "select" it and the vacuity
 * control below would pass without the probability comparison ever running —
 * measured: neutering the tie-break left all arms green until this was flipped.
 * Second position means only a real comparison can lift the settled row.
 */
const ARSENAL = [
  item({
    market_id: 102,
    outcome_id: 1002,
    market_name: "English Premier League Champion",
    probability: 0.465, // the live 2026-27 market
    is_winner: false,
  }),
  item({
    market_id: 101,
    outcome_id: 1001,
    market_name: "English Premier League Winner?",
    probability: 0.995,
    is_winner: true, // graded 2025-26 champion
  }),
];

describe("#7396 a graded winner is a result, not a live price", () => {
  test("the hero picks the LIVE market even though the settled one is higher", () => {
    const pick = pickJourneyFuture(ARSENAL);
    expect(pick?.marketName).toBe("English Premier League Champion");
    expect(pick?.probability).toBe(0.465);
    expect(pick?.marketId).toBe(102);
    expect(pick?.outcomeId).toBe(1002);
  });

  test("Barcelona's La Liga shape lands the same way", () => {
    const pick = pickJourneyFuture([
      item({
        market_id: 202,
        outcome_id: 2002,
        market_name: "La Liga Champion",
        probability: 0.7,
        is_winner: false,
      }),
      item({
        market_id: 201,
        outcome_id: 2001,
        market_name: "La Liga Winner",
        probability: 0.995,
        is_winner: true,
      }),
    ]);
    expect(pick?.marketName).toBe("La Liga Champion");
    expect(pick?.probability).toBe(0.7);
  });

  test("VACUITY CONTROL: the settled row really does win the old tie-break", () => {
    // Same rows with the grade stripped — the ONLY difference from the first
    // arm. If this does not select the 0.995 row, the first arm proves nothing,
    // because the live row would have been picked either way.
    const ungraded = ARSENAL.map((f) => ({ ...f, is_winner: false }));
    const pick = pickJourneyFuture(ungraded);
    expect(pick?.marketName).toBe("English Premier League Winner?");
    expect(pick?.probability).toBe(0.995);
  });

  test("the hero number and label move with it, not just the chart pick", () => {
    // `championship_path` is empty on both real teams (measured), so the hero
    // takes teamHeadline's futures fallback — the branch this fix sits under.
    const headline = teamHeadline([], ARSENAL);
    expect(headline?.probability).toBe(0.465);
    expect(headline?.label).toBe("Championship");
  });

  test("the preferred championship_path branch is untouched", () => {
    // The backend already drops graded markets there (`~graded.exists()`), so
    // this fix must not reach into it: a path entry still wins over futures.
    const headline = teamHeadline(
      [{ tier: 1, label: "Championship", market_name: "EPL", market_id: 9, probability: 0.31, rank: 1, movement: 2 }],
      ARSENAL,
    );
    expect(headline?.probability).toBe(0.31);
    expect(headline?.movement).toBe(2);
  });

  test("a graded LOSER is still eligible — false never means settled", () => {
    // The payload carries `false` for graded losers and ungraded rows alike
    // (measured: never null), so only `true` may be excluded. A team whose best
    // row is a graded loser keeps its line rather than losing the section.
    const pick = pickJourneyFuture([
      item({ market_id: 301, outcome_id: 3001, market_name: "Dead Market", probability: 0.0001, is_winner: false }),
    ]);
    expect(pick?.marketName).toBe("Dead Market");
  });

  test("an absent is_winner (older payload) is still eligible", () => {
    const pick = pickJourneyFuture([
      item({ market_id: 401, outcome_id: 4001, market_name: "No Grade Field", probability: 0.5, is_winner: undefined }),
    ]);
    expect(pick?.marketName).toBe("No Grade Field");
  });

  test("a team whose ONLY row is settled shows no headline rather than a stale 100%", () => {
    // Measured 0 of 22 sampled teams on production, but it is the arm the fix
    // creates, so it is pinned deliberately: no number beats a wrong number.
    expect(pickJourneyFuture([item({ probability: 0.995, is_winner: true })])).toBeNull();
    expect(teamHeadline([], [item({ probability: 0.995, is_winner: true })])).toBeNull();
  });

  test("tier preference still outranks probability", () => {
    // Guards the sort's first key while the second key is what changed.
    const pick = pickJourneyFuture([
      item({ market_tier: 2, market_id: 60, outcome_id: 6, market_name: "Conference", probability: 0.9 }),
      item({ market_tier: 1, market_id: 61, outcome_id: 7, market_name: "Championship", probability: 0.1 }),
    ]);
    expect(pick?.marketName).toBe("Championship");
  });
});
