/**
 * UX-P191 — THE CROSS-SOURCE CARD STOPS PRINTING A DIGIT THAT ISN'T THERE.
 *
 * ═══ WHAT THIS IS ═══
 *
 * `/politics` has one home for "what percentage does this probability print":
 * `formatProbabilityPercent` (UX-P046, `lib/probabilityDisplay.ts`). Every
 * market number on the page goes through it — `MarketRow`, the leader rows, the
 * side markets — except the cross-source spotlight, which printed
 * `.toFixed(1)` inline.
 *
 * Two things follow from bypassing the single home, and both are on the live
 * page:
 *
 *   1. A FORCED DECIMAL. Measured on the deployed payload 2026-08-30, 6 of the
 *      8 served matches carry at least one whole value, and the card rendered
 *      them `86.0%`, `95.0%`, `88.0%`, `16.0%`, `43.0%`, `49.0%`, `36.0%`.
 *      Three of the FOUR rows the section renders show one. `86.0%` is not
 *      more precise than `86%`; it is the same number with a digit of noise
 *      on it.
 *
 *   2. NO BOUNDARY RULE. `formatProbabilityPercent` exists so that "rounding
 *      may never move a probability across a boundary it is not on" — a live
 *      price must never print `0%`, which a reader reads as impossible. This
 *      card had no such guard, on the one surface that SELECTS FOR EXTREMES:
 *      the list is sorted by descending delta and sliced to four, so a side
 *      pinned near 0 or 100 is exactly what reaches it.
 *
 * ═══ WHAT IS DELIBERATELY NOT CHANGED ═══
 *
 * The presidential bar race keeps its one decimal, and that is a measurement,
 * not a shrug. Live the same day its 14 candidates sit between 2.7% and 10.5%;
 * whole numbers put Shapiro 4.2, Kelly 4.0, Cruz 3.9, Vance 3.8, DeSantis 3.8,
 * Emanuel 3.8 and Beshear 3.7 all on `4%` — seven consecutive rows showing one
 * number in a table whose first column is the rank. A decimal earns its place
 * there. On a two-value comparison card sorted by a gap of 46 to 81 points, it
 * does not.
 *
 * ═══ THE ARITHMETIC TRAP ═══
 *
 * Rounding the served `delta` on its own breaks the card: `4.5 / 86.0` prints
 * `5% / 86%` — a gap of 81 — while its served delta of 81.5 rounds to 82. Two
 * of the eight live rows land in that gap. So every derived number on the card
 * is computed FROM THE PRINTED PAIR, and this file asserts that property on
 * every banked row rather than on one example.
 *
 *   npx jest --testPathPatterns=politicsCrossSourcePrecisionCapture
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";
import type { CrossSourceMatch } from "@/lib/api";

/* eslint-disable @typescript-eslint/no-var-requires */
const { CrossSourceCard, CrossSourceSpotlight } =
  require("@/components/crossSource/CrossSourceSpotlight");
const LegacyCrossSourceCard =
  require("../fixtures/uxp187CrossSourceCardLegacy").default;
/* eslint-enable @typescript-eslint/no-var-requires */

const FRONTEND = path.join(__dirname, "..", "..");
const REPO = path.join(FRONTEND, "..");

const banked = JSON.parse(
  fs.readFileSync(
    path.join(
      REPO,
      "backend",
      "tests",
      "fixtures",
      "uxp191_printed_percent.json",
    ),
    "utf8",
  ),
);

/** The verbatim `cross_source` array from GET /api/politics, banked pre-fix. */
const SERVED: CrossSourceMatch[] = banked.politics_cross_source_served;

/** What the section actually renders: `matches.slice(0, 4)`. */
const RENDERED = SERVED.slice(0, 4);

function markup(
  Component: React.ComponentType<{ market: CrossSourceMatch }>,
  market: CrossSourceMatch,
): string {
  return renderToStaticMarkup(React.createElement(Component, { market }));
}

function visibleText(m: string): string {
  return m
    .replace(/<[^>]*>/g, " ")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    // `<1%` and `>99%` reach the markup as `&lt;1%` / `&gt;99%`. Without these
    // two the boundary assertions below read a card that IS printing the right
    // thing as one that is not.
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/\s+/g, " ")
    .trim();
}

/** Every `NN.N%`-shaped token a reader can see. */
function decimalPercents(text: string): string[] {
  return text.match(/\d+\.\d+\s*(?:%|pp|pt)/g) || [];
}

/** Every whole `NN%`-shaped token a reader can see. */
function wholePercents(text: string): number[] {
  return (text.match(/(?<![\d.])\d+%/g) || []).map((t) => parseInt(t, 10));
}

/* ═══ 1 · the banked payload really is the defect ══════════════════════════ */

describe("UX-P191 · the served payload carries the fake digits", () => {
  test("the fixture is the eight rows production served", () => {
    expect(SERVED).toHaveLength(8);
    for (const row of SERVED) {
      expect(typeof row.kalshi).toBe("number");
      expect(typeof row.poly).toBe("number");
      // The served delta really is the gap between the two served numbers, so
      // the "derive from the printed pair" rule below is a display decision
      // and not a disagreement with the server.
      expect(row.delta).toBeCloseTo(Math.abs(row.kalshi - row.poly), 1);
    }
  });

  test("6 of the 8 carry a value with nothing after the decimal point", () => {
    const whole = SERVED.filter((r) => r.kalshi % 1 === 0 || r.poly % 1 === 0);
    expect(whole).toHaveLength(6);
    // And it reaches the reader: the section renders four, three of which
    // showed a `.0`.
    expect(
      RENDERED.filter((r) => r.kalshi % 1 === 0 || r.poly % 1 === 0),
    ).toHaveLength(3);
  });
});

/* ═══ 2 · prove the instrument ═════════════════════════════════════════════ */

describe("UX-P191 · the legacy card is wrong in exactly this way", () => {
  test("the shipped-before card printed `86.0%` for a value of 86", () => {
    const khamenei = SERVED[0];
    expect(khamenei.poly).toBe(86);

    const text = visibleText(markup(LegacyCrossSourceCard, khamenei));
    expect(text).toContain("86.0%");
    expect(decimalPercents(text).length).toBeGreaterThan(0);
  });

  test("...and every one of the four rendered rows showed a decimal", () => {
    for (const row of RENDERED) {
      const text = visibleText(markup(LegacyCrossSourceCard, row));
      expect(decimalPercents(text).length).toBeGreaterThan(0);
    }
  });
});

/* ═══ 3 · the ship, rendered ═══════════════════════════════════════════════ */

describe("UX-P191 · every number on the card is a whole percent", () => {
  test("no rendered row prints a decimal anywhere", () => {
    for (const row of RENDERED) {
      const text = visibleText(markup(CrossSourceCard, row));
      expect(decimalPercents(text)).toEqual([]);
    }
  });

  test("...and the card is not simply empty of numbers", () => {
    // Vacuity companion. A card that rendered no percentages at all would
    // satisfy the assertion above perfectly.
    for (const row of RENDERED) {
      const text = visibleText(markup(CrossSourceCard, row));
      expect(wholePercents(text).length).toBeGreaterThanOrEqual(3);
    }
  });

  test("the Khamenei row: `4.5% / 86.0%` becomes `5% / 86%`", () => {
    const text = visibleText(markup(CrossSourceCard, SERVED[0]));
    expect(text).toContain("5%");
    expect(text).toContain("86%");
    expect(text).not.toContain("4.5%");
    expect(text).not.toContain("86.0%");
  });
});

/* ═══ 4 · the reader's arithmetic holds ════════════════════════════════════ */

describe("UX-P191 · the printed numbers agree with each other", () => {
  test("the printed gap is the difference of the two printed numbers", () => {
    for (const row of RENDERED) {
      const text = visibleText(markup(CrossSourceCard, row));

      const k = Math.round(row.kalshi);
      const p = Math.round(row.poly);
      const gap = Math.abs(k - p);

      // Both the "Disagree by Npp" line and the "⚠ Npt spread" badge, which
      // are the same quantity in two places.
      if (row.delta > 2) expect(text).toContain(`${gap}pp`);
      if (row.delta > 5) expect(text).toContain(`${gap}pt spread`);
    }
  });

  test("rounding the SERVED delta instead would contradict the card", () => {
    // The trap, asserted rather than described: on these rows the naive fix is
    // observably wrong, which is why the derivation exists.
    const contradicted = RENDERED.filter(
      (r) =>
        Math.round(r.delta) !==
        Math.abs(Math.round(r.kalshi) - Math.round(r.poly)),
    );
    expect(contradicted.length).toBeGreaterThan(0);

    for (const row of contradicted) {
      const text = visibleText(markup(CrossSourceCard, row));
      expect(text).not.toContain(`${Math.round(row.delta)}pp`);
    }
  });

  test("Merged sits between the two printed numbers", () => {
    for (const row of RENDERED) {
      const text = visibleText(markup(CrossSourceCard, row));
      const merged = /Merged:\s*(\d+)%/.exec(text);
      expect(merged).not.toBeNull();

      const value = parseInt(merged![1], 10);
      const k = Math.round(row.kalshi);
      const p = Math.round(row.poly);

      expect(value).toBeGreaterThanOrEqual(Math.min(k, p));
      expect(value).toBeLessThanOrEqual(Math.max(k, p));
      // ...and it is exactly the midpoint OF THE PRINTED PAIR. The range check
      // alone is too loose to see the difference: averaging the raw values
      // gives 45 for `4.5 / 86.0` where the printed pair gives 46, and both
      // sit comfortably inside [5, 86].
      expect(value).toBe(Math.round((k + p) / 2));
    }
  });

  test("a badge never announces a spread the card does not show", () => {
    // The gates still read the served float, so the printed gap has to stay
    // large enough for the badge's own words to be true. Proven over the
    // banked rows AND over the boundary values the gates sit on.
    const edges: CrossSourceMatch[] = [
      { ...SERVED[0], kalshi: 60.4, poly: 58.3, delta: 2.1 },
      { ...SERVED[0], kalshi: 60.5, poly: 58.4, delta: 2.1 },
      { ...SERVED[0], kalshi: 60.4, poly: 55.3, delta: 5.1 },
      { ...SERVED[0], kalshi: 60.5, poly: 55.4, delta: 5.1 },
    ];
    for (const row of [...RENDERED, ...edges]) {
      const text = visibleText(markup(CrossSourceCard, row));
      const gap = Math.abs(Math.round(row.kalshi) - Math.round(row.poly));
      if (row.delta > 2) expect(gap).toBeGreaterThanOrEqual(2);
      if (row.delta > 5) {
        expect(gap).toBeGreaterThanOrEqual(5);
        expect(text).toContain("pt spread");
      }
    }
  });
});

/* ═══ 5 · the boundary rule the single home brings with it ═════════════════ */

describe("UX-P191 · a live price never prints as impossible", () => {
  const base = SERVED[0];

  test("a side priced below half a point reads `<1%`, not `0.0%`", () => {
    const text = visibleText(
      markup(CrossSourceCard, { ...base, kalshi: 0.04, poly: 86, delta: 85.96 }),
    );
    expect(text).toContain("<1%");
    expect(text).not.toContain("0.0%");
    expect(text).not.toContain("0%");
  });

  test("a side priced above 99.5 reads `>99%`, not `100%`", () => {
    const text = visibleText(
      markup(CrossSourceCard, { ...base, kalshi: 99.7, poly: 3, delta: 96.7 }),
    );
    expect(text).toContain(">99%");
    expect(text).not.toContain("100%");
  });

  test("an exact 0 and an exact 100 are still printed plainly", () => {
    // The boundary rule guards values INSIDE the interval. A settled 0 or 100
    // is the boundary, and hedging it would be its own wrong answer.
    const text = visibleText(
      markup(CrossSourceCard, { ...base, kalshi: 100, poly: 0, delta: 100 }),
    );
    expect(text).toContain("100%");
    expect(text).toContain("0%");
    expect(text).not.toContain(">99%");
    expect(text).not.toContain("<1%");
  });
});

/* ═══ 6 · nothing else on the card moved ═══════════════════════════════════ */

describe("UX-P191 · the rest of the card is untouched", () => {
  test("the question and the outcome caption still render", () => {
    const row = { ...SERVED[1], outcome: "Ülle Madise" };
    const text = visibleText(markup(CrossSourceCard, row));
    expect(text).toContain(row.q);
    expect(text).toContain("Ülle Madise");
  });

  test("the section still renders four cards", () => {
    const m = renderToStaticMarkup(
      React.createElement(CrossSourceSpotlight, { matches: SERVED }),
    );
    expect(visibleText(m)).toContain("Cross-source spotlight");
    // "Merged:" appears once per card and nowhere else; "Polymarket" does not
    // (the source badge prints it too, so it counts 8 for 4 cards).
    expect((m.match(/Merged:/g) || []).length).toBe(4);
  });

  test("the presidential bar race still prints one decimal", () => {
    // The deliberate non-change, pinned so a later sweep cannot quietly
    // "finish the job" and collapse the ranking. See this file's header.
    const page = fs.readFileSync(
      path.join(FRONTEND, "app", "politics", "page.tsx"),
      "utf8",
    );
    expect(page).toContain("{prob.toFixed(1)}%");
  });

  test("the card no longer open-codes the rounding decision", () => {
    const source = fs.readFileSync(
      path.join(FRONTEND, "components", "crossSource", "CrossSourceSpotlight.tsx"),
      "utf8",
    );
    const code = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
    expect(code).not.toContain("toFixed(");
    expect(code).toContain("formatProbabilityPercent");
    expect(code).toContain("renderedPercent");
  });
});
