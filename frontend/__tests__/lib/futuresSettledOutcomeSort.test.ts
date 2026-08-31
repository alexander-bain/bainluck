/**
 * UX-P232 — CERT-598's BLOCK: ON A SETTLED MARKET THE TABLE LED WITH A LOSER.
 *
 * ═══ WHAT UX-P230 FIXED, AND WHAT IT DID NOT ═══
 *
 * UX-P230 turned the "All Outcomes" table the right way up: the leader stopped
 * rendering last. Its guard states the invariant a reader leans on —
 *
 *     Under the page's own default sort, the FIRST row is the outcome the hero
 *     is about.
 *
 * — and then proved it on two OPEN markets only. On a RESOLVED market the hero
 * is not the price leader. `pickHeroOutcome(outcomes, leader, true)` deliberately
 * features the GRADED WINNER (`is_winner === true`), which is routinely not the
 * highest last-traded probability, because the last price is frozen at whatever it
 * was when the market closed. `sortFuturesOutcomes` could not see `is_winner` at
 * all, so on exactly the surface the page titles **"Final Results"** the hero and
 * the first row disagreed again — the same defect UX-P230 existed to kill, one
 * state over.
 *
 * ═══ THE REAL SPECIMEN, NOT A HYPOTHETICAL ═══
 *
 * `uxp232_futures_59748620_resolved.json` is the verbatim production
 * `GET /api/futures/59748620` body, banked 2026-08-31 18:3xZ. "Arsenal vs Coventry:
 * First Goalscorer", `status: "resolved"`, 13 outcomes:
 *
 *     Christos Tzolis      99%   lost
 *     Riccardo Calafiori   99%   lost
 *     Kai Havertz          21%   WON      ← the hero's subject
 *     Bukayo Saka          17%   lost
 *     … nine more, down to Caleb Yirenkyi at 2%
 *
 * So on UX-P230's own bytes this settled page leads with **Christos Tzolis at 99%,
 * who did not score**, and the man who did sits at row three under a heading that
 * says "Final Results". (On the bytes in production TODAY, which sort ascending,
 * it leads with Caleb Yirenkyi at 2% — both arms bury the winner; only the repair
 * surfaces him.)
 *
 * This is not a rare shape. A `db-query` over resolved multi-outcome markets
 * ordered by id descending returned a full truncated page of them on the first
 * try — EUR/USD ranges, WTI oil ranges, first-goalscorer books, Trump approval
 * bands — every one a market whose winner is not its price leader.
 *
 * ═══ THE RULE, AND ITS DELIBERATE LIMIT ═══
 *
 * The winner leads the **results order** — `probability` + `desc`, which is the
 * page's default and the only ordering that claims to answer "what happened".
 * An EXPLICIT `name` or `change` sort, or `probability` ascending, is a request
 * for a different question and is answered literally: the arrow on the pill must
 * not lie. CERT-598 asked for exactly this limit.
 */

import {
  pickHeroOutcome,
  sortFuturesOutcomes,
  type FuturesSortDirection,
  type FuturesSortField,
} from "@/lib/futuresDetailDisplay";

import resolvedMarket from "../fixtures/uxp232_futures_59748620_resolved.json";
import market109441 from "../fixtures/uxp230_futures_109441.json";

interface Outcome {
  name: string;
  probability: number | null;
  probability_change_24h?: number | null;
  is_winner?: boolean | null;
}

const GOALSCORER = resolvedMarket.outcomes as Outcome[];
const AI_SERIES = market109441.outcomes as Outcome[];

const names = (outcomes: readonly Outcome[]) => outcomes.map((o) => o.name);

/** The page's own defaults (`page.tsx` useState initialisers). */
const DEFAULT_FIELD: FuturesSortField = "probability";
const DEFAULT_DIRECTION: FuturesSortDirection = "desc";

/** How the page derives its hero: highest probability, then the winner override. */
function heroOf(outcomes: readonly Outcome[], resolved: boolean): Outcome | null {
  const leader = [...outcomes].sort((a, b) => (b.probability ?? 0) - (a.probability ?? 0))[0] ?? null;
  return pickHeroOutcome(outcomes, leader, resolved);
}

describe("the fixture is the settled market it claims to be (harness validity)", () => {
  test("59748620 is resolved, 13-way, and its winner is NOT its price leader", () => {
    expect(resolvedMarket.status).toBe("resolved");
    expect(GOALSCORER).toHaveLength(13);

    const winner = GOALSCORER.filter((o) => o.is_winner === true);
    expect(winner).toHaveLength(1);
    expect(winner[0].name).toBe("Kai Havertz");
    expect(winner[0].probability).toBeCloseTo(0.21, 5);

    // The whole reason this file exists: two losers are priced far above him.
    const top = Math.max(...GOALSCORER.map((o) => o.probability ?? 0));
    expect(top).toBeCloseTo(0.99, 5);
    expect(winner[0].probability ?? 0).toBeLessThan(top);
  });

  test("the hero features Havertz, so the table has something to disagree with", () => {
    expect(heroOf(GOALSCORER, true)?.name).toBe("Kai Havertz");
    // And the page's own leader — what the table led with before this fix — is not him.
    expect(heroOf(GOALSCORER, false)?.name).toBe("Christos Tzolis");
  });
});

describe("UX-P232: a settled table leads with the winner", () => {
  test("the first row is Kai Havertz, not the 99% loser", () => {
    const sorted = sortFuturesOutcomes(GOALSCORER, DEFAULT_FIELD, DEFAULT_DIRECTION, true);
    expect(sorted[0].name).toBe("Kai Havertz");
    expect(sorted[0].is_winner).toBe(true);
  });

  test("everything below the winner keeps the probability order", () => {
    // The winner is lifted out; the rest of the table is untouched. A fix that
    // reordered the losers would be solving a different problem.
    const sorted = sortFuturesOutcomes(GOALSCORER, DEFAULT_FIELD, DEFAULT_DIRECTION, true);
    const losers = sorted.slice(1);
    expect(losers.every((o) => o.is_winner !== true)).toBe(true);
    for (let i = 1; i < losers.length; i++) {
      expect(losers[i - 1].probability ?? 0).toBeGreaterThanOrEqual(losers[i].probability ?? 0);
    }
    expect(losers[0].probability).toBeCloseTo(0.99, 5);
  });

  test("THE INVARIANT, stated for BOTH states: the first row is the hero's subject", () => {
    // This is the assertion UX-P230 wrote and could only prove on open markets.
    // It is the one that would have caught CERT-598's finding the day it shipped.
    for (const [outcomes, resolved] of [
      [GOALSCORER, true],
      [AI_SERIES, false],
    ] as [Outcome[], boolean][]) {
      const sorted = sortFuturesOutcomes(outcomes, DEFAULT_FIELD, DEFAULT_DIRECTION, resolved);
      expect(sorted[0].name).toBe(heroOf(outcomes, resolved)?.name);
    }
  });

  test("the winner is inside the first 25 rows even in a field that overflows the slice", () => {
    // `page.tsx` renders `sortedOutcomes.slice(0, 25)` until "Show all N" is
    // clicked. A winner priced near zero in a 60-way field was off the page
    // entirely — the failure UX-P230 measured for leaders, unfixed for winners.
    const field: Outcome[] = Array.from({ length: 60 }, (_, i) => ({
      name: `Runner ${i}`,
      probability: (60 - i) / 100,
      is_winner: false,
    }));
    field.push({ name: "Longshot", probability: 0.004, is_winner: true });

    const sorted = sortFuturesOutcomes(field, DEFAULT_FIELD, DEFAULT_DIRECTION, true);
    expect(sorted.slice(0, 25).map((o) => o.name)).toContain("Longshot");
    expect(sorted[0].name).toBe("Longshot");
  });

  test("a settled market with NO graded winner is plain probability order", () => {
    // `pickHeroOutcome` falls back to the leader when nothing is flagged, so the
    // table must fall back with it — hero and first row still agree.
    const ungraded = GOALSCORER.map((o) => ({ ...o, is_winner: null }));
    const sorted = sortFuturesOutcomes(ungraded, DEFAULT_FIELD, DEFAULT_DIRECTION, true);
    expect(sorted[0].name).toBe("Christos Tzolis");
    expect(sorted[0].name).toBe(heroOf(ungraded, true)?.name);
  });

  test("several graded winners all lead, ordered among themselves by probability", () => {
    // Not every settled market grades exactly one outcome true.
    const multi: Outcome[] = [
      { name: "Loud loser", probability: 0.9, is_winner: false },
      { name: "Small winner", probability: 0.05, is_winner: true },
      { name: "Big winner", probability: 0.4, is_winner: true },
      { name: "Quiet loser", probability: 0.2, is_winner: false },
    ];
    expect(names(sortFuturesOutcomes(multi, DEFAULT_FIELD, DEFAULT_DIRECTION, true))).toEqual([
      "Big winner",
      "Small winner",
      "Loud loser",
      "Quiet loser",
    ]);
  });

  test("`is_winner: false` and `is_winner: null` are both simply 'not the winner'", () => {
    // An ungraded row must not be promoted above a graded loser, and must not be
    // demoted below one either — neither won.
    const mixed: Outcome[] = [
      { name: "Graded loser", probability: 0.3, is_winner: false },
      { name: "Ungraded", probability: 0.5, is_winner: null },
      { name: "Winner", probability: 0.1, is_winner: true },
    ];
    expect(names(sortFuturesOutcomes(mixed, DEFAULT_FIELD, DEFAULT_DIRECTION, true))).toEqual([
      "Winner",
      "Ungraded",
      "Graded loser",
    ]);
  });
});

describe("UX-P232: the rule does NOT reach past the results order", () => {
  test("an OPEN market ignores is_winner entirely", () => {
    // A stray flag on a live market must not reorder anything. `resolved` is the
    // gate, and the page reads it from `market.status`, not from the outcomes.
    const live = GOALSCORER;
    expect(names(sortFuturesOutcomes(live, DEFAULT_FIELD, DEFAULT_DIRECTION, false))[0]).toBe(
      "Christos Tzolis",
    );
    // Identical to not passing the argument at all.
    expect(names(sortFuturesOutcomes(live, DEFAULT_FIELD, DEFAULT_DIRECTION))).toEqual(
      names(sortFuturesOutcomes(live, DEFAULT_FIELD, DEFAULT_DIRECTION, false)),
    );
  });

  test("probability ASCENDING stays honest — the arrow must not lie", () => {
    // "Probability ↑" is an explicit request for smallest-first. Forcing a 21%
    // winner above a 2% longshot would make the pill's arrow untrue.
    const sorted = sortFuturesOutcomes(GOALSCORER, "probability", "asc", true);
    expect(sorted[0].name).toBe("Caleb Yirenkyi");
    expect(sorted[0].probability).toBeCloseTo(0.02, 5);
    for (let i = 1; i < sorted.length; i++) {
      expect(sorted[i - 1].probability ?? 0).toBeLessThanOrEqual(sorted[i].probability ?? 0);
    }
  });

  test("an explicit NAME sort is alphabetical, winner or not", () => {
    for (const direction of ["asc", "desc"] as FuturesSortDirection[]) {
      const sorted = sortFuturesOutcomes(GOALSCORER, "name", direction, true);
      const expected = [...names(GOALSCORER)].sort((a, b) => a.localeCompare(b));
      expect(names(sorted)).toEqual(direction === "asc" ? expected : expected.reverse());
    }
  });

  test("an explicit CHANGE sort ranks by the move, winner or not", () => {
    const moved: Outcome[] = [
      { name: "Winner", probability: 0.1, probability_change_24h: -0.2, is_winner: true },
      { name: "Gainer", probability: 0.6, probability_change_24h: 0.3, is_winner: false },
    ];
    expect(names(sortFuturesOutcomes(moved, "change", "desc", true))).toEqual(["Gainer", "Winner"]);
    expect(names(sortFuturesOutcomes(moved, "change", "asc", true))).toEqual(["Winner", "Gainer"]);
  });
});

describe("UX-P232: properties that hold whatever the data is", () => {
  const FIELDS: FuturesSortField[] = ["probability", "change", "name"];
  const DIRECTIONS: FuturesSortDirection[] = ["asc", "desc"];

  test("every settled combination is still a permutation", () => {
    for (const field of FIELDS) {
      for (const direction of DIRECTIONS) {
        const sorted = sortFuturesOutcomes(GOALSCORER, field, direction, true);
        expect(sorted).toHaveLength(GOALSCORER.length);
        expect([...names(sorted)].sort()).toEqual([...names(GOALSCORER)].sort());
      }
    }
  });

  test("the input array is never mutated", () => {
    const before = names(GOALSCORER);
    for (const field of FIELDS) {
      for (const direction of DIRECTIONS) {
        sortFuturesOutcomes(GOALSCORER, field, direction, true);
      }
    }
    expect(names(GOALSCORER)).toEqual(before);
  });

  test("the comparator stays antisymmetric — the KEYS do not depend on arrival order", () => {
    // A primary key applied to only one side, or an early return that skips the
    // direction flip, makes the comparator inconsistent and V8 then resolves it
    // from the input's arrival order. Reverse the input and require the same key
    // sequence out. Compared on KEYS, not names, because this market has a
    // genuine 99% tie and a stable sort is entitled to keep ties in arrival order.
    const keys = (outcomes: readonly Outcome[]) =>
      outcomes.map((o) => `${o.is_winner === true ? "W" : "-"}:${o.probability ?? 0}`);

    const forward = sortFuturesOutcomes(GOALSCORER, DEFAULT_FIELD, DEFAULT_DIRECTION, true);
    const reversed = sortFuturesOutcomes(
      [...GOALSCORER].reverse(),
      DEFAULT_FIELD,
      DEFAULT_DIRECTION,
      true,
    );
    expect(keys(reversed)).toEqual(keys(forward));
    // And the winner really is the only row carrying the W key, at the top.
    expect(keys(forward)[0]).toBe("W:0.21");
    expect(keys(forward).filter((k) => k.startsWith("W"))).toHaveLength(1);
  });
});
