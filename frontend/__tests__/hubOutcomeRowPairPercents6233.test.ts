/**
 * #6233 — THE BROWSE HUBS PRINTED 101%.
 *
 * Seen on production 2026-09-14 22:15Z at 390px by live/245, routed to ux under
 * notice 41: `/hub/tennis` drew **four of five consecutive match cards** with two
 * numbers that do not add up — Peliwo 56/45, Sultanov 76/25, Kouzmine 72/29,
 * Kouame 89/12.
 *
 * Kalshi quotes a complement pair on a half-cent grid, so `p * 100` lands on `.5`
 * for both sides at once and half-up rounds BOTH up. #2831 built the rule
 * (`renderedCardPercents`) and `FuturesCard` renders through it; the hub's
 * file-local `OutcomeRow` called bare `formatProbability` per side and was never
 * converted — the live instance of the open census #3892.
 *
 * ## Measured across all three hubs, 2026-09-14
 *
 *   631 markets served, 506 with exactly two `top_outcomes`
 *    50 in-band pairs whose naive rounding does NOT total 100   <- the defect
 *    32 pairs OUTSIDE the [0.99, 1.01] band                     <- must not move
 *     0 cards showing two rows for a market with more outcomes  <- the cap trap
 *
 * ## What these guards are for
 *
 * The fix is three lines, and every one of them is a place a plausible wrong
 * version passes. So the suite pins all four directions: the pair is fixed, the
 * OFF-band pair is untouched (gotcha #23 — forcing 1.095 to 100 would invent ten
 * points of probability), a non-pair card is byte-identical, and the percents are
 * computed over the FULL outcome set so the display cap cannot invent a pair.
 */
import fs from "fs";
import path from "path";

import { renderedCardPercents } from "@/lib/renderedPercent";
import { formatProbability } from "@/lib/api";

/**
 * The card's rule, extracted exactly as the page applies it, so these cases
 * exercise the real helper rather than a paraphrase of it. The page's own
 * rendering is asserted separately below.
 */
function printedPercents(probabilities: Array<number | null>): string[] {
  const rendered = renderedCardPercents(probabilities);
  return probabilities.map((p, i) => formatProbability(p, { rendered: rendered[i] ?? null }));
}

const sum = (printed: string[]) =>
  printed.reduce((t, s) => t + (s.endsWith("%") ? parseInt(s.replace(/[^0-9]/g, ""), 10) : 0), 0);

describe("#6233 the four cards a reader saw on /hub/tennis", () => {
  /**
   * The real served pairs behind the four screenshotted cards. Each totals 101
   * under per-side rounding and 100 under the card rule.
   */
  it.each([
    ["Peliwo", 0.555, 0.445],
    ["Sultanov", 0.755, 0.245],
    ["Kouzmine", 0.715, 0.285],
    ["Kouame", 0.885, 0.115],
  ])("%s's card totals 100, not 101", (_name, a, b) => {
    expect(sum(printedPercents([a, b]))).toBe(100);
  });

  it("per-side rounding really did total 101 — the defect, stated", () => {
    // Without the card rule, which is what the hub did before this change.
    const naive = [0.555, 0.445].map((p) => formatProbability(p));
    expect(sum(naive)).toBe(101);
  });
});

describe("#6233 gotcha #23 — an off-band pair is NOT forced to 100", () => {
  /**
   * 32 of the 506 measured pairs sit outside [0.99, 1.01]. These are two
   * independent binaries, not two sides of one question, and normalizing
   * `Hayu Kinoshita vs Victoria Rodriguez: Set 2 Winner` (1.095) to 100 would
   * invent nine points of probability. `renderedCardPercents` self-gates; this
   * pins that the page inherits the gate rather than a rounder.
   */
  it.each([
    ["Set 2 Winner", 0.62, 0.475, 110],
    ["Maria vs Townsend", 0.52, 0.46, 98],
    ["Kalieva vs Day", 0.55, 0.43, 98],
  ])("%s keeps its own total", (_name, a, b, expected) => {
    expect(sum(printedPercents([a, b]))).toBe(expected);
  });

  it("an off-band pair renders each side exactly as it does today", () => {
    expect(printedPercents([0.62, 0.475])).toEqual([
      formatProbability(0.62),
      formatProbability(0.475),
    ]);
  });
});

describe("#6233 everything that is not a two-outcome card is byte-identical", () => {
  it.each([
    ["three outcomes", [0.5, 0.3, 0.2]],
    ["four outcomes", [0.4, 0.3, 0.2, 0.1]],
    ["one outcome", [0.62]],
    ["a null price beside a real one", [0.62, null]],
    ["both prices absent", [null, null]],
  ])("%s", (_name, probs) => {
    expect(printedPercents(probs as Array<number | null>)).toEqual(
      (probs as Array<number | null>).map((p) => formatProbability(p)),
    );
  });

  /**
   * The `<1%` / `>99%` markers are why this goes through
   * `formatProbability(prob, { rendered })` — the UX-P114 seam — and not through
   * a bare `${pct}%`. A bare template would have printed "0%" for a real price,
   * which is the claim UX-P046 exists to prevent.
   */
  it("a small-but-real price still refuses to print 0%", () => {
    const [leader, tail] = printedPercents([0.998, 0.002]);
    expect(leader).not.toBe("100%");
    expect(tail).not.toBe("0%");
  });
});

describe("#6233 the display cap cannot invent a pair", () => {
  /**
   * The rule is computed over the FULL served set and then indexed — the same
   * reason `outcomeDisplayNames` is, three lines above it in the page. If it were
   * computed over the visible slice, the top two rows of a longer market would be
   * normalized against each other and the card would print two numbers summing to
   * 100 for a question with five answers.
   *
   * Measured: 0 such cards exist on the hubs today, which is exactly why this
   * needs a guard — nothing on production would go red if it regressed.
   */
  it("the top two of a five-outcome market are NOT normalized", () => {
    const full = [0.555, 0.445, 0.3, 0.2, 0.1];
    const overFull = renderedCardPercents(full).slice(0, 2);
    const overSlice = renderedCardPercents(full.slice(0, 2));
    expect(overFull).not.toEqual(overSlice);
    // The page takes the first of these two.
    expect(overFull).toEqual([renderedCardPercents(full)[0], renderedCardPercents(full)[1]]);
    expect(sum(overFull.map((r, i) => formatProbability(full[i], { rendered: r })))).toBe(101);
  });
});

describe("#6233 the page is actually wired to the rule", () => {
  /**
   * 🔴 THE LIMIT OF THIS ARM, STATED. Everything above exercises the real
   * `renderedCardPercents` / `formatProbability` pair, but NONE of it proves the
   * hub page calls them — which is precisely the shape that let this ship, since
   * the rule has existed since #2831 and this card simply never used it.
   *
   * `OutcomeRow` and `MarketCard` are file-local to a Next.js page module and are
   * not exported, so there is no component to render here. Exporting them purely
   * to be testable would widen the module's surface for the test's convenience.
   * So this arm reads the SOURCE, and says so rather than dressing itself up as a
   * render assertion.
   *
   * It is not decorative: the defect was literally the bare call, so a guard that
   * reddens when the bare call comes back is the regression this needs. It is
   * paired with the behavioural cases above, which is where correctness lives.
   */
  const SOURCE = fs.readFileSync(
    path.join(__dirname, "..", "app", "hub", "[competition]", "page.tsx"),
    "utf8",
  );

  it("the bare per-side call — the defect itself — is gone", () => {
    expect(SOURCE).not.toMatch(/formatProbability\(\s*o\.probability\s*\)/);
  });

  it("the row prints through the UX-P114 rendered seam", () => {
    expect(SOURCE).toMatch(/formatProbability\(o\.probability,\s*\{\s*rendered\s*\}\)/);
  });

  it("the card computes the percents over the FULL served set, not the visible slice", () => {
    expect(SOURCE).toMatch(
      /renderedCardPercents\(\s*market\.top_outcomes\.map\(\(o\) => o\.probability\),?\s*\)/,
    );
    // The slice is what is RENDERED; it must not be what is MEASURED.
    expect(SOURCE).not.toMatch(/renderedCardPercents\([^)]*slice\(/);
  });

  it("the computed percents reach the row", () => {
    expect(SOURCE).toMatch(/rendered=\{outcomePercents\[i\]\s*\?\?\s*null\}/);
  });
});
