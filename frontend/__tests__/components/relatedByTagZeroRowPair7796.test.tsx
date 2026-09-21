/**
 * #7796 — A SETTLED ZERO IS NOT ONE OF THE TWO.
 *
 * #5961 moved the card's pair rule onto the rows a reader is actually shown. Its
 * caller reaches that arity by dropping outcomes with no price, and the test it
 * uses is `typeof probability === "number"` — which **`0.0` passes**. So a
 * knockout market narrowed to two live finalists, which also carries a graded-out
 * player at zero, is printed at arity THREE, the pair rule refuses it, and the
 * two live legs are rounded independently again.
 *
 * Photographed on production 2026-09-21 12:05Z on a live event page's
 * `MORE TENNIS` rail (`artifacts/ux-1413/walk-15316200-1600.png`):
 *
 *     WTA Sao Paulo Winner
 *     Kaitlin Quevedo   55%
 *     Nadia Podoroska   46%      55 + 46 = 101
 *     Mary Stoiana       0%
 *     +13 more
 *
 * Two players owning 101% of a sixteen-name draw — #5961's exact picture, one row
 * wider.
 *
 * ## The fixtures are production bytes, and the BEFORE is a measurement
 *
 * `ux1413_related_futures_zero_row_7796` is `GET /api/feed?limit=100` from
 * production at that minute, 79 futures items unedited.
 *
 * `ux1413_related_before_7796` is what the component printed for all 79 of them
 * **as it stood on `origin/master`**, rendered while the defect was live. It is a
 * measurement of the old component, not a re-implementation of its rule: a table
 * recomputed from the payload would agree with the payload by construction and
 * would pass against the unfixed file. ARM 3 diffs today's render against it, so
 * the population claim is a diff of two renders rather than an assertion about
 * one.
 *
 * ## The unfixed directions are asserted as hard as the fixed one (gotcha #43)
 *
 * Three live legs summing to 101 (`Brazil Presidential Election`, 59 + 41 + 1)
 * are NOT this rule's business — that is #5262's arity, and normalizing three
 * legs would invent probability. ARM 2 holds those, and ARM 3 holds every other
 * card on the page, at exactly what they print today.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { renderedFieldRowPercents, renderedPercent } from "@/lib/renderedPercent";
import FIXTURE from "../fixtures/ux1413_related_futures_zero_row_7796.20260921.json";
import BEFORE from "../fixtures/ux1413_related_before_7796.20260921.json";

let swrPayload: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: swrPayload, error: undefined, isLoading: false }),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const RelatedByTag = require("@/components/RelatedByTag").default;

const FIELD_VALUE_CLASS = "shrink-0 tabular-nums font-semibold text-text-primary";

interface PrintedCard {
  title: string;
  rows: { name: string; printed: string }[];
}

/**
 * The rows this markup actually prints, per card — read out of the RENDERED
 * OUTPUT, the same reader `relatedByTagPairRounding5961` uses and for the same
 * reason.
 */
function printedCards(markup: string): PrintedCard[] {
  return markup
    .split('data-testid="related-card"')
    .slice(1)
    .map((block) => {
      const title = (block.match(
        /class="min-w-0 text-\[14px\] font-semibold leading-snug text-text-primary">([^<]*)</
      ) ?? ["", ""])[1];
      const rows = [
        ...block.matchAll(
          new RegExp(
            `class="min-w-0 truncate text-text-secondary">([^<]*)<[^]*?class="${FIELD_VALUE_CLASS}">([^<]*)<`,
            "g"
          )
        ),
      ].map((m) => ({ name: m[1], printed: m[2] }));
      return { title, rows };
    });
}

/** Every card on the banked page, so a population claim is possible at all. */
function renderWholePage(): PrintedCard[] {
  swrPayload = FIXTURE;
  return printedCards(
    renderToStaticMarkup(
      React.createElement(RelatedByTag as React.FC, {
        tags: ["sport:tennis"],
        limit: 200,
        title: "More Tennis",
      } as never)
    )
  );
}

function cardNamed(cards: PrintedCard[], needle: string): PrintedCard {
  const found = cards.find((c) => c.title.includes(needle));
  if (!found) throw new Error(`no card titled like "${needle}"`);
  return found;
}

/** The integer a row printed, or null for `-`, `<1%`, `>99%`. */
function asInt(printed: string): number | null {
  const m = printed.match(/^(\d+)%$/);
  return m ? Number(m[1]) : null;
}

function sumOf(card: PrintedCard): number {
  return card.rows.reduce((total, r) => total + (asInt(r.printed) ?? 0), 0);
}

describe("ARM 1 — renderedFieldRowPercents: the pair is the LIVE legs", () => {
  test("the production specimen totals 100 and keeps its zero row", () => {
    expect(renderedFieldRowPercents([0.545, 0.46, 0])).toEqual([54, 46, 0]);
  });

  test("the zero row does not move the two numbers beside it", () => {
    // The pair must be the same decision whether or not a graded-out player is
    // printed under it. If these two ever disagree, the same market prints two
    // different leaders depending on how many people it has eliminated.
    const withZero = renderedFieldRowPercents([0.545, 0.46, 0]);
    const withoutZero = renderedFieldRowPercents([0.545, 0.46]);
    expect(withZero.slice(0, 2)).toEqual(withoutZero);
  });

  test("several zero rows, in any position, still leave one pair", () => {
    expect(renderedFieldRowPercents([0, 0.545, 0, 0.46])).toEqual([0, 54, 0, 46]);
  });

  test("THE ZERO ROW IS NOT A MIXED CARD: derived and served agree by construction", () => {
    // "Whole or not at all" (#2279) forbids a card printing a derived number
    // beside a served one. A zero is the one value where the two paths cannot
    // disagree — assert it rather than take it on trust.
    expect(renderedPercent(0)).toBe(0);
    const served = (FIXTURE.items as Array<{ data: { id: number; top_outcomes: Array<{ probability: number | null; rendered_percent: number | null }> } }>)
      .find((i) => i.data.id === 61264062)!;
    const zeroRow = served.data.top_outcomes.find((o) => o.probability === 0)!;
    expect(zeroRow.rendered_percent).toBe(0);
    expect(renderedFieldRowPercents([0.545, 0.46, 0])[2]).toBe(zeroRow.rendered_percent);
  });

  test("THREE live legs are refused — that is #5262's arity, not this one", () => {
    // `Brazil Presidential Election`, 0.59 / 0.41 / 0.01 on the banked page,
    // prints 101 and must go on printing 101: normalizing three legs would
    // invent probability rather than round it.
    expect(renderedFieldRowPercents([0.59, 0.41, 0.01])).toEqual([null, null, null]);
  });

  test("ONE live leg is refused", () => {
    expect(renderedFieldRowPercents([0.94, 0, 0])).toEqual([null, null, null]);
  });

  test("arity two is delegated untouched, zero row or not", () => {
    expect(renderedFieldRowPercents([0.545, 0.46])).toEqual([54, 46]);
    // Out of the complement band: two independent questions, rounded apart.
    expect(renderedFieldRowPercents([0.3, 0.17])).toEqual([30, 17]);
  });

  test("an out-of-band pair with a zero row is NOT normalized", () => {
    // 0.3 + 0.17 = 0.47. The rule may reach it, and must not change it.
    expect(renderedFieldRowPercents([0.3, 0.17, 0])).toEqual([30, 17, 0]);
  });

  test("a row it cannot place makes it answer for nothing", () => {
    expect(renderedFieldRowPercents([0.545, 0.46, null])).toEqual([null, null, null]);
    expect(renderedFieldRowPercents([0.545, 0.46, Number.NaN])).toEqual([null, null, null]);
    expect(renderedFieldRowPercents([0.545, 0.46, -0.1])).toEqual([null, null, null]);
    expect(renderedFieldRowPercents([])).toEqual([]);
    expect(renderedFieldRowPercents(null)).toEqual([]);
  });
});

describe("ARM 2 — the rendered card: 101 becomes 100, the zero stays", () => {
  test("the specimen prints 54 / 46 / 0", () => {
    const card = cardNamed(renderWholePage(), "WTA Sao Paulo Winner");
    expect(card.rows.map((r) => r.printed)).toEqual(["54%", "46%", "0%"]);
    expect(sumOf(card)).toBe(100);
    // The eliminated player is still on the card — a 0.0 that is a verdict is a
    // fact and belongs on the page (#6195). Dropping her would also fix the
    // total, which is exactly why the row count is asserted beside the sum: the
    // wrong fix passes a total check and fails this one.
    expect(card.rows).toHaveLength(3);
    expect(card.rows[2].name).toBe("Mary Stoiana");
  });

  test("the zero row survives the fix on EVERY card that has one", () => {
    // The same claim over the population rather than the specimen, so a filter
    // change cannot quietly drop verdict rows on cards this suite does not name.
    const zeroRowsBefore = (BEFORE.cards as PrintedCard[]).reduce(
      (n, c) => n + c.rows.filter((r) => r.printed === "0%").length,
      0
    );
    const zeroRowsAfter = renderWholePage().reduce(
      (n, c) => n + c.rows.filter((r) => r.printed === "0%").length,
      0
    );
    expect(zeroRowsBefore).toBeGreaterThan(0);
    expect(zeroRowsAfter).toBe(zeroRowsBefore);
  });

  test("the card the BEFORE printed is the card this replaces", () => {
    // Anchors the claim to the measured old output rather than to prose: if the
    // BEFORE ever stops carrying the defect, this arm says so instead of quietly
    // comparing two identical things.
    const before = (BEFORE.cards as PrintedCard[]).find((c) =>
      c.title.includes("WTA Sao Paulo Winner")
    )!;
    expect(before.rows.map((r) => r.printed)).toEqual(["55%", "46%", "0%"]);
    expect(sumOf(before)).toBe(101);
  });

  test("three live legs summing to 101 are LEFT at 101", () => {
    const card = cardNamed(renderWholePage(), "Brazil Presidential Election");
    expect(sumOf(card)).toBe(101);
  });
});

describe("ARM 3 — the population: exactly one card moves", () => {
  test("every other card on the banked page is byte-identical to the BEFORE", () => {
    const after = renderWholePage();
    const before = BEFORE.cards as PrintedCard[];
    expect(after).toHaveLength(before.length);
    expect(after).toHaveLength(79);

    const moved = after
      .map((card, i) => ({ card, before: before[i] }))
      .filter(
        ({ card, before: was }) =>
          JSON.stringify(card) !== JSON.stringify(was)
      );

    expect(moved.map((m) => m.card.title)).toEqual(["WTA Sao Paulo Winner"]);
  });

  test("no card on the page prints a total it did not print before, except that one", () => {
    // The same claim taken on the number a reader adds up, so a change that
    // preserved the row strings while moving a total could not hide here.
    const after = renderWholePage();
    const before = BEFORE.cards as PrintedCard[];
    const changedTotals = after
      .map((card, i) => [card.title, sumOf(card), sumOf(before[i])] as const)
      .filter(([, now, was]) => now !== was);
    expect(changedTotals).toEqual([["WTA Sao Paulo Winner", 100, 101]]);
  });
});
