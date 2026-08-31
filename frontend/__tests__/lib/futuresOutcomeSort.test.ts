/**
 * UX-P230 — THE "ALL OUTCOMES" TABLE SORTED BACKWARDS ON EVERY FUTURES PAGE.
 *
 * ═══ WHAT A READER SAW ═══
 *
 * `/futures/109441` ("which company ships a fully AI-generated scripted series
 * before 2027") renders a hero entirely about Amazon at 27%. Directly beneath it,
 * under a pill reading **"Probability ↓"**, the table listed:
 *
 *     3%  3%  4%  5%  5%  6%  7%  27%
 *
 * Amazon last. `/futures/109349` (iPhone 18 timing) did the same: 1, 1, 7, 15 —
 * the page's own answer at the bottom of its own table. The rank badges came from
 * the payload's `rank` field, so they counted DOWN the page: 8, 7, 6 … 1.
 *
 * ═══ THE MECHANISM ═══
 *
 * `app/futures/[id]/page.tsx` kept three inline comparators and one shared
 * direction flip. Two of the three were authored in reverse:
 *
 *     probability   (b.probability ?? 0) - (a.probability ?? 0)   ← already descending
 *     change        bChange - aChange                             ← already descending
 *     name          a.name.localeCompare(b.name)                  ← normal convention
 *     …then          direction === "asc" ? comparison : -comparison
 *
 * `name` is the only one written in the normal convention, and that inconsistency
 * is the tell: the shared inverter was written for `name` and then applied to two
 * comparators that had already done the inverting themselves. Default state is
 * `probability` + `desc`, so the page shipped `-(b - a)` = ascending.
 *
 * ═══ WHY THIS FILE EXISTS AND NOT JUST A RENDER TEST ═══
 *
 * An inline switch can only be reached through the page's own state, and the page
 * default exercises exactly ONE of the six field×direction combinations. Five had
 * never been under test — which is how two comparators sat backwards. The
 * comparator now lives in `lib/futuresDetailDisplay` under one stated convention
 * (**every comparator is ascending; the flip at the bottom is the only reverser**)
 * and all six combinations are asserted below.
 *
 * The rendered-order half — that the first row a reader sees IS the hero's leader —
 * is `__tests__/components/futuresDetailOutcomeOrder.test.tsx`, which SSR-renders
 * the real page. Neither file substitutes for the other: this one proves the rule,
 * that one proves the page obeys it.
 *
 * ═══ THE DATA ═══
 *
 * Both fixtures are verbatim production `GET /api/futures/<id>` bodies banked
 * 2026-08-31 17:2xZ — the two markets Alex reviewed, with the values he saw.
 */

import {
  sortFuturesOutcomes,
  type FuturesSortField,
  type FuturesSortDirection,
} from "@/lib/futuresDetailDisplay";

import market109441 from "../fixtures/uxp230_futures_109441.json";
import market109349 from "../fixtures/uxp230_futures_109349.json";

interface Outcome {
  name: string;
  probability: number | null;
  probability_change_24h?: number | null;
}

const AI_SERIES = market109441.outcomes as Outcome[];
const IPHONE_18 = market109349.outcomes as Outcome[];

const names = (outcomes: readonly Outcome[]) => outcomes.map((o) => o.name);
const pcts = (outcomes: readonly Outcome[]) =>
  outcomes.map((o) => Math.round((o.probability ?? 0) * 100));

/** The page's own defaults (`page.tsx` useState initialisers). */
const DEFAULT_FIELD: FuturesSortField = "probability";
const DEFAULT_DIRECTION: FuturesSortDirection = "desc";

describe("the fixtures are the markets Alex reviewed (harness validity)", () => {
  // A guard whose fixture has drifted proves nothing. Pin the facts the
  // assertions below actually lean on.
  test("109441 is the eight-way AI-series market with Amazon at 27%", () => {
    expect(AI_SERIES).toHaveLength(8);
    const amazon = AI_SERIES.find((o) => o.name === "Amazon");
    expect(amazon?.probability).toBeCloseTo(0.27, 5);
    // Amazon is the highest-probability outcome, i.e. the hero's leader.
    expect(Math.max(...AI_SERIES.map((o) => o.probability ?? 0))).toBeCloseTo(0.27, 5);
  });

  test("109349 is the four-way iPhone 18 market led by 'Before 2027' at 15%", () => {
    expect(IPHONE_18).toHaveLength(4);
    expect(IPHONE_18.find((o) => o.name === "Before 2027")?.probability).toBeCloseTo(0.15, 5);
  });

  test("both carry outcomes with a null 24h change, so the null path is exercised", () => {
    expect(AI_SERIES.some((o) => o.probability_change_24h == null)).toBe(true);
    expect(IPHONE_18.some((o) => o.probability_change_24h == null)).toBe(true);
  });
});

describe("UX-P230: the default sort puts the leader first", () => {
  test("109441 reads 27, 7, 6, 5, 5, 4, 3, 3 — not 3, 3, 4, 5, 5, 6, 7, 27", () => {
    const sorted = sortFuturesOutcomes(AI_SERIES, DEFAULT_FIELD, DEFAULT_DIRECTION);
    expect(pcts(sorted)).toEqual([27, 7, 6, 5, 5, 4, 3, 3]);
    expect(sorted[0].name).toBe("Amazon");
  });

  test("109349 reads 15, 7, 1, 1 — not 1, 1, 7, 15", () => {
    const sorted = sortFuturesOutcomes(IPHONE_18, DEFAULT_FIELD, DEFAULT_DIRECTION);
    expect(pcts(sorted)).toEqual([15, 7, 1, 1]);
    expect(sorted[0].name).toBe("Before 2027");
  });

  test("the first row is the highest-probability outcome, on both markets", () => {
    // The invariant a reader relies on, stated independently of the fixture's
    // literal ordering: nothing may outrank the leader under the default sort.
    for (const outcomes of [AI_SERIES, IPHONE_18]) {
      const sorted = sortFuturesOutcomes(outcomes, DEFAULT_FIELD, DEFAULT_DIRECTION);
      const best = Math.max(...outcomes.map((o) => o.probability ?? 0));
      expect(sorted[0].probability ?? 0).toBe(best);
    }
  });

  test("descending probability is monotonic all the way down", () => {
    const sorted = sortFuturesOutcomes(AI_SERIES, "probability", "desc");
    for (let i = 1; i < sorted.length; i++) {
      expect(sorted[i - 1].probability ?? 0).toBeGreaterThanOrEqual(sorted[i].probability ?? 0);
    }
  });
});

describe("UX-P230: all six field × direction combinations", () => {
  test("probability / asc is the honest ascending order (the smallest first)", () => {
    const sorted = sortFuturesOutcomes(AI_SERIES, "probability", "asc");
    expect(pcts(sorted)).toEqual([3, 3, 4, 5, 5, 6, 7, 27]);
    expect(sorted[sorted.length - 1].name).toBe("Amazon");
  });

  test("change / desc puts the biggest GAINER first and the biggest loser last", () => {
    // Real 24h moves on 109441: Disney +1.5pts, Amazon -71.5pts, the rest 0 or null.
    const sorted = sortFuturesOutcomes(AI_SERIES, "change", "desc");
    expect(sorted[0].name).toBe("Disney");
    expect(sorted[0].probability_change_24h).toBeCloseTo(0.015, 5);
    expect(sorted[sorted.length - 1].name).toBe("Amazon");
    expect(sorted[sorted.length - 1].probability_change_24h).toBeCloseTo(-0.715, 5);
  });

  test("change / asc puts the biggest LOSER first — the mirror, not the same list", () => {
    const sorted = sortFuturesOutcomes(AI_SERIES, "change", "asc");
    expect(sorted[0].name).toBe("Amazon");
    expect(sorted[sorted.length - 1].name).toBe("Disney");
  });

  test("change sorts on the SIGNED move, never its magnitude", () => {
    // -71.5 is the largest magnitude on the board and the smallest signed value.
    // A magnitude sort would put Amazon FIRST under `desc`; it must be last.
    const desc = sortFuturesOutcomes(AI_SERIES, "change", "desc");
    expect(desc[0].name).not.toBe("Amazon");
  });

  test("a null 24h change reads as zero, not as a missing row", () => {
    const desc = sortFuturesOutcomes(AI_SERIES, "change", "desc");
    expect(desc).toHaveLength(AI_SERIES.length);
    // The four null-change outcomes sit between Disney (+1.5) and the negatives.
    const nullNames = AI_SERIES.filter((o) => o.probability_change_24h == null).map((o) => o.name);
    const positions = nullNames.map((n) => desc.findIndex((o) => o.name === n));
    expect(Math.min(...positions)).toBeGreaterThan(desc.findIndex((o) => o.name === "Disney"));
    expect(Math.max(...positions)).toBeLessThan(desc.findIndex((o) => o.name === "Amazon"));
  });

  test("a null 24h change and an explicit zero are INTERCHANGEABLE", () => {
    // "No move reported" and "moved by zero" must order identically — and the
    // two `?? 0` defaults in the comparator must agree with each other. A default
    // applied to only one side of the subtraction makes the comparator
    // inconsistent (not antisymmetric), which V8's sort resolves arbitrarily:
    // the order then depends on the input's arrival order, not on the data.
    const withNull: Outcome[] = [
      { name: "Up", probability: 0.4, probability_change_24h: 0.05 },
      { name: "Flat", probability: 0.3, probability_change_24h: null },
      { name: "Down", probability: 0.2, probability_change_24h: -0.05 },
      { name: "Zero", probability: 0.1, probability_change_24h: 0 },
    ];
    const withZero: Outcome[] = withNull.map((o) =>
      o.name === "Flat" ? { ...o, probability_change_24h: 0 } : o,
    );

    for (const direction of ["asc", "desc"] as FuturesSortDirection[]) {
      expect(names(sortFuturesOutcomes(withNull, "change", direction))).toEqual(
        names(sortFuturesOutcomes(withZero, "change", direction)),
      );
    }

    // And the unmoved rows really do sit between the gainer and the loser.
    const desc = sortFuturesOutcomes(withNull, "change", "desc");
    expect(desc[0].name).toBe("Up");
    expect(desc[desc.length - 1].name).toBe("Down");
    expect(new Set([desc[1].name, desc[2].name])).toEqual(new Set(["Flat", "Zero"]));
  });

  test("name / asc is A→Z", () => {
    const sorted = sortFuturesOutcomes(AI_SERIES, "name", "asc");
    expect(names(sorted)).toEqual([...names(AI_SERIES)].sort((a, b) => a.localeCompare(b)));
    expect(sorted[0].name).toBe("Amazon");
  });

  test("name / desc is Z→A — the flip did NOT get traded away with the fix", () => {
    // The tempting one-line "fix" was to invert line :297 instead of the two
    // comparators. That would have corrected probability and change while
    // reversing name. This is the assertion that refuses that trade.
    const asc = sortFuturesOutcomes(AI_SERIES, "name", "asc");
    const desc = sortFuturesOutcomes(AI_SERIES, "name", "desc");
    expect(names(desc)).toEqual([...names(asc)].reverse());
    expect(desc[0].name).toBe("Peacock");
  });
});

describe("UX-P230: properties that hold whatever the data is", () => {
  const FIELDS: FuturesSortField[] = ["probability", "change", "name"];
  const DIRECTIONS: FuturesSortDirection[] = ["asc", "desc"];

  test("every combination is a permutation — nothing is dropped or duplicated", () => {
    for (const outcomes of [AI_SERIES, IPHONE_18]) {
      for (const field of FIELDS) {
        for (const direction of DIRECTIONS) {
          const sorted = sortFuturesOutcomes(outcomes, field, direction);
          expect(sorted).toHaveLength(outcomes.length);
          expect([...names(sorted)].sort()).toEqual([...names(outcomes)].sort());
        }
      }
    }
  });

  test("the input array is never mutated", () => {
    const before = names(AI_SERIES);
    for (const field of FIELDS) {
      for (const direction of DIRECTIONS) {
        sortFuturesOutcomes(AI_SERIES, field, direction);
      }
    }
    expect(names(AI_SERIES)).toEqual(before);
  });

  test("asc and desc are reverses of each other on every field", () => {
    // Ties make a strict reverse impossible, so compare the sort KEY sequence
    // rather than the row order.
    const key = (o: Outcome, field: FuturesSortField) =>
      field === "name" ? o.name : field === "probability" ? o.probability ?? 0 : o.probability_change_24h ?? 0;
    for (const field of FIELDS) {
      const asc = sortFuturesOutcomes(AI_SERIES, field, "asc").map((o) => key(o, field));
      const desc = sortFuturesOutcomes(AI_SERIES, field, "desc").map((o) => key(o, field));
      expect(desc).toEqual([...asc].reverse());
    }
  });

  test("a null probability sorts as zero and does not crash the comparator", () => {
    const withNull: Outcome[] = [
      { name: "Known", probability: 0.4, probability_change_24h: 0.01 },
      { name: "Unpriced", probability: null, probability_change_24h: null },
      { name: "Low", probability: 0.05, probability_change_24h: -0.02 },
    ];
    expect(names(sortFuturesOutcomes(withNull, "probability", "desc"))).toEqual([
      "Known",
      "Low",
      "Unpriced",
    ]);
  });

  test("an empty list and a single row are both fine", () => {
    expect(sortFuturesOutcomes([], "probability", "desc")).toEqual([]);
    const one: Outcome[] = [{ name: "Solo", probability: 0.5 }];
    expect(names(sortFuturesOutcomes(one, "change", "asc"))).toEqual(["Solo"]);
  });
});
