// #5296 — THE DIVERGENCE's `current` pairs still summed to 101%, and its badge
// still contradicted the two levels it sits between.
//
// This is the half #5240 deliberately did not take. That diff says why, in its
// own text: `current` carries the identical rounding defect, but THE DIVERGENCE
// prints a LEVEL and a MOVE, and #2951's rule is that a printed delta is the
// difference of the PRINTED levels. Correcting the levels without the badge would
// make the row contradict itself one column to the right. So the two are decided
// together, by the family, in `divergencePairPercents`.
//
// WHAT A READER SAW. Two separate contradictions, both live on production:
//
//   1. THE SUM. `/events/15310379` (FC Inter Turku v Vaasan Palloseura, LIVE,
//      2026-09-11 18:30Z) served `Both Teams to Score in First Half` as
//      No `0.835` / Yes `0.165` — an exact complement on the wire. Rounded
//      independently that is `Math.round(83.5) = 84` and `Math.round(16.5) = 17`:
//      two sides of one question printing 101%.
//
//   2. THE BADGE. A pair on the half-percent grid moving `0.905 → 0.91` prints
//      both levels as 91% and then a `↑ 1` between them — a badge claiming a move
//      between two identical printed numbers. This is #2951's own Gauff case
//      (`Coco Gauff +1 63%` over "opened at 63%"), which was fixed for match rows
//      in `lib/matchList.ts` and never reached the props body. Worse, the two legs
//      of that one pair disagree with each other: `Math.round(0.5)` is 1 and
//      `Math.round(-0.5)` is -0, so the same move renders `↑ 1` on one side and
//      `±0` on the other.
//
//   3. AND THE DRAWER. Because `isUnchanged` used the raw rounding while the badge
//      used its own, a row could print `↑ 1` from inside the disclosure labelled
//      "didn't move", or sit in the moved list showing `±0`.
//
// NO NEW ROUNDING RULE. `renderedDuelMovePoints` is #2951's existing helper,
// already load-bearing in `lib/matchList.ts`; it rounds BOTH pairs through
// `renderedDuelPercents` and subtracts the results, which is why an opening pair
// cannot sum to 101 either.
//
// SCOPED TO COMPLEMENT PAIRS. A non-complement two-leg family keeps today's
// arithmetic exactly — see the controls. That is the difference between fixing
// this defect and letting #2951 reach a population this ship never measured.
//
// RED-FIRST, measured rather than asserted. Against the parent commit this file
// scores 5 failed, 8 passed of 13. The five that red are the five ship
// assertions; the eight that pass are controls, named individually below so
// "8 passed" is evidence and not a number.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import PropsSection from "../../components/event/PropsSection";
import type { PropMark } from "../../components/event/PropsSection";

const divergence = (items: PropMark[]) =>
  renderToStaticMarkup(<PropsSection items={items} state="divergence" />);
const script = (items: PropMark[]) =>
  renderToStaticMarkup(<PropsSection items={items} state="script" />);

/**
 * SPECIMEN 1 — the real live row. `0.835 + 0.165` is an exact complement, and both
 * legs sit on the `.5` boundary `Math.round` takes upward.
 */
const TURKU: PropMark[] = [
  {
    key: "FC Inter Turku vs. Vaasan Palloseura: Both Teams to Score in First Half|No",
    label: "No",
    pregame_mark: 0.835,
    current: 0.835,
  },
  {
    key: "FC Inter Turku vs. Vaasan Palloseura: Both Teams to Score in First Half|Yes",
    label: "Yes",
    pregame_mark: 0.165,
    current: 0.165,
  },
];

/**
 * SPECIMEN 2 — the badge. A half-percent-grid pair that moves by half a point:
 * both printed levels are 91%, so the only honest badge is no move at all.
 */
const HALF_POINT: PropMark[] = [
  { key: "Aaron Judge: Total Bases O/U 1.5|Over", label: "Over", pregame_mark: 0.905, current: 0.91 },
  { key: "Aaron Judge: Total Bases O/U 1.5|Under", label: "Under", pregame_mark: 0.095, current: 0.09 },
];

/** A pair that really did move, to prove the badge is corrected and not silenced. */
const REAL_MOVE: PropMark[] = [
  { key: "Kyle Tucker: Hits O/U 0.5|Over", label: "Over", pregame_mark: 0.6, current: 0.72 },
  { key: "Kyle Tucker: Hits O/U 0.5|Under", label: "Under", pregame_mark: 0.4, current: 0.28 },
];

describe("#5296 THE DIVERGENCE's levels and its badge stop contradicting each other", () => {
  // ── THE SHIP ──────────────────────────────────────────────────────────────

  test("SHIP: the live pair prints 84% / 16%, not 84% / 17%", () => {
    const html = divergence(TURKU);
    expect(html).toContain("84%");
    // "17%" is what the independent rounding produced. The derived sibling is 16.
    expect(html).not.toContain("17%");
    expect(html).toContain("16%");
  });

  test("SHIP: the OPENING pair stops summing to 101 as well", () => {
    // Measured from the base render: the half-point specimen opened at
    // `91% → ` / `10% → `, which is 101 before the live number is even read.
    // `renderedDuelMovePoints` rounds both ends through `renderedDuelPercents`
    // precisely so the "opened at" pair cannot be the one that is wrong.
    const html = divergence(HALF_POINT);
    expect(html).not.toContain("10% →");
    expect(html).toContain("9% →");
  });

  test("SHIP: a half-point move prints no move, because both levels print 91%", () => {
    const html = divergence(HALF_POINT);
    expect(html).toContain("91%");
    // `Math.round((0.91 - 0.905) * 100)` is 1. The difference of the printed
    // levels is 0, and the printed levels are what the reader can check.
    expect(html).not.toContain("↑ 1");
  });

  test("SHIP: the two legs of one pair stop disagreeing about their own move", () => {
    // Before: `Math.round(0.5) = 1` on the over leg and `Math.round(-0.5) = -0` on
    // the under leg — one badge said `↑ 1` and the other `±0` about ONE move.
    const html = divergence(HALF_POINT);
    expect(html).not.toContain("↑ 1");
    expect(html).not.toContain("↓ 1");
  });

  test("SHIP: a row is filed under moved/didn't-move by the badge it PRINTS", () => {
    // The disclosure names its own count (UX-P036). With both legs printing `±0`
    // the whole family is unchanged, so the drawer must claim both rows. On the
    // base render this family has NO drawer at all — both rows sit in the moved
    // list — so the assertion is the drawer's existence, not the digit `2`, which
    // appears in the markup either way and would have been vacuous.
    expect(divergence(HALF_POINT)).toContain("2 unchanged");
  });

  // ── CONTROLS: states the code already got right, each named ────────────────

  test("CONTROL: a pair that really moved still shows the move", () => {
    // 0.60 → 0.72 is twelve whole points and survives every rounding. A fix that
    // silenced real movement would pass every assertion above and be useless.
    const html = divergence(REAL_MOVE);
    expect(html).toContain("↑ 12");
    expect(html).toContain("↓ 12");
  });

  test("CONTROL: a pair that really moved prints levels that still sum to 100", () => {
    const html = divergence(REAL_MOVE);
    expect(html).toContain("72%");
    expect(html).toContain("28%");
  });

  test("CONTROL: a NON-complement two-leg family keeps today's arithmetic exactly", () => {
    // 0.30 + 0.30 is not a complement. Two independent questions that happen to
    // share a family name must render exactly as they did — this ship is scoped to
    // pairs that sum to one, and widening it here would be #2951 reaching a
    // population nobody measured.
    const pair: PropMark[] = [
      { key: "Team Totals: Runs O/U 4.5|Home Over", label: "Home Over", pregame_mark: 0.3, current: 0.305 },
      { key: "Team Totals: Runs O/U 4.5|Away Over", label: "Away Over", pregame_mark: 0.3, current: 0.305 },
    ];
    const html = divergence(pair);
    // `pct(0.305)` is 31 and `Math.round((0.305 - 0.3) * 100)` is 1, both unchanged.
    expect(html).toContain("31%");
    expect(html).toContain("↑ 1");
  });

  test("CONTROL: a three-leg family is untouched — the rule is a PAIR rule", () => {
    const three: PropMark[] = [
      { key: "Match Result|Home", label: "Home", pregame_mark: 0.455, current: 0.455 },
      { key: "Match Result|Draw", label: "Draw", pregame_mark: 0.265, current: 0.265 },
      { key: "Match Result|Away", label: "Away", pregame_mark: 0.28, current: 0.28 },
    ];
    // 0.455 rounds to 46 on its own and must keep doing so.
    expect(divergence(three)).toContain("46%");
  });

  test("CONTROL: the unnamed group (numeric keys) is untouched", () => {
    // The golf/combat concept page keys marks by market id, so two rows standing
    // together are two different questions. Pairing them would invent a complement.
    const unnamed: PropMark[] = [
      { key: 8801, label: "Rory McIlroy", pregame_mark: 0.835, current: 0.835 },
      { key: 8802, label: "Scottie Scheffler", pregame_mark: 0.165, current: 0.165 },
    ];
    const html = divergence(unnamed);
    expect(html).toContain("84%");
    expect(html).toContain("17%");
  });

  test("CONTROL: a leg with no current price is not paired and stays honest", () => {
    // One endpoint missing means the family cannot be decided at both ends. The
    // sibling must not be quietly re-rounded against a partner that isn't there.
    const halfPriced: PropMark[] = [
      { key: "Shota Imanaga: Strikeouts O/U 5.5|Over", label: "Over", pregame_mark: 0.835, current: null },
      { key: "Shota Imanaga: Strikeouts O/U 5.5|Under", label: "Under", pregame_mark: 0.165, current: 0.165 },
    ];
    const html = divergence(halfPriced);
    expect(html).toContain("17%");
  });

  test("CONTROL: THE SCRIPT is unaffected — #5240's decision still stands alone", () => {
    // The two states must not have started sharing a code path. THE SCRIPT prints
    // one number and no badge, so it keeps `scriptPairPercents`.
    const html = script(TURKU);
    expect(html).toContain("84%");
    expect(html).not.toContain("17%");
  });

  test("CONTROL: the section still renders at all", () => {
    // A rule that threw on a shape it had not seen would take the whole props body
    // down with it, and every `not.toContain` above would pass on an empty string.
    expect(divergence(TURKU).length).toBeGreaterThan(200);
    expect(divergence(TURKU)).toContain("Both Teams to Score");
  });
});
