// #999 L2-75: pure calibration math (extracted from the /calibration page).

import { describeActivityComparison, ece, mce, monthYear } from "../../lib/calibrationMath";

describe("mce (equal-weighted)", () => {
  test("mean of |error| regardless of n", () => {
    // errors 2, 4 → mean 3.0; n is ignored.
    expect(mce([{ n: 10000, error: 2 }, { n: 3, error: 4 }])).toBeCloseTo(3.0);
  });
  test("uses absolute error", () => {
    expect(mce([{ n: 1, error: -6 }, { n: 1, error: 2 }])).toBeCloseTo(4.0);
  });
  test("empty → 0", () => {
    expect(mce([])).toBe(0);
  });
});

describe("ece (n-weighted)", () => {
  test("n-weighted mean of |error| — big bucket dominates", () => {
    // 10000*2 + 3*40 = 20120; /10003 ≈ 2.01 (a thin 40pp bucket barely moves it).
    expect(ece([{ n: 10000, error: 2 }, { n: 3, error: 40 }])).toBeCloseTo(2.01, 1);
  });
  test("differs from MCE when sizes are lopsided", () => {
    const buckets = [{ n: 10000, error: 1 }, { n: 2, error: 20 }];
    expect(ece(buckets)).toBeLessThan(mce(buckets)); // ECE stays honest; MCE over-reacts
  });
  test("empty / zero-n → 0", () => {
    expect(ece([])).toBe(0);
    expect(ece([{ n: 0, error: 5 }])).toBe(0);
  });
});

// L2-230 / C111 [P1]. The bug this locks down: the page rendered an
// unconditional "active trading is dramatically better calibrated" plus
// `unchangedECE / movedECE` labelled "more accurately calibrated". With the
// live 2026-08-02 payload (moved 1.7pp, unchanged 1.0pp) that printed the
// literal string "0.6x more accurately calibrated" — a ratio below one sold as
// superiority, directly contradicting the two stat cards above it.
describe("describeActivityComparison", () => {
  const cohort = (ece: number, n = 10_000) => ({ ece, n });

  describe("the reported production state", () => {
    // Reproduced from GET /api/calibration on 2026-08-02T03:23Z with the page's
    // own aggregation: moved n=349,310 ECE=1.7162; unchanged n=263,022 ECE=1.0341.
    const live = describeActivityComparison(
      cohort(1.7162, 349_310),
      cohort(1.0341, 263_022)
    );

    // #6176: the direction is still DERIVED — `data-activity-direction` is how
    // the audit rail reads the split — but it is no longer allowed to reach a
    // reader. The assertion that used to demand the ranking now forbids it.
    test("still derives the ordering as a machine fact", () => {
      expect(live.direction).toBe("moved_higher");
    });
    test("but the sentence does not rank the two cohorts", () => {
      expect(live.sentence).not.toMatch(/carries the higher|carries the lower/);
      expect(live.sentence).not.toMatch(/\bhigher calibration error\b/);
      expect(live.sentence).not.toMatch(/\blower calibration error\b/);
    });
    test("leads with both displayed values", () => {
      expect(live.sentence).toContain("1.7pp");
      expect(live.sentence).toContain("1.0pp");
    });
    test("and says why the two numbers cannot answer the question", () => {
      expect(live.sentence).toMatch(/different sets of outcomes/);
      expect(live.sentence).toMatch(/does not tell you/);
    });
    test("the ratio is gone, not merely suppressed", () => {
      expect("ratioText" in live).toBe(false);
      // "1.7x the untraded cohort's" was the sharpest form of the claim.
      expect(live.sentence).not.toMatch(/[0-9]x\b/);
    });
    test("the exact shipped-bug string cannot be produced", () => {
      expect(live.sentence).not.toContain("0.6x");
      expect(live.sentence).not.toMatch(/more accurately calibrated/);
    });
  });

  // Every state the section can reach, and what each must say.
  const cases: Array<{
    name: string;
    moved: { ece: unknown; n: unknown };
    unchanged: { ece: unknown; n: unknown };
    direction: string;
    hasSentence: boolean;
  }> = [
    { name: "changed worse", moved: cohort(2.4), unchanged: cohort(1.2), direction: "moved_higher", hasSentence: true },
    { name: "changed better", moved: cohort(1.2), unchanged: cohort(2.4), direction: "unchanged_higher", hasSentence: true },
    { name: "exactly equal", moved: cohort(1.5), unchanged: cohort(1.5), direction: "tied", hasSentence: true },
    // Tolerance boundary: display precision IS the tolerance. 1.44 and 1.54 both
    // print as different values; 1.44 and 1.4999 both print "1.5" and must tie.
    { name: "tie by rounding (1.4499 vs 1.5001 → 1.4 vs 1.5, still ordered)", moved: cohort(1.4499), unchanged: cohort(1.5001), direction: "unchanged_higher", hasSentence: true },
    { name: "tie by rounding (1.4501 vs 1.5000 → both 1.5)", moved: cohort(1.4501), unchanged: cohort(1.5), direction: "tied", hasSentence: true },
    // Ordered but the ratio would print "1.0x", which reads as "the same".
    { name: "ordered, ratio rounds to 1.0 → ratio suppressed", moved: cohort(9.9), unchanged: cohort(9.8), direction: "moved_higher", hasSentence: true },
    // Zero denominator: a real 0.0pp side makes higher/lower infinite.
    { name: "zero lower side → ordering kept, ratio suppressed", moved: cohort(1.3), unchanged: cohort(0), direction: "moved_higher", hasSentence: true },
    { name: "both zero", moved: cohort(0), unchanged: cohort(0), direction: "tied", hasSentence: true },
    // Missing / empty cohorts: the comparison is suppressed entirely.
    { name: "missing moved ECE", moved: { ece: null, n: 10_000 }, unchanged: cohort(1.0), direction: "unknown", hasSentence: false },
    { name: "missing unchanged ECE", moved: cohort(1.0), unchanged: { ece: undefined, n: 10_000 }, direction: "unknown", hasSentence: false },
    { name: "empty moved cohort (n=0)", moved: cohort(0, 0), unchanged: cohort(1.0), direction: "unknown", hasSentence: false },
    { name: "missing n", moved: cohort(1.0), unchanged: { ece: 1.0, n: null }, direction: "unknown", hasSentence: false },
    // Non-finite: NaN/Infinity render as plausible text if they ever reach copy.
    { name: "NaN moved", moved: cohort(NaN), unchanged: cohort(1.0), direction: "unknown", hasSentence: false },
    { name: "Infinity unchanged", moved: cohort(1.0), unchanged: cohort(Infinity), direction: "unknown", hasSentence: false },
    { name: "-Infinity moved", moved: cohort(-Infinity), unchanged: cohort(1.0), direction: "unknown", hasSentence: false },
    // Poison: ECE is a mean of absolute errors, so a negative one is corrupt
    // input. Refuse it rather than ranking it as "best calibrated".
    { name: "poison negative ECE", moved: cohort(-3.0), unchanged: cohort(1.0), direction: "unknown", hasSentence: false },
    { name: "poison negative n", moved: cohort(1.0, -5), unchanged: cohort(1.0), direction: "unknown", hasSentence: false },
    { name: "poison non-numeric ECE", moved: { ece: "1.0", n: 10_000 }, unchanged: cohort(2.0), direction: "unknown", hasSentence: false },
  ];

  test.each(cases)("$name", ({ moved, unchanged, direction, hasSentence }) => {
    const r = describeActivityComparison(
      moved as { ece: number; n: number },
      unchanged as { ece: number; n: number }
    );
    expect(r.direction).toBe(direction);
    expect(r.sentence === null).toBe(!hasSentence);
  });

  describe("invariants across every case", () => {
    test("no case ever claims superiority or causation", () => {
      for (const c of cases) {
        const s = describeActivityComparison(
          c.moved as { ece: number; n: number },
          c.unchanged as { ece: number; n: number }
        ).sentence;
        if (!s) continue;
        expect(s).not.toMatch(/more accurately|better calibrated|dramatically|improves?\b/i);
      }
    });
    test("a rendered sentence never leaks a non-finite token", () => {
      for (const c of cases) {
        const s = describeActivityComparison(
          c.moved as { ece: number; n: number },
          c.unchanged as { ece: number; n: number }
        ).sentence;
        if (!s) continue;
        expect(s).not.toMatch(/NaN|Infinity|undefined|null/);
      }
    });
    // #6176. The ratio invariant that stood here proved the RATIO was honest.
    // The ratio is gone, so this asserts the stronger property that replaced
    // it: no case emits one at all, in any form a reader could read as one.
    test("no case emits a ratio, a multiple, or a comparative", () => {
      for (const c of cases) {
        const r = describeActivityComparison(
          c.moved as { ece: number; n: number },
          c.unchanged as { ece: number; n: number }
        );
        expect("ratioText" in r).toBe(false);
        if (!r.sentence) continue;
        expect(r.sentence).not.toMatch(/[0-9]x\b|\btimes\b/);
        expect(r.sentence).not.toMatch(/\b(higher|lower|worse|best|worst|outperform\w*)\b/i);
      }
    });

    // #6176's load-bearing guard, and the one that fails if anybody reinstates
    // a ranking in any wording at all. Whichever cohort is in front, the
    // sentence must be the SAME sentence — so once the two numbers are masked
    // out, the two strings are character-for-character identical. A ranking
    // cannot survive that, because a ranking has to name a side.
    test("the sentence differs only in its numbers, never in its claim", () => {
      const mask = (s: string | null) => (s ?? "").replace(/[0-9]+\.[0-9]pp/g, "#pp");
      const movedWorse = describeActivityComparison(cohort(2.4), cohort(1.2));
      const unchangedWorse = describeActivityComparison(cohort(1.2), cohort(2.4));
      const tied = describeActivityComparison(cohort(1.5), cohort(1.5));

      // The ordering is still derived...
      expect(movedWorse.direction).toBe("moved_higher");
      expect(unchangedWorse.direction).toBe("unchanged_higher");
      expect(tied.direction).toBe("tied");

      // ...and is invisible in what the reader is handed.
      expect(mask(movedWorse.sentence)).toBe(mask(unchangedWorse.sentence));
      expect(mask(tied.sentence)).toBe(mask(movedWorse.sentence));

      // Non-vacuity: the mask must not have eaten the whole sentence, and the
      // numbers themselves must still be there unmasked in each one.
      expect(mask(movedWorse.sentence).length).toBeGreaterThan(60);
      expect(movedWorse.sentence).toContain("2.4pp");
      expect(movedWorse.sentence).toContain("1.2pp");
      expect(unchangedWorse.sentence).toContain("2.4pp");
      expect(unchangedWorse.sentence).toContain("1.2pp");
    });
  });
});

describe("monthYear", () => {
  test("formats ISO to Mon YYYY", () => {
    expect(monthYear("2026-07-09T00:00:00Z")).toMatch(/Jul 2026/);
  });
  test("echoes unparseable input", () => {
    expect(monthYear("not-a-date")).toBe("not-a-date");
  });
});
