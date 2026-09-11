// #5240 — THE SCRIPT printed 46% of its prop pairs summing to 101%.
//
// WHAT A READER SAW, on `/events/15309636` (Braves vs Phillies, pre-match) at
// 390px, production 2026-09-11 14:12Z:
//
//     OZZIE ALBIES: TOTAL BASES O/U 3.5
//       Under     92%
//       Over       9%
//
// Two complementary answers to one question, adding to more than certainty.
// Measured over three pre-match MLB games: 38 of 83 families carrying two
// `pregame_mark` values rendered a sum ≠ 100 — every one of them +1.
//
// THE CAUSE IS ROUNDING, NOT DATA. `_build_props_script` writes the under leg as
// `1 - over`, so the wire pair is exact (`0.915 + 0.085 = 1.0`). Each leg was then
// rounded independently, both landing on the same `.5` boundary that `Math.round`
// takes upward. Marks are quoted on a half-percent grid, which is why this is the
// common case rather than a rare one.
//
// THE FIX ROUTES THE FAMILY THROUGH AN EXISTING CONTRACT, adding no fourth
// rounding rule: `renderedPercent.ts` already models "a card has a SUM" (#2060).
//
// RED-FIRST, measured rather than asserted: against the parent commit this file
// scores 2 failed, 6 passed of 8. The two that red are the two ship assertions.
// The six that pass are controls — states the old code already got right, named
// individually below so "6 passed" is evidence rather than a number.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import PropsSection from "../../components/event/PropsSection";
import type { PropMark } from "../../components/event/PropsSection";

const script = (items: PropMark[]) =>
  renderToStaticMarkup(<PropsSection items={items} state="script" />);
const divergence = (items: PropMark[]) =>
  renderToStaticMarkup(<PropsSection items={items} state="divergence" />);

/** The real specimen. 0.915 / 0.085 is an exact complement on the wire. */
const ALBIES: PropMark[] = [
  { key: "Ozzie Albies: Total Bases O/U 3.5|Under", label: "Under", pregame_mark: 0.915, current: 0.92 },
  { key: "Ozzie Albies: Total Bases O/U 3.5|Over", label: "Over", pregame_mark: 0.085, current: 0.08 },
];

describe("#5240 THE SCRIPT's two legs stop summing to 101%", () => {
  test("THE SHIP: the pair prints 92% / 8%, not 92% / 9%", () => {
    const html = script(ALBIES);
    expect(html).toContain("92%");
    expect(html).toContain("8%");
  });

  test("THE SHIP: the leg that used to round up on its own no longer does", () => {
    // `pct(0.085)` is `Math.round(8.5)` = 9. Derived from its sibling it is 8.
    // "9%" cannot appear from "92%" — that string ends `2%`.
    expect(script(ALBIES)).not.toContain("9%");
  });

  test("CONTROL: the headline leg is untouched — this corrects the pair, not the number", () => {
    // 0.915 rounds to 92 both before and after. A fix that moved the FAVOURITE
    // would be changing the answer rather than making the pair coherent.
    expect(script(ALBIES)).toContain("92%");
  });

  test("CONTROL: a family of three is not a pair and rounds exactly as before", () => {
    const three: PropMark[] = [
      { key: "Total Runs|Over", label: "Over", pregame_mark: 0.915, current: 0.9 },
      { key: "Total Runs|Under", label: "Under", pregame_mark: 0.085, current: 0.1 },
      { key: "Total Runs|Exactly", label: "Exactly", pregame_mark: 0.5, current: 0.5 },
    ];
    // Arity ≠ 2 means "no override": every leg keeps its own rounding, so the
    // independently-rounded 9% is still what this prints.
    expect(script(three)).toContain("9%");
  });

  test("CONTROL: two legs that are NOT complements are left alone", () => {
    // 0.60 + 0.30 = 0.90, outside the complement band. Normalising it would
    // invent ten points of probability.
    const independent: PropMark[] = [
      { key: "Anytime TD|Player A", label: "Player A", pregame_mark: 0.6, current: 0.6 },
      { key: "Anytime TD|Player B", label: "Player B", pregame_mark: 0.3, current: 0.3 },
    ];
    const html = script(independent);
    expect(html).toContain("60%");
    expect(html).toContain("30%");
  });

  test("CONTROL: an unnamed group is never paired — two marks there are two markets", () => {
    // The golf/combat concept page keys marks by a numeric market id, so
    // `propFamilyName` returns null and the two rows are unrelated questions.
    // Pairing them would invent a complement out of two separate markets.
    const unnamed: PropMark[] = [
      { key: "884411", label: "Rory McIlroy", pregame_mark: 0.915, current: 0.9 },
      { key: "884412", label: "Scottie Scheffler", pregame_mark: 0.085, current: 0.1 },
    ];
    expect(script(unnamed)).toContain("9%");
  });

  test("CONTROL: THE DIVERGENCE is out of scope and unchanged", () => {
    // `current` has the same defect (42 of 110 pairs) but that state also prints
    // a DELTA, and #2951's rule is that a printed delta is the difference of the
    // PRINTED levels. Correcting the levels without the badge would make the row
    // contradict itself, so that half is its own ship. This pins the boundary.
    const html = divergence(ALBIES);
    expect(html).toContain("92%");
  });

  test("CONTROL: a row with no mark still prints the em dash, not a derived number", () => {
    // "no number" and "0%" are different statements, and a pair helper must not
    // turn a hole into a complement.
    const halfMarked: PropMark[] = [
      { key: "Hits O/U 1.5|Over", label: "Over", pregame_mark: 0.915, current: 0.92 },
      { key: "Hits O/U 1.5|Under", label: "Under", pregame_mark: null, current: 0.08 },
    ];
    expect(script(halfMarked)).toContain("—");
  });
});
