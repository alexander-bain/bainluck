// #5408 — THE DIVERGENCE's MARKLESS pairs were invisible to #5240 and #5296, and
// summed to 101 (and to 99) in plain sight on a live page.
//
// WHAT A READER SAW. `/events/15309635` (Angels @ Nationals, LIVE, 2026-09-11
// 22:50Z, 390px), two families four rows apart in one screen:
//
//     CJ ABRAMS: HITS + RUNS + RBIS O/U 3.5      Under 90% / Over  9%   ← 99
//     CADE CAVALLI: STRIKEOUTS O/U 6.5           Over  57% / Under 44%  ← 101
//
// Two complementary answers to one question, one adding to less than certainty
// and one to more. 7 of that page's 22 named families are markless.
//
// WHY THE TWO SHIPPED FIXES DID NOT REACH THEM. Both `scriptPairPercents` (#5240)
// and `divergencePairPercents` (#5296) open by filtering for `pregame_mark != null`,
// because both were written about the three numbers a BADGE relates. A pair with
// no baseline on either leg never entered either filter and each leg rounded on
// its own. #5216 then removed the `script pending` chip that used to sit between
// the label and the price, which is why the two bare percentages now sit side by
// side where a reader notices they disagree. The numbers did not change.
//
// NO NEW ROUNDING RULE. Same `renderedOutcomeRowPercents` the marked cohort uses,
// same `isComplementPair` gate. A markless pair needs only TWO numbers, so the
// #2951 consumer that forced #5240 to stop short (a printed delta must be the
// difference of the printed LEVELS) has nothing to consume here.
//
// THE ROUNDING HALF ONLY. The issue also names a DATA half: `0.9 / 0.09` are not
// complements on the wire. That sum is 0.99 — inside the contract's measured
// [0.99, 1.01] band, whose own census counts and fixes 99s (`renderedPercent.ts`:
// "`0.5/0.49` prints 99 today") — so it normalizes here like every other surface
// in the product. That is deliberate and it is NOT a claim the wire is right; see
// the CJ Abrams test below and the issue filed for the upstream half.
//
// RED-FIRST, measured rather than asserted, and the measurement corrected the
// file. Against the parent commit (`7fdcc217`) this scores **2 failed, 11 passed
// of 13**. Only two assertions can red, because only two numbers on the page
// change: the two SHIP tests below. Three assertions first written as SHIP turned
// out to pass against the parent, and each was re-labelled for what it actually
// does rather than left wearing a claim it could not support:
//
//   - the two GUARD tests are regression guards on the encoding this ship
//     introduces (`move: null`). Proven non-vacuous by mutation: setting
//     `move: 0` instead kills both, and nothing else in the suite notices.
//   - a third — "never prints `null%`" — was DELETED as vacuous. The mark slot is
//     guarded on `item.pregame_mark`, so a markless row cannot reach the template
//     at all; the assertion passed against every mutant of the guard it claimed
//     to test. The invariant it was reaching for is stated on `DivergencePair`.
//
// MUTATION-TESTED (4 mutants, 3 killed, 1 survivor acted on):
//   `move: null` → `move: 0`            KILLED (both GUARD tests)
//   `every` → `some` in the branch gate  KILLED (the MIXED control)
//   mark-slot guard → `paired ?`         SURVIVED → the test was deleted, above
//   drop the `isComplementPair` gate     SURVIVED, and so did the COMPOUND mutant
//       that also removes the clause inside `renderedDuelPercents` which subsumes
//       it — because `renderedCardPercents` self-gates too. That is a dead line,
//       not an equivalent one, so the gate was removed from the ship rather than
//       defended here. See the branch comment.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import PropsSection from "../../components/event/PropsSection";
import type { PropMark } from "../../components/event/PropsSection";

const divergence = (items: PropMark[]) =>
  renderToStaticMarkup(<PropsSection items={items} state="divergence" />);
const script = (items: PropMark[]) =>
  renderToStaticMarkup(<PropsSection items={items} state="script" />);

/**
 * SPECIMEN 1 — the ROUNDING half, read off the payload. `0.565 + 0.435` is an
 * exact complement and both legs sit on the `.5` boundary `Math.round` takes
 * upward, so the family printed 57 / 44 = 101.
 */
const CAVALLI: PropMark[] = [
  {
    key: "Cade Cavalli: Strikeouts O/U 6.5|Over",
    label: "Over",
    pregame_mark: null,
    current: 0.565,
  },
  {
    key: "Cade Cavalli: Strikeouts O/U 6.5|Under",
    label: "Under",
    pregame_mark: null,
    current: 0.435,
  },
];

/**
 * SPECIMEN 2 — the other direction, and the one that is NOT purely rounding.
 * `0.9 + 0.09` is 0.99: the legs are not complements on the wire. It is inside
 * the contract's band, so the pair is normalized (`0.9 / 0.99` → 91, sibling
 * derived as 9) rather than printed as 90 / 9 = 99.
 */
const ABRAMS: PropMark[] = [
  {
    key: "CJ Abrams: Hits + Runs + RBIs O/U 3.5|Under",
    label: "Under",
    pregame_mark: null,
    current: 0.9,
  },
  {
    key: "CJ Abrams: Hits + Runs + RBIs O/U 3.5|Over",
    label: "Over",
    pregame_mark: null,
    current: 0.09,
  },
];

describe("#5408 a markless pair stops printing 101 (and 99)", () => {
  // ── THE SHIP ──────────────────────────────────────────────────────────────

  test("SHIP: the live markless pair prints 57% / 43%, not 57% / 44%", () => {
    const html = divergence(CAVALLI);
    expect(html).toContain("57%");
    // 44 is what the independent rounding produced. The derived sibling is 43.
    expect(html).not.toContain("44%");
    expect(html).toContain("43%");
  });

  test("SHIP: the pair four rows down stops printing 99 as well", () => {
    // The defect is not one-directional, which is why the fix is the contract's
    // pair helper and not a "both legs rounded up" special case.
    const html = divergence(ABRAMS);
    expect(html).toContain("91%");
    expect(html).toContain("9%");
    expect(html).not.toContain("90%");
  });

  // ── GUARDS on this ship's encoding (green on the parent; killed by mutation) ─

  test("GUARD: a markless row still claims NO move — no badge, no arrow", () => {
    // The whole cohort's defining property. A pair helper that handed these rows
    // a `move` would put a badge on a row with nothing to move from, which is the
    // contradiction #5296 exists to prevent arriving from the other side.
    const html = divergence(CAVALLI);
    expect(html).not.toContain("±0");
    expect(html).not.toContain("↑");
    expect(html).not.toContain("↓");
    expect(html).not.toContain("→");
  });

  test("GUARD: a markless pair is NOT filed under 'didn't move'", () => {
    // `didNotMove` reads `pair.move === 0`. Encode a markless pair's absent move
    // as 0 instead of null and both rows — carrying the live price a reader came
    // for on an open window (#5216) — vanish into a drawer labelled "unchanged".
    const html = divergence(CAVALLI);
    expect(html).not.toContain("unchanged");
    expect(html).toContain("57%");
  });

  // ── CONTROLS: states the code already got right, each named ────────────────

  test("CONTROL: a NON-complement markless family keeps today's arithmetic", () => {
    // 0.305 + 0.305 is two independent questions sharing a family name, and they
    // must render exactly as they did — a pair rule that reached them would
    // invent a complement out of rows that are not summing wrong.
    //
    // ENFORCED BY THE CONTRACT, NOT BY THIS BRANCH, and the distinction is worth
    // stating because the branch has no gate of its own: `renderedOutcomeRowPercents`
    // returns the two independent roundings for any pair outside the complement
    // band. This test protects the PROPERTY wherever it is enforced, which is why
    // it stays after the redundant gate was removed.
    const pair: PropMark[] = [
      { key: "Team Totals: Runs O/U 4.5|Home Over", label: "Home Over", pregame_mark: null, current: 0.305 },
      { key: "Team Totals: Runs O/U 4.5|Away Over", label: "Away Over", pregame_mark: null, current: 0.305 },
    ];
    // `pct(0.305)` is 31 on both legs, unchanged.
    expect(divergence(pair)).toContain("31%");
  });

  test("CONTROL: a MIXED family — one leg marked, one not — is untouched", () => {
    // The `every` in the branch guard, and the reason it is not `some`. Pairing
    // these two currents would re-round the marked leg's printed level while its
    // badge kept deriving from the raw one: #2951's self-contradiction by the
    // back door. `0.565` must still print 57 and `0.435` must still print 44.
    const mixed: PropMark[] = [
      { key: "Mixed: Strikeouts O/U 6.5|Over", label: "Over", pregame_mark: 0.5, current: 0.565 },
      { key: "Mixed: Strikeouts O/U 6.5|Under", label: "Under", pregame_mark: null, current: 0.435 },
    ];
    const html = divergence(mixed);
    expect(html).toContain("57%");
    expect(html).toContain("44%");
  });

  test("CONTROL: the MARKED cohort still gets all three of #5296's numbers", () => {
    // The marked branch must not have been altered by the insert above it. This
    // is #5296's own live specimen: 0.835/0.165 prints 84/16, not 84/17.
    const turku: PropMark[] = [
      { key: "Turku vs. VPS: Both Teams to Score in First Half|No", label: "No", pregame_mark: 0.835, current: 0.835 },
      { key: "Turku vs. VPS: Both Teams to Score in First Half|Yes", label: "Yes", pregame_mark: 0.165, current: 0.165 },
    ];
    const html = divergence(turku);
    expect(html).toContain("84%");
    expect(html).not.toContain("17%");
    expect(html).toContain("16%");
  });

  test("CONTROL: a marked pair that really moved still shows its badge", () => {
    // A widening that silenced real movement would pass the markless assertions
    // above and be worse than the defect.
    const realMove: PropMark[] = [
      { key: "Kyle Tucker: Hits O/U 0.5|Over", label: "Over", pregame_mark: 0.6, current: 0.72 },
      { key: "Kyle Tucker: Hits O/U 0.5|Under", label: "Under", pregame_mark: 0.4, current: 0.28 },
    ];
    const html = divergence(realMove);
    expect(html).toContain("↑ 12");
    expect(html).toContain("↓ 12");
  });

  test("CONTROL: a markless leg with no current price is not paired", () => {
    // One priced leg is not a pair. The survivor must not be re-rounded against a
    // partner that isn't there — `0.165` keeps printing 17.
    const halfPriced: PropMark[] = [
      { key: "Shota Imanaga: Strikeouts O/U 5.5|Over", label: "Over", pregame_mark: null, current: null },
      { key: "Shota Imanaga: Strikeouts O/U 5.5|Under", label: "Under", pregame_mark: null, current: 0.165 },
    ];
    expect(divergence(halfPriced)).toContain("17%");
  });

  test("CONTROL: a three-leg markless family is untouched — this is a PAIR rule", () => {
    const three: PropMark[] = [
      { key: "Match Result|Home", label: "Home", pregame_mark: null, current: 0.455 },
      { key: "Match Result|Draw", label: "Draw", pregame_mark: null, current: 0.265 },
      { key: "Match Result|Away", label: "Away", pregame_mark: null, current: 0.28 },
    ];
    // 0.455 rounds to 46 on its own and must keep doing so.
    expect(divergence(three)).toContain("46%");
  });

  test("CONTROL: the unnamed group (numeric keys) is untouched", () => {
    // The golf/combat concept page keys marks by market id, so two rows standing
    // together are two different questions. #5240's reason, unchanged.
    const unnamed: PropMark[] = [
      { key: 8801, label: "Rory McIlroy", pregame_mark: null, current: 0.565 },
      { key: 8802, label: "Scottie Scheffler", pregame_mark: null, current: 0.435 },
    ];
    const html = divergence(unnamed);
    expect(html).toContain("57%");
    expect(html).toContain("44%");
  });

  test("CONTROL: THE SCRIPT is unaffected — a markless row still prints an em dash", () => {
    // The two states must not have started sharing a code path. In THE SCRIPT a
    // markless row has no number to print at all (D102 / #4530).
    const html = script(CAVALLI);
    expect(html).not.toContain("57%");
    expect(html).toContain("—");
  });

  test("CONTROL: the section still renders at all", () => {
    // A rule that threw on a shape it had not seen would take the whole props
    // body down, and every `not.toContain` above would pass on an empty string.
    expect(divergence(CAVALLI).length).toBeGreaterThan(200);
    expect(divergence(CAVALLI)).toContain("Cade Cavalli");
  });
});
