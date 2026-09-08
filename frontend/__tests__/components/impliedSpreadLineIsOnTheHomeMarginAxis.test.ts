/**
 * #3948 repair `3948-KALSHI-IMPLIED-LINE-MATCHES-HOME-MARGIN-AXIS` (CERT-2264).
 *
 * ## What was wrong
 *
 * `ScoreDifferentialChart` plots the `Kalshi Implied` / `Polymarket Implied`
 * dashed lines. It was assigning `pt[key] = data.spread` — but `spread` is
 * **betting-line sign** (negative = HOME favoured) while this chart's Y axis is
 * **`home - away`** (positive = HOME leading). Every other series on the chart
 * is built as `projected_home_score - awayScore`, so the implied line was the
 * only one drawn on the opposite convention: mirrored about zero.
 *
 * On the real production ladder for event 14637256 — Giants home, Dallas away,
 * Dallas favoured by 3 — `spread` is `+3.0`. Drawn raw, the chart claimed the
 * GIANTS were +3 while the hero on the same page favoured Dallas.
 *
 * ## Two arms, because this has two failure modes
 *
 * The **library arm** proves the rule. The **source arm** proves the chart
 * actually spends it — a pure function nothing renders is the classic way this
 * class of fix passes its own test and changes nothing on screen.
 *
 * A rendered assertion is deliberately NOT used: `ScoreDifferentialChart` is
 * Recharts and server-renders to an empty box, so a `not.toContain` against its
 * markup would pass on a component that drew nothing at all
 * (`chartSourceLegendReadsPayload.test.ts` established this constraint and the
 * discipline that goes with it). The source arm therefore **raises** if it
 * cannot find the block it is checking, because a scan that silently matches
 * nothing is how a renamed variable turns this file green by making it vacuous.
 */

import { readFileSync } from "fs";
import { join } from "path";

import { impliedSpreadHomeMargin } from "@/lib/impliedSpreadAxis";

describe("library arm — the implied line reads the chart's own axis", () => {
  it("puts Dallas-favoured below zero on a Giants-home ladder", () => {
    // Verbatim from the production specimen: home Giants, Dallas favoured by 3.
    const arm = { spread: 3.0, home_margin: -3.0 };
    expect(impliedSpreadHomeMargin(arm)).toBeCloseTo(-3.0, 5);
    expect(impliedSpreadHomeMargin(arm)).toBeLessThan(0);
  });

  it("mirrors above zero when the same ladder's sides are swapped", () => {
    const flipped = { spread: -3.0, home_margin: 3.0 };
    expect(impliedSpreadHomeMargin(flipped)).toBeCloseTo(3.0, 5);
    expect(impliedSpreadHomeMargin(flipped)).toBeGreaterThan(0);
  });

  it("never returns the betting-line sign itself", () => {
    // The whole defect in one assertion.
    const arm = { spread: 3.0, home_margin: -3.0 };
    expect(impliedSpreadHomeMargin(arm)).not.toBeCloseTo(arm.spread, 5);
  });

  it("falls back to negating spread for a payload cached before the repair", () => {
    expect(impliedSpreadHomeMargin({ spread: 3.0 })).toBeCloseTo(-3.0, 5);
    expect(impliedSpreadHomeMargin({ spread: -7.5 })).toBeCloseTo(7.5, 5);
  });

  it("keeps a pick'em at zero rather than drifting off it", () => {
    expect(impliedSpreadHomeMargin({ spread: 0, home_margin: -0 })).toBeCloseTo(0, 5);
  });
});

describe("source arm — the chart spends the rule instead of re-deriving it", () => {
  const source = readFileSync(
    join(process.cwd(), "components", "ScoreDifferentialChart.tsx"),
    "utf8",
  );

  it("assigns the implied-spread series through the axis helper", () => {
    const assignment = source.match(/pt\[key\]\s*=\s*([^;]+);/);
    if (!assignment) {
      throw new Error(
        "Could not find the `pt[key] = ...` implied-spread assignment in " +
          "ScoreDifferentialChart.tsx. If it was renamed, update this guard — " +
          "do not let it pass by matching nothing.",
      );
    }
    expect(assignment[1]).toContain("impliedSpreadHomeMargin");
  });

  it("does not plot the raw betting-line spread anywhere in the series builder", () => {
    const block = source.match(
      /if \(pmSpreadData\?\.implied_spreads\) \{[\s\S]*?\n {4}\}/,
    );
    if (!block) {
      throw new Error(
        "Could not find the implied_spreads series-building block in " +
          "ScoreDifferentialChart.tsx. This guard must never pass vacuously.",
      );
    }
    expect(block[0]).not.toMatch(/=\s*data\.spread\b/);
  });

  it("imports the helper it claims to use", () => {
    expect(source).toMatch(
      /import \{ impliedSpreadHomeMargin \} from "@\/lib\/impliedSpreadAxis";/,
    );
  });
});
