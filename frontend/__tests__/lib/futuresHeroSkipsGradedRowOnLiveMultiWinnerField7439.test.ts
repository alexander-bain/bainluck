/**
 * #7439 — A LIVE 28-FIGHTER FIELD WAS HEADED "100% Sean Strickland".
 *
 * Production, `/futures/114091` — *"Who will become a UFC champion in 2026?"*,
 * `status: "open"`, `mutually_exclusive: false`, resolving Dec 31 2026. Sean
 * Strickland's row is `probability 1.0, is_winner true` — a correct grade, since
 * the question asks for *a* champion — and a graded row is unbeatable in a sort
 * by probability, so it took the hero off a live field.
 *
 * 🪤 THE CONTROL IS THE POINT OF THIS FILE, not the repair.
 *
 * 671 open tier<=3 markets carry a graded row beside live ones and they FORK:
 * 329 are `mutually_exclusive = false` (the UFC shape — the graded row is a
 * RESULT and the hero must show the live leader) and 342 are
 * `mutually_exclusive = true`, where a graded row means the question IS answered
 * and skipping it would hide the answer and crown a runner-up — worse than the
 * screen we started with. So the mutex arms below are not politeness: they pin
 * behaviour that MUST NOT MOVE, and a repair that passes the first describe
 * while failing them is a regression on the larger half of the population.
 *
 * Every arm is written so that reverting the fix reddens at least one of them.
 */
import {
  pickChartSeedOutcomes,
  pickHeroOutcome,
  pickLiveLeader,
} from "../../lib/futuresDetailDisplay";

type Row = { name: string; probability: number | null; is_winner: boolean | null };

/** The real payload of `/api/futures/114091`, trimmed to the rows that decide it. */
const STRICKLAND: Row = { name: "Sean Strickland", probability: 1.0, is_winner: true };
const GANE: Row = { name: "Ciryl Gane", probability: 0.979, is_winner: false };
const MERAB: Row = { name: "Merab Dvalishvili", probability: 0.33, is_winner: false };
const UFC_FIELD: Row[] = [STRICKLAND, GANE, MERAB];

/** What the page's own `leader` memo computes, byte-identical comparator. */
function leaderOf(rows: readonly Row[]): Row | null {
  return [...rows].sort((a, b) => (b.probability ?? 0) - (a.probability ?? 0))[0] ?? null;
}

describe("#7439 live + mutually_exclusive false — the hero skips the graded row", () => {
  test("THE SPECIMEN: the UFC field heads with the live leader, not the graded champion", () => {
    const hero = pickHeroOutcome(UFC_FIELD, leaderOf(UFC_FIELD), false, false);
    expect(hero).toBe(GANE);
    // The literal screen defect, asserted as a negative so a partial repair
    // cannot pass by returning some other row.
    expect(hero?.name).not.toBe("Sean Strickland");
    expect(hero?.probability).not.toBe(1.0);
  });

  test("the graded row is still IN the field — the repair moves the feature, it deletes nothing", () => {
    // `pickHeroOutcome` is a selector over a list it does not own; the table,
    // the grade and the checkbox all read the same array afterwards.
    expect(UFC_FIELD).toContain(STRICKLAND);
    expect(UFC_FIELD).toHaveLength(3);
  });

  test("several graded rows: the hero is the best UNGRADED row, not the best of the rest", () => {
    const field = [
      STRICKLAND,
      { name: "Second champ", probability: 0.99, is_winner: true },
      GANE,
      MERAB,
    ];
    expect(pickHeroOutcome(field, leaderOf(field), false, false)).toBe(GANE);
  });

  test("EVERY row graded -> falls back to the leader, never an empty hero", () => {
    const allGraded: Row[] = [
      { name: "A", probability: 1.0, is_winner: true },
      { name: "B", probability: 1.0, is_winner: true },
    ];
    const lead = leaderOf(allGraded);
    expect(pickHeroOutcome(allGraded, lead, false, false)).toBe(lead);
    expect(pickHeroOutcome(allGraded, lead, false, false)).not.toBeNull();
  });

  test("🪤 EVERY LIVE ROW AT 0% -> HOLDS, because that board is decided and 0% is not a repair", () => {
    // /futures/108569, a cumulative ladder: the cleared rung is graded, every
    // tighter rung is dead. Promoting "Above 60" at 0% would trade one wrong
    // headline for a worse one. 51 of the 315 movers look like this.
    const ladder: Row[] = [
      { name: "Above 56", probability: 0.9995, is_winner: true },
      { name: "Above 60", probability: 0, is_winner: false },
      { name: "Above 65", probability: 0, is_winner: false },
    ];
    const hero = pickHeroOutcome(ladder, leaderOf(ladder), false, false);
    expect(hero?.name).toBe("Above 56");
    expect(hero?.probability).not.toBe(0);
  });

  test("a null-priced live row is not a live leader either", () => {
    const rows: Row[] = [
      { name: "Graded", probability: 1.0, is_winner: true },
      { name: "Unpriced", probability: null, is_winner: false },
    ];
    expect(pickHeroOutcome(rows, leaderOf(rows), false, false)?.name).toBe("Graded");
  });

  test("a SMALL but real price still promotes — 0 is the line, not 'low'", () => {
    // /futures/61082184 promotes a 9% row, and "the field's best shot is 9%" is
    // an odd sentence but a true one. Only "nothing here" falls back.
    const rows: Row[] = [
      { name: "Graded", probability: 1.0, is_winner: true },
      { name: "Longshot", probability: 0.09, is_winner: false },
      { name: "Dead", probability: 0, is_winner: false },
    ];
    expect(pickHeroOutcome(rows, leaderOf(rows), false, false)?.name).toBe("Longshot");

    const tiny: Row[] = [
      { name: "Graded", probability: 1.0, is_winner: true },
      { name: "Barely", probability: 0.005, is_winner: false },
    ];
    expect(pickHeroOutcome(tiny, leaderOf(tiny), false, false)?.name).toBe("Barely");
  });

  test("a HEALTHY live field is untouched — the new branch cannot re-order a market with nothing graded", () => {
    const healthy: Row[] = [
      { name: "Fav", probability: 0.58, is_winner: false },
      { name: "Mid", probability: 0.3, is_winner: null },
      { name: "Long", probability: 0.12, is_winner: false },
    ];
    const lead = leaderOf(healthy);
    // Same row the un-gated call returns: the comparator is the page's own.
    expect(pickHeroOutcome(healthy, lead, false, false)).toBe(lead);
    expect(pickHeroOutcome(healthy, lead, false, false)).toBe(
      pickHeroOutcome(healthy, lead, false, true),
    );
  });
});

describe("#7439 CONTROL — the mutually-exclusive half must NOT move (342 of the 671)", () => {
  test("mutually_exclusive TRUE: the graded row keeps the hero, because it IS the answer", () => {
    // `NBA: 2027 Champion` shape — 1 graded, 35 live, one winner possible.
    const hero = pickHeroOutcome(UFC_FIELD, leaderOf(UFC_FIELD), false, true);
    expect(hero).toBe(STRICKLAND);
  });

  test("mutually_exclusive UNDEFINED (field absent from the payload) -> today's behaviour", () => {
    expect(pickHeroOutcome(UFC_FIELD, leaderOf(UFC_FIELD), false, undefined)).toBe(STRICKLAND);
    // The 3-argument call is what every pre-#7439 caller makes.
    expect(pickHeroOutcome(UFC_FIELD, leaderOf(UFC_FIELD), false)).toBe(STRICKLAND);
  });

  test("mutually_exclusive NULL -> today's behaviour (an unknown field is mutex, matching the serializer default)", () => {
    expect(pickHeroOutcome(UFC_FIELD, leaderOf(UFC_FIELD), false, null)).toBe(STRICKLAND);
  });

  test("the gate is an EXPLICIT false, not a falsy value", () => {
    // Guards against `if (!mutuallyExclusive)`, which would sweep null/undefined
    // — i.e. the entire unknown population — into the new branch.
    const truthyish = [undefined, null, true] as const;
    for (const m of truthyish) {
      expect(pickHeroOutcome(UFC_FIELD, leaderOf(UFC_FIELD), false, m)).toBe(STRICKLAND);
    }
    expect(pickHeroOutcome(UFC_FIELD, leaderOf(UFC_FIELD), false, false)).toBe(GANE);
  });
});

describe("#7439 CONTROL — the RESOLVED arm is untouched under either flag", () => {
  test("resolved still features the graded winner, mutex true or false", () => {
    const lead = leaderOf(UFC_FIELD);
    expect(pickHeroOutcome(UFC_FIELD, lead, true, false)).toBe(STRICKLAND);
    expect(pickHeroOutcome(UFC_FIELD, lead, true, true)).toBe(STRICKLAND);
    expect(pickHeroOutcome(UFC_FIELD, lead, true)).toBe(STRICKLAND);
  });

  test("resolved with a LOWER-probability winner still wins (the #883 L2-49 case)", () => {
    const rows: Row[] = [
      { name: "Favorite", probability: 0.58, is_winner: false },
      { name: "Underdog", probability: 0.3, is_winner: true },
    ];
    expect(pickHeroOutcome(rows, leaderOf(rows), true, false)).toBe(rows[1]);
  });

  test("resolved with NOTHING graded falls back to the leader (#6301 Vuelta shape)", () => {
    const rows: Row[] = [
      { name: "Pogacar", probability: 0.0, is_winner: false },
      { name: "Mas", probability: 0.0, is_winner: false },
    ];
    // Must stay the leader and must NOT become null: the settled page still
    // features a row, and the "won" chip is gated elsewhere on the grade.
    expect(pickHeroOutcome(rows, rows[0], true, false)).toBe(rows[0]);
  });
});

describe("#7439 pickLiveLeader", () => {
  test("returns the highest-probability ungraded row", () => {
    expect(pickLiveLeader(UFC_FIELD)).toBe(GANE);
  });

  test("returns null when every row is graded, and on an empty field", () => {
    expect(pickLiveLeader([{ name: "A", probability: 1, is_winner: true }])).toBeNull();
    expect(pickLiveLeader([])).toBeNull();
  });

  test("returns null when every ungraded row is at 0% — 'no live leader', the second way", () => {
    expect(
      pickLiveLeader([
        { name: "Graded", probability: 1, is_winner: true },
        { name: "Dead", probability: 0, is_winner: false },
      ]),
    ).toBeNull();
  });

  test("an unpriced row is not a live leader", () => {
    const rows: Row[] = [
      { name: "Graded", probability: 1.0, is_winner: true },
      { name: "Unpriced", probability: null, is_winner: false },
    ];
    expect(pickLiveLeader(rows)).toBeNull();
  });

  test("🪤 PAYLOAD ORDER IS NOT PROBABILITY ORDER — the sort is what finds the leader", () => {
    // Every fixture above arrives pre-sorted, exactly as /api/futures serves it,
    // which makes the sort invisible: `.find(ungraded)` over the raw array gives
    // the same answer. Deleting the sort survived the first mutation run for
    // precisely this reason. This row is shuffled, so it cannot.
    const shuffled: Row[] = [
      { name: "Low", probability: 0.1, is_winner: false },
      { name: "Graded", probability: 1.0, is_winner: true },
      { name: "TrueLeader", probability: 0.8, is_winner: false },
      { name: "Mid", probability: 0.4, is_winner: false },
    ];
    expect(pickLiveLeader(shuffled)?.name).toBe("TrueLeader");
    expect(pickHeroOutcome(shuffled, leaderOf(shuffled), false, false)?.name).toBe(
      "TrueLeader",
    );
    // An ascending sort would answer "Low"; payload order would answer "Low" too.
    expect(pickLiveLeader(shuffled)?.name).not.toBe("Low");
  });

  test("ties keep payload order, the same way the page's leader memo does", () => {
    const rows: Row[] = [
      { name: "First", probability: 0.5, is_winner: false },
      { name: "Second", probability: 0.5, is_winner: false },
    ];
    expect(pickLiveLeader(rows)).toBe(rows[0]);
  });

  test("does not mutate the array it is given", () => {
    // `.sort` is in-place, so a missing copy would silently re-order the very
    // array the page renders its table from — identity, not just equality.
    const rows = [MERAB, STRICKLAND, GANE];
    const before = [...rows];
    pickLiveLeader(rows);
    expect(rows).toEqual(before);
    expect(rows[0]).toBe(MERAB);
    expect(rows[2]).toBe(GANE);
  });

  test("is_winner false and null are both LIVE — only an explicit true is graded", () => {
    const rows: Row[] = [
      { name: "NullGrade", probability: 0.9, is_winner: null },
      { name: "FalseGrade", probability: 0.8, is_winner: false },
    ];
    expect(pickLiveLeader(rows)).toBe(rows[0]);
  });
});

/**
 * #7439 — the chart's first paint.
 *
 * 🪤 These arms exist because the first mutation run killed every helper mutant
 * and let EVERY chart-seed mutant through — inverting the filter, deleting it,
 * and removing the empty-pool fallback all passed. The rule was inline in the
 * page's seed effect, where the only available test is a source grep, and a
 * grep cannot tell a correct filter from an inverted one. Extracting it is what
 * made these assertions possible; the extraction is part of the fix, not tidying.
 */
type SeedRow = Row & { id: number };

const S_GRADED: SeedRow = { id: 1, name: "Graded", probability: 1.0, is_winner: true };
const S_LEAD: SeedRow = { id: 2, name: "LiveLeader", probability: 0.979, is_winner: false };
const S_TWO: SeedRow = { id: 3, name: "Second", probability: 0.33, is_winner: false };
const S_THREE: SeedRow = { id: 4, name: "Third", probability: 0.19, is_winner: false };
const S_FOUR: SeedRow = { id: 5, name: "Fourth", probability: 0.1, is_winner: false };
const SEED_FIELD: SeedRow[] = [S_GRADED, S_LEAD, S_TWO, S_THREE, S_FOUR];

describe("#7439 pickChartSeedOutcomes — live, mutually_exclusive false", () => {
  test("THE SPECIMEN: seeds the live rows, so no flat 100% line is drawn on an open market", () => {
    const seeds = pickChartSeedOutcomes(SEED_FIELD, false, false);
    expect(seeds).toEqual([S_LEAD, S_TWO, S_THREE]);
    expect(seeds).not.toContain(S_GRADED);
  });

  test("still seeds three rows — the filter must not shrink the chart", () => {
    expect(pickChartSeedOutcomes(SEED_FIELD, false, false)).toHaveLength(3);
  });

  test("EVERY row graded -> falls back to the full board, never an empty chart", () => {
    const allGraded: SeedRow[] = [
      { id: 1, name: "A", probability: 1.0, is_winner: true },
      { id: 2, name: "B", probability: 0.9, is_winner: true },
    ];
    const seeds = pickChartSeedOutcomes(allGraded, false, false);
    expect(seeds).toHaveLength(2);
    expect(seeds[0]).toBe(allGraded[0]);
  });

  test("🪤 all live rows at 0% -> the seed HOLDS, so chart and hero agree", () => {
    // If the hero holds the graded row and the chart dropped it, the page would
    // headline one row and plot three others. Both carry the same two clauses.
    const ladder: SeedRow[] = [
      { id: 1, name: "Above 56", probability: 0.9995, is_winner: true },
      { id: 2, name: "Above 60", probability: 0, is_winner: false },
      { id: 3, name: "Above 65", probability: 0, is_winner: false },
    ];
    const seeds = pickChartSeedOutcomes(ladder, false, false);
    expect(seeds[0]).toBe(ladder[0]);
    expect(pickHeroOutcome(ladder, ladder[0], false, false)).toBe(ladder[0]);
  });

  test("shuffled payload order still seeds by probability", () => {
    const shuffled = [S_THREE, S_GRADED, S_LEAD, S_FOUR, S_TWO];
    expect(pickChartSeedOutcomes(shuffled, false, false)).toEqual([S_LEAD, S_TWO, S_THREE]);
  });

  test("does not mutate the array it is given", () => {
    const rows = [S_THREE, S_GRADED, S_LEAD];
    const before = [...rows];
    pickChartSeedOutcomes(rows, false, false);
    expect(rows).toEqual(before);
    expect(rows[0]).toBe(S_THREE);
  });
});

describe("#7439 pickChartSeedOutcomes CONTROL — mutex and settled fields must NOT move", () => {
  test("mutually_exclusive TRUE keeps the graded row in the seed — it is the answer", () => {
    const seeds = pickChartSeedOutcomes(SEED_FIELD, false, true);
    expect(seeds).toEqual([S_GRADED, S_LEAD, S_TWO]);
    expect(seeds).toContain(S_GRADED);
  });

  test("mutually_exclusive UNDEFINED and NULL keep today's behaviour", () => {
    expect(pickChartSeedOutcomes(SEED_FIELD, false, undefined)).toEqual([
      S_GRADED,
      S_LEAD,
      S_TWO,
    ]);
    expect(pickChartSeedOutcomes(SEED_FIELD, false, null)).toEqual([S_GRADED, S_LEAD, S_TWO]);
    // The 3-argument shape every pre-#7439 caller used.
    expect(pickChartSeedOutcomes(SEED_FIELD, false)).toEqual([S_GRADED, S_LEAD, S_TWO]);
  });

  test("SETTLED is unchanged under either flag: the winner plus the runner-up (L2-156 Item 2)", () => {
    // The winner is deliberately NOT the highest current probability here.
    const settled: SeedRow[] = [
      { id: 1, name: "FrozenHigh", probability: 0.9, is_winner: false },
      { id: 2, name: "ActualWinner", probability: 0.2, is_winner: true },
      { id: 3, name: "Other", probability: 0.5, is_winner: false },
    ];
    for (const flag of [false, true, null, undefined] as const) {
      const seeds = pickChartSeedOutcomes(settled, true, flag);
      expect(seeds).toHaveLength(2);
      expect(seeds[0]).toBe(settled[1]);
      expect(seeds[1]).toBe(settled[0]);
    }
  });

  test("settled with a single outcome seeds just that one", () => {
    const one: SeedRow[] = [{ id: 1, name: "Only", probability: 1, is_winner: true }];
    expect(pickChartSeedOutcomes(one, true, false)).toEqual([one[0]]);
  });

  test("settled with nothing graded falls back to the price leader", () => {
    const none: SeedRow[] = [
      { id: 1, name: "Low", probability: 0.1, is_winner: false },
      { id: 2, name: "High", probability: 0.8, is_winner: false },
    ];
    expect(pickChartSeedOutcomes(none, true, false)[0]).toBe(none[1]);
  });

  test("an empty field seeds nothing rather than throwing", () => {
    // 🪤 `toEqual([])` IS VACUOUS HERE and this arm used to use it. Deleting the
    // function's empty guard makes the settled branch return `[undefined]` —
    // `outcomes.find(...)` is undefined and `[].find(...)` never runs its
    // predicate, so nothing throws — and jest's `toEqual` treats `[undefined]`
    // as equal to `[]`. The mutant survived a green assertion. `toHaveLength`
    // and `toStrictEqual` both see the difference; both are here on purpose.
    expect(pickChartSeedOutcomes([], false, false)).toStrictEqual([]);
    expect(pickChartSeedOutcomes([], true, false)).toStrictEqual([]);
    expect(pickChartSeedOutcomes([], true, false)).toHaveLength(0);
    expect(pickChartSeedOutcomes([], true, true)).toHaveLength(0);
  });
});

/**
 * #7439 — the page WIRING.
 *
 * ⚠️ WHAT THIS BLOCK CAN AND CANNOT PROVE, stated plainly so nobody reads more
 * into a green run than it earns.
 *
 * Both helpers above are proven by real assertions. What no assertion above can
 * see is whether the PAGE hands them the live `mutually_exclusive` or a
 * hardcoded constant — three mutants (drop the argument, pass `false`, pass
 * `true`) survived the whole battery, because nothing renders this page: an
 * `app/**\/page.tsx` may not carry a second named export for a test, and a full
 * render needs SWR, recharts and framer.
 *
 * So this is a SOURCE assertion, the same instrument `futuresDetailHeroChart`
 * uses on this file and for the same reason. It is weak against logic — a grep
 * cannot tell a correct filter from an inverted one, which is exactly why the
 * seed rule was moved OUT of the page rather than pinned here. But the claim
 * being made here is itself textual ("the call site passes the real field, not
 * a literal"), so the instrument matches the claim.
 *
 * A render test would be strictly better. It is not free, and it is not this
 * ship.
 */
describe("#7439 page wiring — the real field reaches both call sites", () => {
  const { readFileSync } = require("fs");
  const { join } = require("path");
  const code: string = readFileSync(
    join(__dirname, "../../app/futures/[id]/page.tsx"),
    "utf8",
  )
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\/\/.*$/gm, "");

  test("the page imports both helpers", () => {
    expect(code).toContain("pickHeroOutcome");
    expect(code).toContain("pickChartSeedOutcomes");
  });

  test("the hero call passes market.mutually_exclusive after isResolved", () => {
    expect(code).toMatch(
      /pickHeroOutcome\(\s*market\.outcomes\s*,\s*leader\s*,\s*isResolved\s*,\s*market\.mutually_exclusive\s*,?\s*\)/,
    );
  });

  test("the chart seed call passes market.mutually_exclusive", () => {
    expect(code).toMatch(
      /pickChartSeedOutcomes\(\s*market\.outcomes\s*,[\s\S]{0,80}?market\.mutually_exclusive\s*,?\s*\)/,
    );
  });

  test("neither call site hardcodes the flag", () => {
    expect(code).not.toMatch(/pickHeroOutcome\([\s\S]{0,80}?isResolved\s*,\s*(true|false)\s*\)/);
    expect(code).not.toMatch(/pickChartSeedOutcomes\([\s\S]{0,100}?,\s*(true|false)\s*,?\s*\)/);
  });

  test("the seed effect re-runs when the flag changes", () => {
    // The rule now reads `mutually_exclusive`, so it belongs in the dep array;
    // without it a market whose flag arrives late would keep its first seed.
    expect(code).toMatch(
      /\[\s*market\?\.outcomes\s*,\s*market\?\.status\s*,\s*market\?\.mutually_exclusive\s*,\s*historyOutcomes\s*\]/,
    );
  });
});
